"""Keyframe-based behavior handler for vehicle trajectory generation.

This module provides the KeyframeBehavior class that generates smooth
trajectories from a list of keyframe states using Hermite spline interpolation.
"""

import math
from typing import List, Optional, Tuple
from .behavior_base import BaseBehavior
from ...components.statepoint import StatePoint
from ...utils.physics_helper import kinematic_position
from ...utils.timestamp import to_ns


class KeyframeBehavior(BaseBehavior):
    """Behavior handler for keyframe-based trajectory generation.

    Takes a list of StatePoints (without timestamps) and generates
    complete trajectories by:
    1. Calculating time intervals based on distance/velocity between keyframes
    2. Interpolating between keyframes using Hermite spline interpolation
    3. Returning StatePoints WITH timestamps for replay
    """

    def __init__(self, keystates: List[StatePoint], scenario, obj_id: int = None):
        """Initialize KeyframeBehavior.

        Args:
            keystates: List of StatePoints WITHOUT timestamps (position, velocity, heading only)
            scenario: Parent scenario for duration/frequency information
            obj_id: Object ID for generated StatePoints
        """
        super().__init__(keystates, scenario, obj_id)
        self.keystate_times: List[int] = []

        if self.keystates:
            self._validate_keystates()
            self._calculate_keystate_times()
            self._interpolate_all_frames()

    def _validate_keystates(self):
        """Validate keystate format and content."""
        if not self.keystates:
            raise ValueError("KeyframeBehavior requires at least one keystate")

        for i, keystate in enumerate(self.keystates):
            if not isinstance(keystate, StatePoint):
                raise ValueError(f"Keystate {i} must be a StatePoint")

    def _calculate_keystate_times(self):
        """Calculate timestamps for each keystate based on distance/velocity.

        Uses physics: time = distance / avg_velocity to determine when
        the vehicle arrives at each keystate position.
        """
        if not self.keystates:
            return

        if len(self.keystates) == 1:
            self.keystate_times = [0]
            return

        calculated_times = [0]

        for i in range(1, len(self.keystates)):
            prev_state = self.keystates[i - 1]
            curr_state = self.keystates[i]

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

    def _find_bounding_keystates(self, target_time: int) -> Tuple[Optional[Tuple[int, StatePoint]], Optional[Tuple[int, StatePoint]]]:
        """Find the keystates before and after target time.

        Args:
            target_time: Target timestamp (nanoseconds) to interpolate for

        Returns:
            tuple: (before_keystate, after_keystate) as (time, StatePoint) tuples
                   or (None, keystate) for edge cases
        """
        if not self.keystate_times:
            return None, None

        if target_time <= self.keystate_times[0]:
            return None, (self.keystate_times[0], self.keystates[0])
        elif target_time >= self.keystate_times[-1]:
            return (self.keystate_times[-1], self.keystates[-1]), None
        else:
            for i in range(len(self.keystate_times) - 1):
                if self.keystate_times[i] <= target_time <= self.keystate_times[i + 1]:
                    return (
                        (self.keystate_times[i], self.keystates[i]),
                        (self.keystate_times[i + 1], self.keystates[i + 1])
                    )

        return (self.keystate_times[0], self.keystates[0]), (self.keystate_times[-1], self.keystates[-1])

    def _interpolate_heading(self, start_heading, end_heading, t: float) -> Tuple[float, float, float]:
        """Interpolate heading with proper yaw angle wrapping.

        Args:
            start_heading: Starting heading
            end_heading: Ending heading
            t: Interpolation parameter (0 to 1)

        Returns:
            tuple: Interpolated (roll, pitch, yaw) heading
        """
        roll = start_heading.roll + t * (end_heading.roll - start_heading.roll)
        pitch = start_heading.pitch + t * (end_heading.pitch - start_heading.pitch)

        start_yaw = start_heading.yaw % 360
        end_yaw = end_heading.yaw % 360

        diff = end_yaw - start_yaw

        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360

        interpolated_yaw = (start_yaw + t * diff) % 360

        return (roll, pitch, interpolated_yaw)

    def _interpolate_segment(self, before_keystate: Tuple[int, StatePoint], after_keystate: Tuple[int, StatePoint], target_time: int) -> StatePoint:
        """Hermite spline interpolation between two keystates.

        Uses cubic Hermite interpolation which guarantees:
        - Position matches at both keystate endpoints
        - Velocity (tangent) matches at both endpoints
        - Smooth C1 continuous trajectory

        Args:
            before_keystate: (timestamp, StatePoint) before target
            after_keystate: (timestamp, StatePoint) after target
            target_time: Target timestamp (nanoseconds) for interpolation

        Returns:
            StatePoint: Interpolated state at target_time
        """
        before_time, before_state = before_keystate
        after_time, after_state = after_keystate

        total_time = after_time - before_time

        if total_time <= 0:
            return self._create_interpolated_state(before_state, target_time)

        elapsed = target_time - before_time
        t = elapsed / total_time
        total_time_sec = total_time / 1e9

        p0 = before_state.position.to_tuple()
        p1 = after_state.position.to_tuple()
        v0 = before_state.velocity.to_tuple()
        v1 = after_state.velocity.to_tuple()

        m0 = tuple(v * total_time_sec for v in v0)
        m1 = tuple(v * total_time_sec for v in v1)

        t2 = t * t
        t3 = t2 * t
        h00 = 2*t3 - 3*t2 + 1
        h10 = t3 - 2*t2 + t
        h01 = -2*t3 + 3*t2
        h11 = t3 - t2

        interp_pos = tuple(
            h00*p0[i] + h10*m0[i] + h01*p1[i] + h11*m1[i]
            for i in range(3)
        )

        dh00 = 6*t2 - 6*t
        dh10 = 3*t2 - 4*t + 1
        dh01 = -6*t2 + 6*t
        dh11 = 3*t2 - 2*t

        dp_dt = tuple(
            dh00*p0[i] + dh10*m0[i] + dh01*p1[i] + dh11*m1[i]
            for i in range(3)
        )
        interp_vel = tuple(d / total_time_sec for d in dp_dt)

        d2h00 = 12*t - 6
        d2h10 = 6*t - 4
        d2h01 = -12*t + 6
        d2h11 = 6*t - 2

        d2p_dt2 = tuple(
            d2h00*p0[i] + d2h10*m0[i] + d2h01*p1[i] + d2h11*m1[i]
            for i in range(3)
        )
        interp_acc = tuple(d / (total_time_sec**2) for d in d2p_dt2)

        interp_heading = self._interpolate_heading(before_state.heading, after_state.heading, t)

        return self._create_interpolated_state_from_components(
            position=interp_pos,
            velocity=interp_vel,
            acceleration=interp_acc,
            heading=interp_heading,
            timestamp=target_time
        )

    def _handle_edge_cases(self, before_keystate: Optional[Tuple[int, StatePoint]], after_keystate: Optional[Tuple[int, StatePoint]], target_time: int) -> StatePoint:
        """Handle interpolation edge cases (before first, after last keystate).

        Args:
            before_keystate: (timestamp, StatePoint) or None if before first keystate
            after_keystate: (timestamp, StatePoint) or None if after last keystate
            target_time: Target timestamp (nanoseconds)

        Returns:
            StatePoint: Extrapolated state for edge case
        """
        if before_keystate is None:
            first_time, first_state = after_keystate
            time_diff_seconds = (first_time - target_time) / 1e9

            start_pos = first_state.position.to_tuple()
            velocity = first_state.velocity.to_tuple()

            extrapolated_pos = kinematic_position(start_pos, velocity, (0.0, 0.0, 0.0), -time_diff_seconds)

            return self._create_interpolated_state_from_components(
                position=extrapolated_pos,
                velocity=velocity,
                acceleration=(0.0, 0.0, 0.0),
                heading=first_state.heading.to_tuple(),
                timestamp=target_time
            )

        elif after_keystate is None:
            last_time, last_state = before_keystate
            time_diff_seconds = (target_time - last_time) / 1e9

            start_pos = last_state.position.to_tuple()
            velocity = last_state.velocity.to_tuple()

            extrapolated_pos = kinematic_position(start_pos, velocity, (0.0, 0.0, 0.0), time_diff_seconds)

            return self._create_interpolated_state_from_components(
                position=extrapolated_pos,
                velocity=velocity,
                acceleration=(0.0, 0.0, 0.0),
                heading=last_state.heading.to_tuple(),
                timestamp=target_time
            )

        return self._interpolate_segment(before_keystate, after_keystate, target_time)

    def _create_interpolated_state(self, base_state: StatePoint, timestamp: int) -> StatePoint:
        """Create a new StatePoint based on an existing one with updated timestamp."""
        return self._create_interpolated_state_from_components(
            position=base_state.position.to_tuple(),
            velocity=base_state.velocity.to_tuple(),
            acceleration=base_state.acceleration.to_tuple(),
            heading=base_state.heading.to_tuple(),
            timestamp=timestamp
        )

    def _create_interpolated_state_from_components(self, position: Tuple, velocity: Tuple, acceleration: Tuple, heading: Tuple, timestamp: int) -> StatePoint:
        """Create StatePoint from component tuples."""
        return StatePoint(
            position=position,
            velocity=velocity,
            acceleration=acceleration,
            heading=heading,
            timestamp=timestamp,
            obj_id=self.obj_id
        )

    def _interpolate_all_frames(self):
        """Pre-compute interpolated states for all scenario frames."""
        if not self.scenario or not self.scenario.timestamps or not self.keystates:
            return

        self.interpolated_states = {}

        first_keystate_time = self.keystate_times[0]
        last_keystate_time = self.keystate_times[-1]

        for timestamp in self.scenario.timestamps:
            if timestamp < first_keystate_time or timestamp > last_keystate_time:
                continue

            before_keystate, after_keystate = self._find_bounding_keystates(timestamp)

            if before_keystate is None or after_keystate is None:
                interpolated_state = self._handle_edge_cases(before_keystate, after_keystate, timestamp)
            else:
                interpolated_state = self._interpolate_segment(before_keystate, after_keystate, timestamp)

            self.interpolated_states[timestamp] = interpolated_state

    def get_state_at_time(self, timestamp: int) -> Optional[StatePoint]:
        """Get interpolated state at specific timestamp.

        Args:
            timestamp: Target timestamp (nanoseconds)

        Returns:
            StatePoint: Interpolated state at the given time, or None if vehicle should not be present
        """
        if not self.keystates or not self.keystate_times:
            return None

        first_keystate_time = self.keystate_times[0]
        last_keystate_time = self.keystate_times[-1]

        if timestamp < first_keystate_time or timestamp > last_keystate_time:
            return None

        if timestamp in self.interpolated_states:
            return self.interpolated_states[timestamp]

        before_keystate, after_keystate = self._find_bounding_keystates(timestamp)
        if before_keystate is None or after_keystate is None:
            return self._handle_edge_cases(before_keystate, after_keystate, timestamp)
        else:
            return self._interpolate_segment(before_keystate, after_keystate, timestamp)

    def get_trajectory(self) -> List[StatePoint]:
        """Get complete trajectory as list of StatePoints with timestamps.

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
