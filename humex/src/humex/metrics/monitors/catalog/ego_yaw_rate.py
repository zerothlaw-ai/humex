"""Yaw rate monitor for ego vehicle.

This module calculates the yaw rate (angular velocity around the z-axis) for the
ego vehicle. Yaw rate is the rate of change of the vehicle's heading angle and
is an important metric for detecting aggressive steering maneuvers.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from .frame_interval import FrameInterval
import math


class EgoYawRate(MonitorBase):
    """Monitor for calculating ego vehicle yaw rate.

    OUTPUT_TYPE: FLOAT

    Yaw rate is the angular velocity around the vertical (z) axis, calculated
    as the rate of change of the yaw angle. This implementation properly handles
    angle wrapping to find the shortest angular path.

    This is a stateful monitor that tracks previous frame data.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        """Initialize yaw rate monitor.

        Args:
            scenario: Simulation scenario containing vehicle and map data
        """
        super().__init__(scenario)
        self.frame_interval_monitor = FrameInterval(scenario)
        self.prev_yaw = None  # Store previous frame's yaw angle in radians

    def calculate(self):
        """Calculate yaw rate for current frame.

        Returns:
            float: Yaw rate in rad/s, or 0.0 for first frame or if ego not found
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        # Handle case where ego vehicle is not present in frame
        if ego is None:
            self.prev_yaw = None
            return None

        # Get current yaw angle
        current_yaw = ego.sp.heading.yaw

        # Convert to radians if in degrees (detect by magnitude)
        if abs(current_yaw) > 10.0:  # Likely degrees
            current_yaw_rad = math.radians(current_yaw)
        else:
            current_yaw_rad = current_yaw  # Already in radians

        # For the first frame or when previous data is unavailable, return 0
        if self.prev_yaw is None:
            self.prev_yaw = current_yaw_rad
            return 0.0

        # Calculate yaw difference with proper angle wrapping
        yaw_diff = current_yaw_rad - self.prev_yaw

        # Normalize angle difference to [-π, π] to find shortest angular path
        # This handles wraparound (e.g., from -179° to 179° or vice versa)
        while yaw_diff > math.pi:
            yaw_diff -= 2 * math.pi
        while yaw_diff < -math.pi:
            yaw_diff += 2 * math.pi

        # Get time interval between frames
        self.frame_interval_monitor.curr_frame = self.curr_frame
        time_interval = self.frame_interval_monitor.calculate()

        # Calculate yaw rate
        if time_interval < 1e-6:
            # Invalid time interval, return 0
            yaw_rate = 0.0
        else:
            yaw_rate = yaw_diff / time_interval

        # Update previous yaw for next frame
        self.prev_yaw = current_yaw_rad

        return yaw_rate
