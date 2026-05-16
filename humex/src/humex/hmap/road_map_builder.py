# from .map import Map, Lane
from .road_map import LaneData, RoadMap
# from ..utils.paths import MAP_DATA  # Legacy path removed - maps now in results/{scenario_name}/
import os
from ..utils.math_helper import *
import json

class LaneIDAssigner:
    def __init__(self, start: int = 0):
        self._counter = start

    def next(self) -> int:
        current = self._counter
        self._counter += 1
        return current

    def reset(self, value: int = 0):
        self._counter = value


class MapBuilder(object):
    def __init__(self, map_name=None):
        self.map = RoadMap(map_name=map_name)
        self.id_assigner = LaneIDAssigner()

    def _parse(self, config):
        #TODO build from config
        pass

    def extend_straight_lane(self, prev_lane=None, length=None, width=None, heading=None, target_interval=1):
        lane = LaneData(self.id_assigner.next())
        p_num = int(length // target_interval)
        actual_interval = length / p_num

        prev_lane_id = None
        if prev_lane is not None:
            start_point = prev_lane.center_points[-1]
            prev_point = prev_lane.center_points[-2]
            heading = math.atan2(start_point[1] - prev_point[1], start_point[0] - prev_point[0])
            prev_lane_id = prev_lane.id
        else:
            start_point = (0.0, 0.0, 0.0)
            if heading is None:
                heading = 0.0

        center_points = [start_point]
        left_points = [(start_point[0] - math.sin(heading) * width / 2, start_point[1] + math.cos(heading) * width / 2, 0.0)]
        right_points = [(start_point[0] + math.sin(heading) * width / 2, start_point[1] - math.cos(heading) * width / 2, 0.0)]
        for i in range(1, p_num):
            prev_x, prev_y = center_points[-1][0], center_points[-1][1]
            new_x, new_y = math.cos(heading) * actual_interval + prev_x, math.sin(heading) * actual_interval + prev_y

            center_points.append((new_x, new_y, 0.0))
            left_points.append((new_x - math.sin(heading) * width / 2, new_y + math.cos(heading) * width / 2, 0.0))
            right_points.append((new_x + math.sin(heading) * width / 2, new_y - math.cos(heading) * width / 2, 0.0))

        lane.center_points = center_points
        lane.left_points = left_points
        lane.right_points = right_points
        self.map.add_lane(lane, prev_lane_id=prev_lane_id)
        return lane

    def extend_curved_lane(self, prev_lane=None, length=10.0, width=None, target_interval=1, radius=None, cw=False):
        lane = LaneData(self.id_assigner.next())
        prev_lane_id = None
        if prev_lane is None:
            x0, y0, z0 = -1.0, 0.0, 0.0
            x1, y1, z1 = 0.0, 0.0, 0.0
        else:
            x0, y0, z0 = prev_lane.center_points[-2]
            x1, y1, z1 = prev_lane.center_points[-1]
            prev_lane_id = prev_lane.id
        p_num = int(length // target_interval)
        lane.center_points = generate_arc_points(prev_p=(x0, y0, z0), start_p=(x1, y1, z1),
                                                 arc_length=length, radius=radius,
                                                 num_points=p_num, clockwise=cw)
        heading = math.atan2(y1 - y0, x1 - x0)

        left_radius = radius - width/4 if not cw else radius + width/4
        left_length = length / radius * left_radius
        l_x0, l_y0, l_z0 = x0 - math.sin(heading) * width / 2, y0 + math.cos(heading) * width / 2, 0.0
        l_x1, l_y1, l_z1 = x1 - math.sin(heading) * width / 2, y1 + math.cos(heading) * width / 2, 0.0
        l_p_num = int(left_length // target_interval)
        lane.left_points = generate_arc_points(prev_p=(l_x0, l_y0, l_z0), start_p=(l_x1, l_y1, l_z1),
                                                 arc_length=left_length, radius=left_radius,
                                                 num_points=l_p_num, clockwise=cw)

        right_radius = radius + width / 4 if not cw else radius - width / 4
        right_length = length / radius * right_radius
        r_x0, r_y0, r_z0 = x0 + math.sin(heading) * width / 2, y0 - math.cos(heading) * width / 2, 0.0
        r_x1, r_y1, r_z1 = x1 + math.sin(heading) * width / 2, y1 - math.cos(heading) * width / 2, 0.0
        r_p_num = int(right_length // target_interval)
        lane.right_points = generate_arc_points(prev_p=(r_x0, r_y0, r_z0), start_p=(r_x1, r_y1, r_z1),
                                               arc_length=right_length, radius=right_radius,
                                               num_points=r_p_num, clockwise=cw)
        self.map.add_lane(lane, prev_lane_id=prev_lane_id)
        return lane

    def save_map_to_json(self):
        def tuple_list(obj):
            return [list(p) for p in obj]
        map_data = self.map.map_data

        serializable = {
            "lanes": {
                lane_id: {
                    "center_points": tuple_list(lane.center_points),
                    "left_points": tuple_list(lane.left_points),
                    "right_points": tuple_list(lane.right_points),
                    "is_left_solid": lane.is_left_solid,
                    "is_right_solid": lane.is_right_solid,
                    "width": lane.width,
                    "type": lane.type,
                    "is_intersection": lane.is_intersection,
                    "speed_limit_mps": lane.speed_limit_mps,
                    "left_neighbor": lane.left_neighbor,
                    "right_neighbor": lane.right_neighbor
                }
                for lane_id, lane in map_data.lanes.items()
            },
            "next_lanes": dict(map_data.next_lanes),
            "prev_lanes": dict(map_data.prev_lanes),
        }
        # NOTE: This function needs to be updated for new structure
        # Maps should now be saved in results/{scenario_name}/ava_map_{scenario_name}.json
        map_path = f'./legacy_maps/{self.map.name}.json'  # Temporary fallback
        os.makedirs('./legacy_maps', exist_ok=True)
        with open(map_path, "w") as f:
            json.dump(serializable, f, indent=2)


if __name__ == '__main__':
    x = MapBuilder('road_map_track1_sparse')
    interval = 1
    l0 = x.extend_straight_lane(length=200.0, width=4, heading=0.0, target_interval=interval)
    l1 = x.extend_curved_lane(prev_lane=l0, width=4, length=math.pi * 50.0, radius=50.0, target_interval=interval)
    l2 = x.extend_straight_lane(prev_lane=l1, width=4, length=200.0, target_interval=interval)
    l3 = x.extend_curved_lane(prev_lane=l2, width=4, length=math.pi * 50.0, radius=50.0, target_interval=interval)
    x.save_map_to_json()
    x.map.plot()
