"""Lateral acceleration monitor for ego vehicle.

Calculates the lateral (perpendicular to velocity) component of the ego
vehicle's acceleration vector. Uses 2D projection in the ground plane.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
import numpy as np


class EgoLatAccel(MonitorBase):
    """Monitor for calculating ego vehicle lateral acceleration.

    OUTPUT_TYPE: FLOAT

    Decomposes the ego's acceleration vector into longitudinal (along velocity)
    and lateral (perpendicular to velocity) components in the 2D ground plane,
    and returns the magnitude of the lateral component in m/s².
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        """Calculate lateral acceleration for current frame.

        Returns:
            float: Lateral acceleration magnitude in m/s², or None if ego absent
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
        lat_accel_vector = acceleration - lon_accel * velocity_direction

        return float(np.linalg.norm(lat_accel_vector))
