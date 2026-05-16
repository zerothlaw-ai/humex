"""Monitor for detecting when the ego vehicle has crossed a stop line."""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.math_helper import dist2d


class StopLineCrossed(MonitorBase):
    """Detects when the ego vehicle's front bumper has crossed a stop line.

    OUTPUT_TYPE: BOOL

    For each frame, finds the closest lane to the ego position. If that lane
    has a stop line, checks whether the ego's front bumper has crossed it.
    If the closest lane has no stop line, falls back to checking the nearest
    stop point within range (handles cases where the KD-tree returns an
    adjacent lane near intersections).
    """
    OUTPUT_TYPE = OutputType.BOOL

    # Maximum distance from ego center to a stop point to consider
    MAX_STOP_DISTANCE = 15.0

    def __init__(self, scenario):
        super().__init__(scenario)
        # Pre-compute {lane_id: (stop_point_xy, lane_direction_xy)} for lanes with stop points
        self._lane_stop_info = self._build_stop_info()

    def _build_stop_info(self):
        """Build a lookup of stop point position and lane direction for each lane with a stop point.

        Returns:
            dict: {lane_id: ((sx, sy), (dx, dy))} where (sx,sy) is the stop point
                  and (dx,dy) is the unit direction vector of the lane at that point.
        """
        info = {}
        scenario = self.scenario
        if scenario is None or scenario.map is None:
            return info

        for lane_id, lane in scenario.map.map_data.lanes.items():
            if lane.stop_point is None:
                continue

            sp_x, sp_y = lane.stop_point.x, lane.stop_point.y

            # Collect all centerline points for this lane
            centerline_pts = []
            for seg in lane.center_line:
                for pt in seg.points:
                    centerline_pts.append((pt.x, pt.y))

            if len(centerline_pts) < 2:
                continue

            # Find the centerline point closest to the stop point
            best_idx = 0
            best_dist = float('inf')
            for i in range(len(centerline_pts)):
                d = dist2d((sp_x, sp_y), centerline_pts[i])
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            # Compute direction vector from consecutive points
            if best_idx < len(centerline_pts) - 1:
                p0 = centerline_pts[best_idx]
                p1 = centerline_pts[best_idx + 1]
            else:
                p0 = centerline_pts[best_idx - 1]
                p1 = centerline_pts[best_idx]

            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            length = (dx * dx + dy * dy) ** 0.5
            if length < 1e-9:
                continue
            dx /= length
            dy /= length

            info[lane_id] = ((sp_x, sp_y), (dx, dy))

        return info

    def _find_nearest_stop_info(self, ego_x, ego_y):
        """Find the nearest stop point info within MAX_STOP_DISTANCE.

        Returns:
            tuple or None: ((sp_x, sp_y), (dx, dy)) of nearest stop point, or None.
        """
        best_info = None
        best_dist_sq = self.MAX_STOP_DISTANCE ** 2
        for (sp_x, sp_y), (dx, dy) in self._lane_stop_info.values():
            dist_sq = (ego_x - sp_x) ** 2 + (ego_y - sp_y) ** 2
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_info = ((sp_x, sp_y), (dx, dy))
        return best_info

    def calculate(self):
        """Check if ego vehicle's front bumper has crossed a stop line.

        Returns:
            bool: True if the ego's front bumper has crossed a nearby stop line.
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        if not self._lane_stop_info:
            return False

        ego_pos = ego.sp.position
        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        # Primary: find closest lane and check if it has a stop point
        lane_id = self.scenario.map.find_closest_lane(
            (ego_pos.x, ego_pos.y, ego_pos.z), heading=ego_heading
        )

        stop_info = None
        if lane_id is not None and lane_id in self._lane_stop_info:
            stop_info = self._lane_stop_info[lane_id]
        else:
            # Fallback: closest lane has no stop point, but ego may be near one
            # on an adjacent lane (common near intersections with multiple lanes)
            stop_info = self._find_nearest_stop_info(ego_pos.x, ego_pos.y)

        if stop_info is None:
            return False

        (sp_x, sp_y), (dx, dy) = stop_info

        # Compute ego front bumper center
        fl = ego.bbox.front_left
        fr = ego.bbox.front_right
        front_x = (fl.x + fr.x) * 0.5
        front_y = (fl.y + fr.y) * 0.5

        # Signed distance of front bumper along lane direction relative to stop point
        front_dist = (front_x - sp_x) * dx + (front_y - sp_y) * dy

        # Front bumper has crossed the stop line
        return front_dist > 0
