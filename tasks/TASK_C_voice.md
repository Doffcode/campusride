# TASK C: Voice pipeline with Sarvam AI (`/voice`)

You are **Agent C**. You only create/edit files inside `voice/`.
First read `shared/CONTEXT.md`, `shared/models.py`, **`shared/sarvam_notes.md` (the only source for API details)**, and `shared/aliases.json`. Then read this file fully.

## Goal
Turn a student's spoken request (any supported Indian language) into a `BookingIntent`, and turn reply text into speech. Everything uses Sarvam AI. It must **never crash the demo**: every network failure has a fallback.

## Files to create

```
voice/__init__.py     already exists (empty). Leave it empty.
voice/sarvam.py       3 thin HTTP functions: stt, chat, tts. Nothing else.
voice/intent.py       prompt building, JSON parsing, rule-based fallback, extract_intent
voice/messages.py     fixed reply templates per language
voice/pipeline.py     public API used by the backend: understand, speak, confirmation_text
voice/run.py          CLI: python -m voice.run <audio_file> <lang>
voice/README.md       at the end
```

## Import rule (IMPORTANT for tests)
In `intent.py` and `pipeline.py`, import the HTTP module as a module, not its functions:
```python
from voice import sarvam            # correct: tests monkeypatch sarvam.chat / sarvam.stt / sarvam.tts
# from voice.sarvam import chat     # WRONG: monkeypatching would not work
```
and call `sarvam.chat(...)`, `sarvam.stt(...)`, `sarvam.tts(...)`.

---

## `voice/sarvam.py`

```python
import os
import httpx

BASE = "https://api.sarvam.ai"
TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}

class SarvamError(Exception):
    pass

def _key() -> str:   # raise SarvamError("SARVAM_API_KEY not set") if missing
def stt(audio: bytes, filename: str, lang: str) -> str        # returns transcript
def chat(messages: list[dict]) -> str                         # returns message content string
def tts(text: str, lang: str) -> str                          # returns base64 WAV (audios[0])
```
- Copy the request code from `shared/sarvam_notes.md` sections 1, 2, 3 exactly (URLs, headers, fields, model names).
- Use `httpx.post(..., timeout=30.0)`.
- Wrap everything: any `httpx.HTTPError`, non-2xx status, missing field, or empty content → `raise SarvamError(f"<api> failed: <status> <short text>")`. Never let other exception types escape.
- `tts`: if `lang not in TTS_LANGS`, use `"en-IN"`.
- `stt`: pass `lang` as `language_code`. If `lang` is empty, pass `"unknown"`.

---

## `voice/intent.py`

```python
import json, re
from pathlib import Path
from voice import sarvam
from voice.messages import clarification_text
from shared.graph import load_graph
from shared.models import BookingIntent

ALIASES_PATH = Path(__file__).resolve().parent.parent / "shared" / "aliases.json"
```

### `load_places() -> list[tuple[str, str, list[str]]]`
Returns `[(id, name, aliases), ...]` using `load_graph().locations()` for id+name and `aliases.json` for aliases (skip the `_comment` key; missing → `[]`). Always add `name.lower()` and `id.replace("_", " ")` to that place's alias list. Cache in a module-level variable after the first call.

### `build_messages(transcript: str, lang: str) -> list[dict]`
Return exactly two messages. System prompt (fill in `{places}` with one line per place: `- <id>: <name> (also called: <alias1>, <alias2>, ...)`):
```
You extract campus ride bookings from a student's spoken request.
The request may be in English, Hindi, Tamil, Telugu, Kannada, Bengali, Marathi, or a mix (e.g. Hinglish).
Valid places (use ONLY these ids):
{places}

Rules:
- "pickup" is where the student is now / wants to be picked up from. "drop" is where they want to go.
- Hindi: "X se Y" / "X से Y" means pickup X, drop Y. Tamil: "X-இலிருந்து / X-லிருந்து Y" means pickup X, drop Y. English: "from X to Y".
- If only one place is mentioned, it is usually the drop; set pickup to null.
- If a place is not in the list or you are unsure, use null. Never invent ids.
- confidence: 0.0 to 1.0, how sure you are about BOTH fields.
Reply with ONLY a JSON object, no other text:
{"pickup": "<id or null>", "drop": "<id or null>", "confidence": <number>}
```
User message: `f"Language: {lang}\nStudent said: {transcript}"`.

### `parse_llm_json(text: str) -> dict`
1. Remove `<think>...</think>` blocks (regex, DOTALL).
2. Remove markdown fences such as ```` ```json ```` and ```` ``` ````.
3. Take the substring from the first `{` to the last `}`. If there isn't one → `raise ValueError("no JSON object")`.
4. `json.loads` it (a `json.JSONDecodeError` is already a ValueError, so let it raise). If the result is not a dict → ValueError.

### `rule_based_intent(transcript: str) -> tuple[str | None, str | None]`
Offline fallback, no network. Algorithm:
1. `t = transcript.lower()`
2. Collect matches: for every place and every alias `a` (lowercased), find every occurrence of `a` in `t` (`str.find` loop) → `(start, end, place_id)`.
3. Sort by `(start, -(end - start))`. Greedily keep non-overlapping matches: skip a match if `start < last_kept_end`.
4. Collapse consecutive duplicates of the same place_id → ordered list `found`.
5. Decide:
   - `len(found) == 0` → `(None, None)`
   - `len(found) == 1` → `(None, found[0])` (one place = drop)
   - `len(found) >= 2`:
     - pickup marker: go through the kept matches in order and take the FIRST one where any of these is true:
       - `after = t[end:end+12].lstrip(" -")` starts with `"se "`, `"से"`, or equals `"se"`
       - `t[end:end+12]` contains `"லிருந்து"` or `"இருந்து"` (Tamil "from" suffix)
       - `t[:start]` ends with `"from "` or `"from the "`

       That match's place is the pickup, and the drop is the first OTHER place in `found`.
     - else pickup = `found[0]`, drop = `found[-1]`.
     - if pickup == drop → `(None, drop)`

Examples (tests check these):
- `"मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है"` → `("hostel_a", "academic_block")`
- `"I need a ride from the medical center to the cafeteria"` → `("medical_center", "cafeteria")`
- `"take me to the library from hostel b"` → `("hostel_b", "library")`
- `"मुझे लाइब्रेरी जाना है"` → `(None, "library")`
- `"hello"` → `(None, None)`

### `extract_intent(transcript: str, lang: str) -> BookingIntent`
```
valid = {id for id, _, _ in load_places()}
try:
    data = parse_llm_json(sarvam.chat(build_messages(transcript, lang)))
    pickup, drop = data.get("pickup"), data.get("drop")
    confidence = float(data.get("confidence", 0.0))
except (sarvam.SarvamError, ValueError, TypeError):
    pickup, drop = rule_based_intent(transcript)
    confidence = 0.7 if (pickup and drop) else 0.3
# normalise
pickup = pickup if pickup in valid else None      # also turns "null"/"" into None
drop = drop if drop in valid else None
confidence = min(max(confidence, 0.0), 1.0)
if pickup is not None and pickup == drop: drop = None
needs = pickup is None or drop is None or confidence < 0.6
if pickup is None and drop is None:   missing = "both"
elif pickup is None:                  missing = "pickup"
elif drop is None:                    missing = "drop"
else:                                 missing = "both"      # low-confidence case: ask again
reply = clarification_text(missing, lang) if needs else ""
return BookingIntent(pickup=pickup, drop=drop, confidence=confidence, needs_clarification=needs, reply_text=reply)
```

---

## `voice/messages.py`
Fixed templates. **No LLM here**, so replies are instant and reliable. Use these exact strings (tests check en-IN and hi-IN):

```python
PLACE_NAMES = None  # lazily: {id: name} from load_graph()

CONFIRM = {
    "en-IN": "Your ride is booked. {ev} will reach {pickup} in about {eta} min.",
    "hi-IN": "आपकी राइड बुक हो गई है। {ev} लगभग {eta} मिनट में {pickup} पहुँचेगी।",
    "ta-IN": "உங்கள் பயணம் பதிவு செய்யப்பட்டது. {ev} சுமார் {eta} நிமிடங்களில் {pickup} வந்தடையும்.",
}
QUEUED = {
    "en-IN": "All EVs are busy right now. Your ride is in the queue and will be assigned soon.",
    "hi-IN": "अभी सभी ईवी व्यस्त हैं। आपकी राइड कतार में है और जल्द ही असाइन होगी।",
    "ta-IN": "எல்லா வாகனங்களும் தற்போது பிஸியாக உள்ளன. உங்கள் பயணம் வரிசையில் உள்ளது.",
}
CLARIFY = {
    "pickup": {"en-IN": "Sorry, where should we pick you up?",
               "hi-IN": "माफ़ कीजिए, आपको कहाँ से पिक करना है?",
               "ta-IN": "மன்னிக்கவும், உங்களை எங்கிருந்து அழைத்துச் செல்ல வேண்டும்?"},
    "drop":   {"en-IN": "Sorry, where do you want to go?",
               "hi-IN": "माफ़ कीजिए, आपको कहाँ जाना है?",
               "ta-IN": "மன்னிக்கவும், நீங்கள் எங்கே போக வேண்டும்?"},
    "both":   {"en-IN": "Sorry, I didn't understand. Please say where you are and where you want to go.",
               "hi-IN": "माफ़ कीजिए, समझ नहीं आया। कृपया बताइए आप कहाँ हैं और कहाँ जाना है।",
               "ta-IN": "மன்னிக்கவும், புரியவில்லை. நீங்கள் எங்கே இருக்கிறீர்கள், எங்கே போக வேண்டும் என்று சொல்லுங்கள்."},
}
```
Functions:
- `confirmation_text(ride: Ride, lang: str) -> str`: if `ride.status == "pending"` → QUEUED; else CONFIRM with `ev = ride.ev_id.replace("ev_", "EV ")`, `pickup = <location name>`, `eta = ride.eta_min`.
- `clarification_text(missing: str, lang: str) -> str`: `missing` in `"pickup" | "drop" | "both"`.
- Language fallback for every dict: if `lang` is not a key, use `"en-IN"`.

---

## `voice/pipeline.py` (the backend calls these 3 functions; signatures FIXED)

```python
from voice import sarvam
from voice.intent import extract_intent
from voice.messages import confirmation_text   # re-export: backend calls pipeline.confirmation_text
from shared.models import BookingIntent

def understand(audio: bytes, filename: str, lang: str) -> tuple[str, BookingIntent]:
    transcript = sarvam.stt(audio, filename, lang)   # SarvamError propagates → backend returns 502
    return transcript, extract_intent(transcript, lang)

def speak(text: str, lang: str) -> str:
    if not text: return ""
    try: return sarvam.tts(text, lang)
    except sarvam.SarvamError: return ""
```

## `voice/run.py` (CLI)
`python -m voice.run <audio_path> <lang>`:
- read the file, call `understand`, print `transcript: ...` then `intent.model_dump_json(indent=2)`
- flag `--speak`: also call `speak(intent.reply_text or "test", lang)` and write `voice_reply.wav` in the current directory (base64-decode it).
- Use `argparse`. Print SarvamError messages nicely and exit 1. No traceback.

## Test audio
`shared/samples/*.wav` are created by the orchestrator from real Sarvam TTS. `shared/samples/expected.json` lists the expected pickup/drop per file. If the folder is missing, ask the orchestrator. Don't record your own.

## Acceptance tests (offline, no API key needed; they monkeypatch `sarvam.*`)
```
python -m pytest acceptance/test_voice.py -q
```
## Manual check (needs `SARVAM_API_KEY`)
```
python -m voice.run shared/samples/hi_hostel_a_to_academic.wav hi-IN
python -m voice.run shared/samples/en_medical_to_cafeteria.wav en-IN
python -m voice.run shared/samples/hi_only_drop.wav hi-IN        # must say needs_clarification: true
python -m voice.run shared/samples/ta_library_to_hostel_b.wav ta-IN --speak
```
Write the actual outputs into `voice/README.md`.

## Do NOT
- use the `sarvamai` SDK, `requests`, `openai`, or any other package
- call the LLM for reply text (use the templates)
- add caching, retries loops, async, classes
- let any exception other than `SarvamError` escape `sarvam.py`

## Done when
- `python -m pytest acceptance/test_voice.py -q` → all passed
- the 4 manual commands give the expected results from `expected.json` (the Tamil one may fall back to the rules; that's OK if the result is right)
- `voice/README.md` written
