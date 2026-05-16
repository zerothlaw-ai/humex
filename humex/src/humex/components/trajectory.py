#! /usr/bin/env python
import math
from copy import deepcopy

import numpy as np
from .statepoint import StatePoint
from ..utils.math_helper import linear_interpolate, get_2d_heading, is_behind


class Trajectory(object):
    def __init__(self):
        self.statepoints = list()
        self.keypoint_index = None

    def search_keypoint(self):
        num = 0
        for point in self.statepoints:
            if point.is_keypoint:
                num += 1
        return num

    ###########################################
    ##########       statepoint        ##########
    ###########################################

    def add_statepoint(self, statepoint):
        assert isinstance(statepoint, StatePoint)
        self.statepoints.append(statepoint)

    def insert_statepoint(self, index, statepoint):
        assert isinstance(statepoint, StatePoint)
        self.statepoints.insert(index, statepoint)

    def get_statepoint(self, *args, **kwargs):
        if len(args) > 1 or len(kwargs) > 1:
            raise TypeError("get_statepoint input arguments invalid!")
        if len(args) == 1 and len(kwargs) != 0 or len(kwargs) == 1 and len(args) != 0:
            raise TypeError("get_statepoint input arguments invalid!")

        if len(args) == 1:
            idx = args[0]
            return self._get_statepoint_by_idx(idx)

        if len(kwargs) == 1:
            if 'idx' in kwargs.keys():
                idx = kwargs['idx']
                return self._get_statepoint_by_idx(idx)
            elif 'timestamp' in kwargs.keys():
                timestamp = kwargs['timestamp']
                return self._get_statepoint_by_timestamp(timestamp)

        # print 'statepoint not found, returning None'
        return None

    def _get_statepoint_by_idx(self, idx):
        if 0 <= idx < len(self.statepoints):
            return self.statepoints[idx]
        elif idx < 0 and abs(idx) <= len(self.statepoints):
            return self.statepoints[idx]
        else:
            # print 'statepoint index not valid, returning None'
            return None

    def _get_statepoint_by_timestamp(self, timestamp):
        for point in self.statepoints:
            if point.timestamp >= timestamp:
                return point
        return None

    def get_statepoint_list(self):
        return self.statepoints

    def pop_statepoint(self, idx):
        return self.statepoints.pop(idx)

    def clear_statepoints(self):
        self.statepoints = list()

    ###########################################
    ############# Get Information #############
    ###########################################

    def size(self):
        return len(self.statepoints)

    def get_keypoint_index(self):
        if self.keypoint_index is not None:
            return self.keypoint_index

    def length(self):
        return self.segment_length(0, len(self.statepoints) - 1)

    def segment_length(self, start_idx, end_idx):
        dist = 0.0
        for i in range(start_idx, end_idx):
            dist += Trajectory.get_dist(self.statepoints[start_idx], self.statepoints[start_idx + 1])
        return dist

    ###########################################
    ############# Return Modified #############
    ###########################################

    @staticmethod
    def get_segment_traj(target_traj, start_idx, end_idx):
        res_traj = deepcopy(target_traj)
        res_traj.statepoints = res_traj.statepoints[start_idx:end_idx + 1]
        return res_traj

    @staticmethod
    def resample_traj(trajectory, frequency, duration):
        result_traj = Trajectory()

        frame_num = int(math.floor(frequency * duration))
        timestamp_list = list(np.linspace(0.0, duration, frame_num))
        last_timestamp = trajectory.get_statepoint(-1).timestamp
        for i in range(0, len(timestamp_list)):
            if timestamp_list[i] >= last_timestamp:
                del timestamp_list[i:]
                break
        lo = 0
        hi = 1
        for i in range(0, len(timestamp_list)):
            while trajectory.get_statepoint(hi).timestamp < timestamp_list[i]:
                lo += 1
                hi += 1
            lo_point = trajectory.get_statepoint(lo)
            hi_point = trajectory.get_statepoint(hi)
            mid_timestamp = timestamp_list[i]
            position_x = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                       b0=lo_point.position.x, b1=hi_point.position.x)
            position_y = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                       b0=lo_point.position.y, b1=hi_point.position.y)
            heading_yaw = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                        b0=lo_point.heading.yaw, b1=hi_point.heading.yaw)
            velocity_x = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                       b0=lo_point.velocity.x, b1=hi_point.velocity.x)
            velocity_y = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                       b0=lo_point.velocity.y, b1=hi_point.velocity.y)
            velocity_z = linear_interpolate(a0=lo_point.timestamp, a1=hi_point.timestamp, a=mid_timestamp,
                                                       b0=lo_point.velocity.z, b1=hi_point.velocity.z)
            waypoint = StatePoint(position=(position_x, position_y, 0.0), heading=(0.0, 0.0, heading_yaw),
                                  velocity=(velocity_x, velocity_y, velocity_z), timestamp=mid_timestamp)
            result_traj.add_statepoint(waypoint)
        return result_traj

    @staticmethod
    def get_invisible_traj():
        res = Trajectory()
        p = StatePoint(position=(0.0, 0.0, 0.0), velocity=(0.0, 0.0, 0.0), heading=(0.0, 0.0, 0.0))
        res.add_statepoint(p)
        return res

    @staticmethod
    def is_invisible_traj(traj):
        assert isinstance(traj, Trajectory)
        if traj.size() == 1:
            sp = traj.get_statepoint(0)
            if sp.position.x == 0.0 and sp.position.y == 0.0 and sp.position.z == 0.0:
                return True
        else:
            return False

    @staticmethod
    def assign_key_points(key_traj, resampled_traj):
        """  After the traj is resampled, it lost its keypoints information.
            This function uses a simple algorithm to assign key points based on input key_traj.
        """
        assert isinstance(key_traj, Trajectory)
        assert isinstance(resampled_traj, Trajectory)

        new_point_list = resampled_traj.get_statepoint_list()
        for key_point in key_traj.get_statepoint_list():
            new_key_point = min(new_point_list, key=lambda p: Trajectory.get_dist(p, key_point))
            new_key_point.is_keypoint = True
        return resampled_traj

    ###########################################
    #############      Debug      #############
    ###########################################

    def show(self):
        for point in self.statepoints:
            point.show()

    def plot(self, content=None):
        """Plot the trajectory. Requires matplotlib to be installed."""
        # Lazy import matplotlib only when plot() is called
        import matplotlib.pyplot as plt

        plt.figure()

        for i in range(len(self.statepoints)):
            point = self.statepoints[i]
            if content is None or content == 'position':
                plt.plot(point.position.x, point.position.y, '.r')
            elif content == 'heading':
                plt.plot(i, point.heading.yaw, '.r')
        plt.show()

    ###########################################
    #############     Utility     #############
    ###########################################


    @staticmethod
    def get_dist(point1, point2):
        assert isinstance(point1, StatePoint)
        assert isinstance(point2, StatePoint)
        x1, y1 = point1.position.x, point1.position.y
        x2, y2 = point2.position.x, point2.position.y
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    @staticmethod
    def generate_test_traj():
        key_p = [
            (70191.66752269458, -74380.53825148118, 2.5106702787929063),
            (70146.87887807352, -74352.32770483491, 2.509812207605343),
            (70111.93540930077, -74326.93730379245, 2.5106469363564625),
            (70071.70450885619, -74292.15704162222, 2.5106588804353165)

        ]
        key_v = [29, 0, 30, 29]
        test_traj = Trajectory()
        for i in range(len(key_p)):
            test_traj.add_statepoint(StatePoint.from_dubins_point(key_p[i]))
            test_traj.statepoints[-1].rewrite_velocity((key_v[i], 0.0, 0.0))

        return test_traj

    @staticmethod
    def get_vector_heading(point1, point2):
        p1_x = point1.position.x
        p1_y = point1.position.y
        p2_x = point2.position.x
        p2_y = point2.position.y

        return get_2d_heading(p1_x, p1_y, p2_x, p2_y)

    @staticmethod
    def is_focus_behind_target(focus_point, target_point):
        self_x = focus_point.position.x
        self_y = focus_point.position.y
        self_heading = focus_point.heading.yaw
        target_x = target_point.position.x
        target_y = target_point.position.y

        return is_behind(self_x, self_y, self_heading, target_x, target_y)


    @staticmethod
    def get_lat_lng_dist(focus_point, target_point):
        assert isinstance(focus_point, StatePoint) and isinstance(target_point, StatePoint)
        focus_heading = focus_point.heading.yaw
        delta_angle = Trajectory.get_vector_heading(focus_point, target_point)
        dist = Trajectory.get_dist(focus_point, target_point)
        lat_dist = abs(math.sin(focus_heading - delta_angle) * dist)
        lng_dist = abs(math.cos(focus_heading - delta_angle) * dist)
        return lat_dist, lng_dist


if __name__=='__main__':
    angle = -1.15 * 180.0 / math.pi
    result = Trajectory.get_min_equal_heading(angle * math.pi / 180.0)
    print(result * 180.0 / math.pi)