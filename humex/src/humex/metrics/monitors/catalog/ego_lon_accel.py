"""Longitudinal acceleration monitor for ego vehicle.

Calculates the longitudinal (along velocity) component of the ego
vehicle's acceleration vector. Uses 2D projection in the ground plane.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
import numpy as np


class EgoLonAccel(MonitorBase):
    """Monitor for calculating ego vehicle longitudinal acceleration.

    OUTPUT_TYPE: FLOAT

    Projects the ego's acceleration vector onto the velocity direction in the
    2D ground plane. Positive values indicate acceleration (speeding up),
    negative values indicate braking.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate longitudinal acceleration for current frame.

        Returns:
            float: Longitudinal acceleration in m/s² (signed), or None if ego absent
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        if ego is None:
            return None

        accel = ego.sp.acceleration
        vel = ego.sp.velocity

        if accel.x is None or accel.y is None or vel.x is None or vel.y is None:
            return 0.0

        velocity = np.array([vel.x, vel.y])
        acceleration = np.array([accel.x, accel.y])

        speed = np.linalg.norm(velocity)
        if speed < 1e-6:
            return 0.0

        velocity_direction = velocity / speed
        lon_accel = np.dot(acceleration, velocity_direction)

        return float(lon_accel)
