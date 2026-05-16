"""Waymo Open Dataset converter for Hume."""

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from humex.converters.base import BaseConverter, ConversionResult


class WaymoConverterError(Exception):
    """Exception raised for Waymo conversion errors."""

    pass


FORMAT_VERSION = "0.3.0"


class WaymoConverter(BaseConverter):
    """Converter for Waymo Open Dataset TFRecord files.

    Ships as the standalone ``humex-converter-waymo`` package — install
    alongside ``humex`` to enable. The TF / waymo-open-dataset deps live
    here and are never pulled into a clean ``humex`` install.
    """

    # Recognised file shapes:
    #   regular: foo.tfrecord
    #   sharded: foo.tfrecord-00031-of-01000
    # The substring form (no leading dot) lets BaseConverter.can_handle
    # pick up both via its name-contains fallback.
    EXTENSIONS = (".tfrecord", "tfrecord")

    def __init__(self, input_path: str | Path):
        """Initialize the Waymo converter.

        Args:
            input_path: Path to a Waymo TFRecord scenario file.

        Raises:
            FileNotFoundError: If the input file does not exist.
            ValueError: If the file is not a TFRecord file.
        """
        super().__init__(input_path)
        if not self.can_handle(self.input_path):
            raise ValueError(
                f"Expected a .tfrecord file, got: {self.input_path.name}"
            )

    @property
    def name(self) -> str:
        """Return the name of the converter."""
        return "waymo"

    def _check_dependencies(self) -> None:
        """Check if required dependencies are available."""
        try:
            from waymo_open_dataset.protos import scenario_pb2  # noqa: F401
        except ImportError as e:
            raise WaymoConverterError(
                "Waymo conversion requires the waymo-open-dataset package. "
                "Install with: pip install humex-converter-waymo"
            ) from e

    def convert(
        self,
        output_dir: Optional[str | Path] = None,
        ego_id: Optional[int] = None,
    ) -> ConversionResult:
        """Convert a Waymo TFRecord file to humex-compatible format.

        This produces in a subfolder named after the input file:
        - scenario.pb: ScenarioData protobuf
        - map.pb: Map protobuf
        - signal.pb: SignalData protobuf
        - meta.json: Metadata (name, duration, frequency, ego_id, etc.)

        Args:
            output_dir: Directory to write output files. Defaults to
                the 'output' folder in the repo root.
            ego_id: Optional ID of the ego vehicle. If not specified,
                the converter will use a default selection.

        Returns:
            ConversionResult with paths to generated files.

        Raises:
            WaymoConverterError: If conversion fails or dependencies are missing.
        """
        self._check_dependencies()

        from humex_converter_waymo.map_converter import WaymoMapConverter
        from humex_converter_waymo.scenario_converter import WaymoScenarioConverter

        # Generate UUID for this conversion
        conversion_uuid = str(uuid.uuid4())[:8]

        # Extract scenario name from filename
        filename = self.input_path.name
        scenario_name = filename.split(".tfrecord")[0]

        # Determine output directory and create subfolder
        if output_dir is None:
            output_dir = Path("converted")
        subfolder = Path(output_dir) / scenario_name
        subfolder.mkdir(parents=True, exist_ok=True)

        try:
            # Convert scenario and signals (get protobuf objects)
            scenario_converter = WaymoScenarioConverter(str(self.input_path))
            scenario_pb, signal_pb = scenario_converter.convert_to_proto(
                ego_id=ego_id,
            )

            # Convert map (get protobuf object)
            map_converter = WaymoMapConverter(str(self.input_path))
            map_pb = map_converter.convert_to_proto(
                conversion_uuid=conversion_uuid,
            )

            # Write scenario.pb
            scenario_path = subfolder / "scenario.pb"
            scenario_bytes = scenario_pb.SerializeToString()
            with open(scenario_path, "wb") as f:
                f.write(scenario_bytes)

            # Write map.pb
            map_path = subfolder / "map.pb"
            map_bytes = map_pb.SerializeToString()
            with open(map_path, "wb") as f:
                f.write(map_bytes)

            # Write signal.pb
            signal_path = subfolder / "signal.pb"
            signal_bytes = signal_pb.SerializeToString()
            with open(signal_path, "wb") as f:
                f.write(signal_bytes)

            # Compute SHA256 hashes
            scenario_sha256 = hashlib.sha256(scenario_bytes).hexdigest()
            map_sha256 = hashlib.sha256(map_bytes).hexdigest()
            signal_sha256 = hashlib.sha256(signal_bytes).hexdigest()

            # Write meta.json with scenario metadata
            meta = {
                "format_version": FORMAT_VERSION,
                "scenario_name": scenario_name,
                "source_file": self.input_path.name,
                "converted_at": datetime.now().isoformat(),
                "converter": "waymo",
                "format": "split",
                "duration": scenario_pb.duration,
                "frequency": scenario_pb.frequency,
                "ego_id": scenario_pb.ego_id,
                "files": {
                    "scenario": scenario_path.name,
                    "map": map_path.name,
                    "signal": signal_path.name,
                },
                "sha256": {
                    "scenario": scenario_sha256,
                    "map": map_sha256,
                    "signal": signal_sha256,
                },
            }
            with open(subfolder / "meta.json", "w") as f:
                json.dump(meta, f, indent=2)

            return ConversionResult(
                scenario_path=scenario_path,
                map_path=map_path,
                signal_path=signal_path,
            )

        except Exception as e:
            raise WaymoConverterError(
                f"Conversion failed for {self.input_path.name}: "
                f"{type(e).__name__}: {e}"
            ) from e

    def validate_input(self) -> bool:
        """Validate the Waymo TFRecord file.

        Returns:
            True if the file appears to be a valid Waymo TFRecord.

        Raises:
            ValueError: If the file is not a valid TFRecord.
        """
        # Basic validation - check file extension and existence
        if not self.input_path.exists():
            raise ValueError(f"File not found: {self.input_path}")

        if not self._is_tfrecord_file(self.input_path):
            raise ValueError(f"Not a TFRecord file: {self.input_path}")

        # Check file is not empty
        if self.input_path.stat().st_size == 0:
            raise ValueError(f"Empty file: {self.input_path}")

        return True
