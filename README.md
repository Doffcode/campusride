# ⚡ CampusRide: voice-first EV dispatch for NIT Trichy, powered by Sarvam AI

Students book campus EVs by **speaking in their own language**: 11 Indian languages plus Hinglish. The system picks the nearest EV, routes it along the **shortest road path**, and shows a **live ETA**, instead of calling a number and waiting blind.

Sarvam AI handles every language step:
| Step | Sarvam model |
|---|---|
| Speech → text + language detection (campus place names passed as key terms) | **Saaras v4** (falls back to v3) |
| Understanding the trip: "Opal se Orion jana hai" → `{pickup: opal, drop: orion}` | **Sarvam-105B** |
| Reply in Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi… | **Sarvam Translate** |
| Spoken confirmation + "EV has arrived" announcement | **Bulbul v3** |

## Run locally
```powershell
powershell -ExecutionPolicy Bypass -File mvp\run.ps1
```
Live: https://campusride-plum.vercel.app

Locally: open http://localhost:8000. For voice, copy `.env.example` to `.env` and add your `SARVAM_API_KEY`.

## Deploy on Vercel
1. Import this GitHub repo in Vercel. No build settings are needed: `app.py` is the FastAPI entrypoint and `public/` is the frontend.
2. Project → Settings → Environment Variables: add `SARVAM_API_KEY`.
3. Redeploy. Vercel serves over HTTPS, so the mic also works on phones.

## Layout
```
public/        frontend: map, shortest paths, dispatch, EV simulation (vanilla JS + SVG)
mvp/           FastAPI backend: Sarvam Saaras / Sarvam-105B / Translate / Bulbul proxy + campus map (campus.json)
app.py         Vercel entrypoint
```
Details and the demo script: [mvp/README.md](mvp/README.md).
`shared/`, `tasks/`, `acceptance/` hold the spec for a fuller multi-agent version (ride pooling, no-shows, driver app). They are not needed for the MVP.
