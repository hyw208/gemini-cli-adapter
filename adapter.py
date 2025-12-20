import os
import json
from flask import Flask, request, jsonify
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
            tools.append({
                "type": "function",
                "function": {
                    "name": func.get('name'),
                    "description": func.get('description'),
                    "parameters": func.get('parameters') or {"type": "object", "properties": {}}
                }
            })

    openai_req = {
        "model": model,
        "messages": messages,
        "temperature": generation_config.get('temperature'),
        "max_tokens": generation_config.get('maxOutputTokens'),
        "top_p": generation_config.get('topP'),
        "stop": generation_config.get('stopSequences'),
        "tools": tools if tools else None
    }
    return {k: v for k, v in openai_req.items() if v is not None}

def openai_to_google_response(openai_resp):
    """Translates OpenAI ChatCompletionResponse to Google GenerateContentResponse"""
    choices = openai_resp.choices
    candidates = []
    
    for choice in choices:
        message = choice.message
        content = message.content
        
        candidate = {
            "content": {
                "parts": [{"text": content} if content else {}],
                "role": "model"
            },
            "finishReason": getattr(choice, 'finish_reason', 'STOP').upper() if getattr(choice, 'finish_reason', None) else 'STOP',
            "index": getattr(choice, 'index', 0),
            "safetyRatings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"}
            ]
        }
        
        # Handle tool calls
        tool_calls = getattr(message, 'tool_calls', [])
        if tool_calls:
            # Clear text part if it's empty/None when tool calls exist
            if not content:
                candidate["content"]["parts"] = []
            
            for tool_call in tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except:
                    args = {}
                    
                function_call = {
                    "functionCall": {
                        "name": tool_call.function.name,
                        "args": args
                    }
                }
                candidate["content"]["parts"].append(function_call)
                
        candidates.append(candidate)
    
    # Extract usage
    usage = getattr(openai_resp, 'usage', None)
    usage_metadata = {}
    if usage:
        usage_metadata = {
            "promptTokenCount": getattr(usage, 'prompt_tokens', 0),
            "candidatesTokenCount": getattr(usage, 'completion_tokens', 0),
            "totalTokenCount": getattr(usage, 'total_tokens', 0)
        }
        
    return {
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
        
        # Check if streaming is requested
        is_streaming = 'streamGenerateContent' in request.path or request.args.get('alt') == 'sse'
        
        if is_streaming:
            def generate():
                try:
                    print("Starting stream generation...")
                    response = litellm.completion(
                        **openai_req,
                        stream=True
                    )
                    for chunk in response:
                        # Translate chunk to Google format
                        content = chunk.choices[0].delta.content or ""
                        
                        google_chunk = {
                            "candidates": [{
                                "content": {
                                    "parts": [{"text": content}],
                                    "role": "model"
                                },
                                "finishReason": (chunk.choices[0].finish_reason.upper() if getattr(chunk.choices[0], 'finish_reason', None) else None),
                                "index": 0
                            }]
                        }
                        yield f"data: {json.dumps(google_chunk)}\n\n"
                except Exception as e:
                    print(f"Streaming Error: {e}")
                    # In streaming, we yield one last candidate with the error message
                    # so the user actually sees it in the CLI
                    error_chunk = {
                        "candidates": [{
                            "content": {
                                "parts": [{"text": f"\n\n❌ Error: {str(e)}"}],
                                "role": "model"
                            },
                            "finishReason": "OTHER"
                        }]
                    }
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
