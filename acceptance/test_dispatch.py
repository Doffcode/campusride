"""Acceptance tests for Agent A (dispatch). OWNER: orchestrator. DO NOT EDIT.

Run: python -m pytest acceptance/test_dispatch.py -q
"""

from pathlib import Path

import pytest

from dispatch.core import assign, compute_etas, plan_route, shortest_path
from shared.graph import load_graph
from shared.models import EV, Ride, Stop

G = load_graph(Path(__file__).parent / "fixtures" / "test_graph.json")


def ride(rid, pickup, drop):
    return Ride(id=rid, student_name="S", pickup=pickup, drop=drop, lang="en-IN", created_at=0)


def ev(eid, node, **kw):
    return EV(id=eid, current_node=node, **kw)


def P(rid, node):
    return Stop(ride_id=rid, node=node, kind="pickup")


def D(rid, node):
    return Stop(ride_id=rid, node=node, kind="drop")


def demo_fleet():
    return [ev("ev_1", "main_gate"), ev("ev_2", "hostel_b"), ev("ev_3", "library")]


# ---------------------------------------------------------------- shortest_path
def test_shortest_path_long():
    assert shortest_path(G, "main_gate", "hostel_a") == (
        1000, ["admin_block", "library", "academic_block", "hostel_a"])


def test_shortest_path_prefers_direct_edge():
    assert shortest_path(G, "hostel_b", "library") == (550, ["academic_block", "library"])


def test_shortest_path_same_node():
    assert shortest_path(G, "library", "library") == (0, [])


def test_shortest_path_unknown_node():
    with pytest.raises(ValueError):
        shortest_path(G, "library", "hostel_z")


# ---------------------------------------------------------------- plan_route
def test_plan_route_skips_repeated_nodes():
    stops = [P("r1", "hostel_a"), P("r2", "hostel_a"), D("r2", "academic_block"), D("r1", "library")]
    assert plan_route(G, "hostel_b", stops) == ["hostel_a", "academic_block", "library"]


def test_plan_route_empty():
    assert plan_route(G, "library", []) == []


# ---------------------------------------------------------------- assign
def test_single_ride_goes_to_closest_ev():
    a = assign(ride("ride_1", "hostel_a", "library"), demo_fleet(), G)
    assert a.ev_id == "ev_2"
    assert a.stops == [P("ride_1", "hostel_a"), D("ride_1", "library")]
    assert a.route == ["hostel_a", "academic_block", "library"]
    assert a.eta_min == 1
    assert a.cost_m == 200


def test_pooling_same_pickup_drop_on_the_way():
    fleet = [
        ev("ev_1", "main_gate"),
        ev("ev_2", "hostel_b", status="enroute", seats_free=3,
           route=["hostel_a", "academic_block", "library"],
           stops=[P("ride_1", "hostel_a"), D("ride_1", "library")]),
        ev("ev_3", "library"),
    ]
    a = assign(ride("ride_2", "hostel_a", "academic_block"), fleet, G)
    assert a.ev_id == "ev_2"
    assert a.stops == [P("ride_2", "hostel_a"), P("ride_1", "hostel_a"),
                       D("ride_2", "academic_block"), D("ride_1", "library")]
    assert a.route == ["hostel_a", "academic_block", "library"]
    assert a.eta_min == 1
    assert a.cost_m == 200


def test_waiting_ev_keeps_its_current_pickup_first():
    fleet = [
        ev("ev_1", "main_gate"),
        ev("ev_2", "hostel_a", status="waiting", seats_free=3,
           route=["academic_block", "library"],
           stops=[P("ride_1", "hostel_a"), D("ride_1", "library")]),
        ev("ev_3", "medical_center"),
    ]
    a = assign(ride("ride_2", "hostel_a", "academic_block"), fleet, G)
    assert a.ev_id == "ev_2"
    assert a.stops[0] == P("ride_1", "hostel_a")
    assert a.stops == [P("ride_1", "hostel_a"), P("ride_2", "hostel_a"),
                       D("ride_2", "academic_block"), D("ride_1", "library")]
    assert a.route == ["academic_block", "library"]
    assert a.eta_min == 0


def test_full_ev_is_skipped():
    fleet = [ev("ev_1", "main_gate"), ev("ev_2", "hostel_b", seats_free=0), ev("ev_3", "library")]
    a = assign(ride("ride_1", "hostel_a", "library"), fleet, G)
    assert a.ev_id == "ev_3"
    assert a.route == ["academic_block", "hostel_a", "academic_block", "library"]
    assert a.eta_min == 2


def test_no_capacity_returns_none():
    fleet = [ev(e.id, e.current_node, seats_free=0) for e in demo_fleet()]
    assert assign(ride("ride_1", "hostel_a", "library"), fleet, G) is None


def test_tie_break_lowest_ev_id():
    fleet = [ev("ev_2", "library"), ev("ev_1", "library")]  # deliberately unsorted
    a = assign(ride("ride_1", "library", "cafeteria"), fleet, G)
    assert a.ev_id == "ev_1"
    assert a.eta_min == 0


def test_demo_ride_3_goes_to_ev_1():
    a = assign(ride("ride_3", "medical_center", "cafeteria"), demo_fleet(), G)
    assert a.ev_id == "ev_1"
    assert a.eta_min == 1


def test_assign_does_not_mutate_inputs():
    fleet = [
        ev("ev_1", "main_gate"),
        ev("ev_2", "hostel_b", status="enroute", seats_free=3,
           route=["hostel_a", "academic_block", "library"],
           stops=[P("ride_1", "hostel_a"), D("ride_1", "library")]),
    ]
    r = ride("ride_2", "hostel_a", "academic_block")
    before = ([e.model_dump() for e in fleet], r.model_dump())
    assign(r, fleet, G)
    assert ([e.model_dump() for e in fleet], r.model_dump()) == before


# ---------------------------------------------------------------- compute_etas
def test_etas_with_partial_progress():
    e = ev("ev_2", "hostel_b", status="enroute", seats_free=2, progress=0.4,
           route=["hostel_a", "academic_block", "library"],
           stops=[P("ride_1", "hostel_a"), P("ride_2", "hostel_a"),
                  D("ride_2", "academic_block"), D("ride_1", "library")])
    assert compute_etas(G, e) == {"ride_1": 1, "ride_2": 1}


def test_etas_exact_minutes_not_rounded_up_twice():
    e = ev("ev_1", "main_gate", status="enroute",
           route=["admin_block", "library", "academic_block", "hostel_a"],
           stops=[P("ride_9", "hostel_a")])
    assert compute_etas(G, e) == {"ride_9": 4}   # exactly 1000 m = 4.0 min


def test_etas_progress_on_first_edge():
    e = ev("ev_1", "main_gate", status="enroute", progress=0.5,
           route=["admin_block", "library", "academic_block", "hostel_a"],
           stops=[P("ride_9", "hostel_a")])
    assert compute_etas(G, e) == {"ride_9": 4}   # 150 + 700 = 850 m = 3.4 -> 4


def test_etas_onboard_ride_uses_drop():
    e = ev("ev_1", "academic_block", status="enroute", route=["library"],
           stops=[D("ride_1", "library")])
    assert compute_etas(G, e) == {"ride_1": 1}


def test_etas_empty():
    assert compute_etas(G, ev("ev_1", "library")) == {}
