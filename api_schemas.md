# API Schema Research & Comparison

## 1. OpenAI Chat Completions API (v1)

### Request Schema
```json
{
  "model": "string (Required)",
  "messages": [
    {
      "role": "debug/system/user/assistant/tool",
      "content": "string or array of parts",
      "name": "string (Optional)",
      "tool_call_id": "string (Required for tool role)",
      "tool_calls": [
        {
          "id": "string",
          "type": "function",
          "function": {
            "name": "string",
            "arguments": "string (JSON)"
          }
        }
      ]
    }
  ],
  "frequency_penalty": "number (-2.0 to 2.0)",
  "logit_bias": "object",
  "logprobs": "boolean",
  "top_logprobs": "integer (0-20)",
  "max_tokens": "integer",
  "n": "integer",
  "presence_penalty": "number (-2.0 to 2.0)",
  "response_format": {
    "type": "text | json_object | json_schema",
    "json_schema": {
        "name": "string",
        "strict": "boolean",
        "schema": "object"
    }
  },
  "seed": "integer",
  "service_tier": "auto | default",
  "stop": "string or array of strings",
  "stream": "boolean",
  "stream_options": { "include_usage": "boolean" },
  "temperature": "number (0-2)",
  "top_p": "number (0-1)",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "string",
        "description": "string",
        "parameters": "object (JSON Schema)"
      }
    }
  ],
  "tool_choice": "none | auto | required | object",
  "parallel_tool_calls": "boolean",
  "user": "string"
}
```

### Response Schema (Non-Streaming)
```json
{
  "id": "string",
  "choices": [
    {
      "finish_reason": "stop | length | tool_calls | content_filter | function_call",
      "index": "integer",
      "message": {
        "role": "assistant",
        "content": "string",
        "tool_calls": "array of tool_call objects"
      },
      "logprobs": "object"
    }
  ],
  "created": "integer (Unix timestamp)",
  "model": "string",
  "system_fingerprint": "string",
  "object": "chat.completion",
  "usage": {
    "completion_tokens": "integer",
    "prompt_tokens": "integer",
    "total_tokens": "integer",
    "completion_tokens_details": {
        "reasoning_tokens": "integer",
        "accepted_prediction_tokens": "integer",
        "rejected_prediction_tokens": "integer"
    },
    "prompt_tokens_details": {
        "cached_tokens": "integer",
        "audio_tokens": "integer"
    }
  },
  "service_tier": "string"
}
```

---

## 2. Google Gemini GenerateContent API (v1beta)

### Request Schema
```json
{
  "contents": [
    {
      "role": "user | model",
      "parts": [
        {
          "text": "string",
          "inlineData": { "mimeType": "string", "data": "string (base64)" },
          "fileData": { "mimeType": "string", "fileUri": "string" },
          "functionCall": { "name": "string", "args": "object" },
          "functionResponse": { "name": "string", "response": "object" }
        }
      ]
    }
  ],
  "tools": [
    {
      "functionDeclarations": [
        {
          "name": "string",
          "description": "string",
          "parameters": "object (JSON Schema)"
        }
      ],
      "codeExecution": {},
      "googleSearchRetrieval": {}
    }
  ],
  "toolConfig": {
    "functionCallingConfig": {
      "mode": "ANY | NONE | AUTO",
      "allowedFunctionNames": ["string"]
    }
  },
  "safetySettings": [
    {
      "category": "HARM_CATEGORY_...",
      "threshold": "BLOCK_..."
    }
  ],
  "systemInstruction": {
    "role": "system",
    "parts": [{ "text": "string" }]
  },
  "generationConfig": {
    "stopSequences": ["string"],
    "responseMimeType": "string",
    "responseSchema": "object",
    "candidateCount": "integer",
    "maxOutputTokens": "integer",
    "temperature": "number",
    "topP": "number",
    "topK": "integer",
    "presencePenalty": "number",
    "frequencyPenalty": "number",
    "responseLogprobs": "boolean",
    "logprobs": "integer",
    "enableEnhancedNetworkSearch": "boolean",
    "thinkingConfig": { "thinkingLevel": "integer" }
  },
  "cachedContent": "string"
}
```

### Response Schema
```json
{
  "candidates": [
    {
      "content": {
        "role": "model",
        "parts": [
          { "text": "string" },
          { "functionCall": { "name": "string", "args": "object" } }
        ]
      },
      "finishReason": "STOP | MAX_TOKENS | SAFETY | RECITATION | OTHER",
      "index": "integer",
      "safetyRatings": "array",
      "citationMetadata": "object",
      "tokenCount": "integer",
      "groundingMetadata": "object",
      "avgLogprobs": "number",
      "logprobsResult": "object"
    }
  ],
  "usageMetadata": {
    "promptTokenCount": "integer",
    "candidatesTokenCount": "integer",
    "totalTokenCount": "integer",
    "cachedContentTokenCount": "integer"
  },
  "modelVersion": "string",
  "promptFeedback": {
    "blockReason": "SAFETY | OTHER",
    "safetyRatings": "array"
  },
  "responseId": "string"
}
```

---

## 3. Comparison and Differences

| Feature | OpenAI Chat Completions | Google Gemini GenerateContent | Mapping |
| :--- | :--- | :--- | :--- |
| **Finish Reason** | `stop` | `STOP` | `stop` -> `STOP` |
| **Finish Reason** | `length` | `MAX_TOKENS` | `length` -> `MAX_TOKENS` |
| **Finish Reason** | `content_filter` | `SAFETY` | `content_filter` -> `SAFETY` |
| **Finish Reason** | `tool_calls` | `STOP` | `tool_calls` -> `STOP` |
| **Usage** | `prompt_tokens` | `promptTokenCount` | Direct mapping |
| **Usage** | `completion_tokens` | `candidatesTokenCount`| Direct mapping |
| **Usage** | `total_tokens` | `totalTokenCount` | Direct mapping |
| **Part Type** | `content: string` | `parts: [{text: ...}]` | Structural translation |
| **Part Type** | `tool_calls` | `parts: [{functionCall: ...}]` | Structural translation |
| **Role (User)** | `user` | `user` | Same |
| **Role (AI)** | `assistant` | `model` | `assistant` <-> `model` |
| **Role (System)** | `system` | `systemInstruction` | Object move |
| **Role (Tool)** | `role: tool` | `parts: [{functionResponse: ...}]` | Move to part with `role: user` |

### Verified Details:
- **Google FinishReasons**: `STOP`, `MAX_TOKENS`, `SAFETY`, `RECITATION`, `OTHER`, `BLOCKLIST`, `SPII`, `MALFORMED_FUNCTION_CALL`.
- **Google UsageMetadata**: `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, `totalTokenCount`.
- **OpenAI Tool Calls**: Requires `id`, `type: "function"`, and `function: {name, arguments}`.
- **OpenAI Tool Response**: Requires `tool_call_id` and `content`.
- **Google Parts**: Union of `text`, `inlineData`, `fileData`, `functionCall`, `functionResponse`.

---

## 4. Translation Strategy

### Google Request -> OpenAI (Outgoing)
- **Contents -> Messages**:
  - `user` -> `user`
  - `model` -> `assistant`
  - `system_instruction` -> `role: system` (prepend to messages)
  - `functionResponse` -> `role: tool` with `tool_call_id` mapped from `name`.
- **GenerationConfig -> Parameters**:
  - `maxOutputTokens` -> `max_tokens`
  - `stopSequences` -> `stop`
- **Tools**:
  - `functionDeclarations` -> `tools` with `type: function`.

### OpenAI Response -> Google (Incoming)
- **Choices -> Candidates**:
  - `message.content` -> `parts` with `{text: content}`
  - `message.tool_calls` -> `parts` with `{functionCall: ...}`
  - `finish_reason` -> `finishReason` (UPPERCASE and mapped)
- **Usage -> UsageMetadata**:
  - `prompt_tokens` -> `promptTokenCount`
  - `completion_tokens` -> `candidatesTokenCount`
  - `total_tokens` -> `totalTokenCount`
