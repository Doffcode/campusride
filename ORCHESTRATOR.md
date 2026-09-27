# Orchestrator runbook (for you, not for agents)

## Phase 0: One-time setup (before the event)
```
winget install Python.Python.3.11          # if Python is missing
python -m pip install -r requirements.txt
$env:SARVAM_API_KEY = "sk_..."             # PowerShell. Get it from dashboard.sarvam.ai
python shared/sarvam_smoke.py              # must print [OK] for TTS, STT, CHAT and create shared/samples/*.wav
```
If a smoke step FAILS, fix `shared/sarvam_notes.md` first (agents copy from it).
If CHAT content comes back `None` with `reasoning_effort="low"` but works with `None`, change the notes + TASK_C to `None`.

## Phase 1: Launch agents (all 4 in parallel)
Paste the same prompt into each agent, changing only the letter/folder:

```
You are Agent A in this repo. Your folder is dispatch/.
Read AGENTS.md, then shared/CONTEXT.md, then tasks/TASK_A_dispatch.md, then acceptance/test_dispatch.py.
Implement exactly what the task file says, nothing more. Only edit files in dispatch/.
Loop: write code → run `python -m pytest acceptance/test_dispatch.py -q` → fix → repeat until all pass.
Never edit acceptance/ or shared/. If blocked by the contract, write dispatch/CONTRACT_ISSUE.md and stop.
Finish by pasting the pytest summary line and listing the files you created.
```
| Agent | folder | task | test |
|---|---|---|---|
| A | dispatch/ | tasks/TASK_A_dispatch.md | acceptance/test_dispatch.py |
| B | backend/ | tasks/TASK_B_backend.md | acceptance/test_backend.py |
| C | voice/ | tasks/TASK_C_voice.md | acceptance/test_voice.py |
| D | frontend/ | tasks/TASK_D_frontend.md | manual checklist in the task file |

A weak agent? Give it ONE function at a time: "Implement only shortest_path from the task file, then run the tests."

## Phase 2: Review (every 10 to 15 min)
- `git status` / `git diff --stat`: did anyone touch a folder outside their own? Revert it.
- Look for `*/CONTRACT_ISSUE.md`. You decide the fix, and only you edit `shared/`.
- Red flags: a new package in imports, models redefined locally, `sys.path` hacks, edits in `acceptance/`, the "sarvamai" SDK.

## Phase 3: Merge + verify (in this order)
1. `python -m pytest acceptance/test_dispatch.py -q`
2. `python -m pytest acceptance/test_backend.py -q` (with the REAL dispatch; delete `backend/_dispatch_stub.py` if present)
3. `python -m pytest acceptance/test_voice.py -q`
4. `python -m pytest acceptance -q`: everything green together
5. `uvicorn backend.app:app --port 8000` → open http://localhost:8000/frontend/admin.html, student.html, driver.html?ev=ev_2
6. Walk through the demo script below once, end to end.

## Demo script (about 4 minutes)
Screen: admin.html on the projector. Student view on your phone, or a second tab. Driver view in a third tab.
1. **Problem (20 s):** "Today: call a number, no ETA, EVs wait for no-shows."
2. **Ride 1 (text):** student.html → Aarav, Hostel A → Library → ev_2, ETA 1 min. Point to the map.
3. **Ride 2 (Hindi voice):** "मुझे हॉस्टल ए से एकेडमिक ब्लॉक जाना है" → the transcript appears, the Hindi voice reply plays, and it's **pooled into ev_2**. Admin shows Pooled = 2.
4. **Ride 3 (English/Tamil voice):** "Medical center to cafeteria" → ev_1.
5. **Driver:** driver.html?ev=ev_2 → when it's waiting at Hostel A, tap "Picked up" for both.
6. **Ride 4 (no-show):** Cafeteria → Sports Complex → ev_3 waits → countdown → auto no-show, EV freed. (Book this early in the demo, since it takes 48 s + 120 s.)
7. **Close (30 s):** "Sarvam = the language layer (Saaras STT, Sarvam-105B intent, Bulbul TTS) in 10+ Indian languages. Algorithm = the decisions. Next: the same voice agent on a phone number (IVR) for students without smartphones, and class-timetable demand prediction."

## If something breaks live
- Sarvam down → text booking still works. The voice LLM falls back to rules. Say "offline fallback".
- The backend crashes → restart uvicorn (state resets; re-book quickly).
- Mic blocked → use `python -m voice.run shared/samples/hi_hostel_a_to_academic.wav hi-IN` in a terminal to show the pipeline.
