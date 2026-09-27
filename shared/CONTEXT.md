# CampusRide: Shared Context

> READ THIS FULLY BEFORE WRITING ANY CODE. Then read your own task file in `tasks/`.
> This file is the single source of truth. If anything you are told conflicts with it, this file wins.
> Do NOT add features, change contracts, or touch files outside your folder.

**Reading order for every agent:**
1. `shared/CONTEXT.md` (this file)
2. `shared/models.py` (the exact data models; your code must import them)
3. your task file: `tasks/TASK_A_dispatch.md`, `TASK_B_backend.md`, `TASK_C_voice.md`, or `TASK_D_frontend.md`
4. the acceptance tests for your module in `acceptance/` (your code is done only when these pass)

---

## 1. Product

**CampusRide** is a dispatch system for campus EVs (electric shuttles).

**Problem today:** Students call a phone number and wait for an unknown amount of time. There is no ETA and no coordination between multiple EVs, so EVs take inefficient routes, and they waste time waiting for students who don't show up.

**Solution:** Students book by voice in their own language (via Sarvam AI) or by text. The system assigns the best EV, pools rides going the same way, shows a live ETA, and auto-cancels no-shows.

**Users:**
- **Student**: books a ride and sees the assigned EV and live ETA
- **Driver**: sees the next stop and taps "Picked up" (and "Arrived"/"Dropped" if needed)
- **Admin**: sees a live map of all EVs and all rides

**Division of work:** Sarvam AI handles the language side (speech → text → intent → spoken reply). A deterministic algorithm handles the decisions (which EV, which route). The LLM never decides routing.

---

## 2. Scope

### In scope (MVP)
- Campus graph (nodes + weighted edges) loaded from `shared/graph.json`
- Multi-EV dispatch with shortest paths and ride pooling
- Live ETA updates
- No-show auto-cancel after 120 s
- Voice booking in Indian languages via Sarvam (STT → intent → TTS reply)
- Three web views: student, driver, admin
- Simulated EV movement along graph edges

### Out of scope (DO NOT BUILD)
- Authentication, user accounts, login
- Payments
- Real GPS, Google Maps, Leaflet, or any external map API/library
- Databases (all state is in memory)
- Deployment, Docker, CI
- Streaming STT, phone/IVR integration (pitch-only ideas)
- Any feature not listed under "In scope"

---

## 3. Tech stack (fixed)

- **Python 3.11+**, FastAPI, uvicorn, Pydantic v2, httpx, pytest, python-multipart. Exact list is in `requirements.txt`. No other packages.
- **Frontend:** plain HTML + CSS + vanilla JavaScript. No framework, no npm, no build step, no CDN libraries. Map drawn with inline SVG.
- **AI:** Sarvam AI REST APIs only, called with httpx. Use the exact endpoints/fields in `shared/sarvam_notes.md`. Never guess endpoints from memory. Do not install the `sarvamai` SDK.
- **Config:** API key from env var `SARVAM_API_KEY`. Never hardcode keys.
- **Imports:** always run from the repo root. Import as packages: `from shared.models import Ride`, `from dispatch.core import assign`, `from voice import pipeline`. Never use `sys.path` hacks.

---

## 4. Repository layout and ownership

```
/                       repo root. Run everything from here.
  requirements.txt      orchestrator
  conftest.py           orchestrator (makes the root importable for pytest)
  AGENTS.md, CLAUDE.md  orchestrator (pointers to this file)
  ORCHESTRATOR.md       orchestrator runbook (agents: ignore)
/shared                 ORCHESTRATOR ONLY. Read-only for all agents.
  CONTEXT.md            this file
  models.py             canonical Pydantic models + constants
  graph.py              Graph class + load_graph()
  graph.json            campus nodes + edges (demo map)
  aliases.json          spoken names for each location (voice uses these)
  sarvam_notes.md       verified Sarvam API usage
  sarvam_smoke.py       orchestrator's API check script
  samples/              real test audio WAVs (created by sarvam_smoke.py)
  mocks/                sample State / Ride / VoiceBookResponse JSON
/tasks                  ORCHESTRATOR ONLY. One detailed task file per agent.
/acceptance             ORCHESTRATOR ONLY. Acceptance tests. NEVER edit these.
  fixtures/test_graph.json   frozen copy of the graph used by tests
/dispatch               Agent A: routing + assignment logic
/backend                Agent B: FastAPI server, state, simulation, WebSocket
/voice                  Agent C: Sarvam STT / intent / TTS pipeline
/frontend               Agent D: student.html, driver.html, admin.html
```

**Rules:** edit only your own folder. Import from `shared/` and never copy or redefine its models. Never edit `acceptance/`. If a test looks wrong, report it (see Section 9, rule 3).

---

## 5. Data models (canonical: the code in `shared/models.py` is authoritative)

Units: distance in **meters**, time in **seconds** (unix timestamps, int), ETA in **whole minutes, rounded up**.
Constants (import them from `shared.models`): `EV_SPEED_M_PER_MIN = 250`, `EV_SPEED_M_PER_S = 250/60`, `EV_CAPACITY = 4`, `NO_SHOW_SECONDS = 120`, `TICK_SECONDS = 1.0`, `DEFAULT_EV_STARTS = {"ev_1": "main_gate", "ev_2": "hostel_b", "ev_3": "library"}`.
All IDs are lowercase snake_case strings.

```text
Location:  id, name, x, y

EV:
  id: str                  "ev_1"
  current_node: str        last node the EV was exactly at
  route: list[str]         upcoming nodes, NOT including current_node. route[0] = node it is driving to
  progress: float          0..1 along edge current_node -> route[0]. 0 when waiting/idle
  stops: list[Stop]        upcoming pickups/drops in order
  seats_free: int          EV_CAPACITY minus rides assigned/waiting_at_pickup/picked on this EV
  status: "idle" | "enroute" | "waiting"

Stop:      ride_id, node, kind: "pickup" | "drop"

Ride:
  id: str                  "ride_1", "ride_2", ... counter starts at 1
  student_name, pickup, drop, lang
  status: pending | assigned | waiting_at_pickup | picked | done | no_show | cancelled
  ev_id: str | None
  eta_min: int | None      assigned -> mins to pickup; waiting_at_pickup -> 0;
                           picked -> mins to drop; otherwise None
  created_at: int
  arrived_at: int | None   when the EV reached the pickup

State:          evs, rides, server_time
BookingIntent:  pickup | None, drop | None, confidence 0..1, needs_clarification, reply_text
Assignment:     ev_id, stops, route, eta_min, cost_m     (return value of dispatch.assign)
RideRequest:    student_name, pickup, drop, lang
RideIdRequest:  ride_id
VoiceBookResponse: transcript, intent, ride | None, reply_audio_b64
ErrorResponse:  error
```

---

## 6. API contract (backend, port 8000)

| Method | Path | Body | Returns | Errors |
|---|---|---|---|---|
| GET | `/locations` | none | `list[Location]` | |
| GET | `/state` | none | `State` | |
| POST | `/ride` | JSON `RideRequest` | `Ride` | 400 bad location / pickup == drop |
| POST | `/ride/{id}/cancel` | none | `Ride` | 404 unknown, 409 already final or picked |
| POST | `/ev/{id}/arrived` | none | `EV` | 404 unknown, 409 not at next stop |
| POST | `/ev/{id}/picked` | JSON `RideIdRequest` | `Ride` | 404, 409 not waiting for this ride |
| POST | `/ev/{id}/dropped` | JSON `RideIdRequest` | `Ride` | 404, 409 ride not on board this EV |
| POST | `/voice/book` | multipart: `audio` (file), `lang`, `student_name` | `VoiceBookResponse` | 503 voice module missing, 502 Sarvam failure |
| WS | `/live` | none | every 1 s: `{"type": "state", "data": State}` | |

Every error response is `{"error": "<message>"}` with the status code shown above. It must NOT use FastAPI's default `{"detail": ...}` shape.
The backend also serves static files: `/frontend/...` → `frontend/` folder, `/shared/...` → `shared/` folder, and allows CORS from any origin.

---

## 7. Dispatch rules (Agent A implements, Agent B calls)

```python
from dispatch.core import assign, shortest_path, plan_route, compute_etas
assign(ride: Ride, evs: list[EV], graph: Graph) -> Assignment | None      # pure, no mutation
```
- Shortest paths: Dijkstra on edge meters.
- For each EV with `seats_free > 0`, try every insertion of the new pickup and drop into its current `stops` (pickup before drop). Cost in **meters** (integers, so ties are exact):
  `cost_m = distance_to_new_pickup + sum over existing drop stops of (new_arrival - old_arrival)`
- If an EV is `waiting`, the new pickup may not be inserted at position 0.
- Lowest cost wins. Tie-break: lowest `ev.id`, then lowest pickup index, then lowest drop index. This works automatically when you loop in that order and replace only on strictly smaller cost.
- Returns `None` if no EV has a free seat. The ride stays `pending` and the backend retries it every tick.
- The exact algorithm is in `tasks/TASK_A_dispatch.md`.

## 8. Voice pipeline (Agent C implements, Agent B calls)

1. Audio + `lang` → Sarvam STT (`saaras:v3`) → transcript
2. Transcript + location list + aliases → Sarvam LLM (`sarvam-105b`, JSON mode) → `{pickup, drop, confidence}`
3. If the LLM fails, fall back to rule-based alias matching. The demo must never crash.
4. Missing pickup/drop, pickup == drop, or confidence < 0.6 → `needs_clarification = true` and `reply_text` = a clarification question from fixed templates in the user's language
5. Backend creates the ride, then builds `reply_text` from a fixed confirmation template, and calls Sarvam TTS (`bulbul:v3`) → base64 WAV
6. Standalone CLI: `python -m voice.run shared/samples/hi_hostel_a_to_academic.wav hi-IN` prints transcript + BookingIntent JSON

## 9. Rules for every agent

1. Stay inside your folder. `shared/`, `tasks/`, `acceptance/` are read-only.
2. Use the models from `shared/models.py` exactly. Do not rename, add, or remove fields.
3. If the contract or an acceptance test looks wrong or blocks you, STOP and write the problem to `<your_folder>/CONTRACT_ISSUE.md` (what, where, why, suggested fix). Do not work around it silently.
4. Until other modules are ready, develop against `shared/mocks/` or small stubs. Do not wait on them.
5. No extra features, no speculative abstractions, no refactoring outside your task.
6. Prefer simple, readable code that works in a live demo over clever code. Short functions and clear names. Add a comment only where the logic is not obvious.
7. You are done only when `python -m pytest acceptance/<your test file> -q` passes and the manual checks in your task file work.
8. At the end, write `<your_folder>/README.md` with: how to run it, what's done, what's stubbed or known broken.

## 10. Demo scenario (everything must support this)

- 3 EVs start at `main_gate` (ev_1), `hostel_b` (ev_2), `library` (ev_3)
- Ride 1: text booking, Hostel A → Library. Gets ev_2 (closest), ETA 1 min.
- Ride 2: voice booking in **Hindi**, Hostel A → Academic Block, booked right after Ride 1. **Pooled into ev_2** (same pickup, drop is on the way).
- Ride 3: voice booking in **English or Tamil**, Medical Center → Cafeteria. Gets **ev_1** (a different EV).
- Ride 4: Cafeteria → Sports Complex. Gets ev_3. Nobody taps "Picked up", so after 120 s it becomes **no_show** and ev_3 continues.
- The admin view shows all of this live.
