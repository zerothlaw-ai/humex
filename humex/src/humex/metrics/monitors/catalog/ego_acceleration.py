"""Monitor for ego vehicle acceleration magnitude."""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class EgoAcceleration(MonitorBase):
    """Monitor for calculating ego vehicle acceleration magnitude.

    OUTPUT_TYPE: FLOAT

    Returns the magnitude of the ego vehicle's acceleration vector for each frame.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate ego vehicle acceleration magnitude for current frame.
        
        Returns:
            float: Acceleration magnitude in m/s², or None if ego not found
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        
        # Handle case where ego vehicle is not present in frame
        if ego is None:
            return None
            
        # Return acceleration magnitude - now enhanced by data enhancer
        return ego.sp.acceleration.norm()