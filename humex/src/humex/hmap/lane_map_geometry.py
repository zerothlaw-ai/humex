"""Pure-function 2D polyline geometry helpers used by LaneMap v2.

Everything here is z-agnostic (planar) and stateless. The builder uses these
to resample centerlines, synthesise parallel boundaries, and find content-
aware split points; the query layer uses `frenet_project` to map a world
(x, y) onto a lane's centerline.

All functions take and return `(x, y)` 2-tuples or lists thereof. Z is
preserved on `LaneMapPoint` outputs by callers that care; in this module
we only do 2D math.
"""
from __future__ import annotations

from typing import List, Tuple
import math

from .lane_map import LaneMapPoint


# ---- arc-length parameterisation ----------------------------------------


def cumulative_arc_length(points: List[LaneMapPoint]) -> List[float]:
    """Cumulative 2D arc-length along the polyline. `out[0] == 0.0`,
    `out[-1] == total_length`. Empty input → empty output."""
    if not points:
        return []
    out = [0.0]
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        out.append(out[-1] + math.hypot(b.x - a.x, b.y - a.y))
    return out


def total_length(points: List[LaneMapPoint]) -> float:
    if len(points) < 2:
        return 0.0
    return cumulative_arc_length(points)[-1]


def _interp(a: LaneMapPoint, b: LaneMapPoint, t: float) -> LaneMapPoint:
    """Lerp between a and b at parameter t in [0, 1]. Preserves z."""
    return LaneMapPoint(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t,
    )


def resample_at_arc(
    points: List[LaneMapPoint], target_step: float
) -> List[LaneMapPoint]:
    """Resample a polyline at uniform arc-length steps.

    Returns a list of points at arc positions 0, step, 2·step, …, total_length.
    The endpoint is always emitted (even if not on a step boundary). The first
    point is always the original start point.

    Empty / single-point input is returned unchanged."""
    if len(points) < 2:
        return list(points)

    arc = cumulative_arc_length(points)
    L = arc[-1]
    if L <= 0.0:
        return [points[0]]

    step = max(0.1, target_step)  # guard against 0
    n_steps = max(1, int(math.floor(L / step)))

    out: List[LaneMapPoint] = []
    seg_idx = 0
    for k in range(n_steps + 1):
        s = min(k * step, L)
        # advance seg_idx so arc[seg_idx] <= s <= arc[seg_idx+1]
        while seg_idx + 1 < len(arc) and arc[seg_idx + 1] < s:
            seg_idx += 1
        if seg_idx + 1 >= len(arc):
            out.append(points[-1])
            continue
        seg_len = arc[seg_idx + 1] - arc[seg_idx]
        if seg_len <= 0:
            out.append(points[seg_idx])
        else:
            t = (s - arc[seg_idx]) / seg_len
            out.append(_interp(points[seg_idx], points[seg_idx + 1], t))

    # If we stopped before the true endpoint by more than a tiny epsilon,
    # append it so callers always have a polyline that ends where it should.
    if len(out) >= 1 and math.hypot(out[-1].x - points[-1].x, out[-1].y - points[-1].y) > 0.05:
        out.append(points[-1])
    return out


# ---- parallel offset ----------------------------------------------------


def _normal_at(points: List[LaneMapPoint], i: int) -> Tuple[float, float]:
    """Unit left-normal at point i along the polyline. Uses the average of
    incoming and outgoing tangents at interior points; the appropriate end
    tangent at the endpoints. Left-normal = (-ty, tx) for tangent (tx, ty)."""
    n = len(points)
    if n < 2:
        return (0.0, 1.0)
    if i == 0:
        a, b = points[0], points[1]
        tx, ty = b.x - a.x, b.y - a.y
    elif i == n - 1:
        a, b = points[-2], points[-1]
        tx, ty = b.x - a.x, b.y - a.y
    else:
        # average of in and out tangents
        a, b, c = points[i - 1], points[i], points[i + 1]
        tx, ty = (c.x - a.x), (c.y - a.y)
    mag = math.hypot(tx, ty)
    if mag < 1e-9:
        return (0.0, 1.0)
    # left-normal of (tx, ty) is (-ty, tx)
    return (-ty / mag, tx / mag)


def parallel_offset(
    points: List[LaneMapPoint], signed_offset: float
) -> List[LaneMapPoint]:
    """Offset a polyline by `signed_offset` along its left-normal at every
    point. Positive offset → left side; negative → right.

    No clothoid / curvature compensation: at tight curves the inner side may
    self-intersect. Acceptable for v2 (5m segments rarely turn enough to
    cause self-intersection); v3 can add proper offsetting (e.g. Shapely's
    parallel_offset or a clothoid fit).
    """
    out: List[LaneMapPoint] = []
    for i, p in enumerate(points):
        nx, ny = _normal_at(points, i)
        out.append(LaneMapPoint(p.x + nx * signed_offset, p.y + ny * signed_offset, p.z))
    return out


# ---- Frenet projection --------------------------------------------------


def heading_at_arc(points: List[LaneMapPoint], s: float) -> float:
    """Lane heading (radians, atan2 of tangent) at arc position s along the
    centerline. Returns 0.0 for empty / single-point input."""
    if len(points) < 2:
        return 0.0
    arc = cumulative_arc_length(points)
    L = arc[-1]
    s = max(0.0, min(s, L))
    seg_idx = 0
    while seg_idx + 1 < len(arc) and arc[seg_idx + 1] < s:
        seg_idx += 1
    if seg_idx + 1 >= len(arc):
        seg_idx = len(arc) - 2
    a, b = points[seg_idx], points[seg_idx + 1]
    return math.atan2(b.y - a.y, b.x - a.x)


def frenet_project(
    point_xy: Tuple[float, float], polyline: List[LaneMapPoint]
) -> Tuple[float, float, float]:
    """Project a 2D point onto the polyline. Returns (s, d, heading) where:
        s = arc-length offset of the foot along the polyline
        d = signed lateral distance from polyline (positive = left of travel)
        heading = lane tangent heading at s (radians, atan2)

    The foot is constrained to the polyline (clamped at segment endpoints).
    Ranking uses the Euclidean distance from the point to the foot (so a
    point whose true perpendicular falls on segment k is correctly handled
    even though earlier segments might be artificially "close" to their
    clamped endpoints).

    Returns (0.0, +inf, 0.0) for empty / single-point polylines so callers
    can filter on |d|.
    """
    if len(polyline) < 2:
        return (0.0, float("inf"), 0.0)

    px, py = point_xy
    best_s = 0.0
    best_d = float("inf")
    best_dist = float("inf")
    best_heading = 0.0
    cum_s = 0.0

    for i in range(len(polyline) - 1):
        a, b = polyline[i], polyline[i + 1]
        ax, ay = a.x, a.y
        bx, by = b.x, b.y
        ex, ey = bx - ax, by - ay
        seg_len2 = ex * ex + ey * ey
        if seg_len2 < 1e-12:
            continue
        seg_len = math.sqrt(seg_len2)
        # parameter t of perpendicular foot along [a, b], clamped to [0, 1]
        t = ((px - ax) * ex + (py - ay) * ey) / seg_len2
        was_clamped = t < 0.0 or t > 1.0
        t_clamped = max(0.0, min(1.0, t))
        fx = ax + t_clamped * ex
        fy = ay + t_clamped * ey
        # Euclidean distance to the (possibly clamped) foot — used both as
        # ranking key and (when clamped) as the unsigned d we report. When
        # NOT clamped, d is the signed perpendicular so callers can filter
        # on side. When clamped, signed d isn't well-defined for this
        # segment (the foot is the endpoint, not on the line through it),
        # so we report Euclidean distance with arbitrary positive sign.
        dist = math.hypot(px - fx, py - fy)
        if dist < best_dist:
            best_dist = dist
            if was_clamped:
                best_d = dist
            else:
                # left-normal of (ex, ey) is (-ey, ex)/seg_len
                nx, ny = -ey / seg_len, ex / seg_len
                best_d = (px - fx) * nx + (py - fy) * ny
            best_s = cum_s + t_clamped * seg_len
            best_heading = math.atan2(ey, ex)
        cum_s += seg_len

    return (best_s, best_d, best_heading)


# ---- content-aware split ------------------------------------------------


def heading_break_indices(
    points: List[LaneMapPoint], threshold_deg: float
) -> List[int]:
    """Return the indices of polyline points where the local heading change
    exceeds `threshold_deg`. Used by the builder to split a source lane into
    pieces before fixed-arc resampling.

    The endpoints (0 and len-1) are NEVER returned — those are implicit
    breaks. Only interior pivot points are reported."""
    if len(points) < 3:
        return []
    threshold_rad = math.radians(threshold_deg)
    breaks: List[int] = []
    prev_heading: float | None = None
    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        seg_len = math.hypot(b.x - a.x, b.y - a.y)
        if seg_len < 1e-6:
            continue
        h = math.atan2(b.y - a.y, b.x - a.x)
        if prev_heading is not None:
            delta = _angle_diff(h, prev_heading)
            if abs(delta) > threshold_rad:
                # The break is at point i-1 (the pivot between the two
                # differing tangents). 0 and len-1 are never reported.
                if 0 < i - 1 < len(points) - 1:
                    breaks.append(i - 1)
        prev_heading = h
    return breaks


def _angle_diff(a: float, b: float) -> float:
    """Smallest signed delta from angle b to angle a, in radians, in (-pi, pi]."""
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d <= -math.pi:
        d += 2 * math.pi
    return d


def split_at_indices(
    points: List[LaneMapPoint], split_indices: List[int]
) -> List[List[LaneMapPoint]]:
    """Split a polyline at the given interior indices, INCLUSIVE on both
    sides (each split point is the last point of one piece AND the first
    point of the next, so successive pieces share an endpoint).

    Empty split list returns `[points]` unchanged."""
    if not split_indices:
        return [list(points)]
    pieces: List[List[LaneMapPoint]] = []
    sorted_idx = sorted(set(split_indices))
    prev = 0
    for idx in sorted_idx:
        if idx <= prev or idx >= len(points) - 1:
            continue
        pieces.append(list(points[prev : idx + 1]))
        prev = idx
    pieces.append(list(points[prev:]))
    return pieces
