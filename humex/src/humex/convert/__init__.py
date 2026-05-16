"""humex post-extraction pipeline — enhance, lane_map, role.

Plugin converters (``humex-converter-waymo`` et al.) handle the
format-specific extraction of raw scenario data. Everything that happens
afterwards — recomputing kinematics, building the lane graph, deriving
ego-relative agent roles — lives in this package and is run uniformly
across every dataset.

``humex convert <input>`` invokes :func:`run_pipeline` immediately after a
plugin succeeds. Users who want to re-run just the sidecars
(without re-extracting) can call :func:`run_sidecars_only`, or use the
``humex lane-map`` CLI command which wraps it.
"""

from .enhance import enhance_scenario, DataEnhancer
from .lane_map import build_lane_map_sidecar
from .role import build_role_sidecar
from .pipeline import PipelineResult, run_pipeline, run_sidecars_only

__all__ = [
    "DataEnhancer",
    "PipelineResult",
    "build_lane_map_sidecar",
    "build_role_sidecar",
    "enhance_scenario",
    "run_pipeline",
    "run_sidecars_only",
]
