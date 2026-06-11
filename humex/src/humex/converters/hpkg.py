"""Read and write the ``.hpkg`` archive format — the single source of truth.

A ``.hpkg`` (humex package) is a zip archive::

    manifest.json
    scenario/
        scenario.pb      # ScenarioData (optional — map-only packages are valid)
        map.pb           # Map
        signal.pb        # optional (AV scenarios)
        robot.pb         # optional (articulated-robot scenarios)
        config.json      # optional editable scenario config (vehicles/keyframes)
        meta.json        # optional converter metadata
        robots/...       # optional URDF + meshes referenced by robot.pb
    metrics/
        metricresult.pb  # optional MetricResult
        metrics.yaml     # optional metric DAG config

This module owns the layout, arcnames, legacy name fallbacks, and the manifest
schema, so every producer/consumer agrees. It is **pure stdlib** (no protobuf /
numpy) so it imports cleanly in constrained runtimes such as Pyodide.

Symmetric API: :func:`pack_hpkg` (pieces -> bytes) and :func:`unpack_hpkg`
(bytes -> pieces). :func:`extract_hpkg` is the on-disk variant for callers that
need real file paths (e.g. serving ``robots/`` assets).
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# --- canonical write-side arcnames (single source of truth) ----------------
MANIFEST = "manifest.json"
SCENARIO_PB = "scenario/scenario.pb"
MAP_PB = "scenario/map.pb"
SIGNAL_PB = "scenario/signal.pb"
ROBOT_PB = "scenario/robot.pb"
CONFIG_JSON = "scenario/config.json"
METRIC_RESULT_PB = "metrics/metricresult.pb"
METRIC_YAML = "metrics/metrics.yaml"

# --- read-side fallbacks (other tools / older exports wrote flat/alt names) -
_SCENARIO_CANDIDATES = ["scenario/scenario.pb", "scenario.pb"]
_MAP_CANDIDATES = ["scenario/map.pb", "map.pb"]
_SIGNAL_CANDIDATES = ["scenario/signal.pb", "signal.pb"]
_ROBOT_CANDIDATES = ["scenario/robot.pb", "robot.pb"]
_CONFIG_CANDIDATES = ["scenario/config.json", "config.json"]
_RESULT_CANDIDATES = ["metrics/metricresult.pb", "metrics/metric_result.pb"]
_YAML_CANDIDATES = ["metrics/metrics.yaml", "metrics/config.yaml"]


def build_manifest(
    *,
    name: str,
    source: Any = "zeno",
    scenario_metadata: Optional[dict] = None,
    has_scenario: bool = False,
    has_map: bool = False,
    has_signal: bool = False,
    has_robot: bool = False,
    has_metric_result: bool = False,
    has_metric_config: bool = False,
    has_scenario_config: bool = False,
) -> dict:
    """Build the one canonical manifest (``format_version`` 1).

    ``source`` may be a dict (converter metadata) or a string tool name.
    """
    return {
        "format_version": 1,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source if isinstance(source, dict) else {"tool": source},
        "contents": {
            "scenario_data": has_scenario,
            "map_data": has_map,
            "metric_result": has_metric_result,
            "metric_config": has_metric_config,
            "scenario_config": has_scenario_config,
            "signal_data": has_signal,
            "robot_data": has_robot,
        },
        "scenario_metadata": scenario_metadata or {},
    }


def pack_hpkg(
    *,
    name: str,
    scenario_pb: Optional[bytes] = None,
    map_pb: Optional[bytes] = None,
    signal_pb: Optional[bytes] = None,
    robot_pb: Optional[bytes] = None,
    metric_result_pb: Optional[bytes] = None,
    metric_yaml: Optional[str] = None,
    config_json: Optional[dict] = None,
    extra_files: Optional[Dict[str, bytes]] = None,
    source: Any = "zeno",
    scenario_metadata: Optional[dict] = None,
) -> bytes:
    """Build a ``.hpkg`` zip in memory from the given pieces; return raw bytes.

    Scenario is optional (map-only packages are valid). ``extra_files`` maps
    arbitrary arcnames -> bytes (e.g. ``scenario/robots/…``, ``scenario/meta.json``).
    The manifest ``contents`` flags are derived from what is present.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if scenario_pb is not None:
            zf.writestr(SCENARIO_PB, scenario_pb)
        if map_pb is not None:
            zf.writestr(MAP_PB, map_pb)
        if signal_pb is not None:
            zf.writestr(SIGNAL_PB, signal_pb)
        if robot_pb is not None:
            zf.writestr(ROBOT_PB, robot_pb)
        if config_json is not None:
            zf.writestr(CONFIG_JSON, json.dumps(config_json, indent=2))
        if metric_result_pb is not None:
            zf.writestr(METRIC_RESULT_PB, metric_result_pb)
        if metric_yaml:
            zf.writestr(METRIC_YAML, metric_yaml)
        for arcname, data in (extra_files or {}).items():
            zf.writestr(arcname, data)
        manifest = build_manifest(
            name=name,
            source=source,
            scenario_metadata=scenario_metadata,
            has_scenario=scenario_pb is not None,
            has_map=map_pb is not None,
            has_signal=signal_pb is not None,
            has_robot=robot_pb is not None,
            has_metric_result=metric_result_pb is not None,
            has_metric_config=bool(metric_yaml),
            has_scenario_config=config_json is not None,
        )
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
    return buf.getvalue()


@dataclass
class HpkgContents:
    """In-memory result of :func:`unpack_hpkg`."""

    manifest: dict
    scenario_pb: Optional[bytes] = None
    map_pb: Optional[bytes] = None
    signal_pb: Optional[bytes] = None
    robot_pb: Optional[bytes] = None
    metric_result_pb: Optional[bytes] = None
    metric_yaml: Optional[str] = None
    config_json: Optional[dict] = None
    files: Dict[str, bytes] = field(default_factory=dict)


def _first(names, candidates: List[str]) -> Optional[str]:
    for cand in candidates:
        if cand in names:
            return cand
    return None


def _first_glob(names, prefix: str, suffixes) -> Optional[str]:
    for n in sorted(names):
        if n.startswith(prefix) and n.endswith(tuple(suffixes)):
            return n
    return None


def unpack_hpkg(data: bytes) -> HpkgContents:
    """Read a ``.hpkg`` from raw bytes. Resolves all legacy name fallbacks."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        files = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}

    manifest: dict = {}
    if MANIFEST in files:
        try:
            manifest = json.loads(files[MANIFEST].decode("utf-8"))
        except Exception:
            manifest = {}

    def pick(cands):
        n = _first(files, cands)
        return files[n] if n is not None else None

    result_pb = pick(_RESULT_CANDIDATES)
    if result_pb is None:
        n = _first_glob(files, "metrics/", (".pb",))
        result_pb = files[n] if n is not None else None

    yaml_bytes = pick(_YAML_CANDIDATES)
    if yaml_bytes is None:
        n = _first_glob(files, "metrics/", (".yaml", ".yml"))
        yaml_bytes = files[n] if n is not None else None

    config_json = None
    config_bytes = pick(_CONFIG_CANDIDATES)
    if config_bytes is not None:
        try:
            config_json = json.loads(config_bytes.decode("utf-8"))
        except Exception:
            config_json = None

    return HpkgContents(
        manifest=manifest,
        scenario_pb=pick(_SCENARIO_CANDIDATES),
        map_pb=pick(_MAP_CANDIDATES),
        signal_pb=pick(_SIGNAL_CANDIDATES),
        robot_pb=pick(_ROBOT_CANDIDATES),
        metric_result_pb=result_pb,
        metric_yaml=yaml_bytes.decode("utf-8") if yaml_bytes is not None else None,
        config_json=config_json,
        files=files,
    )


@dataclass
class HpkgExtract:
    """On-disk result of :func:`extract_hpkg` (canonical paths into ``out_dir``)."""

    manifest: dict
    out_dir: str
    scenario_dir: Optional[str] = None
    scenario_pb: Optional[str] = None
    map_pb: Optional[str] = None
    signal_pb: Optional[str] = None
    robot_pb: Optional[str] = None
    metric_result_pb: Optional[str] = None
    metric_yaml: Optional[str] = None
    config_json: Optional[str] = None


def extract_hpkg(src: Union[bytes, str, Path], out_dir: Union[str, Path]) -> HpkgExtract:
    """Extract a ``.hpkg`` to ``out_dir`` and resolve canonical file paths.

    ``src`` may be raw bytes or a path to an ``.hpkg``. Handles the same legacy
    name fallbacks as :func:`unpack_hpkg`. The on-disk layout (including
    ``scenario/robots/…``) is preserved so callers can serve those assets.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zsrc: Any = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else str(src)
    with zipfile.ZipFile(zsrc) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        zf.extractall(out)

    manifest: dict = {}
    mpath = out / MANIFEST
    if mpath.exists():
        try:
            manifest = json.loads(mpath.read_text())
        except Exception:
            manifest = {}

    def pick_path(cands):
        n = _first(names, cands)
        return str(out / n) if n is not None else None

    result = pick_path(_RESULT_CANDIDATES)
    if result is None:
        n = _first_glob(names, "metrics/", (".pb",))
        result = str(out / n) if n is not None else None

    yaml_path = pick_path(_YAML_CANDIDATES)
    if yaml_path is None:
        n = _first_glob(names, "metrics/", (".yaml", ".yml"))
        yaml_path = str(out / n) if n is not None else None

    scenario_dir = str(out / "scenario") if (out / "scenario").is_dir() else None

    return HpkgExtract(
        manifest=manifest,
        out_dir=str(out),
        scenario_dir=scenario_dir,
        scenario_pb=pick_path(_SCENARIO_CANDIDATES),
        map_pb=pick_path(_MAP_CANDIDATES),
        signal_pb=pick_path(_SIGNAL_CANDIDATES),
        robot_pb=pick_path(_ROBOT_CANDIDATES),
        metric_result_pb=result,
        metric_yaml=yaml_path,
        config_json=pick_path(_CONFIG_CANDIDATES),
    )
