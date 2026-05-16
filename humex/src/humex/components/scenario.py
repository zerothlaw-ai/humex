import numpy as np
from collections import Counter
from .frame import Frame
from humex.utils.timestamp import to_ns


class Scenario(object):
    def __init__(self, duration=10.0, frequency=10.0, map_obj=None, ego_id=None, role_table=None):
        """
        duration is in seconds
        frequency is in hertz

        ``map_obj`` is normally an ``HMap`` facade constructed by the
        loader from (legacy RoadMap, LaneMap v2). Tests and direct-construction
        paths may pass a raw ``RoadMap`` — lane queries fall back to the legacy
        KDTree implementation in that case. Production code (Hume scenarios)
        always carries an HMap.
        """
        self.duration, self.frequency = duration, frequency
        self.interval = 1.0 / frequency
        self.frames, self.timestamps = self._init_frames(int(duration * frequency))
        self.roster = dict()
        self.map = map_obj
        self.ego_id = ego_id
        # Optional sidecar — set by the loader when role.pb is present next
        # to scenario.pb. Monitors that have migrated short-circuit to this
        # precomputed table; the slow path remains as fallback.
        self.role_table = role_table

    def add_obj_to_roster(self, obj):
        obj_id = self._generate_object_id() if obj.id is None else obj.id
        if obj_id in self.roster:
            raise ValueError(f'{obj_id} already in scenario roster')
        new_obj = obj.copy()

        self.roster[obj_id] = new_obj

    def get_obj_copy_from_roster(self, obj_id):
        if obj_id not in self.roster:
            raise ValueError(f'{obj_id} not in roster')
        return self.roster[obj_id].copy()

    def add_obj_to_frame(self, obj, frame):
        """
        Add obj with corresponding statepoint into the synced frames
        Statepoint can be assignd or skipped depends on the situations
        """
        # obj = self._get_obj_copy(obj_id)
        # statepoint.id = obj_id
        # obj.sp = statepoint

        ts = frame.timestamp

        # If ts is an exact match, assign this statepoint directly
        if ts in self.frames:
            self.frames[ts].add_obj(obj)
            return

        # If ts is not an exact match, find the closest ts and corresponding frame
        # If same object already has a statepoint in that frame, then skip
        # Otherwise assign the statepoint
        closest_ts = self._find_closest_ts(ts, self.timestamps)
        closest_frame = self.frames[closest_ts]
        if obj.id in closest_frame.obj_list:
            return
        closest_frame.add_obj(obj)  # TODO Instead of direct assignment, should interpolate

    def get_all_frames(self):
        return self.frames

    def get_frame_by_index(self, index=0):
        ts = self.timestamps[index]
        return self.frames[ts]

    def get_frame_by_ts(self, ts=0):
        final_ts = ts if ts in self.frames else self._find_closest_ts(ts, self.timestamps)
        return self.frames[final_ts]

    def assign_ego_id(self):
        """
        If ego is not assigned, will find the obj who appears in most frames
        """
        all_agents = [agent_id for frame_id, frame in self.frames.items() for agent_id in frame.obj_list]
        if not all_agents:
            return None
        counter = Counter(all_agents)

        # Most common ID and count
        most_common_id, count = counter.most_common(1)[0]
        self.ego_id = most_common_id
        return most_common_id

    def print(self):
        for frame_id, frame in self.frames.items():
            frame.print()

    def _generate_object_id(self):
        ids = sorted(list(self.roster.keys()))
        if len(ids) == 0:
            return 0
        return max(ids) + 1

    def _init_frames(self, frame_nums):
        """
        Based on numbers of frames, create frame object and store in a dictionary
        Keys are ts, vals are frame objects
        """
        frames = dict()
        synced_timestamps = self._get_synced_timestamps(frame_nums)
        for ts in synced_timestamps:
            frames[ts] = Frame(ts)
        return frames, synced_timestamps

    def _get_synced_timestamps(self, frame_nums):
        """
        Helper function to prepare the synced timestamp list in int64 nanoseconds
        """
        return [to_ns(ts * self.interval) for ts in range(frame_nums)]

    def _find_closest_ts(self, ts, ts_list):
        array = np.asarray(ts_list)
        idx = (np.abs(array - ts)).argmin()
        return array[idx]





