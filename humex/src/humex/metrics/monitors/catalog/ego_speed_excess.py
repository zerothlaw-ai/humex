"""Ego vehicle speed excess monitor.

This module implements a monitor that calculates how much the ego vehicle
exceeds the speed limit in its current lane.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class EgoSpeedExcess(MonitorBase):
    """Monitor for calculating ego vehicle speed excess over speed limit.

    OUTPUT_TYPE: FLOAT

    Returns the amount by which ego speed exceeds the lane speed limit.
    Positive values indicate speeding, negative values indicate compliance.

    This is equivalent to ``ego_speed - ego_lane_speed_limit`` and could be composed
    in a DAG using those two monitors with a subtract operator. It is provided
    as a convenience to avoid a 3-node subgraph for this common check.

    See Also:
        EgoLaneSpeedLimit: Returns the raw lane speed limit at the ego's position.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        """Initialize ego speed excess monitor.
        
        Args:
            scenario: Simulation scenario containing vehicle and map data
        """
        super().__init__(scenario)

    def calculate(self):
        """Calculate ego speed excess over lane speed limit.
        
        Computes the difference between ego vehicle speed and the speed limit
        for the lane the ego vehicle is currently in.
        
        Returns:
            float: Speed excess in m/s (positive = over limit, negative/zero = compliant)
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        
        # Handle case where ego vehicle is not present in frame
        if ego is None:
            return None

        # Get ego speed
        ego_speed = ego.sp.velocity.norm()
        
        # Get ego position
        ego_position = ego.sp.position.to_tuple()
        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        # Find the closest lane to ego vehicle
        map_obj = self.scenario.map
        if map_obj is None:
            return None
        closest_lane_id = map_obj.find_closest_lane(ego_position, max_distance=10.0, heading=ego_heading)
        
        if closest_lane_id is None:
            # Ego vehicle not near any lane (off-road) - assume no speed limit
            return 0.0
            
        # Get the lane data and its speed limit
        lane_data = map_obj.map_data.lanes.get(closest_lane_id)
        if lane_data is None or lane_data.speed_limit <= 0.0:
            # No speed limit set - assume compliant
            return 0.0
            
        # Calculate speed excess (positive = over limit)
        speed_excess = ego_speed - lane_data.speed_limit
        return speed_excess