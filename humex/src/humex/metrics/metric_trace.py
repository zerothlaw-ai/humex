"""Unified metric trace output format for time-series metric data."""

from dataclasses import dataclass, field
from typing import List, Any, Tuple


@dataclass
class MetricTrace:
    """Unified output format for all metric computations.

    Represents time-series metric data with support for event segmentation and
    multi-layer processing through DAG operators.

    Attributes:
        timestamps: List of int64 nanosecond timestamps, must be sorted
        frame_values: List of metric values (any type), one per timestamp
        segments: List of (start_ts, end_ts) tuples defining evaluation segments
        frame_results: List of frame-level boolean results (populated by compare operators)
        reduced_value: Single aggregated value (computed by reduce operators)
        reduced_result: Single scenario-level pass/fail result (from compare on reduced_value)
        source_monitors: List of monitor node IDs that produced original data
    """
    timestamps: List[int] = field(default_factory=list)
    frame_values: List[Any] = field(default_factory=list)
    segments: List[Tuple[int, int]] = field(default_factory=list)
    frame_results: List[Any] = field(default_factory=list)
    reduced_value: Any = None
    reduced_result: Any = None
    source_monitors: List[int] = field(default_factory=list)

    def __post_init__(self):
        """Validate that timestamps and frame_values have matching lengths."""
        if len(self.timestamps) != len(self.frame_values):
            raise ValueError(
                f"timestamps and frame_values must have same length: "
                f"got {len(self.timestamps)} vs {len(self.frame_values)}"
            )

        # Validate segments
        for segment in self.segments:
            if not isinstance(segment, (tuple, list)) or len(segment) != 2:
                raise ValueError(
                    f"Each segment must be a (start_ts, end_ts) tuple, got {segment}"
                )
            start_ts, end_ts = segment
            if not isinstance(start_ts, int) or not isinstance(end_ts, int):
                raise ValueError(
                    f"Segment timestamps must be int64, got {type(start_ts).__name__} and {type(end_ts).__name__}"
                )
            if start_ts > end_ts:
                raise ValueError(
                    f"Segment start_ts must be <= end_ts, got {start_ts} > {end_ts}"
                )

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            dict: Dictionary with timestamps, frame_values, segments, and other fields
        """
        return {
            'timestamps': self.timestamps,
            'frame_values': self.frame_values,
            'segments': self.segments,
            'frame_results': self.frame_results,
            'reduced_value': self.reduced_value,
            'reduced_result': self.reduced_result,
            'source_monitors': self.source_monitors
        }

    @staticmethod
    def from_dict(data: dict) -> 'MetricTrace':
        """Create MetricTrace from dictionary representation.

        Args:
            data: Dictionary with 'timestamps', 'frame_values', and optional other fields

        Returns:
            MetricTrace: New instance from dictionary data
        """
        return MetricTrace(
            timestamps=data.get('timestamps', []),
            frame_values=data.get('frame_values', data.get('values', [])),  # Support 'values' for compatibility
            segments=data.get('segments', []),
            frame_results=data.get('frame_results', []),
            reduced_value=data.get('reduced_value', None),
            reduced_result=data.get('reduced_result', None),
            source_monitors=data.get('source_monitors', [])
        )

    def __len__(self) -> int:
        """Return number of data points in trace."""
        return len(self.frame_values)

    def __bool__(self) -> bool:
        """Return True if trace has data points."""
        return len(self.frame_values) > 0

    def get_value_at_index(self, index: int) -> Any:
        """Get value at specific index.

        Args:
            index: Index into frame_values list

        Returns:
            Value at index, or None if index out of range
        """
        if 0 <= index < len(self.frame_values):
            return self.frame_values[index]
        return None

    def get_timestamp_at_index(self, index: int) -> int:
        """Get timestamp at specific index.

        Args:
            index: Index into timestamps list

        Returns:
            Timestamp at index, or None if index out of range
        """
        if 0 <= index < len(self.timestamps):
            return self.timestamps[index]
        return None
