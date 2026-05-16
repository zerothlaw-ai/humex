"""Front vehicle bumper-to-bumper distance using lane-graph reachability.

Uses BFS over the lane graph and centerline s-coordinate projection
to compute along-lane distance — works correctly on curved lanes.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from ._front_vehicle_utils import find_front_vehicle_on_lane_path


class FrontVehicleDistance(MonitorBase):
    """Bumper-to-bumper distance to front vehicle using lane-graph reachability and centerline projection.

    OUTPUT_TYPE: FLOAT
    """
    OUTPUT_TYPE = OutputType.FLOAT
    PARAMS = [
        {"name": "max_search_distance", "type": "float", "default": 200.0,
         "description": "Max centerline distance (m) to search for front vehicle"},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        self.max_search_distance = float(self.params.get("max_search_distance", 200.0))

    def calculate(self):
        """Calculate bumper-to-bumper distance to front vehicle along lane path.

        Returns:
            float: Bumper-to-bumper distance in meters, or float('inf') if no front vehicle
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        vehicle_id, vehicle_obj, s_gap = find_front_vehicle_on_lane_path(
            ego, frame, self.scenario, self.max_search_distance
        )

        if vehicle_id is None:
            return float('inf')

        # Subtract half-lengths for bumper-to-bumper distance
        bumper_distance = s_gap - ego.length / 2.0 - vehicle_obj.length / 2.0
        return max(0.0, bumper_distance)
