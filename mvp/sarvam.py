"""Thin Sarvam AI REST client (see shared/sarvam_notes.md). Every failure becomes SarvamError."""

import os
from pathlib import Path

import httpx

BASE = "https://api.sarvam.ai"
TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


class SarvamError(Exception):
    pass


def _load_dotenv() -> None:
    """Let the key live in a .env file (repo root or mvp/) so nobody has to set env vars at the venue."""
    for p in (Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                k, _, v = line.partition("=")
                if k.strip() and v.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")


_load_dotenv()


def has_key() -> bool:
    return bool(os.environ.get("SARVAM_API_KEY"))


def _key() -> str:
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise SarvamError("SARVAM_API_KEY not set")
    return key


def _post(api: str, url: str, timeout: float, **kw) -> dict:
    try:
        r = httpx.post(url, timeout=timeout, **kw)
    except httpx.HTTPError as e:
        raise SarvamError(f"{api} failed: {type(e).__name__}") from e
    if r.status_code >= 300:
        raise SarvamError(f"{api} failed: {r.status_code} {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise SarvamError(f"{api} failed: bad JSON") from e


def stt(audio: bytes, filename: str, lang: str) -> tuple[str, str]:
    """Returns (transcript, detected_language_code)."""
    data = _post("STT", f"{BASE}/speech-to-text", 30.0,
                 headers={"api-subscription-key": _key()},
                 files={"file": (filename, audio)},
                 data={"model": "saaras:v3", "mode": "transcribe", "language_code": lang or "unknown"})
    transcript = data.get("transcript")
    if not isinstance(transcript, str):
        raise SarvamError("STT failed: no transcript")
    return transcript, data.get("language_code") or lang


def chat(messages: list[dict]) -> str:
    key = _key()
    data = _post("Chat", f"{BASE}/v1/chat/completions", 20.0,
                 headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
                 json={"model": os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b"),
                       "messages": messages, "temperature": 0.0, "max_tokens": 800,
                       "response_format": {"type": "json_object"},
                       "reasoning_effort": os.environ.get("SARVAM_REASONING", "low")})
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise SarvamError("Chat failed: unexpected response") from e
    if not content:
        raise SarvamError("Chat failed: empty content")
    return content


def tts(text: str, lang: str) -> str:
    """Returns base64 WAV."""
    data = _post("TTS", f"{BASE}/text-to-speech", 30.0,
                 headers={"api-subscription-key": _key()},
                 json={"text": text[:2400], "language_code": lang if lang in TTS_LANGS else "en-IN",
                       "model": "bulbul:v3", "speaker": os.environ.get("SARVAM_SPEAKER", "shubh"),
                       "pace": 1.05, "output_audio_codec": "wav"})
    try:
        return data["audios"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise SarvamError("TTS failed: no audio") from e
