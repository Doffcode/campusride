"""Offline tests for the MVP server (no Sarvam key or network needed).

Run from the repo root:  .venv\\Scripts\\python -m pytest mvp -q
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from mvp import nlu, sarvam
from mvp.server import app

client = TestClient(app)


def boom(*a, **k):
    raise sarvam.SarvamError("down")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # Default: every Sarvam call fails, so tests exercise the offline fallback unless they patch it.
    monkeypatch.setattr(sarvam, "chat", boom)
    monkeypatch.setattr(sarvam, "stt", boom)
    monkeypatch.setattr(sarvam, "tts", boom)


@pytest.mark.parametrize("text,expected", [
    ("मुझे ओपल हॉस्टल से ओरियन जाना है", ("opal", "orion")),
    ("garnet se library jana hai", ("garnet", "library")),
    ("I need a ride from the hospital to the LHC", ("hospital", "lhc")),
    ("take me to mega mess from zircon", ("zircon", "mega_mess")),
    ("நான் அகேட்லிருந்து ஓரியன் போக வேண்டும்", ("agate", "orion")),
    ("मुझे ओरियन जाना है", (None, "orion")),
    ("agate to main gate", ("agate", "main_gate")),       # "gate" inside "agate" must not match
    ("sports complex to barn hall", ("sports", "barn_hall")),
    ("hello there", (None, None)),
])
def test_rule_based(text, expected):
    assert nlu.rule_based(text) == expected


@pytest.mark.parametrize("raw", [
    '{"pickup": "opal", "drop": "orion", "confidence": 0.9}',
    '<think>hmm</think>```json\n{"pickup": "opal", "drop": "orion", "confidence": 0.9}\n```',
    'Sure: {"pickup": "opal", "drop": "orion", "confidence": 0.9}',
])
def test_parse_llm_json(raw):
    assert nlu.parse_llm_json(raw)["drop"] == "orion"


def test_understand_uses_llm(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", lambda m: '{"pickup": "opal", "drop": "orion", "confidence": 0.95}')
    r = nlu.understand("ओपल से ओरियन", "hi-IN")
    assert (r["pickup"], r["drop"], r["source"]) == ("opal", "orion", "sarvam-llm")


def test_understand_rejects_invented_ids(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", lambda m: '{"pickup": "mars", "drop": "orion", "confidence": 0.95}')
    r = nlu.understand("mars to orion", "en-IN")
    assert r["pickup"] is None and r["drop"] == "orion"


def test_understand_falls_back_to_rules():
    r = nlu.understand("garnet se library jana hai", "hi-IN")
    assert (r["pickup"], r["drop"], r["source"]) == ("garnet", "library", "rules")


def test_low_confidence_llm_rescued_by_rules(monkeypatch):
    monkeypatch.setattr(sarvam, "chat", lambda m: '{"pickup": null, "drop": null, "confidence": 0.2}')
    r = nlu.understand("garnet se library jana hai", "hi-IN")
    assert (r["pickup"], r["drop"]) == ("garnet", "library")


def test_api_understand():
    r = client.post("/api/understand", json={"text": "hospital to orion", "lang": "en-IN"})
    assert r.status_code == 200
    body = r.json()
    assert (body["pickup"], body["drop"], body["source"]) == ("hospital", "orion", "rules")
    assert client.post("/api/understand", json={"text": "  "}).status_code == 400


def test_api_voice(monkeypatch):
    monkeypatch.setattr(sarvam, "stt", lambda a, f, l: ("मुझे ओपल हॉस्टल से ओरियन जाना है", "hi-IN"))
    r = client.post("/api/voice", files={"audio": ("s.webm", b"x" * 2000, "audio/webm")}, data={"lang": "unknown"})
    assert r.status_code == 200
    body = r.json()
    assert (body["pickup"], body["drop"], body["lang"]) == ("opal", "orion", "hi-IN")
    assert "stt_ms" in body["timings"]


def test_api_voice_errors():
    short = client.post("/api/voice", files={"audio": ("s.webm", b"x", "audio/webm")})
    assert short.status_code == 400 and "error" in short.json()
    down = client.post("/api/voice", files={"audio": ("s.webm", b"x" * 2000, "audio/webm")})
    assert down.status_code == 502 and "error" in down.json()


def test_api_speak(monkeypatch):
    assert client.post("/api/speak", json={"text": "hi", "lang": "hi-IN"}).status_code == 502
    monkeypatch.setattr(sarvam, "tts", lambda t, l: "QUJD")
    r = client.post("/api/speak", json={"text": "hi", "lang": "hi-IN"})
    assert r.status_code == 200 and r.json()["audio_b64"] == "QUJD"


def test_static_served():
    assert client.get("/").status_code == 200
    campus = client.get("/api/campus").json()
    ids = {n["id"] for n in campus["nodes"]}
    assert all(a in ids and b in ids for a, b in campus["edges"])
    assert all(e["start"] in ids for e in campus["evs"])


def test_sarvam_http_errors_are_wrapped(monkeypatch):
    monkeypatch.undo()   # use the real sarvam functions, with a fake HTTP layer
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(500, text="boom", request=httpx.Request("POST", url)))
    for fn, args in [(sarvam.stt, (b"x", "a.wav", "hi-IN")), (sarvam.chat, ([],)), (sarvam.tts, ("hi", "hi-IN"))]:
        with pytest.raises(sarvam.SarvamError):
            fn(*args)
