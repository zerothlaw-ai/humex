"""Tests for the SignalStateIs monitor.

Covers the required cases:
  - signal red + "red" selected      -> True
  - signal green + "red" selected     -> False
  - ego absent                        -> None
  - empty states                      -> None
  - no signal data                    -> False

The fakes mirror the exact production HMap surface the monitor touches:
  - map.find_closest_lane(position, heading=) -> segment id
  - map.lane_map.get_lane(seg).source_lane_id -> source lane id
  - map.legacy_map.get_signal_state(source_id, ts) -> state int or None
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.components.frame import Frame
from humex.components.object import Object
from humex.components.statepoint import StatePoint
from humex.proto import signal_pb2
from humex.metrics.monitors.catalog.signal_state_is import SignalStateIs

_State = signal_pb2.SignalState.State


# ---------------------------------------------------------------------------
# Fakes mirroring the HMap / LaneMap / RoadMap surface
# ---------------------------------------------------------------------------

class _FakeLane:
    def __init__(self, source_lane_id):
        self.source_lane_id = source_lane_id


class _FakeLaneMap:
    """seg_id -> source_lane_id, like LaneMap.get_lane(seg).source_lane_id."""
    def __init__(self, seg_to_source):
        self._seg_to_source = seg_to_source

    def get_lane(self, lane_id):
        src = self._seg_to_source.get(lane_id)
        return _FakeLane(src) if src is not None else None


class _FakeRoadMap:
    """signals: {source_lane_id: state_int}, or None meaning 'no signal data'."""
    def __init__(self, signals):
        self._signals = signals

    def has_signals(self):
        return self._signals is not None

    def get_signal_state(self, lane_id, timestamp):
        if self._signals is None:
            return None
        return self._signals.get(lane_id)


class _FakeHMap:
    def __init__(self, closest_lane, lane_map, legacy):
        self._closest = closest_lane
        self.lane_map = lane_map
        self.legacy_map = legacy

    def find_closest_lane(self, position, heading=None):
        return self._closest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ego(obj_id=0):
    ego = Object(obj_id=obj_id, length=4.8, width=1.7, is_ego=True)
    ego.update_mutable(StatePoint(position=(10.0, 5.0, 0.0), heading=(0.0, 0.0, 0.5)))
    return ego


def _scenario_with_signal(state_int, *, seg_id=100, source_id=7):
    """HMap-backed scenario where ego's lane (segment seg_id -> source source_id)
    has signal state ``state_int``. Pass state_int=None-signals via signals=None.
    """
    lane_map = _FakeLaneMap({seg_id: source_id})
    legacy = _FakeRoadMap({source_id: state_int})
    hmap = _FakeHMap(closest_lane=seg_id, lane_map=lane_map, legacy=legacy)
    return SimpleNamespace(ego_id=0, map=hmap)


def _scenario_no_signals(*, seg_id=100, source_id=7):
    lane_map = _FakeLaneMap({seg_id: source_id})
    legacy = _FakeRoadMap(None)  # has_signals() == False
    hmap = _FakeHMap(closest_lane=seg_id, lane_map=lane_map, legacy=legacy)
    return SimpleNamespace(ego_id=0, map=hmap)


def _run(monitor, frame):
    monitor.curr_frame = frame
    return monitor.calculate()


def _frame_with_ego(timestamp=0):
    frame = Frame(timestamp=timestamp)
    frame.obj_list[0] = _make_ego(0)
    return frame


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_red_signal_red_selected_is_true():
    scenario = _scenario_with_signal(_State.LANE_STATE_STOP)
    monitor = SignalStateIs(scenario, params={"states": ["red"]})
    assert _run(monitor, _frame_with_ego()) is True


def test_green_signal_red_selected_is_false():
    scenario = _scenario_with_signal(_State.LANE_STATE_GO)
    monitor = SignalStateIs(scenario, params={"states": ["red"]})
    assert _run(monitor, _frame_with_ego()) is False


def test_ego_absent_is_none():
    scenario = _scenario_with_signal(_State.LANE_STATE_STOP)
    monitor = SignalStateIs(scenario, params={"states": ["red"]})
    empty_frame = Frame(timestamp=0)  # no objects -> get_ego() returns None
    assert _run(monitor, empty_frame) is None


def test_empty_states_is_none():
    scenario = _scenario_with_signal(_State.LANE_STATE_STOP)
    monitor = SignalStateIs(scenario, params={"states": []})
    # Ego present, but nothing selected -> not evaluated -> None
    assert _run(monitor, _frame_with_ego()) is None


def test_no_signal_data_is_false():
    scenario = _scenario_no_signals()
    monitor = SignalStateIs(scenario, params={"states": ["red"]})
    assert _run(monitor, _frame_with_ego()) is False


# ---------------------------------------------------------------------------
# Extra coverage: multi-select match + segment->source resolution
# ---------------------------------------------------------------------------

def test_multi_select_matches_any_selected_state():
    scenario = _scenario_with_signal(_State.LANE_STATE_FLASHING_STOP)
    monitor = SignalStateIs(scenario, params={"states": ["red", "flashing_red"]})
    assert _run(monitor, _frame_with_ego()) is True


def test_lane_has_no_signal_entry_is_false():
    # Signals exist, but not for this lane's source id -> get_signal_state None.
    lane_map = _FakeLaneMap({100: 7})
    legacy = _FakeRoadMap({999: _State.LANE_STATE_STOP})  # different lane
    hmap = _FakeHMap(closest_lane=100, lane_map=lane_map, legacy=legacy)
    scenario = SimpleNamespace(ego_id=0, map=hmap)
    monitor = SignalStateIs(scenario, params={"states": ["red"]})
    assert _run(monitor, _frame_with_ego()) is False
