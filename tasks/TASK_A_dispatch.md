# TASK A: Dispatch engine (`/dispatch`)

You are **Agent A**. You only create/edit files inside `dispatch/`.
First read `shared/CONTEXT.md`, `shared/models.py`, `shared/graph.py`. Then read this file fully.

## Goal
A pure-Python module (no I/O, no network, no globals that change) that:
1. finds shortest paths on the campus graph,
2. decides which EV gets a new ride and in what order it visits its stops,
3. computes routes and ETAs for an EV.

The backend (Agent B) imports these 4 functions. Their names and signatures are FIXED.

## Files to create

```
dispatch/__init__.py        already exists (empty). Leave it empty.
dispatch/core.py            ALL the code below
dispatch/README.md          at the end
```
Do not create any other files. Only use the standard library + `shared`.

## Imports at the top of `dispatch/core.py`

```python
import heapq
import math

from shared.graph import Graph
from shared.models import EV, EV_SPEED_M_PER_MIN, Assignment, Ride, Stop
```

## Function 1: `shortest_path`

```python
def shortest_path(graph: Graph, a: str, b: str) -> tuple[int, list[str]]:
    """Return (meters, path) for the shortest path from a to b.
    path EXCLUDES a and INCLUDES b.   a == b  ->  (0, [])
    Raise ValueError if a or b is not a node, or b is unreachable."""
```
Algorithm: standard Dijkstra with `heapq`.
- `dist = {a: 0}`, `prev = {}`, heap `[(0, a)]`.
- Pop `(d, u)`. If `d > dist[u]`, skip. If `u == b`, stop.
- For each `(v, w)` in `graph.neighbors(u).items()`: if `d + w < dist.get(v, inf)`, then set `dist[v] = d + w`, `prev[v] = u`, and push.
- Rebuild the path by walking `prev` back from `b` to `a`, reverse it, and drop `a`.
- **Tie rule (important for tests):** push heap items as `(distance, node_id)`. Equal distances then pop in alphabetical order. Only replace a distance on strictly smaller `<`.

Examples (on `acceptance/fixtures/test_graph.json`):
- `shortest_path(g, "main_gate", "hostel_a")` → `(1000, ["admin_block", "library", "academic_block", "hostel_a"])`
- `shortest_path(g, "hostel_b", "library")` → `(550, ["academic_block", "library"])` (the direct 350 m edge beats going via hostel_a, which is 650). Your Dijkstra computes this. Never hand-code paths.
- `shortest_path(g, "library", "library")` → `(0, [])`

## Function 2: `plan_route`

```python
def plan_route(graph: Graph, start: str, stops: list[Stop]) -> list[str]:
    """Concatenate shortest paths start -> stops[0].node -> stops[1].node -> ...
    Returns the node list NOT including start. Consecutive stops on the same node add nothing.
    Example: start="hostel_b", stops at [hostel_a, hostel_a, academic_block, library]
             -> ["hostel_a", "academic_block", "library"]"""
```
Implementation: `route = []; cur = start; for s in stops: _, p = shortest_path(graph, cur, s.node); route += p; cur = s.node`.

## Helper: `_arrivals` (private)

```python
def _arrivals(graph: Graph, start: str, stops: list[Stop]) -> list[int]:
    """Cumulative meters from start to each stop, same order as stops."""
    out, cur, total = [], start, 0
    for s in stops:
        total += shortest_path(graph, cur, s.node)[0]
        out.append(total)
        cur = s.node
    return out
```
(Optional speed-up: cache shortest_path results in a dict inside `assign`. Not required. The graph is tiny.)

## Function 3: `assign` (the core)

```python
def assign(ride: Ride, evs: list[EV], graph: Graph) -> Assignment | None:
```

**Must NOT mutate** `ride`, `evs`, or any EV/stop. Build new lists (`list(ev.stops)` and then `insert`).

Exact algorithm (follow it literally; the tests depend on the exact order):

```
P = Stop(ride_id=ride.id, node=ride.pickup, kind="pickup")
D = Stop(ride_id=ride.id, node=ride.drop,   kind="drop")
best = None           # (cost_m, ev, new_stops, pickup_meters)

for ev in sorted(evs, key=lambda e: e.id):
    if ev.seats_free <= 0: continue
    old = ev.stops
    old_arr = _arrivals(graph, ev.current_node, old)
    # old arrival time of each existing DROP stop, keyed by ride_id
    old_drop = {s.ride_id: old_arr[k] for k, s in enumerate(old) if s.kind == "drop"}
    n = len(old)
    first_i = 1 if ev.status == "waiting" else 0
    for i in range(first_i, n + 1):             # pickup position
        for j in range(i + 1, n + 2):           # drop position (in the list AFTER inserting P)
            new = list(old)
            new.insert(i, P)
            new.insert(j, D)
            arr = _arrivals(graph, ev.current_node, new)
            pickup_m = arr[i]
            detour = 0
            for k, s in enumerate(new):
                if s.kind == "drop" and s.ride_id in old_drop:
                    detour += arr[k] - old_drop[s.ride_id]
            cost = pickup_m + detour
            if best is None or cost < best[0]:      # STRICT <  (this is the tie-break)
                best = (cost, ev, new, pickup_m)

if best is None: return None
cost, ev, new, pickup_m = best
return Assignment(
    ev_id=ev.id,
    stops=new,
    route=plan_route(graph, ev.current_node, new),
    eta_min=math.ceil(pickup_m / EV_SPEED_M_PER_MIN),
    cost_m=cost,
)
```
Notes:
- If `ev.status == "waiting"` and `n == 0` (should not happen), then `range(1, 1)` is empty and that EV is skipped. That's fine.
- Validation: if `ride.pickup` or `ride.drop` is not in the graph, raise `ValueError`. (`shortest_path` will do it.)
- Distances are integers. Only `eta_min` is divided, and it's rounded UP with `math.ceil`. `0` meters → `0` min.

## Function 4: `compute_etas`

```python
def compute_etas(graph: Graph, ev: EV) -> dict[str, int]:
    """Minutes (rounded up) until the EV reaches each ride's NEXT stop in ev.stops.
    Key = ride_id, value = minutes to that ride's FIRST stop in ev.stops
    (the pickup if not yet picked, else the drop). Uses the EV's partial progress."""
```
Algorithm:
```
if ev.progress > 0 and ev.route:
    start = ev.route[0]
    base = graph.edge_len(ev.current_node, ev.route[0]) * (1 - ev.progress)
else:
    start = ev.current_node
    base = 0
arr = _arrivals(graph, start, ev.stops)
out = {}
for k, s in enumerate(ev.stops):
    if s.ride_id not in out:
        out[s.ride_id] = math.ceil((base + arr[k]) / EV_SPEED_M_PER_MIN - 1e-9)
return out
```
(`- 1e-9` stops floating-point noise such as 1.0000000002 from becoming 2.)

## Acceptance tests
`acceptance/test_dispatch.py` (do NOT edit). Run from repo root:
```
python -m pytest acceptance/test_dispatch.py -q
```
They cover: shortest paths, plan_route, single ride choice, pooling, waiting-EV rule, capacity full → None, tie-break by id, no mutation, compute_etas with progress.

You may add your own tests in `dispatch/tests/`, but the acceptance file is what counts.

## Do NOT
- add classes, caching layers, config files, logging, CLI
- import anything from `backend/`, `voice/`, `frontend/`
- change any signature above
- use floats for cost

## Done when
- `python -m pytest acceptance/test_dispatch.py -q` → all passed
- `dispatch/README.md` written (3 to 10 lines)
