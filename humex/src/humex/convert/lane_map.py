"""Stage 2B — build a ``lane_map.pb`` sidecar from a scenario's ``map.pb``.

Thin wrapper around :func:`humex.hmap.build_lane_map` that handles loading
the source map, calling the builder, and writing the proto-serialized result
next to ``scenario.pb``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from humex.hmap import build_lane_map as _build
from humex.hmap.lane_map import LaneMap
from humex.hmap.road_map_loader import RoadMapLoader


def build_lane_map_sidecar(
    scenario_dir: Path,
    *,
    force: bool = False,
) -> Optional[Path]:
    """Build ``<scenario_dir>/lane_map.pb`` from ``<scenario_dir>/map.pb``.

    Returns the output path on success, ``None`` when skipped because the file
    already exists and ``force=False``. Raises if ``map.pb`` is missing or the
    build fails — the pipeline caller catches and records the failure.
    """
    scenario_dir = Path(scenario_dir)
    map_pb = scenario_dir / "map.pb"
    if not map_pb.exists():
        raise FileNotFoundError(f"map.pb missing in {scenario_dir}")

    out = scenario_dir / "lane_map.pb"
    if out.exists() and not force:
        return None

    road_map = RoadMapLoader.create_road_map(str(map_pb), map_name=scenario_dir.name)
    lm: LaneMap = _build(road_map)
    out.write_bytes(lm.to_proto().SerializeToString())
    return out
