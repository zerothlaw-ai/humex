from abc import ABC, abstractmethod
from enum import Enum
import inspect
from humex.metrics.metric_trace import MetricTrace


class OutputType(Enum):
    """Allowed output value types for monitors."""
    FLOAT = "float"
    BOOL = "bool"
    INT = "int"
    STRING = "string"


class MonitorBase(ABC):
    MAX_DESCRIPTION_LENGTH = 200

    def __init_subclass__(cls, **kwargs):
        """Validate that all monitor subclasses have proper descriptions and output types."""
        super().__init_subclass__(**kwargs)
        cls._validate_description()
        cls._validate_output_type()

    @classmethod
    def _validate_description(cls):
        """Validate that monitor has a description of appropriate length.

        Raises:
            TypeError: If description is missing or exceeds MAX_DESCRIPTION_LENGTH
        """
        # Check for explicit docstring (not inherited)
        if cls.__doc__ is None:
            raise TypeError(
                f"Monitor '{cls.__name__}' must have a docstring. "
                f"Add a description in the class docstring."
            )

        doc = inspect.getdoc(cls)
        if not doc:
            raise TypeError(
                f"Monitor '{cls.__name__}' has empty docstring. "
                f"First line of docstring must not be empty."
            )

        first_line = doc.split('\n')[0].strip()
        if not first_line:
            raise TypeError(
                f"Monitor '{cls.__name__}' has empty docstring. "
                f"First line of docstring must not be empty."
            )

        if len(first_line) > cls.MAX_DESCRIPTION_LENGTH:
            raise TypeError(
                f"Monitor '{cls.__name__}' description exceeds {cls.MAX_DESCRIPTION_LENGTH} chars. "
                f"Current: {len(first_line)} chars. "
                f"First line: '{first_line[:100]}...'"
            )

    @classmethod
    def _validate_output_type(cls):
        """Validate that monitor defines OUTPUT_TYPE as an OutputType enum.

        Raises:
            TypeError: If OUTPUT_TYPE is missing or not an OutputType enum
        """
        if not hasattr(cls, 'OUTPUT_TYPE'):
            raise TypeError(
                f"Monitor '{cls.__name__}' must define OUTPUT_TYPE. "
                f"Add OUTPUT_TYPE = OutputType.FLOAT (or BOOL, INT, STRING) as a class attribute."
            )

        if not isinstance(cls.OUTPUT_TYPE, OutputType):
            raise TypeError(
                f"Monitor '{cls.__name__}' OUTPUT_TYPE must be an OutputType enum value. "
                f"Got: {type(cls.OUTPUT_TYPE).__name__}"
            )

    def __init__(self, scenario, params=None):
        self.params = params or {}  # DAG-configurable parameters
        self.timestamps = []  # List of int64 ns timestamps
        self.values = []      # List of metric values (any type)
        self.scenario = scenario
        self.curr_frame = None

    # ---- Convenience accessors for optional sidecars -----------------
    # Many scenarios (older imports, third-party data) won't have a
    # lane_map.pb or role.pb sidecar attached. These properties return
    # None when the sidecar is absent so monitor `calculate()` methods
    # can short-circuit gracefully and fall back to per-frame compute.

    @property
    def lane_map(self):
        """The v2 :class:`LaneMap` for this scenario, or ``None`` when no
        ``lane_map.pb`` sidecar was loaded.

        ``scenario.map`` is normally an :class:`HMap` facade that
        exposes the underlying ``LaneMap`` via a ``lane_map`` property.
        For scenarios loaded without a lane_map sidecar, ``scenario.map``
        is the raw legacy ``RoadMap`` and this returns ``None``.
        """
        m = getattr(self.scenario, "map", None)
        if m is None:
            return None
        # HMap exposes `lane_map`; raw RoadMap doesn't have that attr.
        return getattr(m, "lane_map", None)

    @property
    def role_table(self):
        """The precomputed :class:`RoleTable` for this scenario, or ``None``
        when no ``role.pb`` sidecar was loaded.

        Use the ``isinstance`` check rather than truthiness — MagicMock'd
        scenarios in unit-test fixtures auto-generate ``role_table`` as a
        Mock, and we don't want to mistake that for a real table.
        """
        rt = getattr(self.scenario, "role_table", None)
        if rt is None:
            return None
        from humex.hmap.role_table import RoleTable
        return rt if isinstance(rt, RoleTable) else None

    def current_frame_index(self):
        """Index of ``self.curr_frame`` in ``scenario.timestamps``, or
        ``None`` if no current frame is set or its timestamp isn't known.
        Used by monitors that read the role table (which is keyed by
        frame_index, not timestamp)."""
        if self.curr_frame is None:
            return None
        ts = getattr(self.curr_frame, "timestamp", None)
        if ts is None:
            return None
        try:
            return self.scenario.timestamps.index(ts)
        except (ValueError, AttributeError):
            return None

    def run(self, frame):
        """
        Process a single frame and store result with timestamp.

        Args:
            frame: Frame object with timestamp attribute (int64 ns)
        """
        self.curr_frame = frame
        result = self.calculate()
        self.timestamps.append(frame.timestamp)
        self.values.append(result)

    def output(self) -> MetricTrace:
        """
        Return collected metrics as a MetricTrace.

        Initializes the trace with:
        - All collected timestamps and frame_values
        - Default segment covering entire scenario (first to last timestamp)
        - Empty source_monitors (will be set by DAGEvaluator)

        Returns:
            MetricTrace with timestamps, frame_values, and default segment
        """
        # Initialize default segment covering entire scenario
        segments = []
        if self.timestamps:
            # Create single segment spanning from first to last timestamp
            segments = [(self.timestamps[0], self.timestamps[-1])]

        return MetricTrace(
            timestamps=self.timestamps,
            frame_values=self.values,  # Renamed from 'values' to 'frame_values'
            segments=segments,  # Default segment for entire scenario
            source_monitors=[]  # Will be populated by DAGEvaluator
        )

    @abstractmethod
    def calculate(self):
        """
        Calculate metric for current frame.

        Subclasses must implement this to perform their unique calculation logic.
        Should return the metric value for the current frame.

        Returns:
            Metric value for current frame
        """
        pass
