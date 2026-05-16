"""Autonomous vehicle simulation engine.

This module provides the core simulation functionality for autonomous vehicle
scenarios, including initialization from configuration files, physics simulation,
control system execution, and data export.
"""

import json
import os
import time
from humex.proto import scenario_pb2 as scenario_data_pb2
from ..components.scenario import Scenario
from ..components.statepoint import StatePoint
from ..components.object import Car, KeyframeCar, SmartKeyframeCar, LaneFollowCar
from ..components.perception import Perception
from .vehicle.models import BicycleModel
from .vehicle.controllers import LKA, ACC
from ..utils.paths import SCENARIO_DATA, SCENARIO_CONFIG


class Simulator(object):
    """Main simulation engine for autonomous vehicle scenarios.
    
    Manages the complete simulation lifecycle from initialization through
    execution to data export. Supports multiple vehicles with different
    control systems and dynamics models.
    """
    def __init__(self, config_name=None):
        """Initialize simulator with configuration.
        
        Args:
            config_name (str): Name of configuration file (without .json extension)
        """
        self.scenario = None
        self.scenario_name = config_name
        config_path = f'{SCENARIO_CONFIG}{config_name}.json'
        self.initialize(config_path)

    def initialize(self, config_path):
        """Initialize simulation from JSON configuration file.
        
        Loads scenario parameters, creates vehicles with control systems,
        sets up initial states, and configures the simulation environment.
        
        Args:
            config_path (str): Path to JSON configuration file
        """
        start = time.perf_counter()

        
        # Load configuration from JSON file
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        # Extract scenario parameters
        map_name = config['map']
        duration, frequency = config['duration'], config['frequency']
        self.scenario = Scenario(duration, frequency, map_obj=None)
        self.scenario.map_name = map_name  # Add map_name attribute for protobuf export
        
        # Initialize vehicles from configuration
        for vehicle in config['vehicles']:
            obj_id = int(vehicle['id'])  # Convert to integer for protobuf compatibility
            is_ego = vehicle['name'] == 'ego'
            object_type = vehicle.get('object_type', 'car')  # Default to 'car' if not specified

            if object_type == 'keyframe' or object_type == 'smartkeyframe':
                # Create keyframe-based car with keystates (no timestamps in input)
                keystates_data = vehicle.get('keystates', [])
                keystates = []

                for keystate_data in keystates_data:
                    position = tuple(keystate_data['position'])
                    velocity = tuple(keystate_data['velocity'])

                    heading = tuple(keystate_data.get('heading', (0, 0, 0)))

                    # Create StatePoint for this keystate (no timestamp)
                    state_point = StatePoint(
                        obj_id=obj_id,
                        position=position,
                        velocity=velocity,
                        heading=heading
                    )

                    keystates.append(state_point)

                # Create appropriate car object based on type
                if object_type == 'smartkeyframe':
                    speed_controller = vehicle.get('speed_controller', 'kinematics')
                    heading_controller = vehicle.get('heading_controller', 'pure_pursuit')
                    turning_radius = vehicle.get('turning_radius', 6.0)
                    car = SmartKeyframeCar(
                        obj_id=obj_id,
                        scenario=self.scenario,
                        keystates=keystates,
                        is_ego=is_ego,
                        speed_controller=speed_controller,
                        heading_controller=heading_controller,
                        turning_radius=turning_radius,
                    )
                else:
                    car = KeyframeCar(
                        obj_id=obj_id,
                        scenario=self.scenario,
                        keystates=keystates,
                        is_ego=is_ego
                    )

                # Add to scenario roster
                self.scenario.add_obj_to_roster(car)

                # Add initial state to first frame
                initial_frame = self.scenario.frames[0]
                initial_car = self.scenario.get_obj_copy_from_roster(obj_id=obj_id)
                initial_state = car.get_state_at_time(self.scenario.timestamps[0])
                if initial_state:
                    initial_car.update_mutable(initial_state)
                    self.scenario.add_obj_to_frame(initial_car, initial_frame)

            elif object_type == 'lanefollow':
                # Lane-following car with pure pursuit + ACC
                vel = tuple(vehicle['initial_states']['velocity'])
                import math as _math
                yaw = _math.atan2(vel[1], vel[0]) if (vel[0] != 0 or vel[1] != 0) else 0.0
                sp = StatePoint(
                    obj_id=obj_id,
                    position=tuple(vehicle['initial_states']['position']),
                    velocity=vel,
                    heading=(0.0, 0.0, yaw),
                )

                car = LaneFollowCar(
                    obj_id=obj_id,
                    scenario=self.scenario,
                    is_ego=is_ego,
                    target_speed=vehicle.get('target_speed', 10.0),
                    look_ahead_distance=vehicle.get('look_ahead_distance', 15.0),
                    lane_choice=vehicle.get('lane_choice', 'random'),
                )

                self.scenario.add_obj_to_roster(car)

                initial_frame = self.scenario.frames[0]
                initial_car = self.scenario.get_obj_copy_from_roster(obj_id=obj_id)
                initial_car.update_mutable(sp)
                self.scenario.add_obj_to_frame(initial_car, initial_frame)

            else:
                # Default car type with dynamics and controllers
                # Create initial state point from configuration
                sp = StatePoint(
                    obj_id=obj_id,
                    position=tuple(vehicle['initial_states']['position']),
                    velocity=tuple(vehicle['initial_states']['velocity'])
                )

                # Create car with dynamics model and controllers
                car = Car(
                    obj_id=obj_id,
                    scenario=self.scenario,
                    dynamic_model=BicycleModel(self.scenario),
                    lon_controller=ACC(interval=self.scenario.interval),
                    lat_controller=LKA(look_ahead_time=0.3)
                )

                # Mark ego vehicle
                car.is_ego = is_ego
                self.scenario.add_obj_to_roster(car)

                # Add vehicle to initial frame with starting state
                initial_frame = self.scenario.frames[0]
                initial_car = self.scenario.get_obj_copy_from_roster(obj_id=obj_id)
                initial_car.update_mutable(sp)
                self.scenario.add_obj_to_frame(initial_car, initial_frame)

        # Initialize perception system for spatial relationships (after all vehicles are added)
        initial_frame = self.scenario.frames[0]
        initial_frame.update_perception(Perception(initial_frame, self.scenario.map))

        end = time.perf_counter()
        print(f"Initialization took {end - start:.6f} seconds")

    def run(self):
        """Execute the complete simulation.
        
        Steps through all time frames, updating vehicle states through their
        control systems and dynamics models, maintaining perception data,
        and finally exporting results.
        
        Returns:
            str: Scenario name for the generated data
        """
        print(f'Simulator is simulating: {self.scenario_name}')
        start = time.perf_counter()
        
        # Simulate each time step
        for i in range(1, len(self.scenario.timestamps)):
            # Get previous and current time frames
            last_ts, curr_ts = self.scenario.timestamps[i - 1], self.scenario.timestamps[i]
            last_frame, curr_frame = self.scenario.frames[last_ts], self.scenario.frames[curr_ts]
            
            # Update each vehicle's state for current time step
            for obj_id, last_obj in last_frame.get_obj_list().items():
                # Execute control and dynamics for one time step
                curr_obj = last_obj.step()
                # Only add to frame if vehicle should be present (not None)
                if curr_obj is not None:
                    self.scenario.add_obj_to_frame(curr_obj, curr_frame)

            # Update perception system with new spatial relationships
            curr_frame.update_perception(Perception(curr_frame, self.scenario.map))

        # Export simulation results to protobuf format
        self.dump_proto(data_name=self.scenario_name)
        # Alternative JSON export (commented out)
        # self.dump_json(data_name=self.scenario_name)
        
        end = time.perf_counter()
        print(f"Running took {end - start:.6f} seconds")

        return self.scenario_name

    def dump_proto(self, data_name):
        """Export simulation data to protobuf format.

        Creates a folder named after data_name in the output directory and
        saves the scenario protobuf file using the standard naming convention.

        Args:
            data_name (str): Name for the output folder and scenario

        Returns:
            str: Path to the generated protobuf file
        """
        # Create protobuf data structure
        data = scenario_data_pb2.ScenarioData()
        data.duration = self.scenario.duration
        data.frequency = self.scenario.frequency
        data.map_name = self.scenario.map_name
        
        # Export vehicle roster with static properties
        for obj_id, obj in self.scenario.roster.items():
            new_obj = data.roster[obj_id]
            new_obj.id = obj.id
            new_obj.length, new_obj.width, new_obj.height = obj.length, obj.width, obj.height
            new_obj.is_ego = obj.is_ego
            
        # Export all frames with vehicle states
        for ts, frame in self.scenario.frames.items():
            new_frame = data.frames[str(ts)]
            new_frame.timestamp = ts
            
            # Export each vehicle's state in this frame
            for obj_id, obj in frame.obj_list.items():
                new_obj = new_frame.obj_list[obj_id]
                # Position data
                new_obj.sp.position.x, new_obj.sp.position.y, new_obj.sp.position.z = (
                    obj.sp.position.x, obj.sp.position.y, obj.sp.position.z
                )
                # Velocity data
                new_obj.sp.velocity.x, new_obj.sp.velocity.y, new_obj.sp.velocity.z = (
                    obj.sp.velocity.x, obj.sp.velocity.y, obj.sp.velocity.z
                )
                # Heading/orientation data
                new_obj.sp.heading.roll, new_obj.sp.heading.pitch, new_obj.sp.heading.yaw = (
                    obj.sp.heading.roll, obj.sp.heading.pitch, obj.sp.heading.yaw
                )
                # Acceleration data
                new_obj.sp.acceleration.x, new_obj.sp.acceleration.y, new_obj.sp.acceleration.z = (
                    obj.sp.acceleration.x, obj.sp.acceleration.y, obj.sp.acceleration.z
                )

        # Create output folder structure
        scenario_folder = f'{SCENARIO_DATA}{data_name}/'

        # Create folder if it doesn't exist
        if not os.path.exists(scenario_folder):
            os.makedirs(scenario_folder)

        # Write serialized data to file with proper naming convention
        data_path = f'{scenario_folder}ava_scenario_{data_name}.pb'
        with open(data_path, 'wb') as f:
            f.write(data.SerializeToString())

        print(f"Scenario data generated: {data_path}")
        return data_path


if __name__ == '__main__':
    # Example usage - run simulation with two-car ACC scenario
    sim = Simulator('test4-2')
    sim.run()