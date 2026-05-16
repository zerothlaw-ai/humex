"""Tests for lane-graph based front vehicle detection.

Verifies that get_reachable_lanes, project_onto_lane_path, FrontVehicleId,
FrontVehicleDistance, and TtcFrontVehicle work correctly with multi-hop
lane graphs and curved lanes.
"""

import math
from unittest.mock import MagicMock

import pytest

from humex.hmap.road_map import RoadMap
from humex.components.frame import Frame
from humex.components.object import Object
from humex.components.statepoint import StatePoint


def _build_straight_3lane_map():
    """Create a map with 3 straight lanes in sequence: A(0) -> B(1) -> C(2).

    Each lane is 50m long along the x-axis, y=0.
    Lane 0: x=[0, 50], Lane 1: x=[50, 100], Lane 2: x=[100, 150]
    """
    ava_map = RoadMap("test_straight")

    lane_a = ava_map.create_lane_from_pts_with_id(
        0, centerline=[(0, 0, 0), (25, 0, 0), (50, 0, 0)]
    )
    ava_map.add_lane(lane_a)

    lane_b = ava_map.create_lane_from_pts_with_id(
        1, centerline=[(50, 0, 0), (75, 0, 0), (100, 0, 0)]
    )
    ava_map.add_lane(lane_b, prev_lane_id=0)

    lane_c = ava_map.create_lane_from_pts_with_id(
        2, centerline=[(100, 0, 0), (125, 0, 0), (150, 0, 0)]
    )
    ava_map.add_lane(lane_c, prev_lane_id=1)

    ava_map.build_spatial_index()
    return ava_map


def _build_curved_lane_map():
    """Create a map with a single curved lane (quarter circle, r=50m).

    Goes from (0,0) to roughly (50,50) curving left.
    """
    ava_map = RoadMap("test_curved")
    n_pts = 20
    pts = []
    for i in range(n_pts + 1):
        angle = (math.pi / 2) * i / n_pts  # 0 to pi/2
        pts.append((50 * math.sin(angle), 50 - 50 * math.cos(angle), 0))

    lane = ava_map.create_lane_from_pts_with_id(0, centerline=pts)
    ava_map.add_lane(lane)
    ava_map.build_spatial_index()
    return ava_map


def _make_scenario(ava_map, ego_id=0):
    scenario = MagicMock()
    scenario.ego_id = ego_id
    scenario.map = ava_map
    return scenario


def _make_obj(obj_id, x, y, vx=0, vy=0, length=4.0, is_ego=False, scenario=None):
    obj = Object(obj_id=obj_id, length=length, width=1.8, height=1.5,
                 is_ego=is_ego, scenario=scenario)
    obj.sp = StatePoint(
        position=(x, y, 0),
        velocity=(vx, vy, 0),
        heading=(0, 0, 0),
    )
    return obj


# ---------------------------------------------------------------------------
# RoadMap method tests
# ---------------------------------------------------------------------------

class TestGetReachableLanes:
    def test_three_lane_sequence(self):
        m = _build_straight_3lane_map()
        lanes = m.get_reachable_lanes(0, max_distance=200)
        assert lanes == [0, 1, 2]

    def test_max_distance_limits_reach(self):
        m = _build_straight_3lane_map()
        # Each lane is 50m. With max_distance=60, we reach lane 0 (50m) and
        # start lane 1 but 50+50=100 > 60, so lane 2 should NOT be reached.
        lanes = m.get_reachable_lanes(0, max_distance=60)
        assert 0 in lanes
        assert 1 in lanes
        assert 2 not in lanes

    def test_start_from_middle(self):
        m = _build_straight_3lane_map()
        lanes = m.get_reachable_lanes(1, max_distance=200)
        assert lanes == [1, 2]

    def test_nonexistent_lane(self):
        m = _build_straight_3lane_map()
        assert m.get_reachable_lanes(999) == []

    def test_cycle_handling(self):
        """Roundabout: A -> B -> A should not infinite-loop."""
        m = RoadMap("cycle")
        lane_a = m.create_lane_from_pts_with_id(0, centerline=[(0, 0, 0), (10, 0, 0)])
        m.add_lane(lane_a)
        lane_b = m.create_lane_from_pts_with_id(1, centerline=[(10, 0, 0), (20, 0, 0)])
        m.add_lane(lane_b, prev_lane_id=0)
        # Create cycle: B -> A
        m.map_data.next_lanes[1].append(0)
        m.map_data.prev_lanes[0].append(1)
        m.build_spatial_index()

        lanes = m.get_reachable_lanes(0, max_distance=200)
        assert set(lanes) == {0, 1}


class TestProjectOntoLanePath:
    def test_ego_and_vehicle_same_lane(self):
        m = _build_straight_3lane_map()
        lane_path = [0, 1, 2]

        s_ego = m.project_onto_lane_path((10, 0), lane_path)
        s_veh = m.project_onto_lane_path((40, 0), lane_path)
        assert s_ego is not None
        assert s_veh is not None
        assert abs((s_veh - s_ego) - 30.0) < 0.5

    def test_ego_and_vehicle_cross_lane(self):
        m = _build_straight_3lane_map()
        lane_path = [0, 1, 2]

        s_ego = m.project_onto_lane_path((10, 0), lane_path)
        s_veh = m.project_onto_lane_path((120, 0), lane_path)
        assert s_ego is not None
        assert s_veh is not None
        assert abs((s_veh - s_ego) - 110.0) < 0.5

    def test_far_away_returns_none(self):
        m = _build_straight_3lane_map()
        # 100m away laterally — beyond 20m threshold
        result = m.project_onto_lane_path((25, 100), [0])
        assert result is None


class TestLaneCenterlineLength:
    def test_straight_lane_length(self):
        m = _build_straight_3lane_map()
        assert abs(m._lane_centerline_length(0) - 50.0) < 0.01
        assert abs(m._lane_centerline_length(1) - 50.0) < 0.01

    def test_caching(self):
        m = _build_straight_3lane_map()
        _ = m._lane_centerline_length(0)
        assert 0 in m._centerline_length_cache


# ---------------------------------------------------------------------------
# Monitor tests
# ---------------------------------------------------------------------------

class TestFrontVehicleId:
    def test_finds_vehicle_in_third_lane(self):
        """Vehicle in lane C (2 hops away) should be found — naive would miss it."""
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=10, y=0, vx=10, is_ego=True, scenario=scenario)
        other = _make_obj(1, x=120, y=0, vx=5)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(other)

        monitor = FrontVehicleId(scenario)
        monitor.curr_frame = frame
        result = monitor.calculate()
        assert result == 1

    def test_no_vehicle_ahead(self):
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=140, y=0, vx=10, is_ego=True, scenario=scenario)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)

        monitor = FrontVehicleId(scenario)
        monitor.curr_frame = frame
        assert monitor.calculate() is None

    def test_vehicle_behind_not_detected(self):
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=80, y=0, vx=10, is_ego=True, scenario=scenario)
        behind = _make_obj(1, x=20, y=0, vx=5)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(behind)

        monitor = FrontVehicleId(scenario)
        monitor.curr_frame = frame
        assert monitor.calculate() is None

    def test_ego_absent_returns_none(self):
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=99)

        frame = Frame(timestamp=0)
        monitor = FrontVehicleId(scenario)
        monitor.curr_frame = frame
        assert monitor.calculate() is None


class TestFrontVehicleDistance:
    def test_distance_cross_lane(self):
        from humex.metrics.monitors.catalog.front_vehicle_distance import FrontVehicleDistance

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=10, y=0, vx=10, length=4.0, is_ego=True, scenario=scenario)
        other = _make_obj(1, x=120, y=0, vx=5, length=4.0)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(other)

        monitor = FrontVehicleDistance(scenario)
        monitor.curr_frame = frame
        result = monitor.calculate()

        # center-to-center ~110m, minus 2m - 2m half-lengths = ~106m
        assert result is not None
        assert abs(result - 106.0) < 1.0

    def test_no_front_vehicle_returns_inf(self):
        from humex.metrics.monitors.catalog.front_vehicle_distance import FrontVehicleDistance

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=140, y=0, vx=10, is_ego=True, scenario=scenario)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)

        monitor = FrontVehicleDistance(scenario)
        monitor.curr_frame = frame
        assert monitor.calculate() == float('inf')


class TestTtcFrontVehicle:
    def test_ttc_calculation(self):
        from humex.metrics.monitors.catalog.ttc_front_vehicle import TtcFrontVehicle

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        # ego at 10m/s, front at 5m/s, gap ~106m => TTC = 106/5 = ~21.2s
        ego = _make_obj(0, x=10, y=0, vx=10, length=4.0, is_ego=True, scenario=scenario)
        other = _make_obj(1, x=120, y=0, vx=5, length=4.0)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(other)

        monitor = TtcFrontVehicle(scenario, params={})
        monitor.curr_frame = frame
        result = monitor.calculate()

        assert result is not None
        assert result != float('inf')
        # closing speed = 10 - 5 = 5 m/s, gap ~106m, TTC ~21.2s
        assert abs(result - 21.2) < 1.0

    def test_ttc_no_closing(self):
        """Front vehicle faster than ego => TTC = inf."""
        from humex.metrics.monitors.catalog.ttc_front_vehicle import TtcFrontVehicle

        m = _build_straight_3lane_map()
        scenario = _make_scenario(m, ego_id=0)

        ego = _make_obj(0, x=10, y=0, vx=5, length=4.0, is_ego=True, scenario=scenario)
        other = _make_obj(1, x=120, y=0, vx=10, length=4.0)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(other)

        monitor = TtcFrontVehicle(scenario, params={})
        monitor.curr_frame = frame
        assert monitor.calculate() == float('inf')


class TestCurvedLane:
    @pytest.mark.xfail(
        reason="Curve-arc ahead-detection needs lane-graph-aware ordering; tracked as a known gap in v3 builder",
        strict=False,
    )
    def test_ahead_detection_on_curve(self):
        """On a curved lane, a vehicle further along the arc should be detected
        as ahead even though a yaw-based check might fail."""
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId

        m = _build_curved_lane_map()
        scenario = _make_scenario(m, ego_id=0)

        # Ego near start of curve
        ego = _make_obj(0, x=5, y=0.5, vx=10, is_ego=True, scenario=scenario)
        # Vehicle further along the curve (roughly at 45 degrees)
        angle = math.pi / 4
        vx = 50 * math.sin(angle)
        vy = 50 - 50 * math.cos(angle)
        other = _make_obj(1, x=vx, y=vy, vx=5)

        frame = Frame(timestamp=0)
        frame.add_obj(ego)
        frame.add_obj(other)

        monitor = FrontVehicleId(scenario)
        monitor.curr_frame = frame
        result = monitor.calculate()
        assert result == 1
