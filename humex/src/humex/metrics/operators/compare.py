"""Compare operator for element-wise threshold comparisons."""

import operator
from typing import Any

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


# Dictionary mapping string operators to Python operator functions
# Used for dynamic operator selection in metric evaluation
OPS = {
    '<': operator.lt,    # Less than
    '<=': operator.le,   # Less than or equal
    '>': operator.gt,    # Greater than
    '>=': operator.ge,   # Greater than or equal
    '==': operator.eq,   # Equal to
    '!=': operator.ne    # Not equal to
}


class CompareOperator(OperatorBase):
    """Operator for comparing values against a threshold.

    Performs element-wise comparison between trace values and a threshold,
    commonly used to convert time-series measurements to pass/fail results.
    Properly handles None values by preserving them in output.
    """

    def __init__(self, data: MetricTrace, op_name: str = 'compare') -> None:
        """Initialize compare operator.

        Args:
            data: MetricTrace with values to compare
            op_name: Name of the operation (default: 'compare')
        """
        super().__init__(data, op_name)

    def run(self, op_symbol: str, threshold: Any = None, tolerance_upper: float = 0.0, tolerance_lower: float = 0.0) -> MetricTrace:
        """Apply comparison operator to each element.

        Performs element-wise comparison with proper None handling.
        Updates frame_results only if they're empty (first compare in pipeline).
        This ensures that frame-level visualization uses comparisons closest to
        the original monitor source.

        Args:
            op_symbol: Comparison operator as string ('<', '<=', '>', '>=', '==', '!=')
            threshold: Value to compare each element against
            tolerance_upper: Positive tolerance — raises the threshold.
                For < and <=, this shifts threshold up (makes comparison easier to pass).
                For == and !=, defines the upper bound of the acceptance range.
            tolerance_lower: Negative tolerance — lowers the threshold.
                For > and >=, this shifts threshold down (makes comparison easier to pass).
                For == and !=, defines the lower bound of the acceptance range.

        Returns:
            MetricTrace with boolean results and optional frame_results

        Example:
            >>> trace = MetricTrace([0, 100, 200], frame_values=[1, 2, 3])
            >>> op = CompareOperator(trace, 'compare')
            >>> result = op.run('>', 2)
            >>> result.frame_values
            [False, False, True]
        """
        # Coerce string threshold to numeric if possible
        if isinstance(threshold, str):
            try:
                threshold = int(threshold) if '.' not in threshold else float(threshold)
            except (ValueError, TypeError):
                pass

        is_numeric_threshold = (
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
        )

        # Compute effective threshold with tolerance
        use_upper = tolerance_upper > 0 and is_numeric_threshold
        use_lower = tolerance_lower > 0 and is_numeric_threshold

        if use_lower and op_symbol in ('>', '>='):
            effective_threshold = threshold - tolerance_lower
        elif use_upper and op_symbol in ('<', '<='):
            effective_threshold = threshold + tolerance_upper
        else:
            effective_threshold = threshold

        # For == and != with tolerance, use range-based comparison
        use_range = (use_upper or use_lower) and op_symbol in ('==', '!=')

        def _compare(value, thresh):
            if value is None:
                return None
            try:
                if use_range:
                    lower_bound = threshold - tolerance_lower
                    upper_bound = threshold + tolerance_upper
                    in_range = lower_bound <= value <= upper_bound
                    return in_range if op_symbol == '==' else not in_range
                return OPS[op_symbol](value, thresh)
            except (TypeError, ValueError):
                return None

        # Get values, considering segments
        segmented_values = self._get_segmented_values()

        # Perform comparison on all values
        frame_values = [_compare(v, effective_threshold) for v in segmented_values]

        # Update frame_results with the comparison results
        # This ensures frame_results contain the boolean evaluation (pass/fail)
        # not the raw monitor values
        frame_results = frame_values

        # Compute reduced_result from frame_values if there's a reduced_value
        reduced_result = _compare(self.data.reduced_value, effective_threshold) if self.data.reduced_value is not None else None


        return self._create_output_trace(
            frame_values=frame_values,
            frame_results=frame_results,
            reduced_value=self.data.reduced_value,
            reduced_result=reduced_result
        )
