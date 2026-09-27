"""Acceptance tests for Agent C (voice). OWNER: orchestrator. DO NOT EDIT.

Offline: no API key and no network needed. Sarvam calls are monkeypatched.
Run: python -m pytest acceptance/test_voice.py -q
"""

import json

import httpx
import pytest

from shared.models import Ride
from voice import intent as intent_mod
from voice import pipeline, sarvam
from voice.intent import extract_intent, parse_llm_json, rule_based_intent
from voice.messages import clarification_text, confirmation_text


def fake_chat(reply):
    def _chat(messages):
        assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
        assert "hostel_a" in messages[0]["content"]      # place ids are in the prompt
        return reply
    return _chat


def boom(*a, **k):
    raise sarvam.SarvamError("down")


# ------------------------------------------------------------ parse_llm_json
@pytest.mark.parametrize("text", [
    '{"pickup": "hostel_a", "drop": "library", "confidence": 0.9}',
    '```json\n{"pickup": "hostel_a", "drop": "library", "confidence": 0.9}\n```',
    '<think>user wants library</think>{"pickup": "hostel_a", "drop": "library", "confidence": 0.9}',
    'Sure! {"pickup": "hostel_a", "drop": "library", "confidence": 0.9} Hope that helps.',
])
def test_parse_llm_json_variants(text):
    assert parse_llm_json(text) == {"pickup": "hostel_a", "drop": "library", "confidence": 0.9}


def test_parse_llm_json_garbage():
    with pytest.raises(ValueError):
        parse_llm_json("I don't know")


# ------------------------------------------------------------ rule_based_intent
@pytest.mark.parametrize("text,expected", [
    ("मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है", ("hostel_a", "academic_block")),
    ("I need a ride from the medical center to the cafeteria", ("medical_center", "cafeteria")),
    ("take me to the library from hostel b", ("hostel_b", "library")),
    ("hostel a se library jana hai", ("hostel_a", "library")),
    ("நான் லைப்ரரியிலிருந்து ஹாஸ்டல் பி போக வேண்டும்", ("library", "hostel_b")),
    ("मुझे लाइब्रेरी जाना है", (None, "library")),
    ("hello", (None, None)),
])
def test_rule_based_intent(text, expected):
    assert rule_based_intent(text) == expected


# ------------------------------------------------------------ extract_intent
def test_extract_intent_llm_success(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": "hostel_a", "drop": "academic_block", "confidence": 0.95}'))
    i = extract_intent("मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है", "hi-IN")
    assert (i.pickup, i.drop, i.needs_clarification, i.reply_text) == ("hostel_a", "academic_block", False, "")
    assert i.confidence == pytest.approx(0.95)


def test_extract_intent_invented_id_is_dropped(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": "hostel_z", "drop": "library", "confidence": 0.9}'))
    i = extract_intent("from hostel z to library", "en-IN")
    assert i.pickup is None and i.drop == "library" and i.needs_clarification
    assert i.reply_text == "Sorry, where should we pick you up?"


def test_extract_intent_low_confidence(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": "hostel_a", "drop": "library", "confidence": 0.4}'))
    i = extract_intent("something", "hi-IN")
    assert i.needs_clarification
    assert i.reply_text == "माफ़ कीजिए, समझ नहीं आया। कृपया बताइए आप कहाँ हैं और कहाँ जाना है।"


def test_extract_intent_same_pickup_and_drop(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": "library", "drop": "library", "confidence": 0.9}'))
    i = extract_intent("library", "en-IN")
    assert i.pickup == "library" and i.drop is None and i.needs_clarification
    assert i.reply_text == "Sorry, where do you want to go?"


def test_extract_intent_null_values(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": null, "drop": "library", "confidence": 0.8}'))
    i = extract_intent("मुझे लाइब्रेरी जाना है", "hi-IN")
    assert i.pickup is None and i.drop == "library" and i.needs_clarification
    assert i.reply_text == "माफ़ कीजिए, आपको कहाँ से पिक करना है?"


def test_extract_intent_falls_back_when_llm_down(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", boom)
    i = extract_intent("I need a ride from the medical center to the cafeteria", "en-IN")
    assert (i.pickup, i.drop, i.needs_clarification) == ("medical_center", "cafeteria", False)
    assert i.confidence == pytest.approx(0.7)


def test_extract_intent_falls_back_on_bad_json(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", fake_chat("no json here"))
    i = extract_intent("hostel a se library jana hai", "hi-IN")
    assert (i.pickup, i.drop, i.needs_clarification) == ("hostel_a", "library", False)


# ------------------------------------------------------------ messages
def _ride(**kw):
    base = dict(id="ride_2", student_name="Priya", pickup="hostel_a", drop="academic_block",
                lang="hi-IN", status="assigned", ev_id="ev_2", eta_min=1, created_at=0)
    base.update(kw)
    return Ride(**base)


def test_confirmation_text():
    assert confirmation_text(_ride(), "en-IN") == "Your ride is booked. EV 2 will reach Hostel A in about 1 min."
    assert confirmation_text(_ride(), "hi-IN") == "आपकी राइड बुक हो गई है। EV 2 लगभग 1 मिनट में Hostel A पहुँचेगी।"
    assert confirmation_text(_ride(), "xx-IN") == confirmation_text(_ride(), "en-IN")


def test_confirmation_text_pending():
    t = confirmation_text(_ride(status="pending", ev_id=None, eta_min=None), "en-IN")
    assert t == "All EVs are busy right now. Your ride is in the queue and will be assigned soon."


def test_clarification_text_fallback_language():
    assert clarification_text("drop", "bn-IN") == "Sorry, where do you want to go?"


# ------------------------------------------------------------ pipeline
def test_understand(monkeypatch):
    monkeypatch.setattr(sarvam, "stt", lambda audio, filename, lang: "hostel a se library jana hai")
    monkeypatch.setattr(sarvam, "chat", fake_chat('{"pickup": "hostel_a", "drop": "library", "confidence": 0.9}'))
    transcript, i = pipeline.understand(b"RIFF", "a.webm", "hi-IN")
    assert transcript == "hostel a se library jana hai"
    assert (i.pickup, i.drop, i.needs_clarification) == ("hostel_a", "library", False)


def test_understand_propagates_stt_failure(monkeypatch):
    monkeypatch.setattr(sarvam, "stt", boom)
    with pytest.raises(sarvam.SarvamError):
        pipeline.understand(b"RIFF", "a.webm", "hi-IN")


def test_speak(monkeypatch):
    monkeypatch.setattr(sarvam, "tts", lambda text, lang: "QUJD")
    assert pipeline.speak("hello", "en-IN") == "QUJD"
    assert pipeline.speak("", "en-IN") == ""
    monkeypatch.setattr(sarvam, "tts", boom)
    assert pipeline.speak("hello", "en-IN") == ""


def test_pipeline_reexports_confirmation_text():
    assert pipeline.confirmation_text is confirmation_text


# ------------------------------------------------------------ sarvam.py HTTP layer
class Recorder:
    def __init__(self, status, payload):
        self.status, self.payload, self.calls = status, payload, []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        return httpx.Response(self.status, json=self.payload, request=httpx.Request("POST", url))


def test_tts_request_shape_and_language_fallback(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    rec = Recorder(200, {"request_id": "x", "audios": ["QUJD"]})
    monkeypatch.setattr(httpx, "post", rec)
    assert sarvam.tts("hello", "ur-IN") == "QUJD"
    url, kw = rec.calls[0]
    assert url == "https://api.sarvam.ai/text-to-speech"
    assert kw["headers"]["api-subscription-key"] == "sk_test"
    assert kw["json"]["language_code"] == "en-IN"
    assert kw["json"]["model"] == "bulbul:v3"


def test_stt_request_shape(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    rec = Recorder(200, {"request_id": "x", "transcript": "namaste", "language_code": "hi-IN"})
    monkeypatch.setattr(httpx, "post", rec)
    assert sarvam.stt(b"RIFF", "a.wav", "hi-IN") == "namaste"
    url, kw = rec.calls[0]
    assert url == "https://api.sarvam.ai/speech-to-text"
    assert kw["data"]["model"] == "saaras:v3" and kw["data"]["language_code"] == "hi-IN"
    assert "file" in kw["files"]


def test_chat_request_shape(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    rec = Recorder(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}}]})
    monkeypatch.setattr(httpx, "post", rec)
    assert sarvam.chat([{"role": "user", "content": "hi"}]) == "{}"
    url, kw = rec.calls[0]
    assert url == "https://api.sarvam.ai/v1/chat/completions"
    assert kw["headers"]["Authorization"] == "Bearer sk_test"


@pytest.mark.parametrize("fn,args", [
    ("stt", (b"RIFF", "a.wav", "hi-IN")),
    ("chat", ([{"role": "user", "content": "hi"}],)),
    ("tts", ("hello", "hi-IN")),
])
def test_http_errors_become_sarvam_error(monkeypatch, fn, args):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    monkeypatch.setattr(httpx, "post", Recorder(500, {"error": "boom"}))
    with pytest.raises(sarvam.SarvamError):
        getattr(sarvam, fn)(*args)


def test_empty_llm_content_is_error(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    monkeypatch.setattr(httpx, "post", Recorder(200, {"choices": [{"message": {"content": None}}]}))
    with pytest.raises(sarvam.SarvamError):
        sarvam.chat([{"role": "user", "content": "hi"}])


def test_missing_key_is_error(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(sarvam.SarvamError):
        sarvam.tts("hello", "hi-IN")


def test_places_cover_graph():
    ids = {p[0] for p in intent_mod.load_places()}
    assert {"hostel_a", "library", "academic_block", "medical_center", "cafeteria"} <= ids
    aliases = dict((p[0], p[2]) for p in intent_mod.load_places())
    assert "hostel a" in aliases["hostel_a"]


def test_expected_samples_file_is_valid_json_if_present():
    from pathlib import Path
    p = Path("shared/samples/expected.json")
    if p.exists():
        json.loads(p.read_text(encoding="utf-8"))
