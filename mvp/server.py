"""CampusRide MVP server. It only talks to Sarvam, so the API key never reaches the browser.
All map / dispatch / simulation logic runs in the browser (public/app.js).

Local:  .venv\\Scripts\\python -m uvicorn mvp.server:app --port 8000   (from the repo root)
Vercel: app.py at the repo root re-exports this app; public/ is served by Vercel's CDN.
"""

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mvp import nlu, sarvam

PUBLIC = Path(__file__).resolve().parent.parent / "public"
app = FastAPI(title="CampusRide MVP")


@app.middleware("http")
async def no_cache(request, call_next):
    # Edits to the map/app show up on a plain reload during the event.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


class UnderstandRequest(BaseModel):
    text: str
    lang: str = "en-IN"


class SpeakRequest(BaseModel):
    text: str
    lang: str = "en-IN"
    translate: bool = False   # text is English: translate it with Sarvam Translate first


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


@app.get("/api/campus")
def campus():
    return nlu.CAMPUS


@app.get("/api/health")
def health():
    return {"ok": True, "sarvam_key": sarvam.has_key()}


@app.post("/api/understand")
async def understand(req: UnderstandRequest):
    text = req.text.strip()
    if not text:
        return JSONResponse({"error": "empty text"}, status_code=400)
    t0 = time.perf_counter()
    result = await asyncio.to_thread(nlu.understand, text, req.lang)
    return {"transcript": text, "lang": req.lang, **result, "timings": {"llm_ms": _ms(t0)}}


@app.post("/api/voice")
async def voice(audio: UploadFile = File(...), lang: str = Form("unknown")):
    data = await audio.read()
    if len(data) < 1000:
        return JSONResponse({"error": "recording too short, hold the mic a bit longer"}, status_code=400)
    t0 = time.perf_counter()
    try:
        transcript, detected = await asyncio.to_thread(
            sarvam.stt, data, audio.filename or "speech.webm", lang, nlu.KEYTERMS)
    except sarvam.SarvamError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    stt_ms = _ms(t0)
    if not transcript.strip():
        return JSONResponse({"error": "didn't catch that, please speak again"}, status_code=422)
    t1 = time.perf_counter()
    result = await asyncio.to_thread(nlu.understand, transcript, detected)
    return {"transcript": transcript, "lang": detected, **result,
            "timings": {"stt_ms": stt_ms, "llm_ms": _ms(t1)}}


@app.post("/api/speak")
async def speak(req: SpeakRequest):
    if not req.text.strip():
        return JSONResponse({"error": "empty text"}, status_code=400)
    text, timings = req.text, {}
    if req.translate and req.lang != "en-IN":
        t0 = time.perf_counter()
        try:
            text = await asyncio.to_thread(sarvam.translate, req.text, req.lang)
        except sarvam.SarvamError:
            pass   # speak the English text rather than nothing
        timings["translate_ms"] = _ms(t0)
    t0 = time.perf_counter()
    try:
        audio = await asyncio.to_thread(sarvam.tts, text, req.lang)
    except sarvam.SarvamError as e:
        return JSONResponse({"error": str(e), "text": text}, status_code=502)
    timings["tts_ms"] = _ms(t0)
    return {"audio_b64": audio, "text": text, "timings": timings}


# Local dev serves the frontend too. On Vercel, public/ is served by the CDN and may not exist in the function bundle.
if PUBLIC.is_dir():
    app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="public")
