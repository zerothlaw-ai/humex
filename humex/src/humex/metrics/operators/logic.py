"""Logic operator for frame-by-frame boolean operations across multiple traces."""

from typing import Any, List, Union

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class LogicOperator(OperatorBase):
    """Combines multiple boolean traces using frame-by-frame logic operations (AND, OR)."""

    def __init__(self, data: Union[MetricTrace, List[MetricTrace]], op_name: str = 'logic') -> None:
        """Initialize logic operator.

        Args:
            data: List of MetricTraces with boolean frame_values and aligned timestamps.
                  Can also accept a single MetricTrace (though not very useful).
            op_name: Name of the operation (default: 'logic')
        """
        if isinstance(data, list):
            super().__init__(data[0], op_name)
            self.traces = data
        else:
            super().__init__(data, op_name)
            self.traces = [data]

    def run(self, op: str = 'and', num_inputs: int = 2) -> MetricTrace:
        """Apply frame-by-frame boolean logic across all input traces.

        Args:
            op: Logic operation - 'and' or 'or'
            num_inputs: Expected number of input traces (default: 2)

        Returns:
            MetricTrace with boolean frame_values from the logic operation

        Raises:
            ValueError: If op is not 'and' or 'or', or if input count doesn't match num_inputs
        """
        if op not in ('and', 'or'):
            raise ValueError(f"Unknown logic op: {op}. Must be one of: and, or")

        if len(self.traces) != num_inputs:
            raise ValueError(f"Expected {num_inputs} input traces, got {len(self.traces)}")

        num_frames = len(self.traces[0].frame_values)
        result_values = []

        for i in range(num_frames):
            frame_vals = []
            has_none = False
            for trace in self.traces:
                val = trace.frame_values[i] if i < len(trace.frame_values) else None
                if val is None:
                    has_none = True
                    break
                frame_vals.append(val)

            if has_none:
                result_values.append(None)
                continue

            if op == 'and':
                result_values.append(all(frame_vals))
            elif op == 'or':
                result_values.append(any(frame_vals))

        return self._create_output_trace(frame_values=result_values)
