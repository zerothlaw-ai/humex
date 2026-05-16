"""Time headway monitor for ego vehicle safety analysis.

Calculates the time to collision (time headway) between the ego vehicle
and the front vehicle ahead. Time headway is the time it would take for
the ego vehicle to reach the front vehicle's current position at the
ego's current speed.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from .front_vehicle_distance import FrontVehicleDistance
from .ego_speed import EgoSpeed


class TimeHeadway(MonitorBase):
    """Monitor for calculating time headway (time to collision) with front vehicle.

    OUTPUT_TYPE: FLOAT

    Time headway is calculated as the distance to the front vehicle divided by
    the ego vehicle's current speed.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)
        self.front_distance_monitor = FrontVehicleDistance(scenario)
        self.ego_speed_monitor = EgoSpeed(scenario)

    def calculate(self):
        """Calculate time headway to front vehicle for current frame.

        Returns:
            float: Time headway in seconds, or float('inf') if no front vehicle
                   or ego is stopped, or None if ego absent
        """
        self.front_distance_monitor.curr_frame = self.curr_frame
        self.ego_speed_monitor.curr_frame = self.curr_frame

        front_distance = self.front_distance_monitor.calculate()
        if front_distance is None:
            return None

        ego_speed = self.ego_speed_monitor.calculate()
        if ego_speed is None:
            return None

        if front_distance == float('inf') or ego_speed < 0.1:
            return float('inf')

        return front_distance / ego_speed
