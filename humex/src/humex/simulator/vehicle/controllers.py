"""Vehicle control systems for autonomous driving simulation.

This module implements various longitudinal (speed) and lateral (steering)
control systems commonly used in autonomous vehicles, including adaptive
cruise control (ACC) and lane keeping assist (LKA).
"""

import numpy as np
from ...components.statepoint import StatePoint


# ========= Longitudinal Controllers =========
class ConstantSpeed(object):
    """Simple constant speed longitudinal controller.
    
    Maintains a fixed commanded speed regardless of traffic or road conditions.
    Useful for basic testing and scenarios without dynamic speed control.
    """
    def __init__(self, cmd_speed=10.0):
        """Initialize constant speed controller.
        
        Args:
            cmd_speed (float): Constant speed to maintain in m/s (default: 10.0)
        """
        self.cmd_speed = cmd_speed

    def step(self):
        """Return constant commanded speed.
        
        Returns:
            float: Commanded speed in m/s
        """
        return self.cmd_speed


class ACC(object):
    """Adaptive Cruise Control (ACC) longitudinal controller.
    
    Implements intelligent speed control that maintains a safe following distance
    behind lead vehicles while trying to maintain a target speed in free flow.
    Uses PID controllers for both speed and distance regulation.
    """
    def __init__(self, interval=None, target_time_gap=3.0, min_dist=5.0, max_accel=5.0, min_accel=-3.0):
        """Initialize ACC controller with safety and performance parameters.
        
        Args:
            interval (float): Control loop time step in seconds
            target_time_gap (float): Desired time headway behind lead vehicle (seconds)
            min_dist (float): Minimum following distance in meters
            max_accel (float): Maximum acceleration in m/s²
            min_accel (float): Maximum deceleration in m/s² (negative value)
        """
        self.interval = interval
        
        # PID controller for distance regulation (car-following mode)
        self.distance_control = PID(interval=interval)
        self.distance_control.set_gains(k_p=0.6, k_i=0.2, k_d=0.1)

        # PID controller for speed regulation (free-flow mode)
        self.speed_control = PID(interval=interval)
        self.speed_control.set_gains(k_p=0.4)  # Proportional-only control

        # Safety and comfort parameters
        self.time_gap = target_time_gap  # Seconds of following time
        self.min_dist = min_dist         # Minimum distance regardless of speed
        self.max_accel = max_accel       # Comfort limit for acceleration
        self.min_accel = min_accel       # Comfort limit for braking

    def step(self, target_speed=None, target_statepoint=None, ego_statepoint=None):
        """Execute one control step of ACC algorithm.
        
        Determines whether to operate in free-flow (speed control) or car-following
        (distance control) mode based on presence and proximity of lead vehicle.
        
        Args:
            target_speed (float): Desired cruise speed in m/s
            target_statepoint (StatePoint, optional): State of lead vehicle if present
            ego_statepoint (StatePoint): Current state of ego vehicle
            
        Returns:
            float: Commanded speed for next time step in m/s
        """
        current_speed = ego_statepoint.velocity.norm()
        
        # Determine control mode based on presence of lead vehicle
        if target_statepoint is None:
            # Free-flow mode: no lead vehicle detected, maintain target speed
            control = self.speed_control.step(target_speed, current_speed)
        else:
            # Calculate current distance to lead vehicle
            current_dist = StatePoint.get_dist(target_statepoint, ego_statepoint)
            # Calculate desired following distance based on time gap policy
            target_dist = current_speed * self.time_gap + self.min_dist
            
            if current_dist > target_dist:
                # Safe distance maintained, use speed control
                control = self.speed_control.step(target_speed, current_speed)
            else:
                # Too close to lead vehicle, use distance control
                control = self.distance_control.step(target_dist, current_dist)
                control *= -1.0  # Invert for proper deceleration response

        # Apply acceleration limits for comfort and safety
        accel = min(self.max_accel, max(self.min_accel, control))

        # Prevent negative speeds (vehicle can't go backwards)
        if current_speed == 0 and accel < 0:
            return 0.0

        # Calculate new speed using simple integration
        result_speed = current_speed + self.interval * accel
        return result_speed


class PID(object):
    """Proportional-Integral-Derivative (PID) controller.
    
    General-purpose feedback controller used by ACC for both speed and distance
    regulation. Provides proportional response to current error, integral action
    for steady-state error elimination, and derivative action for stability.
    """
    def __init__(self, interval=None, windup_guard=10.0, k_p=None, k_i=None, k_d=None):
        """Initialize PID controller with gains and parameters.
        
        Args:
            interval (float): Control loop time step in seconds
            windup_guard (float): Maximum allowed integral accumulation to prevent windup
            k_p (float, optional): Proportional gain
            k_i (float, optional): Integral gain
            k_d (float, optional): Derivative gain
        """
        # PID gains (tuning parameters)
        self.k_p = k_p  # Proportional gain - immediate response to error
        self.k_i = k_i  # Integral gain - eliminates steady-state error
        self.k_d = k_d  # Derivative gain - dampens oscillations

        # Control loop parameters
        self.interval = interval
        self.windup_guard = windup_guard  # Limit integral term to prevent windup

        # Internal state variables for PID computation
        self.p_output = None    # Proportional term output
        self.i_output = None    # Integral term output
        self.d_output = None    # Derivative term output

        # Historical data for integral and derivative calculations
        self.last_error = None  # Previous error for derivative calculation
        self.net_error = 0.0    # Accumulated error for integral calculation
        self.timestamp = 0.0    # Internal time tracking

    def set_gains(self, k_p=0.1, k_i=0.0, k_d=0.0):
        """Set PID controller gains.
        
        Args:
            k_p (float): Proportional gain (default: 0.1)
            k_i (float): Integral gain (default: 0.0)
            k_d (float): Derivative gain (default: 0.0)
        """
        self.k_p = k_p
        self.k_i = k_i
        self.k_d = k_d

    def step(self, target_val, feedback_val):
        """Execute one PID control step.
        
        Args:
            target_val (float): Desired setpoint value
            feedback_val (float): Current measured value
            
        Returns:
            float: Control output (sum of P, I, and D terms)
        """
        # Calculate control error
        error = target_val - feedback_val

        # Proportional term - immediate response proportional to current error
        self.p_output = self.k_p * error

        # Integral term - accumulates error over time to eliminate steady-state offset
        self.net_error += error * self.interval
        # Apply windup guard to prevent integral term from growing too large
        self.i_output = self.k_i * min(max(self.net_error, -self.windup_guard), self.windup_guard)

        # Derivative term - responds to rate of error change to improve stability
        self.d_output = 0.0
        if self.timestamp > 0:  # Need previous error for derivative calculation
            self.d_output = self.k_d * (error - self.last_error) / self.interval

        # Update internal state for next iteration
        self.last_error = error
        self.timestamp += self.interval

        # Return combined PID output
        return self.p_output + self.i_output + self.d_output


# ========= Lateral Controllers =========
class ConstantSteer(object):
    """Simple constant steering angle lateral controller.
    
    Applies a fixed steering command regardless of vehicle state or road geometry.
    Useful for basic testing and scenarios with predetermined steering inputs.
    """
    def __init__(self, cmd_steer=0.0):
        """Initialize constant steering controller.
        
        Args:
            cmd_steer (float): Constant steering angle in radians (default: 0.0)
        """
        self.cmd_steer = cmd_steer

    def step(self):
        """Return constant commanded steering angle.
        
        Returns:
            float: Commanded steering angle in radians
        """
        return self.cmd_steer


class LKA:
    """Lane Keeping Assist (LKA) lateral controller.
    
    Implements pure pursuit algorithm to follow lane centerlines or target paths.
    Uses look-ahead distance to determine steering commands that guide the vehicle
    toward desired trajectory points ahead of the current position.
    """
    def __init__(self, look_ahead_time):
        """Initialize LKA controller with look-ahead parameters.
        
        Args:
            look_ahead_time (float): Time ahead to look for target point (seconds)
        """
        self.look_ahead_time = look_ahead_time
        self.wheel_dist = 2.0  # Vehicle wheelbase in meters TODO: Read from config

    def step(self, current_state, target_point):
        """Execute one control step of LKA algorithm.
        
        Args:
            current_state (StatePoint): Current vehicle state
            target_point (tuple): Target point coordinates (x, y, z) to aim for
            
        Returns:
            float: Commanded steering angle in radians
        """
        if current_state is not None and target_point is not None:
            steering = self._pure_pursuit(current_state, target_point)
            return steering
        return 0.0  # No steering if missing state or target information

    def _pure_pursuit(self, current_state, target_point):
        """Implement pure pursuit steering algorithm.
        
        Pure pursuit calculates steering angle to reach a target point by finding
        the radius of curvature needed to intersect the target point.
        
        Args:
            current_state (StatePoint): Current vehicle state
            target_point (tuple): Target point coordinates (x, y, z)
            
        Returns:
            float: Steering angle in radians
        """
        # Extract current vehicle state
        current_x = current_state.position.x
        current_y = current_state.position.y
        current_yaw = current_state.heading.yaw
        target_x, target_y, target_z = target_point

        # Calculate geometric relationship to target point
        target_angle = np.arctan2(target_y - current_y, target_x - current_x)
        target_dist = np.sqrt((target_x - current_x)**2 + (target_y - current_y)**2)
        target_delta_yaw = target_angle - current_yaw

        # Apply pure pursuit formula only if target is sufficiently far
        steering = 0.0
        if target_dist >= 0.5:  # Minimum distance threshold to avoid numerical issues
            # Pure pursuit steering equation based on vehicle wheelbase and geometry
            steering = np.arctan((2 * self.wheel_dist * np.sin(target_delta_yaw)) / target_dist)
            
        return steering




