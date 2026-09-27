# CampusRide MVP: voice-first EV dispatch for NIT Trichy

The working demo. This folder is self-contained. (`shared/`, `tasks/`, `acceptance/` hold the older multi-agent spec for a fuller version; the demo doesn't need them.)

## Run
```
powershell -ExecutionPolicy Bypass -File mvp\run.ps1
```
Open http://localhost:8000 in **Chrome** on the laptop (the mic only works on `localhost` or https, not on a phone over the LAN IP).

Voice needs a key: copy `.env.example` to `.env` and paste `SARVAM_API_KEY=sk_...`. The header pill turns green ("Sarvam AI connected").
Without a key everything else still works: map booking, and typed requests (these use offline rules).

Tests (offline): `.venv\Scripts\python -m pip install -r requirements-dev.txt` then `.venv\Scripts\python -m pytest mvp -q`

## What it does
| Feature | How |
|---|---|
| Speak in Hindi / Tamil / English / Hinglish | Sarvam **Saaras v3** speech-to-text (auto-detects the language) |
| Understand "Opal se Orion jana hai" | Sarvam **Sarvam-105B** extracts `{pickup, drop}` from the campus place list. Falls back to alias rules if the LLM fails. |
| Spoken confirmation + "EV has arrived" announcement | Sarvam **Bulbul v3**, in the student's language |
| Only the destination said | Pickup = the student's pink pin on the map |
| Only the pickup said | Asks "where do you want to go?" and remembers the pickup for the next sentence |
| Student location | Drag the pink pin; it snaps to the nearest pickup point. Shows the live "nearest EV in N min". |
| Shortest path | Dijkstra on the road graph. The dotted pink line previews your trip, the solid colored line is a booked trip, the dashed line is where an EV is heading now. |
| Multiple EVs | Each ride goes to the EV that can reach the pickup soonest, including finishing its current jobs (so it queues if all are busy) |
| Roads | EVs move only along road edges, at 15 km/h (sim speed 1×/4×/8×/16×) |
| Live | ETAs count down, pins show each waiting student, KPIs, fleet status, and a click on a ride highlights its route |

## Demo script (3 min)
1. **Problem (20 s):** "Today you call a number and wait with no idea when the EV comes. 3 EVs, no coordination."
2. Click **▶ Load 3 sample rides** (Pick on map tab). Three students, three EVs, each takes its shortest road path.
3. **Voice, Hindi:** drag the pink pin to Opal Hostel. Tap the mic: "मुझे ओरियन जाना है". Show the pipeline steps with timings. Only the destination was said, so the pickup comes from the pin. The Hindi voice reply plays.
4. **Voice, Tamil or English** from another spot → a different EV, or it queues behind a busy one.
5. Point at the map: the dashed EV heading to the pickup, the pulse while boarding, the passenger badge, the arrival announcement in the student's language.
6. **Close:** "Sarvam handles the language (Saaras, Sarvam-105B, Bulbul) in 10+ Indian languages. A deterministic algorithm makes the dispatch decisions. Next: the same voice agent on a phone number (IVR) for students without smartphones, ride pooling, no-show auto-cancel, and class-timetable demand prediction."

## If something goes wrong live
- Sarvam slow or down: type the sentence instead (it falls back to rules), or use the Pick on map tab.
- The mic is blocked: click the 🔒 in the address bar → allow the microphone, or type.
- Things get messy: the **Reset** button (top right).

## Customising (good small jobs for a coding agent)
- Places/roads: `mvp/campus.json` (`nodes` with x/y on a 1000×700 canvas, `edges` = roads, `aliases` = spoken names, optional `"b": [dx, dy]` moves the building icon).
- Reply sentences: `T` at the top of `public/app.js`.
- Speed/boarding time: `SPEED`, `DWELL` in `public/app.js`.
