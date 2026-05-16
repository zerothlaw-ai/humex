"""DROID scenario converter.

Reads one episode from a DROID-100 chunk parquet and emits an humex-compatible
ScenarioData (with one stationary "ego" Object representing the robot's base)
plus a minimal Map that satisfies humex's loader, which requires a map file.
"""

from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from humex.proto import map_pb2, scenario_pb2

# DROID-100 chunk parquet schema columns we depend on.
_REQUIRED_COLUMNS = ("observation.state", "timestamp", "episode_index", "frame_index")

# Stationary ego — Franka is bolted to the table in DROID. Bbox is a coarse
# axis-aligned guess for the arm's standoff region.
EGO_ID = 1
BASE_LENGTH = 0.6
BASE_WIDTH = 0.6
BASE_HEIGHT = 1.2

MAP_NAME = "droid_franka_table"


class DroidScenarioConverter:
    """Build scenario.pb + map.pb for a single DROID episode."""

    def __init__(self, parquet_path: str | Path, episode_index: int = 0):
        self.parquet_path = Path(parquet_path)
        self.episode_index = int(episode_index)

    def _load_episode(self) -> pd.DataFrame:
        df = pd.read_parquet(self.parquet_path, columns=list(_REQUIRED_COLUMNS))
        ep = (
            df[df["episode_index"] == self.episode_index]
            .sort_values("frame_index")
            .reset_index(drop=True)
        )
        if len(ep) == 0:
            raise ValueError(
                f"no rows for episode_index={self.episode_index} in {self.parquet_path.name}"
            )
        return ep

    def convert_to_proto(
        self,
    ) -> Tuple[scenario_pb2.ScenarioData, map_pb2.Map]:
        """Build (scenario_pb, map_pb) for the episode.

        Returns:
            scenario_pb: ScenarioData with one stationary ego Object across all frames.
            map_pb: minimal Map (no lanes — DROID has no road network).
        """
        ep = self._load_episode()
        ts_sec = ep["timestamp"].to_numpy().astype(np.float64)
        ts_sec = ts_sec - ts_sec[0]  # normalize so t0 = 0
        ts_ns = (ts_sec * 1e9).astype(np.int64)
        n_frames = len(ep)
        span = float(ts_sec[-1])
        fps = (n_frames - 1) / span if span > 0 else 15.0
        # humex's Scenario.__init__ pre-allocates int(duration * frequency) frame
        # slots; report n_frames/fps so all frames survive load.
        duration = n_frames / fps

        scenario = scenario_pb2.ScenarioData()
        scenario.frequency = fps
        scenario.duration = duration
        scenario.map_name = MAP_NAME
        scenario.ego_id = EGO_ID

        roster_obj = scenario.roster[EGO_ID]
        roster_obj.id = EGO_ID
        roster_obj.length = BASE_LENGTH
        roster_obj.width = BASE_WIDTH
        roster_obj.height = BASE_HEIGHT
        roster_obj.is_ego = True
        roster_obj.object_type = "robot"

        for k in range(n_frames):
            ts = int(ts_ns[k])
            fr = scenario.frames[str(ts)]
            fr.timestamp = ts
            fobj = fr.obj_list[EGO_ID]
            fobj.id = EGO_ID
            fobj.length = BASE_LENGTH
            fobj.width = BASE_WIDTH
            fobj.height = BASE_HEIGHT
            fobj.is_ego = True
            fobj.object_type = "robot"
            # Base stays at origin; statepoint defaults are zero.

        map_msg = map_pb2.Map()
        road_map.name = MAP_NAME
        road_map.map_data.map_name = MAP_NAME
        road_map.map_data.version = 1.0

        return scenario, road_map

    def episode_count(self) -> int:
        """How many episodes live in this parquet."""
        df = pd.read_parquet(self.parquet_path, columns=["episode_index"])
        return int(df["episode_index"].nunique())
