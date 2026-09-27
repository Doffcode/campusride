"""
Sarvam smoke test. The orchestrator runs this ONCE, with a real key, before launching agents.

    set SARVAM_API_KEY=sk_...        (PowerShell: $env:SARVAM_API_KEY="sk_...")
    python shared/sarvam_smoke.py

What it does:
  1. TTS: turns 3 booking sentences (hi, en, ta) into WAV files in shared/samples/
     (so the voice agent has real test audio without anyone recording).
  2. STT: transcribes those WAVs back and prints the transcripts.
  3. Chat: checks JSON mode + reasoning_effort, and prints latency and raw content.
Every step prints OK/FAIL with timing. Paste the output into shared/sarvam_notes.md if something differs.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = "https://api.sarvam.ai"
KEY = os.environ.get("SARVAM_API_KEY", "")
SAMPLES = Path(__file__).parent / "samples"

SENTENCES = {
    "hi_hostel_a_to_academic": ("hi-IN", "मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है"),
    "en_medical_to_cafeteria": ("en-IN", "I need a ride from the medical center to the cafeteria"),
    "ta_library_to_hostel_b": ("ta-IN", "நான் லைப்ரரியிலிருந்து ஹாஸ்டல் பி போக வேண்டும்"),
    "hi_only_drop": ("hi-IN", "मुझे लाइब्रेरी जाना है"),
}


def step(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"[OK]   {name}  ({time.time() - t:.2f}s)")
        return out
    except Exception as e:  # noqa: BLE001 - smoke test, print everything
        print(f"[FAIL] {name}  ({time.time() - t:.2f}s): {e}")
        return None


def tts(text, lang):
    r = httpx.post(f"{BASE}/text-to-speech", headers={"api-subscription-key": KEY},
                   json={"text": text, "language_code": lang, "model": "bulbul:v3",
                         "speaker": "shubh", "pace": 1.0, "output_audio_codec": "wav"},
                   timeout=30.0)
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    return base64.b64decode(r.json()["audios"][0])


def stt(path, lang):
    r = httpx.post(f"{BASE}/speech-to-text", headers={"api-subscription-key": KEY},
                   files={"file": (path.name, path.read_bytes())},
                   data={"model": "saaras:v3", "mode": "transcribe", "language_code": lang},
                   timeout=30.0)
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    return r.json()


def chat(reasoning_effort):
    body = {
        "model": os.environ.get("SARVAM_CHAT_MODEL", "sarvam-105b"),
        "messages": [
            {"role": "system", "content": 'Return ONLY JSON: {"pickup": <id or null>, "drop": <id or null>, "confidence": <0..1>}. Valid ids: hostel_a, library, academic_block.'},
            {"role": "user", "content": "मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है"},
        ],
        "temperature": 0.0, "max_tokens": 800,
        "response_format": {"type": "json_object"},
        "reasoning_effort": reasoning_effort,
    }
    r = httpx.post(f"{BASE}/v1/chat/completions",
                   headers={"api-subscription-key": KEY, "Authorization": f"Bearer {KEY}"},
                   json=body, timeout=60.0)
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    content = r.json()["choices"][0]["message"].get("content")
    print("       content:", repr(content)[:300])
    return content


def main():
    if not KEY:
        sys.exit("Set SARVAM_API_KEY first.")
    SAMPLES.mkdir(exist_ok=True)

    for name, (lang, text) in SENTENCES.items():
        wav = step(f"TTS {name}", lambda: tts(text, lang))
        if wav:
            (SAMPLES / f"{name}.wav").write_bytes(wav)

    for name, (lang, _) in SENTENCES.items():
        p = SAMPLES / f"{name}.wav"
        if p.exists():
            res = step(f"STT {name}", lambda: stt(p, lang))
            if res:
                print("       transcript:", res.get("transcript"))

    for effort in ["low", None]:
        step(f"CHAT reasoning_effort={effort!r}", lambda: chat(effort))

    (SAMPLES / "expected.json").write_text(json.dumps({
        "hi_hostel_a_to_academic": {"lang": "hi-IN", "pickup": "hostel_a", "drop": "academic_block"},
        "en_medical_to_cafeteria": {"lang": "en-IN", "pickup": "medical_center", "drop": "cafeteria"},
        "ta_library_to_hostel_b": {"lang": "ta-IN", "pickup": "library", "drop": "hostel_b"},
        "hi_only_drop": {"lang": "hi-IN", "pickup": None, "drop": "library"},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSamples written to", SAMPLES)


if __name__ == "__main__":
    main()
