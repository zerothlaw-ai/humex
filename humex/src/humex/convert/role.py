"""Stage 2C — build a ``role.pb`` sidecar from scenario + lane_map.

Thin wrapper around :func:`humex.hmap.build_role_table`. Requires
``lane_map.pb`` to exist first (it's the input to the role builder).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from humex.hmap import build_role_table as _build
from humex.hmap.hmap import HMap
from humex.hmap.lane_map import LaneMap
from humex.proto import lane_map_pb2


def build_role_sidecar(
    scenario_dir: Path,
    *,
    force: bool = False,
) -> Optional[Path]:
    """Build ``<scenario_dir>/role.pb`` from scenario.pb + map.pb + lane_map.pb.

    Returns the output path on success, ``None`` when skipped (already exists
    and ``force=False``). Raises if any input is missing or the build fails.
    """
    from humex.api import ScenarioAPI

    scenario_dir = Path(scenario_dir)
    scenario_pb = scenario_dir / "scenario.pb"
    map_pb = scenario_dir / "map.pb"
    lane_map_pb_path = scenario_dir / "lane_map.pb"
    if not scenario_pb.exists() or not map_pb.exists():
        raise FileNotFoundError(f"scenario.pb and map.pb required in {scenario_dir}")
    if not lane_map_pb_path.exists():
        raise FileNotFoundError(
            f"lane_map.pb required in {scenario_dir} — run the lane_map stage first"
        )

    out = scenario_dir / "role.pb"
    if out.exists() and not force:
        return None

    scenario = ScenarioAPI().load_from_folder(str(scenario_dir))

    lm_pb = lane_map_pb2.LaneMapData()
    lm_pb.ParseFromString(lane_map_pb_path.read_bytes())
    lane_map = LaneMap.from_proto(lm_pb)

    hmap = HMap(scenario.map, lane_map)
    role_table = _build(scenario, hmap)
    out.write_bytes(role_table.to_proto().SerializeToString())
    return out
