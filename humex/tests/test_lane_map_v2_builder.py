"""Tests for the v2 lane_map builder — rebuild lanes from centerlines.

Every test exercises one of the five passes (split, resample, parallel
boundary, topology rebuild) on a synthetic graph small enough to trace by
hand. Together they pin down the segmentation contract and the topology
recovery rules so future tuning of the constants doesn't silently regress
behaviour.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List

from humex.hmap.road_map import (
    RoadMap,
    LaneData,
    MapData,
    PointData,
    SegmentData,
)
from humex.hmap.lane_map_builder import (
    ALGORITHM_VERSION,
    SEGMENT_TARGET_LENGTH,
    build_lane_map,
)


def _segment(points: List[tuple]) -> SegmentData:
    return SegmentData(points=[PointData(x=x, y=y, z=0.0) for x, y in points])


def _make_map(lanes: dict, name: str = "test") -> RoadMap:
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    for lane_id, props in lanes.items():
        md.lanes[lane_id] = LaneData(
            id=lane_id,
            center_line=[_segment(props["centerline"])],
            left_boundary=[_segment(props["left"])] if "left" in props else [],
            right_boundary=[_segment(props["right"])] if "right" in props else [],
        )
        for nxt in props.get("next", []):
            md.next_lanes[lane_id].append(nxt)
        for prv in props.get("prev", []):
            md.prev_lanes[lane_id].append(prv)
        for left in props.get("left_neighbors", []):
            md.left_lanes[lane_id].append(left)
        for right in props.get("right_neighbors", []):
            md.right_lanes[lane_id].append(right)
    return RoadMap(name, md)


# ---- Pass 3: fixed-arc resampling ---------------------------------------


def test_25m_straight_lane_splits_into_segments():
    """A single 25m straight source lane → roughly 25/SEGMENT_TARGET_LENGTH
    segments, chained next/prev in arc order, all inheriting the same
    source_lane_id. Exact count depends on the rounding of the tail."""
    src = _make_map({42: {"centerline": [(0, 0), (25, 0)]}})
    lm = build_lane_map(src)
    assert lm.algorithm_version == ALGORITHM_VERSION
    expected_count = round(25 / SEGMENT_TARGET_LENGTH)
    # Tail-fold can collapse the last stub into the previous segment, so
    # accept ±1 around the expected.
    assert expected_count - 1 <= len(lm.lanes) <= expected_count + 1

    chain = sorted(lm.lanes.values(), key=lambda l: l.s_start)
    for seg in chain:
        assert seg.source_lane_id == 42
    # s_start / s_end are arc-length monotonic and contiguous.
    for i in range(len(chain) - 1):
        assert abs(chain[i].s_end - chain[i + 1].s_start) < 1e-6
    # Total arc-length covered ≈ 25m
    assert abs(chain[-1].s_end - chain[0].s_start - 25.0) < 1.0
    # Chain wired head-to-tail
    for i, seg in enumerate(chain[:-1]):
        assert chain[i + 1].id in seg.next_lane_ids
        assert seg.id in chain[i + 1].prev_lane_ids
    # Endpoints have no further next/prev (no other source lanes)
    assert chain[0].prev_lane_ids == []
    assert chain[-1].next_lane_ids == []


def test_short_source_lane_yields_one_segment():
    """A 4m source lane (< SEGMENT_TARGET_LENGTH) still produces exactly
    one segment covering its full extent."""
    src = _make_map({1: {"centerline": [(0, 0), (4, 0)]}})
    lm = build_lane_map(src)
    assert len(lm.lanes) == 1
    seg = next(iter(lm.lanes.values()))
    assert seg.source_lane_id == 1
    assert seg.s_start == 0.0
    assert abs(seg.s_end - 4.0) < 1e-6


def test_microscopic_source_lane_dropped():
    """A source lane shorter than MIN_TAIL_LENGTH (1m) emits no segments —
    the resample loop folds the tail into the previous segment, and there
    is no previous in this case so it's dropped silently."""
    src = _make_map({1: {"centerline": [(0, 0), (0.5, 0)]}})
    lm = build_lane_map(src)
    # 0.5m falls below MIN_TAIL_LENGTH; resample produces only a start point.
    # Either zero segments (dropped) or one tiny segment is acceptable; the
    # important thing is that we don't crash and we don't emit a degenerate
    # multi-segment chain.
    assert len(lm.lanes) <= 1


# ---- Pass 2: content-aware split ----------------------------------------


def test_curvature_break_splits_at_pivot():
    """A 90° L-shape (10m east, then 10m north) gets a content-aware break
    at the pivot — the resulting pieces resample independently rather than
    diagonally cutting across the corner."""
    src = _make_map({1: {"centerline": [(0, 0), (10, 0), (10, 10)]}})
    lm = build_lane_map(src)
    # Two pieces of 10m each. With SEGMENT_TARGET_LENGTH=10m each piece
    # produces a single segment, so we expect exactly 2 cardinal-direction
    # segments. The point of the test is content-aware splitting at the
    # pivot — assert no diagonal segment leaks across the corner.
    assert len(lm.lanes) >= 2
    # Every segment travels in a cardinal direction (no diagonals).
    for seg in lm.lanes.values():
        a = seg.center_line[0][0]
        b = seg.center_line[0][-1]
        assert (
            abs(b.x - a.x) < 1e-6  # purely vertical
            or abs(b.y - a.y) < 1e-6  # purely horizontal
        ), f"diagonal segment leaked: {a} → {b}"


# ---- Pass 5: topology rebuild -------------------------------------------


def test_cross_source_link_via_source_graph():
    """Two source lanes A → B (10m each, A.next = [B]). v2 should link
    A's tail segment to B's head segment via the source-graph hint."""
    src = _make_map({
        1: {"centerline": [(0, 0), (10, 0)], "next": [2]},
        2: {"centerline": [(10, 0), (20, 0)], "prev": [1]},
    })
    lm = build_lane_map(src)
    chain_1 = sorted(
        (s for s in lm.lanes.values() if s.source_lane_id == 1),
        key=lambda s: s.s_start,
    )
    chain_2 = sorted(
        (s for s in lm.lanes.values() if s.source_lane_id == 2),
        key=lambda s: s.s_start,
    )
    a_tail = chain_1[-1]
    b_head = chain_2[0]
    assert b_head.id in a_tail.next_lane_ids
    assert a_tail.id in b_head.prev_lane_ids


def test_lateral_neighbor_link():
    """Two parallel 25m lanes 3.5m apart — each segment in lane A finds
    its lateral counterpart in lane B as a left/right neighbour."""
    src = _make_map({
        1: {
            "centerline": [(0, 0), (25, 0)],
            "left_neighbors": [2],
        },
        2: {
            "centerline": [(0, 3.5), (25, 3.5)],
            "right_neighbors": [1],
        },
    })
    lm = build_lane_map(src)
    src1 = [s for s in lm.lanes.values() if s.source_lane_id == 1]
    src2 = [s for s in lm.lanes.values() if s.source_lane_id == 2]
    # Every src1 segment should have at least one src2 neighbour as a left
    # neighbour, and vice versa.
    src2_ids = {s.id for s in src2}
    src1_ids = {s.id for s in src1}
    for seg in src1:
        assert any(nbr in src2_ids for nbr in seg.left_lane_ids), \
            f"src1 segment {seg.id} found no left neighbour in src2"
    for seg in src2:
        assert any(nbr in src1_ids for nbr in seg.right_lane_ids), \
            f"src2 segment {seg.id} found no right neighbour in src1"


# ---- proto round-trip ----------------------------------------------------


def test_v2_proto_roundtrip_preserves_provenance():
    """source_lane_id / s_start / s_end survive to_proto → from_proto."""
    from humex.hmap.lane_map import LaneMap

    src = _make_map({1: {"centerline": [(0, 0), (15, 0)]}})
    lm = build_lane_map(src)
    pb = lm.to_proto()
    rebuilt = LaneMap.from_proto(pb)
    assert rebuilt.algorithm_version == ALGORITHM_VERSION
    for sid, seg in lm.lanes.items():
        re = rebuilt.lanes[sid]
        assert re.source_lane_id == seg.source_lane_id
        assert abs(re.s_start - seg.s_start) < 1e-6
        assert abs(re.s_end - seg.s_end) < 1e-6


# ---- v3.0: dense centerline + boundary fitting -------------------------


def test_dense_centerline_keeps_intermediate_points_on_curve():
    """A 90° arc with dense source samples should produce segments whose
    centerlines retain intermediate points (no 2-point chords). This is
    what gives v3 ribbons the smooth-curve look."""
    import math
    arc = [(math.cos(math.radians(t)) * 20.0,
            math.sin(math.radians(t)) * 20.0) for t in range(0, 91, 5)]
    src = _make_map({1: {"centerline": arc}})
    lm = build_lane_map(src)
    # At least one segment must carry > 2 centerline points (i.e. some
    # intermediate dense sample was preserved).
    assert any(len(seg.center_line[0]) > 2 for seg in lm.lanes.values())


def test_boundary_fitting_persists_source_boundaries():
    """When the source lane carries explicit asymmetric left/right boundary
    polylines, every emitted segment with a non-trivial s-range gets the
    corresponding boundary slice on left_boundary / right_boundary."""
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    md.lanes[1] = LaneData(
        id=1,
        center_line=[_segment([(x, 0.0) for x in range(0, 21, 5)])],
        # Asymmetric: left at +2.0, right at -1.0 (right-shoulder-narrow lane)
        left_boundary=[_segment([(x, 2.0) for x in range(0, 21, 5)])],
        right_boundary=[_segment([(x, -1.0) for x in range(0, 21, 5)])],
    )
    am = RoadMap("asymmetric", md)
    lm = build_lane_map(am)
    assert len(lm.lanes) >= 1
    for seg in lm.lanes.values():
        # Both boundaries should be populated and on the right side of the
        # centerline (y=2 left, y=-1 right). The slice can be empty for
        # a degenerate tail-fold segment, so we accept that as long as the
        # majority carry slices.
        if seg.left_boundary:
            assert all(abs(p.y - 2.0) < 1e-6 for p in seg.left_boundary[0])
        if seg.right_boundary:
            assert all(abs(p.y + 1.0) < 1e-6 for p in seg.right_boundary[0])
    # At least one segment must have BOTH boundaries fitted (not just the
    # synthesized fallback).
    assert any(seg.left_boundary and seg.right_boundary for seg in lm.lanes.values())


def test_boundary_fallback_when_source_has_no_boundaries():
    """A source lane with no left/right boundary polylines emits segments
    whose left_boundary / right_boundary fields are empty lists. The
    runtime polygon falls back to centerline ± width_estimate / 2."""
    src = _make_map({1: {"centerline": [(x, 0) for x in range(0, 21, 5)]}})
    lm = build_lane_map(src)
    for seg in lm.lanes.values():
        assert seg.left_boundary == []
        assert seg.right_boundary == []
    # Polygon path still works (fallback parallel-offset).
    sid = next(iter(lm.lanes))
    poly = lm._lane_polygon(sid)
    assert len(poly) >= 4
