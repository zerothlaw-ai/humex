"""Frame module for autonomous vehicle simulation.

This module defines the Frame class which represents a snapshot in time
during a simulation, containing all objects and their states at a specific timestamp.
"""

from .statepoint import StatePoint


class Frame(object):
    """Represents a single frame (time snapshot) in an autonomous vehicle simulation.
    
    A frame contains all objects present at a specific timestamp, along with
    perception information about how objects relate to each other spatially.
    """
    def __init__(self, timestamp=None):
        """Initialize a new frame with optional timestamp.

        Args:
            timestamp (int, optional): Time value for this frame in nanoseconds (int64)
        """
        self.timestamp = timestamp
        self.obj_list = dict()  # Dictionary mapping object IDs to object instances
        self.perception = None  # Perception data for spatial relationships between objects

    def get_obj_list(self):
        """Get dictionary of all objects in this frame.
        
        Returns:
            dict: Dictionary mapping object IDs to object instances
        """
        return self.obj_list

    def get_ego(self, scenario=None):
        """Get the ego vehicle from this frame.
        
        Args:
            scenario (optional): Scenario object to get ego_id from
        
        Returns:
            Object or None: The ego vehicle object if present, None otherwise
        """
        # Try to get ego_id from scenario parameter first
        ego_id = None
        if scenario is not None and hasattr(scenario, 'ego_id'):
            ego_id = scenario.ego_id
        
        # If no scenario provided or ego_id not found, search for ego in objects
        if ego_id is None:
            for obj_id, obj in self.obj_list.items():
                if hasattr(obj, 'is_ego') and obj.is_ego:
                    ego_id = obj_id
                    break
        
        # Fallback to hardcoded ID 0 if nothing else works
        if ego_id is None:
            ego_id = 0
            
        return self.obj_list[ego_id] if ego_id in self.obj_list else None

    def get_obj(self, obj_id):
        """Get a specific object by ID from this frame.
        
        Args:
            obj_id: Unique identifier for the object
            
        Returns:
            Object or None: The requested object if found, None otherwise
        """
        if obj_id not in self.obj_list:
            return None
        return self.obj_list[obj_id]

    def add_obj(self, obj):
        """Add an object to this frame.
        
        Args:
            obj: Object instance to add to the frame
            
        Note:
            Currently silently returns if object ID already exists.
            TODO: Properly handle duplicate object IDs instead of silent return
        """
        if obj.id in self.obj_list:
            return  # TODO: Handle this error properly instead of silent return
            # raise ValueError(f'Object {obj.id} already existed in frame {self.timestamp}')
        self.obj_list[obj.id] = obj
        obj.update_frame(self)  # Update object's reference to this frame

    def print(self):
        """Print all objects in this frame with their positions.
        
        Outputs object ID and x,y coordinates for each object in the frame.
        """
        for obj_id, obj in self.obj_list.items():
            print(obj_id, obj.sp.position.x, obj.sp.position.y)

    def to_dict(self):
        """Convert frame to dictionary representation.
        
        Returns:
            dict: Dictionary with object IDs as keys and object dictionaries as values
        """
        return {obj_id: obj.to_dict() for obj_id, obj in self.obj_list.items()}


    def update_perception(self, perception):
        """Update the perception data for this frame.
        
        Args:
            perception: Perception object containing spatial relationships between objects
        """
        self.perception = perception


    @staticmethod
    def frame_interpolate(frame_1, frame_2, ratio, extrapolate=False):
        """Create an interpolated frame between two existing frames.
        
        This method interpolates position (x, y), yaw angle, and speed for objects
        that exist in both frames. Used for temporal smoothing or prediction.
        
        Args:
            frame_1 (Frame): First frame for interpolation
            frame_2 (Frame): Second frame for interpolation
            ratio (float): Interpolation ratio (0.0 = frame_1, 1.0 = frame_2)
            extrapolate (bool): If True, apply results to frame_2 instead of frame_1
            
        Returns:
            Frame: New frame with interpolated object states
            
        Note:
            Only interpolates objects that exist in both input frames
        """
        assert isinstance(frame_1, Frame)
        assert isinstance(frame_2, Frame)

        result_frame = Frame()
        for obj_id in frame_1.get_object_list().keys():
            sp_1 = frame_1.get_object_statepoint(obj_id)
            sp_2 = frame_2.get_object_statepoint(obj_id)
            sp_base = sp_1 if not extrapolate else sp_2

            if sp_1 is not None and sp_2 is not None:
                x = (sp_2.position.x - sp_1.position.x) * ratio + sp_base.position.x
                y = (sp_2.position.y - sp_1.position.y) * ratio + sp_base.position.y
                yaw = (sp_2.heading.yaw - sp_1.heading.yaw) * ratio + sp_base.heading.yaw
                speed = (sp_2.velocity.norm() - sp_1.velocity.norm()) * ratio + sp_base.velocity.norm()
                sp_result = StatePoint(position=(x, y, 0.0), velocity=(speed, 0.0, 0.0), heading=(0.0, 0.0, yaw))
                result_frame.add_statepoint(obj_id, sp_result)
        return result_frame

