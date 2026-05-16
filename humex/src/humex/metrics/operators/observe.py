"""Observer operator for no-op terminal nodes that preserve data without producing a verdict."""

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class ObserveOperator(OperatorBase):
    """Operator that preserves monitor data for inspection without producing a pass/fail verdict.

    Acts as a no-op terminal node: it keeps the monitor's frame values visible
    but is excluded from the final AND logic that determines the scenario verdict.
    """

    def __init__(self, data: MetricTrace, op_name: str = 'observe') -> None:
        """Initialize observe operator.

        Args:
            data: MetricTrace with values to observe
            op_name: Name of the operation (default: 'observe')
        """
        super().__init__(data, op_name)

    def run(self) -> MetricTrace:
        """Pass through frame values with no boolean evaluation.

        Returns:
            MetricTrace with original frame_values preserved,
            empty frame_results, and None reduced_value/reduced_result.
        """
        return self._create_output_trace(
            frame_values=self.frame_values,
            frame_results=[],
            reduced_value=None,
            reduced_result=None
        )
