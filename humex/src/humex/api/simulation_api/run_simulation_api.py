"""Simulation API for running autonomous vehicle simulations.

This module provides the RunSimulationAPI class for running simulations
from JSON config and map files, generating scenario result protobufs.
"""

import json
import os
import time
from typing import Dict, List, Optional, Any

from humex.proto import scenario_pb2 as scenario_data_pb2

from ...components.scenario import Scenario
from ...components.statepoint import StatePoint
from ...components.object import Car, KeyframeCar, SmartKeyframeCar, LaneFollowCar
from ...components.perception import Perception
from ...simulator.vehicle.models import BicycleModel
from ...simulator.vehicle.controllers import LKA, ACC
from ...hmap.road_map_loader import RoadMapLoader
from ...hmap.road_map import RoadMap
from ...utils.paths import SCENARIO_DATA


class RunSimulationAPI:
    """API for running simulations from JSON config and map files.

    This API takes a JSON scenario configuration and a map protobuf file,
    runs the simulation, and generates a scenario result protobuf file
    compatible with the converted scenario format.
    """

    def __init__(self):
        """Initialize RunSimulationAPI."""
        pass

    def run(
        self,
        config_path: str,
        map_path: str,
        output_dir: Optional[str] = None,
        output_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run simulation and generate scenario result protobuf.

        Args:
            config_path: Path to JSON scenario configuration file
            map_path: Path to map protobuf file (.pb)
            output_dir: Output directory (default: data/scenarios/{name}/)
            output_name: Output name (default: derived from config)

        Returns:
            dict with keys:
                - 'scenario_proto_path': Path to generated .pb file
                - 'scenario': Scenario object
                - 'simulation_time_seconds': Execution time

        Raises:
            ValueError: If map_path not provided
        """
        start_time = time.perf_counter()

        if not map_path:
            raise ValueError("map_path is required")

        # Load inputs
        config = self._load_config(config_path)

        # Load map
        road_map = self._load_map(map_path, config.get('map', 'unknown'))

        # Determine output naming
        if output_name is None:
            # Try to derive name from config file
            output_name = os.path.splitext(os.path.basename(config_path))[0]

        # Create scenario
        scenario = self._create_scenario(config, road_map)

        # Initialize agents
        self._initialize_agents(config, scenario)

        # Run simulation
        self._run_simulation(scenario)

        # Export results
        proto_path = self._export_proto(scenario, output_dir, output_name)

        end_time = time.perf_counter()
        simulation_time = end_time - start_time

        print(f"Simulation completed in {simulation_time:.4f} seconds")
        print(f"Generated: {proto_path}")

        return {
            'scenario_proto_path': proto_path,
            'scenario': scenario,
            'simulation_time_seconds': simulation_time,
        }

    def _load_config(self, config_path: str) -> Dict:
        """Load JSON configuration file.

        Args:
            config_path: Path to JSON config file

        Returns:
            dict: Parsed configuration
        """
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config

    def _load_map(self, map_path: str, map_name: str) -> RoadMap:
        """Load map from protobuf file.

        Args:
            map_path: Path to map protobuf file
            map_name: Name for the map

        Returns:
            RoadMap: Loaded map object
        """
        map_data = RoadMapLoader.from_file(map_path, format_type="protobuf")
        road_map = RoadMap(map_name=map_name, map_data=map_data)
        road_map.build_spatial_index()
        return road_map

    def _create_scenario(self, config: Dict, road_map: RoadMap) -> Scenario:
        """Create scenario from configuration.

        Args:
            config: Parsed configuration dict
            road_map: Loaded map object

        Returns:
            Scenario: Created scenario object
        """
        duration = config.get('duration', 10.0)
        frequency = config.get('frequency', 10.0)

        scenario = Scenario(duration, frequency, map_obj=road_map)
        scenario.map_name = config.get('map', 'unknown')

        return scenario

    def _initialize_agents(self, config: Dict, scenario: Scenario) -> None:
        """Initialize all agents from configuration.

        Args:
            config: Parsed configuration dict
            scenario: Scenario to add agents to
        """
        vehicles = config.get('vehicles', [])

        for vehicle in vehicles:
            obj_id = int(vehicle['id'])
            is_ego = vehicle.get('name', '') == 'ego'
            object_type = vehicle.get('object_type', 'car').lower()

            if object_type == 'keyframe':
                car = self._create_keyframe_car(vehicle, obj_id, is_ego, scenario)
            elif object_type == 'smartkeyframe':
                car = self._create_smartkeyframe_car(vehicle, obj_id, is_ego, scenario)
            elif object_type == 'lanefollow':
                car = self._create_lanefollow_car(vehicle, obj_id, is_ego, scenario)
            elif object_type == 'car':
                car = self._create_dynamic_car(vehicle, obj_id, is_ego, scenario)
            else:
                # Default to dynamic car
                car = self._create_dynamic_car(vehicle, obj_id, is_ego, scenario)

            # Add to scenario roster
            scenario.add_obj_to_roster(car)

            # Set ego_id on the scenario
            if is_ego:
                scenario.ego_id = obj_id

            # Add initial state to first frame
            initial_frame = scenario.frames[0]
            initial_car = scenario.get_obj_copy_from_roster(obj_id=obj_id)

            # Get initial state
            if object_type == 'keyframe' or object_type == 'smartkeyframe':
                # For keyframe-based cars, get state at first timestamp
                initial_state = car.get_state_at_time(scenario.timestamps[0])
                if initial_state:
                    initial_car.update_mutable(initial_state)
                    scenario.add_obj_to_frame(initial_car, initial_frame)
            else:
                # For dynamic cars, use initial_states from config
                vel = tuple(vehicle['initial_states']['velocity'])
                import math as _math
                yaw = _math.atan2(vel[1], vel[0]) if (vel[0] != 0 or vel[1] != 0) else 0.0
                sp = StatePoint(
                    obj_id=obj_id,
                    position=tuple(vehicle['initial_states']['position']),
                    velocity=vel,
                    heading=(0.0, 0.0, yaw),
                )
                initial_car.update_mutable(sp)
                scenario.add_obj_to_frame(initial_car, initial_frame)

        # Initialize perception system for initial frame
        initial_frame = scenario.frames[0]
        initial_frame.update_perception(Perception(initial_frame, scenario.map))

    def _create_keyframe_car(self, vehicle: Dict, obj_id: int, is_ego: bool, scenario: Scenario) -> KeyframeCar:
        """Create a keyframe-based car.

        Args:
            vehicle: Vehicle configuration dict
            obj_id: Object ID
            is_ego: Whether this is the ego vehicle
            scenario: Parent scenario

        Returns:
            KeyframeCar: Created keyframe car
        """
        keystates_data = vehicle.get('keystates', [])
        keystates = []

        for ks in keystates_data:
            sp = StatePoint(
                position=tuple(ks['position']),
                velocity=tuple(ks['velocity']),
                heading=tuple(ks.get('heading', (0, 0, 0)))
            )
            keystates.append(sp)

        car = KeyframeCar(
            obj_id=obj_id,
            scenario=scenario,
            keystates=keystates,
            is_ego=is_ego,
            length=vehicle.get('length', 4.8),
            width=vehicle.get('width', 1.7),
            height=vehicle.get('height', 1.9),
        )

        return car

    def _create_smartkeyframe_car(self, vehicle: Dict, obj_id: int, is_ego: bool, scenario: Scenario) -> SmartKeyframeCar:
        """Create a smart keyframe car using physics-based simulation.

        Uses SmartKeyframeBehavior with BicycleModel + PurePursuit + PID control.

        Args:
            vehicle: Vehicle configuration dict
            obj_id: Object ID
            is_ego: Whether this is the ego vehicle
            scenario: Parent scenario

        Returns:
            SmartKeyframeCar: Created smart keyframe car
        """
        keystates_data = vehicle.get('keystates', [])
        keystates = []

        for ks in keystates_data:
            sp = StatePoint(
                position=tuple(ks['position']),
                velocity=tuple(ks['velocity']),
                heading=tuple(ks.get('heading', (0, 0, 0)))
            )
            keystates.append(sp)

        speed_controller = vehicle.get('speed_controller', 'kinematics')
        heading_controller = vehicle.get('heading_controller', 'pure_pursuit')
        turning_radius = vehicle.get('turning_radius', 6.0)

        car = SmartKeyframeCar(
            obj_id=obj_id,
            scenario=scenario,
            keystates=keystates,
            is_ego=is_ego,
            length=vehicle.get('length', 4.8),
            width=vehicle.get('width', 1.7),
            height=vehicle.get('height', 1.9),
            speed_controller=speed_controller,
            heading_controller=heading_controller,
            turning_radius=turning_radius,
        )

        return car

    def _create_dynamic_car(self, vehicle: Dict, obj_id: int, is_ego: bool, scenario: Scenario) -> Car:
        """Create a dynamic car with controllers.

        Args:
            vehicle: Vehicle configuration dict
            obj_id: Object ID
            is_ego: Whether this is the ego vehicle
            scenario: Parent scenario

        Returns:
            Car: Created dynamic car
        """
        car = Car(
            obj_id=obj_id,
            scenario=scenario,
            dynamic_model=BicycleModel(scenario),
            lon_controller=ACC(interval=scenario.interval),
            lat_controller=LKA(look_ahead_time=0.3),
            is_ego=is_ego,
            length=vehicle.get('length', 4.8),
            width=vehicle.get('width', 1.7),
            height=vehicle.get('height', 1.9),
        )

        return car

    def _create_lanefollow_car(self, vehicle: Dict, obj_id: int, is_ego: bool, scenario: Scenario) -> LaneFollowCar:
        """Create a lane-following car with pure pursuit + ACC.

        Args:
            vehicle: Vehicle configuration dict
            obj_id: Object ID
            is_ego: Whether this is the ego vehicle
            scenario: Parent scenario

        Returns:
            LaneFollowCar: Created lane-follow car
        """
        car = LaneFollowCar(
            obj_id=obj_id,
            scenario=scenario,
            is_ego=is_ego,
            length=vehicle.get('length', 4.8),
            width=vehicle.get('width', 1.7),
            height=vehicle.get('height', 1.9),
            target_speed=vehicle.get('target_speed', 10.0),
            look_ahead_distance=vehicle.get('look_ahead_distance', 15.0),
            lane_choice=vehicle.get('lane_choice', 'random'),
        )
        return car

    def _run_simulation(self, scenario: Scenario) -> None:
        """Run the simulation loop.

        Args:
            scenario: Scenario to simulate
        """
        print(f"Running simulation: {len(scenario.timestamps)} frames")

        # Simulate each time step (starting from frame 1)
        for i in range(1, len(scenario.timestamps)):
            last_ts = scenario.timestamps[i - 1]
            curr_ts = scenario.timestamps[i]
            last_frame = scenario.frames[last_ts]
            curr_frame = scenario.frames[curr_ts]

            # Update each vehicle's state for current time step
            for obj_id, last_obj in last_frame.get_obj_list().items():
                # Execute control and dynamics for one time step
                curr_obj = last_obj.step()

                # Only add to frame if vehicle should be present (not None)
                if curr_obj is not None:
                    scenario.add_obj_to_frame(curr_obj, curr_frame)

            # Update perception system with new spatial relationships
            curr_frame.update_perception(Perception(curr_frame, scenario.map))

    def _export_proto(self, scenario: Scenario, output_dir: Optional[str], output_name: str) -> str:
        """Export simulation results to protobuf format.

        Args:
            scenario: Completed scenario
            output_dir: Output directory (optional)
            output_name: Output name

        Returns:
            str: Path to generated protobuf file
        """
        # Create protobuf data structure
        data = scenario_data_pb2.ScenarioData()
        data.duration = scenario.duration
        data.frequency = scenario.frequency
        data.map_name = getattr(scenario, 'map_name', 'unknown')

        # Export ego_id
        if scenario.ego_id is not None:
            data.ego_id = scenario.ego_id

        # Export vehicle roster with static properties
        for obj_id, obj in scenario.roster.items():
            new_obj = data.roster[obj_id]
            new_obj.id = obj.id
            new_obj.length = obj.length
            new_obj.width = obj.width
            new_obj.height = obj.height
            new_obj.is_ego = obj.is_ego

        # Export all frames with vehicle states
        for ts, frame in scenario.frames.items():
            new_frame = data.frames[str(ts)]
            new_frame.timestamp = ts

            # Export each vehicle's state in this frame
            for obj_id, obj in frame.obj_list.items():
                new_obj = new_frame.obj_list[obj_id]
                # Position data
                new_obj.sp.position.x = obj.sp.position.x
                new_obj.sp.position.y = obj.sp.position.y
                new_obj.sp.position.z = obj.sp.position.z
                # Velocity data
                new_obj.sp.velocity.x = obj.sp.velocity.x
                new_obj.sp.velocity.y = obj.sp.velocity.y
                new_obj.sp.velocity.z = obj.sp.velocity.z
                # Acceleration data
                new_obj.sp.acceleration.x = obj.sp.acceleration.x if obj.sp.acceleration.x else 0.0
                new_obj.sp.acceleration.y = obj.sp.acceleration.y if obj.sp.acceleration.y else 0.0
                new_obj.sp.acceleration.z = obj.sp.acceleration.z if obj.sp.acceleration.z else 0.0
                # Heading/orientation data
                new_obj.sp.heading.roll = obj.sp.heading.roll
                new_obj.sp.heading.pitch = obj.sp.heading.pitch
                new_obj.sp.heading.yaw = obj.sp.heading.yaw

        # Determine output path
        if output_dir is None:
            output_dir = f'{SCENARIO_DATA}{output_name}/'

        # Create folder if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Write serialized data to file
        proto_path = os.path.join(output_dir, f'ava_scenario_{output_name}.pb')
        with open(proto_path, 'wb') as f:
            f.write(data.SerializeToString())

        return proto_path
