"""Waymo Open Dataset map converter for Hume.

This module converts Waymo Open Dataset map data (lane geometry, boundaries)
from Waymo scenario proto into protobuf map representation.
Extracts road network topology and geometric information.
"""

from pathlib import Path
from waymo_open_dataset.protos import scenario_pb2 as waymo_scenario_pb2
from humex_converter_waymo.tfrecord_reader import read_tfrecord
from humex.proto import map_pb2


class WaymoMapConverter:
    """Converter for Waymo Open Dataset maps to humex format.

    Processes Waymo map features (lanes, boundaries, road edges) and converts
    them to internal map representation for path planning and analysis.
    """

    def __init__(self, tfrecord_path: str):
        """Initialize map converter with Waymo dataset path.

        Args:
            tfrecord_path: Path to Waymo TFRecord file containing map data
        """
        self.record_path = tfrecord_path
        self.id_to_feature = None  # Map feature ID lookup table

    def convert_to_proto(
        self,
        conversion_uuid: str,
    ) -> map_pb2.Map:
        """Convert Waymo map features to protobuf object.

        Extracts lane geometry including centerlines and boundaries from Waymo
        map features and creates map protobuf with proper topology.

        Args:
            conversion_uuid: UUID for naming the map

        Returns:
            Map protobuf object
        """
        # Load map data from scenario
        scenario = self._load_scenario()

        # Build feature lookup table for boundary resolution
        self.id_to_feature = {mf.id: mf for mf in scenario.map_features}

        # Create map protobuf (wrapped in a Map message)
        ava_map = map_pb2.Map()
        ava_map.name = conversion_uuid
        ava_map.map_data.map_name = conversion_uuid
        ava_map.map_data.version = 1.0

        # Collect stop points from dynamic map states (take first non-null per lane)
        lane_stop_points = self._extract_stop_points(scenario)

        # Collect stop signs from map features
        lane_stop_signs = self._extract_stop_signs(scenario)

        # First pass: Create all lanes with geometry
        # IMPORTANT: Preserve Waymo lane IDs so signal data can reference them
        for mf in scenario.map_features:
            # Skip non-lane features (crosswalks, stop signs, etc.)
            if mf.WhichOneof("feature_data") != "lane":
                continue

            lane = mf.lane
            waymo_lane_id = mf.id

            # Create LaneData protobuf
            lane_data = map_pb2.LaneData()
            lane_data.id = waymo_lane_id

            # Extract and convert centerline points to SegmentData
            centerline_segment = lane_data.center_line.add()
            for p in lane.polyline:
                point = centerline_segment.points.add()
                point.x = p.x
                point.y = p.y
                point.z = p.z if hasattr(p, 'z') else 0.0

            # Extract left boundary
            left_boundary_segment = lane_data.left_boundary.add()
            left_boundary_points = self._get_lane_boundary_points(lane, direction='left')
            for x, y in left_boundary_points:
                point = left_boundary_segment.points.add()
                point.x = x
                point.y = y
                point.z = 0.0

            # Extract right boundary
            right_boundary_segment = lane_data.right_boundary.add()
            right_boundary_points = self._get_lane_boundary_points(lane, direction='right')
            for x, y in right_boundary_points:
                point = right_boundary_segment.points.add()
                point.x = x
                point.y = y
                point.z = 0.0

            # Extract speed limit from Waymo lane data (convert mph to m/s)
            if lane.speed_limit_mph > 0:
                lane_data.speed_limit = lane.speed_limit_mph * 0.44704

            # Set stop point (unified from traffic signals and stop signs)
            if waymo_lane_id in lane_stop_points:
                sp = lane_stop_points[waymo_lane_id]
                lane_data.stop_point.x = sp[0]
                lane_data.stop_point.y = sp[1]
                lane_data.stop_point.z = sp[2]
            elif waymo_lane_id in lane_stop_signs:
                pos = lane_stop_signs[waymo_lane_id]
                lane_data.stop_point.x = pos[0]
                lane_data.stop_point.y = pos[1]
                lane_data.stop_point.z = pos[2]

            # Mark if lane has a stop sign
            if waymo_lane_id in lane_stop_signs:
                lane_data.has_stop_sign = True

            # Add lane to map
            ava_map.map_data.lanes[waymo_lane_id].CopyFrom(lane_data)

        # Second pass: Add topology information
        # Since we preserve Waymo IDs, we can use them directly
        for mf in scenario.map_features:
            if mf.WhichOneof("feature_data") != "lane":
                continue

            lane = mf.lane
            lane_id = mf.id

            # Add next lanes (exit lanes in Waymo)
            for exit_lane_id in lane.exit_lanes:
                # Only add if the exit lane was also converted
                if exit_lane_id in ava_map.map_data.lanes:
                    next_lane_conn = ava_map.map_data.next_lanes.add()
                    next_lane_conn.lane_id = lane_id
                    next_lane_conn.connected_lane_ids.append(exit_lane_id)

            # Add previous lanes (entry lanes in Waymo)
            for entry_lane_id in lane.entry_lanes:
                if entry_lane_id in ava_map.map_data.lanes:
                    prev_lane_conn = ava_map.map_data.prev_lanes.add()
                    prev_lane_conn.lane_id = lane_id
                    prev_lane_conn.connected_lane_ids.append(entry_lane_id)

            # Add left neighboring lanes
            for neighbor in lane.left_neighbors:
                if neighbor.feature_id in ava_map.map_data.lanes:
                    left_lane_conn = ava_map.map_data.left_lanes.add()
                    left_lane_conn.lane_id = lane_id
                    left_lane_conn.connected_lane_ids.append(neighbor.feature_id)

            # Add right neighboring lanes
            for neighbor in lane.right_neighbors:
                if neighbor.feature_id in ava_map.map_data.lanes:
                    right_lane_conn = ava_map.map_data.right_lanes.add()
                    right_lane_conn.lane_id = lane_id
                    right_lane_conn.connected_lane_ids.append(neighbor.feature_id)

        return ava_map

    def convert(
        self,
        output_path: str | Path,
        conversion_uuid: str,
    ) -> str:
        """Convert Waymo map features to protobuf format and save to file.

        Extracts lane geometry including centerlines and boundaries from Waymo
        map features and creates map protobuf with proper topology.

        Args:
            output_path: Directory to save output files
            conversion_uuid: UUID for naming output file

        Returns:
            Path to generated map protobuf file
        """
        output_path = Path(output_path)

        # Ensure output directory exists
        output_path.mkdir(parents=True, exist_ok=True)

        # Convert to protobuf object
        ava_map = self.convert_to_proto(conversion_uuid=conversion_uuid)

        # Save map protobuf to file
        output_file = output_path / f"map_{conversion_uuid}.pb"
        with open(output_file, "wb") as f:
            f.write(ava_map.SerializeToString())

        return str(output_file)

    def _extract_stop_points(self, scenario) -> dict[int, tuple[float, float, float]]:
        """Extract stop point locations from dynamic map states.

        Scans traffic signal data across frames to find the stop point
        for each lane. Takes the first valid stop point per lane since
        stop points are static infrastructure.

        Args:
            scenario: Loaded Waymo scenario object

        Returns:
            Dict mapping lane_id to (x, y, z) stop point coordinates
        """
        lane_stop_points = {}
        for dynamic_map_state in scenario.dynamic_map_states:
            for lane_state in dynamic_map_state.lane_states:
                if lane_state.lane not in lane_stop_points and lane_state.HasField('stop_point'):
                    lane_stop_points[lane_state.lane] = (
                        lane_state.stop_point.x,
                        lane_state.stop_point.y,
                        lane_state.stop_point.z,
                    )
        return lane_stop_points

    def _extract_stop_signs(self, scenario) -> dict[int, tuple[float, float, float]]:
        """Extract stop sign locations from map features.

        Finds all stop_sign map features and maps them to their
        associated lane IDs.

        Args:
            scenario: Loaded Waymo scenario object

        Returns:
            Dict mapping lane_id to (x, y, z) stop sign position
        """
        lane_stop_signs = {}
        for mf in scenario.map_features:
            if mf.WhichOneof("feature_data") == "stop_sign":
                stop_sign = mf.stop_sign
                for lane_id in stop_sign.lane:
                    lane_stop_signs[lane_id] = (
                        stop_sign.position.x,
                        stop_sign.position.y,
                        stop_sign.position.z,
                    )
        return lane_stop_signs

    def _get_lane_boundary_points(self, lane, direction: str = 'left') -> list[tuple[float, float]]:
        """Extract lane boundary points from Waymo lane data.

        Resolves boundary feature references to extract geometric points
        for lane edges (road lines, curbs, etc.).

        Args:
            lane: Waymo lane protobuf object
            direction: 'left' or 'right' boundary to extract

        Returns:
            List of (x, y) boundary points
        """
        boundary_data = lane.left_boundaries if direction == 'left' else lane.right_boundaries
        boundary_points = []

        # Process each boundary segment
        for seg in boundary_data:
            boundary_id = seg.boundary_feature_id
            # Note: lane_start_index and lane_end_index are available in seg but
            # not needed for simple point extraction

            # Resolve boundary feature by ID
            boundary_feat = self.id_to_feature[boundary_id]
            boundary_type = boundary_feat.WhichOneof("feature_data")

            # Extract points based on boundary type
            if boundary_type == "road_line":
                # Painted lane markings, reflectors, etc.
                boundary_points = [(p.x, p.y) for p in boundary_feat.road_line.polyline]
            elif boundary_type == "road_edge":
                # Physical road edges, curbs, etc.
                boundary_points = [(p.x, p.y) for p in boundary_feat.road_edge.polyline]
            else:
                # Unsupported boundary type, skip
                continue

        return boundary_points

    def _load_scenario(self) -> waymo_scenario_pb2.Scenario:
        """Load scenario containing map data from Waymo TFRecord file.

        Returns:
            Parsed scenario with map features
        """
        records = read_tfrecord(self.record_path)
        for data in records:
            scenario = waymo_scenario_pb2.Scenario()
            scenario.ParseFromString(data)
            return scenario  # Return first scenario (typical for map data)
