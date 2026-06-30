"""Per-frame predicted PET to the most dangerous cross/oncoming conflicting vehicle.

Uses the lane_map crossing-lane geometry to find vehicles on lanes that
physically cross ego's near-future corridor, computes the conflict point where
ego's path crosses each such lane, and reports the MINIMUM predicted PET
(post-encroachment time) over those vehicles.

PET here is an *instantaneous, constant-velocity* estimate: each agent's
predicted time-to-arrival at the conflict point is signed arc-distance / current
speed, and PET = |t_ego - t_veh|. It is stateless per frame, NOT the post-hoc
trajectory PET (which would need future frames).

Because signalized intersections phase ego and cross-traffic apart, MOST frames
legitimately return inf (ego stopped, the conflicting vehicle stopped, or no
real crossing) — that is correct "no one is encroaching" behaviour, not a miss.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.hmap.lane_map_geometry import frenet_project, heading_at_arc, total_length

# Heading-class bands on normalized |Δheading| in [0, 180] degrees.
_SAME_DIR_MAX_DEG = 45.0    # [0, 45)      -> same direction (dropped)
_ONCOMING_MIN_DEG = 135.0   # (135, 180]   -> oncoming; [45, 135] -> cross


class ConflictingVehiclePet(MonitorBase):
    """Minimum predicted PET (s) to a cross/oncoming vehicle conflicting with ego's path this frame; inf if none, None if ego absent.

    OUTPUT_TYPE: FLOAT

    Computes, per frame, an instantaneous constant-velocity PET (post-encroachment
    time) to each vehicle whose lane crosses ego's reachable corridor, and returns
    the smallest (most dangerous) one. Stateless; NOT a post-hoc trajectory PET.

    Params (from DAG YAML):
        conflict_types (list): Which conflict geometries to consider — multi-select
            of "cross" (perpendicular-ish) and "oncoming" (anti-parallel). Default
            both. Same-direction overlaps are always dropped.
        corridor_horizon_m (float): Forward distance (m) to search ego's
            reachable corridor for crossing lanes. Default 50.0.
        min_speed (float): Speed (m/s) below which an agent is treated as stopped
            (not encroaching). Default 0.1.

    Returns (per frame):
        float: minimum PET in seconds over all conflicting vehicles; the most
            dangerous (smallest) gap. Smaller = worse (like ttc_front_vehicle).
        float('inf'): evaluated, but no encroaching conflict — no candidate
            crossing lane, no real centerline crossing, ego stopped, all
            conflicting vehicles stopped/leaving, or no lane_map sidecar.
        None: NOT evaluated — ego absent from the frame, or conflict_types empty.

    Known limitation: a stopped ego returns inf ("no danger while moving
    through"). Gap-acceptance while waiting at a stop/yield is a separate metric.
    """

    OUTPUT_TYPE = OutputType.FLOAT
    PARAMS = [
        {"name": "conflict_types", "type": "string[]", "default": ["cross", "oncoming"],
         "description": "Conflict geometries to consider: cross and/or oncoming",
         "allowed_values": ["cross", "oncoming"],
         "multi_select": True},
        {"name": "corridor_horizon_m", "type": "float", "default": 50.0,
         "description": "Forward distance (m) to search ego's reachable corridor for crossing lanes"},
        {"name": "min_speed", "type": "float", "default": 0.1,
         "description": "Speed (m/s) below which an agent is treated as stopped (no encroachment)"},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        # Normalize conflict_types (accept list or single string), keep only allowed.
        raw = self.params.get("conflict_types", ["cross", "oncoming"])
        if isinstance(raw, str):
            names = {raw} if raw else set()
        elif isinstance(raw, list):
            names = {str(s) for s in raw if s}
        else:
            names = set()
        self.conflict_types = {n for n in names if n in ("cross", "oncoming")}
        self.corridor_horizon_m = float(self.params.get("corridor_horizon_m", 50.0))
        self.min_speed = float(self.params.get("min_speed", 0.1))

        # Lazy geometry index — the lane_map is static across frames.
        self._indexed = False
        self._lm = None
        self._by_source = {}     # source_key -> [LaneMapLane] sorted by s_start
        self._seg_to_key = {}    # segment id -> source_key
        self._flat_cache = {}    # source_key -> [LaneMapPoint]  (concatenated centerline)
        self._line_cache = {}    # source_key -> shapely LineString | None
        self._cp_cache = {}      # (key_a, key_b) -> [(x, y), ...] intersection points

    # ---- geometry index (built once) ------------------------------------

    def _ensure_index(self):
        if self._indexed:
            return self._lm is not None
        self._indexed = True
        self._lm = self.lane_map  # MonitorBase property: LaneMap or None
        if self._lm is None:
            return False
        for seg_id, lane in self._lm.lanes.items():
            # Unset source_lane_id (v1 lanes / connectors): the slice is its own
            # standalone source. Use a unique negative key so it can't collide
            # with a real positive source id.
            key = lane.source_lane_id if lane.source_lane_id else -(seg_id + 1)
            self._seg_to_key[seg_id] = key
            self._by_source.setdefault(key, []).append(lane)
        for lanes in self._by_source.values():
            lanes.sort(key=lambda lane: lane.s_start)
        return True

    def _source_flat(self, key):
        """Concatenated centerline (list of LaneMapPoint) for a whole source lane."""
        cached = self._flat_cache.get(key)
        if cached is not None:
            return cached
        pts = []
        for lane in self._by_source.get(key, []):
            for seg in lane.center_line:          # public field, no private helpers
                for p in seg:
                    if not pts or pts[-1].x != p.x or pts[-1].y != p.y:
                        pts.append(p)
        self._flat_cache[key] = pts
        return pts

    def _source_line(self, key):
        if key in self._line_cache:
            return self._line_cache[key]
        from shapely.geometry import LineString
        flat = self._source_flat(key)
        line = LineString([(p.x, p.y) for p in flat]) if len(flat) >= 2 else None
        self._line_cache[key] = line
        return line

    def _lane_heading(self, seg_id):
        """Tangent heading (rad) at the midpoint of seg's source lane, or None."""
        key = self._seg_to_key.get(seg_id)
        if key is None:
            return None
        flat = self._source_flat(key)
        if len(flat) < 2:
            return None
        return heading_at_arc(flat, total_length(flat) / 2.0)

    def _conflict_point(self, key_a, key_b, ref_xy):
        """Nearest-to-ref intersection of two source centerlines, or None."""
        ckey = (key_a, key_b)
        pts = self._cp_cache.get(ckey)
        if pts is None:
            la, lb = self._source_line(key_a), self._source_line(key_b)
            pts = []
            if la is not None and lb is not None and la.intersects(lb):
                inter = la.intersection(lb)
                if inter.geom_type == "Point":
                    pts = [(inter.x, inter.y)]
                elif hasattr(inter, "geoms"):
                    pts = [(g.x, g.y) for g in inter.geoms if g.geom_type == "Point"]
            self._cp_cache[ckey] = pts
        if not pts:
            return None
        return min(pts, key=lambda p: (p[0] - ref_xy[0]) ** 2 + (p[1] - ref_xy[1]) ** 2)

    @staticmethod
    def _to_rad(yaw):
        """Normalize a heading that may be in degrees (|yaw|>10) to radians."""
        if yaw is None:
            return None
        return math.radians(yaw) if abs(yaw) > 10.0 else yaw

    @staticmethod
    def _hdelta(a, b):
        """Normalized heading delta in [0, pi]."""
        return abs((a - b + math.pi) % (2 * math.pi) - math.pi)

    def _classify(self, dtheta):
        deg = math.degrees(dtheta)
        if deg < _SAME_DIR_MAX_DEG:
            return "same"
        if deg > _ONCOMING_MIN_DEG:
            return "oncoming"
        return "cross"

    # ---- per-frame ------------------------------------------------------

    def calculate(self):
        """Minimum predicted PET to a conflicting cross/oncoming vehicle this frame.

        Returns:
            float: min PET (s); inf when no encroaching conflict.
            None: ego absent, or conflict_types empty.
        """
        from shapely.geometry import LineString, Point

        ego = self.curr_frame.get_ego(self.scenario)
        if ego is None:
            return None
        if not self.conflict_types:
            return None
        if not self._ensure_index():
            return float('inf')  # no lane_map sidecar — can't compute

        amap = self.scenario.map

        ego_speed = ego.sp.velocity.norm()
        if ego_speed is None or ego_speed < self.min_speed:
            return float('inf')  # stopped ego: no "moving through" conflict

        ego_pos = ego.sp.position.to_tuple()
        ego_xy = ego_pos[:2]
        ego_yaw = self._to_rad(ego.sp.heading.yaw if ego.sp.heading else None)
        ego_seg = amap.find_closest_lane(ego_pos, heading=ego_yaw)
        if ego_seg is None:
            return float('inf')
        ego_key = self._seg_to_key.get(ego_seg)

        # Candidate conflict lanes: ego's current lane + forward-reachable corridor,
        # then the union of crossing lanes over that corridor, filtered by heading.
        corridor = [ego_seg] + [r for r in amap.get_reachable_lanes(ego_seg, self.corridor_horizon_m)
                                if r != ego_seg]
        crossing = {}  # crossing source_key -> corridor lane (cl) that crosses it
        for cl in corridor:
            cl_head = self._lane_heading(cl)
            if cl_head is None:
                continue
            for cid in amap.get_crossing_lanes(cl):
                cid_head = self._lane_heading(cid)
                if cid_head is None:
                    continue
                if self._classify(self._hdelta(cl_head, cid_head)) in self.conflict_types:
                    k = self._seg_to_key.get(cid)
                    if k is not None and k not in crossing:
                        crossing[k] = cl
        if not crossing:
            return float('inf')

        best = float('inf')
        for obj_id, obj in self.curr_frame.obj_list.items():
            if obj_id == self.scenario.ego_id:
                continue
            v = obj.sp.velocity.norm()
            if v is None or v < self.min_speed:
                continue  # stopped vehicle: not encroaching

            obj_pos = obj.sp.position.to_tuple()
            obj_xy = obj_pos[:2]
            obj_yaw = self._to_rad(obj.sp.heading.yaw if obj.sp.heading else None)

            # Vehicle -> lane via containing lanes (heading-aware); match one whose
            # source crosses ego's corridor.
            veh_key = None
            for c in amap.find_containing_lanes(obj_pos, heading=obj_yaw):
                k = self._seg_to_key.get(c)
                if k in crossing:
                    veh_key = k
                    break
            if veh_key is None:
                continue

            cl = crossing[veh_key]
            cl_key = self._seg_to_key.get(cl)
            cp = self._conflict_point(cl_key, veh_key, ego_xy)
            if cp is None:
                continue  # polygons overlap but centerlines don't actually cross

            # Ego forward path: ego_seg source ++ crossing corridor lane source
            # (cl is downstream on ego's route, so this is ego's travel direction).
            ego_flat = self._source_flat(ego_key)
            ego_path_pts = [(p.x, p.y) for p in ego_flat]
            if cl_key != ego_key:
                ego_path_pts += [(p.x, p.y) for p in self._source_flat(cl_key)]
            if len(ego_path_pts) < 2:
                continue
            ego_line = LineString(ego_path_pts)
            d_ego = ego_line.project(Point(cp)) - ego_line.project(Point(ego_xy))
            if d_ego <= 0:
                continue  # conflict point behind ego — already passed it

            # Vehicle distance to CP along its source lane, oriented by its heading.
            veh_line = self._source_line(veh_key)
            veh_flat = self._source_flat(veh_key)
            if veh_line is None or len(veh_flat) < 2:
                continue
            d_raw = veh_line.project(Point(cp)) - veh_line.project(Point(obj_xy))
            _, _, veh_tan = frenet_project(obj_xy, veh_flat)
            if obj_yaw is not None and math.cos(obj_yaw - veh_tan) < 0:
                d_veh = -d_raw  # vehicle travels against the source polyline ordering
            else:
                d_veh = d_raw
            if d_veh <= 0:
                continue  # vehicle has passed / is moving away from the conflict point

            t_ego = d_ego / ego_speed
            t_veh = d_veh / v
            pet = abs(t_ego - t_veh)
            if pet < best:
                best = pet

        return best
