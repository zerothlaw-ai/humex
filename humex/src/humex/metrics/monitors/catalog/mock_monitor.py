from humex.metrics.monitors.monitor_base import MonitorBase, OutputType


class MockMonitor(MonitorBase):
    """Mock monitor for testing DAG evaluation without scenario data.

    OUTPUT_TYPE: FLOAT

    Provides predefined frame values via DAG params instead of computing from
    scenario data. When used in a DAG, the evaluator builds the MetricTrace
    directly from params (frame_values, frame_duration, output_type).
    """
    OUTPUT_TYPE = OutputType.FLOAT

    PARAMS = [
        {"name": "frame_values", "type": "string", "default": "[]",
         "description": "JSON array of values for each frame (e.g. '[false, false, true]' or '[10.0, 20.0]')"},
        {"name": "frame_duration", "type": "float", "default": 0.1,
         "description": "Seconds between frames (e.g. 0.1 for 10Hz)"},
        {"name": "output_type", "type": "string", "default": "float",
         "description": "Type of output values: float, bool, int, string",
         "allowed_values": ["float", "bool", "int", "string"]},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)

    def calculate(self):
        """Not called directly — trace is built from params in DAGEvaluator."""
        return None
