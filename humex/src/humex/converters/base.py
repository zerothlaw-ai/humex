"""Base converter interface for data format conversion."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


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
