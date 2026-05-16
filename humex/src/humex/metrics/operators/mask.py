"""Mask operator for frame selection based on boolean conditions."""

from typing import Any, Optional, List, Union

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class MaskOperator(OperatorBase):
    """Operator for selecting frames based on boolean/None mask conditions.

    Filters frame data based on boolean masks using different selection strategies.
    Useful for isolating specific portions of time-series data based on conditions.

    Supports two input modes:
    - Single input: Mask trace filters its own boolean values
    - Dual input: First trace is mask (boolean), second trace is values to filter
    """

    def __init__(self, data: Union[MetricTrace, List[MetricTrace]], op_name: str = 'mask') -> None:
        """Initialize mask operator.

        Args:
            data: Either a single MetricTrace or a list of two MetricTraces:
                  - Single: MetricTrace with boolean values (mask filters itself)
                  - List: [mask_trace, value_trace] where mask filters value trace
            op_name: Name of the operation (default: 'mask')
        """
        # Handle both single trace and list of traces
        # IMPORTANT: set self.traces AFTER super().__init__() because
        # OperatorBase.__init__() overwrites self.traces = [data]
        if isinstance(data, list):
            super().__init__(data[0], op_name)
            self.traces = data
        else:
            super().__init__(data, op_name)
            self.traces = [data]

    def run(self, mode: str = 'while') -> MetricTrace:
        """Apply frame selection mask to metric trace values.

        Filters frames based on boolean conditions using specified mode.

        Args:
            mode: Selection mode - 'while' (select frames while True)

        Returns:
            MetricTrace with masked values (None for unselected frames, original value for selected)

        Raises:
            ValueError: If mode is not recognized

        Examples:
            Single input mode:
            >>> trace = MetricTrace([0, 100, 200, 300], [True, True, False, True])
            >>> op = MaskOperator(trace, 'mask')
            >>> result = op.run('while')
            >>> result.frame_values
            [True, True, None, True]  # Per-frame: pass True, mask False/None

            Dual input mode:
            >>> mask = MetricTrace([0, 100, 200], [True, True, False])
            >>> values = MetricTrace([0, 100, 200], [1.0, 2.0, 3.0])
            >>> op = MaskOperator([mask, values], 'mask')
            >>> result = op.run('while')
            >>> result.frame_values
            [1.0, 2.0, None]  # Pass through values where mask is True
        """
        if mode == 'while':
            masked_values = self._while()
        else:
            raise ValueError(f'Unknown mask mode: {mode}')

        # For dual input mode, use data trace's segments
        if len(self.traces) > 1:
            self.segments = self.traces[1].segments

        # Mask frame_results to match: pass through where mask is True, None where False
        masked_frame_results = []
        input_frame_results = self.traces[1].frame_results if len(self.traces) > 1 else self.data.frame_results
        if input_frame_results:
            mask_values = self.traces[0].frame_values if len(self.traces) > 1 else self.frame_values
            for i, mask_val in enumerate(mask_values):
                if mask_val is True:
                    fr = input_frame_results[i] if i < len(input_frame_results) else None
                    masked_frame_results.append(fr)
                else:
                    masked_frame_results.append(None)

        return self._create_output_trace(
            frame_values=masked_values,
            frame_results=masked_frame_results if masked_frame_results else None,
        )

    def _while(self) -> list:
        """Select frames where condition is True.

        Evaluates each frame independently against the boolean mask condition.
        Frames where the mask is True pass through; frames where the mask is
        False or None are set to None (masked out).

        For dual input mode:
        - traces[0]: Boolean mask trace
        - traces[1]: Values to filter

        Returns:
            List with selected frames (values from data trace) and masked frames (None)
        """
        results = []

        if len(self.traces) > 1:
            mask_values = self.traces[0].frame_values
            data_values = self.traces[1].frame_values

            for i, mask_val in enumerate(mask_values):
                if mask_val is True:
                    data_val = data_values[i] if i < len(data_values) else None
                    results.append(data_val)
                else:
                    results.append(None)
        else:
            for value in self.frame_values:
                if value is True:
                    results.append(value)
                else:
                    results.append(None)

        return results
