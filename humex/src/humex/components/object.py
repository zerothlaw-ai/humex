"""Object module for autonomous vehicle simulation.

This module defines base Object class and specialized Car class for representing
vehicles and other entities in the simulation with their physical attributes,
states, and behaviors.
"""

import math
from .statepoint import StatePoint, BoundingBox2D
from copy import copy

class Object(object):
    """Base class for simulation objects with physical attributes and state information.
    
    Stores both immutable properties (dimensions, ID) and mutable state information
    (position, velocity, etc.) that changes during simulation.
    """
    def __init__(self, obj_id=None, length=None, width=None, height=None, is_ego=False, scenario=None, object_type=""):
        """Initialize a simulation object with physical and state attributes.

        Args:
            obj_id: Unique identifier for this object
            length (float): Object length in meters
            width (float): Object width in meters
            height (float): Object height in meters
            is_ego (bool): Whether this is the ego vehicle
            scenario: Reference to the parent scenario
            object_type (str): Object type - "car", "pedestrian", "cyclist", "truck", etc.
        """
        # Global scenario access for map queries and other scenario data
        self.scenario = scenario

        # Immutable physical and identification information
        self.id = obj_id
        self.length = length
        self.width = width
        self.height = height
        self.is_ego = is_ego
        self.object_type = object_type

        # Mutable state information that changes during simulation
        self.sp = self._reset_sp()  # StatePoint (position, velocity, heading)
        self.bbox = self._reset_bbox()  # 2D bounding box for collision detection
        self.lane_id = None  # Current lane ID from map queries
        self.frame = None  # Reference to current frame
        self.status = "none"  # Status for visualization color coding

    def copy(self):
        """Create a shallow copy of this object with reset mutable state.
        
        Returns:
            Object: New object instance with same immutable attributes but reset state
        """
        new_obj = copy(self)
        new_obj.reset_mutable()
        return new_obj

    def reset_mutable(self):
        """Reset all mutable state information to default values.
        
        Called when creating object copies to ensure clean state for new instances.
        Resets position, velocity, bounding box, lane assignment, and frame reference.
        """
        self._reset_sp()
        self._reset_bbox()
        self.lane_id = None
        self.frame = None

    def _reset_sp(self):
        """Reset the StatePoint to default values.
        
        Returns:
            StatePoint: Newly created default StatePoint
        """
        self.sp = StatePoint()
        return self.sp

    def _reset_bbox(self):
        """Reset the bounding box with current object dimensions.
        
        Returns:
            BoundingBox2D: Newly created bounding box
        """
        self.bbox = BoundingBox2D(self.length, self.width)
        return self.bbox

    def update_mutable(self, sp):
        """Update mutable state information with new StatePoint.
        
        Args:
            sp (StatePoint): New state point with updated position, velocity, heading
        """
        self.sp = sp
        self._update_bbox()  # Update bounding box based on new position/heading
        # self._update_lane_id()  # Commented out - lane updates done elsewhere

    def _update_bbox(self):
        """Update bounding box vertices based on current state and dimensions."""
        self.bbox.update(self.sp, self.length, self.width)

    def _update_lane_id(self):
        """Query the map to determine which lane this object is currently in."""
        closest_pt, lane_id, _ = self.scenario.map.query_closest_point(self.sp.position.to_tuple())
        self.lane_id = lane_id

    def update_frame(self, frame):
        """Update reference to the current frame containing this object.
        
        Args:
            frame (Frame): The frame that now contains this object
        """
        self.frame = frame

    def to_dict(self):
        """Convert object to dictionary representation for serialization.
        
        Returns:
            dict: Dictionary containing all object attributes and current state
        """
        result = {
            'obj_id': self.id,
            'length': self.length,
            'width': self.width,
            'height': self.height,
            'is_ego': self.is_ego,
            'sp': self.sp.to_dict() if self.sp is not None else None
        }
        return result

    def step(self):
        """Update object state for one simulation time step.
        
        Base implementation does nothing. Subclasses should override
        to implement specific behavior and dynamics.
        
        Returns:
            Object: Updated object instance for next time step
        """
        pass


class Car(Object):
    """Car class representing a vehicle with dynamics and control systems.
    
    Extends the base Object class with vehicle-specific dimensions, dynamics model,
    and longitudinal/lateral controllers for autonomous driving simulation.
    """
    
    def __init__(self, obj_id=None, length=4.8, width=1.7, height=1.9, is_ego=False, scenario=None,
                 dynamic_model=None, lon_controller=None, lat_controller=None):
        """Initialize a Car object with dynamics and control systems.
        
        Args:
            obj_id: Unique identifier for this car
            length (float): Car length in meters (default: 4.8m)
            width (float): Car width in meters (default: 1.7m)
            height (float): Car height in meters (default: 1.9m)
            is_ego (bool): Whether this is the ego vehicle
            scenario: Reference to the parent scenario
            dynamic_model: Vehicle dynamics model for physics simulation
            lon_controller: Longitudinal controller (speed/acceleration)
            lat_controller: Lateral controller (steering)
        """
        super().__init__(obj_id=obj_id, length=length, width=width, height=height, 
                         is_ego=is_ego, scenario=scenario)
        
        # Control and dynamics systems
        self.dynamics_model = dynamic_model    # Physics model (e.g., bicycle model)
        self.lon_controller = lon_controller   # Speed/acceleration control
        self.lat_controller = lat_controller   # Steering control

    def step(self):
        """Execute one simulation step for this car.
        
        Performs longitudinal control (speed), lateral control (steering),
        applies vehicle dynamics, and returns updated car instance for next frame.
        
        Returns:
            Car: New car instance with updated state for next time step
        """
        curr_sp = self.sp

        # Longitudinal control - manage speed based on front vehicle
        front_agent_id = self.frame.perception.get_front(self.id)
        if front_agent_id is None:
            target_state_point = None  # No vehicle ahead, use default behavior
        else:
            # Get state of vehicle directly in front
            target_state_point = self.frame.get_obj(obj_id=front_agent_id).sp
            
        # Calculate commanded speed from longitudinal controller (e.g., ACC)
        cmd_speed = self.lon_controller.step(
            target_speed=self.sp.velocity.norm(), 
            target_statepoint=target_state_point, 
            ego_statepoint=self.sp
        )

        # Lateral control - manage steering to follow lane centerline
        look_ahead_dist = self.lat_controller.look_ahead_time * self.sp.velocity.norm()
        curr_pt = curr_sp.position.to_tuple()
        # Query map for target point ahead on the lane centerline
        target_pt, _, _ = self.scenario.map.query_point_in_front(curr_pt, distance=look_ahead_dist)
        # Calculate commanded steering angle from lateral controller (e.g., LKA)
        cmd_steer = self.lat_controller.step(curr_sp, target_pt)

        # Apply vehicle dynamics model to get new state
        new_sp = self.dynamics_model.step(curr_sp, cmd_speed, cmd_steer)

        # Create new car instance for next frame with updated state
        new_self = self.copy()
        new_self.update_mutable(new_sp)

        return new_self


class KeyframeCar(Object):
    """Car that follows keyframe-defined trajectory.

    Uses KeyframeBehavior to calculate trajectory from input keyframes.
    Input: List of StatePoints (position, velocity, heading - no timestamps)
    Output: Smooth trajectory with calculated timestamps for replay
    """

    def __init__(self, obj_id=None, length=4.8, width=1.7, height=1.9, is_ego=False, scenario=None, keystates=None):
        """Initialize KeyframeCar object.

        Args:
            obj_id: Unique identifier for this car
            length, width, height (float): Car dimensions in meters
            is_ego (bool): Whether this is the ego vehicle
            scenario: Reference to the parent scenario
            keystates (list): List of StatePoints (position, velocity, heading - no timestamps)
        """
        super().__init__(obj_id=obj_id, length=length, width=width, height=height,
                         is_ego=is_ego, scenario=scenario)

        # Import here to avoid circular imports
        from ..simulator.behavior import KeyframeBehavior

        # Create behavior handler (does the actual interpolation)
        self.behavior = KeyframeBehavior(keystates, scenario, obj_id=obj_id)
        self.current_frame_index = 0

    def step(self):
        """Get next state from behavior handler.

        Returns:
            KeyframeCar: New car instance with interpolated state, or None if vehicle should not be present
        """
        if not self.scenario or not self.scenario.timestamps:
            return self.copy()

        # Get current frame timestamp
        if self.current_frame_index < len(self.scenario.timestamps):
            current_timestamp = self.scenario.timestamps[self.current_frame_index]
            interpolated_state = self.behavior.get_state_at_time(current_timestamp)

            # If vehicle should not be present at this time, return None
            if interpolated_state is None:
                return None

            # Create new object instance with interpolated state
            new_self = self.copy()
            new_self.update_mutable(interpolated_state)
            new_self.current_frame_index = self.current_frame_index + 1

            return new_self

        # Return copy if we're past the scenario duration
        return self.copy()

    def get_trajectory(self):
        """Get complete trajectory for replay.

        Returns:
            list: List of StatePoints with calculated timestamps
        """
        return self.behavior.get_trajectory()

    def get_state_at_time(self, timestamp):
        """Get interpolated state at specific timestamp.

        Args:
            timestamp: Target timestamp (nanoseconds)

        Returns:
            StatePoint: Interpolated state, or None if vehicle should not be present
        """
        return self.behavior.get_state_at_time(timestamp)

    def get_keystate_times(self):
        """Get the calculated timestamps for each keystate.

        Returns:
            list: Timestamps (nanoseconds) for each input keystate
        """
        return self.behavior.get_keystate_times()


# Backward compatibility alias
KeyStatesCar = KeyframeCar


class LaneFollowCar(Object):
    """Car that follows lane centerlines using pure pursuit + ACC.

    Continuously drives along lane centerlines at a target speed.
    At lane forks, selects next lane based on the lane_choice strategy.
    Stops when the lane graph ends or the scenario ends.
    """

    def __init__(self, obj_id=None, length=4.8, width=1.7, height=1.9,
                 is_ego=False, scenario=None,
                 target_speed=10.0,
                 look_ahead_distance=15.0,
                 lane_choice="random"):
        super().__init__(obj_id=obj_id, length=length, width=width, height=height,
                         is_ego=is_ego, scenario=scenario)

        self.target_speed = target_speed
        self.look_ahead_distance = look_ahead_distance
        self.lane_choice = lane_choice

        # Reuse existing controllers and dynamics
        from ..simulator.vehicle.models import BicycleModel
        from ..simulator.vehicle.controllers import ACC, LKA

        self.dynamics_model = BicycleModel(scenario)
        self.lon_controller = ACC(interval=scenario.interval)
        self.lat_controller = LKA(look_ahead_time=0.0)  # We compute target point by distance, not time
        self._heading_initialized = False

    def _align_heading_to_lane(self, sp):
        """Align heading to the lane direction at the current position.

        Called on the first step to ensure heading matches the lane the car
        is on, regardless of what the config specified.
        """
        position = sp.position.to_tuple()
        lane_id = self.scenario.map.find_closest_lane(position)
        if lane_id is None:
            return sp

        # Get a point slightly ahead on the lane to determine direction
        fwd = self.scenario.map.get_lookahead_point(position, lane_id, 2.0, self.lane_choice)
        if fwd is None:
            return sp

        dx = fwd[0] - position[0]
        dy = fwd[1] - position[1]
        if dx * dx + dy * dy < 1e-9:
            return sp

        yaw = math.atan2(dy, dx)
        speed = sp.velocity.norm()
        vx = speed * math.cos(yaw)
        vy = speed * math.sin(yaw)

        return StatePoint(
            position=position,
            velocity=(vx, vy, 0.0),
            heading=(0.0, 0.0, yaw),
            acceleration=sp.acceleration.to_tuple() if sp.acceleration.x is not None else (0, 0, 0),
        )

    def step(self):
        curr_sp = self.sp

        # On first step, align heading to lane direction
        if not self._heading_initialized:
            self._heading_initialized = True
            curr_sp = self._align_heading_to_lane(curr_sp)

        position = curr_sp.position.to_tuple()
        heading = curr_sp.heading.yaw if curr_sp.heading else None
        if heading is not None and abs(heading) > 10.0:
            heading = math.radians(heading)

        # Find current lane
        lane_id = self.scenario.map.find_closest_lane(position, heading=heading)
        if lane_id is None:
            # Can't find a lane — coast with no steering
            new_self = self.copy()
            new_self.update_mutable(curr_sp)
            return new_self

        # Get lookahead target point
        target_point = self.scenario.map.get_lookahead_point(
            position, lane_id, self.look_ahead_distance, self.lane_choice
        )

        # Longitudinal control — ACC with car-following awareness
        front_agent_id = self.frame.perception.get_front(self.id)
        target_statepoint = None
        if front_agent_id is not None:
            target_statepoint = self.frame.get_obj(obj_id=front_agent_id).sp

        if target_point is None:
            # Dead end — decelerate to stop
            cmd_speed = self.lon_controller.step(
                target_speed=0.0,
                target_statepoint=target_statepoint,
                ego_statepoint=curr_sp,
            )
        else:
            cmd_speed = self.lon_controller.step(
                target_speed=self.target_speed,
                target_statepoint=target_statepoint,
                ego_statepoint=curr_sp,
            )

        # Lateral control — pure pursuit toward target point
        cmd_steer = self.lat_controller.step(curr_sp, target_point)

        # Apply dynamics
        new_sp = self.dynamics_model.step(curr_sp, cmd_speed, cmd_steer)

        new_self = self.copy()
        new_self.update_mutable(new_sp)
        return new_self


class SmartKeyframeCar(Object):
    """Car that follows keyframe trajectory using physics-based simulation.

    Uses SmartKeyframeBehavior with BicycleModel + PurePursuit + PID control
    to generate realistic trajectories that follow keystate waypoints.
    Unlike KeyframeCar which uses Hermite spline interpolation to guarantee
    exact positions at keystates, this uses physics simulation for more
    realistic vehicle motion.
    """

    def __init__(self, obj_id=None, length=4.8, width=1.7, height=1.9, is_ego=False, scenario=None,
                 keystates=None, speed_controller='kinematics',
                 heading_controller='pure_pursuit', turning_radius=6.0):
        """Initialize SmartKeyframeCar object.

        Args:
            obj_id: Unique identifier for this car
            length, width, height (float): Car dimensions in meters
            is_ego (bool): Whether this is the ego vehicle
            scenario: Reference to the parent scenario
            keystates (list): List of StatePoints (position, velocity, heading - no timestamps)
            speed_controller (str): Speed control mode - 'kinematics' or 'pid'
            heading_controller (str): Heading control mode - 'pure_pursuit' or 'dubins'
            turning_radius (float): Dubins minimum turning radius in meters
        """
        super().__init__(obj_id=obj_id, length=length, width=width, height=height,
                         is_ego=is_ego, scenario=scenario)

        # Import here to avoid circular imports
        from ..simulator.behavior import SmartKeyframeBehavior

        # Create behavior handler (does the physics-based simulation)
        self.behavior = SmartKeyframeBehavior(keystates, scenario, obj_id=obj_id,
                                              speed_controller=speed_controller,
                                              heading_controller=heading_controller,
                                              turning_radius=turning_radius)
        self.current_frame_index = 0

    def step(self):
        """Get next state from behavior handler.

        Returns:
            SmartKeyframeCar: New car instance with simulated state, or None if vehicle should not be present
        """
        if not self.scenario or not self.scenario.timestamps:
            return self.copy()

        # Get current frame timestamp
        if self.current_frame_index < len(self.scenario.timestamps):
            current_timestamp = self.scenario.timestamps[self.current_frame_index]
            simulated_state = self.behavior.get_state_at_time(current_timestamp)

            # If vehicle should not be present at this time, return None
            if simulated_state is None:
                return None

            # Create new object instance with simulated state
            new_self = self.copy()
            new_self.update_mutable(simulated_state)
            new_self.current_frame_index = self.current_frame_index + 1

            return new_self

        # Return copy if we're past the scenario duration
        return self.copy()

    def get_trajectory(self):
        """Get complete trajectory for replay.

        Returns:
            list: List of StatePoints with calculated timestamps
        """
        return self.behavior.get_trajectory()

    def get_state_at_time(self, timestamp):
        """Get simulated state at specific timestamp.

        Args:
            timestamp: Target timestamp (nanoseconds)

        Returns:
            StatePoint: Simulated state, or None if vehicle should not be present
        """
        return self.behavior.get_state_at_time(timestamp)

    def get_keystate_times(self):
        """Get the calculated timestamps for each keystate.

        Returns:
            list: Timestamps (nanoseconds) for each input keystate
        """
        return self.behavior.get_keystate_times()







