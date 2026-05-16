"""Ego heading monitor.

Reports the ego vehicle's heading (yaw angle) in radians per frame.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class EgoHeading(MonitorBase):
    """Monitor for ego vehicle heading direction.

    OUTPUT_TYPE: FLOAT

    Returns the ego vehicle's yaw angle in radians for each frame.
    Uses the same degree/radian auto-detection heuristic as EgoYawRate:
    if abs(yaw) > 10.0, the value is assumed to be in degrees and converted.
    Output is always in radians.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate ego vehicle heading for current frame.

        Returns:
            float: Heading (yaw) in radians, or None if ego not found
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        if ego is None:
            return None

        yaw = ego.sp.heading.yaw

        # Convert to radians if in degrees (detect by magnitude)
        if abs(yaw) > 10.0:  # Likely degrees
            yaw = math.radians(yaw)

        return yaw
