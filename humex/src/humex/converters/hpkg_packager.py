"""Package a converted scenario directory into a portable ``.hpkg`` file.

A ``.hpkg`` (humex package) file is a zip archive with this layout::

    manifest.json
    scenario/
        scenario.pb
        map.pb
        meta.json
        [lane_map.pb]    # built by humex.convert.run_pipeline
        [role.pb]        # built by humex.convert.run_pipeline
        [signal.pb]      # AV scenarios only
        [robot.pb]       # articulated-robot scenarios only
        [robots/...]     # URDF + meshes referenced by robot.pb

The packager doesn't care which converter produced the input directory — it
just zips up whatever is there. DROID episodes carry robot.pb + robots/;
Waymo scenarios carry signal.pb. Both flow through unchanged. Standard zip
tools (``unzip``, ``python -m zipfile``) can crack a ``.hpkg`` open without
this library.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def package_as_hpkg(
    episode_dir: Path,
    output_path: Path,
    *,
    name: str,
    source: Optional[dict[str, Any]] = None,
    scenario_metadata: Optional[dict[str, Any]] = None,
) -> Path:
    """Zip ``episode_dir`` into a ``.hpkg`` file at ``output_path``.

    Returns the output path on success. Raises ``FileNotFoundError`` if the
    input dir is missing scenario.pb or map.pb.
    """
    episode_dir = Path(episode_dir)
    output_path = Path(output_path)

    scenario_pb = episode_dir / "scenario.pb"
    map_pb = episode_dir / "map.pb"
    if not scenario_pb.exists() or not map_pb.exists():
        raise FileNotFoundError(
            f"need scenario.pb and map.pb in {episode_dir} (have: "
            f"{[p.name for p in episode_dir.iterdir() if p.is_file()]})"
        )

    has_signal = (episode_dir / "signal.pb").exists()
    has_robot = (episode_dir / "robot.pb").exists()

    manifest = {
        "format_version": 1,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source or {},
        "contents": {
            "scenario_data": True,
            "metric_result": False,
            "scenario_config": False,
            "signal_data": has_signal,
            "robot_data": has_robot,
        },
        "scenario_metadata": scenario_metadata or {},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for f in sorted(episode_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(episode_dir)
            # Skip any file we'd produce ourselves at the zip root.
            if rel.as_posix() == "manifest.json":
                continue
            zf.write(f, f"scenario/{rel.as_posix()}")

    return output_path


def load_meta_for_manifest(episode_dir: Path) -> dict[str, Any]:
    """Pull duration / frequency / num_frames out of the converter's meta.json."""
    meta_path = Path(episode_dir) / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return {}
    return {
        "duration": meta.get("duration"),
        "frequency": meta.get("frequency"),
        "num_frames": meta.get("num_frames"),
    }
