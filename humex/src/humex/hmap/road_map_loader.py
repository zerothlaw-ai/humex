"""Map loader with support for both JSON and protobuf serialization.

This module provides serialization and deserialization functionality for humex maps,
supporting both legacy JSON format and new protobuf format for efficient storage
and cross-platform compatibility.
"""

import json
from collections import defaultdict
from datetime import datetime
from typing import Optional

from .road_map import PointData, SegmentData, LaneData, MapData, RoadMap
from humex.proto import map_pb2 as map_data_pb2, signal_pb2 as signal_data_pb2


class RoadMapLoader:
    """Serialize and deserialize MapData with support for both JSON and protobuf formats.
    
    Provides backward compatibility with existing JSON format while supporting
    the new protobuf format for improved performance and type safety.
    """

    # ========= JSON Serialization Methods (Legacy Format) =========
    @staticmethod
    def to_json(map_data: MapData, indent: int = 2) -> str:
        """Convert MapData into a JSON string (legacy format).
        
        Args:
            map_data: MapData object to serialize
            indent: JSON indentation level
            
        Returns:
            str: JSON representation of map data
        """
        def encode(obj):
            if isinstance(obj, defaultdict):
                return dict(obj)  # convert defaultdict to dict
            if isinstance(obj, dict):
                return {k: encode(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [encode(v) for v in obj]
            if hasattr(obj, "__dataclass_fields__"):
                return {k: encode(getattr(obj, k)) for k in obj.__dataclass_fields__}
            return obj  # primitive (int, float, str, etc.)

        return json.dumps(encode(map_data), indent=indent)

    @staticmethod
    def to_json_file(map_data: MapData, path: str, indent: int = 2):
        """Write MapData into a JSON file (legacy format).
        
        Args:
            map_data: MapData object to save
            path: Output file path
            indent: JSON indentation level
        """
        with open(path, "w") as f:
            f.write(RoadMapLoader.to_json(map_data, indent=indent))

    @staticmethod
    def from_json(json_str: str) -> MapData:
        """Load MapData from JSON string (legacy format).
        
        Args:
            json_str: JSON string containing map data
            
        Returns:
            MapData: Deserialized map data object
        """
        data = json.loads(json_str)

        def load_point(d: dict) -> PointData:
            return PointData(**d)

        def load_segment(d: dict) -> SegmentData:
            return SegmentData(points=[load_point(p) for p in d.get("points", [])])

        def load_lane(d: dict) -> LaneData:
            return LaneData(
                id=d["id"],
                center_line=[load_segment(s) for s in d.get("center_line", [])],
                left_boundary=[load_segment(s) for s in d.get("left_boundary", [])],
                right_boundary=[load_segment(s) for s in d.get("right_boundary", [])],
            )

        return MapData(
            lanes={int(k): load_lane(v) for k, v in data.get("lanes", {}).items()},
            next_lanes=defaultdict(list, {int(k): v for k, v in data.get("next_lanes", {}).items()}),
            prev_lanes=defaultdict(list, {int(k): v for k, v in data.get("prev_lanes", {}).items()}),
            left_lanes=defaultdict(list, {int(k): v for k, v in data.get("left_lanes", {}).items()}),
            right_lanes=defaultdict(list, {int(k): v for k, v in data.get("right_lanes", {}).items()}),
        )

    @staticmethod
    def from_json_file(path: str) -> MapData:
        """Load MapData from a JSON file (legacy format).
        
        Args:
            path: Path to JSON file
            
        Returns:
            MapData: Deserialized map data object
        """
        with open(path, "r") as f:
            return RoadMapLoader.from_json(f.read())

    # ========= Protobuf Serialization Methods (New Format) =========
    @staticmethod
    def to_protobuf(map_data: MapData, map_name: str = "unnamed") -> bytes:
        """Convert MapData to protobuf binary format.
        
        Args:
            map_data: MapData object to serialize
            map_name: Name of the map for metadata
            
        Returns:
            bytes: Protobuf binary data
        """
        # Create protobuf message
        pb_map = map_data_pb2.Map()
        pb_map.name = map_name
        
        # Set metadata
        pb_map.map_data.map_name = map_name
        pb_map.map_data.version = 1.0
        pb_map.map_data.created_at = datetime.now().isoformat()
        
        # Convert lanes
        for lane_id, lane_data in map_data.lanes.items():
            pb_lane = pb_map.map_data.lanes[lane_id]
            pb_lane.id = lane_id
            
            # Convert center line segments
            for segment in lane_data.center_line:
                pb_segment = pb_lane.center_line.add()
                for point in segment.points:
                    pb_point = pb_segment.points.add()
                    pb_point.x = point.x
                    pb_point.y = point.y
                    pb_point.z = point.z
            
            # Convert left boundary segments
            for segment in lane_data.left_boundary:
                pb_segment = pb_lane.left_boundary.add()
                for point in segment.points:
                    pb_point = pb_segment.points.add()
                    pb_point.x = point.x
                    pb_point.y = point.y
                    pb_point.z = point.z
            
            # Convert right boundary segments
            for segment in lane_data.right_boundary:
                pb_segment = pb_lane.right_boundary.add()
                for point in segment.points:
                    pb_point = pb_segment.points.add()
                    pb_point.x = point.x
                    pb_point.y = point.y
                    pb_point.z = point.z

            pb_lane.speed_limit = lane_data.speed_limit

            if lane_data.stop_point is not None:
                pb_lane.stop_point.x = lane_data.stop_point.x
                pb_lane.stop_point.y = lane_data.stop_point.y
                pb_lane.stop_point.z = lane_data.stop_point.z
            pb_lane.has_stop_sign = lane_data.has_stop_sign

        # Convert lane connections
        for lane_id, connected_lanes in map_data.next_lanes.items():
            if connected_lanes:  # Only add if there are connections
                pb_conn = pb_map.map_data.next_lanes.add()
                pb_conn.lane_id = lane_id
                pb_conn.connected_lane_ids.extend(connected_lanes)
        
        for lane_id, connected_lanes in map_data.prev_lanes.items():
            if connected_lanes:
                pb_conn = pb_map.map_data.prev_lanes.add()
                pb_conn.lane_id = lane_id
                pb_conn.connected_lane_ids.extend(connected_lanes)
        
        for lane_id, connected_lanes in map_data.left_lanes.items():
            if connected_lanes:
                pb_conn = pb_map.map_data.left_lanes.add()
                pb_conn.lane_id = lane_id
                pb_conn.connected_lane_ids.extend(connected_lanes)
        
        for lane_id, connected_lanes in map_data.right_lanes.items():
            if connected_lanes:
                pb_conn = pb_map.map_data.right_lanes.add()
                pb_conn.lane_id = lane_id
                pb_conn.connected_lane_ids.extend(connected_lanes)
        
        return pb_map.SerializeToString()
    
    @staticmethod
    def to_protobuf_file(map_data: MapData, path: str, map_name: str = "unnamed"):
        """Write MapData to protobuf file.
        
        Args:
            map_data: MapData object to save
            path: Output file path
            map_name: Name of the map for metadata
        """
        with open(path, "wb") as f:
            f.write(RoadMapLoader.to_protobuf(map_data, map_name))
    
    @staticmethod
    def from_proto(pb_map: map_data_pb2.Map) -> MapData:
        """Load MapData from protobuf message object.

        Args:
            pb_map: RoadMap protobuf message object

        Returns:
            MapData: Deserialized map data object
        """
        # Create MapData object
        map_data = MapData()

        # Convert lanes
        for lane_id, pb_lane in pb_map.map_data.lanes.items():
            lane_data = LaneData(id=lane_id)

            # Convert center line
            for pb_segment in pb_lane.center_line:
                segment = SegmentData()
                for pb_point in pb_segment.points:
                    point = PointData(x=pb_point.x, y=pb_point.y, z=pb_point.z)
                    segment.points.append(point)
                lane_data.center_line.append(segment)

            # Convert left boundary
            for pb_segment in pb_lane.left_boundary:
                segment = SegmentData()
                for pb_point in pb_segment.points:
                    point = PointData(x=pb_point.x, y=pb_point.y, z=pb_point.z)
                    segment.points.append(point)
                lane_data.left_boundary.append(segment)

            # Convert right boundary
            for pb_segment in pb_lane.right_boundary:
                segment = SegmentData()
                for pb_point in pb_segment.points:
                    point = PointData(x=pb_point.x, y=pb_point.y, z=pb_point.z)
                    segment.points.append(point)
                lane_data.right_boundary.append(segment)

            lane_data.speed_limit = pb_lane.speed_limit

            # Load stop point if present
            if pb_lane.HasField('stop_point'):
                lane_data.stop_point = PointData(
                    x=pb_lane.stop_point.x,
                    y=pb_lane.stop_point.y,
                    z=pb_lane.stop_point.z,
                )
            lane_data.has_stop_sign = pb_lane.has_stop_sign

            map_data.lanes[lane_id] = lane_data

        # Convert lane connections
        for pb_conn in pb_map.map_data.next_lanes:
            map_data.next_lanes[pb_conn.lane_id] = list(pb_conn.connected_lane_ids)

        for pb_conn in pb_map.map_data.prev_lanes:
            map_data.prev_lanes[pb_conn.lane_id] = list(pb_conn.connected_lane_ids)

        for pb_conn in pb_map.map_data.left_lanes:
            map_data.left_lanes[pb_conn.lane_id] = list(pb_conn.connected_lane_ids)

        for pb_conn in pb_map.map_data.right_lanes:
            map_data.right_lanes[pb_conn.lane_id] = list(pb_conn.connected_lane_ids)

        return map_data

    @staticmethod
    def from_protobuf(pb_data: bytes) -> MapData:
        """Load MapData from protobuf binary data.

        Args:
            pb_data: Protobuf binary data

        Returns:
            MapData: Deserialized map data object
        """
        pb_map = map_data_pb2.Map()
        pb_map.ParseFromString(pb_data)
        return RoadMapLoader.from_proto(pb_map)

    @staticmethod
    def from_protobuf_file(path: str) -> MapData:
        """Load MapData from protobuf file.

        Args:
            path: Path to protobuf file

        Returns:
            MapData: Deserialized map data object
        """
        with open(path, "rb") as f:
            return RoadMapLoader.from_protobuf(f.read())

    # ========= Signal Data Loading Methods =========
    @staticmethod
    def load_signal_file(path: str) -> signal_data_pb2.SignalData:
        """Load signal data from protobuf file.

        Args:
            path: Path to signal protobuf file (.pb)

        Returns:
            signal_data_pb2.SignalData: Signal data protobuf object
        """
        signal_data = signal_data_pb2.SignalData()
        with open(path, "rb") as f:
            signal_data.ParseFromString(f.read())
        return signal_data

    @staticmethod
    def create_road_map(map_path: str, map_name: str = "unnamed", signal_path: Optional[str] = None) -> RoadMap:
        """Create an RoadMap instance from map file and optional signal file.

        This is a convenience method that loads both map and signal data in one call.

        Args:
            map_path: Path to map file (.json or .pb)
            map_name: Name of the map
            signal_path: Optional path to signal file (.pb)

        Returns:
            RoadMap: Configured RoadMap instance with map data and optional signals
        """
        # Load map data
        map_data = RoadMapLoader.from_file(map_path)

        # Create RoadMap instance
        ava_map = RoadMap(map_name=map_name, map_data=map_data)

        # Load signals if provided
        if signal_path is not None:
            signal_data = RoadMapLoader.load_signal_file(signal_path)
            ava_map.load_signals(signal_data)

        return ava_map

    # ========= Unified Interface Methods =========
    @staticmethod
    def to_file(map_data: MapData, path: str, map_name: str = "unnamed", format_type: str = "auto"):
        """Save MapData to file with automatic format detection or explicit format.
        
        Args:
            map_data: MapData object to save
            path: Output file path
            map_name: Name of the map for metadata
            format_type: 'json', 'protobuf', or 'auto' (detect from file extension)
        """
        if format_type == "auto":
            if path.endswith('.json'):
                format_type = "json"
            elif path.endswith('.pb'):
                format_type = "protobuf"
            else:
                # Default to protobuf for new files
                format_type = "protobuf"
        
        if format_type == "json":
            RoadMapLoader.to_json_file(map_data, path)
        elif format_type == "protobuf":
            RoadMapLoader.to_protobuf_file(map_data, path, map_name)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")
    
    @staticmethod
    def from_file(path: str, format_type: str = "auto") -> MapData:
        """Load MapData from file with automatic format detection.
        
        Args:
            path: Path to map file
            format_type: 'json', 'protobuf', or 'auto' (detect from file extension)
            
        Returns:
            MapData: Deserialized map data object
        """
        if format_type == "auto":
            if path.endswith('.json'):
                format_type = "json"
            elif path.endswith('.pb'):
                format_type = "protobuf"
            else:
                # Try to detect format by reading file header
                try:
                    with open(path, "rb") as f:
                        first_byte = f.read(1)
                        if first_byte == b'{':
                            format_type = "json"
                        else:
                            format_type = "protobuf"
                except OSError:
                    format_type = "json"  # Unreadable header → assume JSON
        
        if format_type == "json":
            return RoadMapLoader.from_json_file(path)
        elif format_type == "protobuf":
            return RoadMapLoader.from_protobuf_file(path)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")