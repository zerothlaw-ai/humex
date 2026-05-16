"""Longitudinal time-to-collision (TTC) monitor for the front vehicle.

Computes TTC using closing speed: TTC = gap / (ego_speed - front_speed).
Uses the same front vehicle detection as FrontVehicleDistance (lane-graph
reachability + centerline projection) to ensure consistency.

When a polygon collision is detected (via EgoCollision logic), TTC = 0
regardless of the lane-graph front vehicle search result.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.math_helper import dist2d, polygons_collide
from ._front_vehicle_utils import find_front_vehicle_on_lane_path


class TtcFrontVehicle(MonitorBase):
    """Time-to-collision with the front vehicle using longitudinal closing speed.

    OUTPUT_TYPE: FLOAT

    Params (from DAG YAML):
        min_closing_speed (float): Minimum closing speed (m/s) below which TTC = infinity. Default 0.01.
    """
    OUTPUT_TYPE = OutputType.FLOAT
    PARAMS = [
        {"name": "min_closing_speed", "type": "float", "default": 0.01,
         "description": "Minimum closing speed (m/s) below which TTC = infinity"},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        self.min_closing_speed = float(self.params.get("min_closing_speed", 0.01))

    def _ego_has_collision(self, ego, frame):
        """Check if ego is currently colliding with any vehicle using polygon intersection."""
        ego_pt = ego.sp.position.to_tuple()
        for obj_id, obj in frame.obj_list.items():
            if obj_id == self.scenario.ego_id:
                continue
            obj_pt = obj.sp.position.to_tuple()
            if dist2d(ego_pt, obj_pt) > 50.0:
                continue
            ego_polygon = [
                ego.bbox.front_left.to_tuple(),
                ego.bbox.front_right.to_tuple(),
                ego.bbox.rear_left.to_tuple(),
                ego.bbox.rear_right.to_tuple(),
            ]
            obj_polygon = [
                obj.bbox.front_left.to_tuple(),
                obj.bbox.front_right.to_tuple(),
                obj.bbox.rear_right.to_tuple(),
                obj.bbox.rear_left.to_tuple(),
            ]
            if polygons_collide(ego_polygon, obj_polygon):
                return True
        return False

    def calculate(self):
        """Calculate TTC to the front vehicle for the current frame.

        Formula: TTC = bumper_to_bumper_gap / closing_speed

        Returns:
            float: TTC in seconds, or float('inf') if no front vehicle or not closing.
                   None if ego absent. 0.0 if collision detected (polygon or bumper overlap).
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        # Check for actual polygon collision first — TTC = 0 if colliding
        if self._ego_has_collision(ego, frame):
            return 0.0

        # Single call to find front vehicle — same as FrontVehicleDistance
        vehicle_id, vehicle_obj, s_gap = find_front_vehicle_on_lane_path(
            ego, frame, self.scenario,
            max_search_distance=float(self.params.get("max_search_distance", 200.0))
        )

        if vehicle_id is None:
            return float('inf')

        # Bumper-to-bumper distance
        bumper_distance = s_gap - ego.length / 2.0 - vehicle_obj.length / 2.0

        # Collision — bumpers overlapping
        if bumper_distance <= 0:
            return 0.0

        # Ego speed
        ego_speed = ego.sp.velocity.norm()

        # Front vehicle speed
        front_speed = vehicle_obj.sp.velocity.norm()

        # Closing speed
        closing_speed = ego_speed - front_speed
        if closing_speed <= self.min_closing_speed:
            return float('inf')

        return bumper_distance / closing_speed
