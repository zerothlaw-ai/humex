"""Aggregate operator for segmenting and aggregating time-series data."""

from typing import Any

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class AggregateOperator(OperatorBase):
    """Operator for aggregating time-series data using segmentation strategies.

    Processes time-series data to compute aggregated metrics like continuous
    duration (cumulative sum with reset on None values).
    """

    def __init__(self, data: MetricTrace, op_name: str = 'aggregate') -> None:
        """Initialize aggregate operator.

        Args:
            data: MetricTrace with values to aggregate
            op_name: Name of the operation (default: 'aggregate')
        """
        super().__init__(data, op_name)

    def run(self, op_symbol: str, recalc_segments: bool = False) -> MetricTrace:
        """Apply aggregation operation to metric trace values.

        Supports aggregation strategies like continuous duration calculation.

        Args:
            op_symbol: Aggregation operation - currently supports 'continuous_duration'
            recalc_segments: If True, recalculate segments based on output values

        Returns:
            MetricTrace with aggregated values

        Raises:
            ValueError: If op_symbol is not recognized

        Examples:
            >>> trace = MetricTrace([0, 100, 200, 300], [1.0, 2.0, None, 3.0])
            >>> op = AggregateOperator(trace, 'aggregate')
            >>> result = op.run('continuous_duration')
            >>> result.values
            [1.0, 3.0, 0.0, 3.0]
        """
        if op_symbol != "continuous_duration":
            raise ValueError(f'Unknown aggregation operator: {op_symbol}')

        aggregated_values = self._continuous_duration()

        # Create output trace
        trace = MetricTrace(
            timestamps=self.timestamps,
            frame_values=aggregated_values,
            segments=self.data.segments
        )

        # Optionally recalculate segments based on output values
        if recalc_segments:
            trace.segments = self._recalculate_segments(aggregated_values)

        return trace

    def _continuous_duration(self) -> list:
        """Calculate continuous duration with reset on None values.

        Maintains a cumulative sum that resets to 0 when encountering None.
        Useful for measuring continuous durations of met conditions.

        Returns:
            List of cumulative sums with resets at None values
        """
        results = []
        cumulative_sum = 0.0

        for item in self.frame_values:
            if item is None:
                results.append(0.0)
                cumulative_sum = 0.0  # Reset cumulative sum
            else:
                assert isinstance(item, (int, float)), \
                    f"Expected numeric value in aggregation, got {type(item).__name__}"
                cumulative_sum += float(item)
                results.append(cumulative_sum)

        return results

    def _recalculate_segments(self, values: list) -> list:
        """Recalculate segments based on aggregated values.

        Creates segments where values are non-zero (active periods).

        Args:
            values: Aggregated values

        Returns:
            List of (start_ts, end_ts) tuples for non-zero segments
        """
        segments = []
        segment_start = None

        for i, value in enumerate(values):
            if value is not None and value != 0.0:
                # Value is active
                if segment_start is None:
                    segment_start = self.timestamps[i]
            else:
                # Value is inactive
                if segment_start is not None:
                    # End current segment
                    segments.append((segment_start, self.timestamps[i - 1]))
                    segment_start = None

        # Handle case where last segment extends to end
        if segment_start is not None:
            segments.append((segment_start, self.timestamps[-1]))

        return segments
