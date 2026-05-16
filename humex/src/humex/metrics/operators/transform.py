"""Transform operator for element-wise mathematical transformations."""

from typing import Any, Callable, Dict

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


# Dictionary mapping function names to Python built-in functions
FUNCS: Dict[str, Callable] = {
    'abs': abs  # Absolute value
}


class TransformOperator(OperatorBase):
    """Operator for applying element-wise mathematical transformations.

    Applies mathematical functions to each element in a list while preserving
    None values. Used for preprocessing data before comparison or reduction.
    """

    def __init__(self, data: MetricTrace, op_name: str = 'transform') -> None:
        """Initialize transform operator.

        Args:
            data: MetricTrace with values to transform
            op_name: Name of the operation (default: 'transform')
        """
        super().__init__(data, op_name)

    def run(self, sign: str) -> MetricTrace:
        """Apply element-wise mathematical function to metric trace values.

        Preserves None values in the output. Supported functions are defined
        in the FUNCS dictionary.

        Args:
            sign: Name of the function to apply (key in FUNCS)

        Returns:
            MetricTrace with transformed values and None values preserved

        Raises:
            KeyError: If the function name is not recognized

        Examples:
            >>> trace = MetricTrace([0, 100, 200, 300], frame_values=[-1, 2, -3, None])
            >>> op = TransformOperator(trace, 'transform')
            >>> result = op.run('abs')
            >>> result.frame_values
            [1, 2, 3, None]
        """
        if sign not in FUNCS:
            raise KeyError(f'Unknown function: {sign}')

        # Get values, considering segments
        segmented_values = self._get_segmented_values()

        func = FUNCS[sign]
        frame_values = [None if v is None else func(v) for v in segmented_values]

        return self._create_output_trace(
            frame_values=frame_values,
            frame_results=self.data.frame_results,
            reduced_value=self.data.reduced_value,
            reduced_result=self.data.reduced_result
        )
