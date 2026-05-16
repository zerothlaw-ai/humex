"""Build a per-frame ego-relative agent role table.

v2: each agent has 5 reference points (centroid + 4 bbox corners). For each
point at each frame, we collect every lane whose drivable polygon contains
the point — usually 1 lane, sometimes more when polygons overlap. We then
*disambiguate* per-(agent, point) using corridor_id continuity: at each
frame pick the candidate that stays in the same drivable strip as the
prior frame's pick. This produces 5 per-agent corridors.

Front/rear detection then becomes a multi-point filter: an agent is a
candidate when ANY of its 5 disambiguated lanes at frame K is in ego's
corridor union. The closest agent wins (centroid arc-length gap, signed).

Pipeline:

  Pass 1 — per (agent, frame, point), call
           ``LaneMap.find_containing_lanes(point, heading)`` and store the
           list of candidate lane ids.

  Pass 2 — per (agent, point), forward-sweep disambiguation using
           corridor_id continuity (with next/prev/lateral fallbacks).
           Build a 5-corridor bundle per agent.

  Pass 3 — per-frame role assignment. For each non-ego agent: candidate iff
           any of the 5 disambiguated lanes at this frame is in ego's
           corridor union. Rank candidates by signed centroid gap on ego's
           centre corridor; min positive = front, min |negative| = rear.

The builder takes the unified :class:`HMap` facade — never the legacy
RoadMap and never a raw LaneMap — so all lane work flows through LaneMap v2.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .hmap import HMap
    from ..components.scenario import Scenario

from .role_table import (
    AgentCorridor,
    AgentLaneFrame,
    AgentRole,
    DistanceRange,
    FrameRoles,
    PointLaneAssignment,
    POINT_NAMES,
    RoleTable,
)


ALGORITHM_VERSION = "role-table-v2.1"

MAX_FORWARD_DISTANCE = 200.0  # meters; beyond this, no front / lead
MAX_REAR_DISTANCE = 100.0     # meters; beyond this, no rear / follow
# v2.1: longitudinal slack added to (ego.length + agent.length) / 2 when
# deciding whether a side-lane agent is "alongside" (overlapping ego's
# bbox lengthwise) vs lead / follow. Absorbs measurement noise so the
# same agent doesn't toggle between roles at the boundary.
ALONGSIDE_SLACK_M = 0.5


def build_role_table(
    scenario: "Scenario",
    hmap: "HMap",
) -> RoleTable:
    if scenario is None or hmap is None:
        raise ValueError("build_role_table requires a Scenario and an HMap")
    if scenario.ego_id is None:
        scenario.assign_ego_id()
    ego_id = scenario.ego_id
    if ego_id is None:
        return RoleTable(algorithm_version=ALGORITHM_VERSION, ego_id=0, frames=[])

    timestamps = list(scenario.timestamps)
    n = len(timestamps)
    if n == 0:
        return RoleTable(algorithm_version=ALGORITHM_VERSION, ego_id=ego_id, frames=[])

    # ---- Pass 1: raw per (agent, frame, point) candidate lane lists ----
    # raw_cands[agent_id][k][p] = list of lane_ids whose polygon contains
    # the agent's reference point ``p`` at frame ``k``. Empty when off-road
    # / agent missing. Also cache the 5 (x, y) points for Pass 3 projection.
    raw_cands: Dict[int, List[List[List[int]]]] = {}
    point_xy: Dict[int, List[Optional[List[Tuple[float, float]]]]] = {}
    for agent_id in scenario.roster:
        raw_cands[agent_id] = [[[], [], [], [], []] for _ in range(n)]
        point_xy[agent_id] = [None] * n

    for k, ts in enumerate(timestamps):
        frame = scenario.frames.get(ts)
        if frame is None:
            continue
        for obj_id, agent in frame.obj_list.items():
            if agent.sp is None:
                continue
            pts = _five_points(agent)
            point_xy.setdefault(obj_id, [None] * n)[k] = pts
            cands_for_frame = []
            for (x, y) in pts:
                # No heading filter — we want SPATIAL membership ("is this
                # corner inside any lane polygon"), not driving-direction
                # match. A merging agent at a 60deg angle still has its
                # leading corner inside the target lane; the 30deg heading
                # filter would reject it. The disambiguation pass uses
                # corridor continuity to pick the agent's actual lane;
                # Pass 3 uses raw_cands directly for corridor-overlap.
                cands = hmap.find_containing_lanes(
                    (x, y, 0.0), heading=None, lateral_slack=0.5
                )
                cands_for_frame.append(list(cands))
            raw_cands.setdefault(obj_id, [[[], [], [], [], []] for _ in range(n)])[k] = cands_for_frame

    # ---- Pass 2: per (agent, point) corridor disambiguation ----
    # disamb[agent_id][k][p] = single chosen lane_id (or 0 = unassigned)
    # corridors[agent_id][p] = ordered_unique list of lane_ids visited
    disamb: Dict[int, List[List[int]]] = {}
    corridors: Dict[int, List[List[int]]] = {}
    for agent_id, per_frame_lists in raw_cands.items():
        # 5 separate disambiguation sweeps, one per point
        per_point_picks = [[0] * n for _ in range(5)]
        per_point_corridors: List[List[int]] = [[] for _ in range(5)]
        for p in range(5):
            sequence = [per_frame_lists[k][p] for k in range(n)]
            picks = _disambiguate_point(sequence, hmap)
            for k, pick in enumerate(picks):
                per_point_picks[p][k] = pick or 0
            per_point_corridors[p] = _ordered_unique_nonzero(picks)
        # transpose for convenient frame-major access: disamb[agent][k][p]
        disamb_agent: List[List[int]] = [
            [per_point_picks[p][k] for p in range(5)] for k in range(n)
        ]
        disamb[agent_id] = disamb_agent
        corridors[agent_id] = per_point_corridors

    # ---- Pass 3: per-frame ego-relative role assignment ----
    ego_corridors = corridors.get(ego_id, [[] for _ in range(5)])
    ego_corridor_union: set = set()
    for c in ego_corridors:
        ego_corridor_union.update(c)

    # s-axis path for centroid arc-length: ego.center_corridor extended both
    # directions with reachable lanes so agents slightly outside ego's
    # actual trajectory still get a sensible projection.
    ego_center_corridor = ego_corridors[0]
    fwd_ext: List[int] = []
    if ego_center_corridor:
        for lid in hmap.get_reachable_lanes(ego_center_corridor[-1], MAX_FORWARD_DISTANCE):
            if lid not in ego_center_corridor and lid not in fwd_ext:
                fwd_ext.append(lid)
    rev_ext: List[int] = []
    if ego_center_corridor:
        rev_raw = _reachable_lanes_backward(
            hmap, ego_center_corridor[0], MAX_REAR_DISTANCE
        )
        rev_ext = [l for l in reversed(rev_raw) if l not in ego_center_corridor]
    s_axis = rev_ext + ego_center_corridor + fwd_ext
    # Add the extensions to the corridor union too — agents in the extension
    # lanes (slightly past where ego's trajectory ends) should still count.
    ego_corridor_union.update(s_axis)

    # ---- Per-frame side-neighbor lookup (v2.1) ----
    # For each frame K, derive ego's immediate left and right neighbour lane
    # from the LaneMap topology of ego's centroid lane at K. The actual
    # side-corridors are built PER FRAME below (one short BFS keyed on the
    # ego-side-lane id, cached so consecutive frames sharing an ego lane
    # don't re-expand). Side roles only fire at frames where ego ACTUALLY
    # has a neighbour on that side — frames without one stay None.
    ego_disamb = disamb.get(ego_id)
    ego_left_per_frame: List[Optional[int]] = [None] * n
    ego_right_per_frame: List[Optional[int]] = [None] * n
    if ego_disamb is not None:
        for k in range(n):
            el = ego_disamb[k][0]  # centroid pick (0 = unassigned)
            if not el:
                continue
            lefts = hmap.left_lanes(el)
            rights = hmap.right_lanes(el)
            if lefts:
                ego_left_per_frame[k] = lefts[0]
            if rights:
                ego_right_per_frame[k] = rights[0]

    # Cache: ego-side-lane id → expanded corridor (list of lane ids)
    side_corridor_cache: Dict[int, List[int]] = {}

    def _side_corridor_for(seed_lane: Optional[int]) -> List[int]:
        if seed_lane is None or seed_lane == 0:
            return []
        cached = side_corridor_cache.get(seed_lane)
        if cached is not None:
            return cached
        visited = [seed_lane]
        fwd_ext: List[int] = []
        for lid in hmap.get_reachable_lanes(seed_lane, MAX_FORWARD_DISTANCE):
            if lid not in visited and lid not in fwd_ext:
                fwd_ext.append(lid)
        rev_raw = _reachable_lanes_backward(
            hmap, seed_lane, MAX_REAR_DISTANCE
        )
        rev_ext = [l for l in reversed(rev_raw) if l not in visited]
        corridor = rev_ext + visited + fwd_ext
        side_corridor_cache[seed_lane] = corridor
        return corridor

    out_frames: List[FrameRoles] = []
    for k, ts in enumerate(timestamps):
        fr = FrameRoles(frame_index=k, timestamp_ns=int(ts))
        frame = scenario.frames.get(ts)
        if frame is None:
            out_frames.append(fr)
            continue
        ego = frame.obj_list.get(ego_id)
        if ego is None or ego.sp is None or not s_axis:
            # Still emit per-agent lane block for this frame (debug / UI).
            _populate_agent_lanes(fr, frame, ego_id, disamb, k)
            out_frames.append(fr)
            continue

        ego_pos2 = (ego.sp.position.x, ego.sp.position.y)
        s_ego = hmap.project_onto_lane_path(ego_pos2, s_axis)
        if s_ego is None:
            _populate_agent_lanes(fr, frame, ego_id, disamb, k)
            out_frames.append(fr)
            continue

        front_best: Optional[Tuple[float, "object"]] = None
        rear_best: Optional[Tuple[float, "object"]] = None

        for obj_id, agent in frame.obj_list.items():
            if obj_id == ego_id or agent.sp is None:
                continue
            agent_raw = raw_cands.get(obj_id)
            if agent_raw is None:
                continue
            # Multi-point filter using RAW per-point candidates (every lane
            # whose polygon contains a corner). This catches merging
            # agents whose disambiguated lane (their primary lane) is the
            # adjacent one but whose leading bbox corner already sits
            # inside ego's corridor.
            five_lists = agent_raw[k]
            if not any(lid in ego_corridor_union
                       for cands in five_lists for lid in cands):
                continue
            a_pos2 = (agent.sp.position.x, agent.sp.position.y)
            s_a = hmap.project_onto_lane_path(a_pos2, s_axis)
            if s_a is None:
                continue
            delta = s_a - s_ego
            if delta > 0.0 and delta <= MAX_FORWARD_DISTANCE:
                if front_best is None or delta < front_best[0]:
                    front_best = (delta, agent)
            elif delta < 0.0 and -delta <= MAX_REAR_DISTANCE:
                if rear_best is None or -delta < -rear_best[0]:
                    rear_best = (delta, agent)

        if front_best is not None:
            gap, agent = front_best
            fr.front = AgentRole(
                agent_id=agent.id,
                distance=_bbox_distance_band(ego, agent),
                s_gap=float(gap),
            )
        if rear_best is not None:
            gap, agent = rear_best
            fr.rear = AgentRole(
                agent_id=agent.id,
                distance=_bbox_distance_band(ego, agent),
                s_gap=float(gap),
            )

        # ---- Side roles (v2.1): per-frame side corridor ----
        # Each side fires only if ego has a neighbour on that side AT THIS
        # frame; corridor expansion is scoped to that immediate neighbour
        # so a faraway right-neighbour from a much later frame doesn't bleed
        # into the early-frame classification.
        left_corr_k  = _side_corridor_for(ego_left_per_frame[k])
        right_corr_k = _side_corridor_for(ego_right_per_frame[k])
        _classify_side(
            fr, side="left",
            side_corridor=left_corr_k,
            side_corridor_set=set(left_corr_k),
            frame=frame, ego=ego, ego_id=ego_id, k=k,
            disamb=disamb, hmap=hmap, ego_pos2=ego_pos2,
        )
        _classify_side(
            fr, side="right",
            side_corridor=right_corr_k,
            side_corridor_set=set(right_corr_k),
            frame=frame, ego=ego, ego_id=ego_id, k=k,
            disamb=disamb, hmap=hmap, ego_pos2=ego_pos2,
        )

        _populate_agent_lanes(fr, frame, ego_id, disamb, k)
        out_frames.append(fr)

    # Build the per-agent corridor list for the proto.
    agent_corridors: List[AgentCorridor] = []
    for agent_id in sorted(corridors.keys()):
        c = corridors[agent_id]
        agent_corridors.append(AgentCorridor(
            agent_id=agent_id,
            center_corridor=list(c[0]),
            front_left_corridor=list(c[1]),
            front_right_corridor=list(c[2]),
            rear_left_corridor=list(c[3]),
            rear_right_corridor=list(c[4]),
        ))

    return RoleTable(
        algorithm_version=ALGORITHM_VERSION,
        ego_id=ego_id,
        frames=out_frames,
        agent_corridors=agent_corridors,
    )


# ---------------------------------------------------------------------------
# helpers


def _populate_agent_lanes(
    fr: FrameRoles,
    frame,
    ego_id: int,
    disamb: Dict[int, List[List[int]]],
    k: int,
) -> None:
    """Fill the per-frame agent_lanes block from the disambiguated picks.
    Includes ego too — useful for the UI and per-agent role queries later."""
    for obj_id in sorted(frame.obj_list.keys()):
        picks = disamb.get(obj_id)
        if picks is None:
            continue
        five = picks[k]
        # Skip purely off-road agents (all 5 zero) to keep the block tight.
        if all(v == 0 for v in five):
            continue
        fr.agent_lanes.append(AgentLaneFrame(
            agent_id=obj_id,
            lanes=PointLaneAssignment(
                center=five[0],
                front_left=five[1],
                front_right=five[2],
                rear_left=five[3],
                rear_right=five[4],
            ),
        ))


def _build_side_corridor(
    ego_side_lane_per_frame: List[Optional[int]],
    hmap,
    fwd_dist: float,
    rear_dist: float,
) -> List[int]:
    """Build a corridor along ego's immediate left or right neighbour lanes.

    Mirrors the centre-corridor construction: ordered_unique of per-frame
    side-neighbour lanes, plus forward / backward reachable extensions
    bookended on the first / last visited side lane. Returns ``[]`` if the
    side has no neighbour anywhere across the trajectory."""
    visited = _ordered_unique(l for l in ego_side_lane_per_frame if l is not None)
    if not visited:
        return []
    fwd_ext: List[int] = []
    for lid in hmap.get_reachable_lanes(visited[-1], fwd_dist):
        if lid not in visited and lid not in fwd_ext:
            fwd_ext.append(lid)
    rev_raw = _reachable_lanes_backward(hmap, visited[0], rear_dist)
    rev_ext = [l for l in reversed(rev_raw) if l not in visited]
    return rev_ext + visited + fwd_ext


def _classify_side(
    fr: FrameRoles,
    *,
    side: str,                      # "left" or "right"
    side_corridor: List[int],
    side_corridor_set: set,
    frame,
    ego,
    ego_id: int,
    k: int,
    disamb: Dict[int, List[List[int]]],
    hmap,
    ego_pos2: Tuple[float, float],
) -> None:
    """Pick lead / alongside / follow on one side and write the result back
    onto the FrameRoles. Mutually exclusive — each side-lane agent ends up
    in exactly one of the three buckets per frame.

    Membership uses the agent's CENTROID disambiguated lane (not the
    multi-point raw candidates used for front/rear). An agent whose body
    is in ego's lane but whose corner briefly clips the side lane should
    NOT be classified as a side neighbour — that role is reserved for
    vehicles whose primary lane is the side lane."""
    if not side_corridor:
        return
    s_ego_side = hmap.project_onto_lane_path(ego_pos2, side_corridor)
    if s_ego_side is None:
        return

    lead_best: Optional[Tuple[float, "object"]] = None
    follow_best: Optional[Tuple[float, "object"]] = None
    alongside_best: Optional[Tuple[float, "object"]] = None

    ego_len = float(getattr(ego, "length", 4.0) or 4.0)

    for obj_id, agent in frame.obj_list.items():
        if obj_id == ego_id or agent.sp is None:
            continue
        agent_disamb = disamb.get(obj_id)
        if agent_disamb is None:
            continue
        # Centroid-only membership: agent's primary (centroid) lane must be
        # in this side's corridor. Index 0 of the per-point pick is the
        # centroid lane (0 = unassigned).
        center_lane = agent_disamb[k][0]
        if not center_lane or center_lane not in side_corridor_set:
            continue
        a_pos2 = (agent.sp.position.x, agent.sp.position.y)
        s_a = hmap.project_onto_lane_path(a_pos2, side_corridor)
        if s_a is None:
            continue
        delta = s_a - s_ego_side
        agent_len = float(getattr(agent, "length", 4.0) or 4.0)
        threshold = (ego_len + agent_len) / 2.0 + ALONGSIDE_SLACK_M
        if abs(delta) <= threshold:
            if alongside_best is None or abs(delta) < abs(alongside_best[0]):
                alongside_best = (delta, agent)
        elif delta > 0.0 and delta <= MAX_FORWARD_DISTANCE:
            if lead_best is None or delta < lead_best[0]:
                lead_best = (delta, agent)
        elif delta < 0.0 and -delta <= MAX_REAR_DISTANCE:
            if follow_best is None or -delta < -follow_best[0]:
                follow_best = (delta, agent)

    def _make(best):
        if best is None:
            return None
        gap, agent = best
        return AgentRole(
            agent_id=agent.id,
            distance=_bbox_distance_band(ego, agent),
            s_gap=float(gap),
        )

    if side == "left":
        fr.left_lead = _make(lead_best)
        fr.left_alongside = _make(alongside_best)
        fr.left_follow = _make(follow_best)
    else:
        fr.right_lead = _make(lead_best)
        fr.right_alongside = _make(alongside_best)
        fr.right_follow = _make(follow_best)


def _disambiguate_point(
    per_frame_cands: List[List[int]],
    hmap,
) -> List[Optional[int]]:
    """For one (agent, point), walk frame-by-frame and pick the lane that
    keeps continuity. Strategy:

      1. Stay on the same lane if it's still a candidate.
      2. Stay in the same corridor (corridor_id match).
      3. Cross-corridor traversal: prefer next_lane_ids of the prior pick.
      4. Lateral neighbour (lane change): prefer left/right neighbour.
      5. Last-resort: first candidate.

    At frame 0 (no history) use one-step lookahead: prefer a candidate that
    also appears at frame 1 — this stabilises the choice when several lanes
    are equally plausible at the very start.
    """
    n = len(per_frame_cands)
    picks: List[Optional[int]] = [None] * n
    prev_lane: Optional[int] = None
    prev_corr: int = 0

    for k in range(n):
        cands = per_frame_cands[k]
        if not cands:
            picks[k] = None
            continue

        if prev_lane is not None and prev_lane in cands:
            picks[k] = prev_lane
        elif prev_lane is not None:
            # 2. Same corridor — O(1) preferred path.
            same_corr = [c for c in cands
                         if prev_corr != 0 and hmap.get_corridor_id(c) == prev_corr]
            if same_corr:
                picks[k] = same_corr[0]
            else:
                # 3. Chain via next/prev.
                chain_set = set(hmap.next_lanes(prev_lane)) | set(hmap.prev_lanes(prev_lane))
                chain = [c for c in cands if c in chain_set]
                if chain:
                    picks[k] = chain[0]
                else:
                    # 4. Lateral neighbour (lane change).
                    lateral_set = set(hmap.left_lanes(prev_lane)) | set(hmap.right_lanes(prev_lane))
                    lat = [c for c in cands if c in lateral_set]
                    picks[k] = lat[0] if lat else cands[0]
        else:
            # First frame, no history. One-step lookahead.
            ahead: set = set()
            if k + 1 < n:
                ahead = set(per_frame_cands[k + 1])
            shared = [c for c in cands if c in ahead]
            picks[k] = shared[0] if shared else cands[0]

        prev_lane = picks[k]
        prev_corr = hmap.get_corridor_id(prev_lane) if prev_lane else 0
    return picks


def _heading_radians(yaw: float) -> float:
    """Match BoundingBox2D.update's degree-vs-radian heuristic."""
    if abs(yaw) > 10.0:
        return math.radians(yaw)
    return float(yaw)


def _five_points(obj) -> List[Tuple[float, float]]:
    """Return [center, front_left, front_right, rear_left, rear_right]
    as 2D (x, y) tuples in the world frame. Mirrors BoundingBox2D.update
    so we don't depend on whether obj.bbox happens to have been refreshed."""
    sp = obj.sp
    cx, cy = sp.position.x, sp.position.y
    yaw = _heading_radians(sp.heading.yaw)
    half_l = obj.length / 2.0
    half_w = obj.width / 2.0
    cos_h, sin_h = math.cos(yaw), math.sin(yaw)
    locals_ = [
        (0.0, 0.0),                  # center
        (+half_l, +half_w),          # front-left
        (+half_l, -half_w),          # front-right
        (-half_l, +half_w),          # rear-left
        (-half_l, -half_w),          # rear-right
    ]
    return [
        (cx + lx * cos_h - ly * sin_h, cy + lx * sin_h + ly * cos_h)
        for (lx, ly) in locals_
    ]


def _bbox_corners(obj) -> List[Tuple[float, float]]:
    """4 corners in CCW order: front-left, front-right, rear-right, rear-left.
    A valid polygon ring (Shapely needs non-self-intersecting). Used by the
    bbox distance band — NOT the same order as :func:`_five_points` (which
    is centroid + 4 corners in a UI-friendly order, not a polygon ring)."""
    sp = obj.sp
    cx, cy = sp.position.x, sp.position.y
    yaw = _heading_radians(sp.heading.yaw)
    half_l = obj.length / 2.0
    half_w = obj.width / 2.0
    cos_h, sin_h = math.cos(yaw), math.sin(yaw)
    ring = [
        (+half_l, +half_w),  # front-left
        (+half_l, -half_w),  # front-right
        (-half_l, -half_w),  # rear-right
        (-half_l, +half_w),  # rear-left
    ]
    return [
        (cx + lx * cos_h - ly * sin_h, cy + lx * sin_h + ly * cos_h)
        for (lx, ly) in ring
    ]


def _reachable_lanes_backward(
    hmap, start_lane: int, max_distance: float
) -> List[int]:
    """BFS over prev_lane_ids from ``start_lane`` until cumulative centerline
    length reaches ``max_distance``. Returns lanes in BFS order EXCLUDING
    ``start_lane``."""
    visited = {start_lane}
    out: List[int] = []
    queue = deque([(start_lane, 0.0)])
    while queue:
        cur, traversed = queue.popleft()
        if traversed >= max_distance:
            continue
        lane = hmap.get_lane(cur)
        if lane is None:
            continue
        length = 0.0
        if lane.center_line and len(lane.center_line[0]) >= 2:
            pts = lane.center_line[0]
            for i in range(1, len(pts)):
                length += math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
        for prev_id in lane.prev_lane_ids:
            if prev_id in visited:
                continue
            visited.add(prev_id)
            out.append(prev_id)
            queue.append((prev_id, traversed + length))
    return out


def _ordered_unique(it):
    seen: set = set()
    out: List[int] = []
    for x in it:
        if x is None or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _ordered_unique_nonzero(it):
    """Like _ordered_unique but skips None and 0 (= unassigned)."""
    seen: set = set()
    out: List[int] = []
    for x in it:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _bbox_distance_band(ego, agent) -> DistanceRange:
    """closest = Shapely polygon distance (0.0 if intersecting);
    farthest = max corner-to-corner Euclidean distance."""
    ego_corners = _bbox_corners(ego)
    a_corners = _bbox_corners(agent)
    try:
        from shapely.geometry import Polygon
        ego_poly = Polygon(ego_corners)
        a_poly = Polygon(a_corners)
        if not ego_poly.is_valid:
            ego_poly = ego_poly.buffer(0)
        if not a_poly.is_valid:
            a_poly = a_poly.buffer(0)
        closest = float(ego_poly.distance(a_poly))
    except Exception:
        closest = min(
            math.hypot(ex - ax, ey - ay)
            for (ex, ey) in ego_corners
            for (ax, ay) in a_corners
        )
    farthest = max(
        math.hypot(ex - ax, ey - ay)
        for (ex, ey) in ego_corners
        for (ax, ay) in a_corners
    )
    return DistanceRange(closest=closest, farthest=farthest)
