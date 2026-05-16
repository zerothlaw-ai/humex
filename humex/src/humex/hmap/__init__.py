"""humex map subsystem — HD-map data + queries for AV / physical-AI scenarios.

``HMap`` is the public facade that combines lane-graph queries (``LaneMap``)
and road-level queries (``RoadMap``). Most callers can use ``HMap`` and let it
delegate. ``build_lane_map`` and ``build_role_table`` are the canonical builders.
"""

from .hmap import HMap
from .lane_map import LaneMap
from .road_map import RoadMap
from .lane_map_builder import build_lane_map
from .role_table import RoleTable
from .role_table_builder import build_role_table

__all__ = [
    "HMap",
    "LaneMap",
    "RoadMap",
    "RoleTable",
    "build_lane_map",
    "build_role_table",
]
