"""Tests for the .hpkg archive format (humex.converters.hpkg)."""

import io
import json
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.converters.hpkg import (  # noqa: E402
    extract_hpkg,
    pack_hpkg,
    unpack_hpkg,
)
from humex.converters.hpkg_packager import package_as_hpkg  # noqa: E402


def test_pack_unpack_full_round_trip():
    data = pack_hpkg(
        name="demo",
        scenario_pb=b"SCN",
        map_pb=b"MAP",
        metric_yaml="description: x\nnodes: {}\n",
        config_json={"vehicles": [1, 2]},
        metric_result_pb=b"RES",
    )
    c = unpack_hpkg(data)
    assert c.scenario_pb == b"SCN"
    assert c.map_pb == b"MAP"
    assert c.metric_result_pb == b"RES"
    assert c.metric_yaml.startswith("description")
    assert c.config_json == {"vehicles": [1, 2]}
    assert c.manifest["contents"] == {
        "scenario_data": True,
        "map_data": True,
        "metric_result": True,
        "metric_config": True,
        "scenario_config": True,
        "signal_data": False,
        "robot_data": False,
    }


def test_pack_map_only():
    c = unpack_hpkg(pack_hpkg(name="maponly", map_pb=b"MAP"))
    assert c.scenario_pb is None
    assert c.map_pb == b"MAP"
    assert c.manifest["contents"]["scenario_data"] is False
    assert c.manifest["contents"]["map_data"] is True


def test_unpack_legacy_flat_and_alt_names():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("scenario.pb", b"S2")  # flat (no scenario/ prefix)
        zf.writestr("map.pb", b"M2")
        zf.writestr("metrics/metric_result.pb", b"R2")  # alt name
        zf.writestr("metrics/config.yaml", "yaml: 1")  # alt name
        zf.writestr("config.json", json.dumps({"a": 1}))
        zf.writestr("manifest.json", json.dumps({"name": "legacy"}))
    c = unpack_hpkg(buf.getvalue())
    assert c.scenario_pb == b"S2"
    assert c.map_pb == b"M2"
    assert c.metric_result_pb == b"R2"
    assert c.metric_yaml == "yaml: 1"
    assert c.config_json == {"a": 1}


def test_extract_hpkg_paths(tmp_path):
    data = pack_hpkg(name="demo", scenario_pb=b"SCN", map_pb=b"MAP", metric_yaml="y: 1")
    ex = extract_hpkg(data, tmp_path / "out")
    assert Path(ex.scenario_pb).read_bytes() == b"SCN"
    assert Path(ex.map_pb).read_bytes() == b"MAP"
    assert ex.scenario_dir and Path(ex.scenario_dir).is_dir()
    assert ex.metric_yaml and Path(ex.metric_yaml).exists()


def test_extract_hpkg_from_path(tmp_path):
    src = tmp_path / "demo.hpkg"
    src.write_bytes(pack_hpkg(name="demo", scenario_pb=b"S", map_pb=b"M"))
    ex = extract_hpkg(src, tmp_path / "out")
    assert Path(ex.scenario_pb).read_bytes() == b"S"


def test_package_as_hpkg_is_unpackable(tmp_path):
    ep = tmp_path / "ep"
    ep.mkdir()
    (ep / "scenario.pb").write_bytes(b"S")
    (ep / "map.pb").write_bytes(b"M")
    out = package_as_hpkg(ep, tmp_path / "ep.hpkg", name="ep", source={"converter": "t"})
    c = unpack_hpkg(Path(out).read_bytes())
    assert c.scenario_pb == b"S"
    assert c.map_pb == b"M"
    assert c.manifest["contents"]["scenario_data"] is True
    assert c.manifest["source"] == {"converter": "t"}
