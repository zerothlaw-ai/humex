"""Velocity / acceleration enhancement — Stage 2A of the conversion pipeline.

Plugin converters (Waymo, DROID, LAFAN) extract raw position tracks; many of
them do not populate velocity or acceleration. This module recomputes those
from positions using central differencing on interior frames and forward /
backward differencing at track endpoints, with a heading-based fallback for
outliers.

Public entry point: :func:`enhance_scenario` mutates a loaded scenario in
place and returns it. The legacy :class:`DataEnhancer` namespace is preserved
for callers that still reference it.
"""

import logging

from ..utils.math_helper import calculate_velocity_from_positions, calculate_velocity_from_heading_and_speed
from ..utils.timestamp import to_seconds

logger = logging.getLogger(__name__)


# Per-frame quality limits used by both velocity and acceleration enhancement.
_MAX_REALISTIC_SPEED = 100.0      # m/s (~360 km/h)
_HEADING_FALLBACK_SPEED_CAP = 30.0  # m/s
_MAX_REALISTIC_ACCEL = 20.0       # m/s^2 (~2g)


def _collect_position_tracks(scenario):
    """Build {obj_id: [(timestamp, (x,y,z), obj_ref), ...]} sorted by timestamp.

    A track is the ordered sequence of frames an object appears in. This lets
    the enhancer use central differencing on interior frames instead of
    forward-only on frame 0 + backward-only on the rest, which previously
    duplicated the first two frames' velocities (since v_0 = forward(0,1) =
    backward(0,1) = v_1).
    """
    tracks = {}
    for ts in sorted(scenario.frames.keys()):
        frame = scenario.frames[ts]
        for obj_id, obj in frame.obj_list.items():
            pos = (obj.sp.position.x, obj.sp.position.y, obj.sp.position.z)
            tracks.setdefault(obj_id, []).append((ts, pos, obj))
    return tracks


def _collect_velocity_tracks(scenario):
    """Same as ``_collect_position_tracks`` but reads velocity instead of position."""
    tracks = {}
    for ts in sorted(scenario.frames.keys()):
        frame = scenario.frames[ts]
        for obj_id, obj in frame.obj_list.items():
            vel = (obj.sp.velocity.x, obj.sp.velocity.y, obj.sp.velocity.z)
            tracks.setdefault(obj_id, []).append((ts, vel, obj))
    return tracks


def _diff_neighbors(track, i):
    """Pick the (start_value, end_value, dt_seconds) used to estimate the
    derivative at track[i]. Prefers central differencing when both neighbors
    are available; falls back to forward at the start and backward at the end.

    Returns ``None`` when the object is only sampled once and no derivative is
    defined.
    """
    n = len(track)
    if n == 1:
        return None
    ts_curr, val_curr, _ = track[i]
    if i > 0 and i < n - 1:
        ts_prev, val_prev, _ = track[i - 1]
        ts_next, val_next, _ = track[i + 1]
        return val_prev, val_next, to_seconds(ts_next - ts_prev)
    if i == 0:
        ts_next, val_next, _ = track[i + 1]
        return val_curr, val_next, to_seconds(ts_next - ts_curr)
    # i == n - 1
    ts_prev, val_prev, _ = track[i - 1]
    return val_prev, val_curr, to_seconds(ts_curr - ts_prev)


class DataEnhancer(object):
    """Data enhancement utilities for scenario kinematic calculations."""

    @staticmethod
    def enhance_scenario_with_velocities(scenario):
        """Enhance scenario by calculating realistic velocities from position data.

        For each object's track, velocities are estimated as:
          - Central difference on interior frames: v_i = (p_{i+1} - p_{i-1}) / (t_{i+1} - t_{i-1})
          - Forward difference on the first frame of the track
          - Backward difference on the last frame of the track
        Objects sampled in only one frame get zero velocity.

        Velocities are always recomputed from positions — any value previously
        stored on the object is overwritten. The previous "trust non-zero
        stored values" policy let upstream-duplicated frames (e.g. a prior
        forward-then-backward enhancement pass that produced ``v_0 == v_1``)
        propagate forever.

        Speeds above 100 m/s fall back to a heading-based estimate (capped at
        30 m/s) when a yaw is available, otherwise to zero.

        Args:
            scenario: Loaded scenario object with frames and objects.

        Returns:
            scenario: Same scenario with velocities populated.
        """
        logger.debug("Enhancing scenario with calculated velocities")

        tracks = _collect_position_tracks(scenario)
        enhanced_objects = 0

        for obj_id, track in tracks.items():
            for i, (_ts, _pos, obj) in enumerate(track):
                neighbors = _diff_neighbors(track, i)
                if neighbors is None:
                    obj.sp.update_velocity((0.0, 0.0, 0.0))
                    continue

                p1, p2, dt = neighbors
                if dt <= 0:
                    obj.sp.update_velocity((0.0, 0.0, 0.0))
                    continue

                try:
                    velocity = calculate_velocity_from_positions(p1, p2, dt)
                except (ValueError, ZeroDivisionError) as e:
                    logger.warning("Could not calculate velocity for object %s at frame %d: %s", obj_id, i, e)
                    obj.sp.update_velocity((0.0, 0.0, 0.0))
                    continue

                speed = (velocity[0] ** 2 + velocity[1] ** 2 + velocity[2] ** 2) ** 0.5
                if speed < _MAX_REALISTIC_SPEED:
                    obj.sp.update_velocity(velocity)
                    enhanced_objects += 1
                    continue

                # Heading-based fallback for unrealistic estimates.
                yaw = getattr(getattr(obj.sp, "heading", None), "yaw", None)
                if yaw is not None:
                    distance_2d = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
                    estimated_speed = min(distance_2d / dt, _HEADING_FALLBACK_SPEED_CAP)
                    obj.sp.update_velocity(
                        calculate_velocity_from_heading_and_speed(yaw, estimated_speed)
                    )
                    enhanced_objects += 1
                else:
                    obj.sp.update_velocity((0.0, 0.0, 0.0))

        logger.debug("Enhanced %d object velocity measurements across %d frames", enhanced_objects, len(scenario.frames))
        return scenario

    @staticmethod
    def enhance_scenario_with_accelerations(scenario):
        """Enhance scenario by calculating accelerations from (already-enhanced) velocities.

        Same differencing strategy as :meth:`enhance_scenario_with_velocities`:
        central on interior frames, forward at the start of an object's track,
        backward at the end. Magnitudes above 20 m/s² are clipped to zero.
        Accelerations are always recomputed; any prior value is overwritten.

        Args:
            scenario: Scenario object with enhanced velocity data.

        Returns:
            scenario: Same scenario with accelerations populated.
        """
        logger.debug("Enhancing scenario with calculated accelerations")

        tracks = _collect_velocity_tracks(scenario)
        enhanced_objects = 0

        for obj_id, track in tracks.items():
            for i, (_ts, _vel, obj) in enumerate(track):
                neighbors = _diff_neighbors(track, i)
                if neighbors is None:
                    obj.sp.update_acceleration((0.0, 0.0, 0.0))
                    continue

                v1, v2, dt = neighbors
                if dt <= 0:
                    obj.sp.update_acceleration((0.0, 0.0, 0.0))
                    continue

                try:
                    acceleration = calculate_velocity_from_positions(v1, v2, dt)
                except (ValueError, ZeroDivisionError) as e:
                    logger.warning("Could not calculate acceleration for object %s at frame %d: %s", obj_id, i, e)
                    obj.sp.update_acceleration((0.0, 0.0, 0.0))
                    continue

                magnitude = (acceleration[0] ** 2 + acceleration[1] ** 2 + acceleration[2] ** 2) ** 0.5
                if magnitude < _MAX_REALISTIC_ACCEL:
                    obj.sp.update_acceleration(acceleration)
                    enhanced_objects += 1
                else:
                    obj.sp.update_acceleration((0.0, 0.0, 0.0))

        logger.debug("Enhanced %d object acceleration measurements across %d frames", enhanced_objects, len(scenario.frames))
        return scenario


def enhance_scenario(scenario):
    """Run both velocity and acceleration enhancement on ``scenario`` in place.

    Order matters — acceleration is derived from velocity, so velocity must be
    populated first. Returns the same scenario object.
    """
    DataEnhancer.enhance_scenario_with_velocities(scenario)
    DataEnhancer.enhance_scenario_with_accelerations(scenario)
    return scenario
