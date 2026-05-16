"""humex Waymo Open Dataset converter.

Registers :class:`WaymoConverter` via the ``humex.converters`` entry-point
group declared in this package's ``pyproject.toml``. Don't import from
the core ``humex.converters`` module — the registry walks entry points,
not Python imports.
"""

from humex_converter_waymo.converter import WaymoConverter, WaymoConverterError

__version__ = "0.2.0"

__all__ = ["WaymoConverter", "WaymoConverterError"]
