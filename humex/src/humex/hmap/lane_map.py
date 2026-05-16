"""Cleaned, source-agnostic lane representation derived from an RoadMap.

The LaneMap is built once at scenario import time (Stage 2 of the conversion-
task pipeline) by `lane_map_builder.build_lane_map(ava_map)`, persisted as
the sidecar `lane_map.pb`, and consumed by monitors that have been migrated
to the new graph. Monitors still relying on the source RoadMap continue to
work; the LaneMap is opt-in.

What it gives over RoadMap:
  - Synthesised intersection connectors (most source maps either omit these
    or represent them sparsely).
  - Cleaned, re-sampled centerlines.
  - Width estimates per lane.
  - Explicit `Intersection` groups for "is the agent in a junction" queries.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from scipy.spatial import KDTree


# Mirror map_pb2's TurnType values to keep monitors free of proto deps.
TURN_UNKNOWN = 0
TURN_STRAIGHT = 1
TURN_LEFT = 2
TURN_RIGHT = 3
TURN_U_TURN = 4


def _angle_norm(a: float) -> float:
    """Normalise an angle (radians) to (-pi, pi]."""
    while a > math.pi:
        a -= 2 * math.pi
    while a <= -math.pi:
        a += 2 * math.pi
    return a


def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """Point-in-polygon via ray casting. Polygon is a closed list of (x, y)
    pairs (last point need not equal first)."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        # Edge crosses horizontal ray from (x, y)
        if (yi > y) != (yj > y):
            x_intersect = xj + (y - yj) * (xi - xj) / (yi - yj)
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def _polyline_length(points: List["LaneMapPoint"]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        total += math.hypot(b.x - a.x, b.y - a.y)
    return total


@dataclass
class LaneMapPoint:
    x: float
    y: float
    z: float = 0.0


@dataclass
class LaneMapLane:
    id: int
    is_connector: bool = False
    center_line: List[List[LaneMapPoint]] = field(default_factory=list)
    width_estimate: float = 3.5
    next_lane_ids: List[int] = field(default_factory=list)
    prev_lane_ids: List[int] = field(default_factory=list)
    left_lane_ids: List[int] = field(default_factory=list)
    right_lane_ids: List[int] = field(default_factory=list)
    turn_type: int = TURN_UNKNOWN
    stop_point: Optional[LaneMapPoint] = None
    has_stop_sign: bool = False
    # v2 provenance: which source lane this segment came from and its arc-length
    # span within that source. Zero/unset on v1 lane_maps and on synthesised
    # connectors. Used for debugging misclassifications and tracing.
    source_lane_id: int = 0
    s_start: float = 0.0
    s_end: float = 0.0
    # v2.1: lanes whose drivable polygon physically crosses this lane's,
    # excluding self / prev / next / left / right. Captures genuine
    # crossings (intersection connectors crossing each other, merge points).
    # Empty on v1 / v2.0 lane_maps.
    overlapping_lane_ids: List[int] = field(default_factory=list)
    # v2.2: maximal-unambiguous-chain id. Two lanes share a corridor_id iff
    # they're part of one drivable strip with no branches/merges between
    # them (no choice when walking next_lane_ids). Used for O(1) per-point
    # disambiguation in the role-table v2 builder. 0 = unset (older maps).
    corridor_id: int = 0
    # v3.0: per-segment fitted boundaries derived from the source RoadMap's
    # left_boundary / right_boundary polylines (when they exist). Same
    # shape as center_line: outer = segments (almost always 1), inner =
    # ordered points along the boundary. Empty on v1/v2 lane_maps and on
    # source lanes that didn't carry boundaries — the runtime polygon
    # falls back to centerline +/- width_estimate / 2 in that case.
    left_boundary: List[List[LaneMapPoint]] = field(default_factory=list)
    right_boundary: List[List[LaneMapPoint]] = field(default_factory=list)


@dataclass
class LaneMapIntersection:
    id: int
    lane_ids: List[int] = field(default_factory=list)
    centroid: Optional[LaneMapPoint] = None


class LaneMap:
    """Query surface mirroring RoadMap. Ids are stable with the source map for
    non-connector lanes; synthesised connectors get fresh ids beyond the
    largest source id (`builder` chooses)."""

    def __init__(
        self,
        algorithm_version: str = "lane-map-v1.0",
        source_map_name: str = "",
        built_at_unix_ns: int = 0,
        lanes: Optional[Dict[int, LaneMapLane]] = None,
        intersections: Optional[List[LaneMapIntersection]] = None,
    ) -> None:
        self.algorithm_version = algorithm_version
        self.source_map_name = source_map_name
        self.built_at_unix_ns = built_at_unix_ns
        self.lanes: Dict[int, LaneMapLane] = lanes or {}
        self.intersections: List[LaneMapIntersection] = intersections or []

        # Build on demand. 2D KDTree on centerline points; same convention as
        # RoadMap (z dropped to avoid ego-z-vs-map-z mismatches).
        self._kdtree: Optional[KDTree] = None
        self._kdtree_refs: List[Tuple[int, int, int]] = []
        self._intersection_by_lane: Optional[Dict[int, int]] = None

        # v2 query caches: derived once on first query, invalidated only by
        # mutating the lanes dict (which monitors don't do).
        self._flat_cache: Dict[int, List[LaneMapPoint]] = {}
        self._polygon_cache: Dict[int, List[Tuple[float, float]]] = {}

    # ---- spatial index ----

    def _build_kdtree(self) -> None:
        points: List[Tuple[float, float]] = []
        refs: List[Tuple[int, int, int]] = []
        for lane_id, lane in self.lanes.items():
            for seg_idx, seg in enumerate(lane.center_line):
                for pt_idx, pt in enumerate(seg):
                    points.append((pt.x, pt.y))
                    refs.append((lane_id, seg_idx, pt_idx))
        self._kdtree = KDTree(points) if points else None
        self._kdtree_refs = refs

    def find_closest_lane(
        self,
        position: Tuple[float, float, float],
        max_distance: Optional[float] = None,
        heading: Optional[float] = None,
    ) -> Optional[int]:
        """Locate the lane that contains `position` (Apollo-style):

        1. KDTree narrows to up to K=10 candidate lanes by closest centerline
           sample.
        2. Frenet projection per candidate yields (s, d, lane_heading).
        3. Filter: |d| < width/2 + slack AND |Δheading| < 30° (when heading
           supplied; otherwise heading filter is skipped).
        4. Polygon-membership confirms with a true point-in-polygon test on
           the lane's drivable polygon (centerline ± width/2).
        5. Score remaining candidates by |d| + 0.5·|Δheading| (radians);
           pick the lowest. Ties broken by smaller |d|.

        This is deliberately stricter than v1: when no candidate's polygon
        contains the point, it falls back to the candidate with smallest
        |d| (so vehicles slightly outside the painted lane still get an
        answer, matching the v1 behaviour for those edge cases).
        """
        # Lazy import — keeps module loadable in test fixtures that build
        # lanes by hand without any geometry.
        from .lane_map_geometry import frenet_project

        if self._kdtree is None:
            self._build_kdtree()
        if self._kdtree is None:
            return None

        # Pass 1: candidates from KDTree
        k = min(10, len(self._kdtree_refs))
        distances, pt_indices = self._kdtree.query(position[:2], k=k)
        if k == 1:
            distances = [distances]
            pt_indices = [pt_indices]
        if max_distance is not None and distances[0] > max_distance:
            return None

        # Distinct candidate lane ids in the order of nearest sample first
        seen: set = set()
        candidates: List[int] = []
        for pt_idx in pt_indices:
            lid = self._kdtree_refs[pt_idx][0]
            if lid not in seen:
                seen.add(lid)
                candidates.append(lid)
        if not candidates:
            return None

        head_tol = math.radians(30.0)
        slack = 0.5  # extra lateral tolerance beyond the painted half-width

        # Pass 2-3-4-5
        best_lane: Optional[int] = None
        best_score = float("inf")
        # Fallback ranking when no polygon contains the point
        fb_best_lane: Optional[int] = None
        fb_best_dabs = float("inf")

        for lid in candidates:
            lane = self.lanes.get(lid)
            if lane is None:
                continue
            flat = self._flat_centerline_for(lid)
            if len(flat) < 2:
                continue
            half_w = max(0.5, lane.width_estimate / 2.0)
            s, d, lane_h = frenet_project(position[:2], flat)
            d_abs = abs(d)

            # Filters
            if d_abs > half_w + slack:
                # too far laterally — record for fallback only if closer
                if d_abs < fb_best_dabs:
                    fb_best_dabs = d_abs
                    fb_best_lane = lid
                continue
            if heading is not None:
                # Heading delta in [0, pi]; allow anti-parallel for one-way
                # streets only when caller hasn't asked for direction-aware
                # matching by passing `heading`.
                dh = abs(_angle_norm(heading - lane_h))
                if dh > head_tol:
                    if d_abs < fb_best_dabs:
                        fb_best_dabs = d_abs
                        fb_best_lane = lid
                    continue
            else:
                dh = 0.0

            # Polygon confirm
            poly = self._lane_polygon(lid)
            if poly and not _point_in_polygon(position[:2], poly):
                if d_abs < fb_best_dabs:
                    fb_best_dabs = d_abs
                    fb_best_lane = lid
                continue

            score = d_abs + 0.5 * dh
            if score < best_score:
                best_score = score
                best_lane = lid

        if best_lane is not None:
            return best_lane
        # Nothing passed the strict filters — return the best fallback
        # candidate (smallest |d|) so callers still get an answer.
        return fb_best_lane

    def find_containing_lanes(
        self,
        position: Tuple[float, float, float],
        heading: Optional[float] = None,
        lateral_slack: float = 0.5,
    ) -> List[int]:
        """Return EVERY lane whose drivable polygon contains ``position``
        (or is within ``lateral_slack`` meters of containing it).

        Same KDTree narrow + heading filter as :meth:`find_closest_lane`,
        but instead of scoring and returning one winner, return every lane
        that passes the polygon membership test. Empty list when off-road.

        ``lateral_slack`` widens the polygon by that many meters on each
        side, matching the slack baked into :meth:`find_closest_lane`'s
        Frenet filter so the two queries agree on borderline points (a
        bbox corner right at the lane edge counts as inside). Set to 0 for
        strict polygon containment.
        """
        if self._kdtree is None:
            self._build_kdtree()
        if self._kdtree is None:
            return []

        k = min(10, len(self._kdtree_refs))
        distances, pt_indices = self._kdtree.query(position[:2], k=k)
        if k == 1:
            distances = [distances]
            pt_indices = [pt_indices]

        seen: set = set()
        candidates: List[int] = []
        for pt_idx in pt_indices:
            lid = self._kdtree_refs[pt_idx][0]
            if lid not in seen:
                seen.add(lid)
                candidates.append(lid)
        if not candidates:
            return []

        from .lane_map_geometry import frenet_project

        head_tol = math.radians(30.0)
        hits: List[int] = []
        for lid in candidates:
            lane = self.lanes.get(lid)
            if lane is None:
                continue
            flat = self._flat_centerline_for(lid)
            if len(flat) < 2:
                continue
            half_w = max(0.5, lane.width_estimate / 2.0)

            # Frenet d gives signed lateral offset; pair it with the
            # polygon test for the strict case, and widen with slack.
            s, d, lane_h = frenet_project(position[:2], flat)
            if abs(d) > half_w + lateral_slack:
                continue
            if heading is not None:
                dh = abs(_angle_norm(heading - lane_h))
                if dh > head_tol:
                    continue
            # Strict polygon test as a final confirm when slack=0; with
            # slack > 0 the Frenet-d filter is the membership criterion
            # (a slack-expanded polygon == |d| <= half_w + slack).
            if lateral_slack <= 0:
                poly = self._lane_polygon(lid)
                if not poly or not _point_in_polygon(position[:2], poly):
                    continue
            hits.append(lid)
        return hits

    def lanes_in_corridor(self, corridor_id: int) -> List[int]:
        """All lane ids sharing ``corridor_id``. Returns [] for unknown ids."""
        if corridor_id == 0:
            return []
        return [lid for lid, lane in self.lanes.items()
                if lane.corridor_id == corridor_id]

    def project_onto_lane_path(
        self,
        point: Tuple[float, float],
        lane_path: List[int],
    ) -> Optional[float]:
        """Project a 2D point onto the concatenation of `lane_path` lanes
        and return the cumulative arc-length s. Returns None if no segment
        in the path is nearby (|d| > 20m) or the path is empty."""
        from .lane_map_geometry import frenet_project

        if not lane_path:
            return None

        cum_offset = 0.0
        best_s: Optional[float] = None
        best_d_abs = 20.0

        for lid in lane_path:
            flat = self._flat_centerline_for(lid)
            if len(flat) < 2:
                continue
            s, d, _ = frenet_project(point, flat)
            d_abs = abs(d)
            if d_abs < best_d_abs:
                best_d_abs = d_abs
                best_s = cum_offset + s
            cum_offset += _polyline_length(flat)
        return best_s

    def get_reachable_lanes(
        self, lane_id: int, max_distance: float
    ) -> List[int]:
        """BFS forward over next_lane_ids from `lane_id` until cumulative
        traversed centerline length reaches `max_distance` meters. Returns
        the visited lane ids in BFS order (starting with `lane_id`)."""
        start = self.lanes.get(lane_id)
        if start is None:
            return []
        visited: set = {lane_id}
        order: List[int] = [lane_id]
        queue: deque = deque(
            [(lane_id, _polyline_length(self._flat_centerline_for(lane_id)))]
        )
        while queue:
            cur, traversed = queue.popleft()
            if traversed >= max_distance:
                continue
            cur_lane = self.lanes.get(cur)
            if cur_lane is None:
                continue
            for nxt in cur_lane.next_lane_ids:
                if nxt in visited or nxt not in self.lanes:
                    continue
                visited.add(nxt)
                order.append(nxt)
                queue.append(
                    (nxt, traversed + _polyline_length(self._flat_centerline_for(nxt)))
                )
        return order

    # ---- internal: cache helpers ----

    def _flat_centerline_for(self, lane_id: int) -> List[LaneMapPoint]:
        """Flatten LaneMapLane.center_line (list of segments) into a single
        polyline, cached. Most v2 lanes only have one segment; this still
        handles v1 lanes with multiple segments."""
        cached = self._flat_cache.get(lane_id)
        if cached is not None:
            return cached
        lane = self.lanes.get(lane_id)
        if lane is None:
            self._flat_cache[lane_id] = []
            return []
        flat: List[LaneMapPoint] = []
        for seg in lane.center_line:
            flat.extend(seg)
        self._flat_cache[lane_id] = flat
        return flat

    def _lane_polygon(self, lane_id: int) -> List[Tuple[float, float]]:
        """Return the lane's drivable polygon (left boundary forward, right
        boundary reversed) as a list of (x, y) pairs, cached.

        Two paths:

        1. **Real boundary** (v3.0+): when the segment carries fitted
           ``left_boundary`` / ``right_boundary`` slices from the source
           RoadMap, use them directly. The polygon hugs the actual road
           edge — including asymmetric shoulders, lane drops, etc.

        2. **Synthesized fallback**: parallel-offset of the dense centerline
           at ``width_estimate / 2``. Used when the source lane lacked
           boundaries. Now smooth because v3.0 segments keep intermediate
           centerline samples (not 2-point chords).
        """
        cached = self._polygon_cache.get(lane_id)
        if cached is not None:
            return cached
        lane = self.lanes.get(lane_id)
        if lane is None:
            self._polygon_cache[lane_id] = []
            return []

        # 1. Boundary path
        left_pts: List[LaneMapPoint] = []
        for seg in lane.left_boundary:
            left_pts.extend(seg)
        right_pts: List[LaneMapPoint] = []
        for seg in lane.right_boundary:
            right_pts.extend(seg)
        if len(left_pts) >= 2 and len(right_pts) >= 2:
            poly: List[Tuple[float, float]] = [(p.x, p.y) for p in left_pts]
            poly.extend((p.x, p.y) for p in reversed(right_pts))
            self._polygon_cache[lane_id] = poly
            return poly

        # 2. Synthesized fallback
        from .lane_map_geometry import parallel_offset
        flat = self._flat_centerline_for(lane_id)
        if len(flat) < 2:
            self._polygon_cache[lane_id] = []
            return []
        half_w = max(0.5, lane.width_estimate / 2.0)
        left = parallel_offset(flat, half_w)
        right = parallel_offset(flat, -half_w)
        poly = [(p.x, p.y) for p in left]
        poly.extend((p.x, p.y) for p in reversed(right))
        self._polygon_cache[lane_id] = poly
        return poly

    def _lane_direction_at(
        self, lane_id: int, seg_idx: int, pt_idx: int
    ) -> Optional[Tuple[float, float]]:
        lane = self.lanes.get(lane_id)
        if lane is None or seg_idx >= len(lane.center_line):
            return None
        seg = lane.center_line[seg_idx]
        if pt_idx + 1 < len(seg):
            a, b = seg[pt_idx], seg[pt_idx + 1]
        elif pt_idx > 0:
            a, b = seg[pt_idx - 1], seg[pt_idx]
        else:
            return None
        dx, dy = b.x - a.x, b.y - a.y
        mag = math.hypot(dx, dy)
        if mag < 1e-9:
            return None
        return (dx / mag, dy / mag)

    # ---- graph queries ----

    def get_lane(self, lane_id: int) -> Optional[LaneMapLane]:
        return self.lanes.get(lane_id)

    def next_lanes(self, lane_id: int) -> List[int]:
        lane = self.lanes.get(lane_id)
        return list(lane.next_lane_ids) if lane else []

    def prev_lanes(self, lane_id: int) -> List[int]:
        lane = self.lanes.get(lane_id)
        return list(lane.prev_lane_ids) if lane else []

    def left_lanes(self, lane_id: int) -> List[int]:
        lane = self.lanes.get(lane_id)
        return list(lane.left_lane_ids) if lane else []

    def right_lanes(self, lane_id: int) -> List[int]:
        lane = self.lanes.get(lane_id)
        return list(lane.right_lane_ids) if lane else []

    # ---- intersection queries ----

    def get_intersection_for_lane(self, lane_id: int) -> Optional[LaneMapIntersection]:
        if self._intersection_by_lane is None:
            self._intersection_by_lane = {}
            for inter in self.intersections:
                for lid in inter.lane_ids:
                    self._intersection_by_lane[lid] = inter.id
        inter_id = self._intersection_by_lane.get(lane_id)
        if inter_id is None:
            return None
        for inter in self.intersections:
            if inter.id == inter_id:
                return inter
        return None

    def is_lane_in_intersection(self, lane_id: int) -> bool:
        return self.get_intersection_for_lane(lane_id) is not None

    # ---- proto serialization ----

    @classmethod
    def from_proto(cls, pb: "lane_map_pb2.LaneMapData") -> "LaneMap":  # noqa: F821
        lanes: Dict[int, LaneMapLane] = {}
        for lane_id, pb_lane in pb.lanes.items():
            center_line: List[List[LaneMapPoint]] = []
            for seg in pb_lane.center_line:
                center_line.append(
                    [LaneMapPoint(p.x, p.y, p.z) for p in seg.points]
                )
            left_boundary: List[List[LaneMapPoint]] = []
            for seg in pb_lane.left_boundary:
                left_boundary.append(
                    [LaneMapPoint(p.x, p.y, p.z) for p in seg.points]
                )
            right_boundary: List[List[LaneMapPoint]] = []
            for seg in pb_lane.right_boundary:
                right_boundary.append(
                    [LaneMapPoint(p.x, p.y, p.z) for p in seg.points]
                )
            stop_point = None
            if pb_lane.HasField("stop_point"):
                sp = pb_lane.stop_point
                stop_point = LaneMapPoint(sp.x, sp.y, sp.z)
            lanes[lane_id] = LaneMapLane(
                id=pb_lane.id,
                is_connector=pb_lane.is_connector,
                center_line=center_line,
                width_estimate=pb_lane.width_estimate,
                next_lane_ids=list(pb_lane.next_lane_ids),
                prev_lane_ids=list(pb_lane.prev_lane_ids),
                left_lane_ids=list(pb_lane.left_lane_ids),
                right_lane_ids=list(pb_lane.right_lane_ids),
                turn_type=pb_lane.turn_type,
                stop_point=stop_point,
                has_stop_sign=pb_lane.has_stop_sign,
                source_lane_id=pb_lane.source_lane_id,
                s_start=pb_lane.s_start,
                s_end=pb_lane.s_end,
                overlapping_lane_ids=list(pb_lane.overlapping_lane_ids),
                corridor_id=pb_lane.corridor_id,
                left_boundary=left_boundary,
                right_boundary=right_boundary,
            )
        intersections: List[LaneMapIntersection] = []
        for pb_inter in pb.intersections:
            centroid = None
            if pb_inter.HasField("centroid"):
                c = pb_inter.centroid
                centroid = LaneMapPoint(c.x, c.y, c.z)
            intersections.append(
                LaneMapIntersection(
                    id=pb_inter.id,
                    lane_ids=list(pb_inter.lane_ids),
                    centroid=centroid,
                )
            )
        return cls(
            algorithm_version=pb.algorithm_version,
            source_map_name=pb.source_map_name,
            built_at_unix_ns=pb.built_at_unix_ns,
            lanes=lanes,
            intersections=intersections,
        )

    def to_proto(self):
        # Imported lazily so this module is usable without humex installed
        # in environments where only RoadMap is needed.
        from humex.proto import lane_map_pb2, map_pb2

        pb = lane_map_pb2.LaneMapData(
            algorithm_version=self.algorithm_version,
            source_map_name=self.source_map_name,
            built_at_unix_ns=self.built_at_unix_ns,
        )
        for lane_id, lane in self.lanes.items():
            pb_lane = pb.lanes[lane_id]
            pb_lane.id = lane.id
            pb_lane.is_connector = lane.is_connector
            for seg in lane.center_line:
                pb_seg = pb_lane.center_line.add()
                for pt in seg:
                    pb_pt = pb_seg.points.add()
                    pb_pt.x, pb_pt.y, pb_pt.z = pt.x, pt.y, pt.z
            pb_lane.width_estimate = lane.width_estimate
            pb_lane.next_lane_ids.extend(lane.next_lane_ids)
            pb_lane.prev_lane_ids.extend(lane.prev_lane_ids)
            pb_lane.left_lane_ids.extend(lane.left_lane_ids)
            pb_lane.right_lane_ids.extend(lane.right_lane_ids)
            pb_lane.turn_type = lane.turn_type
            if lane.stop_point is not None:
                pb_lane.stop_point.x = lane.stop_point.x
                pb_lane.stop_point.y = lane.stop_point.y
                pb_lane.stop_point.z = lane.stop_point.z
            pb_lane.has_stop_sign = lane.has_stop_sign
            pb_lane.source_lane_id = lane.source_lane_id
            pb_lane.s_start = lane.s_start
            pb_lane.s_end = lane.s_end
            pb_lane.overlapping_lane_ids.extend(lane.overlapping_lane_ids)
            pb_lane.corridor_id = lane.corridor_id
            for seg in lane.left_boundary:
                pb_seg = pb_lane.left_boundary.add()
                for pt in seg:
                    pb_pt = pb_seg.points.add()
                    pb_pt.x, pb_pt.y, pb_pt.z = pt.x, pt.y, pt.z
            for seg in lane.right_boundary:
                pb_seg = pb_lane.right_boundary.add()
                for pt in seg:
                    pb_pt = pb_seg.points.add()
                    pb_pt.x, pb_pt.y, pb_pt.z = pt.x, pt.y, pt.z
        for inter in self.intersections:
            pb_inter = pb.intersections.add()
            pb_inter.id = inter.id
            pb_inter.lane_ids.extend(inter.lane_ids)
            if inter.centroid is not None:
                pb_inter.centroid.x = inter.centroid.x
                pb_inter.centroid.y = inter.centroid.y
                pb_inter.centroid.z = inter.centroid.z
        return pb
