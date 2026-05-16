"""Arithmetic operator for frame-by-frame numeric operations across multiple traces."""

from typing import List, Union

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase

VALID_OPS = {"add", "subtract", "multiply", "divide"}


class ArithmeticOperator(OperatorBase):
    """Performs frame-by-frame arithmetic across multiple float input traces.

    Supported operations: add, subtract, multiply, divide.
    Operations are applied left-to-right across inputs (e.g., subtract: a - b - c).
    Returns None for any frame where an input is None or division by zero occurs.
    Only accepts float inputs.
    """

    def __init__(self, data: Union[MetricTrace, List[MetricTrace]], op_name: str = 'arithmetic') -> None:
        """Initialize arithmetic operator.

        Args:
            data: List of MetricTraces with float frame_values and aligned timestamps.
                  Can also accept a single MetricTrace.
            op_name: Name of the operation (default: 'arithmetic')
        """
        if isinstance(data, list):
            super().__init__(data[0], op_name)
            self.traces = data
        else:
            super().__init__(data, op_name)
            self.traces = [data]

    def run(self, op: str = 'add', num_inputs: int = 2, abs_result: bool = False) -> MetricTrace:
        """Apply frame-by-frame arithmetic across all input traces.

        Args:
            op: Arithmetic operation - 'add', 'subtract', 'multiply', or 'divide'
            num_inputs: Expected number of input traces (default: 2)
            abs_result: If True, take absolute value of each frame result (default: False)

        Returns:
            MetricTrace with float frame_values from the arithmetic operation

        Raises:
            ValueError: If op is not valid, or if input count doesn't match num_inputs
        """
        if op not in VALID_OPS:
            raise ValueError(f"Unknown arithmetic op: {op}. Must be one of: {', '.join(sorted(VALID_OPS))}")

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

            try:
                if op == 'add':
                    val = sum(frame_vals)
                elif op == 'subtract':
                    val = frame_vals[0]
                    for v in frame_vals[1:]:
                        val -= v
                elif op == 'multiply':
                    val = frame_vals[0]
                    for v in frame_vals[1:]:
                        val *= v
                elif op == 'divide':
                    val = frame_vals[0]
                    for v in frame_vals[1:]:
                        if v == 0:
                            val = None
                            break
                        val /= v

                if val is not None and abs_result:
                    val = abs(val)
                result_values.append(val)
            except (TypeError, ValueError):
                result_values.append(None)

        return self._create_output_trace(frame_values=result_values)
