"""Reusable pytest contract for converter plugins.

A converter plugin should pass this contract to guarantee it composes
correctly with the humex CLI and downstream metrics pipeline. Subclass
:class:`ConverterContract` in the plugin's ``tests/`` directory, point
the class attrs at a small fixture file, and pytest does the rest::

    # converters/waymo/tests/test_contract.py
    from humex.converters.testing import ConverterContract
    from humex_converter_waymo import WaymoConverter
    from pathlib import Path

    class TestWaymoContract(ConverterContract):
        converter_cls = WaymoConverter
        fixture_path = Path(__file__).parent / "fixtures" / "small.tfrecord"
        # Optional knobs forwarded to convert():
        convert_kwargs = {"ego_id": None}

The contract checks:

- The converter is registered under the right entry-point group.
- ``can_handle`` returns True for the fixture and False for an unrelated
  temp file.
- ``convert(output_dir)`` returns a :class:`ConversionResult` with at
  least ``scenario_path`` and ``map_path`` pointing at real files.
- The produced ``scenario.pb`` deserializes as
  :class:`humex.proto.scenario_pb2.ScenarioData`.

Plugins that need stricter checks (e.g. shape of a robot.pb, presence of
a signal.pb) override the relevant ``test_…`` method or add their own.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, ClassVar

import pytest

from humex.converters.base import BaseConverter, ConversionResult
from humex.converters.registry import ENTRY_POINT_GROUP, converters


class ConverterContract:
    """Subclass and set ``converter_cls`` + ``fixture_path`` to use."""

    #: The converter class under test. Must subclass BaseConverter.
    converter_cls: ClassVar[type[BaseConverter]]

    #: Path to a small valid fixture file the converter should handle.
    fixture_path: ClassVar[Path]

    #: Extra kwargs forwarded to ``convert()`` (per-converter knobs).
    convert_kwargs: ClassVar[dict[str, Any]] = {}

    # ── checks ─────────────────────────────────────────────────────────

    def test_registered_via_entry_point(self) -> None:
        """The converter must be discoverable through the registry —
        otherwise it won't show up under `humex convert` no matter how
        well the rest works."""
        installed = converters()
        assert self.converter_cls in installed.values(), (
            f"{self.converter_cls.__name__} is not registered under the "
            f"{ENTRY_POINT_GROUP!r} entry-point group. Check the "
            "`[project.entry-points.\"humex.converters\"]` table in "
            "this plugin's pyproject.toml."
        )

    def test_can_handle_fixture(self) -> None:
        assert self.fixture_path.exists(), (
            f"Fixture not found: {self.fixture_path}"
        )
        assert self.converter_cls.can_handle(self.fixture_path), (
            f"{self.converter_cls.__name__}.can_handle returned False for "
            f"its own fixture {self.fixture_path.name!r}."
        )

    def test_rejects_unrelated_file(self) -> None:
        """A converter must NOT claim files it can't actually handle —
        otherwise CLI dispatch routes the wrong format to it."""
        with tempfile.NamedTemporaryFile(suffix=".unrelated_xyz") as tmp:
            assert not self.converter_cls.can_handle(Path(tmp.name)), (
                f"{self.converter_cls.__name__}.can_handle returned True "
                "for an unrelated .unrelated_xyz file. Tighten the check."
            )

    def test_convert_produces_pb_files(self, tmp_path: Path) -> None:
        converter = self.converter_cls(self.fixture_path)
        result = converter.convert(output_dir=tmp_path, **self.convert_kwargs)
        assert isinstance(result, ConversionResult), (
            f"convert() returned {type(result).__name__}, not ConversionResult"
        )
        assert result.scenario_path is not None and result.scenario_path.is_file(), (
            f"convert() didn't write scenario.pb (got {result.scenario_path!r})"
        )
        assert result.map_path is not None and result.map_path.is_file(), (
            f"convert() didn't write map.pb (got {result.map_path!r})"
        )

    def test_scenario_pb_deserializes(self, tmp_path: Path) -> None:
        """The produced ScenarioData proto must be parseable by humex.proto.

        Catches format-version drift: if the plugin emits an older proto
        shape, monitors downstream will silently misread fields.
        """
        try:
            from humex.proto import scenario_pb2
        except ImportError:
            pytest.skip("humex.proto.scenario_pb2 unavailable in test env")
        converter = self.converter_cls(self.fixture_path)
        result = converter.convert(output_dir=tmp_path, **self.convert_kwargs)
        pb = scenario_pb2.ScenarioData()
        pb.ParseFromString(result.scenario_path.read_bytes())
        # Frames need timestamps; a converter that emits an empty proto
        # is almost certainly broken.
        assert len(pb.frames) > 0, "ScenarioData has zero frames"
