from humex.proto import scenario_pb2 as scenario_data_pb2
from ..components.scenario import Scenario
from ..components.statepoint import StatePoint
from ..components.object import Object
from ..hmap.road_map import RoadMap
from ..hmap.road_map_loader import RoadMapLoader
from .paths import get_scenario_file_path, get_map_file_path, get_signal_file_path
from .timestamp import to_ns


class DataLoader(object):
    """
    This is a class to load scenario file into memory with internal data structure such as frame and statepoint
    """
    def __init__(self):
        """
        duration is in seconds
        frequency is in hertz
        """
        pass

    @staticmethod
    def _load_scenario_from_proto_data(scenario_pb, map_data_pb, signal_data=None, scenario_name=None):
        """
        Core method to load scenario from protobuf data.

        This method contains all the shared logic for creating and loading objects
        from protobuf format, regardless of whether the data came from files or
        from gRPC request objects. It handles:
        - Creating RoadMap from map data
        - Creating Scenario from scenario protobuf
        - Loading roster, frames, and statepoints
        - Attaching signals and map to scenario

        Args:
            scenario_pb: Scenario protobuf message (contains frames)
            map_data_pb: Map data in protobuf format
            signal_data: Signal data (optional, can be None)
            scenario_name: Name of the scenario for RoadMap initialization (optional)

        Returns:
            Scenario: Internal Scenario object with loaded frames and attached map/signals
        """
        # Use scenario map_name if scenario_name not provided
        if scenario_name is None:
            scenario_name = scenario_pb.map_name

        # Create RoadMap from map data
        print('Creating Ava Map')
        road_map = RoadMap(scenario_name)
        road_map.map_data = map_data_pb

        # Create Scenario
        print('Creating Ava Scenario')
        # Read ego_id from protobuf (primary source)
        ego_id = scenario_pb.ego_id if scenario_pb.ego_id != 0 else None
        scenario = Scenario(duration=scenario_pb.duration, frequency=scenario_pb.frequency, map_obj=road_map, ego_id=ego_id)
        scenario.scenario_name = scenario_pb.map_name  # Store scenario name for results

        # Load all object information
        for obj_id, obj in scenario_pb.roster.items():
            object = Object(obj_id=int(obj_id), length=obj.length, width=obj.width, height=obj.height, is_ego=obj.is_ego, scenario=scenario, object_type=obj.object_type)
            scenario.add_obj_to_roster(object)
        print(f'Roster Created with {len(scenario_pb.roster)} objects')

        # Load all frames and statepoints information
        for ts, frame_data in scenario_pb.frames.items():
            # Skip empty frames (backward compatibility with older scenarios)
            if len(frame_data.obj_list) == 0:
                continue

            # Handle backward compatibility: convert float seconds to int64 nanoseconds if needed
            # Old .pb files/JSON have float timestamps in seconds; new ones have int64 in nanoseconds
            if isinstance(ts, str):
                # String format (from JSON/text) - parse as float, then convert to int64 nanoseconds
                ts_int64 = to_ns(float(ts))
            elif isinstance(ts, float):
                # Old format: float seconds - convert to int64 nanoseconds
                ts_int64 = to_ns(ts)
            else:
                # New format: already int64 nanoseconds
                ts_int64 = int(ts)

            frame = scenario.get_frame_by_ts(ts_int64)
            for obj_id, obj_data in frame_data.obj_list.items():
                new_obj = scenario.get_obj_copy_from_roster(int(obj_id))
                point = obj_data.sp
                position = (point.position.x, point.position.y, point.position.z)
                heading = (point.heading.roll, point.heading.pitch, point.heading.yaw)
                sp = StatePoint(obj_id=obj_id, position=position, heading=heading)
                new_obj.update_mutable(sp)

                # Fallback: Check frame-level is_ego for backward compatibility with old protobuf files
                if scenario.ego_id is None and obj_data.is_ego:
                    new_obj.is_ego = obj_data.is_ego
                    scenario.ego_id = obj_id
                scenario.add_obj_to_frame(new_obj, frame)

        # Remove empty frames from scenario (cleanup after loading)
        empty_timestamps = [ts for ts, frame in scenario.frames.items() if len(frame.obj_list) == 0]
        for ts in empty_timestamps:
            del scenario.frames[ts]
            if ts in scenario.timestamps:
                scenario.timestamps.remove(ts)

        # Attach signal data if provided
        if signal_data is not None:
            road_map.load_signals(signal_data)

        # Last resort: Auto-assign ego based on frequency
        if scenario.ego_id is None:
            scenario.assign_ego_id()

        num_frames = len(scenario.frames)
        print(f'Scenario loaded with {num_frames} frames')
        return scenario

    @staticmethod
    def load_from_proto_objects(scenario_data_pb, map_data_pb, signal_pb=None):
        """
        Load scenario from in-memory protobuf objects (e.g., from gRPC request).

        This method handles input parsing for objects coming directly from gRPC
        clients and delegates all object creation and loading to the core function.

        Args:
            scenario_data_pb: Scenario protobuf message
            map_data_pb: MapData protobuf message
            signal_pb: Signal protobuf message (optional)

        Returns:
            Scenario: Internal Scenario object with loaded frames and attached map
        """
        print(f'DataLoader is loading scenario from protobuf objects')

        # Parse signal data if provided
        signal_data = None
        if signal_pb is not None:
            try:
                signal_data = signal_pb
            except Exception as e:
                print(f'Warning: Failed to load signal data from protobuf: {e}')

        # Delegate all object creation and loading to core function
        return DataLoader._load_scenario_from_proto_data(
            scenario_data_pb,
            map_data_pb,
            signal_data,
            scenario_data_pb.map_name
        )

    @staticmethod
    def load_proto(scenario_name):
        """
        Load scenario from file system (scenario, map, and signal files).

        This method loads scenario data from the local file system and uses
        the shared core loading logic to convert protobuf to internal Scenario.

        Args:
            scenario_name: Name of the scenario to load

        Returns:
            Scenario: Internal Scenario object with loaded frames and attached map
        """
        # Load Scenario Data
        print(f'Dataloader is loading scenario data: {scenario_name}')
        data_path = get_scenario_file_path(scenario_name)
        data = scenario_data_pb2.ScenarioData()
        with open(data_path, "rb") as f:
            data.ParseFromString(f.read())

        # Load Scenario Map
        print(f'Dataloader is loading map data: {scenario_name}')

        # Try protobuf format first, fallback to JSON
        pb_map_path = get_map_file_path(scenario_name)
        # Note: JSON maps should also be converted and placed in scenario folders
        json_map_path = pb_map_path.replace('.pb', '.json')

        try:
            map_data = RoadMapLoader.from_file(pb_map_path, format_type="protobuf")
            print(f'Loaded map in protobuf format from: {pb_map_path}')
        except (FileNotFoundError, Exception) as e:
            try:
                map_data = RoadMapLoader.from_file(json_map_path, format_type="json")
                print(f'Loaded map in JSON format from: {json_map_path}')
            except (FileNotFoundError, Exception) as e2:
                raise FileNotFoundError(f'Could not load map {scenario_name} in either protobuf (.pb) or JSON (.json) format. '
                                      f'Protobuf error: {e}, JSON error: {e2}')

        # Parse Signal Data (optional)
        signal_data = None
        signal_path = get_signal_file_path(scenario_name)
        try:
            signal_data = RoadMapLoader.load_signal_file(signal_path)
            print(f'Loaded signal data from: {signal_path}')
        except FileNotFoundError:
            print(f'No signal data found for scenario: {scenario_name} (optional)')
        except Exception as e:
            print(f'Warning: Failed to load signal data: {e}')

        # Delegate all object creation and loading to core function
        return DataLoader._load_scenario_from_proto_data(
            data,
            map_data,
            signal_data,
            scenario_name
        )

if __name__=='__main__':
    # Lazy import Visualizer only when running as main script
    from ..simulator.visualizer.visualizer_3d import Visualizer

    # scenario = DataLoader().load_proto('two_car_acc')
    data_name = 'ava_scenario.uncompressed_scenario_training_training.tfrecord-00000-of-01000'
    map_name = 'ava_map.uncompressed_scenario_training_training.tfrecord-00000-of-01000'
    scenario = DataLoader().load_proto(data_name, map_name)
    viz = Visualizer(scenario)
    viz.run()