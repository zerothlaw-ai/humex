"""Waymo Open Dataset scenario converter for Hume.

This module converts Waymo Open Dataset scenario files (TFRecord format) into
humex-compatible protobuf format. Extracts vehicle trajectories and traffic
signal states.
"""

from pathlib import Path
from waymo_open_dataset.protos import scenario_pb2 as waymo_scenario_pb2
from humex.converters.tfrecord_reader import read_tfrecord
from humex.proto import scenario_pb2, signal_pb2


class WaymoScenarioConverter:
    """Converter for Waymo Open Dataset scenarios to humex format.

    Processes Waymo TFRecord files containing vehicle trajectory data and
    converts them to humex's protobuf scenario format for analysis and replay.
    """

    def __init__(self, path: str):
        """Initialize converter with Waymo dataset path.

        Args:
            path: Path to Waymo TFRecord scenario file
        """
        self.data_path = path
        self.map = None       # Associated map data (if loaded)
        self.scenario = None  # Loaded Waymo scenario data
        self.data = None      # Converted scenario data

    def load_scenario(self) -> waymo_scenario_pb2.Scenario:
        """Load the first scenario from Waymo TFRecord file.

        Returns:
            Parsed Waymo scenario containing vehicle trajectories
        """
        records = read_tfrecord(self.data_path)
        for data in records:
            scenario = waymo_scenario_pb2.Scenario()
            scenario.ParseFromString(data)
            return scenario  # Return first scenario only (typical use case)

    def extract(self) -> dict:
        """Extract vehicle trajectory data from Waymo scenario.

        Processes all vehicle tracks across time to create a time-indexed
        dictionary of vehicle states (position and heading).

        Returns:
            Nested dictionary {timestamp: {vehicle_id: (x, y, heading, velocity_x, velocity_y)}}
        """
        scenario = self.load_scenario()
        num_frames = len(scenario.timestamps_seconds)
        raw_data = dict()

        # Process each time frame
        for t in range(num_frames):
            ts = scenario.timestamps_seconds[t]
            raw_data[ts] = dict()

            # Extract vehicle states for this time frame
            for track in scenario.tracks:
                state = track.states[t]

                # Skip invalid states (vehicle not present in this frame)
                if not state.valid:
                    continue

                # Store vehicle position and heading
                if track.id not in raw_data[ts]:
                    raw_data[ts][track.id] = dict()
                raw_data[ts][track.id] = (state.center_x, state.center_y, state.heading, state.velocity_x, state.velocity_y)

        return raw_data

    def extract_signals(self, scenario) -> signal_pb2.SignalData:
        """Extract traffic signal data from Waymo scenario.

        Processes dynamic map states (traffic signals) across time to create
        time-indexed signal data compatible with humex's signal protobuf format.

        Args:
            scenario: Loaded Waymo scenario object

        Returns:
            SignalData protobuf with all frames
        """
        signal_data = signal_pb2.SignalData()
        signal_data.scenario_id = scenario.scenario_id

        # Process each dynamic map state (one per frame)
        for frame_idx, dynamic_map_state in enumerate(scenario.dynamic_map_states):
            # Create signal frame with timestamp
            signal_frame = signal_pb2.SignalFrame()
            signal_frame.timestamp = round(scenario.timestamps_seconds[frame_idx] * 1_000_000_000)

            # Extract signal states for each lane
            for lane_state in dynamic_map_state.lane_states:
                signal_state = signal_pb2.SignalState()
                signal_state.lane_id = lane_state.lane
                signal_state.state = lane_state.state  # Enum values match

                signal_frame.lane_signals.append(signal_state)

            # Only add frame if it has signal data
            if len(signal_frame.lane_signals) > 0:
                signal_data.frames.append(signal_frame)

        return signal_data

    def convert_to_proto(
        self,
        ego_id: int | None = None,
    ) -> tuple[scenario_pb2.ScenarioData, signal_pb2.SignalData]:
        """Convert Waymo scenario to protobuf objects.

        Creates scenario with vehicle roster and time-series trajectory data.
        Handles scenario metadata, vehicle properties, and state information.
        Also extracts traffic signal data.

        Args:
            ego_id: ID of the ego vehicle (optional)

        Returns:
            Tuple of (ScenarioData, SignalData) protobuf objects
        """
        # Load and process Waymo scenario
        scenario = self.load_scenario()
        num_frames = len(scenario.timestamps_seconds)

        # Auto-detect ego from Waymo's SDV track if not explicitly provided
        if ego_id is None:
            sdc_track = scenario.tracks[scenario.sdc_track_index]
            ego_id = sdc_track.id

        # Create scenario protobuf structure
        data = scenario_pb2.ScenarioData()
        data.duration = scenario.timestamps_seconds[-1]  # Total scenario duration
        data.frequency = round(num_frames / data.duration, 2)  # Sampling frequency

        # Extract trajectory data and build vehicle roster
        raw_data = self.extract()
        roster = set()

        # Collect all unique vehicle IDs across all frames
        for ts, frame in raw_data.items():
            for agent_id in frame:
                if agent_id not in roster:
                    roster.add(agent_id)

        # Create vehicle roster with physical properties
        for obj_id in roster:
            new_obj = data.roster[obj_id]
            new_obj.id = obj_id
            # TODO: Extract actual vehicle dimensions from Waymo data instead of hardcoding
            new_obj.length, new_obj.width, new_obj.height = 4.5, 2, 1.8
            new_obj.is_ego = True if obj_id == ego_id else False

        # Convert trajectory data to frame format
        for ts, frame in raw_data.items():
            # Skip empty frames (timestamps where no vehicles are valid)
            if not frame:
                continue

            new_frame = data.frames[str(ts)]
            new_frame.timestamp = round(ts * 1_000_000_000)

            # Add vehicle states for this frame
            for obj_id, obj_state in frame.items():
                new_obj = new_frame.obj_list[obj_id]
                # Position data (x, y at ground level)
                new_obj.sp.position.x = obj_state[0]
                new_obj.sp.position.y = obj_state[1]
                new_obj.sp.position.z = 0.0
                # Velocity data from Waymo source
                new_obj.sp.velocity.x = obj_state[3]
                new_obj.sp.velocity.y = obj_state[4]
                new_obj.sp.velocity.z = 0.0
                # Heading data (roll, pitch, yaw)
                new_obj.sp.heading.roll = 0.0
                new_obj.sp.heading.pitch = 0.0
                new_obj.sp.heading.yaw = obj_state[2]
                # Set is_ego flag on frame object
                new_obj.is_ego = (obj_id == ego_id)

        # Set ego_id at scenario level
        data.ego_id = ego_id

        # Extract traffic signal data
        signal_data = self.extract_signals(scenario)

        return data, signal_data

    def convert(
        self,
        output_path: str | Path,
        conversion_uuid: str,
        ego_id: int | None = None,
    ) -> tuple[str, str]:
        """Convert Waymo scenario to protobuf format and save to files.

        Creates scenario with vehicle roster and time-series trajectory data.
        Handles scenario metadata, vehicle properties, and state information.
        Also extracts and saves traffic signal data.

        Args:
            output_path: Directory to save output files
            conversion_uuid: UUID for naming output files
            ego_id: ID of the ego vehicle (optional)

        Returns:
            Tuple of (scenario_path, signal_path) - paths to generated files
        """
        output_path = Path(output_path)

        # Ensure output directory exists
        output_path.mkdir(parents=True, exist_ok=True)

        # Convert to protobuf objects
        data, signal_data = self.convert_to_proto(ego_id=ego_id)

        # Save converted scenario to file
        data_path = output_path / f"scenario_{conversion_uuid}.pb"
        with open(data_path, "wb") as f:
            f.write(data.SerializeToString())

        # Save traffic signal data
        signal_path = output_path / f"signal_{conversion_uuid}.pb"
        with open(signal_path, "wb") as f:
            f.write(signal_data.SerializeToString())

        return str(data_path), str(signal_path)
