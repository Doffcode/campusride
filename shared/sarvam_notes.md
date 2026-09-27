# Sarvam API notes (verified from docs.sarvam.ai, Sept 2026)

> Use ONLY what is written here. Do NOT use endpoints, model names, or SDKs from memory.
> Do NOT install the `sarvamai` SDK. We call the REST API with `httpx` so the code is simple and visible.
> Items marked **[CHECK]** were not fully confirmed in the docs. `shared/sarvam_smoke.py` checks them with a real key.

## Common

- Base URL: `https://api.sarvam.ai`
- Auth header on every request: `api-subscription-key: <key>`
- The chat endpoint also wants `Authorization: Bearer <key>`. Send **both** headers to the chat endpoint.
- Key comes from env var `SARVAM_API_KEY`. Never hardcode it and never print it.
- Timeouts: use `httpx.Client(timeout=30.0)`. On any non-2xx, raise an error that includes the status code and `response.text[:300]`.

---

## 1. Speech-to-Text (STT). Model: Saaras v3

- `POST https://api.sarvam.ai/speech-to-text`
- Body: **multipart/form-data** (NOT JSON)

| field | value we use | notes |
|---|---|---|
| `file` | the audio bytes, with a filename | formats: wav, mp3, ogg, opus, flac, m4a, **webm** (browser MediaRecorder output works) |
| `model` | `saaras:v3` | |
| `mode` | `transcribe` | keeps the original language. Other modes: translate, verbatim, translit, codemix |
| `language_code` | e.g. `hi-IN` | or `unknown` for auto-detect |

- Keep recordings under **25 seconds** **[CHECK]**. The REST endpoint is for short clips.
- Response JSON:
```json
{"request_id": "…", "transcript": "नमस्ते, आप कैसे हैं?", "language_code": "hi-IN", "language_probability": 0.98}
```

```python
import httpx, os
def stt(audio: bytes, filename: str, lang: str) -> str:
    r = httpx.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
        files={"file": (filename, audio)},
        data={"model": "saaras:v3", "mode": "transcribe", "language_code": lang},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["transcript"]
```

---

## 2. Chat completion (LLM). Model: Sarvam-105B

- `POST https://api.sarvam.ai/v1/chat/completions` (OpenAI-style)
- Headers: `api-subscription-key: <key>`, `Authorization: Bearer <key>`, `Content-Type: application/json`
- Models: `sarvam-105b` (128K context, flagship) or `sarvam-105b-conversations` (32K, tuned for real-time voice agents). We use `sarvam-105b` by default. Env var `SARVAM_CHAT_MODEL` can override it.

| field | value we use | notes |
|---|---|---|
| `model` | `sarvam-105b` | |
| `messages` | `[{"role":"system","content":…},{"role":"user","content":…}]` | |
| `temperature` | `0.0` | we want deterministic extraction |
| `max_tokens` | `800` | |
| `response_format` | `{"type": "json_object"}` | JSON mode is supported |
| `reasoning_effort` | `"low"` | allowed: `"low"`, `"medium"` (default), `"high"`, `"max"`. Docs say it can be disabled with `null` **[CHECK]**. Use `"low"` for speed. |

- Response JSON:
```json
{"id": "…", "model": "sarvam-105b", "object": "chat.completion",
 "choices": [{"index": 0, "finish_reason": "stop",
   "message": {"role": "assistant", "content": "{\"pickup\": …}", "reasoning_content": "…optional…"}}],
 "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30}}
```
- Read `choices[0]["message"]["content"]`. **It can be `null`** if reasoning used up all tokens. Treat null/empty as a failure.
- Ignore `reasoning_content`.
- Defensive parsing: the content might still contain `<think>…</think>` or markdown fences. Strip them, then take the text from the first `{` to the last `}` and `json.loads` it.

```python
def chat(messages: list[dict]) -> str:
    key = os.environ["SARVAM_API_KEY"]
    r = httpx.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
        json={"model": os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b"),
              "messages": messages, "temperature": 0.0, "max_tokens": 800,
              "response_format": {"type": "json_object"}, "reasoning_effort": "low"},
        timeout=30.0,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"].get("content")
    if not content:
        raise RuntimeError("empty LLM content")
    return content
```

---

## 3. Text-to-Speech (TTS). Model: Bulbul v3

- `POST https://api.sarvam.ai/text-to-speech`
- Body: JSON

| field | value we use | notes |
|---|---|---|
| `text` | reply text | max 2500 chars for bulbul:v3 |
| `language_code` | e.g. `hi-IN` | **Only these 11:** bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, od-IN, pa-IN, ta-IN, te-IN. For any other language use `en-IN`. |
| `model` | `bulbul:v3` | |
| `speaker` | `shubh` | default voice for v3. Others include anushka, priya, kavya, rahul, amit, … |
| `pace` | `1.0` | 0.5–2.0 |
| `output_audio_codec` | `wav` | |

- Response JSON: `{"request_id": "…", "audios": ["<base64 WAV>"]}`. Use `audios[0]`.
- In the browser, play it with: `new Audio("data:audio/wav;base64," + b64).play()`

```python
def tts(text: str, lang: str) -> str:
    r = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
        json={"text": text, "language_code": lang, "model": "bulbul:v3",
              "speaker": "shubh", "pace": 1.0, "output_audio_codec": "wav"},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["audios"][0]
```

---

## 4. Translate (Mayura). OPTIONAL, not in the MVP

- `POST https://api.sarvam.ai/translate`, JSON body:
  `{"input": "...", "source_language_code": "en-IN", "target_language_code": "hi-IN", "model": "mayura:v1", "mode": "formal"}`
- Max 1000 chars (mayura:v1). Response: `{"request_id": "…", "translated_text": "…", "source_language_code": "en-IN"}`
- Note: the translate docs list Kannada as `ka-IN`, but STT/TTS use `kn-IN` **[CHECK]**.

---

## Language codes we support in the UI

`en-IN, hi-IN, ta-IN, te-IN, kn-IN, bn-IN, mr-IN`. STT, TTS, and chat support all of them.

## Other things to know

- Real-time streaming STT exists over WebSocket (`saaras:v3-realtime`). **Not used in the MVP.** It's only a pitch point.
- If an API call fails during the demo, the app must still work. Text booking never touches Sarvam, and voice falls back to a rule-based intent (see TASK_C).
