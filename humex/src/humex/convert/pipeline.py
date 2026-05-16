"""Conversion pipeline orchestration.

A successful run of ``humex convert <input>`` does four things, in order:

  1. **Extract** — a plugin converter parses the raw input file (TFRecord,
     parquet, CSV, ...) and writes ``scenario.pb`` + ``map.pb`` (+ optional
     ``signal.pb``, ``meta.json``) into the output directory.
  2. **Enhance** — recompute per-frame velocity and acceleration from raw
     position tracks (see :mod:`humex.convert.enhance`). The enhanced
     scenario overwrites the raw one — there is only one canonical
     ``scenario.pb``.
  3. **Lane map** — derive a lane graph (segments, neighbors, corridors)
     from ``map.pb`` and write ``lane_map.pb``
     (see :mod:`humex.convert.lane_map`).
  4. **Role table** — compute per-frame ego-relative agent roles (front,
     rear, left/right alongside, …) and write ``role.pb``
     (see :mod:`humex.convert.role`).

Stages 2–4 are best-effort: a failure in one stage records the error but
does not abort subsequent stages **as long as their inputs are still on
disk** (e.g. role needs lane_map; if lane_map fails, role is skipped).

The plugin extraction (stage 1) is the responsibility of the CLI — this
module assumes ``scenario.pb`` and ``map.pb`` already exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from humex.api import ScenarioAPI
from humex.proto import scenario_pb2

from .enhance import enhance_scenario
from .lane_map import build_lane_map_sidecar
from .role import build_role_sidecar


@dataclass
class PipelineResult:
    """Outcome of running stages 2–4 over a converted scenario directory."""

    scenario_dir: Path
    enhance_ok: bool = False
    lane_map_ok: bool = False
    role_ok: bool = False
    enhance_error: Optional[str] = None
    lane_map_error: Optional[str] = None
    role_error: Optional[str] = None
    lane_map_path: Optional[Path] = None
    role_path: Optional[Path] = None

    @property
    def all_ok(self) -> bool:
        return self.enhance_ok and self.lane_map_ok and self.role_ok

    def summary_lines(self) -> list[str]:
        """One ``OK <stage>`` / ``FAIL <stage>: <error>`` line per stage."""
        lines = []
        for name, ok, err in (
            ("enhance", self.enhance_ok, self.enhance_error),
            ("lane_map", self.lane_map_ok, self.lane_map_error),
            ("role", self.role_ok, self.role_error),
        ):
            lines.append(f"OK {name}" if ok else f"FAIL {name}: {err}")
        return lines


def run_pipeline(scenario_dir: Path, *, force: bool = False) -> PipelineResult:
    """Run stages 2–4 (enhance → lane_map → role) over an extracted scenario.

    ``scenario_dir`` must already contain ``scenario.pb`` + ``map.pb`` from
    a plugin converter run. The enhanced scenario overwrites
    ``scenario.pb`` in place; lane_map and role sidecars are written next
    to it.

    Each stage is wrapped in its own try/except so a failure doesn't abort
    the others (matching the hume backend's stage-2 semantics). When a stage
    fails the corresponding ``*_error`` field carries the message.
    """
    scenario_dir = Path(scenario_dir)
    scenario_pb_path = scenario_dir / "scenario.pb"
    map_pb_path = scenario_dir / "map.pb"
    if not scenario_pb_path.exists() or not map_pb_path.exists():
        raise FileNotFoundError(
            f"scenario.pb and map.pb must already exist in {scenario_dir} — "
            "plugin extraction (stage 1) is the caller's responsibility"
        )

    result = PipelineResult(scenario_dir=scenario_dir)

    # ---- Stage 2: enhance ----
    try:
        api = ScenarioAPI()
        # load_from_folder auto-discovers scenario.pb + map.pb + signal.pb
        # by filename, which matches what plugin converters write.
        scenario = api.load_from_folder(str(scenario_dir), enhance=False)
        enhance_scenario(scenario)
        scenario_pb = api.scenario_to_proto(scenario)
        scenario_pb_path.write_bytes(scenario_pb.SerializeToString())
        result.enhance_ok = True
    except Exception as e:
        result.enhance_error = f"{type(e).__name__}: {e}"

    # ---- Stage 3: lane_map ----
    try:
        out = build_lane_map_sidecar(scenario_dir, force=force)
        result.lane_map_path = out if out is not None else scenario_dir / "lane_map.pb"
        result.lane_map_ok = True
    except Exception as e:
        result.lane_map_error = f"{type(e).__name__}: {e}"

    # ---- Stage 4: role (skips silently if lane_map failed) ----
    if result.lane_map_ok:
        try:
            out = build_role_sidecar(scenario_dir, force=force)
            result.role_path = out if out is not None else scenario_dir / "role.pb"
            result.role_ok = True
        except Exception as e:
            result.role_error = f"{type(e).__name__}: {e}"
    else:
        result.role_error = "skipped (lane_map stage failed)"

    return result


def run_sidecars_only(scenario_dir: Path, *, force: bool = False) -> PipelineResult:
    """Re-run only stages 3+4 (lane_map → role) without touching scenario.pb.

    Useful when iterating on the lane_map / role algorithm: tweak the builder,
    rerun this on an already-converted directory, skip the expensive plugin
    + enhance steps. Backs ``humex lane-map`` on the CLI.
    """
    scenario_dir = Path(scenario_dir)
    result = PipelineResult(scenario_dir=scenario_dir, enhance_ok=True)

    try:
        out = build_lane_map_sidecar(scenario_dir, force=force)
        result.lane_map_path = out if out is not None else scenario_dir / "lane_map.pb"
        result.lane_map_ok = True
    except Exception as e:
        result.lane_map_error = f"{type(e).__name__}: {e}"

    if result.lane_map_ok:
        try:
            out = build_role_sidecar(scenario_dir, force=force)
            result.role_path = out if out is not None else scenario_dir / "role.pb"
            result.role_ok = True
        except Exception as e:
            result.role_error = f"{type(e).__name__}: {e}"
    else:
        result.role_error = "skipped (lane_map stage failed)"

    return result
