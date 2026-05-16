"""Mathematical utility functions for autonomous vehicle simulation.

This module provides common mathematical operations including coordinate transformations,
geometric calculations, polygon operations, and angular arithmetic used throughout
the humex framework.
"""

import math
from shapely.geometry import Polygon
import numpy as np


# ========= Unit Conversion Functions =========
def mph_to_ms(mph):
    """Convert speed from miles per hour to meters per second.
    
    Args:
        mph (float): Speed in miles per hour
        
    Returns:
        float: Speed in meters per second
    """
    return mph * 0.44704

def ms_to_mph(ms):
    """Convert speed from meters per second to miles per hour.
    
    Args:
        ms (float): Speed in meters per second
        
    Returns:
        float: Speed in miles per hour
    """
    return ms / 0.44704


# ========= Angle Conversion Functions =========
def deg2rad(angle):
    """Convert angle from degrees to radians.
    
    Args:
        angle (float): Angle in degrees
        
    Returns:
        float: Angle in radians
    """
    return angle * math.pi / 180.0


def rad2deg(radian):
    """Convert angle from radians to degrees.
    
    Args:
        radian (float): Angle in radians
        
    Returns:
        float: Angle in degrees
    """
    return radian * 180.0 / math.pi


# ========= Interpolation and Distance Functions =========
def linear_interpolate(a0, a1, a, b0, b1):
    """Perform linear interpolation between two points.
    
    Given points (a0,b0) and (a1,b1), finds the b value corresponding to a.
    
    Args:
        a0, a1 (float): X-coordinates of known points
        a (float): X-coordinate to interpolate at
        b0, b1 (float): Y-coordinates of known points
        
    Returns:
        float: Interpolated y-value at x=a
    """
    return (a - a0) / (a1 - a0) * (b1 - b0) + b0


def dist2d(p0, p1):
    """Calculate Euclidean distance between two 2D points.
    
    Args:
        p0, p1 (tuple): Points as (x, y) coordinates
        
    Returns:
        float: Distance between points
    """
    x0, y0 = p0[0], p0[1]
    x1, y1 = p1[0], p1[1]
    return math.sqrt((y1 - y0)**2 + (x1 - x0)**2)


def dist3d(p0, p1):
    """Calculate Euclidean distance between two 3D points.
    
    Args:
        p0, p1 (tuple): Points as (x, y, z) coordinates
        
    Returns:
        float: Distance between points
    """
    return np.linalg.norm(np.array(p0) - np.array(p1))

# ========= Angular Arithmetic Functions =========
def min_equal_heading(heading):
    """Normalize angle to be within (-π, π] range.
    
    Wraps angle to the standard range for consistent angular arithmetic.
    
    Args:
        heading (float): Input angle in radians
        
    Returns:
        float: Equivalent angle in range (-π, π]
    """
    # Reduce angle to (-π, π] range using modular arithmetic
    if heading > math.pi:
        heading -= (int((heading - math.pi) / 2 / math.pi) + 1) * 2 * math.pi
    elif heading < -1.0 * math.pi:
        heading += (int((-1.0 * math.pi - heading) / 2 / math.pi) + 1) * 2 * math.pi
    return heading


# ========= Coordinate Transformation Functions =========
def transform2D(px, py, tx, ty, rot):
    """Apply 2D rigid body transformation to a point.
    
    Performs rotation followed by translation to transform a point from
    local coordinates to global coordinates.
    
    Args:
        px, py (float): Point coordinates in local frame
        tx, ty (float): Translation offset
        rot (float): Rotation angle in radians (counterclockwise positive)
        
    Returns:
        tuple: Transformed point coordinates (x, y) in global frame
    """
    # Apply rotation matrix followed by translation
    x = math.cos(rot) * px - math.sin(rot) * py + tx
    y = math.sin(rot) * px + math.cos(rot) * py + ty
    return x, y


def get_2d_heading(tail_x, tail_y, head_x, head_y):
    """Calculate heading angle from tail point to head point.
    
    Args:
        tail_x, tail_y (float): Starting point coordinates
        head_x, head_y (float): Ending point coordinates
        
    Returns:
        float: Heading angle in radians (0 = east, π/2 = north)
    """
    x = head_x - tail_x
    y = head_y - tail_y
    return math.atan2(y, x)


def is_behind(self_x, self_y, self_heading, target_x, target_y):
    """Determine if target point is behind the vehicle.
    
    Args:
        self_x, self_y (float): Vehicle position
        self_heading (float): Vehicle heading angle in radians
        target_x, target_y (float): Target point coordinates
        
    Returns:
        bool: True if target is within 90 degrees of vehicle's forward direction
    """
    # Calculate angle from vehicle to target
    relative_heading = get_2d_heading(tail_x=self_x, tail_y=self_y, head_x=target_x, head_y=target_y)
    
    # Calculate angular difference between vehicle heading and target direction
    delta = abs(min_equal_heading(abs(self_heading - relative_heading)))
    
    # Target is "behind" if within 90 degrees of forward direction
    return delta <= math.pi/2.0


# ========= Polygon Geometry Functions =========
def polygons_collide(poly1, poly2):
    """Check if two polygons intersect using Shapely library.

    Used primarily for vehicle collision detection by testing bounding box overlap.
    Handles both intersection and touching cases as collisions.

    Args:
        poly1 (list of (x, y)): First polygon vertices in order
        poly2 (list of (x, y)): Second polygon vertices in order

    Returns:
        bool: True if polygons intersect or touch, False otherwise
    """
    polygon1 = Polygon(poly1)
    polygon2 = Polygon(poly2)
    return polygon1.intersects(polygon2)

def point_in_polygon(point, polygon):
    """Determine if a 2D point is inside a polygon using ray-casting algorithm.
    
    Implements the standard ray-casting (even-odd rule) algorithm for point-in-polygon
    testing. Casts a ray from the point eastward and counts intersections with polygon edges.

    Args:
        point (tuple): The point to test as (x, y)
        polygon (list): List of (x, y) tuples representing polygon vertices in order

    Returns:
        bool: True if point is inside polygon, False otherwise
    """
    x, y = point[0], point[1]
    n = len(polygon)
    inside = False

    # Test ray intersection with each polygon edge
    for i in range(n):
        j = (i + 1) % n  # Next vertex (wrapping to start)
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]

        # Check if horizontal ray crosses this edge
        if (yi > y) != (yj > y):  # Edge crosses the horizontal line through point
            # Calculate x-coordinate where edge intersects the horizontal ray
            x_intersect = (y - yi) * (xj - xi) / (yj - yi + 1e-12) + xi  # Small epsilon to avoid division by zero
            
            # If intersection is to the right of point, toggle inside status
            if x < x_intersect:
                inside = not inside

    return inside


# ========= Velocity Calculation Functions =========
def calculate_velocity_from_positions(pos1, pos2, time_delta):
    """Calculate 3D velocity vector from position change over time.
    
    Computes velocity by taking the difference between two 3D positions
    and dividing by the time interval between measurements.
    
    Args:
        pos1 (tuple): Previous position as (x, y, z)
        pos2 (tuple): Current position as (x, y, z) 
        time_delta (float): Time interval between positions in seconds
        
    Returns:
        tuple: Velocity vector as (vx, vy, vz) in meters per second
        
    Raises:
        ValueError: If time_delta is zero or negative
    """
    if time_delta <= 0:
        raise ValueError(f"Time delta must be positive, got {time_delta}")
    
    # Calculate displacement vector
    dx = pos2[0] - pos1[0]
    dy = pos2[1] - pos1[1] 
    dz = pos2[2] - pos1[2]
    
    # Divide by time to get velocity
    vx = dx / time_delta
    vy = dy / time_delta
    vz = dz / time_delta
    
    return (vx, vy, vz)


def calculate_velocity_from_heading_and_speed(heading_yaw, speed):
    """Calculate 2D velocity vector from heading direction and speed magnitude.
    
    Converts a heading angle and scalar speed into velocity components.
    Assumes motion in the XY plane (vz = 0).
    
    Args:
        heading_yaw (float): Heading angle in radians (0 = east, π/2 = north)
        speed (float): Speed magnitude in meters per second
        
    Returns:
        tuple: Velocity vector as (vx, vy, 0.0)
    """
    vx = speed * math.cos(heading_yaw)
    vy = speed * math.sin(heading_yaw)
    vz = 0.0
    
    return (vx, vy, vz)


def estimate_speed_from_heading_change(prev_heading, curr_heading, wheelbase, time_delta):
    """Estimate vehicle speed from heading change using bicycle model.
    
    Uses the kinematic bicycle model to estimate forward speed based on
    how much the vehicle's heading changed over a time interval.
    
    Args:
        prev_heading (float): Previous heading angle in radians
        curr_heading (float): Current heading angle in radians  
        wheelbase (float): Vehicle wheelbase length in meters (typical: 2.5-3.0m)
        time_delta (float): Time interval in seconds
        
    Returns:
        float: Estimated forward speed in meters per second
        
    Note:
        This is an approximation that assumes the vehicle follows bicycle kinematics.
        The estimate becomes less accurate for large heading changes or high speeds.
    """
    if time_delta <= 0:
        return 0.0
    
    # Calculate angular velocity (heading change rate)
    heading_delta = min_equal_heading(curr_heading - prev_heading)
    angular_velocity = abs(heading_delta) / time_delta
    
    # For bicycle model: v = ω * R where R is turning radius
    # For small angles: R ≈ wheelbase / tan(steering_angle) ≈ wheelbase / steering_angle
    # Angular velocity ω = v / R, so v = ω * R
    
    if angular_velocity < 1e-6:  # Nearly straight motion
        return 0.0  # Cannot estimate speed from heading alone
    
    # Rough estimate: assume moderate steering angle relationship
    # This is a heuristic - real relationship depends on steering geometry
    estimated_turning_radius = wheelbase / (2 * angular_velocity * time_delta)
    estimated_speed = angular_velocity * estimated_turning_radius
    
    return estimated_speed


# ========= Path Generation Functions =========
def generate_arc_points(prev_p, start_p, arc_length, radius, num_points, clockwise=False):
    """Generate a sequence of points along a circular arc.
    
    Creates smooth curved paths for vehicle trajectory planning. Uses the direction
    from prev_p to start_p to determine initial tangent direction, then generates
    points along a circular arc of specified curvature.

    Args:
        prev_p (tuple): Previous point before arc starts (x, y, z) - establishes initial direction
        start_p (tuple): Starting point of the arc (x, y, z)
        arc_length (float): Total length of arc to generate (meters)
        radius (float): Radius of curvature (meters, positive values)
        num_points (int): Number of intermediate points to generate
        clockwise (bool): Arc direction - False for left turns, True for right turns

    Returns:
        list of tuples: Sequence of (x, y, 0.0) points forming the arc path
    """

    # Extract coordinates from input points
    x0, y0, z0 = prev_p[0], prev_p[1], prev_p[2]
    x1, y1, z1 = start_p[0], start_p[1], prev_p[2]

    # Calculate initial tangent direction from previous point to start point
    start_angle = math.atan2(y1 - y0, x1 - x0)

    # Calculate angular parameters for arc generation
    circle_circum = 2 * math.pi * radius
    delta_arc_angle = 2 * math.pi * (arc_length / circle_circum) / num_points

    # Calculate angular step between generated points using chord geometry
    # This ensures smooth point distribution along the arc
    delta_point_angle = math.pi / 2.0 - (math.pi - delta_arc_angle) / 2.0

    # Adjust direction for clockwise arcs (right turns)
    if clockwise:
        delta_arc_angle *= -1

    # Initialize path with starting point and direction
    points = [start_p]
    angles = [start_angle]

    # Generate points iteratively along the arc
    for i in range(1, num_points * 2 + 1):
        prev_x, prev_y, prev_z = points[-1]
        prev_angle = angles[-1]

        # Update direction angle for next point
        new_angle = prev_angle + delta_point_angle

        # Calculate chord distance between consecutive points
        # This approximates the arc length for small angular increments
        point_dist = math.sin(delta_arc_angle / 2.0) * radius * 2

        # Generate new point coordinates using trigonometry
        new_x = prev_x + math.cos(new_angle) * point_dist
        new_y = prev_y + math.sin(new_angle) * point_dist
        new_z = 0.0  # Keep z-coordinate at ground level

        # Add new point and angle to sequences
        points.append((new_x, new_y, new_z))
        angles.append(new_angle)

    return points




