"""DROID robot converter — builds robot.pb from one episode's joint trajectory.

Maps DROID `observation.state` (motor_0..motor_6, 7-DOF Franka arm) to
`panda_joint1..panda_joint7` and produces a `RobotData` proto with one
RobotDescription + one RobotState per frame, packed and keyed by Object.id.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from humex.proto import robot_pb2

EGO_ID = 1
JOINT_NAMES = [f"panda_joint{i + 1}" for i in range(7)]
URDF_PATH_RELATIVE = "robots/franka/panda.urdf"
DISPLAY_NAME = "Franka Panda"

_REQUIRED_COLUMNS = ("observation.state", "timestamp", "episode_index", "frame_index")


class DroidRobotConverter:
    """Build robot.pb for a single DROID episode."""

    def __init__(self, parquet_path: str | Path, episode_index: int = 0):
        self.parquet_path = Path(parquet_path)
        self.episode_index = int(episode_index)

    def convert_to_proto(self) -> robot_pb2.RobotData:
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

        states = np.stack(ep["observation.state"].to_numpy())  # (N, 7)
        if states.shape[1] != len(JOINT_NAMES):
            raise ValueError(
                f"expected {len(JOINT_NAMES)}-DOF observation.state, got shape {states.shape}"
            )
        ts_sec = ep["timestamp"].to_numpy().astype(np.float64)
        ts_sec = ts_sec - ts_sec[0]
        ts_ns = (ts_sec * 1e9).astype(np.int64)

        robot = robot_pb2.RobotData()
        desc = robot.roster[EGO_ID]
        desc.object_id = EGO_ID
        desc.urdf_path = URDF_PATH_RELATIVE
        desc.joint_names.extend(JOINT_NAMES)
        desc.display_name = DISPLAY_NAME

        for k in range(len(ep)):
            ts = int(ts_ns[k])
            rfr = robot.frames[str(ts)]
            rfr.timestamp = ts
            rs = rfr.robot_list[EGO_ID]
            rs.object_id = EGO_ID
            rs.joint_positions.extend(states[k].astype(np.float64).tolist())

        return robot
