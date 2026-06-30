"""Unit tests for the ConflictingVehiclePet monitor.

Builds a real LaneMap + HMap with hand-made crossing geometry (so the real
find_closest_lane / get_reachable_lanes / get_crossing_lanes / find_containing_lanes
code paths run), places ego + a conflicting vehicle, and asserts the PET.

Geometry:
  - ego lane E: straight east along y=0, x in [0, 40], source 1, seg id 1
  - cross lane C: straight north along x=20, y in [-20, 20], source 2, seg id 2
    (perpendicular -> "cross"); E and C overlap, crossing at (20, 0)
  - oncoming lane O: ~anti-parallel, (40,3)->(0,-3), source 3, seg id 3,
    also crossing ego at (20, 0) (Δheading ~171° -> "oncoming")
"""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.components.frame import Frame
from humex.components.object import Object
from humex.components.statepoint import StatePoint
from humex.hmap.hmap import HMap
from humex.hmap.lane_map import LaneMap, LaneMapLane, LaneMapPoint
from humex.metrics.monitors.catalog.conflicting_vehicle_pet import ConflictingVehiclePet


# ---- geometry builders ---------------------------------------------------

def _pts(coords):
    return [[LaneMapPoint(x, y, 0.0) for (x, y) in coords]]

def _ego_lane():
    return LaneMapLane(id=1, source_lane_id=1,
                       center_line=_pts([(x, 0.0) for x in range(0, 45, 5)]),
                       overlapping_lane_ids=[])

def _cross_lane():
    return LaneMapLane(id=2, source_lane_id=2,
                       center_line=_pts([(20.0, y) for y in range(-20, 25, 5)]),
                       overlapping_lane_ids=[1])

def _oncoming_lane():
    # (40,3) -> (0,-3): heading ~ -171.5 deg, crosses y=0 at x=20
    coords = [(40.0 - 5.0 * i, 3.0 - 0.75 * i) for i in range(9)]
    return LaneMapLane(id=3, source_lane_id=3, center_line=_pts(coords),
                       overlapping_lane_ids=[1])

def _hmap(lanes, ego_crossings):
    """Build HMap; ego lane (id 1) gets overlapping_lane_ids = ego_crossings."""
    lane_dict = {l.id: l for l in lanes}
    lane_dict[1].overlapping_lane_ids = list(ego_crossings)
    lm = LaneMap(lanes=lane_dict)
    return HMap(SimpleNamespace(name="test"), lm)

def _obj(oid, x, y, vx, vy, is_ego=False):
    o = Object(obj_id=oid, length=4.0, width=2.0, is_ego=is_ego)
    yaw = math.atan2(vy, vx) if (vx or vy) else 0.0
    o.update_mutable(StatePoint(position=(x, y, 0.0), velocity=(vx, vy, 0.0), heading=(0.0, 0.0, yaw)))
    return o

def _scenario(hmap):
    return SimpleNamespace(ego_id=0, map=hmap)

def _frame(*objs):
    f = Frame(timestamp=0)
    for o in objs:
        f.obj_list[o.id] = o
    return f

def _run(hmap, frame, params=None):
    sc = _scenario(hmap)
    mon = ConflictingVehiclePet(sc, params=params if params is not None else {})
    mon.curr_frame = frame
    return mon.calculate()


# ---- cross-traffic core cases -------------------------------------------

def test_cross_equal_arrival_pet_zero():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)   # 15 m to CP, 10 m/s -> 1.5 s
    veh = _obj(1, 20.0, -15.0, 0.0, 10.0)             # 15 m to CP, 10 m/s -> 1.5 s
    pet = _run(hmap, _frame(ego, veh))
    assert pet is not None and pet < 1e-6           # simultaneous -> PET ~ 0

def test_cross_staggered_arrival_positive_pet():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)   # 15/10 = 1.5 s
    veh = _obj(1, 20.0, -15.0, 0.0, 5.0)              # 15/5  = 3.0 s
    pet = _run(hmap, _frame(ego, veh))
    assert abs(pet - 1.5) < 1e-3

def test_cross_filtered_out_when_only_oncoming_selected():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)
    veh = _obj(1, 20.0, -15.0, 0.0, 10.0)
    pet = _run(hmap, _frame(ego, veh), params={"conflict_types": ["oncoming"]})
    assert pet == float("inf")                      # perpendicular lane is "cross", excluded


# ---- oncoming case -------------------------------------------------------

def test_oncoming_detected_when_selected_and_filtered_when_cross_only():
    hmap = _hmap([_ego_lane(), _oncoming_lane()], ego_crossings=[3])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)
    # vehicle on O at its t=2 sample (30, 1.5), travelling toward (0,-3)
    veh = _obj(1, 30.0, 1.5, -9.88, -1.52)
    pet_oncoming = _run(hmap, _frame(ego, veh), params={"conflict_types": ["oncoming"]})
    pet_cross = _run(hmap, _frame(ego, veh), params={"conflict_types": ["cross"]})
    assert pet_oncoming != float("inf") and pet_oncoming >= 0.0
    assert pet_cross == float("inf")


# ---- edge cases ----------------------------------------------------------

def test_conflict_point_behind_ego_is_inf():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 30.0, 0.0, 10.0, 0.0, is_ego=True)  # already past CP at x=20
    veh = _obj(1, 20.0, -15.0, 0.0, 10.0)
    assert _run(hmap, _frame(ego, veh)) == float("inf")

def test_stopped_ego_is_inf():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 0.05, 0.0, is_ego=True)   # below min_speed
    veh = _obj(1, 20.0, -15.0, 0.0, 10.0)
    assert _run(hmap, _frame(ego, veh)) == float("inf")

def test_stopped_vehicle_is_inf():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)
    veh = _obj(1, 20.0, -15.0, 0.0, 0.05)             # below min_speed
    assert _run(hmap, _frame(ego, veh)) == float("inf")

def test_ego_absent_is_none():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    assert _run(hmap, _frame()) is None               # empty frame

def test_empty_conflict_types_is_none():
    hmap = _hmap([_ego_lane(), _cross_lane()], ego_crossings=[2])
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)
    veh = _obj(1, 20.0, -15.0, 0.0, 10.0)
    assert _run(hmap, _frame(ego, veh), params={"conflict_types": []}) is None

def test_no_lane_map_is_inf():
    sc = SimpleNamespace(ego_id=0, map=None)          # self.lane_map -> None
    ego = _obj(0, 5.0, 0.0, 10.0, 0.0, is_ego=True)
    mon = ConflictingVehiclePet(sc, params={})
    mon.curr_frame = _frame(ego)
    assert mon.calculate() == float("inf")
