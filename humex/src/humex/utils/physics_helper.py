"""Physics utility functions for autonomous vehicle simulation.

This module provides Newton's kinematic equations and other physics-based
calculations used throughout the humex framework for motion modeling,
trajectory planning, and vehicle dynamics.
"""

import math


# ========= Newton's Kinematic Equations =========
def kinematic_position(initial_position, initial_velocity, acceleration, time):
    """Calculate position using Newton's kinematic equation: s = s₀ + v₀t + ½at².

    Computes final position given initial conditions and constant acceleration.
    Supports both scalar and vector calculations.

    Args:
        initial_position (float or tuple): Initial position s₀ (scalar or (x, y, z))
        initial_velocity (float or tuple): Initial velocity v₀ (scalar or (vx, vy, vz))
        acceleration (float or tuple): Constant acceleration a (scalar or (ax, ay, az))
        time (float): Time interval t in seconds

    Returns:
        float or tuple: Final position (same type as input)

    Examples:
        >>> kinematic_position(0, 10, 2, 3)  # 1D case
        39.0
        >>> kinematic_position((0, 0, 0), (10, 5, 0), (2, 1, 0), 3)  # 3D case
        (39.0, 19.5, 0.0)
    """
    if isinstance(initial_position, (tuple, list)):
        # Vector case - apply equation component-wise
        return tuple(
            s0 + v0 * time + 0.5 * a * time**2
            for s0, v0, a in zip(initial_position, initial_velocity, acceleration)
        )
    else:
        # Scalar case
        return initial_position + initial_velocity * time + 0.5 * acceleration * time**2


def kinematic_velocity(initial_velocity, acceleration, time):
    """Calculate velocity using Newton's kinematic equation: v = v₀ + at.

    Computes final velocity given initial velocity and constant acceleration.
    Supports both scalar and vector calculations.

    Args:
        initial_velocity (float or tuple): Initial velocity v₀ (scalar or (vx, vy, vz))
        acceleration (float or tuple): Constant acceleration a (scalar or (ax, ay, az))
        time (float): Time interval t in seconds

    Returns:
        float or tuple: Final velocity (same type as input)

    Examples:
        >>> kinematic_velocity(10, 2, 3)  # 1D case
        16.0
        >>> kinematic_velocity((10, 5, 0), (2, 1, 0), 3)  # 3D case
        (16.0, 8.0, 0.0)
    """
    if isinstance(initial_velocity, (tuple, list)):
        # Vector case - apply equation component-wise
        return tuple(v0 + a * time for v0, a in zip(initial_velocity, acceleration))
    else:
        # Scalar case
        return initial_velocity + acceleration * time


def kinematic_position_from_velocities(initial_position, initial_velocity, final_velocity, time):
    """Calculate position using kinematic equation: s = s₀ + (v₀ + v)t/2.

    Uses average velocity method when both initial and final velocities are known.
    Assumes constant acceleration between initial and final velocity.

    Args:
        initial_position (float or tuple): Initial position s₀
        initial_velocity (float or tuple): Initial velocity v₀
        final_velocity (float or tuple): Final velocity v
        time (float): Time interval t in seconds

    Returns:
        float or tuple: Final position (same type as input)

    Examples:
        >>> kinematic_position_from_velocities(0, 10, 16, 3)  # 1D case
        39.0
        >>> kinematic_position_from_velocities((0, 0, 0), (10, 5, 0), (16, 8, 0), 3)
        (39.0, 19.5, 0.0)
    """
    if isinstance(initial_position, (tuple, list)):
        # Vector case - apply equation component-wise
        return tuple(
            s0 + (v0 + vf) * time / 2.0
            for s0, v0, vf in zip(initial_position, initial_velocity, final_velocity)
        )
    else:
        # Scalar case
        return initial_position + (initial_velocity + final_velocity) * time / 2.0


def kinematic_velocity_squared(initial_velocity, acceleration, displacement):
    """Calculate velocity using kinematic equation: v² = v₀² + 2as.

    Computes final velocity from initial velocity, acceleration, and displacement.
    Useful when time is unknown but displacement is known.

    Args:
        initial_velocity (float or tuple): Initial velocity v₀
        acceleration (float or tuple): Constant acceleration a
        displacement (float or tuple): Displacement s - s₀

    Returns:
        float or tuple: Final velocity (same type as input)

    Examples:
        >>> kinematic_velocity_squared(10, 2, 39)  # 1D case
        16.0
        >>> kinematic_velocity_squared((10, 5, 0), (2, 1, 0), (39, 19.5, 0))
        (16.0, 8.0, 0.0)
    """
    if isinstance(initial_velocity, (tuple, list)):
        # Vector case - apply equation component-wise
        return tuple(
            math.sqrt(v0**2 + 2 * a * s) if (v0**2 + 2 * a * s) >= 0 else 0.0
            for v0, a, s in zip(initial_velocity, acceleration, displacement)
        )
    else:
        # Scalar case
        velocity_squared = initial_velocity**2 + 2 * acceleration * displacement
        return math.sqrt(max(0.0, velocity_squared))  # Avoid negative square root


def kinematic_time_to_velocity(initial_velocity, final_velocity, acceleration):
    """Calculate time required to reach final velocity: t = (v - v₀)/a.

    Computes time needed to change from initial to final velocity at constant acceleration.

    Args:
        initial_velocity (float): Initial velocity v₀
        final_velocity (float): Target final velocity v
        acceleration (float): Constant acceleration a (must be non-zero)

    Returns:
        float: Time required in seconds

    Raises:
        ValueError: If acceleration is zero

    Examples:
        >>> kinematic_time_to_velocity(10, 16, 2)
        3.0
        >>> kinematic_time_to_velocity(20, 0, -5)  # Braking
        4.0
    """
    if abs(acceleration) < 1e-12:
        raise ValueError("Acceleration cannot be zero for time calculation")

    return (final_velocity - initial_velocity) / acceleration


def kinematic_time_to_displacement(initial_velocity, acceleration, displacement):
    """Calculate time to travel given displacement: solve s = v₀t + ½at² for t.

    Solves the quadratic equation to find time needed for given displacement.
    Returns the positive (physical) solution.

    Args:
        initial_velocity (float): Initial velocity v₀
        acceleration (float): Constant acceleration a
        displacement (float): Target displacement s

    Returns:
        float: Time required in seconds (positive solution)

    Raises:
        ValueError: If no real positive solution exists

    Examples:
        >>> kinematic_time_to_displacement(10, 2, 39)
        3.0
        >>> kinematic_time_to_displacement(0, 5, 45)  # From rest
        4.24
    """
    # Handle special case of zero acceleration (constant velocity)
    if abs(acceleration) < 1e-12:
        if abs(initial_velocity) < 1e-12:
            raise ValueError("Cannot reach displacement with zero velocity and zero acceleration")
        return displacement / initial_velocity

    # Solve quadratic equation: ½at² + v₀t - s = 0
    # Using quadratic formula: t = (-v₀ ± √(v₀² + 2as)) / a
    a_coeff = 0.5 * acceleration
    b_coeff = initial_velocity
    c_coeff = -displacement

    discriminant = b_coeff**2 - 4 * a_coeff * c_coeff

    if discriminant < 0:
        raise ValueError("No real solution exists for given displacement")

    # Calculate both solutions
    sqrt_discriminant = math.sqrt(discriminant)
    t1 = (-b_coeff + sqrt_discriminant) / (2 * a_coeff)
    t2 = (-b_coeff - sqrt_discriminant) / (2 * a_coeff)

    # Return the positive solution
    if t1 > 0 and t2 > 0:
        return min(t1, t2)  # Both positive, return smaller
    elif t1 > 0:
        return t1
    elif t2 > 0:
        return t2
    else:
        raise ValueError("No positive time solution exists")


def kinematic_acceleration_from_velocities(initial_velocity, final_velocity, time):
    """Calculate acceleration from velocity change: a = (v - v₀)/t.

    Computes constant acceleration needed to change velocity over given time.

    Args:
        initial_velocity (float or tuple): Initial velocity v₀
        final_velocity (float or tuple): Final velocity v
        time (float): Time interval t in seconds (must be non-zero)

    Returns:
        float or tuple: Required acceleration (same type as input)

    Raises:
        ValueError: If time is zero or negative

    Examples:
        >>> kinematic_acceleration_from_velocities(10, 16, 3)
        2.0
        >>> kinematic_acceleration_from_velocities((10, 5, 0), (16, 8, 0), 3)
        (2.0, 1.0, 0.0)
    """
    if time <= 0:
        raise ValueError(f"Time must be positive, got {time}")

    if isinstance(initial_velocity, (tuple, list)):
        # Vector case
        return tuple((vf - v0) / time for v0, vf in zip(initial_velocity, final_velocity))
    else:
        # Scalar case
        return (final_velocity - initial_velocity) / time


def kinematic_acceleration_from_displacement(initial_velocity, displacement, time):
    """Calculate acceleration from displacement: solve s = v₀t + ½at² for a.

    Computes acceleration needed to achieve given displacement in specified time.

    Args:
        initial_velocity (float): Initial velocity v₀
        displacement (float): Target displacement s
        time (float): Time interval t in seconds (must be non-zero)

    Returns:
        float: Required acceleration

    Raises:
        ValueError: If time is zero or negative

    Examples:
        >>> kinematic_acceleration_from_displacement(10, 39, 3)
        2.0
        >>> kinematic_acceleration_from_displacement(0, 45, 3)  # From rest
        10.0
    """
    if time <= 0:
        raise ValueError(f"Time must be positive, got {time}")

    # Rearrange s = v₀t + ½at² to solve for a:
    # a = 2(s - v₀t) / t²
    return 2 * (displacement - initial_velocity * time) / (time**2)


def kinematic_time_from_velocities_and_displacement(initial_velocity, final_velocity, displacement):
    """Calculate time using displacement and velocities: t = 2s/(v₀ + v).

    Uses the average velocity method to find time when displacement and both velocities are known.
    This is derived from s = (v₀ + v)t/2.

    Args:
        initial_velocity (float): Initial velocity v₀
        final_velocity (float): Final velocity v
        displacement (float): Displacement s

    Returns:
        float: Time required in seconds

    Raises:
        ValueError: If average velocity is zero

    Examples:
        >>> kinematic_time_from_velocities_and_displacement(10, 16, 39)
        3.0
        >>> kinematic_time_from_velocities_and_displacement(0, 20, 50)  # From rest
        5.0
    """
    average_velocity = (initial_velocity + final_velocity) / 2.0

    if abs(average_velocity) < 1e-12:
        raise ValueError("Average velocity cannot be zero for time calculation")

    return displacement / average_velocity


def kinematic_acceleration_from_velocities_and_displacement(initial_velocity, final_velocity, displacement):
    """Calculate acceleration using velocities and displacement: a = (v² - v₀²)/(2s).

    Uses the kinematic equation v² = v₀² + 2as, rearranged to solve for acceleration.
    Useful when time is unknown but displacement and both velocities are known.

    Args:
        initial_velocity (float): Initial velocity v₀
        final_velocity (float): Final velocity v
        displacement (float): Displacement s (must be non-zero)

    Returns:
        float: Required acceleration

    Raises:
        ValueError: If displacement is zero

    Examples:
        >>> kinematic_acceleration_from_velocities_and_displacement(10, 16, 39)
        2.0
        >>> kinematic_acceleration_from_velocities_and_displacement(20, 0, -40)  # Braking
        -5.0
    """
    if abs(displacement) < 1e-12:
        raise ValueError("Displacement cannot be zero for acceleration calculation")

    return (final_velocity**2 - initial_velocity**2) / (2.0 * displacement)