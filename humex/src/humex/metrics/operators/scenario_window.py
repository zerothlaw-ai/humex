"""Scenario window operator for time-based windowing of traces."""

from typing import Any, List, Tuple, Union

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class ScenarioWindowOperator(OperatorBase):
    """Passes through values for frames within time windows, None for frames outside."""

    def run(self, windows: List = None) -> MetricTrace:
        """Apply time-based windowing to a trace.

        For frames whose timestamp falls within any specified window, the original
        value passes through unchanged. For frames outside all windows, the value
        becomes None.

        Args:
            windows: List of [start_sec, end_sec] pairs in seconds (floats).
                     A single [start, end] is auto-wrapped to [[start, end]].
                     Boundaries are inclusive.

        Returns:
            MetricTrace with original values inside windows, None outside
        """
        if not windows:
            return self._create_output_trace(
                frame_values=[None] * len(self.frame_values)
            )

        # Normalize single window [s, e] to [[s, e]]
        if windows and not isinstance(windows[0], (list, tuple)):
            windows = [windows]

        # Convert seconds to nanoseconds
        windows_ns = [(int(s * 1e9), int(e * 1e9)) for s, e in windows]

        result = []
        for i, ts in enumerate(self.timestamps):
            if any(start <= ts <= end for start, end in windows_ns):
                result.append(self.frame_values[i])
            else:
                result.append(None)

        return self._create_output_trace(frame_values=result)
