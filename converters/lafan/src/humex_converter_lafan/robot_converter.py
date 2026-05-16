"""LAFAN1 robot converter — builds robot.pb from one H1 sequence.

The LAFAN1 retargeted CSV stores 19 joint angles per frame (cols 7..25) in the
order Unitree's `h1.urdf` declares them (URDF parser sees these in order):

    0  left_hip_yaw_joint
    1  left_hip_roll_joint
    2  left_hip_pitch_joint
    3  left_knee_joint
    4  left_ankle_joint
    5  right_hip_yaw_joint
    6  right_hip_roll_joint
    7  right_hip_pitch_joint
    8  right_knee_joint
    9  right_ankle_joint
   10  torso_joint
   11  left_shoulder_pitch_joint
   12  left_shoulder_roll_joint
   13  left_shoulder_yaw_joint
   14  left_elbow_joint
   15  right_shoulder_pitch_joint
   16  right_shoulder_roll_joint
   17  right_shoulder_yaw_joint
   18  right_elbow_joint
"""

from pathlib import Path

import numpy as np
import pandas as pd

from humex.proto import robot_pb2

EGO_ID = 1
URDF_PATH_RELATIVE = "robots/h1/h1.urdf"
DISPLAY_NAME = "Unitree H1"

# LAFAN1 retargeted motions are sampled at 30 Hz.
LAFAN_FPS = 30.0

H1_JOINT_NAMES = [
    "left_hip_yaw_joint",
    "left_hip_roll_joint",
    "left_hip_pitch_joint",
    "left_knee_joint",
    "left_ankle_joint",
    "right_hip_yaw_joint",
    "right_hip_roll_joint",
    "right_hip_pitch_joint",
    "right_knee_joint",
    "right_ankle_joint",
    "torso_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
]


class LafanRobotConverter:
    """Build robot.pb for a single LAFAN1 H1 sequence."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)

    def convert_to_proto(self) -> robot_pb2.RobotData:
        df = pd.read_csv(self.csv_path, header=None)
        if df.shape[1] != 26:
            raise ValueError(
                f"expected 26 columns in {self.csv_path.name}, got {df.shape[1]}"
            )
        joint_arr = df.iloc[:, 7:].to_numpy()  # (N, 19)
        if joint_arr.shape[1] != len(H1_JOINT_NAMES):
            raise ValueError(
                f"expected {len(H1_JOINT_NAMES)} joint columns, got {joint_arr.shape[1]}"
            )
        n_frames = joint_arr.shape[0]
        ts_ns = (np.arange(n_frames) * (1e9 / LAFAN_FPS)).astype(np.int64)

        robot = robot_pb2.RobotData()
        desc = robot.roster[EGO_ID]
        desc.object_id = EGO_ID
        desc.urdf_path = URDF_PATH_RELATIVE
        desc.joint_names.extend(H1_JOINT_NAMES)
        desc.display_name = DISPLAY_NAME

        for k in range(n_frames):
            ts = int(ts_ns[k])
            rfr = robot.frames[str(ts)]
            rfr.timestamp = ts
            rs = rfr.robot_list[EGO_ID]
            rs.object_id = EGO_ID
            rs.joint_positions.extend(joint_arr[k].astype(np.float64).tolist())

        return robot
