"""Smart keyframe behavior with physics-based trajectory generation.

This module provides SmartKeyframeBehavior that uses a closed-loop control
simulation with BicycleModel, Pure Pursuit, and PID to generate realistic
vehicle trajectories that follow keystate waypoints.
"""

import math
import numpy as np
from typing import List, Optional, Tuple
from .behavior_base import BaseBehavior
from ...components.statepoint import StatePoint
from ...utils.timestamp import to_ns
from ..vehicle.models import BicycleModel
from ..vehicle.controllers import PID


class SmartKeyframeBehavior(BaseBehavior):
    """Behavior handler using BicycleModel + PurePursuit + PID control.

    Generates trajectories by simulating vehicle dynamics:
    - Keystates define target waypoints and speeds
    - Pure Pursuit computes steering to follow keystate path
    - PID controls speed toward next keystate's target speed
    - BicycleModel propagates physics each frame

    Unlike KeyframeBehavior which uses Hermite spline interpolation to
    guarantee exact positions at keystates, this behavior produces more
    realistic vehicle motion that respects physical constraints.
    """

    def __init__(self, keystates: List[StatePoint], scenario, obj_id: int = None,
                 speed_controller: str = 'kinematics',
                 heading_controller: str = 'pure_pursuit',
                 turning_radius: float = 6.0):
        """Initialize SmartKeyframeBehavior.

        Args:
            keystates: List of StatePoints defining target waypoints and speeds
            scenario: Parent scenario for timing information
            obj_id: Object ID for generated StatePoints
            speed_controller: Speed control mode - 'kinematics' for SUVAT constant
                acceleration per segment, 'pid' for PID-based speed control
            heading_controller: Heading control mode - 'pure_pursuit' for linear
                path with Pure Pursuit tracking, 'dubins' for Dubins curve path
            turning_radius: Dubins minimum turning radius in meters (only used
                when heading_controller='dubins')
        """
        super().__init__(keystates, scenario, obj_id)
        self.speed_controller = speed_controller
        self.heading_controller = heading_controller
        self.turning_radius = turning_radius
        self.keystate_times: List[int] = []
        self.segment_accelerations: List[float] = []
        self.segment_distances: List[float] = []
        self.segment_start_speeds: List[float] = []
        self._dubins_path_points: List[Tuple[float, float, float]] = []

        if self.keystates and self.scenario:
            self._validate_keystates()
            self._calculate_keystate_times()
            self._initialize_controllers()
            if self.speed_controller == 'kinematics':
                self._precompute_kinematics()
            self._simulate_trajectory()

    def _validate_keystates(self):
        """Validate keystate format and content."""
        if not self.keystates:
            raise ValueError("SmartKeyframeBehavior requires at least one keystate")

        for i, keystate in enumerate(self.keystates):
            if not isinstance(keystate, StatePoint):
                raise ValueError(f"Keystate {i} must be a StatePoint")

    def _calculate_keystate_times(self):
        """Calculate timestamps for each keystate based on distance/velocity.

        Uses physics: time = distance / avg_velocity to determine when
        the vehicle should arrive at each keystate position.
        When heading_controller='dubins', uses Dubins arc lengths instead of
        Euclidean distances.
        """
        if not self.keystates:
            return

        if len(self.keystates) == 1:
            self.keystate_times = [0]
            return

        # Pre-compute Dubins segments if needed (used by both time calc and path building)
        dubins_segments = None
        if self.heading_controller == 'dubins':
            from ...utils.dubins_utils import compute_all_dubins_segments
            poses = [StatePoint.to_dubins_point(ks) for ks in self.keystates]
            dubins_segments = compute_all_dubins_segments(poses, self.turning_radius)
            # Cache Dubins path points for trajectory simulation
            self._dubins_path_points = []
            for seg in dubins_segments:
                self._dubins_path_points.extend(seg['sample_points'])
            # Add final point if not already included
            if self._dubins_path_points:
                last_pose = poses[-1]
                last_cached = self._dubins_path_points[-1]
                if (abs(last_cached[0] - last_pose[0]) > 0.1 or
                        abs(last_cached[1] - last_pose[1]) > 0.1):
                    self._dubins_path_points.append(last_pose)

        calculated_times = [0]

        for i in range(1, len(self.keystates)):
            prev_state = self.keystates[i - 1]
            curr_state = self.keystates[i]

            # Use Dubins arc length or Euclidean distance
            if dubins_segments is not None:
                distance = dubins_segments[i - 1]['path_length']
            else:
                prev_pos = prev_state.position.to_tuple()
                curr_pos = curr_state.position.to_tuple()
                distance = math.sqrt(sum((curr - prev) ** 2 for curr, prev in zip(curr_pos, prev_pos)))

            prev_vel = prev_state.velocity.to_tuple()
            curr_vel = curr_state.velocity.to_tuple()
            prev_speed = math.sqrt(sum(v ** 2 for v in prev_vel))
            curr_speed = math.sqrt(sum(v ** 2 for v in curr_vel))
            avg_speed = (prev_speed + curr_speed) / 2.0

            if avg_speed > 1e-6:
                time_interval = distance / avg_speed
            else:
                time_interval = 1.0

            calculated_times.append(calculated_times[-1] + to_ns(time_interval))

        self.keystate_times = calculated_times

        if self.scenario and hasattr(self.scenario, 'duration'):
            max_time_ns = max(calculated_times)
            duration_ns = to_ns(self.scenario.duration)
            if max_time_ns > duration_ns:
                scale_factor = duration_ns / max_time_ns
                self.keystate_times = [int(t * scale_factor) for t in calculated_times]

    def _initialize_controllers(self):
        """Initialize BicycleModel, PID (if needed), and Pure Pursuit parameters."""
        self.bicycle_model = BicycleModel(self.scenario)

        # PID for speed control (only needed in pid mode)
        if self.speed_controller == 'pid':
            self.speed_pid = PID(interval=self.scenario.interval)
            self.speed_pid.set_gains(k_p=0.5, k_i=0.1, k_d=0.05)

        # Pure Pursuit parameters
        self.look_ahead_time = 0.5  # seconds
        self.wheel_dist = 2.0  # meters (vehicle wheelbase)

    def _precompute_kinematics(self):
        """Pre-compute constant acceleration for each keystate segment using SUVAT.

        Uses a = (vf² - v0²) / (2s) per segment. When heading_controller='dubins',
        uses Dubins arc lengths for accurate distance computation.
        """
        from ...utils.physics_helper import kinematic_acceleration_from_velocities_and_displacement

        # Get Dubins arc lengths if available
        dubins_arc_lengths = None
        if self.heading_controller == 'dubins' and self._dubins_path_points:
            from ...utils.dubins_utils import compute_all_dubins_segments
            poses = [StatePoint.to_dubins_point(ks) for ks in self.keystates]
            dubins_segments = compute_all_dubins_segments(poses, self.turning_radius)
            dubins_arc_lengths = [seg['path_length'] for seg in dubins_segments]

        for i in range(len(self.keystates) - 1):
            if dubins_arc_lengths is not None:
                distance = dubins_arc_lengths[i]
            else:
                p0 = self.keystates[i].position.to_tuple()
                p1 = self.keystates[i + 1].position.to_tuple()
                distance = math.sqrt(sum((b - a) ** 2 for a, b in zip(p0, p1)))

            v0 = self.keystates[i].velocity.norm()
            vf = self.keystates[i + 1].velocity.norm()

            if distance > 1e-6:
                accel = kinematic_acceleration_from_velocities_and_displacement(v0, vf, distance)
            else:
                accel = 0.0

            self.segment_distances.append(distance)
            self.segment_start_speeds.append(v0)
            self.segment_accelerations.append(accel)

    def _get_kinematic_speed(self, timestamp: int, current_state: StatePoint) -> float:
        """Compute speed from SUVAT kinematics: v = sqrt(v0² + 2·a·d_traveled).

        Finds the current segment based on timestamp, then computes the
        expected speed given the distance traveled from the segment start.

        Args:
            timestamp: Current timestamp in nanoseconds
            current_state: Current vehicle state (for position)

        Returns:
            Target speed in m/s
        """
        # Find which segment we're in
        segment_idx = 0
        for i in range(len(self.keystate_times) - 1):
            if self.keystate_times[i] <= timestamp < self.keystate_times[i + 1]:
                segment_idx = i
                break
        else:
            segment_idx = max(0, len(self.keystate_times) - 2)

        if segment_idx >= len(self.segment_accelerations):
            return self.keystates[-1].velocity.norm()

        v0 = self.segment_start_speeds[segment_idx]
        accel = self.segment_accelerations[segment_idx]

        # Distance traveled from segment start position
        seg_start = self.keystates[segment_idx].position.to_tuple()
        curr = (current_state.position.x, current_state.position.y, 0.0)
        d_traveled = min(
            math.sqrt(sum((c - s) ** 2 for c, s in zip(curr, seg_start))),
            self.segment_distances[segment_idx]
        )

        return math.sqrt(max(0.0, v0 ** 2 + 2 * accel * d_traveled))

    def _build_trajectory_path(self) -> List[Tuple[float, float, float]]:
        """Build dense path from keystates for tracking.

        When heading_controller='dubins': uses pre-computed Dubins path points.
        When heading_controller='pure_pursuit': creates linear interpolation
        between keystates (approximately every 1 meter) for Pure Pursuit.

        Returns:
            List of (x, y, z) points along the keystate trajectory
        """
        if self.heading_controller == 'dubins' and self._dubins_path_points:
            # Convert Dubins (x, y, yaw) points to (x, y, z) path
            return [(pt[0], pt[1], 0.0) for pt in self._dubins_path_points]

        # Pure pursuit: linear interpolation between keystates
        path = []
        for i in range(len(self.keystates) - 1):
            p0 = self.keystates[i].position.to_tuple()
            p1 = self.keystates[i + 1].position.to_tuple()

            # Calculate distance and number of intermediate points
            dist = math.sqrt(sum((b - a) ** 2 for a, b in zip(p0, p1)))
            num_points = max(2, int(dist / 1.0))  # ~1 meter spacing

            for j in range(num_points):
                t = j / num_points
                point = tuple(p0[k] + t * (p1[k] - p0[k]) for k in range(3))
                path.append(point)

        # Add final keystate position
        path.append(self.keystates[-1].position.to_tuple())
        return path

    def _find_look_ahead_point(self, current_state: StatePoint,
                               path: List[Tuple[float, float, float]],
                               look_ahead_dist: float) -> Tuple[float, float, float]:
        """Find target point on path at look_ahead_dist ahead of vehicle.

        Args:
            current_state: Current vehicle state
            path: List of path points (x, y, z)
            look_ahead_dist: Distance ahead to find target point

        Returns:
            Target point (x, y, z) on the path
        """
        curr_pos = (current_state.position.x, current_state.position.y)

        # Find closest path point to current position
        min_dist = float('inf')
        closest_idx = 0
        for i, pt in enumerate(path):
            d = math.sqrt((pt[0] - curr_pos[0]) ** 2 + (pt[1] - curr_pos[1]) ** 2)
            if d < min_dist:
                min_dist = d
                closest_idx = i

        # Walk along path until we've traveled look_ahead_dist
        traveled = 0.0
        for i in range(closest_idx, len(path) - 1):
            seg_dist = math.sqrt(sum((path[i + 1][k] - path[i][k]) ** 2 for k in range(2)))
            if seg_dist < 1e-6:
                continue
            if traveled + seg_dist >= look_ahead_dist:
                # Interpolate to exact point
                remaining = look_ahead_dist - traveled
                ratio = remaining / seg_dist
                return tuple(path[i][k] + ratio * (path[i + 1][k] - path[i][k]) for k in range(3))
            traveled += seg_dist

        # Return last point if path ends before look_ahead_dist
        return path[-1]

    def _pure_pursuit_steering(self, current_state: StatePoint,
                               target_point: Tuple[float, float, float]) -> float:
        """Compute steering angle using Pure Pursuit algorithm.

        Pure pursuit calculates the steering angle needed to follow a circular
        arc from the current position to the target point.

        Args:
            current_state: Current vehicle state
            target_point: Target point (x, y, z) to aim for

        Returns:
            Steering angle in radians
        """
        current_x = current_state.position.x
        current_y = current_state.position.y
        current_yaw = current_state.heading.yaw
        target_x, target_y, _ = target_point

        # Calculate geometric relationship to target point
        target_angle = np.arctan2(target_y - current_y, target_x - current_x)
        target_dist = np.sqrt((target_x - current_x) ** 2 + (target_y - current_y) ** 2)
        delta_yaw = target_angle - current_yaw

        # Normalize delta_yaw to [-pi, pi]
        while delta_yaw > np.pi:
            delta_yaw -= 2 * np.pi
        while delta_yaw < -np.pi:
            delta_yaw += 2 * np.pi

        # Apply pure pursuit formula only if target is sufficiently far
        steering = 0.0
        if target_dist >= 0.5:
            steering = np.arctan((2 * self.wheel_dist * np.sin(delta_yaw)) / target_dist)

        return steering

    def _get_target_speed(self, timestamp: int) -> float:
        """Get target speed based on next keystate velocity.

        Args:
            timestamp: Current timestamp in nanoseconds

        Returns:
            Target speed in m/s (speed magnitude of the next keystate)
        """
        for i in range(len(self.keystate_times) - 1):
            if self.keystate_times[i] <= timestamp < self.keystate_times[i + 1]:
                # Target is the next keystate's speed
                return self.keystates[i + 1].velocity.norm()
        return self.keystates[-1].velocity.norm()

    def _simulate_trajectory(self):
        """Run simulation to generate trajectory.

        For dubins + kinematics: directly propagates along the pre-computed
        Dubins path using time-based SUVAT, bypassing BicycleModel entirely.

        For dubins + pid: uses Dubins path with BicycleModel + Pure Pursuit.

        For pure_pursuit (any speed mode): uses BicycleModel + Pure Pursuit
        with linear-interpolated path (original behavior).
        """
        if not self.keystates or not self.scenario.timestamps:
            return

        if self.heading_controller == 'dubins' and self.speed_controller == 'kinematics':
            self._simulate_dubins_kinematics()
        else:
            self._simulate_with_bicycle_model()

    def _simulate_dubins_kinematics(self):
        """Direct propagation along Dubins path with SUVAT speed control.

        Bypasses BicycleModel and Pure Pursuit. At each timestep:
        1. Compute speed from v = v0 + a*t (time-based SUVAT)
        2. Advance cumulative distance by speed * dt
        3. Interpolate (x, y, yaw) from Dubins path at current distance
        """
        from ...utils.physics_helper import kinematic_velocity

        path = self._build_trajectory_path()
        if not path or len(path) < 2:
            return

        # Pre-compute cumulative distances along the Dubins path
        cum_distances = [0.0]
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            cum_distances.append(cum_distances[-1] + math.sqrt(dx * dx + dy * dy))
        total_path_length = cum_distances[-1]

        first_time = self.keystate_times[0]
        last_time = self.keystate_times[-1]

        # Track time within current segment for SUVAT
        cumulative_distance = 0.0
        segment_idx = 0
        segment_time = 0.0  # Time elapsed within current segment

        for timestamp in self.scenario.timestamps:
            if timestamp < first_time or timestamp > last_time:
                continue

            # Determine which segment we're in based on timestamp
            new_segment_idx = segment_idx
            for i in range(len(self.keystate_times) - 1):
                if self.keystate_times[i] <= timestamp < self.keystate_times[i + 1]:
                    new_segment_idx = i
                    break
            else:
                new_segment_idx = max(0, len(self.keystate_times) - 2)

            # If we've moved to a new segment, reset segment time
            if new_segment_idx != segment_idx:
                segment_idx = new_segment_idx
                segment_time = 0.0

            if segment_idx >= len(self.segment_accelerations):
                segment_idx = len(self.segment_accelerations) - 1

            v0 = self.segment_start_speeds[segment_idx]
            accel = self.segment_accelerations[segment_idx]

            # Speed from time-based SUVAT: v = v0 + a*t
            speed = max(0.0, kinematic_velocity(v0, accel, segment_time))

            # Advance distance
            cumulative_distance += speed * self.scenario.interval
            cumulative_distance = min(cumulative_distance, total_path_length)

            # Interpolate position and yaw from Dubins path
            x, y, yaw = self._interpolate_path_at_distance(
                path, cum_distances, cumulative_distance
            )

            # Build velocity and acceleration vectors along heading
            vx = speed * math.cos(yaw)
            vy = speed * math.sin(yaw)
            ax = accel * math.cos(yaw)
            ay = accel * math.sin(yaw)

            state = StatePoint(
                position=(x, y, 0.0),
                velocity=(vx, vy, 0.0),
                acceleration=(ax, ay, 0.0),
                heading=(0.0, 0.0, yaw),
                timestamp=timestamp,
                obj_id=self.obj_id,
            )

            self.interpolated_states[timestamp] = state
            segment_time += self.scenario.interval

    def _interpolate_path_at_distance(self, path, cum_distances, distance):
        """Interpolate (x, y, yaw) from path at a given cumulative distance.

        Args:
            path: list of (x, y, z) points
            cum_distances: cumulative distance at each path point
            distance: target distance along path

        Returns:
            (x, y, yaw) tuple
        """
        # Binary search for the segment containing the target distance
        lo, hi = 0, len(cum_distances) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if cum_distances[mid] <= distance:
                lo = mid
            else:
                hi = mid

        if lo >= len(path) - 1:
            # At or past end of path
            pt = path[-1]
            # Compute yaw from last two points
            if len(path) >= 2:
                dx = path[-1][0] - path[-2][0]
                dy = path[-1][1] - path[-2][1]
                yaw = math.atan2(dy, dx)
            else:
                yaw = 0.0
            return pt[0], pt[1], yaw

        seg_length = cum_distances[hi] - cum_distances[lo]
        if seg_length < 1e-8:
            pt = path[lo]
            dx = path[hi][0] - path[lo][0]
            dy = path[hi][1] - path[lo][1]
            yaw = math.atan2(dy, dx) if (abs(dx) > 1e-8 or abs(dy) > 1e-8) else 0.0
            return pt[0], pt[1], yaw

        ratio = (distance - cum_distances[lo]) / seg_length
        x = path[lo][0] + ratio * (path[hi][0] - path[lo][0])
        y = path[lo][1] + ratio * (path[hi][1] - path[lo][1])

        # Compute yaw from the interpolated segment direction
        dx = path[hi][0] - path[lo][0]
        dy = path[hi][1] - path[lo][1]
        yaw = math.atan2(dy, dx)

        return x, y, yaw

    def _simulate_with_bicycle_model(self):
        """Original closed-loop simulation using BicycleModel + Pure Pursuit.

        Used for pure_pursuit heading controller (any speed mode),
        and dubins + pid mode.
        """
        # Build dense path from keystates
        path = self._build_trajectory_path()

        # Initialize from first keystate
        current_state = StatePoint(
            position=self.keystates[0].position.to_tuple(),
            velocity=self.keystates[0].velocity.to_tuple(),
            heading=self.keystates[0].heading.to_tuple(),
            timestamp=self.keystate_times[0],
            obj_id=self.obj_id
        )

        first_time = self.keystate_times[0]
        last_time = self.keystate_times[-1]

        for timestamp in self.scenario.timestamps:
            if timestamp < first_time or timestamp > last_time:
                continue

            # Get current speed
            current_speed = current_state.velocity.norm()

            # Longitudinal control: branch on speed controller mode
            if self.speed_controller == 'kinematics':
                cmd_speed = max(0.0, self._get_kinematic_speed(timestamp, current_state))
            else:
                target_speed = self._get_target_speed(timestamp)
                speed_output = self.speed_pid.step(target_speed, current_speed)
                cmd_speed = max(0.0, current_speed + speed_output * self.scenario.interval)

            # Lateral control: Pure Pursuit
            look_ahead_dist = max(5.0, self.look_ahead_time * current_speed)
            target_point = self._find_look_ahead_point(current_state, path, look_ahead_dist)
            cmd_steering = self._pure_pursuit_steering(current_state, target_point)

            # Vehicle dynamics: BicycleModel
            new_state = self.bicycle_model.step(current_state, cmd_speed, cmd_steering)

            # Create StatePoint with timestamp and obj_id
            new_state = StatePoint(
                position=new_state.position.to_tuple(),
                velocity=new_state.velocity.to_tuple(),
                acceleration=new_state.acceleration.to_tuple(),
                heading=new_state.heading.to_tuple(),
                timestamp=timestamp,
                obj_id=self.obj_id
            )

            self.interpolated_states[timestamp] = new_state
            current_state = new_state

    def get_state_at_time(self, timestamp: int) -> Optional[StatePoint]:
        """Get simulated state at specific timestamp.

        Args:
            timestamp: Target timestamp (nanoseconds)

        Returns:
            StatePoint at the given time, or None if vehicle should not be present
        """
        if not self.keystates or not self.keystate_times:
            return None

        first_keystate_time = self.keystate_times[0]
        last_keystate_time = self.keystate_times[-1]

        if timestamp < first_keystate_time or timestamp > last_keystate_time:
            return None

        if timestamp in self.interpolated_states:
            return self.interpolated_states[timestamp]

        return None

    def get_trajectory(self) -> List[StatePoint]:
        """Get complete simulated trajectory as list of StatePoints.

        Returns:
            List of StatePoints for all frames within keystate time range,
            sorted by timestamp.
        """
        if not self.interpolated_states:
            return []

        sorted_timestamps = sorted(self.interpolated_states.keys())
        return [self.interpolated_states[ts] for ts in sorted_timestamps]

    def get_keystate_times(self) -> List[int]:
        """Get the calculated timestamps for each keystate.

        Returns:
            List of timestamps (nanoseconds) for each keystate
        """
        return self.keystate_times.copy()
