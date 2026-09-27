# CampusRide on Sarvam Samvaad: project context

> Paste this whole file into **Genie** (Build → Agents → describe your agent), or keep it open while building.
> Platform: https://indus.sarvam.ai/samvaad (Sarvam Voice Agents). Docs: https://docs.sarvam.ai/conversations/overview

## 1. Problem (NIT Trichy)
- Campus EVs/cabs are coordinated by phone. A student calls a number and waits an unknown time.
- Nobody tells the driver the exact pickup and drop. Drivers get vague info, go to the wrong gate, or don't know the student is waiting.
- There are multiple EVs and nobody decides which one should go.
- Students and drivers speak different languages (Tamil, Hindi, Telugu, English).

## 2. What we build on Samvaad
A voice agent that does the phone work of the human dispatcher:

```
Student ──(speaks: "Opal se Orion jana hai")──▶ STUDENT DESK agent
                                                   │ collects pickup, drop, name
                                                   ▼
                                    DRIVER CALLER agent ──calls──▶ Driver's phone
                                    "Pickup Opal Hostel, drop Orion. Can you take it?
                                     How many minutes to reach Opal Hostel?"
                                                   │ driver: "haan, 5 minute"
                                                   ▼
                  Student hears: "Driver Ramesh accepted. He'll reach Opal Hostel in about 5 minutes."
```

**Core (must work):** the **Driver Caller** agent. Given pickup, drop and student name, it calls the driver, explains the trip clearly in the driver's language, gets yes/no plus an ETA in minutes, and stores them as output variables.
**Next:** the **Student Desk** agent, which collects the trip from the student by voice.
**Stretch:** connect the two through our backend (it picks the nearest driver by shortest road path, triggers the driver call, and reads back the ETA). See `BRIDGE.md`.

## 3. Why Sarvam
- Speech-to-text, the LLM and text-to-speech in 10+ Indian languages, on a real phone call. It works for drivers without a smartphone app.
- Drivers get called in *their* language (Tamil/Hindi), students speak in *theirs*. The agent translates in between.
- The call outcome (accepted, ETA) comes back as structured data, so it can be tracked and shown on a dashboard.

## 4. Campus places (use ONLY these names)
| id | Name to say | Also called |
|---|---|---|
| main_gate | Main Gate | front gate, gate |
| admin | Admin Building | admin block, administration |
| library | Central Library | library, lib |
| octagon | Octagon | computer centre |
| hospital | Hospital | health centre, medical, dispensary |
| orion | Orion | Orion building |
| lhc | Lecture Hall Complex | LHC, lecture hall |
| barn_hall | Barn Hall | Barn |
| diamond | Diamond Hostel | Diamond |
| sac | SAC | Student Activity Centre |
| mega_mess | Mega Mess | mess, canteen |
| sports | Sports Complex | ground, stadium, gym |
| opal | Opal Hostel | Opal, girls hostel |
| agate | Agate Hostel | Agate |
| garnet | Garnet Hostel | Garnet |
| zircon | Zircon Hostel | Zircon |

This is a dummy map for the demo. Replace it with the real list if you have one. The same list is in `mvp/campus.json`, and the web dashboard uses it.

## 5. Languages
- Students: auto-detect; English, Hindi, Tamil, Telugu, and Hinglish code-mix.
- Drivers: start in **Hindi** (or Tamil). Switch language if the driver replies in another one (core tool: Language switch).
- Always say place names in English as written above ("Opal Hostel", "Orion"), because everyone on campus uses these names.

## 6. Rules for both agents (voice UX)
- Short sentences. One question at a time. Never read out lists longer than 3 items.
- Always repeat the key facts back before finishing: pickup, drop, minutes.
- Numbers: say minutes as a number ("5 minutes"). If a driver says "abhi aata hoon" or "thodi der", ask "roughly how many minutes, 5, 10 or 15?"
- Never invent a place, a driver, or an ETA.
- If the person is busy or it's a wrong number: apologise, thank them, end the call (core tool: End call).
- Keep a driver call under 45 seconds.

## 7. Files in this folder
| file | what |
|---|---|
| `CONTEXT.md` | this overview (paste into Genie) |
| `driver_agent.md` | the Driver Caller agent: copy-paste config, prompt, variables, tests |
| `student_agent.md` | the Student Desk agent: copy-paste config, prompt, variables, tests |
| `drivers_cohort.csv` | contact list for an outbound campaign (put your own test phone numbers here) |
| `campus_places.md` | knowledge base file to upload (places + landmarks) |
| `BRIDGE.md` | stretch: connecting the agents to our backend and map |
| `BUILD_CHECKLIST.md` | step by step order for the event |
