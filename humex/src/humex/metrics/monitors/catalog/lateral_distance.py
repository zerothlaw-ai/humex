"""Lateral distance monitor — shortest bbox-to-bbox distance to an alongside
vehicle in either adjacent lane.

Fast path (role.pb v2.1 present): read the precomputed
``left_alongside`` / ``right_alongside`` slots from the role table for the
current frame and return the smaller of the two ``distance.closest`` values
(already a real bbox-to-bbox metric). When neither side has an alongside
agent at this frame, return None.

Slow path (no role table): fall back to centroid-projected lateral distance
against vehicles in the adjacent lanes — the original v0 behaviour.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
import numpy as np
import math


class LateralDistance(MonitorBase):
    """Shortest bbox-to-bbox distance from ego to any alongside vehicle.

    OUTPUT_TYPE: FLOAT

    Returns ``None`` (not infinity) when no alongside vehicle exists for
    the current frame — monitors downstream interpret None as "no
    constraint at this frame" instead of an infinite-safe headway.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        # ---- Fast path: precomputed role table ----
        # role_table + current_frame_index() come from MonitorBase. The
        # isinstance gate inside `role_table` ensures MagicMock'd test
        # scenarios don't snap to the fast path with bogus attributes.
        rt = self.role_table
        if rt is not None:
            idx = self.current_frame_index()
            if idx is not None:
                fr = rt.get_frame(idx)
                if fr is not None:
                    candidates = []
                    if fr.left_alongside is not None:
                        candidates.append(fr.left_alongside.distance.closest)
                    if fr.right_alongside is not None:
                        candidates.append(fr.right_alongside.distance.closest)
                    return min(candidates) if candidates else None

        # ---- Slow path: centroid lateral projection over adjacent lanes ----
        ego_position = ego.sp.position.to_tuple()[:2]
        ego_yaw = ego.sp.heading.yaw
        ego_yaw_rad = math.radians(ego_yaw) if abs(ego_yaw) > 10.0 else ego_yaw
        lateral_direction = np.array([-math.sin(ego_yaw_rad), math.cos(ego_yaw_rad)])

        adjacent_lane_ids = self._get_adjacent_lane_ids(ego_position, ego_yaw_rad)
        if not adjacent_lane_ids:
            return None

        min_lateral_distance = float('inf')
        for obj_id, obj in frame.obj_list.items():
            if obj_id == self.scenario.ego_id:
                continue
            obj_position_3d = obj.sp.position.to_tuple()
            obj_yaw = obj.sp.heading.yaw if obj.sp.heading else None
            if obj_yaw is not None and abs(obj_yaw) > 10.0:
                obj_yaw = math.radians(obj_yaw)
            obj_lane = self.scenario.map.find_closest_lane(obj_position_3d, heading=obj_yaw)
            if obj_lane is None or obj_lane not in adjacent_lane_ids:
                continue
            obj_position = obj_position_3d[:2]
            ego_to_vehicle = np.array(obj_position) - np.array(ego_position)
            lateral_distance = float(abs(np.dot(ego_to_vehicle, lateral_direction)))
            if lateral_distance < min_lateral_distance:
                min_lateral_distance = lateral_distance

        return min_lateral_distance if min_lateral_distance != float('inf') else None

    def _get_adjacent_lane_ids(self, ego_position, ego_heading=None):
        """Set of left + right neighbour lane ids of ego's current lane,
        or None when the map can't resolve them."""
        scenario_map = getattr(self.scenario, "map", None)
        if scenario_map is None:
            return None
        ego_lane_id = scenario_map.find_closest_lane(ego_position, heading=ego_heading)
        if ego_lane_id is None:
            return None
        adjacent = set()
        if self.lane_map is not None:
            adjacent.update(scenario_map.left_lanes(ego_lane_id))
            adjacent.update(scenario_map.right_lanes(ego_lane_id))
        else:
            map_data = scenario_map.map_data
            adjacent.update(map_data.left_lanes.get(ego_lane_id, []))
            adjacent.update(map_data.right_lanes.get(ego_lane_id, []))
        return adjacent or None
