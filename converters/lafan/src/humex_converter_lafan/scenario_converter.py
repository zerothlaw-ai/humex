"""LAFAN1 scenario converter.

Reads one Unitree H1 retargeted motion sequence (CSV) and emits an humex-compatible
ScenarioData carrying the **per-frame base pose** of the humanoid pelvis (xyz +
yaw extracted from the quaternion). Joints come from `lafan_robot_converter`;
this file only handles the base.

The CSV layout (no header, 26 columns):
   col 0..2  : base position (x, y, z) — meters, Z-up
   col 3..6  : base orientation quaternion (qx, qy, qz, qw)
   col 7..25 : 19 joint angles in radians (consumed by the robot converter)
"""

import math
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from humex.proto import map_pb2, scenario_pb2

# LAFAN1 retargeted motions are sampled at 30 Hz (Ubisoft mocap origin).
LAFAN_FPS = 30.0

# Standing H1 ~1.8 m tall, ~0.6 m wide; used for the bbox/dimensions on the
# scenario.Object — the URDF replaces the box geometry in 3D anyway.
EGO_ID = 1
H1_LENGTH = 0.6
H1_WIDTH = 0.6
H1_HEIGHT = 1.8

MAP_NAME = "lafan_floor"


def _quat_xyzw_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """Extract Z-axis yaw from a quaternion (ZYX intrinsic Euler decomposition).

    LAFAN data has small roll/pitch (humanoid stays upright), so yaw is the
    only base rotation that matters for visualization. Future work could
    plumb the full quaternion through scenario.Statepoint.heading.
    """
    return math.atan2(
        2.0 * (qw * qz + qx * qy),
        1.0 - 2.0 * (qy * qy + qz * qz),
    )


class LafanScenarioConverter:
    """Build scenario.pb + map.pb for a single LAFAN1 H1 sequence."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)

    def _load_sequence(self) -> np.ndarray:
        df = pd.read_csv(self.csv_path, header=None)
        if df.shape[1] != 26:
            raise ValueError(
                f"expected 26 columns in {self.csv_path.name}, got {df.shape[1]}"
            )
        return df.to_numpy()

    def convert_to_proto(
        self,
    ) -> Tuple[scenario_pb2.ScenarioData, map_pb2.Map]:
        arr = self._load_sequence()
        n_frames = arr.shape[0]
        # Synthesize timestamps at LAFAN_FPS — the CSV doesn't ship them.
        ts_ns = (np.arange(n_frames) * (1e9 / LAFAN_FPS)).astype(np.int64)
        # humex's Scenario pre-allocates int(duration * fps) slots; report
        # n_frames/fps so all slots survive the loader.
        duration = n_frames / LAFAN_FPS

        scenario = scenario_pb2.ScenarioData()
        scenario.frequency = LAFAN_FPS
        scenario.duration = duration
        scenario.map_name = MAP_NAME
        scenario.ego_id = EGO_ID

        roster_obj = scenario.roster[EGO_ID]
        roster_obj.id = EGO_ID
        roster_obj.length = H1_LENGTH
        roster_obj.width = H1_WIDTH
        roster_obj.height = H1_HEIGHT
        roster_obj.is_ego = True
        roster_obj.object_type = "humanoid"

        for k in range(n_frames):
            row = arr[k]
            x, y, z = float(row[0]), float(row[1]), float(row[2])
            qx, qy, qz, qw = float(row[3]), float(row[4]), float(row[5]), float(row[6])
            yaw = _quat_xyzw_to_yaw(qx, qy, qz, qw)

            ts = int(ts_ns[k])
            fr = scenario.frames[str(ts)]
            fr.timestamp = ts

            fobj = fr.obj_list[EGO_ID]
            fobj.id = EGO_ID
            fobj.length = H1_LENGTH
            fobj.width = H1_WIDTH
            fobj.height = H1_HEIGHT
            fobj.is_ego = True
            fobj.object_type = "humanoid"
            fobj.sp.position.x = x
            fobj.sp.position.y = y
            fobj.sp.position.z = z
            fobj.sp.heading.yaw = yaw

        map_msg = map_pb2.Map()
        road_map.name = MAP_NAME
        road_map.map_data.map_name = MAP_NAME
        road_map.map_data.version = 1.0

        return scenario, road_map
