"""Monitor for detecting objects within an enlarged bounding box around the ego vehicle.

Like ego_collision but with a configurable buffer zone and optional object type filtering.
"""

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.utils.math_helper import dist2d, transform2D, polygons_collide


class ObjectWithinEgoBuffer(MonitorBase):
    """Detect any object entering a buffered bounding box around the ego vehicle.

    OUTPUT_TYPE: BOOL

    Params (from DAG YAML):
        buffer_lon (float): Longitudinal buffer in meters extending front and rear. Default 0.0.
        buffer_lat (float): Lateral buffer in meters extending left and right. Default 0.0.
        object_type (list): Filter by object type(s). Empty list means all objects. Default [].
    """
    OUTPUT_TYPE = OutputType.BOOL
    PARAMS = [
        {"name": "buffer_lon", "type": "float", "default": 0.0,
         "description": "Longitudinal buffer in meters extending front and rear"},
        {"name": "buffer_lat", "type": "float", "default": 0.0,
         "description": "Lateral buffer in meters extending left and right"},
        {"name": "object_type", "type": "string[]", "default": [],
         "description": "Filter by object type(s). Empty = all objects",
         "allowed_values": ["car", "pedestrian", "cyclist", "truck"],
         "multi_select": True},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        self.buffer_lon = float(self.params.get("buffer_lon", 0.0))
        self.buffer_lat = float(self.params.get("buffer_lat", 0.0))
        # Normalize object_type: accept string (backward compat) or list
        raw = self.params.get("object_type", [])
        if isinstance(raw, str):
            self.object_types = {raw} if raw else set()
        elif isinstance(raw, list):
            self.object_types = {str(t) for t in raw if t}
        else:
            self.object_types = set()

    def calculate(self):
        """Check if any object is within the ego vehicle's buffered bounding box.

        Returns:
            bool: True if any (matching) object is inside the buffer zone, False otherwise.
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)

        if ego is None:
            return None

        ego_x, ego_y = ego.sp.position.x, ego.sp.position.y
        ego_yaw = ego.sp.heading.yaw

        # Build enlarged polygon around ego using buffer
        half_length = ego.length / 2 + self.buffer_lon
        half_width = ego.width / 2 + self.buffer_lat

        # Compute 4 corners of the enlarged bounding box in global frame
        # Local frame: front-left, front-right, rear-right, rear-left
        fl = transform2D(half_length, half_width, ego_x, ego_y, ego_yaw)
        fr = transform2D(half_length, -half_width, ego_x, ego_y, ego_yaw)
        rr = transform2D(-half_length, -half_width, ego_x, ego_y, ego_yaw)
        rl = transform2D(-half_length, half_width, ego_x, ego_y, ego_yaw)

        ego_polygon = [fl, fr, rr, rl]

        # Distance pre-filter threshold: diagonal of enlarged box + generous margin
        max_ego_dim = max(half_length, half_width) * 2
        dist_threshold = max_ego_dim + 50.0

        ego_pt = (ego_x, ego_y)

        for obj_id, obj in frame.obj_list.items():
            # Skip ego vehicle
            if obj_id == self.scenario.ego_id:
                continue

            # Filter by object type(s) if specified
            if self.object_types and getattr(obj, "object_type", "") not in self.object_types:
                continue

            # Stage 1: Distance pre-filter
            obj_pt = obj.sp.position.to_tuple()
            if dist2d(ego_pt, obj_pt) > dist_threshold:
                continue

            # Stage 2: Polygon intersection check
            obj_fl, obj_fr, obj_rl, obj_rr = (
                obj.bbox.front_left.to_tuple(),
                obj.bbox.front_right.to_tuple(),
                obj.bbox.rear_left.to_tuple(),
                obj.bbox.rear_right.to_tuple(),
            )
            obj_polygon = [obj_fl, obj_fr, obj_rr, obj_rl]

            if polygons_collide(ego_polygon, obj_polygon):
                return True

        return False
