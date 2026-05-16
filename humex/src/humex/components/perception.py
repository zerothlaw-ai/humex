from ..utils.math_helper import is_behind, dist2d
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class Relations:
    front: int = None
    front_dist: float = None
    rear: int = None
    left: int = None
    right: int = None


class Perception(object):
    def __init__(self, frame, map_handle):
        self.frame = frame
        self.map = map_handle
        self.neighbors = defaultdict(Relations)

        self._update_neighbors()

    def get_front(self, obj_id):
        if obj_id not in self.neighbors:
            return None
        return self.neighbors[obj_id].front

    def _update_neighbors(self):
        for base_id, base_obj in self.frame.get_obj_list().items():
            for target_id, target_obj in self.frame.get_obj_list().items():
                if base_id == target_id:
                    continue
                self.__update_relation(base_obj, target_obj)

    def __update_relation(self, base_obj=None, target_obj=None):

        # If Front
        relation = is_behind(base_obj.sp.position.x, base_obj.sp.position.y,
                             base_obj.sp.heading.yaw,
                             target_obj.sp.position.x, target_obj.sp.position.y)
        if relation:
            front_dist = dist2d(base_obj.sp.position.to_tuple(), target_obj.sp.position.to_tuple())
            if self.neighbors[base_obj.id].front is None or \
               front_dist < self.neighbors[base_obj.id].front_dist:
                self.neighbors[base_obj.id].front = target_obj.id
                self.neighbors[base_obj.id].front_dist = front_dist

            if base_obj.is_ego:
                target_obj.status = 'front'
