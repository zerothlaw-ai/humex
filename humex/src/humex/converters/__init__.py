"""Converter plugin host.

The core ``humex`` package no longer ships built-in converters. Each
format (Waymo, DROID, LAFAN, …) lives in its own pip package and
registers via the ``humex.converters`` entry-point group; see
:mod:`humex.converters.registry`.

What stays here:

- :class:`BaseConverter` — the contract every plugin subclasses.
- :class:`ConversionResult` — return type from ``convert()``.
- :mod:`humex.converters.registry` — entry-point discovery.
- :mod:`humex.converters.hpkg` — the ``.hpkg`` archive format: pack/unpack/extract.
- :mod:`humex.converters.hpkg_packager` — directory packager used by the CLI.
"""

from humex.converters.base import BaseConverter, ConversionResult
from humex.converters.hpkg import (
    HpkgContents,
    HpkgExtract,
    extract_hpkg,
    pack_hpkg,
    unpack_hpkg,
)

__all__ = [
    "BaseConverter",
    "ConversionResult",
    "HpkgContents",
    "HpkgExtract",
    "extract_hpkg",
    "pack_hpkg",
    "unpack_hpkg",
]
