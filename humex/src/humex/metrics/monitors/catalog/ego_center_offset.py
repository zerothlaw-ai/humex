"""Monitor for tracking ego vehicle lateral deviation from lane centerline."""

import math
from typing import Iterable, Tuple

import numpy as np

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.hmap.road_map import LaneData


class EgoCenterOffset(MonitorBase):
    """Returns the lateral distance between the ego center and its lane center.

    OUTPUT_TYPE: FLOAT
    """
    OUTPUT_TYPE = OutputType.FLOAT

    def __init__(self, scenario):
        super().__init__(scenario)

    def calculate(self):
        frame = self.curr_frame
        scenario = self.scenario

        if scenario is None or scenario.map is None:
            return None

        ego = frame.get_ego(scenario)
        if ego is None or ego.sp is None or ego.sp.position is None:
            return None

        ego_position = ego.sp.position.to_tuple()
        if ego_position is None:
            return math.nan

        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        lane_id = scenario.map.find_closest_lane(ego_position, heading=ego_heading)
        if lane_id is None:
            return math.nan

        lane = scenario.map.map_data.lanes.get(lane_id)
        if lane is None:
            return math.nan

        centerline_pts = self._flatten_centerline(lane)
        if centerline_pts.shape[0] < 2:
            return math.nan

        ego_xy = np.array(ego_position[:2], dtype=float)
        return float(self._distance_to_polyline(ego_xy, centerline_pts))

    def _flatten_centerline(self, lane: LaneData) -> np.ndarray:
        """Collect all centerline points for the lane as an array."""
        points = []
        for segment in lane.center_line:
            for pt in getattr(segment, "points", []):
                points.append((float(pt.x), float(pt.y)))
        if not points:
            return np.empty((0, 2))
        return np.asarray(points, dtype=float)

    def _distance_to_polyline(self, point: np.ndarray, polyline: np.ndarray) -> float:
        """Compute the minimal perpendicular distance from point to a polyline."""
        min_dist_sq = math.inf
        for start, end in self._iter_segments(polyline):
            seg_vec = end - start
            seg_len_sq = float(np.dot(seg_vec, seg_vec))
            if seg_len_sq == 0.0:
                # Degenerate segment; treat as single point
                diff = point - start
                dist_sq = float(np.dot(diff, diff))
            else:
                t = float(np.dot(point - start, seg_vec) / seg_len_sq)
                t = float(np.clip(t, 0.0, 1.0))
                projection = start + t * seg_vec
                diff = point - projection
                dist_sq = float(np.dot(diff, diff))
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
        return math.sqrt(min_dist_sq)

    def _iter_segments(self, polyline: np.ndarray) -> Iterable[Tuple[np.ndarray, np.ndarray]]:
        """Yield consecutive segment endpoints from the polyline."""
        for idx in range(len(polyline) - 1):
            yield polyline[idx], polyline[idx + 1]
