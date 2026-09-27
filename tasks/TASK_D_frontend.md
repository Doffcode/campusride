# TASK D: Frontend (`/frontend`)

You are **Agent D**. You only create/edit files inside `frontend/`.
First read `shared/CONTEXT.md` (Sections 5 and 6 especially), `shared/models.py`, and the JSON files in `shared/mocks/`. Then read this file fully.

## Goal
Three simple, mobile-friendly pages in plain HTML/CSS/JS. They must look clean and professional in a live demo. No frameworks, no npm, no CDN, no build step.

## Files to create

```
frontend/common.js      shared code: API base, fetch helpers, live connection, SVG map, formatting
frontend/style.css      shared styles
frontend/student.html   book a ride (text + voice) and track it
frontend/driver.html    one EV's next stop + action buttons
frontend/admin.html     live map + tables of all EVs and rides
frontend/README.md      at the end
```
Each HTML file: `<link rel="stylesheet" href="style.css">` and `<script src="common.js"></script>` then its own inline `<script>`.

## Two data modes (build mock mode FIRST)

- **Mock mode**: URL has `?mock=1`. Read `../shared/mocks/state.json` and `../shared/mocks/locations.json` with `fetch`. POST calls just `console.log` and show a toast "mock: <action>". "Live" updates = re-render the same mock every 1 s.
- **Live mode** (default): talk to the backend.
  - `API` = `new URLSearchParams(location.search).get("api") || (location.port === "8000" ? "" : "http://localhost:8000")`
  - WebSocket URL: `API` converted `http→ws` + `/live`. If `API` is `""`, use `` `ws://${location.host}/live` ``.
  - Messages look like `{"type": "state", "data": State}`. Reconnect 2 s after close. While disconnected, show a small red "offline" pill in the header. When connected, show green "live".

How to run in mock mode without the backend (from the repo root):
```
python -m http.server 8080
```
then open http://localhost:8080/frontend/admin.html?mock=1
In live mode, the backend serves the pages at http://localhost:8000/frontend/admin.html

## `common.js` (functions to write; the pages use only these)

```js
const MOCK = new URLSearchParams(location.search).has("mock");
const API = ...;                                  // see above
async function getLocations()                     // -> [{id,name,x,y}]  (mock or GET /locations)
async function api(method, path, body)            // JSON fetch; on non-2xx throw new Error(json.error || status)
function onState(callback)                        // subscribe: callback(State) every update (WS or mock timer)
function locName(id)                              // "hostel_a" -> "Hostel A" (after getLocations loaded)
function evLabel(id)                              // "ev_2" -> "EV 2"
function toast(msg, kind="info")                  // small message bottom-center, auto-hide 3 s; kind: info|error|ok
function statusBadge(status)                      // returns HTML <span class="badge st-<status>">text</span>
function drawMap(svgEl, locations, state, opts)   // see below
const EV_COLORS = {ev_1: "#e4572e", ev_2: "#2f5dd6", ev_3: "#14a098"};  // unknown ev -> "#666"
```

Status badge text + color:
| status | text | color |
|---|---|---|
| pending | Finding EV | grey |
| assigned | EV on the way | blue |
| waiting_at_pickup | EV is here! | orange (pulse) |
| picked | On board | purple |
| done | Completed | green |
| no_show | No-show | red |
| cancelled | Cancelled | dark grey |
| idle / enroute / waiting (EV) | Idle / En route / Waiting | grey / blue / orange |

### `drawMap(svgEl, locations, state, opts)`
- `svgEl` has `viewBox="0 0 1000 800"`. Clear it and redraw everything each call (simple, fast enough).
- Edges: you need the edges. Fetch `../shared/graph.json` in mock mode, or `/shared/graph.json` via `API` in live mode, once. Draw a light grey line (`stroke-width 6`, round caps) for each edge.
- Nodes: white circle r=14 with a dark border + the name label under it (font-size 22).
- Pending/assigned pickups: for each ride in status pending|assigned|waiting_at_pickup, draw a small pin (circle r=8, orange) at its pickup node, offset +18px x per extra ride at the same node.
- EVs: position = if `ev.progress > 0 && ev.route.length` then interpolate `current_node → route[0]` by progress, else at `current_node`. Draw a circle r=20 in `EV_COLORS[ev.id]` with the number ("1", "2", "3") in white bold text. If `status === "waiting"`, add a pulsing ring (CSS animation).
- Planned route: for each EV with a route, draw a dashed polyline in its color (opacity 0.6) from the EV position through its route nodes.
- `opts.highlightEv` (optional): if set, other EVs draw at opacity 0.3.
- Add a CSS `transition` on EV `transform` (use `<g transform="translate(x,y)">` for each EV) so movement looks smooth between 1 s updates.

---

## `student.html`
Layout (single column, max-width 480px, centered):
1. Header "CampusRide", subtitle "Book a campus EV in your language", live pill.
2. **Booking card** (`id="booking-card"`)
   - `input#student-name` (placeholder "Your name")
   - `select#lang`: English (en-IN), हिन्दी (hi-IN), தமிழ் (ta-IN), తెలుగు (te-IN), ಕನ್ನಡ (kn-IN), বাংলা (bn-IN), मराठी (mr-IN)
   - **Voice**: big round button `button#mic-btn` "🎤 Tap to speak". Tap once: start recording (MediaRecorder, `audio/webm`), the button turns red, label "Tap to stop". Tap again: stop and upload. Auto-stop after 20 s.
     Upload: `FormData` with `audio` (Blob, filename `speech.webm`), `lang`, `student_name` → `POST {API}/voice/book`.
     While waiting, show a spinner "Understanding…".
     Show the result in `div#voice-result`: "You said: <transcript>" and the `intent.reply_text`. Play `reply_audio_b64` if not empty: `new Audio("data:audio/wav;base64," + b64).play()`.
     If `ride` is not null → it becomes "my ride". If `needs_clarification` → keep the booking card open so they can speak again.
   - **Text**: `select#pickup`, `select#drop` (filled from getLocations), `button#book-btn` "Book ride" → `POST /ride` with `{student_name, pickup, drop, lang}`. Show the error toast on 400 (e.g. same pickup and drop).
3. **My ride card** (`id="my-ride"`, hidden until a ride exists). The ride id is saved in `localStorage["campusride_ride_id"]`, so a page reload keeps tracking it.
   - Big status badge, `EV 2`, "Pickup: Hostel A → Drop: Library"
   - Big ETA number: assigned → "Arrives in N min" (if N is 0: "Arriving now"); waiting_at_pickup → "EV is waiting for you!" + countdown "Auto-cancels in Ns" (120 − (server_time − arrived_at)); picked → "Reaching drop in N min"; final statuses → message + button "Book another ride" (clears localStorage).
   - `button#cancel-btn` "Cancel ride" (only while pending/assigned/waiting_at_pickup) → `POST /ride/{id}/cancel`.
   - Small map (`svg#map`) with `highlightEv` = my EV.
   - Updates from `onState`: find my ride in `state.rides` by id.

## `driver.html`
- `select#ev-select` (ev_1, ev_2, ev_3; default from `?ev=` or ev_1). Remember the choice in localStorage.
- Header shows EV color dot + "EV 2" + status badge + "Seats free: 3/4".
- **Next stop card** (`id="next-stop"`), very large text (drivers glance at it):
  - "PICKUP" or "DROP" label (green for pickup, blue for drop), location name, student name, ride id small.
  - If no stops: "No rides. Stay at <current location>."
- Buttons (height ≥ 64px, full width):
  - `button#picked-btn` "✅ Student picked up": enabled only when `ev.status === "waiting"` and the next stop is a pickup → `POST /ev/{id}/picked {ride_id}`
  - `button#arrived-btn` "📍 Arrived": enabled when the next stop's node === current_node and status !== "waiting" → `POST /ev/{id}/arrived`
  - `button#dropped-btn` "Drop now": enabled when the next stop is a drop → `POST /ev/{id}/dropped {ride_id}`
  - While waiting: show the no-show countdown "No-show in Ns".
- **Upcoming stops list** (`ol#stops`): every stop with its kind icon, place name, student name.
- Small map with `highlightEv`.

## `admin.html` (the main demo screen, designed for a laptop/projector)
- Two columns on wide screens (map 60% | panels 40%), stacked on mobile.
- Left: `svg#map` large, drawMap with everything.
- Right:
  - **KPI row** (`id="kpis"`): Active rides (assigned+waiting_at_pickup+picked), Pending, Completed, No-shows, Pooled rides (rides whose EV has more than one ride_id in its stops)
  - **EVs table** (`table#ev-table`): color dot, EV, status badge, at/next (current_node → route[0]), seats free, stops count
  - **Rides table** (`table#ride-table`), newest first: id, student, pickup → drop, lang, status badge, EV, ETA
  - Highlight a row for 2 s (yellow fade) when its status changes (compare with the previous state).
- Links at the top to open the student and driver views in new tabs.

## Style
- System font stack, background #f5f6f8, white cards, border-radius 14px, soft shadow, 16px padding.
- Primary color #2f5dd6. Large touch targets. Works at 375px width.
- No external fonts or icon libraries (emojis are fine).

## Acceptance (manual; there are no automated tests for the frontend)
Check each item in mock mode first, then in live mode:
- [ ] admin.html?mock=1 shows 10 places, all edges, 3 colored EVs (ev_2 mid-edge between hostel_b and hostel_a), the dashed route, the pickup pins, both tables, KPIs = Active 3, Pending 1, Completed 1, No-shows 1, Pooled 2
- [ ] driver.html?mock=1&ev=ev_1 shows PICKUP Medical Center, Karthik, and the picked button enabled
- [ ] student.html?mock=1 fills the pickup/drop dropdowns; the booking button shows the mock toast
- [ ] live: booking by text from student.html shows up on admin.html within 1 s
- [ ] live: the mic records, uploads, and plays the reply audio (Chrome; allow the mic permission)
- [ ] live: stopping the backend shows "offline", restarting it reconnects without a page reload
- [ ] no console errors

## Do NOT
- use React/Vue/Tailwind/Leaflet/any CDN
- invent fields not in `shared/models.py`
- call Sarvam directly from the browser (the backend does it; the key must never reach the browser)

## Done when
All checklist items pass and `frontend/README.md` lists what was checked.
