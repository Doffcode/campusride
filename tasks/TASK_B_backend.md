# TASK B: Backend (`/backend`)

You are **Agent B**. You only create/edit files inside `backend/`.
First read `shared/CONTEXT.md`, `shared/models.py`, `shared/graph.py`, `tasks/TASK_A_dispatch.md` (you call its functions). Then read this file fully.

## Goal
A FastAPI server that holds all state in memory, runs the EV simulation every second, exposes the API in CONTEXT Section 6, and pushes live state over a WebSocket.

## Files to create

```
backend/__init__.py      already exists (empty). Leave it empty.
backend/store.py         Store class: ALL state + ALL business logic. No FastAPI imports here.
backend/app.py           FastAPI app: routes, error handlers, sim loop, websocket, static files
backend/README.md        at the end
```

## Dependency on dispatch (Agent A)
Import exactly: `from dispatch.core import assign, plan_route, compute_etas`.
If `dispatch/core.py` doesn't exist yet, create a TEMPORARY file `backend/_dispatch_stub.py` with the same 3 function names (e.g. assign = nearest idle EV, just append P and D to its stops) and do
```python
try:
    from dispatch.core import assign, plan_route, compute_etas
except ImportError:
    from backend._dispatch_stub import assign, plan_route, compute_etas
```
Signatures: `assign(ride, evs, graph) -> Assignment | None`, `plan_route(graph, start, stops) -> list[str]`, `compute_etas(graph, ev) -> dict[ride_id, int]`.

---

## `backend/store.py`: exact spec

```python
import time
from typing import Callable

from shared.graph import Graph
from shared.models import (EV, EV_CAPACITY, EV_SPEED_M_PER_S, DEFAULT_EV_STARTS,
    FINAL_RIDE_STATUSES, NO_SHOW_SECONDS, Ride, State, Stop)


class ConflictError(Exception):
    """Action not allowed in the current state. The API maps it to HTTP 409."""


class Store:
    def __init__(self, graph: Graph, ev_starts: dict[str, str] | None = None,
                 clock: Callable[[], float] = time.time):
        self.graph = graph
        self.clock = clock
        starts = ev_starts if ev_starts is not None else DEFAULT_EV_STARTS
        self.evs: dict[str, EV] = {eid: EV(id=eid, current_node=node) for eid, node in starts.items()}
        self.rides: dict[str, Ride] = {}      # insertion order = creation order
        self._next_ride = 1
```
`now()` = `int(self.clock())`. Always get time through it; tests inject a fake clock.
Errors: unknown ev/ride id → `KeyError("unknown ev: ev_9")`. Invalid input → `ValueError("...")`. Wrong state → `ConflictError("...")`.

### Public methods (names/signatures FIXED, tests call them)

**`snapshot(self) -> State`**
`State(evs=[ev copies sorted by id], rides=[ride copies in creation order], server_time=now())`. Use `model_copy(deep=True)` so callers can't mutate internal state.

**`create_ride(self, student_name: str, pickup: str, drop: str, lang: str) -> Ride`**
1. If pickup or drop is not `graph.has_node(...)` → `ValueError(f"unknown location id: {x}")`
2. If pickup == drop → `ValueError("pickup and drop must be different")`
3. If `student_name.strip()` is empty → use `"Student"`
4. `ride = Ride(id=f"ride_{self._next_ride}", student_name=..., pickup, drop, lang, status="pending", created_at=now())`, then increment the counter, then store it
5. `self._try_assign(ride)`
6. `self._update_etas()`
7. return `ride.model_copy()`

**`cancel_ride(self, ride_id: str) -> Ride`**
- unknown → KeyError. Status in FINAL_RIDE_STATUSES or `picked` → `ConflictError("ride cannot be cancelled in status X")`
- `self._release_ride(ride, "cancelled")`, then return a copy

**`ev_arrived(self, ev_id: str) -> EV`** (manual driver tap; the sim normally does this itself)
- unknown → KeyError
- If `ev.status == "waiting"` → just return a copy (idempotent)
- If NOT (`ev.stops` and `ev.stops[0].node == ev.current_node` and `ev.progress == 0`) → `ConflictError("EV is not at its next stop")`
- else `self._process_stops_here(ev)` and return a copy

**`ev_picked(self, ev_id: str, ride_id: str) -> Ride`**
- unknown ev or ride → KeyError
- Require: `ev.status == "waiting"` and `ev.stops` and `ev.stops[0].kind == "pickup"` and `ev.stops[0].ride_id == ride_id`. Otherwise `ConflictError("EV is not waiting for this ride")`
- `ev.stops.pop(0)`; `ride.status = "picked"`; `ev.status = "enroute"`
- `self._process_stops_here(ev)` (another pooled pickup may be waiting at the same node → waits again)
- `self._replan(ev)`; `self._update_etas()`; return a copy of ride

**`ev_dropped(self, ev_id: str, ride_id: str) -> Ride`** (manual early drop; sim auto-drops)
- unknown → KeyError. Require `ride.status == "picked"` and `ride.ev_id == ev_id`, else ConflictError
- `self._release_ride(ride, "done")`; return a copy

**`tick(self, dt: float = 1.0) -> None`**: one simulation step. Exact order:
```
now = self.now()
# 1. retry pending rides, oldest first
for ride in list(self.rides.values()):
    if ride.status == "pending":
        self._try_assign(ride)
# 2. no-shows
for ev in sorted evs by id:
    if ev.status == "waiting" and ev.stops:
        ride = self.rides[ev.stops[0].ride_id]
        if ride.arrived_at is not None and now - ride.arrived_at >= NO_SHOW_SECONDS:
            self._release_ride(ride, "no_show")
# 3. movement
for ev in sorted evs by id:
    if ev.status == "waiting":
        continue
    self._process_stops_here(ev)          # handles an EV that is already at its next stop
    if ev.status == "waiting":
        continue
    if not ev.route:
        ev.progress = 0.0
        ev.status = "idle" if not ev.stops else "enroute"
        continue
    ev.status = "enroute"
    ev.progress += EV_SPEED_M_PER_S * dt / self.graph.edge_len(ev.current_node, ev.route[0])
    if ev.progress >= 1.0:
        ev.current_node = ev.route.pop(0)
        ev.progress = 0.0
        self._process_stops_here(ev)
# 4. ETAs
self._update_etas()
```

### Private helpers (write them exactly like this)

**`_try_assign(self, ride)`**
```
result = assign(ride, [self.evs[k] for k in sorted(self.evs)], self.graph)
if result is None: return                        # stays pending
ev = self.evs[result.ev_id]
old_next = ev.route[0] if ev.route else None
ev.stops = result.stops
ev.route = result.route
new_next = ev.route[0] if ev.route else None
if ev.progress > 0 and new_next != old_next:
    ev.progress = 0.0                            # EV turns around; restart edge from current_node
ev.seats_free -= 1
if ev.status == "idle": ev.status = "enroute"
ride.status = "assigned"; ride.ev_id = ev.id; ride.eta_min = result.eta_min
```

**`_process_stops_here(self, ev)`**: handles the stops at the EV's current node
```
if ev.progress != 0: return
while ev.stops and ev.stops[0].node == ev.current_node:
    stop = ev.stops[0]
    ride = self.rides[stop.ride_id]
    if stop.kind == "drop":
        ev.stops.pop(0)
        ride.status = "done"; ride.eta_min = None
        ev.seats_free += 1
        continue
    # pickup
    ride.status = "waiting_at_pickup"; ride.eta_min = 0
    if ride.arrived_at is None: ride.arrived_at = self.now()
    ev.status = "waiting"; ev.progress = 0.0
    return
# no more stops at this node
self._replan(ev)
ev.status = "enroute" if ev.stops else "idle"
```

**`_replan(self, ev)`**
```
old_next = ev.route[0] if ev.route else None
ev.route = plan_route(self.graph, ev.current_node, ev.stops)
if ev.progress > 0 and (not ev.route or ev.route[0] != old_next):
    ev.progress = 0.0
```

**`_release_ride(self, ride, final_status)`**: used by cancel / no_show / manual drop
```
if ride.ev_id is not None and ride.status in ("assigned", "waiting_at_pickup", "picked"):
    ev = self.evs[ride.ev_id]
    was_waiting_for_it = ev.status == "waiting" and ev.stops and ev.stops[0].ride_id == ride.id
    ev.stops = [s for s in ev.stops if s.ride_id != ride.id]
    ev.seats_free += 1
    if was_waiting_for_it:
        ev.status = "enroute"
        self._process_stops_here(ev)   # may wait for another pooled pickup at the same node
    self._replan(ev)
    if not ev.stops and ev.status != "waiting":
        ev.status = "idle"
ride.status = final_status
ride.eta_min = None
```

**`_update_etas(self)`**
```
for ev in self.evs.values():
    etas = compute_etas(self.graph, ev)
    for ride_id, m in etas.items():
        r = self.rides[ride_id]
        r.eta_min = 0 if r.status == "waiting_at_pickup" else m
```

---

## `backend/app.py`: exact spec

```python
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.store import ConflictError, Store
from shared.graph import load_graph
from shared.models import EV, Location, Ride, RideIdRequest, RideRequest, State, VoiceBookResponse

ROOT = Path(__file__).resolve().parent.parent


def create_app(store: Store | None = None, run_sim: bool = True) -> FastAPI:
    ...

app = create_app()        # used by: uvicorn backend.app:app
```

Inside `create_app`:
1. `store = store or Store(load_graph())`. Put it on `app.state.store`.
2. **Lifespan**: if `run_sim`, start an asyncio task that loops forever:
   `store.tick(1.0)`, then broadcast `{"type": "state", "data": store.snapshot().model_dump()}` to all connected websockets (use `send_json`, and drop sockets that raise), then `await asyncio.sleep(1.0)`. Cancel the task on shutdown.
   Wrap each loop iteration in `try/except Exception` and print the error. **The loop must never die.**
3. `app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`
4. **Error handlers** (register with `@app.exception_handler`):
   - `ValueError` → 400, `KeyError` → 404, `ConflictError` → 409
   - Body: `JSONResponse({"error": str(exc).strip("'\"")}, status_code=...)`
   - Also override `RequestValidationError` (from `fastapi.exceptions`) → 400 `{"error": "invalid request body"}`
5. Routes. Every route is a thin one-liner that calls the store:

| route | code |
|---|---|
| `GET /locations` → `list[Location]` | `store.graph.locations()` |
| `GET /state` → `State` | `store.snapshot()` |
| `POST /ride` body `RideRequest` → `Ride` | `store.create_ride(req.student_name, req.pickup, req.drop, req.lang)` |
| `POST /ride/{ride_id}/cancel` → `Ride` | `store.cancel_ride(ride_id)` |
| `POST /ev/{ev_id}/arrived` → `EV` | `store.ev_arrived(ev_id)` |
| `POST /ev/{ev_id}/picked` body `RideIdRequest` → `Ride` | `store.ev_picked(ev_id, req.ride_id)` |
| `POST /ev/{ev_id}/dropped` body `RideIdRequest` → `Ride` | `store.ev_dropped(ev_id, req.ride_id)` |

6. `WS /live`: `await ws.accept()`, add to a set, **immediately send one state message**, then `while True: await ws.receive_text()` (just to detect disconnect). On `WebSocketDisconnect`, remove it from the set.
7. `POST /voice/book` (multipart: `audio: UploadFile = File(...)`, `lang: str = Form("en-IN")`, `student_name: str = Form("Student")`):
```python
try:
    from voice import pipeline
except ImportError:
    return JSONResponse({"error": "voice module not ready"}, status_code=503)
audio_bytes = await audio.read()
try:
    transcript, intent = await asyncio.to_thread(pipeline.understand, audio_bytes, audio.filename or "audio.webm", lang)
except Exception as e:
    return JSONResponse({"error": f"voice failed: {e}"}, status_code=502)
ride = None
if not intent.needs_clarification:
    ride = store.create_ride(student_name, intent.pickup, intent.drop, lang)
    intent.reply_text = pipeline.confirmation_text(ride, lang)
audio_b64 = await asyncio.to_thread(pipeline.speak, intent.reply_text, lang)   # returns "" on failure
return VoiceBookResponse(transcript=transcript, intent=intent, ride=ride, reply_audio_b64=audio_b64)
```
   (Voice API from Agent C: `pipeline.understand(audio: bytes, filename: str, lang: str) -> tuple[str, BookingIntent]`, `pipeline.confirmation_text(ride: Ride, lang: str) -> str`, `pipeline.speak(text: str, lang: str) -> str`.)
8. Static files, mounted AFTER all routes:
   `app.mount("/frontend", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")` and
   `app.mount("/shared", StaticFiles(directory=ROOT / "shared"), name="shared")`.
   Also add `GET /` that returns a `RedirectResponse("/frontend/admin.html")`.
9. Return `app`.

## Run it
```
uvicorn backend.app:app --reload --port 8000
```
Open http://localhost:8000/docs to try every endpoint. http://localhost:8000/state should show 3 idle EVs.

## Acceptance tests
```
python -m pytest acceptance/test_backend.py -q
```
They use `Store(graph, clock=fake_clock)` directly and `create_app(store, run_sim=False)` with FastAPI's `TestClient`. So the fixed names above matter.

## Manual check (do it)
1. Start the server. POST /ride `{"student_name":"A","pickup":"hostel_a","drop":"library","lang":"en-IN"}` → status `assigned`, ev_id `ev_2`, eta_min 1.
2. Watch GET /state every few seconds: ev_2's progress rises, then it reaches hostel_a and becomes `waiting`.
3. POST /ev/ev_2/picked `{"ride_id":"ride_1"}` → ride `picked`, EV continues; later the ride becomes `done`.
4. Book another ride and never tap picked → after 120 s it becomes `no_show`.

## Do NOT
- put business logic in app.py routes
- use `print` for normal logging inside tick (it's every second), only for errors
- add a database, auth, background threads (use asyncio), or extra endpoints
- modify dispatch/, voice/, frontend/, shared/

## Done when
- `python -m pytest acceptance/test_backend.py -q` → all passed
- manual check steps 1 to 4 work
- `backend/README.md` written
