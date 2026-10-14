"""Dispatch engine: shortest paths, EV route planning, and ride assignment.

Pure functions only. No I/O, no mutation of inputs, no module-level state.
"""

import heapq
import math

from shared.graph import Graph
from shared.models import EV, EV_SPEED_M_PER_MIN, Assignment, Ride, Stop


def shortest_path(graph: Graph, a: str, b: str) -> tuple[int, list[str]]:
    """Return (meters, path) for the shortest path from a to b.
    path EXCLUDES a and INCLUDES b. a == b -> (0, []).
    Raises ValueError if a or b is not a node, or b is unreachable."""
    if not graph.has_node(a):
        raise ValueError(f"unknown node: {a}")
    if not graph.has_node(b):
        raise ValueError(f"unknown node: {b}")
    if a == b:
        return 0, []

    dist = {a: 0}
    prev: dict[str, str] = {}
    heap = [(0, a)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        if u == b:
            break
        for v, w in graph.neighbors(u).items():
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if b not in dist:
        raise ValueError(f"{b} is unreachable from {a}")

    path = []
    cur = b
    while cur != a:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return dist[b], path


def plan_route(graph: Graph, start: str, stops: list[Stop]) -> list[str]:
    """Concatenate shortest paths start -> stops[0].node -> stops[1].node -> ...
    Returns the node list NOT including start. Consecutive stops on the same
    node add nothing."""
    route: list[str] = []
    cur = start
    for s in stops:
        _, p = shortest_path(graph, cur, s.node)
        route += p
        cur = s.node
    return route


def _arrivals(graph: Graph, start: str, stops: list[Stop]) -> list[int]:
    """Cumulative meters from start to each stop, same order as stops."""
    out, cur, total = [], start, 0
    for s in stops:
        total += shortest_path(graph, cur, s.node)[0]
        out.append(total)
        cur = s.node
    return out


def assign(ride: Ride, evs: list[EV], graph: Graph) -> Assignment | None:
    """Cheapest-insertion dispatch: try every valid (pickup, drop) insertion
    position in every EV with a free seat, and take the lowest-cost one.

    cost_m = meters to reach the new pickup + total extra meters the
    insertion adds to every existing drop already queued on that EV (the
    detour it imposes on riders already assigned/picked up).

    Does not mutate ride, evs, or any EV/Stop. Returns None if no EV has a
    free seat (the ride stays pending and should be retried by the caller).
    """
    if not graph.has_node(ride.pickup):
        raise ValueError(f"unknown node: {ride.pickup}")
    if not graph.has_node(ride.drop):
        raise ValueError(f"unknown node: {ride.drop}")

    P = Stop(ride_id=ride.id, node=ride.pickup, kind="pickup")
    D = Stop(ride_id=ride.id, node=ride.drop, kind="drop")
    best = None  # (cost_m, ev, new_stops, pickup_meters)

    for ev in sorted(evs, key=lambda e: e.id):
        if ev.seats_free <= 0:
            continue
        old = ev.stops
        old_arr = _arrivals(graph, ev.current_node, old)
        old_drop = {s.ride_id: old_arr[k] for k, s in enumerate(old) if s.kind == "drop"}
        n = len(old)
        first_i = 1 if ev.status == "waiting" else 0
        for i in range(first_i, n + 1):          # pickup position
            for j in range(i + 1, n + 2):          # drop position, after inserting P
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
                if best is None or cost < best[0]:
                    best = (cost, ev, new, pickup_m)

    if best is None:
        return None
    cost, ev, new, pickup_m = best
    return Assignment(
        ev_id=ev.id,
        stops=new,
        route=plan_route(graph, ev.current_node, new),
        eta_min=math.ceil(pickup_m / EV_SPEED_M_PER_MIN),
        cost_m=cost,
    )


def compute_etas(graph: Graph, ev: EV) -> dict[str, int]:
    """Minutes (rounded up) until the EV reaches each ride's NEXT stop in
    ev.stops. Key = ride_id, value = minutes to that ride's FIRST stop in
    ev.stops (the pickup if not yet picked, else the drop). Uses the EV's
    partial progress along its current edge."""
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
