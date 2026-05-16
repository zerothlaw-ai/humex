"""Longitudinal jerk monitor for ego vehicle.

Calculates the rate of change of longitudinal acceleration (jerk) for the
ego vehicle. Uses 2D projection in the ground plane.

Uses a Savitzky-Golay filter to simultaneously smooth the acceleration signal
and compute its derivative (jerk) in a single step. This is the industry-standard
approach for computing jerk from noisy discrete sensor data, avoiding the noise
amplification that occurs when chaining separate smoothing and differentiation.

The window size is specified in seconds (default 0.5s) and converted to frame
count at runtime based on actual timestamps, so it behaves consistently
regardless of the scenario's sampling frequency.
"""

from collections import deque

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.timestamp import to_seconds
import numpy as np
from scipy.signal import savgol_coeffs

_WINDOW_SECONDS = 1.0  # Smoothing window duration (1s balances noise vs responsiveness)
_MIN_WINDOW = 7        # Minimum frames for SG filter (cubic needs >= 4)
_POLYORDER = 3         # Cubic polynomial for SG fit


class EgoLonJerk(MonitorBase):
    """Monitor for calculating ego vehicle longitudinal jerk.

    OUTPUT_TYPE: FLOAT

    Jerk is the 1st derivative of longitudinal acceleration, computed via
    Savitzky-Golay filter (cubic polynomial, 0.5s window). The SG filter
    fits a polynomial to the buffered acceleration samples and analytically
    differentiates it, producing a smoothed derivative in one step.
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)
        self._accel_buf: list[float] = []   # raw lon_accel values
        self._ts_buf: list[int] = []        # timestamps (nanoseconds)
        self._window_frames: int | None = None  # computed from actual dt
        self._sg_coeffs: np.ndarray | None = None

    def _init_filter(self):
        """Compute window size and SG coefficients from actual sample rate."""
        if len(self._ts_buf) < 2:
            return
        # Estimate dt from median of consecutive timestamp differences
        dts = [to_seconds(self._ts_buf[i+1] - self._ts_buf[i])
               for i in range(len(self._ts_buf) - 1)]
        dt = float(np.median(dts))
        if dt < 1e-6:
            return

        window = max(_MIN_WINDOW, int(round(_WINDOW_SECONDS / dt)))
        if window % 2 == 0:
            window += 1  # SG requires odd window
        polyorder = min(_POLYORDER, window - 1)

        self._window_frames = window
        # SG coefficients for 1st derivative at the center of the window
        self._sg_coeffs = savgol_coeffs(window, polyorder, deriv=1, delta=dt)

    def calculate(self):
        """Calculate longitudinal jerk for current frame.

        Returns:
            float: Longitudinal jerk in m/s³, or None if ego absent
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        if ego is None:
            self._accel_buf.clear()
            self._ts_buf.clear()
            self._window_frames = None
            self._sg_coeffs = None
            return None

        accel = ego.sp.acceleration
        vel = ego.sp.velocity

        if accel.x is None or accel.y is None or vel.x is None or vel.y is None:
            self._accel_buf.clear()
            self._ts_buf.clear()
            self._window_frames = None
            self._sg_coeffs = None
            return 0.0

        velocity = np.array([vel.x, vel.y])
        acceleration = np.array([accel.x, accel.y])

        speed = np.linalg.norm(velocity)
        if speed < 1e-6:
            current_lon_accel = 0.0
        else:
            velocity_direction = velocity / speed
            current_lon_accel = float(np.dot(acceleration, velocity_direction))

        self._accel_buf.append(current_lon_accel)
        self._ts_buf.append(frame.timestamp)

        # Initialize filter once we have enough samples to estimate dt
        if self._sg_coeffs is None:
            if len(self._ts_buf) >= _MIN_WINDOW:
                self._init_filter()
            if self._sg_coeffs is None:
                return 0.0

        # Wait until buffer has enough frames
        if len(self._accel_buf) < self._window_frames:
            return 0.0

        # Keep only the last window_frames samples
        if len(self._accel_buf) > self._window_frames:
            self._accel_buf = self._accel_buf[-self._window_frames:]
            self._ts_buf = self._ts_buf[-self._window_frames:]

        # SG derivative: dot product of coefficients with the buffered values
        jerk = float(np.dot(self._sg_coeffs, self._accel_buf))
        return jerk
