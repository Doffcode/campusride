# dispatch

Pure-Python dispatch engine. No I/O, no state, no mutation of inputs.

- `shortest_path(graph, a, b)` — Dijkstra on the campus graph.
- `plan_route(graph, start, stops)` — concatenated shortest paths through a stop list.
- `assign(ride, evs, graph)` — cheapest-insertion dispatch: tries every valid (pickup, drop) position in every EV with a free seat, and returns the lowest-cost insertion (pickup distance + detour imposed on existing riders already queued on that EV). Respects capacity (`seats_free`) and the "waiting EV can't be bumped off its current pickup" rule. Returns `None` if no EV has a free seat.
- `compute_etas(graph, ev)` — per-ride minutes to each ride's next stop, accounting for the EV's partial progress along its current edge.

Run `python -m pytest acceptance/test_dispatch.py -q` from the repo root — 19/19 passing.

Nothing here is wired into `backend/`, `voice/`, or the `public/` demo yet — see the repo root for how `public/app.js` currently dispatches (a simpler, capacity-unaware greedy) and the plan to replace it with this module.
