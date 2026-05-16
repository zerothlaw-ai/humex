"""Frame interval monitor for calculating time duration between frames.

This module provides the FrameInterval monitor that calculates the actual
time interval between consecutive frames using their timestamps.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.timestamp import to_seconds


class FrameInterval(MonitorBase):
    """Monitor for calculating frame time intervals.

    OUTPUT_TYPE: FLOAT

    Returns the actual time duration between the current and previous frame.
    Uses scenario timestamps for accurate intervals regardless of frame rate.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate the time interval between current and previous frame.

        Returns:
            float: Time interval in seconds. Returns scenario.interval for the
                   first frame (no previous timestamp available).
        """
        if not self.timestamps:
            # First frame — use nominal interval from scenario
            return getattr(self.scenario, 'interval', 0.1)

        prev_ts = self.timestamps[-1]
        curr_ts = self.curr_frame.timestamp
        dt = to_seconds(curr_ts - prev_ts)

        # Sanity check: if dt is zero or negative, fall back to nominal
        if dt <= 0:
            return getattr(self.scenario, 'interval', 0.1)

        return dt
