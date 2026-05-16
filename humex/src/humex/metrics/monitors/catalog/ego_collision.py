"""Ego vehicle collision detection monitor.

This module implements collision detection between the ego vehicle and other
vehicles using bounding box polygon intersection algorithms.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.math_helper import dist2d, polygons_collide


class EgoCollision(MonitorBase):
    """Monitor for detecting collisions involving the ego vehicle.

    OUTPUT_TYPE: BOOL
    
    Uses 2D bounding box polygon intersection to detect physical contact
    between the ego vehicle and other vehicles in the scenario.
    Optimized with distance pre-filtering for computational efficiency.
    """
    OUTPUT_TYPE = OutputType.BOOL

    def __init__(self, scenario):
        """Initialize ego collision monitor.
        
        Args:
            scenario: Simulation scenario containing vehicle and map data
        """
        super().__init__(scenario)

    def calculate(self):
        """Check for collisions between ego vehicle and other vehicles in current frame.

        Uses two-stage detection: distance pre-filtering for efficiency, followed by
        precise polygon intersection testing. Updates vehicle status for visualization.

        Returns:
            bool: True if collision detected, False otherwise
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        
        # Handle case where ego vehicle is not present in frame
        if ego is None:
            return None
            
        ego_pt = ego.sp.position.to_tuple()
        
        # Check collision with each other vehicle
        for obj_id, obj in frame.obj_list.items():
            # Skip ego vehicle itself
            if obj_id == self.scenario.ego_id:
                continue
                
            # Stage 1: Distance pre-filtering for computational efficiency
            obj_pt = obj.sp.position.to_tuple()
            dist = dist2d(ego_pt, obj_pt)
            if dist > 50.0:  # Skip detailed collision check if vehicles are far apart
                continue

            # Stage 2: Precise bounding box polygon intersection
            # Extract ego vehicle bounding box vertices
            ego_fl, ego_fr, ego_rl, ego_rr = (
                ego.bbox.front_left.to_tuple(), 
                ego.bbox.front_right.to_tuple(), 
                ego.bbox.rear_left.to_tuple(), 
                ego.bbox.rear_right.to_tuple()
            )
            
            # Extract other vehicle bounding box vertices
            obj_fl, obj_fr, obj_rl, obj_rr = (
                obj.bbox.front_left.to_tuple(), 
                obj.bbox.front_right.to_tuple(), 
                obj.bbox.rear_left.to_tuple(), 
                obj.bbox.rear_right.to_tuple()
            )

            # Create polygon representations (order matters for intersection algorithm)
            ego_polygon = [ego_fl, ego_fr, ego_rl, ego_rr]
            obj_polygon = [obj_fl, obj_fr, obj_rr, obj_rl]  # Note: different vertex order

            # Test for polygon intersection
            collision = polygons_collide(ego_polygon, obj_polygon)
            
            if collision:
                # Update vehicle status for visualization feedback
                ego.status = 'collision'
                obj.status = 'collision'
                return True
                
        # No collision detected with any vehicle
        return False


