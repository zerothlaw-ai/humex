from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class EgoSpeed(MonitorBase):
    """Monitor for calculating ego vehicle speed.

    OUTPUT_TYPE: FLOAT
    
    Returns the magnitude of the ego vehicle's velocity vector for each frame.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate ego vehicle speed for current frame.
        
        Returns:
            float: Speed magnitude in meters per second, or None if ego not found
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        
        # Handle case where ego vehicle is not present in frame
        if ego is None:
            return None

        # Return velocity magnitude (speed) - now enhanced by data loader
        return ego.sp.velocity.norm()