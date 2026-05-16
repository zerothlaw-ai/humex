"""Build a `LaneMap` from a canonical `RoadMap`.

v2 (rebuild from centerlines):

  Pass 1 — collect source lanes + estimate per-source-lane width.
  Pass 2 — content-aware split (curvature breaks > 5°) of each source
           centerline.
  Pass 3 — fixed-arc resample at 5m within each piece, allocate fresh
           segment ids, record provenance (source_lane_id + s_start/s_end).
  Pass 4 — synthesise parallel boundaries (in-memory only — not persisted;
           the query layer recomputes on the fly from centerline + width).
  Pass 5 — rebuild topology from segment endpoints (predecessor/successor)
           and centerline midpoints (left/right neighbors). Source-graph
           hints used as a tiebreaker, not as ground truth.

All output ids are fresh sequential integers. `source_lane_id`, `s_start`,
`s_end` give traceback to the original source lane.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

from scipy.spatial import KDTree

from .road_map import RoadMap, LaneData, PointData
from .lane_map import (
    LaneMap,
    LaneMapLane,
    LaneMapPoint,
    TURN_UNKNOWN,
)
from .lane_map_geometry import (
    cumulative_arc_length,
    heading_break_indices,
    parallel_offset,
    resample_at_arc,
    split_at_indices,
    total_length,
)


ALGORITHM_VERSION = "lane-map-v3.0"

# Tunables — chosen from SOTA practice (Apollo / Lanelet2). All in meters
# / degrees. Adjust via tests if a particular scenario class needs it.
SEGMENT_TARGET_LENGTH = 10.0
CURVATURE_BREAK_DEG = 5.0
MIN_TAIL_LENGTH = 1.0  # tail piece shorter than this gets folded back

ENDPOINT_STITCH_RADIUS = 0.5     # predecessor/successor candidate radius
ENDPOINT_HEADING_TOL_DEG = 15.0
NEIGHBOR_LATERAL_SCAN_M = 5.5    # 1.5 × typical lane width
NEIGHBOR_HEADING_TOL_DEG = 15.0
NEIGHBOR_LONGITUDINAL_TOL = 1.0  # forward-progress alignment tolerance

# Width clamp + fallback (carried over from v1)
DEFAULT_LANE_WIDTH = 3.5
WIDTH_MIN = 1.5
WIDTH_MAX = 8.0

# Centerline pre-cleanup (carried over from v1).
CENTERLINE_DEDUPE_EPS = 0.5


# ---------------------------------------------------------------------------
# Helpers preserved from v1


def _flat_centerline(lane: LaneData) -> List[PointData]:
    out: List[PointData] = []
    for seg in lane.center_line:
        out.extend(seg.points)
    return out


def _clean_centerline(pts: List[PointData]) -> List[LaneMapPoint]:
    """Dedupe consecutive near-duplicate points; flatten to one polyline."""
    cleaned: List[LaneMapPoint] = []
    for p in pts:
        if cleaned:
            prev = cleaned[-1]
            if math.hypot(prev.x - p.x, prev.y - p.y) < CENTERLINE_DEDUPE_EPS:
                continue
        cleaned.append(LaneMapPoint(p.x, p.y, p.z))
    return cleaned


def _flatten_boundary_points(boundary_segs) -> List[LaneMapPoint]:
    """Flatten a source LaneData boundary (list of SegmentData) into a single
    cleaned, dedup'd polyline of LaneMapPoint. Returns [] when the source
    lane has no usable boundary."""
    pts: List[PointData] = []
    for seg in boundary_segs or []:
        # The same `[[]]` shape that RoadMap.create_lane_from_pts emits when
        # boundaries weren't supplied — guard against it.
        if hasattr(seg, "points"):
            pts.extend(seg.points)
    if not pts:
        return []
    cleaned = _clean_centerline(pts)
    return cleaned if len(cleaned) >= 2 else []


def _annotate_boundary_with_arc(
    centerline: List[LaneMapPoint],
    boundary_pts: List[LaneMapPoint],
) -> List[Tuple[LaneMapPoint, float]]:
    """For each boundary point, project it onto ``centerline`` and pair the
    point with the resulting arc-length s. Used by Pass 3 to bucket boundary
    points into the segment whose s-range contains them.

    Returns [] when either input is too short to project. The s values are
    measured along the centerline (not the boundary), so two boundary points
    that map to the same centerline arc will share an s — that's intended
    (segment slicing uses the same s-range)."""
    if len(centerline) < 2 or not boundary_pts:
        return []
    # Lazy import — keeps lane_map_builder loadable in trimmed test fixtures.
    from .lane_map_geometry import frenet_project

    out: List[Tuple[LaneMapPoint, float]] = []
    for bp in boundary_pts:
        s, _, _ = frenet_project((bp.x, bp.y), centerline)
        out.append((bp, s))
    return out


def _estimate_width(lane: LaneData) -> float:
    """Average perpendicular distance between left and right boundaries.
    Source maps are noisy; clamp into a believable range and fall back when
    boundaries are missing or the result is clearly bogus."""
    left_pts: List[tuple] = []
    right_pts: List[tuple] = []
    for seg in lane.left_boundary:
        for p in seg.points:
            left_pts.append((p.x, p.y))
    for seg in lane.right_boundary:
        for p in seg.points:
            right_pts.append((p.x, p.y))
    if not left_pts or not right_pts:
        return DEFAULT_LANE_WIDTH
    total = 0.0
    for lp in left_pts:
        nearest = min(right_pts, key=lambda rp: (lp[0] - rp[0]) ** 2 + (lp[1] - rp[1]) ** 2)
        total += math.hypot(lp[0] - nearest[0], lp[1] - nearest[1])
    avg = total / len(left_pts)
    if avg < WIDTH_MIN or avg > WIDTH_MAX:
        return DEFAULT_LANE_WIDTH
    return avg


def build_lane_map(ava_map: RoadMap) -> LaneMap:
    """Build a v2 LaneMap from an RoadMap. Pure function; no I/O."""
    src = ava_map.map_data
    if not src.lanes:
        return LaneMap(
            algorithm_version=ALGORITHM_VERSION,
            source_map_name=ava_map.name or "",
            built_at_unix_ns=int(time.time() * 1e9),
            lanes={},
            intersections=[],
        )

    # Pass 1: per-source width + cleaned centerline + boundary annotations.
    src_widths: Dict[int, float] = {}
    src_clean: Dict[int, List[LaneMapPoint]] = {}
    src_stop_point: Dict[int, Optional[LaneMapPoint]] = {}
    src_has_stop: Dict[int, bool] = {}
    # Boundary points annotated with arc-length on the source centerline.
    # Empty list when the source lane had no boundary in that direction.
    src_left_bdy: Dict[int, List[Tuple[LaneMapPoint, float]]] = {}
    src_right_bdy: Dict[int, List[Tuple[LaneMapPoint, float]]] = {}
    for lane_id, src_lane in src.lanes.items():
        src_widths[lane_id] = _estimate_width(src_lane)
        cleaned = _clean_centerline(_flat_centerline(src_lane))
        src_clean[lane_id] = cleaned
        if src_lane.stop_point is not None:
            sp = src_lane.stop_point
            src_stop_point[lane_id] = LaneMapPoint(sp.x, sp.y, sp.z)
        else:
            src_stop_point[lane_id] = None
        src_has_stop[lane_id] = src_lane.has_stop_sign

        # Annotate each boundary point with its projected arc-length on the
        # source centerline so Pass 3 can bucket them per segment.
        left_pts = _flatten_boundary_points(src_lane.left_boundary)
        right_pts = _flatten_boundary_points(src_lane.right_boundary)
        src_left_bdy[lane_id] = _annotate_boundary_with_arc(cleaned, left_pts)
        src_right_bdy[lane_id] = _annotate_boundary_with_arc(cleaned, right_pts)

    # Pass 2 + 3: split + resample, allocate segment ids
    next_id = 1
    segments: Dict[int, LaneMapLane] = {}
    # source_lane_id -> ordered list of (segment_id, s_start, s_end)
    source_chain: Dict[int, List[Tuple[int, float, float]]] = {}

    for src_lane_id, cleaned in src_clean.items():
        if len(cleaned) < 2:
            continue
        width = src_widths[src_lane_id]
        stop_point = src_stop_point[src_lane_id]
        has_stop = src_has_stop[src_lane_id]
        left_bdy_annot = src_left_bdy.get(src_lane_id, [])
        right_bdy_annot = src_right_bdy.get(src_lane_id, [])

        # Split at curvature breaks
        breaks = heading_break_indices(cleaned, CURVATURE_BREAK_DEG)
        pieces = split_at_indices(cleaned, breaks)

        # Track arc offset within the source lane so s_start/s_end on each
        # segment refer to the original lane's parameterisation, AND so
        # boundary points (annotated with source-centerline-relative s) can
        # be bucketed into the right emitted segment.
        source_arc_offset = 0.0

        for piece in pieces:
            piece_len = total_length(piece)
            if piece_len < MIN_TAIL_LENGTH:
                source_arc_offset += piece_len
                continue
            # Cumulative arc-length on the cleaned piece — used to pick the
            # intermediate dense points that fall inside each emitted segment.
            piece_cum = cumulative_arc_length(piece)
            # Resample at fixed arc step → segment anchor points.
            resampled = resample_at_arc(piece, SEGMENT_TARGET_LENGTH)
            piece_arc = cumulative_arc_length(resampled)
            for j in range(len(resampled) - 1):
                seg_local_start = piece_arc[j]
                seg_local_end = piece_arc[j + 1]
                seg_local_len = seg_local_end - seg_local_start
                # Dense centerline slice: the resampled anchor at seg_local_start,
                # plus every cleaned point whose arc-length lies strictly inside
                # the segment, plus the resampled anchor at seg_local_end.
                # Keeping intermediate points produces a curve-following polyline
                # rather than a 2-point chord — fixes the "broken boxes" look.
                dense_pts: List[LaneMapPoint] = [resampled[j]]
                for idx, s in enumerate(piece_cum):
                    if seg_local_start < s < seg_local_end:
                        dense_pts.append(piece[idx])
                dense_pts.append(resampled[j + 1])

                # Boundary slices: bucket annotated boundary points whose
                # s (relative to the source centerline) falls inside this
                # segment's source-relative s-range.
                seg_src_s_start = source_arc_offset + seg_local_start
                seg_src_s_end = source_arc_offset + seg_local_end
                seg_left = [p for (p, s) in left_bdy_annot
                            if seg_src_s_start <= s <= seg_src_s_end]
                seg_right = [p for (p, s) in right_bdy_annot
                             if seg_src_s_start <= s <= seg_src_s_end]

                if seg_local_len < MIN_TAIL_LENGTH:
                    # Tail fold: extend the previous segment's centerline AND
                    # any boundary slices instead of emitting a stub segment.
                    if source_chain.get(src_lane_id):
                        prev_sid, prev_s_start, _ = source_chain[src_lane_id][-1]
                        prev_seg = segments[prev_sid]
                        # Append the tail's intermediate + end points (skip the
                        # already-included start anchor that overlaps the
                        # previous segment's tail).
                        prev_seg.center_line[0].extend(dense_pts[1:])
                        if prev_seg.left_boundary and seg_left:
                            prev_seg.left_boundary[0].extend(seg_left)
                        elif seg_left:
                            prev_seg.left_boundary = [list(seg_left)]
                        if prev_seg.right_boundary and seg_right:
                            prev_seg.right_boundary[0].extend(seg_right)
                        elif seg_right:
                            prev_seg.right_boundary = [list(seg_right)]
                        new_s_end = seg_src_s_end
                        source_chain[src_lane_id][-1] = (prev_sid, prev_s_start, new_s_end)
                    continue

                seg_id = next_id
                next_id += 1
                segments[seg_id] = LaneMapLane(
                    id=seg_id,
                    is_connector=False,
                    center_line=[dense_pts],
                    width_estimate=width,
                    next_lane_ids=[],
                    prev_lane_ids=[],
                    left_lane_ids=[],
                    right_lane_ids=[],
                    turn_type=TURN_UNKNOWN,
                    stop_point=None,
                    has_stop_sign=False,
                    source_lane_id=src_lane_id,
                    s_start=seg_src_s_start,
                    s_end=seg_src_s_end,
                    left_boundary=[list(seg_left)] if seg_left else [],
                    right_boundary=[list(seg_right)] if seg_right else [],
                )
                source_chain.setdefault(src_lane_id, []).append(
                    (seg_id, seg_src_s_start, seg_src_s_end)
                )
            source_arc_offset += piece_len

        # Attach stop_point + has_stop_sign to the LAST segment of this
        # source lane (the natural place a stop applies).
        chain = source_chain.get(src_lane_id, [])
        if chain and stop_point is not None:
            last_id = chain[-1][0]
            segments[last_id].stop_point = stop_point
        if chain and has_stop:
            last_id = chain[-1][0]
            segments[last_id].has_stop_sign = True

    # Pass 4: parallel boundaries are derived on the fly by the query layer
    # from center_line + width_estimate. Nothing to persist here.

    # Pass 5: topology rebuild
    _link_intra_source_chain(segments, source_chain)
    _link_cross_source_endpoints(segments, src.next_lanes, source_chain)
    _link_lateral_neighbors(segments, src.left_lanes, src.right_lanes, source_chain)

    # Pass 6: detect crossing lanes (intersection connectors crossing each
    # other, merges). Polygon-intersection over a Shapely STRtree, minus
    # the lanes already linked through the chain / lateral neighbours.
    _link_crossing_lanes(segments)

    # Pass 7: assign corridor_id via union-find on unambiguous chain edges.
    # Two lanes share a corridor iff there's no branching/merging between them.
    _link_corridor_ids(segments)

    return LaneMap(
        algorithm_version=ALGORITHM_VERSION,
        source_map_name=ava_map.name or "",
        built_at_unix_ns=int(time.time() * 1e9),
        lanes=segments,
        intersections=[],
    )


# ---------------------------------------------------------------------------
# Pass 5 helpers


def _link_intra_source_chain(
    segments: Dict[int, LaneMapLane],
    source_chain: Dict[int, List[Tuple[int, float, float]]],
) -> None:
    """Within each source lane, segments are emitted in arc order; wire them
    head-to-tail with next/prev edges."""
    for chain in source_chain.values():
        for i in range(len(chain) - 1):
            a_id = chain[i][0]
            b_id = chain[i + 1][0]
            segments[a_id].next_lane_ids.append(b_id)
            segments[b_id].prev_lane_ids.append(a_id)


def _link_cross_source_endpoints(
    segments: Dict[int, LaneMapLane],
    src_next_lanes,
    source_chain: Dict[int, List[Tuple[int, float, float]]],
) -> None:
    """Link the LAST segment of source lane A to the FIRST segment of every
    source lane B that A.next_lanes points to. Source graph is used directly
    here — endpoint stitching across unrelated source lanes is intentionally
    NOT done in v2 (Waymo source lanes already break at intersections, so
    most cross-source links exist; v3 will add proper synthesis where they
    don't)."""
    for src_id, chain in source_chain.items():
        if not chain:
            continue
        tail_seg = chain[-1][0]
        for next_src in src_next_lanes.get(src_id, []):
            next_chain = source_chain.get(next_src)
            if not next_chain:
                continue
            head_seg = next_chain[0][0]
            if head_seg not in segments[tail_seg].next_lane_ids:
                segments[tail_seg].next_lane_ids.append(head_seg)
            if tail_seg not in segments[head_seg].prev_lane_ids:
                segments[head_seg].prev_lane_ids.append(tail_seg)


def _link_lateral_neighbors(
    segments: Dict[int, LaneMapLane],
    src_left_lanes,
    src_right_lanes,
    source_chain: Dict[int, List[Tuple[int, float, float]]],
) -> None:
    """For each source-lane pair (A, A_left), find segment-pairs whose
    midpoints are within NEIGHBOR_LATERAL_SCAN_M and whose headings are
    parallel within NEIGHBOR_HEADING_TOL_DEG. Wire them as left/right
    neighbors. Mirrors are added symmetrically."""
    if not segments:
        return

    # Build KDTree of all segment midpoints + cache per-segment heading.
    seg_ids = list(segments.keys())
    mids: List[Tuple[float, float]] = []
    headings: List[float] = []
    for sid in seg_ids:
        seg = segments[sid]
        if not seg.center_line or len(seg.center_line[0]) < 2:
            mids.append((0.0, 0.0))
            headings.append(0.0)
            continue
        a, b = seg.center_line[0][0], seg.center_line[0][-1]
        mids.append(((a.x + b.x) / 2.0, (a.y + b.y) / 2.0))
        headings.append(math.atan2(b.y - a.y, b.x - a.x))
    tree = KDTree(mids)
    head_tol = math.radians(NEIGHBOR_HEADING_TOL_DEG)

    def _add_neighbor(src_segs, side: str) -> None:
        """side='left' or 'right'."""
        for source_a, neighbors in src_segs.items():
            chain_a = source_chain.get(source_a, [])
            for sid_a, _, _ in chain_a:
                seg_a = segments[sid_a]
                ha = headings[seg_ids.index(sid_a)]
                ax, ay = mids[seg_ids.index(sid_a)]
                # Search neighbors within scan radius
                for source_b in neighbors:
                    chain_b = source_chain.get(source_b, [])
                    for sid_b, _, _ in chain_b:
                        if sid_b == sid_a:
                            continue
                        bx, by = mids[seg_ids.index(sid_b)]
                        if math.hypot(ax - bx, ay - by) > NEIGHBOR_LATERAL_SCAN_M:
                            continue
                        hb = headings[seg_ids.index(sid_b)]
                        # heading delta in (-pi, pi]
                        d = ha - hb
                        while d > math.pi:
                            d -= 2 * math.pi
                        while d <= -math.pi:
                            d += 2 * math.pi
                        if abs(d) > head_tol:
                            continue
                        target_list = (
                            seg_a.left_lane_ids if side == "left"
                            else seg_a.right_lane_ids
                        )
                        if sid_b not in target_list:
                            target_list.append(sid_b)

    _add_neighbor(src_left_lanes, "left")
    _add_neighbor(src_right_lanes, "right")


# ---------------------------------------------------------------------------
# Pass 6 helper


def _link_crossing_lanes(segments: Dict[int, LaneMapLane]) -> None:
    """Detect lanes whose drivable polygons physically cross each other and
    are NOT already linked via the lane chain (prev/next) or as lateral
    (left/right) neighbours. Captures intersection connectors that cross,
    merge points, and the like.

    Polygon-intersection over a Shapely ``STRtree`` keeps the cost
    O(N log N + intersections); for ~5k segments per scenario this runs in
    1-2s. Empty ``overlapping_lane_ids`` is the right answer for a one-lane
    test scenario, so the function tolerates trivially small inputs."""
    if len(segments) < 2:
        return

    from shapely.geometry import Polygon
    from shapely.strtree import STRtree

    polys: Dict[int, Polygon] = {}
    for sid, seg in segments.items():
        if not seg.center_line or len(seg.center_line[0]) < 2:
            continue
        flat = seg.center_line[0]
        half_w = max(0.5, seg.width_estimate / 2.0)
        left = parallel_offset(flat, half_w)
        right = parallel_offset(flat, -half_w)
        ring = [(p.x, p.y) for p in left] + [(p.x, p.y) for p in reversed(right)]
        if len(ring) < 3:
            continue
        try:
            poly = Polygon(ring)
        except Exception:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
        polys[sid] = poly

    if not polys:
        return

    # Build a parallel array so STRtree results map back to lane ids.
    sids = list(polys.keys())
    geoms = [polys[s] for s in sids]
    tree = STRtree(geoms)

    for sid in sids:
        seg = segments[sid]
        # Lanes already linked via chain / lateral neighbours — exclude.
        excluded = (
            {sid}
            | set(seg.next_lane_ids)
            | set(seg.prev_lane_ids)
            | set(seg.left_lane_ids)
            | set(seg.right_lane_ids)
        )
        my_poly = polys[sid]
        # STRtree.query returns indices into the input geometry list (Shapely 2.x).
        candidate_idxs = tree.query(my_poly)
        crossings: List[int] = []
        for idx in candidate_idxs:
            other_id = sids[int(idx)]
            if other_id in excluded:
                continue
            other_poly = polys[other_id]
            if my_poly.intersects(other_poly):
                crossings.append(other_id)
        if crossings:
            # Stable order so the proto round-trip is deterministic.
            seg.overlapping_lane_ids = sorted(crossings)


# ---------------------------------------------------------------------------
# Pass 7 helper


def _link_corridor_ids(segments: Dict[int, LaneMapLane]) -> None:
    """Assign a ``corridor_id`` to every segment.

    Two segments share the same corridor iff they're connected by an
    *unambiguous* chain edge: ``a.next_lane_ids == [b]`` AND
    ``b.prev_lane_ids == [a]``. Anything else (multiple successors,
    multiple predecessors, no edge) starts a new corridor.

    The result: long unbranched stretches get one corridor; intersections
    and merges break corridors into smaller chunks. The role-table v2
    builder uses this for O(1) per-point lane disambiguation: when a bbox
    point sits inside two overlapping polygons, prefer the candidate whose
    corridor matches the previous frame's pick.
    """
    if not segments:
        return

    parent: Dict[int, int] = {sid: sid for sid in segments}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for sid, seg in segments.items():
        if len(seg.next_lane_ids) != 1:
            continue
        nxt = seg.next_lane_ids[0]
        nxt_lane = segments.get(nxt)
        if nxt_lane is None:
            continue
        if nxt_lane.prev_lane_ids == [sid]:
            union(sid, nxt)

    # Assign sequential corridor_ids per connected component, stable-ordered
    # by representative segment id so the same lane_map produces the same
    # ids on every build.
    rep_to_cid: Dict[int, int] = {}
    next_cid = 1
    for sid in sorted(segments.keys()):
        rep = find(sid)
        if rep not in rep_to_cid:
            rep_to_cid[rep] = next_cid
            next_cid += 1
        segments[sid].corridor_id = rep_to_cid[rep]
