"""LAFAN1 (Unitree H1) dataset converter for Hume.

Reads one or more retargeted motion CSVs from
`lvhaidong/LAFAN1_Retargeting_Dataset` (or unitreerobotics' gated mirror) and
emits scenario.pb / map.pb / robot.pb plus the bundled H1 URDF tree.

Each CSV is one motion sequence (~minutes of mocap). The converter treats
each CSV as one "episode" — so a single .csv input produces one episode dir
named `episode_<csv_stem>/`, e.g. `episode_walk1_subject1/`.
"""

import hashlib
import json
import shutil
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from humex.converters.base import BaseConverter, ConversionResult

FORMAT_VERSION = "0.4.0"


class LafanConverterError(Exception):
    """Exception raised for LAFAN conversion errors."""


def _bundled_h1_dir() -> Path:
    """Locate the bundled H1 URDF assets inside this plugin."""
    pkg_root = resources.files("humex_converter_lafan")
    return Path(str(pkg_root)) / "assets"


def is_lafan_csv(path: Path) -> bool:
    """Heuristic: a CSV with the LAFAN1 H1 schema (26 columns, no header).

    Cheap to invoke — reads only the first row.
    """
    if path.suffix.lower() != ".csv":
        return False
    try:
        head = pd.read_csv(path, header=None, nrows=1)
        return head.shape[1] == 26
    except Exception:
        return False


class LafanConverter(BaseConverter):
    """Converter for LAFAN1 retargeted Unitree H1 motion sequences.

    Accepts either a single .csv (one motion) or a directory of them. Each
    becomes its own episode in the output.
    """

    # Many CSV formats coexist in the wild — ``.csv`` alone over-matches.
    # We override can_handle below to confirm the LAFAN1-H1 column count
    # before claiming the file.
    EXTENSIONS = (".csv",)

    @classmethod
    def can_handle(cls, path: Path) -> bool:
        return is_lafan_csv(path)

    def __init__(self, input_path: str | Path):
        super().__init__(input_path)
        if self.input_path.is_file() and self.input_path.suffix.lower() != ".csv":
            raise ValueError(f"Expected a .csv file, got: {self.input_path.name}")

    @property
    def name(self) -> str:
        return "lafan"

    def _list_csvs(self) -> list[Path]:
        if self.input_path.is_file():
            return [self.input_path]
        # Directory: find all CSVs that look like LAFAN sequences.
        return sorted(p for p in self.input_path.rglob("*.csv") if is_lafan_csv(p))

    def convert(
        self,
        output_dir: Optional[str | Path] = None,
        **_: object,
    ) -> ConversionResult:
        out_root = Path(output_dir or "converted")
        csvs: Iterable[Path] = self._list_csvs()
        if not csvs:
            raise LafanConverterError(f"No LAFAN CSVs found at {self.input_path}")

        last: Optional[ConversionResult] = None
        for csv_path in csvs:
            last = self._convert_one_csv(csv_path, out_root)
        assert last is not None
        return last

    def _convert_one_csv(self, csv_path: Path, out_root: Path) -> ConversionResult:
        from humex_converter_lafan.robot_converter import LafanRobotConverter
        from humex_converter_lafan.scenario_converter import (
            LafanScenarioConverter,
        )

        # Source-stem: parent dir name (e.g. "h1") if input was a folder, else
        # the CSV's own stem. Per-episode folder named after the CSV stem.
        if self.input_path.is_dir():
            source_stem = self.input_path.name
        else:
            source_stem = self.input_path.parent.name or self.input_path.stem
        ep_name = f"episode_{csv_path.stem}"
        ep_folder = out_root / source_stem / ep_name
        ep_folder.mkdir(parents=True, exist_ok=True)

        try:
            scenario_pb, map_pb = LafanScenarioConverter(csv_path).convert_to_proto()
            robot_pb = LafanRobotConverter(csv_path).convert_to_proto()

            scenario_bytes = scenario_pb.SerializeToString()
            map_bytes = map_pb.SerializeToString()
            robot_bytes = robot_pb.SerializeToString()

            scenario_path = ep_folder / "scenario.pb"
            map_path = ep_folder / "map.pb"
            robot_path = ep_folder / "robot.pb"
            scenario_path.write_bytes(scenario_bytes)
            map_path.write_bytes(map_bytes)
            robot_path.write_bytes(robot_bytes)

            urdf_src = _bundled_h1_dir()
            urdf_dst = ep_folder / "robots" / "h1"
            if urdf_dst.exists():
                shutil.rmtree(urdf_dst)
            shutil.copytree(urdf_src, urdf_dst)

            num_frames = len(scenario_pb.frames)
            meta = {
                "format_version": FORMAT_VERSION,
                "scenario_name": ep_name,
                "source_file": csv_path.name,
                "converted_at": datetime.now().isoformat(),
                "converter": "lafan",
                "format": "split",
                "duration": scenario_pb.duration,
                "frequency": scenario_pb.frequency,
                "num_frames": num_frames,
                "ego_id": scenario_pb.ego_id,
                "robot_count": len(robot_pb.roster),
                "robot_dof": len(next(iter(robot_pb.roster.values())).joint_names),
                "robot_kind": "humanoid",
                "files": {
                    "scenario": scenario_path.name,
                    "map": map_path.name,
                    "robot": robot_path.name,
                },
                "sha256": {
                    "scenario": hashlib.sha256(scenario_bytes).hexdigest(),
                    "map": hashlib.sha256(map_bytes).hexdigest(),
                    "robot": hashlib.sha256(robot_bytes).hexdigest(),
                },
            }
            (ep_folder / "meta.json").write_text(json.dumps(meta, indent=2))

            return ConversionResult(
                scenario_path=scenario_path,
                map_path=map_path,
                robot_path=robot_path,
            )

        except Exception as e:
            raise LafanConverterError(
                f"LAFAN conversion failed for {csv_path.name}: "
                f"{type(e).__name__}: {e}"
            ) from e
