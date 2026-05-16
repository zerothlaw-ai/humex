"""Tests for Pass 6 (overlapping_lane_ids) of the lane_map builder."""
from collections import defaultdict

from humex.hmap.road_map import RoadMap, MapData, LaneData, SegmentData, PointData
from humex.hmap.lane_map_builder import build_lane_map


def _seg(pts):
    s = SegmentData()
    for x, y in pts:
        s.points.append(PointData(x, y, 0.0))
    return s


def _make_map(lanes):
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    for lid, pts in lanes.items():
        md.lanes[lid] = LaneData(
            id=lid, center_line=[_seg(pts)], left_boundary=[], right_boundary=[]
        )
    return RoadMap("overlap_test", md)


def test_two_crossing_lanes_each_overlap_the_other():
    """E-W and N-S lanes crossing at the origin must list each other's
    segments in overlapping_lane_ids."""
    src = _make_map({
        1: [(x, 0) for x in range(-15, 16, 5)],   # E-W
        2: [(0, y) for y in range(-15, 16, 5)],   # N-S
    })
    lm = build_lane_map(src)

    ew = [lid for lid, l in lm.lanes.items() if l.source_lane_id == 1]
    ns = [lid for lid, l in lm.lanes.items() if l.source_lane_id == 2]
    assert ew and ns

    ew_overlaps = sum(len(lm.lanes[s].overlapping_lane_ids) for s in ew)
    ns_overlaps = sum(len(lm.lanes[s].overlapping_lane_ids) for s in ns)
    assert ew_overlaps > 0
    assert ns_overlaps > 0

    for s in ew:
        for o in lm.lanes[s].overlapping_lane_ids:
            assert lm.lanes[o].source_lane_id == 2
    for s in ns:
        for o in lm.lanes[s].overlapping_lane_ids:
            assert lm.lanes[o].source_lane_id == 1


def test_parallel_lanes_do_not_overlap():
    """Two lanes far apart laterally should NOT show up in each other's
    overlapping_lane_ids — the polygons don't intersect."""
    src = _make_map({
        1: [(x, 0) for x in range(0, 21, 5)],
        2: [(x, 20) for x in range(0, 21, 5)],   # 20m to the side
    })
    lm = build_lane_map(src)
    for lid, lane in lm.lanes.items():
        assert lane.overlapping_lane_ids == [], (
            f"Lane {lid} has overlaps {lane.overlapping_lane_ids} but should be empty"
        )


def test_chain_neighbours_excluded_from_overlap():
    """Lane segments wired via the prev/next chain should NOT appear in each
    other's overlapping_lane_ids — only NON-chain crossings count."""
    src = _make_map({
        1: [(x, 0) for x in range(0, 31, 5)],   # one long lane gets resampled
    })
    lm = build_lane_map(src)
    for lid, lane in lm.lanes.items():
        excluded = set(lane.next_lane_ids) | set(lane.prev_lane_ids)
        for o in lane.overlapping_lane_ids:
            assert o not in excluded, (
                f"Lane {lid} lists chain-linked lane {o} in overlapping_lane_ids"
            )


def test_round_trip_preserves_overlapping_lane_ids():
    """Serialise to proto and deserialise back; overlapping_lane_ids must
    survive the round-trip."""
    from humex.hmap.lane_map import LaneMap

    src = _make_map({
        1: [(x, 0) for x in range(-15, 16, 5)],
        2: [(0, y) for y in range(-15, 16, 5)],
    })
    lm = build_lane_map(src)
    pb = lm.to_proto()
    lm2 = LaneMap.from_proto(pb)
    for lid in lm.lanes:
        assert lm2.lanes[lid].overlapping_lane_ids == lm.lanes[lid].overlapping_lane_ids


# --- corridor_id (Pass 7) -------------------------------------------------


def test_corridor_id_single_chain_is_one_corridor():
    """A single source lane resampled into N segments → all share one corridor_id."""
    src = _make_map({1: [(x, 0) for x in range(0, 31, 5)]})
    lm = build_lane_map(src)
    assert len(lm.lanes) > 1
    cids = {l.corridor_id for l in lm.lanes.values()}
    assert len(cids) == 1


def test_corridor_id_two_parallel_lanes_are_distinct_corridors():
    """Two disjoint parallel lanes never have any chain edge → two corridors."""
    src = _make_map({
        1: [(x, 0) for x in range(0, 21, 5)],
        2: [(x, 10) for x in range(0, 21, 5)],
    })
    lm = build_lane_map(src)
    cids = {l.corridor_id for l in lm.lanes.values()}
    assert len(cids) == 2


def test_corridor_id_y_merge_breaks_corridor():
    """Two source lanes feeding one — the merged-into lane has 2 prevs, so
    the chain edge into it is ambiguous and corridor breaks at the merge."""
    from collections import defaultdict
    md = MapData()
    md.next_lanes = defaultdict(list); md.next_lanes[1].append(3); md.next_lanes[2].append(3)
    md.prev_lanes = defaultdict(list); md.prev_lanes[3].extend([1, 2])
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    md.lanes[1] = LaneData(id=1, center_line=[_seg([(0, 0), (5, 0), (10, 0), (15, 5)])], left_boundary=[], right_boundary=[])
    md.lanes[2] = LaneData(id=2, center_line=[_seg([(0, 10), (5, 10), (10, 10), (15, 5)])], left_boundary=[], right_boundary=[])
    md.lanes[3] = LaneData(id=3, center_line=[_seg([(15, 5), (20, 5), (25, 5)])], left_boundary=[], right_boundary=[])
    am = RoadMap("y_merge", md)
    lm = build_lane_map(am)
    # Source lane 3's segments must NOT share corridor with source 1 or 2.
    src_to_cids = {1: set(), 2: set(), 3: set()}
    for lid, lane in lm.lanes.items():
        src_to_cids[lane.source_lane_id].add(lane.corridor_id)
    assert src_to_cids[3].isdisjoint(src_to_cids[1])
    assert src_to_cids[3].isdisjoint(src_to_cids[2])


def test_corridor_id_round_trip_preserved():
    src = _make_map({1: [(x, 0) for x in range(0, 16, 5)]})
    lm = build_lane_map(src)
    from humex.hmap.lane_map import LaneMap
    pb = lm.to_proto()
    lm2 = LaneMap.from_proto(pb)
    for lid in lm.lanes:
        assert lm2.lanes[lid].corridor_id == lm.lanes[lid].corridor_id
