"""Vehicle dynamics models for autonomous vehicle simulation.

This module implements various vehicle dynamics models used to simulate
the physical behavior and motion of vehicles in response to control inputs.
"""

import numpy as np
from ...components.statepoint import StatePoint


class BicycleModel(object):
    """Bicycle model for vehicle dynamics simulation.
    
    Implements the kinematic bicycle model, a simplified 2D vehicle model
    that captures the essential steering and motion characteristics of a car.
    Used for real-time simulation and control system development.
    """
    def __init__(self, scenario):
        """Initialize bicycle model with scenario parameters.
        
        Args:
            scenario: Simulation scenario containing timing and configuration data
        """
        self.interval = scenario.interval

        # Vehicle geometric parameters
        # TODO: Read these from configuration file instead of hardcoding
        self.front_wheel_dist = 2.0  # Distance from center to front axle (m)
        self.back_wheel_dist = 2.0   # Distance from center to rear axle (m)

    def step(self, current_state, cmd_speed, cmd_steering):
        """Execute one time step of the bicycle model dynamics.
        
        Implements the kinematic bicycle model equations to update vehicle
        position, heading, and velocity based on control inputs.
        
        Args:
            current_state (StatePoint): Current vehicle state (position, velocity, heading)
            cmd_speed (float): Commanded speed in m/s
            cmd_steering (float): Commanded steering angle in radians
            
        Returns:
            StatePoint: Updated vehicle state for next time step
        """
        # Extract current state values
        current_x = current_state.position.x
        current_y = current_state.position.y
        current_yaw = current_state.heading.yaw

        # Bicycle model kinematic equations
        # Calculate slip angle (angle between velocity vector and vehicle heading)
        slip_angle = np.arctan(
            self.back_wheel_dist / (self.front_wheel_dist + self.back_wheel_dist) * np.tan(cmd_steering)
        )
        
        # Calculate yaw rate (rate of change of heading)
        yaw_rate = cmd_speed / self.back_wheel_dist * np.sin(slip_angle)
        
        # Update heading
        yaw = current_yaw + yaw_rate * self.interval
        
        # Calculate velocity components in global frame
        v_x = cmd_speed * np.cos(yaw + slip_angle)
        v_y = cmd_speed * np.sin(yaw + slip_angle)

        # Compute acceleration (change in velocity / time interval)
        prev_vx = current_state.velocity.x if current_state.velocity.x else 0.0
        prev_vy = current_state.velocity.y if current_state.velocity.y else 0.0
        accel_x = (v_x - prev_vx) / self.interval
        accel_y = (v_y - prev_vy) / self.interval
        accel_z = 0.0  # No vertical motion in 2D model

        # Update position using integrated velocity
        result_position = (
            current_x + v_x * self.interval,
            current_y + v_y * self.interval,
            0.0
        )
        result_heading = (0.0, 0.0, yaw)
        result_velocity = (v_x, v_y, 0.0)  # Store velocity components in global frame
        result_acceleration = (accel_x, accel_y, accel_z)

        # Create and return new state point
        result = StatePoint(
            position=result_position,
            heading=result_heading,
            velocity=result_velocity,
            acceleration=result_acceleration
        )

        return result