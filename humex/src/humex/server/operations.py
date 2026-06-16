"""Stateful humex operations for the local ``humex serve`` HTTP server.

Each browser tab gets its own :class:`Session`. A session owns a temp
directory that holds the currently-loaded ``scenario.pb`` / ``map.pb`` so a
follow-up evaluate / simulate / export operates on the held bytes — exactly
the stash model zeno's Pyodide worker implements in MEMFS
(see zeno ``frontend/public/workers/pyodide.worker.js``).

This module contains zero HTTP concerns; it only turns request payloads into
JSON-serializable dicts whose shapes match the worker's replies so the zeno
``LocalServerRuntime`` and ``BrowserRuntime`` are interchangeable.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional

import yaml
from google.protobuf.json_format import MessageToDict

from humex.proto import (
    map_pb2,
    metric_result_pb2,
    scenario_pb2,
    signal_pb2,
)

__all__ = ["Session"]


def _decode(data: Optional[bytes], msg_cls) -> Optional[dict]:
    """Raw protobuf bytes -> JSON dict (no field renaming; the TS transformers
    own zeno-shape conversion). Returns ``None`` for absent pieces."""
    if data is None:
        return None
    msg = msg_cls()
    msg.ParseFromString(data)
    return MessageToDict(msg, preserving_proto_field_name=True)


class Session:
    """One client tab's runtime state.

    Holds a temp dir with the loaded scenario/map bytes. Methods mirror the
    worker commands one-for-one (``parseHpkg`` → :meth:`import_package`, etc.).
    """

    def __init__(self) -> None:
        self._dir = tempfile.mkdtemp(prefix="humex-serve-")

    # -- paths -------------------------------------------------------------
    @property
    def _scenario_path(self) -> str:
        return os.path.join(self._dir, "scenario.pb")

    @property
    def _map_path(self) -> str:
        return os.path.join(self._dir, "map.pb")

    def _has_scenario(self) -> bool:
        return os.path.exists(self._scenario_path)

    def _has_map(self) -> bool:
        return os.path.exists(self._map_path)

    def close(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- stateless ops -----------------------------------------------------
    def parse_yaml(self, yaml_text: str) -> Dict[str, Any]:
        try:
            return {"success": True, "config": yaml.safe_load(yaml_text or "")}
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI verbatim
            return {"success": False, "error": str(exc)}

    def test_dag(self, dag_yaml: str) -> Dict[str, Any]:
        """Quick-Test a DAG against inline ``mock_monitors`` (no scenario/map)."""
        from humex.api.metrics_api import TestDagMetricsAPI

        out_dir = os.path.join(self._dir, "testdag_out")
        dag_path = os.path.join(self._dir, "testdag.yaml")
        with open(dag_path, "w") as f:
            f.write(dag_yaml or "")
        try:
            parsed = yaml.safe_load(dag_yaml or "") or {}
            raw = parsed.get("mock_monitors", [])
            mocks: Dict[str, Any] = {}
            if isinstance(raw, list):
                for m in raw:
                    mocks[m.get("name", "")] = {k: v for k, v in m.items() if k != "name"}
            elif isinstance(raw, dict):
                mocks = raw

            res = TestDagMetricsAPI().compute(
                dag_yaml_path=dag_path,
                mock_monitors=mocks or None,
                output_dir=out_dir,
            )
            path = res.get("metric_result_path")
            if not path or not os.path.exists(path):
                return {"success": False, "error": "test-dag produced no result"}
            with open(path, "rb") as f:
                mr = metric_result_pb2.MetricResult()
                mr.ParseFromString(f.read())
            return {
                "success": True,
                "metric_result_pb": MessageToDict(mr, preserving_proto_field_name=True),
                "logs": res.get("logs", []),
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # -- stateful ops ------------------------------------------------------
    def import_package(self, pkg_bytes: bytes) -> Dict[str, Any]:
        """Unpack a ``.hpkg``; stash scenario/map; return proto-shape dicts.

        Mirrors the worker's ``parseHpkg``: the archive layout is owned by
        ``humex.converters.hpkg``; we only decode the bytes and compute
        lane-boundary ``map_segments`` (opaque polylines to the TS side).
        """
        from humex.converters.hpkg import unpack_hpkg
        from humex.hmap.road_map_loader import RoadMapLoader

        c = unpack_hpkg(pkg_bytes)

        # Stash scenario.pb so a later evaluate/export reads it without a
        # re-upload; drop any stale scenario when this package has none.
        if c.scenario_pb is not None:
            with open(self._scenario_path, "wb") as f:
                f.write(c.scenario_pb)
        elif self._has_scenario():
            os.remove(self._scenario_path)
        if c.map_pb is not None:
            with open(self._map_path, "wb") as f:
                f.write(c.map_pb)

        map_segments: List[List[List[float]]] = []
        if c.map_pb is not None:
            try:
                road_map = RoadMapLoader.create_road_map(
                    self._map_path, map_name="hpkg_upload"
                )
                for seg in road_map.get_segments(centerline=False):
                    pts = []
                    for p in seg:
                        if isinstance(p, tuple):
                            pts.append([float(p[0]), float(p[1])])
                        else:
                            pts.append([float(p.x), float(p.y)])
                    map_segments.append(pts)
            except Exception as exc:  # noqa: BLE001 — non-fatal, log + continue
                print(f"humex serve: get_segments failed: {exc}")

        return {
            "manifest": c.manifest,
            "scenario_pb": _decode(c.scenario_pb, scenario_pb2.ScenarioData),
            "map_pb": _decode(c.map_pb, map_pb2.Map),
            "signal_pb": _decode(c.signal_pb, signal_pb2.SignalData),
            "metric_result_pb": _decode(
                c.metric_result_pb, metric_result_pb2.MetricResult
            ),
            "metric_config_yaml": c.metric_yaml,
            "config_json": c.config_json,
            "map_segments": map_segments,
        }

    def run_simulation(self, config_json: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate from an AVA config against the stashed map; promote the
        result to the scenario stash so Evaluate/Export use it next."""
        from humex.api.simulation_api import RunSimulationAPI

        if not self._has_map():
            return {
                "success": False,
                "error": 'No map loaded — use "Create from Map" before simulating.',
            }
        cfg_path = os.path.join(self._dir, "sim_config.json")
        with open(cfg_path, "w") as f:
            json.dump(config_json or {}, f)
        try:
            t0 = time.perf_counter()
            result = RunSimulationAPI().run(
                config_path=cfg_path,
                map_path=self._map_path,
                output_dir=os.path.join(self._dir, "sim_out"),
                output_name="sim",
            )
            shutil.copyfile(result["scenario_proto_path"], self._scenario_path)
            with open(self._scenario_path, "rb") as f:
                msg = scenario_pb2.ScenarioData()
                msg.ParseFromString(f.read())
            return {
                "success": True,
                "scenario_pb": MessageToDict(msg, preserving_proto_field_name=True),
                "simulation_time_seconds": result.get(
                    "simulation_time_seconds", time.perf_counter() - t0
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def evaluate_metrics(self, metric_yaml_content: str) -> Dict[str, Any]:
        """Evaluate a DAG against the stashed scenario+map."""
        from humex.api.metrics_api import ComputeDagMetricsAPI

        if not self._has_scenario() or not self._has_map():
            return {
                "success": False,
                "error": "scenario or map not loaded (import a package first)",
            }
        yaml_path = os.path.join(self._dir, "metric.yaml")
        with open(yaml_path, "w") as f:
            f.write(metric_yaml_content or "")
        try:
            result = ComputeDagMetricsAPI().compute(
                dag_yaml_path=yaml_path,
                scenario_file_path=self._scenario_path,
                map_file_path=self._map_path,
                save_metrics_result=False,
            )
            mr = result.get("metric_result") if isinstance(result, dict) else None
            metric_dict = (
                MessageToDict(mr, preserving_proto_field_name=True)
                if mr is not None
                else None
            )
            meta = result.get("evaluation_metadata", {}) if isinstance(result, dict) else {}
            return {
                "success": True,
                "metric_result_pb": metric_dict,
                "evaluation_metadata": meta,
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def build_hpkg(
        self,
        name: str,
        config_json: Optional[dict],
        metric_yaml: Optional[str],
        have_scenario: bool,
    ) -> bytes:
        """Pack a ``.hpkg`` from the stashed map (+ optional scenario/config/
        metric yaml). Raises if no map is loaded."""
        from humex.converters.hpkg import pack_hpkg

        if not self._has_map():
            raise RuntimeError(
                "No map is loaded — re-import a package before exporting."
            )
        with open(self._map_path, "rb") as f:
            map_pb = f.read()
        scenario_pb = None
        if have_scenario and self._has_scenario():
            with open(self._scenario_path, "rb") as f:
                scenario_pb = f.read()
        return pack_hpkg(
            name=name or "scenario",
            scenario_pb=scenario_pb,
            map_pb=map_pb,
            config_json=config_json,
            metric_yaml=metric_yaml,
            source="zeno",
        )
