import os
import json
from flask import Flask, request, jsonify, Response
import litellm
from dotenv import load_dotenv

# Load environment variables if run directly
load_dotenv()

app = Flask(__name__)

@app.before_request
def log_request_info():
    print(f"DEBUG: Incoming {request.method} {request.path}")
    if request.is_json:
        print(f"DEBUG: Body: {json.dumps(request.json, indent=2)}")

# Directory for debug logs
DEBUG_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_logs")

def save_debug_json(filename, data):
    """Saves data to a JSON file in the debug_logs directory if DEBUG_SAVE_JSON is enabled"""
    if os.getenv('DEBUG_SAVE_JSON', '').lower() == 'true':
        if not os.path.exists(DEBUG_LOGS_DIR):
            os.makedirs(DEBUG_LOGS_DIR)
        filepath = os.path.join(DEBUG_LOGS_DIR, filename)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"DEBUG: Saved {filename}")

def trim_payload_for_small_models(openai_req, model):
    """
    Trim request payload for models with small context limits (e.g., GitHub models: 8000 tokens)
    Returns a trimmed copy of the request.
    """
    # Models with small input limits (approximate token limit)
    SMALL_CONTEXT_MODELS = {
        'github/': 6000,  # GitHub models have 8000 token limit, leave some margin
    }
    
    # Check if this model needs trimming
    trim_limit = None
    for prefix, limit in SMALL_CONTEXT_MODELS.items():
        if model.startswith(prefix):
            trim_limit = limit
            break
    
    if not trim_limit:
        return openai_req  # No trimming needed
    
    trimmed_req = openai_req.copy()
    
    # 1. Remove or limit tools (MCP tools can be very large)
    tools = trimmed_req.get('tools', [])
    if tools:
        tool_count = len(tools)
        # Keep only essential tools or remove all if too many
        if tool_count > 10:
            print(f"DEBUG: Removing {tool_count} tools for small-context model")
            trimmed_req['tools'] = None
        elif tool_count > 5:
            # Keep only first 5 tools
            print(f"DEBUG: Trimming tools from {tool_count} to 5 for small-context model")
            trimmed_req['tools'] = tools[:5]
    
    # 2. Trim system message if too long (rough estimate: 4 chars ≈ 1 token)
    messages = trimmed_req.get('messages', [])
    if messages and messages[0].get('role') == 'system':
        system_content = messages[0].get('content', '')
        estimated_tokens = len(system_content) // 4
        if estimated_tokens > 2000:
            # Trim to first 2000 tokens worth
            trimmed_content = system_content[:8000] + "\n...[System instructions trimmed for model compatibility]"
            print(f"DEBUG: Trimmed system message from ~{estimated_tokens} to ~2000 tokens")
            trimmed_req['messages'] = [{"role": "system", "content": trimmed_content}] + messages[1:]
    
    return trimmed_req

def google_to_openai_request(google_req, model):
    """Translates Google GenerateContentRequest to OpenAI ChatCompletionRequest"""
    messages = []
    
    # 1. Handle systemInstruction
    system_instruction = google_req.get('systemInstruction', {})
    if system_instruction:
        parts = system_instruction.get('parts', [])
        text = "\n".join([p.get('text', '') for p in parts if 'text' in p])
        if text:
            messages.append({"role": "system", "content": text})
    
    # 2. Handle contents (history + current prompt)
    contents = google_req.get('contents', [])
    for content in contents:
        role = content.get('role', 'user')
        if role == 'model': role = 'assistant'
        if role == 'function': role = 'tool'
            
        parts = content.get('parts', [])
        text_content = ""
        tool_calls = []
        
        for part in parts:
            if 'text' in part:
                text_content += part['text']
            elif 'functionCall' in part:
                fc = part['functionCall']
                call_id = f"call_{fc['name']}"
                # Ensure args is a dict
                args = fc.get('args', {})
                if not isinstance(args, dict):
                    args = {}
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": fc['name'],
                        "arguments": json.dumps(args)
                    }
                })
            elif 'functionResponse' in part:
                fr = part['functionResponse']
                # Ensure response exists and is a dict
                resp_data = fr.get('response', {})
                if not isinstance(resp_data, dict):
                    resp_data = {"result": str(resp_data)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_{fr['name']}",
                    "content": json.dumps(resp_data)
                })
                role = 'tool' 

        if role == 'tool':
            continue
            
        if text_content or tool_calls:
            msg = {"role": role, "content": text_content if text_content else None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.append(msg)
        
    # Extract config
    generation_config = google_req.get('generationConfig', {})
    
    # Extract safety settings (logged for now, as LiteLLM handles them per-provider)
    safety_settings = google_req.get('safetySettings', [])
    if safety_settings:
        print(f"DEBUG: Received safety settings: {json.dumps(safety_settings)}")

    # Extract tools (definitions)
    tools = []
    google_tools = google_req.get('tools', [])
    for tool in google_tools:
        for func in tool.get('functionDeclarations', []):
            # Google AI SDK / CLI might send parameters as 'parameters' or 'parametersJsonSchema'
            params = func.get('parameters') or func.get('parametersJsonSchema')
            tools.append({
                "type": "function",
                "function": {
                    "name": func.get('name'),
                    "description": func.get('description'),
                    "parameters": params or {"type": "object", "properties": {}}
                }
            })

    openai_req = {
        "model": model,
        "messages": messages,
        "temperature": generation_config.get('temperature'),
        "max_tokens": generation_config.get('maxOutputTokens'),
        "top_p": generation_config.get('topP'),
        "stop": generation_config.get('stopSequences'),
        "presence_penalty": generation_config.get('presencePenalty'),
        "frequency_penalty": generation_config.get('frequencyPenalty'),
        "tools": tools if tools else None,
        "stream_options": {"include_usage": True}
    }
    return {k: v for k, v in openai_req.items() if v is not None}

def openai_to_google_response(openai_resp):
    """Translates OpenAI ChatCompletionResponse to Google GenerateContentResponse"""
    choices = openai_resp.choices
    candidates = []
    
    # Map OpenAI finish reasons to Google
    FINISH_REASON_MAP = {
        'stop': 'STOP',
        'length': 'MAX_TOKENS',
        'content_filter': 'SAFETY',
        'tool_calls': 'STOP',
        'function_call': 'STOP'
    }
    
    for choice in choices:
        message = choice.message
        content = message.content
        
        # 1. Map Finish Reason
        openai_finish_reason = getattr(choice, 'finish_reason', 'stop')
        finish_reason = FINISH_REASON_MAP.get(openai_finish_reason, 'STOP')
            
        # 2. Handle Parts (Text + Tool Calls)
        parts = []
        if content:
            parts.append({"text": content})
            
        tool_calls = getattr(message, 'tool_calls', [])
        if tool_calls:
            for tool_call in tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except:
                    args = {}
                    
                parts.append({
                    "functionCall": {
                        "name": tool_call.function.name,
                        "args": args
                    }
                })
        
        if not parts:
            parts = [{"text": ""}]
            
        candidates.append({
            "content": {
                "parts": parts,
                "role": "model"
            },
            "finishReason": finish_reason,
            "index": getattr(choice, 'index', 0),
            "safetyRatings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"}
            ]
        })
    
    # Extract usage
    usage = getattr(openai_resp, 'usage', None)
    usage_metadata = {}
    if usage:
        usage_metadata = {
            "promptTokenCount": getattr(usage, 'prompt_tokens', 0),
            "candidatesTokenCount": getattr(usage, 'completion_tokens', 0),
            "totalTokenCount": getattr(usage, 'total_tokens', 0)
        }
    
    response = {
        "candidates": candidates,
        "usageMetadata": usage_metadata,
        "modelVersion": "gemini-2.0-flash-001",
        "promptFeedback": {
            "safetyRatings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"}
            ]
        }
    }
    print(f"DEBUG: Translated Google Response: {json.dumps(response)}")
    return response

@app.route('/v1beta/models/<path:model>:generateContent', methods=['POST'])
@app.route('/v1beta/models/<path:model>:streamGenerateContent', methods=['POST'])
@app.route('/v1/models/<path:model>:generateContent', methods=['POST'])
@app.route('/v1/models/<path:model>:streamGenerateContent', methods=['POST'])
def generate_content(model):
    """Handle generateContent request"""
    try:
        print(f"Received request for model: {model}")
        print(f"Request Headers: {request.headers}")
        google_req = request.json
        save_debug_json("google_request.json", google_req)
        
        # Smart model routing for different providers
        # If model already has a provider prefix (e.g., deepseek/, openai/), use it as-is
        # Otherwise, detect the provider based on model name patterns
        if '/' in model:
            # Normalize github_copilot/ to github/ for litellm
            if model.startswith('github_copilot/'):
                target_model = model.replace('github_copilot/', 'github/', 1)
            else:
                # Model already has provider prefix (e.g., "deepseek/deepseek-chat")
                target_model = model
        elif model.startswith('gpt-') or model.startswith('o1-'):
            # OpenAI models (gpt-4, gpt-3.5-turbo, gpt-4o-mini, o1-preview, etc.)
            target_model = f"openai/{model}"
        else:
            # No prefix and not OpenAI, assume Google Gemini
            target_model = f"gemini/{model}"
        
        openai_req = google_to_openai_request(google_req, target_model)
        save_debug_json("openai_request.json", openai_req)
        
        # Trim payload for models with small context limits
        openai_req = trim_payload_for_small_models(openai_req, target_model)
        
        # Explicitly pass API keys for providers that need them
        # LiteLLM can use environment variables, but being explicit is more reliable
        api_key = None
        if target_model.startswith('github/'):
            api_key = os.getenv('GITHUB_API_KEY')
        elif target_model.startswith('openai/'):
            api_key = os.getenv('OPENAI_API_KEY')
        elif target_model.startswith('groq/'):
            api_key = os.getenv('GROQ_API_KEY')
        elif target_model.startswith('anthropic/'):
            api_key = os.getenv('ANTHROPIC_API_KEY')
        elif target_model.startswith('deepseek/'):
            api_key = os.getenv('DEEPSEEK_API_KEY')
        elif target_model.startswith('together_ai/'):
            api_key = os.getenv('TOGETHER_API_KEY')
        elif target_model.startswith('gemini/'):
            api_key = os.getenv('GEMINI_API_KEY')
        
        # Add api_key to request if found
        if api_key:
            openai_req['api_key'] = api_key

        # Check if streaming is requested
        is_streaming = 'streamGenerateContent' in request.path or request.args.get('alt') == 'sse'
        
        if is_streaming:
            def generate():
                try:
                    print("DEBUG: Starting incremental stream generation...")
                    response = litellm.completion(
                        **openai_req,
                        stream=True
                    )
                    
                    accumulated_tool_calls = {}
                    role_sent = False
                    
                    for chunk in response:
                        # 0. Handle Usage (can be in any chunk, typically the last)
                        if hasattr(chunk, 'usage') and chunk.usage:
                            usage = chunk.usage
                            usage_meta = {
                                "promptTokenCount": getattr(usage, 'prompt_tokens', 0),
                                "candidatesTokenCount": getattr(usage, 'completion_tokens', 0),
                                "totalTokenCount": getattr(usage, 'total_tokens', 0)
                            }
                            data_str = f"data: {json.dumps({'usageMetadata': usage_meta})}\n\n"
                            print(f"DEBUG: Yielding usage chunk: {data_str}")
                            yield data_str

                        if not chunk.choices:
                            continue
                            
                        delta = chunk.choices[0].delta
                        finish_reason = getattr(chunk.choices[0], 'finish_reason', None)
                        
                        # 1. Text Content
                        content = getattr(delta, 'content', None) or ""
                        if content:
                            google_chunk = {
                                "candidates": [{
                                    "content": {
                                        "parts": [{"text": content}],
                                        "role": "model"
                                    },
                                    "index": 0
                                }]
                            }
                            data_str = f"data: {json.dumps(google_chunk)}\n\n"
                            print(f"DEBUG: Yielding text chunk: {data_str[:100]}...")
                            yield data_str
                            
                        # 2. Tool Calls
                        tool_calls_delta = getattr(delta, 'tool_calls', None)
                        if tool_calls_delta:
                            for tc_delta in tool_calls_delta:
                                idx = tc_delta.index
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {
                                        "name": getattr(tc_delta.function, 'name', None),
                                        "arguments": ""
                                    }
                                if tc_delta.function.arguments:
                                    accumulated_tool_calls[idx]["arguments"] += tc_delta.function.arguments
                        
                        # 3. Handle Finish
                        if finish_reason:
                            print(f"DEBUG: Stream finished. Reason: {finish_reason}")
                            
                            FINISH_REASON_MAP = {
                                'stop': 'STOP',
                                'length': 'MAX_TOKENS',
                                'content_filter': 'SAFETY',
                                'tool_calls': 'STOP',
                                'function_call': 'STOP'
                            }
                            finish_reason_upper = FINISH_REASON_MAP.get(finish_reason, 'STOP')
                            
                            parts = []
                            # If we have tool calls, include them
                            if accumulated_tool_calls:
                                for idx in sorted(accumulated_tool_calls.keys()):
                                    tc = accumulated_tool_calls[idx]
                                    try:
                                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                                    except:
                                        args = {}
                                    parts.append({
                                        "functionCall": {
                                            "name": tc["name"],
                                            "args": args
                                        }
                                    })
                            
                            # Final terminal chunk 
                            final_chunk = {
                                "candidates": [{
                                    "finishReason": finish_reason_upper,
                                    "index": 0
                                }]
                            }
                            
                            # If we have parts (tool calls), insert them into this final chunk
                            if parts:
                                final_chunk["candidates"][0]["content"] = {
                                    "parts": parts,
                                    "role": "model"
                                }
                                # Log specifically for tool calls
                                data_str = f"data: {json.dumps(final_chunk)}\n\n"
                                print(f"DEBUG: Yielding combined tool+stop chunk: {data_str}")
                                yield data_str
                            else:
                                # Just a stop reason
                                data_str = f"data: {json.dumps(final_chunk)}\n\n"
                                print(f"DEBUG: Yielding final stop chunk: {data_str}")
                                yield data_str
                            
                except Exception as e:
                    error_msg = f"Adapter Error: {type(e).__name__}: {str(e)}"
                    print(f"DEBUG: Streaming Error: {error_msg}")
                    # Try to yield a message to the CLI so it doesn't just hang
                    error_chunk = {
                        "candidates": [{
                            "content": {
                                "parts": [{"text": f"\n\n[Error from Adapter]: {error_msg}\n\nThis is often due to provider rate limits or configuration issues."}],
                                "role": "model"
                            },
                            "finishReason": "OTHER"
                        }]
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    error_chunk = {"error": {"code": 500, "message": str(e)}}
                    yield f"data: {json.dumps(error_chunk)}\n\n"
            
            return app.response_class(generate(), mimetype='text/event-stream')
            
        else:
            # Non-streaming
            response = litellm.completion(**openai_req)
            
            # Save raw OpenAI response for analysis
            save_debug_json("openai_response.json", response.model_dump())
            
            google_resp = openai_to_google_response(response)
            save_debug_json("google_response.json", google_resp)
            
            return jsonify(google_resp)
            
    except Exception as e:
        print(f"Adapter Error: {e}")
        # Return standard Google API error format
        status_code = 500
        if hasattr(e, 'status_code'):
            status_code = e.status_code
            
        error_response = {
            "error": {
                "code": status_code,
                "message": str(e),
                "status": "INTERNAL"
            }
        }
        return jsonify(error_response), status_code

@app.route('/v1beta/models', methods=['GET'])
@app.route('/v1/models', methods=['GET'])
def list_models():
    """Handle list models request"""
    return jsonify({
        "models": [
            {
                "name": "models/gemini-2.0-flash-001",
                "version": "001",
                "displayName": "Gemini 2.0 Flash",
                "description": "Embedded LiteLLM",
                "supportedGenerationMethods": ["generateContent"]
            }
        ]
    })

if __name__ == '__main__':
    print("🚀 Starting Embedded Gemini-LiteLLM Adapter on port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)
