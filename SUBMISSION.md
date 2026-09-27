Hi, I'm Shivansh Sharma. I built CampusRide: a voice-first EV dispatch system for NIT Trichy. Students book a campus EV just by speaking in their own language, and see which EV is coming, its shortest route and a live ETA.

CampusRide — Voice-First Campus EV Dispatch

Live demo: [Vercel link]
Repo: https://github.com/Doffcode/campusride

The Problem
Campus EVs are coordinated over a phone call. Students call a number and wait with no idea when the EV will come. Multiple EVs have no coordination, so they take inefficient routes, and students and drivers often don't share a language.

What it does
- Student speaks in Hindi, Tamil, English or Hinglish ("Opal se Orion jana hai")
- Language auto-detected, no menu
- Pickup and destination understood from natural speech; if only the destination is said, the student's pin on the map is used as pickup
- The EV that can reach the student soonest is assigned automatically, and routed along the shortest road path
- Live map: EVs move only along campus roads, with a live ETA for every student and a route preview before booking
- Confirmation and "EV has arrived" announcements are spoken back in the student's language
- Still works if the AI is unavailable (offline fallback + tap-to-book on the map)

Pipeline
```
Student Voice → Speech-to-Text + Language ID → LLM extracts {pickup, drop} → Shortest-path dispatch (Dijkstra) → Live map + ETA
Booking / Arrival → Reply in student's language → Text-to-Speech → Student hears it
```

Stack
Python (FastAPI) · Vanilla JavaScript + SVG · Vercel · Sarvam AI (Saaras v3 STT, Sarvam-105B, Bulbul v3 TTS)
