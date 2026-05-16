from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
import random


class LaneChangeState(MonitorBase):
    """Monitor for detecting current lane change state of the ego vehicle.

    OUTPUT_TYPE: STRING
    """
    OUTPUT_TYPE = OutputType.STRING

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        #TODO Implement actual logic
        a = ['left', 'right', 'none']
        result = random.choice(a)
        return result