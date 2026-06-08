"""humex — behavioral metrics for autonomous-vehicle and physical-AI scenarios.

High-level Python APIs for:
- Loading and preparing scenarios
- Analyzing scenarios with metrics
- Converting and computing metric DAGs
- Natural language interaction via LLM

See ``humex.api.core_apis`` for a comprehensive facade listing all public APIs
with full signatures, parameter descriptions, and usage examples::

    import humex.api.core_apis
    help(humex.api.core_apis)

    from humex.api.core_apis import (
        ScenarioAPI,
        ComputeDagMetricsAPI,
    )
"""

from .api import (
    Chat,
    ScenarioAPI,
    ComputeDagMetricsAPI,
)
from .hmap import HMap, LaneMap, RoadMap, RoleTable, build_lane_map, build_role_table

__version__ = "0.2.0"

# Plugin-API version. Converter plugins may declare a ``MIN_HUMEX_API_VERSION``
# class attr; the registry skips converters whose minimum exceeds this value
# instead of letting an incompatible plugin crash the host. Bump on breaking
# changes to BaseConverter / ConversionResult / registry contracts.
__api_version__ = 1

__all__ = [
    "ScenarioAPI",
    "ComputeDagMetricsAPI",
    "Chat",
    "HMap",
    "LaneMap",
    "RoadMap",
    "RoleTable",
    "build_lane_map",
    "build_role_table",
]
