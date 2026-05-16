"""DROID dataset converter for Hume.

Reads a DROID-100 chunk parquet (lerobot/droid_100 schema) and emits humex-compatible
scenario.pb / map.pb / robot.pb plus the bundled Franka URDF asset tree, one folder
per episode. The robot.pb sidecar is the new articulated-robot extension defined in
humex/robot.proto and is keyed by the same Object.id as the scenario's roster.
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


class DroidConverterError(Exception):
    """Exception raised for DROID conversion errors."""


def _bundled_franka_dir() -> Path:
    """Locate the URDF assets bundled inside the humex package."""
    pkg_root = resources.files("humex.converters")
    return Path(str(pkg_root)) / "assets" / "franka"


def _is_droid_parquet(path: Path) -> bool:
    """Heuristic: a parquet file with DROID-100 columns."""
    if path.suffix.lower() != ".parquet":
        return False
    try:
        # Read just metadata + 0 rows to inspect columns cheaply.
        head = pd.read_parquet(path, columns=["observation.state", "episode_index"])
        return len(head.columns) == 2
    except Exception:
        return False


class DroidConverter(BaseConverter):
    """Converter for DROID-100 chunk parquet files.

    Each chunk parquet may contain many episodes (DROID-100 ships 100 episodes
    in one file). Calling .convert() with `episode=None` writes every episode
    into its own subfolder; passing `episode=N` converts that one episode only.
    """

    def __init__(self, input_path: str | Path):
        super().__init__(input_path)
        if self.input_path.suffix.lower() != ".parquet":
            raise ValueError(f"Expected a .parquet file, got: {self.input_path.name}")

    @property
    def name(self) -> str:
        return "droid"

    def _list_episode_indices(self) -> list[int]:
        df = pd.read_parquet(self.input_path, columns=["episode_index"])
        return sorted(int(x) for x in df["episode_index"].unique())

    def convert(
        self,
        output_dir: Optional[str | Path] = None,
        episode: Optional[int] = None,
        **_: object,
    ) -> ConversionResult:
        """Convert one or all episodes in the chunk parquet.

        Args:
            output_dir: Where to write per-episode subfolders. Defaults to ./converted/.
            episode: If given, convert only that episode_index. Otherwise convert all.

        Returns:
            ConversionResult pointing at the *last* episode's outputs (or the only one).
            For batch runs, the per-episode files live under
            `<output_dir>/<source_stem>/episode_NNNN/`.
        """
        out_root = Path(output_dir or "converted")

        if episode is not None:
            episodes: Iterable[int] = [int(episode)]
        else:
            episodes = self._list_episode_indices()

        if not episodes:
            raise DroidConverterError(f"No episodes found in {self.input_path.name}")

        last_result: Optional[ConversionResult] = None
        for ep in episodes:
            last_result = self._convert_one_episode(ep, out_root)
        assert last_result is not None
        return last_result

    def _convert_one_episode(self, episode_index: int, out_root: Path) -> ConversionResult:
        from humex.converters.droid_robot_converter import DroidRobotConverter
        from humex.converters.droid_scenario_converter import DroidScenarioConverter

        source_stem = self.input_path.stem  # e.g. "file-000"
        ep_folder = out_root / source_stem / f"episode_{episode_index:04d}"
        ep_folder.mkdir(parents=True, exist_ok=True)

        try:
            scenario_pb, map_pb = DroidScenarioConverter(
                self.input_path, episode_index=episode_index
            ).convert_to_proto()
            robot_pb = DroidRobotConverter(
                self.input_path, episode_index=episode_index
            ).convert_to_proto()

            scenario_bytes = scenario_pb.SerializeToString()
            map_bytes = map_pb.SerializeToString()
            robot_bytes = robot_pb.SerializeToString()

            scenario_path = ep_folder / "scenario.pb"
            map_path = ep_folder / "map.pb"
            robot_path = ep_folder / "robot.pb"
            scenario_path.write_bytes(scenario_bytes)
            map_path.write_bytes(map_bytes)
            robot_path.write_bytes(robot_bytes)

            # Copy bundled URDF + meshes into per-episode robots/franka/.
            urdf_src = _bundled_franka_dir()
            urdf_dst = ep_folder / "robots" / "franka"
            if urdf_dst.exists():
                shutil.rmtree(urdf_dst)
            shutil.copytree(urdf_src, urdf_dst)

            meta = {
                "format_version": FORMAT_VERSION,
                "scenario_name": f"droid_episode_{episode_index:04d}",
                "source_file": self.input_path.name,
                "converted_at": datetime.now().isoformat(),
                "converter": "droid",
                "format": "split",
                "duration": scenario_pb.duration,
                "frequency": scenario_pb.frequency,
                "num_frames": len(scenario_pb.frames),
                "ego_id": scenario_pb.ego_id,
                "episode_index": episode_index,
                "robot_count": len(robot_pb.roster),
                "robot_dof": len(next(iter(robot_pb.roster.values())).joint_names),
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
            raise DroidConverterError(
                f"DROID conversion failed for episode {episode_index} "
                f"of {self.input_path.name}: {type(e).__name__}: {e}"
            ) from e
