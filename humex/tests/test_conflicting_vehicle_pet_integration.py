"""Real-data integration test for ConflictingVehiclePet against converted/scenario7.

Exercises the full production path (HMap + lane_map.pb): reachable-corridor
crossing-lane selection, source-lane union, Shapely conflict-point geometry,
and arc-length PET — on real Waymo geometry, guarding against pipeline drift
that the unit-test geometry can't catch (e.g. overlapping_lane_ids not being
populated, or segment->source id divergence).

IMPORTANT expectation: this is a SIGNALIZED intersection, so ego and cross
traffic are phased apart and rarely move through the conflict point at once.
MOST frames legitimately return inf (ego stopped, conflicting vehicle stopped,
or no real crossing). The test asserts "at least some frames yield a finite PET
in a plausible band", NOT that many do.

converted/ is gitignored, so the scenario is absent in CI; the test skips
cleanly when the data isn't present.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_SCENARIO_DIR = Path(__file__).parent.parent.parent / "converted" / "scenario7"
_REQUIRED = ["scenario.pb", "map.pb", "lane_map.pb"]
_missing = [f for f in _REQUIRED if not (_SCENARIO_DIR / f).is_file()]
pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason=f"converted/scenario7 not available (missing: {_missing}); gitignored, absent in CI",
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


def _run_all(scenario, params):
    from humex.metrics.monitors.catalog.conflicting_vehicle_pet import ConflictingVehiclePet
    mon = ConflictingVehiclePet(scenario, params=params)
    out = []
    for ts in sorted(scenario.frames.keys()):
        mon.curr_frame = scenario.frames[ts]
        out.append((ts, mon.calculate()))
    return out


def test_loads_as_hmap(scenario):
    assert type(scenario.map).__name__ == "HMap"
    assert scenario.map.lane_map is not None


def test_some_finite_pet_in_plausible_band(scenario):
    results = _run_all(scenario, {"conflict_types": ["cross", "oncoming"]})
    finite = [r for _, r in results if r not in (None, float("inf"))]
    assert len(finite) >= 1, "expected at least one finite PET frame on scenario7"
    # plausible band for an urban intersection (seconds)
    assert all(0.0 <= v <= 60.0 for v in finite), f"PET out of plausible band: {finite}"


def test_most_frames_are_inf_or_none(scenario):
    """Signal phasing => finite-PET frames are a minority, not a failure."""
    results = _run_all(scenario, {"conflict_types": ["cross", "oncoming"]})
    finite = [r for _, r in results if r not in (None, float("inf"))]
    assert len(finite) < len(results) / 2


def test_ego_absent_frames_return_none(scenario):
    results = _run_all(scenario, {"conflict_types": ["cross", "oncoming"]})
    for ts, r in results:
        if scenario.frames[ts].get_ego(scenario) is None:
            assert r is None


def test_cross_only_is_subset_of_both(scenario):
    both = {ts for ts, r in _run_all(scenario, {"conflict_types": ["cross", "oncoming"]})
            if r not in (None, float("inf"))}
    cross = {ts for ts, r in _run_all(scenario, {"conflict_types": ["cross"]})
             if r not in (None, float("inf"))}
    assert cross <= both                    # narrowing types can't add conflicts
    assert len(cross) >= 1                   # scenario7's conflicts are cross-type
