Hi, I'm Shivansh Sharma. I built CampusRide: a voice-first EV dispatch system for NIT Trichy, powered end to end by Sarvam AI. Students book a campus EV just by speaking in their own language, and see which EV is coming, its shortest route and a live ETA.

CampusRide — Voice-First Campus EV Dispatch, powered by Sarvam AI

Live demo: [Vercel link]
Repo: https://github.com/Doffcode/campusride

The Problem
Campus EVs are coordinated over a phone call. Students call a number and wait with no idea when the EV will come. Multiple EVs have no coordination, so they take inefficient routes, and students and drivers often don't share a language.

What it does
- Student speaks in any of 11 Indian languages or Hinglish ("Opal se Orion jana hai"), and Sarvam Saaras v4 transcribes it
- Language auto-detected by Sarvam, no menu; campus place names are passed to Saaras as key terms so "Garnet Hostel" isn't misheard
- Sarvam-105B understands the trip and extracts the pickup and destination from natural speech; if only the destination is said, the student's pin on the map is the pickup
- The EV that can reach the student soonest is assigned automatically, and routed along the shortest road path
- Live map: EVs move only along campus roads, with a live ETA for every student and a route preview before booking
- The confirmation and the "EV has arrived" announcement are translated by Sarvam Translate and spoken by Sarvam Bulbul v3 in the student's own language
- Still works if the network drops (offline fallback + tap-to-book on the map)

Pipeline (Sarvam AI at every language step)
```
Student Voice → Sarvam Saaras v4 (speech-to-text + language ID) → Sarvam-105B (extracts {pickup, drop}) → Shortest-path dispatch → Live map + ETA
Booking / Arrival → Sarvam Translate (student's language) → Sarvam Bulbul v3 (text-to-speech) → Student hears it
```

Stack
Sarvam AI (Saaras v4, Sarvam-105B, Sarvam Translate, Bulbul v3) · Python (FastAPI) · Vanilla JavaScript + SVG · Vercel
