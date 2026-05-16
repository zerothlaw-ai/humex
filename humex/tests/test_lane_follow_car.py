"""Tests for LaneFollowCar agent and get_lookahead_point."""

import math
from unittest.mock import MagicMock

from humex.hmap.road_map import RoadMap
from humex.components.scenario import Scenario
from humex.components.frame import Frame
from humex.components.object import LaneFollowCar, Object
from humex.components.statepoint import StatePoint
from humex.components.perception import Perception


def _build_straight_3lane_map():
    """A -> B -> C, each 50m along x-axis."""
    m = RoadMap("test_straight")

    lane_a = m.create_lane_from_pts_with_id(
        0, centerline=[(0, 0, 0), (25, 0, 0), (50, 0, 0)]
    )
    m.add_lane(lane_a)

    lane_b = m.create_lane_from_pts_with_id(
        1, centerline=[(50, 0, 0), (75, 0, 0), (100, 0, 0)]
    )
    m.add_lane(lane_b, prev_lane_id=0)

    lane_c = m.create_lane_from_pts_with_id(
        2, centerline=[(100, 0, 0), (125, 0, 0), (150, 0, 0)]
    )
    m.add_lane(lane_c, prev_lane_id=1)

    m.build_spatial_index()
    return m


def _build_y_junction_map():
    """Trunk A(0) -> fork to B(1) and C(2).

    A: x=[0,50] y=0
    B: goes straight x=[50,100] y=0
    C: goes up-right x=[50,100] y=[0,50]
    """
    m = RoadMap("test_y")

    lane_a = m.create_lane_from_pts_with_id(
        0, centerline=[(0, 0, 0), (25, 0, 0), (50, 0, 0)]
    )
    m.add_lane(lane_a)

    lane_b = m.create_lane_from_pts_with_id(
        1, centerline=[(50, 0, 0), (75, 0, 0), (100, 0, 0)]
    )
    m.add_lane(lane_b, prev_lane_id=0)

    lane_c = m.create_lane_from_pts_with_id(
        2, centerline=[(50, 0, 0), (75, 25, 0), (100, 50, 0)]
    )
    m.add_lane(lane_c, prev_lane_id=0)

    m.build_spatial_index()
    return m


# ---------------------------------------------------------------------------
# get_lookahead_point tests
# ---------------------------------------------------------------------------

class TestGetLookaheadPoint:
    def test_within_same_lane(self):
        m = _build_straight_3lane_map()
        pt = m.get_lookahead_point((10, 0, 0), lane_id=0, distance=15.0)
        assert pt is not None
        # Should be ~25m along x-axis (10 + 15 = 25)
        assert abs(pt[0] - 25.0) < 1.0
        assert abs(pt[1]) < 0.1

    def test_crosses_lane_boundary(self):
        m = _build_straight_3lane_map()
        # At x=40, lookahead 20m should land at x=60 (in lane B)
        pt = m.get_lookahead_point((40, 0, 0), lane_id=0, distance=20.0)
        assert pt is not None
        assert abs(pt[0] - 60.0) < 1.0

    def test_dead_end_returns_none(self):
        m = _build_straight_3lane_map()
        # At x=140 in lane C, only 10m of road left, ask for 20m
        pt = m.get_lookahead_point((140, 0, 0), lane_id=2, distance=20.0)
        assert pt is None

    def test_nonexistent_lane_returns_none(self):
        m = _build_straight_3lane_map()
        pt = m.get_lookahead_point((0, 0, 0), lane_id=999, distance=10.0)
        assert pt is None

    def test_y_junction_picks_a_branch(self):
        m = _build_y_junction_map()
        # From x=40 in lane A, lookahead 20m should reach into either B or C
        pt = m.get_lookahead_point((40, 0, 0), lane_id=0, distance=20.0)
        assert pt is not None
        # Should be roughly 60m from origin along one of the branches
        dist_from_fork = math.sqrt((pt[0] - 50) ** 2 + (pt[1] - 0) ** 2)
        assert dist_from_fork > 5.0  # Past the fork point


# ---------------------------------------------------------------------------
# LaneFollowCar integration tests
# ---------------------------------------------------------------------------

class TestLaneFollowCar:
    def _make_scenario_with_car(self, ava_map, start_x=10.0, start_vx=10.0,
                                 target_speed=10.0, duration=1.0, frequency=10.0):
        """Create a real Scenario with a LaneFollowCar and run a few steps."""
        scenario = Scenario(duration=duration, frequency=frequency, map_obj=ava_map)

        car = LaneFollowCar(
            obj_id=0, scenario=scenario, is_ego=True,
            target_speed=target_speed, look_ahead_distance=15.0,
        )
        scenario.add_obj_to_roster(car)

        # Set initial state in first frame
        initial_frame = scenario.frames[scenario.timestamps[0]]
        initial_car = scenario.get_obj_copy_from_roster(obj_id=0)
        sp = StatePoint(
            position=(start_x, 0, 0),
            velocity=(start_vx, 0, 0),
            heading=(0, 0, 0),
        )
        initial_car.update_mutable(sp)
        scenario.add_obj_to_frame(initial_car, initial_frame)
        initial_frame.update_perception(Perception(initial_frame, scenario.map))

        return scenario

    def test_car_moves_forward(self):
        ava_map = _build_straight_3lane_map()
        scenario = self._make_scenario_with_car(ava_map, start_x=10.0, start_vx=10.0)

        # Simulate 3 steps
        for i in range(1, min(4, len(scenario.timestamps))):
            last_ts = scenario.timestamps[i - 1]
            curr_ts = scenario.timestamps[i]
            last_frame = scenario.frames[last_ts]
            curr_frame = scenario.frames[curr_ts]

            for obj_id, obj in last_frame.get_obj_list().items():
                new_obj = obj.step()
                if new_obj is not None:
                    scenario.add_obj_to_frame(new_obj, curr_frame)

            curr_frame.update_perception(Perception(curr_frame, scenario.map))

        # Check that the car moved forward (x increased)
        last_simulated_ts = scenario.timestamps[3]
        last_frame = scenario.frames[last_simulated_ts]
        car = last_frame.get_obj(obj_id=0)
        assert car is not None
        assert car.sp.position.x > 10.0  # Moved forward from start

    def test_car_stays_near_centerline(self):
        ava_map = _build_straight_3lane_map()
        scenario = self._make_scenario_with_car(ava_map, start_x=10.0, start_vx=10.0)

        # Simulate several steps
        for i in range(1, min(6, len(scenario.timestamps))):
            last_ts = scenario.timestamps[i - 1]
            curr_ts = scenario.timestamps[i]
            last_frame = scenario.frames[last_ts]
            curr_frame = scenario.frames[curr_ts]

            for obj_id, obj in last_frame.get_obj_list().items():
                new_obj = obj.step()
                if new_obj is not None:
                    scenario.add_obj_to_frame(new_obj, curr_frame)

            curr_frame.update_perception(Perception(curr_frame, scenario.map))

        # Car should stay close to y=0 centerline
        for i in range(1, min(6, len(scenario.timestamps))):
            ts = scenario.timestamps[i]
            frame = scenario.frames[ts]
            car = frame.get_obj(obj_id=0)
            if car is not None:
                assert abs(car.sp.position.y) < 2.0, f"Car drifted off centerline at step {i}: y={car.sp.position.y}"
