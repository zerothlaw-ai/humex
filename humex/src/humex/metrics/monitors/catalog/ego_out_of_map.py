"""Monitor for detecting whether ego vehicle has gone out of map bounds.

This module checks whether the ego vehicle's position falls within
any lane polygon defined by the map's lane boundaries.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.math_helper import point_in_polygon


class EgoOutOfMap(MonitorBase):
    """Monitor for detecting whether ego vehicle has gone out of map bounds.

    OUTPUT_TYPE: BOOL
    """
    OUTPUT_TYPE = OutputType.BOOL

    # Maximum distance (meters) from any lane centerline to consider
    # before concluding the ego is out of map.
    MAX_LANE_DISTANCE = 50.0

    # Maximum distance (meters) from a lane centerline to still count as
    # "in map".  Covers junction gaps where lane boundary polygons don't
    # overlap but centerlines are continuous.
    CENTERLINE_TOLERANCE = 5.0

    def __init__(self, scenario):
        super().__init__(scenario)
        # Pre-build lane polygons from map data for reuse across frames
        self._lane_polygons = self._build_lane_polygons()

    def _build_lane_polygons(self):
        """Build closed polygons from lane left/right boundaries.

        Each lane polygon is formed by concatenating the left boundary points
        with the reversed right boundary points, creating a closed region.

        Returns:
            list: List of polygons, each a list of (x, y) tuples
        """
        polygons = []
        scenario = self.scenario
        if scenario is None or scenario.map is None:
            return polygons

        for lane in scenario.map.map_data.lanes.values():
            left_pts = []
            for seg in lane.left_boundary:
                for pt in getattr(seg, "points", []):
                    left_pts.append((float(pt.x), float(pt.y)))

            right_pts = []
            for seg in lane.right_boundary:
                for pt in getattr(seg, "points", []):
                    right_pts.append((float(pt.x), float(pt.y)))

            # Need both boundaries to form a polygon
            if len(left_pts) >= 2 and len(right_pts) >= 2:
                polygon = left_pts + list(reversed(right_pts))
                polygons.append(polygon)

        return polygons

    def calculate(self):
        """Check if the ego vehicle's position is outside all map lane boundaries.

        Returns:
            bool: True if ego is out of map bounds, False otherwise
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        if ego is None:
            return None

        ego_position = ego.sp.position.to_tuple()
        ego_xy = (ego_position[0], ego_position[1])
        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        ava_map = self.scenario.map

        # ---- fast path: LaneMap v2 drivable-polygon containment ----
        # HMap.find_containing_lanes returns the lane ids whose drivable
        # polygon contains the point (KDTree-backed, O(log n) candidates +
        # polygon test). Non-empty → ego is on at least one lane → in map.
        if self.lane_map is not None:
            if ava_map.find_containing_lanes(ego_position):
                return False
            # Junction-gap fallback: still close to a centerline.
            if ava_map.find_closest_lane(
                ego_position,
                max_distance=self.CENTERLINE_TOLERANCE,
                heading=ego_heading,
            ) is not None:
                return False
            return True

        # ---- slow path: precomputed legacy lane polygons ----
        if not self._lane_polygons:
            return False

        # Quick pre-filter: if no lane centerline is within range, ego is out of map
        closest_lane_id = ava_map.find_closest_lane(
            ego_position, max_distance=self.MAX_LANE_DISTANCE, heading=ego_heading
        )
        if closest_lane_id is None:
            return True

        # Check if ego position falls within any lane polygon
        for polygon in self._lane_polygons:
            if point_in_polygon(ego_xy, polygon):
                return False

        # Fallback: ego is outside all lane polygons but may be in a junction
        # gap where boundary polygons don't overlap.  Check distance to the
        # nearest centerline point — if close enough, treat as in-map.
        if getattr(ava_map, "_kdtree", None) is not None:
            dist, _ = ava_map._kdtree.query(ego_xy)
            if dist <= self.CENTERLINE_TOLERANCE:
                return False

        return True
