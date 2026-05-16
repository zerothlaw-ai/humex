from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, DefaultDict
from collections import defaultdict, deque
from scipy.spatial import KDTree
import math
import random


@dataclass
class PointData:
    x: float
    y: float
    z: float

@dataclass
class SegmentData:
    points: List[PointData] = field(default_factory=list)

@dataclass
class LaneData:
    id: int
    center_line: List[SegmentData] = field(default_factory=list)
    left_boundary: List[SegmentData] = field(default_factory=list)
    right_boundary: List[SegmentData] = field(default_factory=list)
    speed_limit: float = 0.0  # Speed limit in m/s
    stop_point: Optional[PointData] = None  # Where vehicle must stop
    has_stop_sign: bool = False  # Whether lane has a stop sign

@dataclass
class MapData:
    lanes: Dict[int, LaneData] = field(default_factory=dict)
    next_lanes: DefaultDict[int, List[int]] = field(default_factory=lambda: defaultdict(list))
    prev_lanes: DefaultDict[int, List[int]] = field(default_factory=lambda: defaultdict(list))
    left_lanes: DefaultDict[int, List[int]] = field(default_factory=lambda: defaultdict(list))
    right_lanes: DefaultDict[int, List[int]] = field(default_factory=lambda: defaultdict(list))



class RoadMap:
    def __init__(self, map_name: str, map_data: Optional[MapData] = None):
        self.name = map_name
        self.map_data = map_data if map_data else MapData()
        self.lane_id_counter = 0

        # For spatial queries (2D: x, y only for correct lane finding)
        self._kdtree: Optional[KDTree] = None
        self._kdtree_points: List[Tuple[float, float]] = []
        self._kdtree_refs: List[Tuple[int, int, int]] = []  # (lane_id, seg_idx, pt_idx)

        # Traffic signal data (optional, time-series)
        # Structure: {timestamp: {lane_id: state_value}}
        # Timestamps are int64 nanoseconds
        self.signal_data: Optional[Dict[int, Dict[int, int]]] = None
        self.signal_timestamps: List[int] = []  # Sorted list of signal timestamps (int64 nanoseconds)

    def create_lane_from_pts(self, centerline, left_boundary=None, right_boundary=None, speed_limit=0.0) -> LaneData:
        center_seg, left_seg, right_seg = [], [], []
        center_seg = self._create_seg_from_pts(centerline)
        if left_boundary is not None:
            left_seg = self._create_seg_from_pts(left_boundary)
        if right_boundary is not None:
            right_seg = self._create_seg_from_pts(right_boundary)
        lane_data = LaneData(id=self.lane_id_counter, center_line=[center_seg], left_boundary=[left_seg], right_boundary=[right_seg], speed_limit=speed_limit)
        self.lane_id_counter += 1
        return lane_data

    def create_lane_from_pts_with_id(self, lane_id: int, centerline, left_boundary=None, right_boundary=None, speed_limit=0.0) -> LaneData:
        """Create a lane with a specific ID (preserves external IDs like Waymo lane IDs).

        Args:
            lane_id: Specific lane ID to use (e.g., from Waymo data)
            centerline: List of centerline points
            left_boundary: Optional list of left boundary points
            right_boundary: Optional list of right boundary points
            speed_limit: Speed limit in m/s

        Returns:
            LaneData: Created lane object with specified ID
        """
        center_seg, left_seg, right_seg = [], [], []
        center_seg = self._create_seg_from_pts(centerline)
        if left_boundary is not None:
            left_seg = self._create_seg_from_pts(left_boundary)
        if right_boundary is not None:
            right_seg = self._create_seg_from_pts(right_boundary)
        lane_data = LaneData(id=lane_id, center_line=[center_seg], left_boundary=[left_seg], right_boundary=[right_seg], speed_limit=speed_limit)
        return lane_data

    def _create_seg_from_pts(self, pts: List[Tuple[float, float, float]]) -> SegmentData:
        seg = SegmentData()
        for pt in pts:
            x, y = pt[0], pt[1]
            z = pt[2] if len(pt) > 2 else 0.0
            seg.points.append(PointData(x, y, z))
        return seg

    def add_lane(self, lane: LaneData, prev_lane_id: Optional[int] = None):
        self.map_data.lanes[lane.id] = lane
        if prev_lane_id is not None:
            self.map_data.next_lanes[prev_lane_id].append(lane.id)
            self.map_data.prev_lanes[lane.id].append(prev_lane_id)

    def build_spatial_index(self):
        """Build 2D spatial index for fast lane queries.

        Uses only (x, y) coordinates so that z-offset between ego and map
        data does not cause incorrect lane selection.
        """
        self._kdtree_points.clear()
        self._kdtree_refs.clear()
        for lane_id, lane in self.map_data.lanes.items():
            for seg_idx, seg in enumerate(lane.center_line):
                for pt_idx, pt in enumerate(seg.points):
                    self._kdtree_points.append((pt.x, pt.y))
                    self._kdtree_refs.append((lane_id, seg_idx, pt_idx))
        if self._kdtree_points:
            self._kdtree = KDTree(self._kdtree_points)
        else:
            self._kdtree = None

    def segment_to_pts(self, seg: SegmentData) -> List[Tuple[float, float, float]]:
        result = []
        for pt in seg.points:
            result.append((float(pt.x), float(pt.y), float(pt.z)))
        return result

    def _lane_direction_at(self, lane_id: int, seg_idx: int, pt_idx: int) -> Optional[Tuple[float, float]]:
        """Get the lane's travel direction (unit vector) at the given centerline point."""
        lane = self.map_data.lanes.get(lane_id)
        if lane is None:
            return None
        pts = self._flat_centerline(lane_id)
        if not pts:
            return None

        # Compute the flat index from seg_idx and pt_idx
        flat_idx = 0
        for si, seg in enumerate(lane.center_line):
            if si == seg_idx:
                flat_idx += pt_idx
                break
            flat_idx += len(seg.points)

        # Use forward difference, or backward at the end
        if flat_idx + 1 < len(pts):
            dx = pts[flat_idx + 1].x - pts[flat_idx].x
            dy = pts[flat_idx + 1].y - pts[flat_idx].y
        elif flat_idx > 0:
            dx = pts[flat_idx].x - pts[flat_idx - 1].x
            dy = pts[flat_idx].y - pts[flat_idx - 1].y
        else:
            return None

        mag = math.sqrt(dx * dx + dy * dy)
        if mag < 1e-9:
            return None
        return (dx / mag, dy / mag)

    def find_closest_lane(self, position: Tuple[float, float, float],
                          max_distance: Optional[float] = None,
                          heading: Optional[float] = None) -> Optional[int]:
        """Find the lane closest to the given position using 2D KD-tree.

        When heading is provided and multiple lanes are similarly close (within
        1.5x the nearest distance), the lane whose direction best aligns with
        the vehicle's heading is preferred. This prevents random lane flipping
        at lane boundaries and junctions.

        Args:
            position: (x, y, z) position tuple (z is ignored for lane finding)
            max_distance: Maximum 2D search distance (optional)
            heading: Vehicle heading in radians (optional). When provided,
                     used to disambiguate between equidistant lanes.

        Returns:
            int or None: Lane ID of closest lane, None if no lanes found within max_distance
        """
        if self._kdtree is None:
            self.build_spatial_index()

        if self._kdtree is None:
            return None

        if heading is None:
            # Original behavior: single nearest point
            distance, pt_idx = self._kdtree.query(position[:2])
            if max_distance is not None and distance > max_distance:
                return None
            lane_id, seg_idx, point_idx = self._kdtree_refs[pt_idx]
            return lane_id

        # Query multiple nearby candidates
        k = min(10, len(self._kdtree_points))
        distances, pt_indices = self._kdtree.query(position[:2], k=k)

        # Ensure arrays (k=1 returns scalars)
        if k == 1:
            distances = [distances]
            pt_indices = [pt_indices]

        if max_distance is not None and distances[0] > max_distance:
            return None

        # Consider candidates within 2x the closest distance (or at least 3m)
        threshold = max(distances[0] * 2.0, 3.0)

        # Vehicle direction from heading
        vx = math.cos(heading)
        vy = math.sin(heading)

        best_lane = None
        best_score = -float('inf')

        for dist, pt_idx in zip(distances, pt_indices):
            if dist > threshold:
                break
            lane_id, seg_idx, point_idx = self._kdtree_refs[pt_idx]

            lane_dir = self._lane_direction_at(lane_id, seg_idx, point_idx)
            if lane_dir is None:
                continue

            # Cosine similarity (dot product of unit vectors)
            # Use abs() so anti-parallel lanes (opposite direction) don't match
            alignment = abs(vx * lane_dir[0] + vy * lane_dir[1])

            # Reject lanes that are nearly perpendicular (alignment < 0.5 ≈ >60°)
            # unless it's the only candidate. This prevents selecting cross-traffic
            # lanes at intersections where the centerline happens to be closer.
            if alignment < 0.5 and dist > distances[0] * 1.01:
                continue

            # Score: heavily weight heading alignment, with distance as tiebreaker.
            # alignment ranges [0, 1], distance_penalty ranges [0, 0.3].
            # A well-aligned lane (alignment=1.0) at max threshold distance scores
            # 1.0 - 0.3 = 0.7, while a perpendicular lane (alignment=0) at closest
            # distance scores 0 - 0 = 0. This ensures orientation dominates.
            score = alignment - 0.3 * (dist / threshold)

            if score > best_score:
                best_score = score
                best_lane = lane_id

        return best_lane

    def get_lookahead_point(
        self,
        position: Tuple[float, float, float],
        lane_id: int,
        distance: float,
        lane_choice: str = "random",
    ) -> Optional[Tuple[float, float, float]]:
        """Walk forward along chained centerlines and return the 3D target point.

        Starting from the closest centerline point in lane_id, accumulates
        distance along centerline points. When a lane ends, picks a next_lane
        according to lane_choice strategy. Interpolates to the exact distance.

        Args:
            position: Current (x, y, z) position
            lane_id: Lane the vehicle is currently on
            distance: Lookahead distance in meters
            lane_choice: Strategy for picking next lane at forks ("random")

        Returns:
            (x, y, z) target point, or None if lane graph ends first
        """
        lane = self.map_data.lanes.get(lane_id)
        if lane is None:
            return None

        # Flatten centerline points for the current lane
        pts = self._flat_centerline(lane_id)
        if not pts:
            return None

        # Find the closest segment and project position onto it
        px, py = position[0], position[1]
        best_seg_idx = 0
        best_t = 0.0
        best_dist_sq = float('inf')

        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            seg_dx, seg_dy = p2.x - p1.x, p2.y - p1.y
            seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
            if seg_len_sq < 1e-12:
                continue
            t = ((px - p1.x) * seg_dx + (py - p1.y) * seg_dy) / seg_len_sq
            t = max(0.0, min(1.0, t))
            proj_x = p1.x + t * seg_dx
            proj_y = p1.y + t * seg_dy
            d2 = (px - proj_x) ** 2 + (py - proj_y) ** 2
            if d2 < best_dist_sq:
                best_dist_sq = d2
                best_seg_idx = i
                best_t = t

        # Start walking from the projection point on the best segment
        # Remaining distance in the current segment after the projection
        p1, p2 = pts[best_seg_idx], pts[best_seg_idx + 1]
        seg_len = math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
        remaining_in_seg = (1.0 - best_t) * seg_len

        remaining = distance
        if remaining <= remaining_in_seg:
            # Target is within the same segment
            t_final = best_t + remaining / seg_len
            return (
                p1.x + t_final * (p2.x - p1.x),
                p1.y + t_final * (p2.y - p1.y),
                p1.z + t_final * (p2.z - p1.z),
            )
        remaining -= remaining_in_seg
        idx = best_seg_idx + 1

        while True:
            # Walk within current lane's points
            while idx < len(pts) - 1:
                p1, p2 = pts[idx], pts[idx + 1]
                seg_len = math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
                if seg_len < 1e-12:
                    idx += 1
                    continue
                if remaining <= seg_len:
                    t = remaining / seg_len
                    return (
                        p1.x + t * (p2.x - p1.x),
                        p1.y + t * (p2.y - p1.y),
                        p1.z + t * (p2.z - p1.z),
                    )
                remaining -= seg_len
                idx += 1

            # Current lane exhausted — pick a next lane
            next_lanes = self.map_data.next_lanes.get(lane_id, [])
            if not next_lanes:
                return None  # Dead end

            if lane_choice == "random":
                lane_id = random.choice(next_lanes)
            else:
                lane_id = next_lanes[0]

            pts = self._flat_centerline(lane_id)
            if not pts:
                return None
            idx = 0

    def _flat_centerline(self, lane_id: int) -> List['PointData']:
        """Return a flat list of PointData for a lane's centerline segments."""
        lane = self.map_data.lanes.get(lane_id)
        if lane is None:
            return []
        result = []
        for seg in lane.center_line:
            result.extend(seg.points)
        return result

    # def query_closest_point(
    #     self, point: Tuple[float, float, float], max_distance: Optional[float] = None
    # ) -> Optional[Tuple[Tuple[float, float, float], int, int, int]]:
    #     if self._kdtree is None:
    #         raise RuntimeError("Spatial index not built. Call build_spatial_index() first.")
    #
    #     dist, pt_idx = self._kdtree.query(point)
    #     if max_distance is not None and dist > max_distance:
    #         return None
    #
    #     closest_pt = self._kdtree_points[pt_idx]
    #     lane_id, seg_id, pt_id = self._kdtree_refs[pt_idx]
    #     return closest_pt, lane_id, seg_id, pt_id
    #
    # def query_point_in_front(self, point: Tuple[float, float, float], distance=0.0) -> Optional[
    #     Tuple[Tuple[float, float, float], int, int, int]]:
    #     if self._kdtree is None:
    #         raise RuntimeError("Spatial index not built. Call build_spatial_index() first.")
    #
    #     remain_dist = distance
    #     result = self.query_closest_point(point)
    #     if result is None:
    #         return None, None, None, None
    #
    #     curr_pt, curr_lane_id, curr_seg_id, curr_pt_id = result
    #
    #     while True:
    #         curr_lane = self.map_data.lanes.get(curr_lane_id)
    #         if curr_lane is None:
    #             return None, None, None, None
    #
    #         center_points = curr_lane.center_line.points
    #         while curr_pt_idx < len(center_points) - 1:
    #             next_pt_idx = curr_pt_idx + 1
    #             next_pt = center_points[next_pt_idx]
    #             delta_dist = dist3d(curr_pt, next_pt)
    #             if remain_dist <= delta_dist:
    #                 interp = np.array(curr_pt) + remain_dist * (np.array(next_pt) - np.array(curr_pt)) / delta_dist
    #                 # return tuple(interp), curr_lane_id, next_pt_idx
    #                 return curr_pt, curr_lane_id, curr_pt_idx
    #             remain_dist -= delta_dist
    #             curr_pt = next_pt
    #             curr_pt_idx = next_pt_idx
    #
    #         next_lanes = self.map_data.next_lanes.get(curr_lane_id, [])
    #         if not next_lanes:
    #             return None, None, None
    #         curr_lane_id = next_lanes[0]
    #         curr_pt_idx = 0
    #         curr_pt = self.map_data.lanes[curr_lane_id].center_points[0]
    #
    # def query_next_point_in_lane(self, lane_id, point_index) -> Optional[Tuple[Tuple[float, float, float], int]]:
    #     lane = self.map_data.lanes[lane_id]
    #     if point_index >= len(lane.center_points):
    #         return None
    #     return lane.center_points[point_index + 1], point_index + 1
    #
    # def compute_longitudinal_s(
    #     self, lane_id: int, point_idx: int
    # ) -> float:
    #     lane = self.map_data.lanes.get(lane_id)
    #     if lane is None:
    #         raise ValueError(f"Lane id {lane_id} not found")
    #
    #     s = 0.0
    #     pts = lane.center_points
    #     for i in range(1, point_idx + 1):
    #         p1 = np.array(pts[i])
    #         p0 = np.array(pts[i - 1])
    #         s += np.linalg.norm(p1 - p0)
    #     return s
    #
    # def get_lane_heading(self, lane_id: int, point_idx: int) -> Tuple[float, float, float]:
    #     lane = self.map_data.lanes.get(lane_id)
    #     if lane is None:
    #         raise ValueError(f"Lane id {lane_id} not found")
    #     pts = lane.center_points
    #     if point_idx < 0 or point_idx >= len(pts):
    #         raise IndexError("point_idx out of range")
    #     if point_idx < len(pts) - 1:
    #         p0 = np.array(pts[point_idx])
    #         p1 = np.array(pts[point_idx + 1])
    #     else:
    #         p0 = np.array(pts[point_idx - 1])
    #         p1 = np.array(pts[point_idx])
    #     vec = p1 - p0
    #     norm = np.linalg.norm(vec)
    #     return tuple(vec / norm) if norm > 0 else (0.0, 0.0, 0.0)
    #

    def _lane_centerline_length(self, lane_id: int) -> float:
        """Compute the total centerline length for a lane.

        Args:
            lane_id: Lane ID to compute length for

        Returns:
            float: Total centerline length in meters
        """
        if not hasattr(self, '_centerline_length_cache'):
            self._centerline_length_cache: Dict[int, float] = {}

        if lane_id in self._centerline_length_cache:
            return self._centerline_length_cache[lane_id]

        lane = self.map_data.lanes.get(lane_id)
        if lane is None:
            return 0.0

        total = 0.0
        for seg in lane.center_line:
            pts = seg.points
            for i in range(len(pts) - 1):
                dx = pts[i + 1].x - pts[i].x
                dy = pts[i + 1].y - pts[i].y
                total += math.sqrt(dx * dx + dy * dy)

        self._centerline_length_cache[lane_id] = total
        return total

    def next_lanes(self, lane_id: int) -> List[int]:
        return list(self.map_data.next_lanes.get(lane_id, []))

    def prev_lanes(self, lane_id: int) -> List[int]:
        return list(self.map_data.prev_lanes.get(lane_id, []))

    def left_lanes(self, lane_id: int) -> List[int]:
        return list(self.map_data.left_lanes.get(lane_id, []))

    def right_lanes(self, lane_id: int) -> List[int]:
        return list(self.map_data.right_lanes.get(lane_id, []))

    def get_lane(self, lane_id: int):
        return self.map_data.lanes.get(lane_id)

    def get_reachable_lanes(self, start_lane_id: int, max_distance: float = 200.0) -> List[int]:
        """BFS over next_lanes from start_lane_id, stopping when cumulative
        centerline distance exceeds max_distance.

        Returns list of lane IDs in traversal order (includes start_lane_id).
        """
        if start_lane_id not in self.map_data.lanes:
            return []

        result = []
        visited = set()
        # Queue of (lane_id, cumulative_distance_at_start_of_this_lane)
        queue = deque([(start_lane_id, 0.0)])
        visited.add(start_lane_id)

        while queue:
            lane_id, cum_dist = queue.popleft()
            result.append(lane_id)

            lane_length = self._lane_centerline_length(lane_id)
            next_cum_dist = cum_dist + lane_length

            if next_cum_dist >= max_distance:
                continue

            for next_id in self.map_data.next_lanes.get(lane_id, []):
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, next_cum_dist))

        return result

    def project_onto_lane_path(self, position: Tuple[float, float], lane_path: List[int]) -> Optional[float]:
        """Project a 2D position onto the chained centerlines of lane_path.

        Returns cumulative s-coordinate along the path, or None if position
        is too far from any lane (> 20m lateral distance).
        """
        best_s = None
        best_lateral_dist = float('inf')
        cumulative_offset = 0.0
        max_lateral = 20.0

        pos_x, pos_y = position[0], position[1]

        for lane_id in lane_path:
            lane = self.map_data.lanes.get(lane_id)
            if lane is None:
                cumulative_offset += self._lane_centerline_length(lane_id)
                continue

            for seg in lane.center_line:
                pts = seg.points
                for i in range(len(pts) - 1):
                    p1x, p1y = pts[i].x, pts[i].y
                    p2x, p2y = pts[i + 1].x, pts[i + 1].y

                    seg_dx = p2x - p1x
                    seg_dy = p2y - p1y
                    seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy

                    if seg_len_sq < 1e-12:
                        continue

                    seg_len = math.sqrt(seg_len_sq)

                    # Projection ratio clamped to [0, 1]
                    t = ((pos_x - p1x) * seg_dx + (pos_y - p1y) * seg_dy) / seg_len_sq
                    t = max(0.0, min(1.0, t))

                    proj_x = p1x + t * seg_dx
                    proj_y = p1y + t * seg_dy

                    lat_dist = math.sqrt((pos_x - proj_x) ** 2 + (pos_y - proj_y) ** 2)

                    if lat_dist < best_lateral_dist:
                        best_lateral_dist = lat_dist
                        # s = cumulative offset to start of this segment point + distance along segment
                        seg_start_s = cumulative_offset
                        for j in range(i):
                            dx = pts[j + 1].x - pts[j].x
                            dy = pts[j + 1].y - pts[j].y
                            seg_start_s += math.sqrt(dx * dx + dy * dy)
                        best_s = seg_start_s + t * seg_len

            cumulative_offset += self._lane_centerline_length(lane_id)

        if best_lateral_dist > max_lateral:
            return None

        return best_s

    def get_segments(self, centerline=False):
       segments = []
       for lane in self.map_data.lanes.values():
           left_pts, right_pts = [], []
           for seg in lane.left_boundary:
               left_pts += self.segment_to_pts(seg)
           segments.append(left_pts)
           for seg in lane.right_boundary:
               right_pts += self.segment_to_pts(seg)
           segments.append(right_pts)
           if not centerline:
               continue
           center_pts = []
           for seg in lane.center_line:
               center_pts += self.segment_to_pts(seg)
           segments.append(center_pts)
       return segments

    def load_signals(self, signal_data_proto):
        """Load traffic signal data into the map.

        Args:
            signal_data_proto: SignalData protobuf containing time-series signal states

        The signal data is stored internally as {timestamp: {lane_id: state_value}}
        for efficient querying.
        """
        from humex.proto import signal_pb2 as signal_data_pb2

        self.signal_data = {}
        self.signal_timestamps = []

        # Track unknown lanes to only warn once per lane
        unknown_lanes = set()

        # Convert protobuf to internal format
        for frame in signal_data_proto.frames:
            timestamp = frame.timestamp
            self.signal_timestamps.append(timestamp)
            self.signal_data[timestamp] = {}

            for lane_signal in frame.lane_signals:
                lane_id = lane_signal.lane_id
                state = lane_signal.state

                # Validate lane exists in map (warn once per unique lane)
                if lane_id not in self.map_data.lanes:
                    if lane_id not in unknown_lanes:
                        unknown_lanes.add(lane_id)

                self.signal_data[timestamp][lane_id] = state

        # Sort timestamps for efficient lookup
        self.signal_timestamps.sort()

        # Print summary of warnings
        if unknown_lanes:
            print(f"Warning: Signal data references {len(unknown_lanes)} lanes not in map: {sorted(unknown_lanes)}")

    def has_signals(self) -> bool:
        """Check if this map has signal data loaded.

        Returns:
            bool: True if signal data is available, False otherwise
        """
        return self.signal_data is not None and len(self.signal_data) > 0

    def get_signal_state(self, lane_id: int, timestamp: int) -> Optional[int]:
        """Get the signal state for a specific lane at a specific time.

        Args:
            lane_id: The lane ID to query
            timestamp: The timestamp to query (int64 nanoseconds, will find closest frame)

        Returns:
            int or None: Signal state value, or None if no signal data available
        """
        if not self.has_signals():
            return None

        # Find closest timestamp
        closest_ts = self._find_closest_signal_timestamp(timestamp)
        if closest_ts is None:
            return None

        # Get signal state for this lane at this timestamp
        return self.signal_data[closest_ts].get(lane_id, None)

    def get_signal_frame(self, timestamp: int) -> Optional[Dict[int, int]]:
        """Get all signal states at a specific timestamp.

        Args:
            timestamp: The timestamp to query (int64 nanoseconds, will find closest frame)

        Returns:
            dict or None: Dictionary of {lane_id: state} or None if no signals
        """
        if not self.has_signals():
            return None

        closest_ts = self._find_closest_signal_timestamp(timestamp)
        if closest_ts is None:
            return None

        return self.signal_data[closest_ts].copy()

    def _find_closest_signal_timestamp(self, timestamp: int) -> Optional[int]:
        """Find the closest signal timestamp to the given timestamp.

        Args:
            timestamp: Target timestamp (int64 nanoseconds)

        Returns:
            int or None: Closest timestamp in signal data (int64 nanoseconds), or None if no signals
        """
        if not self.signal_timestamps:
            return None

        # Binary search for closest timestamp
        import bisect
        idx = bisect.bisect_left(self.signal_timestamps, timestamp)

        if idx == 0:
            return self.signal_timestamps[0]
        if idx == len(self.signal_timestamps):
            return self.signal_timestamps[-1]

        # Return closer of the two adjacent timestamps
        before = self.signal_timestamps[idx - 1]
        after = self.signal_timestamps[idx]

        if abs(timestamp - before) <= abs(timestamp - after):
            return before
        else:
            return after

    def plot(self, centerline=False):
        """
        Plot all left and right lane boundary points (not centerline).

        Note: This method requires matplotlib to be installed.
        """
        # Lazy import matplotlib only when plot() is called
        from matplotlib import pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.set_aspect('equal')
        ax.set_title("Ava Map")
        segments = self.get_segments(centerline=centerline)
        for pts in segments:
            if len(pts) <= 0:
                continue
            x, y= zip(*[(x, y) for x, y, *_ in pts])
            ax.plot(x, y, 'k')

        ax.grid(True)
        plt.show()