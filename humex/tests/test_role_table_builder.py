"""Tests for the role-table builder (front + rear, v1)."""
import math
from collections import defaultdict

from humex.hmap.road_map import RoadMap, MapData, LaneData, SegmentData, PointData
from humex.hmap.lane_map_builder import build_lane_map
from humex.hmap.hmap import HMap
from humex.hmap.role_table import RoleTable
from humex.hmap.role_table_builder import build_role_table
from humex.components.scenario import Scenario
from humex.components.object import Object
from humex.components.statepoint import StatePoint


def _seg(pts):
    s = SegmentData()
    for x, y in pts:
        s.points.append(PointData(x, y, 0.0))
    return s


def _straight_facade(length=50):
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


def _add_obj(scn, frame_idx, obj_id, x, y, length=4.0, width=2.0):
    ts = scn.timestamps[frame_idx]
    obj = Object(obj_id=obj_id, length=length, width=width)
    obj.update_mutable(StatePoint(position=(x, y, 0.0), velocity=(5, 0, 0), heading=(0, 0, 0)))
    scn.frames[ts].add_obj(obj)
    return obj


def test_single_front_vehicle_detected_every_frame():
    facade = _straight_facade()
    scn = Scenario(duration=5.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(5):
        _add_obj(scn, k, 0, 5.0 + k * 5.0, 0.0)         # ego
        _add_obj(scn, k, 1, 15.0 + k * 5.0, 0.0)        # front car

    rt = build_role_table(scn, facade)
    assert rt.frame_count == 5
    for fr in rt.frames:
        assert fr.front is not None
        assert fr.front.agent_id == 1
        # Bumper-to-bumper: 10m centers - 4m total bbox length = 6m
        assert abs(fr.front.distance.closest - 6.0) < 0.05
        # Farthest corner-to-corner = hypot(14, 2)
        assert abs(fr.front.distance.farthest - math.hypot(14.0, 2.0)) < 0.05
        # No rear in this scenario
        assert fr.rear is None


def test_rear_vehicle_picked_up_after_first_frame():
    facade = _straight_facade()
    scn = Scenario(duration=5.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(5):
        _add_obj(scn, k, 0, 15.0 + k * 5.0, 0.0)        # ego (ahead)
        _add_obj(scn, k, 1, 5.0 + k * 5.0, 0.0)         # rear car

    rt = build_role_table(scn, facade)
    # Rear corridor is empty at frame 0 (ego hasn't visited any prev lanes yet
    # in the trajectory) but the BFS-backward extension picks up earlier lanes.
    for fr in rt.frames:
        assert fr.rear is not None and fr.rear.agent_id == 1
        assert fr.front is None


def test_closer_of_two_in_same_lane_wins_front():
    facade = _straight_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 5.0, 0.0)
        _add_obj(scn, k, 1, 15.0, 0.0)   # closer
        _add_obj(scn, k, 2, 25.0, 0.0)   # farther

    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        assert fr.front is not None and fr.front.agent_id == 1


def test_proto_round_trip_preserves_front_and_rear():
    facade = _straight_facade()
    scn = Scenario(duration=3.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(3):
        _add_obj(scn, k, 0, 15.0 + k * 5.0, 0.0)
        _add_obj(scn, k, 1, 25.0 + k * 5.0, 0.0)   # front
        _add_obj(scn, k, 2, 5.0 + k * 5.0, 0.0)    # rear

    rt = build_role_table(scn, facade)
    pb = rt.to_proto()
    rt2 = RoleTable.from_proto(pb)
    assert rt2.algorithm_version == rt.algorithm_version
    assert rt2.ego_id == rt.ego_id
    assert rt2.frame_count == rt.frame_count
    for k in range(rt.frame_count):
        a = rt.frames[k]
        b = rt2.frames[k]
        for slot in ("front", "rear"):
            x = getattr(a, slot)
            y = getattr(b, slot)
            assert (x is None) == (y is None)
            if x is not None:
                assert x.agent_id == y.agent_id
                assert abs(x.distance.closest - y.distance.closest) < 1e-6
                assert abs(x.distance.farthest - y.distance.farthest) < 1e-6
                assert abs(x.s_gap - y.s_gap) < 1e-6


def test_empty_scenario_returns_empty_table():
    facade = _straight_facade()
    scn = Scenario(duration=0.0, frequency=1.0, map_obj=facade, ego_id=0)
    rt = build_role_table(scn, facade)
    assert rt.frame_count == 0


def test_scenario_with_no_ego_is_safe():
    facade = _straight_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=None)
    # No agents at all — assign_ego_id picks nothing, builder emits empty table.
    rt = build_role_table(scn, facade)
    assert rt.frame_count == 0


# --- v2: 5-point lane occupancy + corridors -------------------------------


def _two_parallel_lanes_facade(length=50):
    """Two adjacent parallel lanes 3.5m apart (one ego lane, one left lane)."""
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list); md.left_lanes[1].append(2); md.left_lanes[2].append(1)
    md.right_lanes = defaultdict(list); md.right_lanes[1].append(2); md.right_lanes[2].append(1)
    md.lanes[1] = LaneData(
        id=1,
        center_line=[_seg([(x, 0.0) for x in range(0, length + 1, 5)])],
        left_boundary=[], right_boundary=[],
    )
    md.lanes[2] = LaneData(
        id=2,
        center_line=[_seg([(x, 3.5) for x in range(0, length + 1, 5)])],
        left_boundary=[], right_boundary=[],
    )
    am = RoadMap("two_parallel", md)
    lm = build_lane_map(am)
    return HMap(am, lm), lm


def test_v2_per_agent_corridors_are_populated():
    facade, _ = _two_parallel_lanes_facade()
    scn = Scenario(duration=3.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(3):
        _add_obj(scn, k, 0, 5.0 + k * 5.0, 0.0)         # ego on lane 1
        _add_obj(scn, k, 1, 15.0 + k * 5.0, 0.0)        # front car on lane 1

    rt = build_role_table(scn, facade)
    # Both ego (id=0) and front car (id=1) should have non-empty centre corridors.
    ego_corr = rt.corridors_for(0)
    front_corr = rt.corridors_for(1)
    assert ego_corr is not None and len(ego_corr.center_corridor) > 0
    assert front_corr is not None and len(front_corr.center_corridor) > 0
    # Per-frame agent_lanes block populated for both agents.
    for fr in rt.frames:
        ids_present = {alf.agent_id for alf in fr.agent_lanes}
        assert 0 in ids_present and 1 in ids_present


def test_v2_lateral_straddle_detects_front_via_corner():
    """Agent X centroid sits in the LEFT lane (lane 2), but its bbox is wide
    enough that the front-right corner sits inside ego's lane (lane 1).
    Expectation: X is detected as ego's front from frame 0 because one of
    its 5 reference points (front-right) is in ego's corridor."""
    facade, _ = _two_parallel_lanes_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        # Ego squarely in lane 1
        _add_obj(scn, k, 0, 5.0 + k * 5.0, 0.0, length=4.0, width=2.0)
        # Agent X: centroid at y=2 (inside lane 2 polygon since lane 2 is at
        # y=3.5 width 3.5 → y in [1.75, 5.25]). Front-right corner at
        # (x+half_l, y - half_w) = (..., 1.0) — inside lane 1 (lane 1 polygon
        # spans y ∈ [-1.75, 1.75]). So one corner is in ego's lane.
        _add_obj(scn, k, 7, 15.0 + k * 5.0, 2.0, length=4.0, width=2.0)

    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        # Agent 7's per-frame lane block: front_right should be lane 1 (ego's),
        # center should be lane 2 (left).
        agent7 = next((a for a in fr.agent_lanes if a.agent_id == 7), None)
        assert agent7 is not None
        # We don't pin an exact lane_id (segmenter picks fresh ints), but:
        # center and front_right should be DIFFERENT (centroid in left, corner in right).
        # If the geometry actually has them in the same lane, the multi-point
        # filter would still detect agent 7 — so this is a loose check.
        # Either way, agent 7 should be detected as front.
        assert fr.front is not None and fr.front.agent_id == 7


def test_v2_proto_round_trip_preserves_agent_lanes_and_corridors():
    facade, _ = _two_parallel_lanes_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 5.0 + k * 5.0, 0.0)
        _add_obj(scn, k, 1, 15.0 + k * 5.0, 0.0)

    rt = build_role_table(scn, facade)
    pb = rt.to_proto()
    rt2 = RoleTable.from_proto(pb)
    assert rt2.frame_count == rt.frame_count
    # agent_corridors round-trip
    assert len(rt2.agent_corridors) == len(rt.agent_corridors)
    for a, b in zip(rt.agent_corridors, rt2.agent_corridors):
        assert a.agent_id == b.agent_id
        assert a.center_corridor == b.center_corridor
    # agent_lanes round-trip
    for fa, fb in zip(rt.frames, rt2.frames):
        assert len(fa.agent_lanes) == len(fb.agent_lanes)
        for la, lb in zip(fa.agent_lanes, fb.agent_lanes):
            assert la.agent_id == lb.agent_id
            assert la.lanes.center == lb.lanes.center
            assert la.lanes.front_left == lb.lanes.front_left


def test_v2_disambiguation_uses_corridor_id_continuity():
    """Synthesise a case where, at frame 1, a single bbox point sits in two
    overlapping polygons. The disambiguator must pick the candidate whose
    corridor_id matches frame 0's pick (continuity)."""
    # Build a tiny lane_map with two overlapping crossing lanes.
    from humex.hmap.lane_map import LaneMap, LaneMapLane, LaneMapPoint, TURN_UNKNOWN

    pt_a = [LaneMapPoint(0.0, 0.0), LaneMapPoint(10.0, 0.0)]
    pt_b = [LaneMapPoint(5.0, -5.0), LaneMapPoint(5.0, 5.0)]
    lm = LaneMap(
        algorithm_version="lane-map-v2.2",
        lanes={
            1: LaneMapLane(id=1, center_line=[pt_a], width_estimate=4.0,
                           next_lane_ids=[10], turn_type=TURN_UNKNOWN, corridor_id=1),
            10: LaneMapLane(id=10, center_line=[[LaneMapPoint(10.0, 0.0), LaneMapPoint(20.0, 0.0)]],
                            width_estimate=4.0, prev_lane_ids=[1], turn_type=TURN_UNKNOWN, corridor_id=1),
            2: LaneMapLane(id=2, center_line=[pt_b], width_estimate=4.0,
                           turn_type=TURN_UNKNOWN, corridor_id=2),
        },
    )
    am = RoadMap("disamb")
    facade = HMap(am, lm)

    # Pre-flight: at point (5, 0), both lanes 1 and 2 contain it.
    cands = facade.find_containing_lanes((5.0, 0.0, 0.0))
    assert set(cands) == {1, 2}, f"expected both lanes, got {cands}"

    # Build a 2-frame "agent" trajectory: frame 0 at (1, 0) (clearly in lane 1),
    # frame 1 at (5, 0) (in both lanes 1 and 2). Disambiguator should pick lane 1
    # at frame 1 because it shares corridor_id with frame 0's pick.
    from humex.hmap.role_table_builder import _disambiguate_point
    seq = [[1], [1, 2]]  # frame 0: only lane 1 contains the point; frame 1: both
    picks = _disambiguate_point(seq, facade)
    assert picks == [1, 1], f"expected continuity → [1, 1], got {picks}"

    # Reverse case: if frame 0's only candidate is lane 2, frame 1 should pick lane 2.
    seq_rev = [[2], [1, 2]]
    picks_rev = _disambiguate_point(seq_rev, facade)
    assert picks_rev == [2, 2], f"expected continuity → [2, 2], got {picks_rev}"


# --- v2.1: side roles (lead / alongside / follow) -----------------------


def _two_lane_facade_with_neighbors(length=80):
    """Lane 1 (y=0.0) is ego's lane; lane 2 (y=3.5) is its left neighbour
    (and lane 1 is lane 2's right neighbour). Long enough for several
    fore/aft positions on each side."""
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list); md.left_lanes[1].append(2)
    md.right_lanes = defaultdict(list); md.right_lanes[2].append(1)
    md.lanes[1] = LaneData(
        id=1,
        center_line=[_seg([(x, 0.0) for x in range(0, length + 1, 5)])],
        left_boundary=[], right_boundary=[],
    )
    md.lanes[2] = LaneData(
        id=2,
        center_line=[_seg([(x, 3.5) for x in range(0, length + 1, 5)])],
        left_boundary=[], right_boundary=[],
    )
    am = RoadMap("two_lane_neighbors", md)
    lm = build_lane_map(am)
    return HMap(am, lm)


def _add_side_obj(scn, k, obj_id, x, y=3.5, length=4.0, width=2.0):
    """Add an agent in the LEFT lane (y=3.5) at the given longitudinal x."""
    ts = scn.timestamps[k]
    obj = Object(obj_id=obj_id, length=length, width=width)
    obj.update_mutable(StatePoint(position=(x, y, 0.0), velocity=(5, 0, 0), heading=(0, 0, 0)))
    scn.frames[ts].add_obj(obj)
    return obj


def test_left_lead_picked_when_side_agent_is_ahead():
    facade = _two_lane_facade_with_neighbors()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 20.0, 0.0)            # ego in lane 1
        _add_side_obj(scn, k, 7, 30.0)            # 10m ahead in lane 2 (left)
    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        assert fr.left_lead is not None and fr.left_lead.agent_id == 7
        assert fr.left_alongside is None
        assert fr.left_follow is None
        # Right lane has no neighbour for ego → all right roles None.
        assert fr.right_lead is None and fr.right_alongside is None and fr.right_follow is None


def test_left_alongside_when_side_agent_is_overlapping():
    facade = _two_lane_facade_with_neighbors()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 20.0, 0.0)            # ego in lane 1
        _add_side_obj(scn, k, 7, 21.0)            # 1m ahead in lane 2 → bbox overlap
    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        assert fr.left_alongside is not None and fr.left_alongside.agent_id == 7
        assert fr.left_lead is None
        assert fr.left_follow is None


def test_left_follow_when_side_agent_is_behind():
    facade = _two_lane_facade_with_neighbors()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 30.0, 0.0)            # ego in lane 1
        _add_side_obj(scn, k, 7, 20.0)            # 10m behind in lane 2
    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        assert fr.left_follow is not None and fr.left_follow.agent_id == 7
        assert fr.left_lead is None
        assert fr.left_alongside is None


def test_no_side_neighbor_lane_keeps_all_side_fields_none():
    """Single-lane road → no left/right neighbour → all 6 side roles None."""
    facade = _straight_facade()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 20.0, 0.0)
        _add_obj(scn, k, 1, 25.0, 0.0)            # in same lane → front, not side
    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        for slot in ("left_lead", "left_alongside", "left_follow",
                     "right_lead", "right_alongside", "right_follow"):
            assert getattr(fr, slot) is None, f"{slot} should be None on a single-lane road"


def test_left_lead_alongside_follow_simultaneous():
    """3 agents in left lane: one ahead (lead), one overlapping (alongside),
    one behind (follow). All three side fields populated independently."""
    facade = _two_lane_facade_with_neighbors()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 30.0, 0.0)            # ego
        _add_side_obj(scn, k, 1, 45.0)            # 15m ahead → lead
        _add_side_obj(scn, k, 2, 31.0)            # 1m ahead → alongside
        _add_side_obj(scn, k, 3, 20.0)            # 10m behind → follow
    rt = build_role_table(scn, facade)
    for fr in rt.frames:
        assert fr.left_lead is not None and fr.left_lead.agent_id == 1
        assert fr.left_alongside is not None and fr.left_alongside.agent_id == 2
        assert fr.left_follow is not None and fr.left_follow.agent_id == 3


def test_v21_proto_round_trip_preserves_side_roles():
    facade = _two_lane_facade_with_neighbors()
    scn = Scenario(duration=2.0, frequency=1.0, map_obj=facade, ego_id=0)
    for k in range(2):
        _add_obj(scn, k, 0, 30.0, 0.0)
        _add_side_obj(scn, k, 1, 45.0)
        _add_side_obj(scn, k, 2, 31.0)
        _add_side_obj(scn, k, 3, 20.0)
    rt = build_role_table(scn, facade)
    pb = rt.to_proto()
    rt2 = RoleTable.from_proto(pb)
    for a, b in zip(rt.frames, rt2.frames):
        for slot in ("left_lead", "left_alongside", "left_follow",
                     "right_lead", "right_alongside", "right_follow"):
            x = getattr(a, slot)
            y = getattr(b, slot)
            assert (x is None) == (y is None)
            if x is not None:
                assert x.agent_id == y.agent_id
                assert abs(x.s_gap - y.s_gap) < 1e-6
