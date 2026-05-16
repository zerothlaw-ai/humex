"""Base converter interface for data format conversion.

Third-party converters subclass :class:`BaseConverter`, declare a
``humex.converters`` entry point in their package's ``pyproject.toml``,
and humex picks them up at runtime via :mod:`humex.converters.registry`.

Required on a subclass:

- ``name`` property — short identifier, used in CLI listings.
- ``can_handle(path)`` classmethod — true if this converter recognizes
  the file at ``path``. Default impl matches on file extension via the
  optional ``EXTENSIONS`` class attr; override for magic-bytes / header
  detection (LAFAN1 inspects the CSV column header, for example).
- ``convert(output_dir, **kwargs)`` — the actual work.

Optional:

- ``EXTENSIONS: tuple[str, ...]`` — class attr used by the default
  ``can_handle``. Lowercased, leading dot included (``(".tfrecord",)``).
- ``MIN_HUMEX_API_VERSION: int`` — minimum humex API version this
  converter supports. The registry skips converters whose minimum is
  higher than the installed ``humex.__api_version__`` with a clear
  warning, so a stale plugin doesn't crash a newer humex.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Optional


class ConversionResult:
    """Result of a data conversion operation."""

    def __init__(
        self,
        scenario_path: Optional[Path] = None,
        map_path: Optional[Path] = None,
        signal_path: Optional[Path] = None,
        robot_path: Optional[Path] = None,
        scenariounit_path: Optional[Path] = None,
    ):
        """Initialize conversion result.

        Args:
            scenario_path: Path to the generated scenario file (legacy).
            map_path: Path to the generated map file (legacy).
            signal_path: Path to the generated signal file (legacy).
            robot_path: Path to the generated robot file (articulated robots only).
            scenariounit_path: Path to the combined ScenarioUnit file.
        """
        self.scenario_path = scenario_path
        self.map_path = map_path
        self.signal_path = signal_path
        self.robot_path = robot_path
        self.scenariounit_path = scenariounit_path

    def __repr__(self) -> str:
        if self.scenariounit_path:
            return f"ConversionResult(scenariounit={self.scenariounit_path})"
        parts = [
            f"scenario={self.scenario_path}",
            f"map={self.map_path}",
            f"signal={self.signal_path}",
        ]
        if self.robot_path:
            parts.append(f"robot={self.robot_path}")
        return f"ConversionResult({', '.join(parts)})"

    def to_dict(self) -> dict[str, Optional[str]]:
        """Convert to dictionary with string paths."""
        result = {
            "scenario": str(self.scenario_path) if self.scenario_path else None,
            "map": str(self.map_path) if self.map_path else None,
            "signal": str(self.signal_path) if self.signal_path else None,
        }
        if self.robot_path:
            result["robot"] = str(self.robot_path)
        if self.scenariounit_path:
            result["scenariounit"] = str(self.scenariounit_path)
        return result


class BaseConverter(ABC):
    """Abstract base class for data format converters."""

    # Optional class attrs subclasses may set.
    EXTENSIONS: ClassVar[tuple[str, ...]] = ()
    MIN_HUMEX_API_VERSION: ClassVar[int] = 1

    def __init__(self, input_path: str | Path):
        """Initialize the converter.

        Args:
            input_path: Path to the input data file.

        Raises:
            FileNotFoundError: If the input file does not exist.
        """
        self.input_path = Path(input_path)
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the converter."""
        ...

    @property
    def source_name(self) -> str:
        """Extract a name from the input file for use in output filenames."""
        return self.input_path.stem

    @classmethod
    def can_handle(cls, path: Path) -> bool:
        """Return True if this converter recognizes ``path``.

        Default implementation matches on lowercase file extension against
        ``cls.EXTENSIONS``. Subclasses with more nuanced detection (magic
        bytes, header sniffing, directory layout) should override.
        """
        if not cls.EXTENSIONS:
            return False
        if not path.is_file():
            return False
        suffix = path.suffix.lower()
        if suffix in cls.EXTENSIONS:
            return True
        # Some formats have compound extensions ("foo.tfrecord-00000-of-00001"
        # ships as a TFRecord). Fall back to substring match on the name
        # when an extension entry doesn't start with a dot.
        name_lower = path.name.lower()
        return any(
            ext in name_lower for ext in cls.EXTENSIONS if not ext.startswith(".")
        )

    @abstractmethod
    def convert(
        self,
        output_dir: Optional[str | Path] = None,
        **kwargs,
    ) -> ConversionResult:
        """Convert the input data to humex-compatible format.

        Args:
            output_dir: Directory to write output files. Defaults to input file directory.
            **kwargs: Additional converter-specific arguments.

        Returns:
            ConversionResult with paths to generated files.
        """
        ...

    def validate_input(self) -> bool:
        """Validate the input file format.

        Returns:
            True if the input file is valid.

        Raises:
            ValueError: If the input file is not valid.
        """
        return True
