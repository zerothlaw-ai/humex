"""Chain result operator for overriding per-chain frame-to-result aggregation."""

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class ChainResultOperator(OperatorBase):
    """Override how a single metric chain aggregates frame results into its chain-level result."""

    def __init__(self, data: MetricTrace, op_name: str = 'chain_result') -> None:
        super().__init__(data, op_name)

    def run(self, mode: str = 'any_pass') -> MetricTrace:
        """Aggregate frame results into a chain-level reduced_result.

        Args:
            mode: Aggregation mode.
                'any_pass' — chain passes if any frame passes (any() logic).
                'all_pass' — chain passes only if all frames pass (all() logic, default behavior).

        Returns:
            MetricTrace with reduced_result set according to the chosen mode.
        """
        frame_results = self.data.frame_results or self.data.frame_values
        bool_frames = [bool(f) for f in frame_results if f is not None]

        if mode == 'any_pass':
            reduced_result = any(bool_frames) if bool_frames else None
        else:
            reduced_result = all(bool_frames) if bool_frames else None

        return self._create_output_trace(
            frame_values=self.data.frame_values,
            frame_results=self.data.frame_results,
            reduced_value=self.data.reduced_value,
            reduced_result=reduced_result,
        )
