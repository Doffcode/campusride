"""Acceptance tests for Agent B (backend). OWNER: orchestrator. DO NOT EDIT.

Run: python -m pytest acceptance/test_backend.py -q
Needs dispatch/core.py (Agent A) or backend/_dispatch_stub.py. Final sign-off requires the real one.
"""

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.store import ConflictError, Store
from shared.graph import load_graph
from shared.models import BookingIntent, State

G = load_graph(Path(__file__).parent / "fixtures" / "test_graph.json")


class FakeClock:
    def __init__(self, t=1_790_000_000):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(clock):
    return Store(G, clock=clock)


def run(store, clock, seconds):
    for _ in range(seconds):
        clock.t += 1
        store.tick(1.0)


def ev_of(store, eid):
    return next(e for e in store.snapshot().evs if e.id == eid)


def ride_of(store, rid):
    return next(r for r in store.snapshot().rides if r.id == rid)


# ------------------------------------------------------------------ Store
def test_initial_state(store):
    s = store.snapshot()
    assert [(e.id, e.current_node, e.status, e.seats_free) for e in s.evs] == [
        ("ev_1", "main_gate", "idle", 4), ("ev_2", "hostel_b", "idle", 4), ("ev_3", "library", "idle", 4)]
    assert s.rides == []


def test_create_ride_assigns_closest(store):
    r = store.create_ride("Aarav", "hostel_a", "library", "en-IN")
    assert (r.id, r.status, r.ev_id, r.eta_min) == ("ride_1", "assigned", "ev_2", 1)
    e = ev_of(store, "ev_2")
    assert e.seats_free == 3
    assert e.status == "enroute"
    assert e.route == ["hostel_a", "academic_block", "library"]


def test_ride_ids_increment(store):
    assert store.create_ride("A", "hostel_a", "library", "en-IN").id == "ride_1"
    assert store.create_ride("B", "cafeteria", "library", "en-IN").id == "ride_2"


def test_invalid_rides_rejected(store):
    with pytest.raises(ValueError):
        store.create_ride("A", "hostel_z", "library", "en-IN")
    with pytest.raises(ValueError):
        store.create_ride("A", "library", "library", "en-IN")


def test_pooling_through_store(store):
    store.create_ride("Aarav", "hostel_a", "library", "en-IN")
    r2 = store.create_ride("Priya", "hostel_a", "academic_block", "hi-IN")
    assert r2.ev_id == "ev_2"
    assert ev_of(store, "ev_2").seats_free == 2


def test_full_trip(store, clock):
    store.create_ride("Aarav", "hostel_a", "library", "en-IN")
    run(store, clock, 10)
    e = ev_of(store, "ev_2")
    assert e.status == "enroute" and 0 < e.progress < 1
    run(store, clock, 45)  # 200 m at 250 m/min = 48 s
    e = ev_of(store, "ev_2")
    r = ride_of(store, "ride_1")
    assert e.status == "waiting" and e.current_node == "hostel_a" and e.progress == 0
    assert r.status == "waiting_at_pickup" and r.eta_min == 0 and r.arrived_at is not None

    r = store.ev_picked("ev_2", "ride_1")
    assert r.status == "picked"
    assert ride_of(store, "ride_1").eta_min == 2        # 450 m to library
    assert ev_of(store, "ev_2").status == "enroute"

    run(store, clock, 125)                               # 450 m = 108 s
    r = ride_of(store, "ride_1")
    e = ev_of(store, "ev_2")
    assert r.status == "done" and r.eta_min is None
    assert e.current_node == "library" and e.status == "idle" and e.seats_free == 4 and e.stops == []


def test_no_show_after_120_seconds(store, clock):
    store.create_ride("Rohan", "cafeteria", "sports_complex", "en-IN")   # ev_3 from library, 200 m
    run(store, clock, 55)
    r = ride_of(store, "ride_1")
    assert r.status == "waiting_at_pickup"
    clock.t = r.arrived_at + 119
    store.tick(1.0)
    assert ride_of(store, "ride_1").status == "waiting_at_pickup"
    clock.t = r.arrived_at + 120
    store.tick(1.0)
    r = ride_of(store, "ride_1")
    e = ev_of(store, "ev_3")
    assert r.status == "no_show" and r.eta_min is None
    assert e.stops == [] and e.seats_free == 4 and e.status == "idle"


def test_cancel(store):
    store.create_ride("A", "hostel_a", "library", "en-IN")
    r = store.cancel_ride("ride_1")
    assert r.status == "cancelled"
    e = ev_of(store, "ev_2")
    assert e.stops == [] and e.seats_free == 4 and e.status == "idle"
    with pytest.raises(ConflictError):
        store.cancel_ride("ride_1")
    with pytest.raises(KeyError):
        store.cancel_ride("ride_99")


def test_picked_requires_waiting(store):
    store.create_ride("A", "hostel_a", "library", "en-IN")
    with pytest.raises(ConflictError):
        store.ev_picked("ev_2", "ride_1")
    with pytest.raises(KeyError):
        store.ev_picked("ev_9", "ride_1")


def test_arrived_requires_being_at_stop(store):
    store.create_ride("A", "hostel_a", "library", "en-IN")
    with pytest.raises(ConflictError):
        store.ev_arrived("ev_2")


def test_pending_ride_retried_when_seat_frees(clock):
    s = Store(G, ev_starts={"ev_1": "library"}, clock=clock)
    for i in range(4):
        assert s.create_ride(f"S{i}", "library", "cafeteria", "en-IN").status == "assigned"
    r5 = s.create_ride("S4", "library", "cafeteria", "en-IN")
    assert r5.status == "pending" and r5.ev_id is None and r5.eta_min is None
    s.cancel_ride("ride_1")
    clock.t += 1
    s.tick(1.0)
    assert ride_of(s, "ride_5").status in ("assigned", "waiting_at_pickup")
    assert ride_of(s, "ride_5").ev_id == "ev_1"


def test_snapshot_is_a_copy(store):
    store.create_ride("A", "hostel_a", "library", "en-IN")
    snap = store.snapshot()
    snap.evs[0].current_node = "hacked"
    snap.rides[0].status = "done"
    assert ev_of(store, "ev_1").current_node == "main_gate"
    assert ride_of(store, "ride_1").status == "assigned"


# ------------------------------------------------------------------ HTTP API
@pytest.fixture
def client(store):
    with TestClient(create_app(store, run_sim=False)) as c:
        yield c


def test_api_locations(client):
    r = client.get("/locations")
    assert r.status_code == 200
    assert len(r.json()) == 10 and {"id", "name", "x", "y"} <= set(r.json()[0])


def test_api_state_shape(client):
    r = client.get("/state")
    assert r.status_code == 200
    State.model_validate(r.json())


def test_api_book_ride(client):
    r = client.post("/ride", json={"student_name": "A", "pickup": "hostel_a", "drop": "library", "lang": "en-IN"})
    assert r.status_code == 200
    assert r.json()["ev_id"] == "ev_2" and r.json()["status"] == "assigned"


def test_api_errors_use_error_key(client):
    r = client.post("/ride", json={"student_name": "A", "pickup": "hostel_z", "drop": "library", "lang": "en-IN"})
    assert r.status_code == 400 and "error" in r.json() and "detail" not in r.json()
    r = client.post("/ride", json={"student_name": "A"})
    assert r.status_code == 400 and "error" in r.json()
    r = client.post("/ride/ride_99/cancel")
    assert r.status_code == 404 and "error" in r.json()
    client.post("/ride", json={"student_name": "A", "pickup": "hostel_a", "drop": "library", "lang": "en-IN"})
    r = client.post("/ev/ev_2/picked", json={"ride_id": "ride_1"})
    assert r.status_code == 409 and "error" in r.json()


def test_api_cancel(client):
    client.post("/ride", json={"student_name": "A", "pickup": "hostel_a", "drop": "library", "lang": "en-IN"})
    r = client.post("/ride/ride_1/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_websocket_sends_state_immediately(client):
    with client.websocket_connect("/live") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state"
        State.model_validate(msg["data"])


def _fake_voice(monkeypatch, intent):
    import voice
    fake = types.ModuleType("voice.pipeline")
    fake.understand = lambda audio, filename, lang: ("hostel a se library", intent)
    fake.confirmation_text = lambda ride, lang: f"booked {ride.id}"
    fake.speak = lambda text, lang: "QUJD"
    monkeypatch.setitem(sys.modules, "voice.pipeline", fake)
    monkeypatch.setattr(voice, "pipeline", fake, raising=False)


def test_voice_book_success(client, monkeypatch):
    _fake_voice(monkeypatch, BookingIntent(pickup="hostel_a", drop="library", confidence=0.9,
                                           needs_clarification=False, reply_text=""))
    r = client.post("/voice/book", files={"audio": ("a.webm", b"xx", "audio/webm")},
                    data={"lang": "hi-IN", "student_name": "Priya"})
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "hostel a se library"
    assert body["ride"]["ev_id"] == "ev_2" and body["ride"]["student_name"] == "Priya"
    assert body["ride"]["lang"] == "hi-IN"
    assert body["intent"]["reply_text"] == "booked ride_1"
    assert body["reply_audio_b64"] == "QUJD"


def test_voice_book_clarification_creates_no_ride(client, monkeypatch):
    _fake_voice(monkeypatch, BookingIntent(pickup=None, drop="library", confidence=0.8,
                                           needs_clarification=True, reply_text="where?"))
    r = client.post("/voice/book", files={"audio": ("a.webm", b"xx", "audio/webm")},
                    data={"lang": "hi-IN", "student_name": "Priya"})
    assert r.status_code == 200
    assert r.json()["ride"] is None and r.json()["intent"]["reply_text"] == "where?"
    assert client.get("/state").json()["rides"] == []
