"""Per-frame check of the traffic signal controlling ego's current lane.

Resolves ego's current lane to the source lane id the signal pipeline is
keyed by, looks up the signal state for that lane at the current frame's
timestamp, and reports whether it is one of the user-selected states.
"""

import math

from humex.metrics.monitors.monitor_base import MonitorBase, OutputType
from humex.proto import signal_pb2


# Readable state name -> proto enum member. The proto (signal.proto /
# signal_pb2) is the single source of truth for the integer values, so a
# change there propagates here automatically — no hardcoded ints.
_State = signal_pb2.SignalState.State
_STATE_NAME_TO_ENUM = {
    "red": _State.LANE_STATE_STOP,
    "yellow": _State.LANE_STATE_CAUTION,
    "green": _State.LANE_STATE_GO,
    "arrow_red": _State.LANE_STATE_ARROW_STOP,
    "arrow_yellow": _State.LANE_STATE_ARROW_CAUTION,
    "arrow_green": _State.LANE_STATE_ARROW_GO,
    "flashing_red": _State.LANE_STATE_FLASHING_STOP,
    "flashing_yellow": _State.LANE_STATE_FLASHING_CAUTION,
    "unknown": _State.LANE_STATE_UNKNOWN,
}


class SignalStateIs(MonitorBase):
    """True when the signal controlling ego's current lane this frame is one of the selected states; per-frame and stateless.

    OUTPUT_TYPE: BOOL

    Params (from DAG YAML):
        states (list): Signal states to match (multi-select). Empty = nothing
            selected. Allowed values: "red", "yellow", "green", "arrow_red",
            "arrow_yellow", "arrow_green", "flashing_red", "flashing_yellow",
            "unknown". Mapped to the signal.proto SignalState.State enum.

    Returns (per frame):
        None in TWO cases — both meaning "not evaluated this frame":
            1. Ego is absent from the frame.
            2. ``states`` is empty (the user selected nothing to match).
        False — ego is present and at least one state is selected, but the
            signal does NOT match: ego is off-map (no lane found), the map
            carries no signal data, or the lane has no signal entry at this
            timestamp. These are evaluated-but-no-match cases, kept distinct
            from the None "not evaluated" cases above.
        True — the current signal state for ego's lane is in ``states``.
    """

    OUTPUT_TYPE = OutputType.BOOL
    PARAMS = [
        {"name": "states", "type": "string[]", "default": [],
         "description": "Signal states to match. Empty = nothing selected (returns None)",
         "allowed_values": ["red", "yellow", "green", "arrow_red", "arrow_yellow",
                            "arrow_green", "flashing_red", "flashing_yellow", "unknown"],
         "multi_select": True},
    ]

    def __init__(self, scenario, params=None):
        super().__init__(scenario, params=params)
        # Normalize states: accept a list (canonical) or a single string
        # (backward-compat), mirroring object_within_ego_buffer.object_type.
        raw = self.params.get("states", [])
        if isinstance(raw, str):
            names = {raw} if raw else set()
        elif isinstance(raw, list):
            names = {str(s) for s in raw if s}
        else:
            names = set()
        # Resolve names -> enum int values once. Unknown names are ignored
        # defensively (allowed_values is enforced upstream by the UI/DAG).
        self.target_values = {
            _STATE_NAME_TO_ENUM[n] for n in names if n in _STATE_NAME_TO_ENUM
        }

    def calculate(self):
        """Whether ego's lane signal this frame is one of the selected states.

        Returns:
            bool: True if the signal state matches one of ``states``; False if
                evaluated but no match (off-map / no signal data / no entry).
            None: if ego is absent, or if ``states`` is empty.
        """
        frame = self.curr_frame
        ego = frame.get_ego(self.scenario)
        if ego is None:
            return None

        # Empty selection -> nothing to evaluate against.
        if not self.target_values:
            return None

        # Ego position + heading. Headings may be stored in degrees or radians;
        # apply the same >10 heuristic used by _front_vehicle_utils.
        ego_position = ego.sp.position.to_tuple()
        ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
        if ego_heading is not None and abs(ego_heading) > 10.0:
            ego_heading = math.radians(ego_heading)

        # Ego's current lane. Under HMap/LaneMap v2 this is a SEGMENT id; under
        # a raw RoadMap it is already a SOURCE lane id.
        lane_id = self.scenario.map.find_closest_lane(ego_position, heading=ego_heading)
        if lane_id is None:
            return False

        # Resolve SEGMENT id -> SOURCE lane id, the id space signals are keyed
        # by (preserved from the dataset by the converter). source_lane_id is
        # 0/unset on v1 lanes and synthesized connectors — in that case the
        # segment id already IS the source id. When no lane_map sidecar is
        # loaded (self.lane_map is None), find_closest_lane returned a source
        # id directly and no resolution is needed.
        source_lane_id = lane_id
        lane_map = self.lane_map
        if lane_map is not None:
            lane = lane_map.get_lane(lane_id)
            src = getattr(lane, "source_lane_id", 0) if lane is not None else 0
            if src:
                source_lane_id = src

        # Signals are owned by the legacy RoadMap; reach it via HMap.legacy_map,
        # falling back to scenario.map when it is already a RoadMap.
        legacy = getattr(self.scenario.map, "legacy_map", None) or self.scenario.map

        # get_signal_state returns None for no-signals / no-entry / no-timestamp;
        # all collapse to "evaluated, no match" -> False.
        state = legacy.get_signal_state(source_lane_id, frame.timestamp)
        if state is None:
            return False

        return state in self.target_values
