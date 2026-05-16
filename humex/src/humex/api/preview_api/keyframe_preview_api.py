"""Keyframe Preview API for computing Dubins paths and resolving SUVAT constraints.

Provides a lightweight preview of keyframe trajectories using actual arc lengths
(Dubins curves) instead of Euclidean approximations, ensuring consistency between
preview and simulation.
"""

import math
from typing import Dict, List, Any, Optional

from ...utils.dubins_utils import compute_all_dubins_segments
from ...utils.physics_helper import (
    kinematic_acceleration_from_velocities_and_displacement,
    kinematic_velocity_squared,
)


class KeyframePreviewAPI:
    """API for previewing keyframe trajectories with SUVAT constraint resolution."""

    def preview(
        self,
        keystates: List[Dict[str, Any]],
        changed_field: str,
        changed_index: int,
        speed_controller: str = 'kinematics',
        heading_controller: str = 'dubins',
        turning_radius: float = 6.0,
    ) -> Dict[str, Any]:
        """Compute preview paths and resolve kinematic constraints.

        Args:
            keystates: list of dicts with keys:
                position: [x, y, z]
                velocity: [vx, vy, vz]
                heading: [roll, pitch, yaw]
                acceleration: [ax, ay, az]  (optional)
            changed_field: 'speed' | 'acceleration' | 'yaw' | 'position'
            changed_index: which keystate was edited
            speed_controller: 'kinematics' | 'pid'
            heading_controller: 'dubins' | 'pure_pursuit'
            turning_radius: Dubins minimum turning radius in meters

        Returns:
            dict with:
                'keystates': updated keystates with resolved speed/accel
                'segments': list of {'path_points': [[x,y],...], 'arc_length': float}
        """
        if len(keystates) < 2:
            return {
                'keystates': keystates,
                'segments': [],
            }

        # Extract poses (x, y, yaw) from keystates
        poses = []
        for ks in keystates:
            x, y = ks['position'][0], ks['position'][1]
            yaw = ks['heading'][2]  # heading is [roll, pitch, yaw]
            poses.append((x, y, yaw))

        # Compute segment distances and path points
        segments_output = []
        arc_lengths = []

        if heading_controller == 'dubins':
            dubins_segments = compute_all_dubins_segments(poses, turning_radius)
            for seg in dubins_segments:
                path_points = [[pt[0], pt[1]] for pt in seg['sample_points']]
                segments_output.append({
                    'path_points': path_points,
                    'arc_length': seg['path_length'],
                })
                arc_lengths.append(seg['path_length'])
        else:
            # Pure pursuit: use Euclidean distance, straight line segments
            for i in range(len(poses) - 1):
                p0 = poses[i]
                p1 = poses[i + 1]
                dist = math.sqrt((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2)
                segments_output.append({
                    'path_points': [[p0[0], p0[1]], [p1[0], p1[1]]],
                    'arc_length': dist,
                })
                arc_lengths.append(dist)

        # Resolve SUVAT constraints (only for kinematics mode)
        updated_keystates = [dict(ks) for ks in keystates]

        if speed_controller == 'kinematics':
            updated_keystates = self._resolve_constraints(
                updated_keystates, arc_lengths, changed_field, changed_index
            )

        return {
            'keystates': updated_keystates,
            'segments': segments_output,
        }

    def _resolve_constraints(
        self,
        keystates: List[Dict[str, Any]],
        arc_lengths: List[float],
        changed_field: str,
        changed_index: int,
    ) -> List[Dict[str, Any]]:
        """Resolve SUVAT kinematic constraints given arc lengths.

        Args:
            keystates: mutable list of keystate dicts
            arc_lengths: arc length per segment
            changed_field: which field was edited
            changed_index: which keystate index was edited

        Returns:
            Updated keystates with resolved speed/acceleration values
        """
        n = len(keystates)

        # Extract scalar speeds from velocity vectors
        speeds = []
        for ks in keystates:
            vx, vy = ks['velocity'][0], ks['velocity'][1]
            speeds.append(math.sqrt(vx ** 2 + vy ** 2))

        if changed_field in ('speed', 'yaw', 'position'):
            # Recompute all accelerations from speeds and arc lengths
            accels = []
            for i in range(n - 1):
                s = arc_lengths[i]
                if s > 1e-6:
                    a = kinematic_acceleration_from_velocities_and_displacement(
                        speeds[i], speeds[i + 1], s
                    )
                else:
                    a = 0.0
                accels.append(a)
            accels.append(0.0)  # last keystate has no outgoing segment

            # Write back acceleration into keystates (decomposed along heading)
            for i in range(n):
                yaw = keystates[i]['heading'][2]
                ax = accels[i] * math.cos(yaw)
                ay = accels[i] * math.sin(yaw)
                keystates[i]['acceleration'] = [ax, ay, 0.0]

        elif changed_field == 'acceleration':
            # User changed acceleration at changed_index
            # Compute next speed from v² = v₀² + 2as
            idx = changed_index
            if idx < n - 1:
                # Get the scalar acceleration the user set
                ax, ay = keystates[idx]['acceleration'][0], keystates[idx]['acceleration'][1]
                a = math.sqrt(ax ** 2 + ay ** 2)
                # Determine sign: if acceleration opposes velocity direction
                yaw = keystates[idx]['heading'][2]
                a_along = ax * math.cos(yaw) + ay * math.sin(yaw)
                if a_along < 0:
                    a = -a

                s = arc_lengths[idx]
                v0 = speeds[idx]
                v_sq = v0 ** 2 + 2 * a * s
                new_speed = math.sqrt(max(0.0, v_sq))
                speeds[idx + 1] = new_speed

                # Write new speed into next keystate
                next_yaw = keystates[idx + 1]['heading'][2]
                keystates[idx + 1]['velocity'] = [
                    new_speed * math.cos(next_yaw),
                    new_speed * math.sin(next_yaw),
                    0.0,
                ]

                # Recompute downstream accelerations
                for i in range(idx + 1, n - 1):
                    seg_s = arc_lengths[i]
                    if seg_s > 1e-6:
                        seg_a = kinematic_acceleration_from_velocities_and_displacement(
                            speeds[i], speeds[i + 1], seg_s
                        )
                    else:
                        seg_a = 0.0
                    seg_yaw = keystates[i]['heading'][2]
                    keystates[i]['acceleration'] = [
                        seg_a * math.cos(seg_yaw),
                        seg_a * math.sin(seg_yaw),
                        0.0,
                    ]

                # Last keystate always 0 acceleration
                keystates[n - 1]['acceleration'] = [0.0, 0.0, 0.0]

        return keystates
