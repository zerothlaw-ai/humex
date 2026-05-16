"""Tests for the HMap unified facade."""
from collections import defaultdict

import pytest

from humex.hmap.road_map import RoadMap, MapData, LaneData, SegmentData, PointData
from humex.hmap.hmap import HMap
from humex.hmap.lane_map import LaneMap, LaneMapLane, LaneMapPoint
from humex.hmap.lane_map_builder import build_lane_map


def _seg(pts):
    s = SegmentData()
    for x, y in pts:
        s.points.append(PointData(x, y, 0.0))
    return s


def _make_simple_map():
    md = MapData()
    md.next_lanes = defaultdict(list)
    md.prev_lanes = defaultdict(list)
    md.left_lanes = defaultdict(list)
    md.right_lanes = defaultdict(list)
    md.lanes[1] = LaneData(
        id=1,
        center_line=[_seg([(x, 0) for x in range(0, 51, 5)])],
        left_boundary=[],
        right_boundary=[],
    )
    am = RoadMap("test", md)
    return am, build_lane_map(am)


def test_constructor_hard_fails_when_lane_map_missing():
    am, _ = _make_simple_map()
    with pytest.raises(ValueError, match="LaneMap v2"):
        HMap(am, None)


def test_lane_queries_route_through_lane_map_v2():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    # find_closest_lane on (10, 0) should return a v2 segment id (in lm.lanes),
    # NOT the source lane id 1 (the legacy RoadMap behaviour).
    lid = facade.find_closest_lane((10.0, 0.0, 0.0), heading=0.0)
    assert lid is not None
    assert lid in lm.lanes
    # The v2 segment should be a child of source lane 1.
    assert lm.lanes[lid].source_lane_id == 1


def test_get_reachable_lanes_uses_v2_chain():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    start = facade.find_closest_lane((2.5, 0.0, 0.0), heading=0.0)
    reachable = facade.get_reachable_lanes(start, max_distance=200.0)
    # Should walk forward through the entire chain. Exact segment count
    # depends on SEGMENT_TARGET_LENGTH; for a 50m source lane with 10m
    # segments that's 5 lanes — assert strictly positive and the start
    # lane is included.
    assert len(reachable) >= 2
    assert start in reachable


def test_neighbour_accessors_return_lists():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    any_id = next(iter(lm.lanes))
    assert isinstance(facade.next_lanes(any_id), list)
    assert isinstance(facade.prev_lanes(any_id), list)
    assert isinstance(facade.left_lanes(any_id), list)
    assert isinstance(facade.right_lanes(any_id), list)


def test_get_crossing_lanes_returns_empty_for_unknown():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    assert facade.get_crossing_lanes(99999) == []


def test_passthrough_to_legacy_for_non_lane_attrs():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    # `name` and `map_data` come from the legacy RoadMap.
    assert facade.name == "test"
    assert facade.map_data is am.map_data
    # signal helpers exist on RoadMap and should be reachable through __getattr__.
    assert callable(facade.has_signals)


def test_lane_map_property_exposes_underlying():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    assert facade.lane_map is lm
    assert facade.legacy_map is am


def test_unknown_attribute_raises():
    am, lm = _make_simple_map()
    facade = HMap(am, lm)
    with pytest.raises(AttributeError):
        _ = facade.no_such_method
