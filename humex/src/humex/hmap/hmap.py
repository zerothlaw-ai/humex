"""Unified map facade.

Wraps the legacy :class:`RoadMap` (signals, road segments, raw map_data,
simulator path-planning helpers) and the v2 :class:`LaneMap` (lane-relative
queries: lane assignment, Frenet projection, lane graph traversal). Every
caller — monitors, role-table builder, visualizers — talks to this class
instead of either underlying map directly. That keeps lane queries on
the v2 implementation and prevents accidental regressions through the
legacy KDTree-tiebreak `find_closest_lane`.

Lane queries are explicit methods that delegate to LaneMap. Everything
else falls through ``__getattr__`` to the legacy RoadMap, so existing
non-lane attributes (``map_data``, ``get_segments``, ``has_signals``,
``get_signal_state``, simulator helpers like ``query_closest_point``,
``query_point_in_front``, ``get_lookahead_point``) keep working unchanged.
"""
from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .road_map import RoadMap
    from .lane_map import LaneMap, LaneMapLane


class HMap:
    def __init__(
        self,
        legacy_map: "RoadMap",
        lane_map: Optional["LaneMap"],
    ) -> None:
        if lane_map is None:
            raise ValueError(
                "HMap requires a LaneMap v2 sidecar. The legacy RoadMap "
                "lane queries are no longer routed for monitors. Re-run the "
                "Hume conversion pipeline to generate lane_map.pb (lane-map-v2.1) "
                "or call regenerate_subtask_asset(asset='lane_map')."
            )
        # Underscore-prefixed so __getattr__ doesn't recurse on these.
        self._legacy = legacy_map
        self._lane_map = lane_map

    # ---- Direct access to the underlying LaneMap for callers that need
    # the raw graph (e.g. role-table builder iterating lanes dict). ----

    @property
    def lane_map(self) -> "LaneMap":
        return self._lane_map

    @property
    def legacy_map(self) -> "RoadMap":
        """Escape hatch for code paths that genuinely need the RoadMap object
        (signal loading, visualizer). Lane queries here would bypass v2 — don't.
        """
        return self._legacy

    # ---- Lane queries: ALL delegate to LaneMap v2 ----

    def find_closest_lane(
        self,
        position: Tuple[float, float, float],
        max_distance: Optional[float] = None,
        heading: Optional[float] = None,
    ) -> Optional[int]:
        return self._lane_map.find_closest_lane(
            position, max_distance=max_distance, heading=heading
        )

    def find_containing_lanes(
        self,
        position: Tuple[float, float, float],
        heading: Optional[float] = None,
        lateral_slack: float = 0.5,
    ) -> List[int]:
        """All lanes whose drivable polygon contains the point (within
        ``lateral_slack`` meters). See :meth:`LaneMap.find_containing_lanes`."""
        return self._lane_map.find_containing_lanes(
            position, heading=heading, lateral_slack=lateral_slack
        )

    def get_corridor_id(self, lane_id: int) -> int:
        """Corridor id of ``lane_id``, or 0 when the lane doesn't exist or
        the underlying lane_map predates v2.2."""
        lane = self._lane_map.get_lane(lane_id)
        return getattr(lane, "corridor_id", 0) if lane is not None else 0

    def project_onto_lane_path(
        self,
        point: Tuple[float, float],
        lane_path: List[int],
    ) -> Optional[float]:
        return self._lane_map.project_onto_lane_path(point, lane_path)

    def get_reachable_lanes(
        self, lane_id: int, max_distance: float = 200.0
    ) -> List[int]:
        return self._lane_map.get_reachable_lanes(lane_id, max_distance)

    def get_lane(self, lane_id: int) -> Optional["LaneMapLane"]:
        return self._lane_map.get_lane(lane_id)

    def next_lanes(self, lane_id: int) -> List[int]:
        return self._lane_map.next_lanes(lane_id)

    def prev_lanes(self, lane_id: int) -> List[int]:
        return self._lane_map.prev_lanes(lane_id)

    def left_lanes(self, lane_id: int) -> List[int]:
        return self._lane_map.left_lanes(lane_id)

    def right_lanes(self, lane_id: int) -> List[int]:
        return self._lane_map.right_lanes(lane_id)

    def get_crossing_lanes(self, lane_id: int) -> List[int]:
        """Lanes whose drivable polygon physically crosses ``lane_id`` (and is
        not a prev/next/left/right neighbor). Populated by lane_map builder
        v2.1+; older lane_maps return empty list.
        """
        lane = self._lane_map.get_lane(lane_id)
        if lane is None:
            return []
        return list(getattr(lane, "overlapping_lane_ids", []))

    def get_intersection_for_lane(self, lane_id: int):
        return self._lane_map.get_intersection_for_lane(lane_id)

    def is_lane_in_intersection(self, lane_id: int) -> bool:
        return self._lane_map.is_lane_in_intersection(lane_id)

    # ---- Non-lane passthrough to legacy RoadMap ----

    @property
    def name(self) -> str:
        return self._legacy.name

    @property
    def map_data(self):
        """Raw legacy MapData. Several monitors still iterate this for
        per-lane stop-line / boundary info that lane_map v2 doesn't carry yet
        (stop_line_crossed, ego_out_of_map, ego_center_offset). Not a lane
        query — it's a data accessor."""
        return self._legacy.map_data

    def __getattr__(self, name: str):
        # Called only when the normal attribute lookup fails. This catches:
        #  - get_segments(), build_spatial_index() (visualizer)
        #  - load_signals(), has_signals(), get_signal_state(),
        #    get_signal_frame() (signal queries)
        #  - query_closest_point(), query_point_in_front(),
        #    get_lookahead_point() (simulator path-planning helpers — these
        #    still use legacy lane lookup; their callers in the simulator
        #    don't go through monitors).
        # Anything not on the legacy RoadMap raises AttributeError naturally.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._legacy, name)
