"""Duration operator for measuring how long boolean conditions hold continuously."""

from typing import List, Tuple

from humex.metrics.metric_trace import MetricTrace
from .operator_base import OperatorBase


class DurationOperator(OperatorBase):
    """Operator for measuring the duration of continuous boolean events.

    Scans a boolean trace to find runs of consecutive target-matching frames,
    optionally bridging small gaps, and outputs the run duration (in seconds)
    for each qualifying frame. Non-qualifying frames receive 0.0.

    Example chain: ego_hard_brake -> compare(> 1.0) -> duration(target=True, min_duration=2.0) -> reduce(max)
    """

    def __init__(self, data: MetricTrace, op_name: str = 'duration') -> None:
        """Initialize duration operator.

        Args:
            data: MetricTrace with boolean frame_values (typically from a compare operator)
            op_name: Name of the operation (default: 'duration')
        """
        super().__init__(data, op_name)

    def run(self, target: bool = True, min_duration: float = 0.0, gap_tolerance: int = 0) -> MetricTrace:
        """Compute duration of continuous boolean events in the trace.

        Args:
            target: Which boolean value constitutes an "event" (default: True)
            min_duration: Minimum run duration in seconds to qualify (default: 0.0)
            gap_tolerance: Max consecutive non-target frames to bridge within a run (default: 0)

        Returns:
            MetricTrace with float duration values (seconds) for qualifying frames, 0.0 elsewhere
        """
        # Coerce parameter types (YAML may pass strings)
        target = self._coerce_bool(target)
        min_duration = self._coerce_float(min_duration)
        gap_tolerance = self._coerce_int(gap_tolerance)

        segmented_values = self._get_segmented_values()

        # Find runs of target values, bridging small gaps
        runs = self._find_runs(segmented_values, target, gap_tolerance)

        # Compute duration for each run and filter by min_duration
        durations = [0.0] * len(segmented_values)
        for start_idx, end_idx in runs:
            run_duration = self._compute_duration(start_idx, end_idx)
            if run_duration >= min_duration:
                for i in range(start_idx, end_idx + 1):
                    durations[i] = run_duration

        # Preserve None for out-of-segment frames
        frame_values = []
        for i, val in enumerate(segmented_values):
            if val is None:
                frame_values.append(None)
            else:
                frame_values.append(durations[i])

        return self._create_output_trace(frame_values=frame_values)

    def _find_runs(self, values: List, target: bool, gap_tolerance: int) -> List[Tuple[int, int]]:
        """Find runs of consecutive target-matching frames, bridging small gaps.

        Args:
            values: List of boolean/None values from segmented trace
            target: The boolean value that constitutes an event
            gap_tolerance: Max consecutive non-target frames to bridge

        Returns:
            List of (start_idx, end_idx) tuples for each identified run
        """
        runs = []
        run_start = None
        gap_count = 0

        for i, val in enumerate(values):
            if val == target:
                if run_start is None:
                    run_start = i
                gap_count = 0
            elif run_start is not None:
                # Non-target frame while in a run
                gap_count += 1
                if gap_count > gap_tolerance:
                    # Gap too large, end the run
                    # End index is before the gap
                    run_end = i - gap_count
                    runs.append((run_start, run_end))
                    run_start = None
                    gap_count = 0

        # Close any open run
        if run_start is not None:
            # Find the last target-matching frame in the run
            run_end = len(values) - 1
            while run_end > run_start and values[run_end] != target:
                run_end -= 1
            runs.append((run_start, run_end))

        return runs

    def _compute_duration(self, start_idx: int, end_idx: int) -> float:
        """Compute segment duration as sum of frame durations (in seconds).

        Each frame's duration = time to next frame. The sum telescopes to
        timestamps[end+1] - timestamps[start]. Edge cases handle when end
        is the last frame in the trace.

        Args:
            start_idx: Index of the first frame in the segment
            end_idx: Index of the last frame in the segment

        Returns:
            Duration in seconds (timestamps are int64 nanoseconds)
        """
        if start_idx >= len(self.timestamps) or end_idx >= len(self.timestamps):
            return 0.0
        if end_idx + 1 < len(self.timestamps):
            # Next timestamp available — sum telescopes to this
            return (self.timestamps[end_idx + 1] - self.timestamps[start_idx]) / 1e9
        elif end_idx > start_idx:
            # Last frame in trace — extrapolate using previous dt
            last_dt = self.timestamps[end_idx] - self.timestamps[end_idx - 1]
            return (self.timestamps[end_idx] - self.timestamps[start_idx] + last_dt) / 1e9
        elif start_idx > 0:
            # Single frame at end of trace — use previous interval
            return (self.timestamps[start_idx] - self.timestamps[start_idx - 1]) / 1e9
        else:
            # Single frame, no reference — can't compute
            return 0.0

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
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
        return float(value)

    @staticmethod
    def _coerce_int(value) -> int:
        """Coerce a value to int (handles YAML string numbers)."""
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(float(value))
        return int(value)
