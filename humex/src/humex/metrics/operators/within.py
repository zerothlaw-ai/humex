"""Within operator for checking if a boolean state transition happens within a time budget."""

from typing import List, Optional

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class WithinOperator(OperatorBase):
    """Operator for checking if a boolean state transition happens within a time budget.

    Evaluates each null-separated group of frames independently. Within each group,
    checks if the target boolean state is reached within the specified time from
    the starting condition. All non-null frames in the group get True/False based
    on whether the transition happened within the time budget.

    Example chain: obstacle_detected -> within(starting="not_null", target=True, within=1.0) -> reduce(all)
    """

    def __init__(self, data: MetricTrace, op_name: str = 'within') -> None:
        super().__init__(data, op_name)

    def run(self, target: bool = True, within: float = 1.0, starting: str = "not_null") -> MetricTrace:
        """Check if boolean state transition happens within a time budget.

        Args:
            target: The target boolean state to reach (default: True)
            within: Max allowed transition time in seconds (default: 1.0)
            starting: What triggers the clock - "not_null", "false", or "true" (default: "not_null")

        Returns:
            MetricTrace with boolean values: True if transition happened within budget, False otherwise
        """
        target = self._coerce_bool(target)
        within = self._coerce_float(within)
        starting = self._coerce_starting(starting)

        segmented_values = self._get_segmented_values()

        # Find groups of consecutive non-null frames
        groups = self._find_groups(segmented_values)

        # Evaluate each group
        frame_values = [None] * len(segmented_values)
        for group_start, group_end in groups:
            result = self._evaluate_group(segmented_values, group_start, group_end, starting, target, within)
            for i in range(group_start, group_end + 1):
                frame_values[i] = result

        return self._create_output_trace(frame_values=frame_values)

    def _find_groups(self, values: List) -> List[tuple]:
        """Find runs of consecutive non-null values.

        Returns:
            List of (start_idx, end_idx) tuples for each group
        """
        groups = []
        group_start = None

        for i, val in enumerate(values):
            if val is not None:
                if group_start is None:
                    group_start = i
            else:
                if group_start is not None:
                    groups.append((group_start, i - 1))
                    group_start = None

        if group_start is not None:
            groups.append((group_start, len(values) - 1))

        return groups

    def _evaluate_group(self, values: List, group_start: int, group_end: int,
                        starting: str, target: bool, within_time: float) -> bool:
        """Evaluate a single group of non-null frames.

        Returns:
            True if target reached within time budget from starting condition, False otherwise
        """
        # Find starting frame index
        start_idx = None
        for i in range(group_start, group_end + 1):
            if self._matches_starting(values[i], starting):
                start_idx = i
                break

        if start_idx is None:
            return False

        # Find target frame index (after starting frame)
        target_idx = None
        for i in range(start_idx, group_end + 1):
            if values[i] == target:
                target_idx = i
                break

        if target_idx is None:
            return False

        # Compute duration from starting to target
        duration = self._compute_duration(start_idx, target_idx)
        return duration <= within_time

    def _matches_starting(self, value, starting: str) -> bool:
        """Check if a value matches the starting condition."""
        if starting == "not_null":
            return value is not None
        elif starting == "false":
            return value is False or value == False
        elif starting == "true":
            return value is True or value == True
        return False

    def _compute_duration(self, start_idx: int, end_idx: int) -> float:
        """Compute time difference between two frame indices in seconds.

        Args:
            start_idx: Index of the starting frame
            end_idx: Index of the ending frame

        Returns:
            Duration in seconds (timestamps are int64 nanoseconds)
        """
        if start_idx >= len(self.timestamps) or end_idx >= len(self.timestamps):
            return 0.0
        return (self.timestamps[end_idx] - self.timestamps[start_idx]) / 1e9

    @staticmethod
    def _coerce_bool(value) -> bool:
        """Coerce a value to bool (handles YAML string 'true'/'false')."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes'):
                return True
            if value.lower() in ('false', '0', 'no'):
                return False
        return bool(value)

    @staticmethod
    def _coerce_float(value) -> float:
        """Coerce a value to float (handles YAML string numbers)."""
        return float(value)

    @staticmethod
    def _coerce_starting(value) -> str:
        """Coerce starting parameter to valid string."""
        if isinstance(value, str):
            val = value.lower().strip()
            if val in ("not_null", "false", "true"):
                return val
        raise ValueError(f"Invalid starting value: {value!r}. Must be 'not_null', 'false', or 'true'.")
