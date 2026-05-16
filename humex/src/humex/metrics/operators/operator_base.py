"""Base class for all operator types in the metrics evaluation system."""

from abc import ABC, abstractmethod
from typing import Any, List, Tuple, Optional, Union
import inspect

from humex.metrics.metric_trace import MetricTrace


class OperatorBase(ABC):
    """Abstract base class for operators used in metric evaluation.

    All operator types (comparator, reducer, aggregator, function) should inherit
    from this class and implement the run() method.

    Operators accept MetricTrace or List[MetricTrace] as input and return MetricTrace
    as output, maintaining temporal coupling between timestamps and values throughout
    metric computation pipelines. Multiple input traces enable binary operations and
    complex transformations.

    Operators are segment-aware: they only process values for timestamps that fall
    within the input trace's segments. Values outside segments are set to None.
    Metadata fields (segments, source_monitors, etc.) are preserved across operators.
    """

    MAX_DESCRIPTION_LENGTH = 200

    def __init_subclass__(cls, **kwargs):
        """Validate that all operator subclasses have proper descriptions."""
        super().__init_subclass__(**kwargs)
        cls._validate_description()

    @classmethod
    def _validate_description(cls):
        """Validate that operator has a description of appropriate length.

        Raises:
            TypeError: If description is missing or exceeds MAX_DESCRIPTION_LENGTH
        """
        # Check for explicit docstring (not inherited)
        if cls.__doc__ is None:
            raise TypeError(
                f"Operator '{cls.__name__}' must have a docstring. "
                f"Add a description in the class docstring."
            )

        doc = inspect.getdoc(cls)
        if not doc:
            raise TypeError(
                f"Operator '{cls.__name__}' has empty docstring. "
                f"First line of docstring must not be empty."
            )

        first_line = doc.split('\n')[0].strip()
        if not first_line:
            raise TypeError(
                f"Operator '{cls.__name__}' has empty docstring. "
                f"First line of docstring must not be empty."
            )

        if len(first_line) > cls.MAX_DESCRIPTION_LENGTH:
            raise TypeError(
                f"Operator '{cls.__name__}' description exceeds {cls.MAX_DESCRIPTION_LENGTH} chars. "
                f"Current: {len(first_line)} chars. "
                f"First line: '{first_line[:100]}...'"
            )

    def __init__(self, data: Union[MetricTrace, List[MetricTrace]], op_name: str) -> None:
        """Initialize operator with metric trace data.

        Args:
            data: Input MetricTrace or List[MetricTrace] containing timestamps, frame_values,
                  segments, and metadata. If list is provided, all traces must have matching
                  timestamps for proper alignment. Primary trace is the first in the list.
            op_name: Name/identifier for the operation (e.g., 'compare', 'reduce')

        Raises:
            TypeError: If data is neither MetricTrace nor List[MetricTrace]
        """
        # Handle both single trace and list of traces
        if isinstance(data, MetricTrace):
            self.data = data
            self.traces = [data]
            self.is_multi_input = False
        elif isinstance(data, list):
            if not data:
                raise ValueError("Input list must not be empty")
            if not all(isinstance(t, MetricTrace) for t in data):
                raise TypeError("All items in list must be MetricTrace instances")
            self.traces = data
            self.data = data[0]  # Use first trace as primary
            self.is_multi_input = True
        else:
            raise TypeError(f"data must be MetricTrace or List[MetricTrace], got {type(data)}")

        self.op_name = op_name
        self.timestamps = self.data.timestamps
        self.frame_values = self.data.frame_values  # Renamed from 'values'
        self.segments = self.data.segments
        self.source_monitors = self.data.source_monitors

    def _is_in_segment(self, timestamp: int) -> bool:
        """Check if a timestamp falls within any of the segments.

        Args:
            timestamp: Timestamp to check (int64 nanoseconds)

        Returns:
            bool: True if timestamp is within any segment, False otherwise
        """
        if not self.segments:
            # No segments defined means process all timestamps
            return True

        for start_ts, end_ts in self.segments:
            if start_ts <= timestamp <= end_ts:
                return True
        return False

    def _get_segmented_values(self) -> List[Any]:
        """Get frame values with None for values outside segments.

        Returns:
            List of values, with None for indices outside segments
        """
        result = []
        for i, ts in enumerate(self.timestamps):
            if i < len(self.frame_values):
                if self._is_in_segment(ts):
                    result.append(self.frame_values[i])
                else:
                    result.append(None)
            else:
                result.append(None)
        return result

    def _create_output_trace(self, frame_values: List[Any],
                            frame_results: Optional[List[Any]] = None,
                            reduced_value: Any = None,
                            reduced_result: Optional[bool] = None) -> MetricTrace:
        """Create output MetricTrace with operator result and preserved metadata.

        Args:
            frame_values: Output frame values
            frame_results: Optional frame-level boolean results
            reduced_value: Optional single aggregated value
            reduced_result: Optional scenario-level boolean result

        Returns:
            MetricTrace with results and preserved segments/source_monitors
        """
        return MetricTrace(
            timestamps=self.timestamps,
            frame_values=frame_values,
            segments=self.segments,  # Preserve segments from input
            frame_results=frame_results or [],
            reduced_value=reduced_value,
            reduced_result=reduced_result,
            source_monitors=self.source_monitors  # Preserve source monitors
        )

    @abstractmethod
    def run(self, *args, **kwargs) -> MetricTrace:
        """Execute the operator on stored metric trace with given parameters.

        Args:
            *args: Operation-specific positional arguments
            **kwargs: Operation-specific keyword arguments

        Returns:
            MetricTrace: Result of the operation with timestamps and values

        Raises:
            NotImplementedError: Subclasses must implement this method
        """
        pass