"""Tests that TimeHeadway picks the role_table fast path when the sidecar is
present, and falls back to the lane-graph slow path when it isn't.

Built because TimeHeadway composes FrontVehicleDistance internally, and that
inner monitor has to share the same scenario (with sidecars) for the fast
path to fire. This test pins both halves of that contract.
"""
from collections import defaultdict
from unittest.mock import patch

from humex.components.object import Object
from humex.components.scenario import Scenario
from humex.components.statepoint import StatePoint
from humex.metrics.monitors.catalog import (
    _front_vehicle_utils as _fvu,
)
from humex.metrics.monitors.catalog.time_headway import TimeHeadway
from humex.hmap.hmap import HMap
from humex.hmap.road_map import (
    RoadMap,
    LaneData,
    MapData,
    PointData,
    SegmentData,
)
from humex.hmap.lane_map_builder import build_lane_map
from humex.hmap.role_table_builder import build_role_table


def _seg(points):
    s = SegmentData()
    for x, y in points:
        s.points.append(PointData(x, y, 0.0))
    return s


def _straight_facade(length=100):
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    md.lanes[1] = LaneData(
        id=1,
        center_line=[_seg([(x, 0) for x in range(0, length + 1, 5)])],
        left_boundary=[],
        right_boundary=[],
    )
    am = RoadMap("straight", md)
    lm = build_lane_map(am)
    return HMap(am, lm)


def _add_obj(scn, frame_idx, obj_id, x, ego_speed=10.0, length=4.0, width=2.0):
    ts = scn.timestamps[frame_idx]
    obj = Object(obj_id=obj_id, length=length, width=width)
    obj.update_mutable(
        StatePoint(
            position=(x, 0.0, 0.0),
            velocity=(ego_speed, 0.0, 0.0),
            heading=(0, 0, 0),
        )
    )
    scn.frames[ts].add_obj(obj)
    return obj


def _build_two_car_scenario():
    """Ego at x=10, front car at x=30, both moving at 10 m/s in lane 1."""
    facade = _straight_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 10.0)  # ego
        _add_obj(scn, k, 1, 30.0)  # front car
    return scn, facade


def test_time_headway_uses_fast_path_when_role_table_present():
    """With a role_table attached, find_front_vehicle_on_lane_path must take
    the fast branch (precomputed RoleTable lookup)."""
    scn, facade = _build_two_car_scenario()
    scn.role_table = build_role_table(scn, facade)

    monitor = TimeHeadway(scn)
    # Run the first frame
    first_ts = scn.timestamps[0]
    monitor.curr_frame = scn.frames[first_ts]

    # Wrap the helper to record which branch fired. A sentinel inside the
    # function body would be cleaner but the helper has no instrumentation
    # hooks — counting `RoleTable` isinstance checks is the next-best signal.
    real_find = _fvu.find_front_vehicle_on_lane_path
    fast_calls = {"hit": 0, "slow_hit": 0}

    def _instrumented(ego, frame, scenario, max_search_distance=200.0):
        from humex.hmap.role_table import RoleTable
        rt = getattr(scenario, "role_table", None)
        if isinstance(rt, RoleTable):
            fast_calls["hit"] += 1
        else:
            fast_calls["slow_hit"] += 1
        return real_find(ego, frame, scenario, max_search_distance)

    with patch.object(_fvu, "find_front_vehicle_on_lane_path", _instrumented):
        # Re-import so FrontVehicleDistance's bound name picks up the patch.
        from humex.metrics.monitors.catalog import front_vehicle_distance as fvd_mod
        with patch.object(fvd_mod, "find_front_vehicle_on_lane_path", _instrumented):
            value = monitor.calculate()

    # ego at 10, front at 30: center-gap=20, bumper-to-bumper=20-2-2=16,
    # ego speed 10 m/s ⇒ time headway = 1.6 s.
    assert value is not None
    assert abs(value - 1.6) < 1e-6, f"expected ~1.6s, got {value}"
    assert fast_calls["hit"] == 1, f"fast path did not fire: {fast_calls}"
    assert fast_calls["slow_hit"] == 0


def test_time_headway_falls_back_to_slow_path_without_role_table():
    """Without a role_table, the helper takes the slow lane-graph branch and
    must still produce the same answer (within tolerance)."""
    scn, _ = _build_two_car_scenario()
    # Explicitly no role_table on the scenario.
    assert getattr(scn, "role_table", None) is None

    monitor = TimeHeadway(scn)
    first_ts = scn.timestamps[0]
    monitor.curr_frame = scn.frames[first_ts]

    value = monitor.calculate()
    assert value is not None
    # Slow path's s_gap is the BFS+Frenet projection result. On a perfectly
    # straight lane it equals the center-to-center gap, so the bumper-to-bumper
    # value matches the fast path within numeric tolerance.
    assert abs(value - 1.6) < 1e-3, f"expected ~1.6s, got {value}"


def test_fast_and_slow_agree_on_same_scenario():
    """Both paths should compute the same time_headway on a simple straight
    lane scenario — pins parity so future regressions in either path show up
    here."""
    scn, facade = _build_two_car_scenario()

    # Slow path
    slow_monitor = TimeHeadway(scn)
    slow_monitor.curr_frame = scn.frames[scn.timestamps[0]]
    slow_value = slow_monitor.calculate()

    # Fast path: attach role_table
    scn.role_table = build_role_table(scn, facade)
    fast_monitor = TimeHeadway(scn)
    fast_monitor.curr_frame = scn.frames[scn.timestamps[0]]
    fast_value = fast_monitor.calculate()

    assert slow_value is not None and fast_value is not None
    assert abs(slow_value - fast_value) < 1e-3, (
        f"fast/slow disagree: slow={slow_value} fast={fast_value}"
    )
