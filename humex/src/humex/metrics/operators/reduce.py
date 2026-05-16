"""Reduce operator for reducing time-series data to single values."""

from typing import Any, Optional, Union

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class ReduceOperator(OperatorBase):
    """Operator for reducing time-series data to a single value.

    Reduces time-series data to a single scalar value for final pass/fail determination.
    Returns result as single-element MetricTrace to maintain unified format.
    Filters out None values before applying the reduction operation.
    """

    def __init__(self, data: MetricTrace, op_name: str = 'reduce') -> None:
        """Initialize reduce operator.

        Args:
            data: MetricTrace with values to reduce (may contain None values)
            op_name: Name of the operation (default: 'reduce')
        """
        super().__init__(data, op_name)

    def run(self, op: str) -> MetricTrace:
        """Apply reduction operation to metric trace values.

        Reduces time-series data to a single value. Filters out None values
        before applying the reduction operation. Sets reduced_value in output.

        If frame_results are empty, also populates them from frame_values
        (handles case where reduce comes before first compare).

        Args:
            op: Reduction operation - 'min', 'max', 'any', 'all', or 'not_any'

        Returns:
            MetricTrace with frame_values, reduced_value, and optional frame_results

        Raises:
            ValueError: If op is not a recognized reduction operation

        Examples:
            >>> trace = MetricTrace([0, 100, 200], frame_values=[True, False, True])
            >>> op = ReduceOperator(trace, 'reduce')
            >>> result = op.run('any')
            >>> result.reduced_value
            True
        """
        # Get values, considering segments
        segmented_values = self._get_segmented_values()

        # Filter out None values which represent excluded frames
        no_none_base = [x for x in segmented_values if x is not None]

        # Handle empty sequences (when all values were None due to unmet conditions)
        if not no_none_base:
            reduced_value = self._handle_empty_case(op)
        else:
            reduced_value = self._reduce_value(op, no_none_base)

        # If frame_results are empty, populate them from frame_values
        # This handles the case where reduce comes before first compare
        frame_results = self.data.frame_results
        if not frame_results:
            frame_results = segmented_values

        return self._create_output_trace(
            frame_values=segmented_values,
            frame_results=frame_results,
            reduced_value=reduced_value,
            reduced_result=None  # Will be set by compare operator if needed
        )

    def _handle_empty_case(self, op: str) -> Optional[Union[bool, float, int]]:
        """Handle reduction when all values are None.

        Args:
            op: Reduction operation

        Returns:
            Default value based on operation semantics
        """
        if op in ['min', 'max']:
            # For min/max on empty sequences, return None
            # This indicates the condition was never met during the scenario
            return None
        elif op == 'any':
            return False  # No elements to be True
        elif op == 'all':
            return True   # No elements means all (none) are True
        elif op == 'not_any':
            return True   # No elements means none are True
        else:
            raise ValueError(f'Unknown reduction operation: {op}')

    def _reduce_value(self, op: str, values) -> Optional[Union[bool, float, int]]:
        """Apply reduction to non-None values.

        Args:
            op: Reduction operation
            values: List of non-None values

        Returns:
            Reduced value
        """
        if op == 'min':
            return min(values)
        elif op == 'max':
            return max(values)
        elif op == 'any':
            return any(values)  # True if any element is True
        elif op == 'all':
            return all(values)  # True if all elements are True
        elif op == 'not_any':
            return not any(values)  # True if no elements are True
        else:
            raise ValueError(f'Unknown reduction operation: {op}')
