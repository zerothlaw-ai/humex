"""Ego vehicle lane speed limit monitor.

This module implements speed limit detection for the ego vehicle's current lane position
using spatial queries against the map's lane speed limit data.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class EgoLaneSpeedLimit(MonitorBase):
    """Monitor for detecting the speed limit at ego vehicle's current lane.

    OUTPUT_TYPE: FLOAT

    Uses the map's spatial index to find the lane containing the ego vehicle,
    then returns the speed limit for that lane in meters per second.

    See Also:
        EgoSpeedExcess: Returns ``ego_speed - ego_lane_speed_limit`` directly if you
            need the difference rather than the raw limit value.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        """Initialize ego lane speed limit monitor.

        Args:
            scenario: Simulation scenario containing vehicle and map data
        """
        super().__init__(scenario)

    def calculate(self):
        """Get speed limit for ego vehicle's current lane position.

        Uses spatial queries to determine which lane the ego vehicle is currently
        in, then returns the speed limit for that lane.

        Returns:
            float: Speed limit in meters per second, 0.0 if no speed limit found,
                   None if ego not found or no map available
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        # Handle case where ego vehicle is not present in frame
        if ego is None:
            return None

        # Handle case where map is not available
        map_obj = self.scenario.map
        if map_obj is None:
            return None

        # Get ego position and heading
        ego_position = ego.sp.position.to_tuple()
        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        # Find the closest lane to ego vehicle
        closest_lane_id = map_obj.find_closest_lane(ego_position, max_distance=10.0, heading=ego_heading)

        if closest_lane_id is None:
            # Ego vehicle not near any lane (off-road)
            return 0.0

        # Get the lane data and return its speed limit
        lane_data = map_obj.map_data.lanes.get(closest_lane_id)
        if lane_data is None:
            return 0.0

        return lane_data.speed_limit
