# Build order at the event (about 40 minutes)

## 0 to 5 min: setup
- [ ] Log in at https://indus.sarvam.ai/samvaad. Find **Build → Agents**.
- [ ] Ask the organisers: **can we make real outbound calls** (phone number / connection provided)? If not, demo with **Test agent** (you play the driver).

## 5 to 20 min: Driver Caller (the core)
- [ ] Either paste `CONTEXT.md` + `driver_agent.md` into **Genie** ("Build this Driver Caller agent"), or **Create from scratch** and copy each field from `driver_agent.md`.
- [ ] Add input variables: `driver_name`, `student_name`, `pickup_place`, `drop_place`.
- [ ] Add output variables with their extraction prompts: `driver_accepted`, `driver_eta_minutes`, `driver_current_location`, `decline_reason`, `call_summary`.
- [ ] Enable core tools: End call, Language switch, Voicemail detection.
- [ ] **Test agent:** fill the variables (Ramesh / Priya / Opal Hostel / Orion) and run test cases 1, 2, 3, 5 from `driver_agent.md`.
- [ ] Check the extracted variables in Monitor → Agent Analytics → Call Logs.

## 20 to 30 min: make it real
- [ ] If telephony is available: an outbound campaign with `drivers_cohort.csv` (your own phone number), or instant outbound. Answer as the driver.
- [ ] Otherwise build the **Student Desk** (`student_agent.md`) and demo both in Test agent.

## 30 to 40 min: demo prep
- [ ] One clean run: the phone rings, a Hindi conversation happens, and the extracted ETA shows up.
- [ ] Open the CampusRide web map (Vercel link) to show the vision: which EV, the shortest path, the live ETA.
- [ ] Pitch (30 s): "Students and drivers today coordinate by phone calls. Our Sarvam voice agent calls the driver in their language, tells them the exact pickup and drop, and gets a committed ETA back as data. No app is needed for drivers. Next: pick the nearest driver automatically by shortest path and call the student back with the ETA."
