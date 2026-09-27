# ⚡ CampusRide: voice-first EV dispatch for NIT Trichy

Students book campus EVs by **speaking in their own language** (Hindi, Tamil, English, Hinglish). The system picks the nearest EV, routes it along the **shortest road path**, and shows a **live ETA**, instead of calling a number and waiting blind.

Built with **Sarvam AI**:
- **Saaras v3** turns speech into text, with automatic language detection
- **Sarvam-105B** extracts the pickup and destination from what the student said
- **Bulbul v3** reads back the confirmation and the "EV has arrived" announcement in the student's language

## Run locally
```powershell
powershell -ExecutionPolicy Bypass -File mvp\run.ps1
```
Open http://localhost:8000. For voice, copy `.env.example` to `.env` and add your `SARVAM_API_KEY`.

## Deploy on Vercel
1. Import this GitHub repo in Vercel. No build settings are needed: `app.py` is the FastAPI entrypoint and `public/` is the frontend.
2. Project → Settings → Environment Variables: add `SARVAM_API_KEY`.
3. Redeploy. Vercel serves over HTTPS, so the mic also works on phones.

## Layout
```
public/        frontend: map, shortest paths, dispatch, EV simulation (vanilla JS + SVG)
mvp/           FastAPI backend: Sarvam STT / LLM / TTS proxy + campus map (campus.json)
app.py         Vercel entrypoint
```
Details and the demo script: [mvp/README.md](mvp/README.md).
`shared/`, `tasks/`, `acceptance/` hold the spec for a fuller multi-agent version (ride pooling, no-shows, driver app). They are not needed for the MVP.
