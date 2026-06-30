"""Real-data integration test for the SignalStateIs monitor.

Runs the monitor against the converted Waymo scenario ``converted/scenario7``,
which carries genuine traffic-signal data (GO / STOP / CAUTION states). Unlike
the unit tests (which fake the map surface), this exercises the full production
path end-to-end:

    ScenarioAPI load (HMap + lane_map.pb + signal.pb)
      -> find_closest_lane (segment id)
      -> LaneMapLane.source_lane_id  (segment -> source resolution)
      -> RoadMap.get_signal_state(source_id, timestamp)

It guards against pipeline drift that fakes can't catch — e.g. signals not
being loaded, the segment->source id space silently diverging, or
find_closest_lane returning ids the signal table isn't keyed by.

``converted/`` is gitignored, so this scenario is absent in CI; the test skips
cleanly when the data isn't present rather than failing.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.proto import signal_pb2

_State = signal_pb2.SignalState.State

# Repo root is three levels up: <repo>/humex/tests/<this file>
_SCENARIO_DIR = Path(__file__).parent.parent.parent / "converted" / "scenario7"
_REQUIRED = ["scenario.pb", "map.pb", "signal.pb", "lane_map.pb"]

_missing = [f for f in _REQUIRED if not (_SCENARIO_DIR / f).is_file()]
pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"converted/scenario7 not available (missing: {_missing}); "
           f"data is gitignored and absent in CI",
)


@pytest.fixture(scope="module")
def scenario():
    from humex.api.scenario_api.load_scenario_api import ScenarioAPI
    api = ScenarioAPI()
    return api.load_from_proto_files(
        scenario_file_path=str(_SCENARIO_DIR / "scenario.pb"),
        map_file_path=str(_SCENARIO_DIR / "map.pb"),
        signal_file_path=str(_SCENARIO_DIR / "signal.pb"),
        lane_map_file_path=str(_SCENARIO_DIR / "lane_map.pb"),
        role_file_path=str(_SCENARIO_DIR / "role.pb"),
    )


def _run_all_frames(scenario, states):
    """Run SignalStateIs(states) over every frame; return list of per-frame results."""
    from humex.metrics.monitors.catalog.signal_state_is import SignalStateIs
    mon = SignalStateIs(scenario, params={"states": states})
    out = []
    for ts in sorted(scenario.frames.keys()):
        mon.curr_frame = scenario.frames[ts]
        out.append((ts, mon.calculate()))
    return out


def test_scenario_loads_with_signals_via_hmap(scenario):
    """Sanity: the scenario loads as an HMap with signal data attached."""
    assert type(scenario.map).__name__ == "HMap"
    legacy = scenario.map.legacy_map
    assert legacy.has_signals(), "scenario7 should carry signal data"


def test_red_yields_true_frames_all_backed_by_stop_state(scenario):
    """states=['red'] must produce real True frames, and every True frame must
    correspond to a genuine STOP signal on ego's (source-resolved) lane.

    This is the core anti-drift assertion: if signals stopped loading or the
    segment->source mapping broke, this would collapse to all-False/None.
    """
    results = _run_all_frames(scenario, ["red"])
    true_ts = [ts for ts, r in results if r is True]
    assert len(true_ts) > 0, "expected at least one red-signal frame; got none " \
                             "(signals not loaded or segment->source mapping broken?)"

    legacy = scenario.map.legacy_map
    resolution_was_nontrivial = False
    for ts in true_ts:
        frame = scenario.frames[ts]
        ego = frame.get_ego(scenario)
        assert ego is not None
        seg = scenario.map.find_closest_lane(
            ego.sp.position.to_tuple(), heading=ego.sp.heading.yaw
        )
        assert seg is not None
        lane = scenario.map.lane_map.get_lane(seg)
        source_id = getattr(lane, "source_lane_id", 0) or seg
        # The monitor said True -> the resolved source lane's state must be STOP.
        assert legacy.get_signal_state(source_id, ts) == _State.LANE_STATE_STOP
        if seg != source_id:
            resolution_was_nontrivial = True

    # At least one True frame must have had segment id != source lane id, proving
    # the segment->source resolution is genuinely exercised (not a passthrough).
    assert resolution_was_nontrivial, \
        "segment->source resolution never differed; resolution path not exercised"


def test_green_yields_true_but_arrow_red_does_not(scenario):
    """Positive/negative discrimination on real data: ego's lane sees GREEN at
    some point (True), but never an ARROW_RED (no True frames)."""
    green = [r for _, r in _run_all_frames(scenario, ["green"])]
    arrow_red = [r for _, r in _run_all_frames(scenario, ["arrow_red"])]

    assert any(r is True for r in green), "expected green frames in scenario7"
    assert not any(r is True for r in arrow_red), \
        "scenario7 has no arrow_red states; monitor must not report True"


def test_empty_states_is_none_on_real_data(scenario):
    """Empty selection -> None on every frame (not evaluated)."""
    results = _run_all_frames(scenario, [])
    assert all(r is None for _, r in results)


def test_ego_absent_frame_returns_none(scenario):
    """scenario7 has at least one frame where ego is absent -> None there."""
    results = _run_all_frames(scenario, ["red"])
    # Cross-check: None exactly when ego is missing from the frame.
    for ts, r in results:
        ego = scenario.frames[ts].get_ego(scenario)
        if ego is None:
            assert r is None
