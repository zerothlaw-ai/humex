"""Front vehicle ID detection using lane-graph reachability.

Uses BFS over the lane graph and centerline s-coordinate projection
to find the nearest vehicle ahead — works correctly on curved lanes.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from ._front_vehicle_utils import find_front_vehicle_on_lane_path


class FrontVehicleId(MonitorBase):
    """Detect front vehicle in ego's path using lane-graph reachability and centerline projection.

    OUTPUT_TYPE: INT
    """
    OUTPUT_TYPE = OutputType.INT
    PARAMS = [
        {"name": "max_search_distance", "type": "float", "default": 200.0,
         "description": "Max centerline distance (m) to search for front vehicle"},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        self.max_search_distance = float(self.params.get("max_search_distance", 200.0))

    def calculate(self):
        """Find front vehicle ID using lane-graph BFS and s-coordinate comparison.

        Returns:
            int or None: ID of front vehicle if detected, None otherwise
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        vehicle_id, _, _ = find_front_vehicle_on_lane_path(
            ego, frame, self.scenario, self.max_search_distance
        )
        return vehicle_id
