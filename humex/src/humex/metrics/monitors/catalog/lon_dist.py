from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class LonDist(MonitorBase):
    """Monitor for calculating longitudinal distance between ego vehicle and front vehicle.

    OUTPUT_TYPE: FLOAT
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):

        pass