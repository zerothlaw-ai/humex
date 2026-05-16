"""Entry-point–based discovery of converter plugins.

Third-party converters live in their own pip packages and register
themselves by declaring a ``humex.converters`` entry point in their
``pyproject.toml``::

    [project.entry-points."humex.converters"]
    waymo = "humex_converter_waymo.converter:WaymoConverter"

At runtime humex enumerates that entry-point group via
:func:`importlib.metadata.entry_points` and builds a name → class map.
The CLI's ``humex convert`` walks the map to find a converter that
recognizes the input file (via :meth:`BaseConverter.can_handle`).

The lookup is cached for the lifetime of the process; call
:func:`refresh` after pip-installing a new plugin in the same Python
session (rare; tests).
"""

from __future__ import annotations

import logging
import warnings
from functools import lru_cache
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Optional

from humex import __api_version__
from humex.converters.base import BaseConverter

logger = logging.getLogger(__name__)

#: The entry-point group plugins declare themselves under. Keep in sync
#: with the docs / cookiecutter / plugin pyproject examples.
ENTRY_POINT_GROUP = "humex.converters"


@lru_cache(maxsize=1)
def converters() -> dict[str, type[BaseConverter]]:
    """Return every installed converter plugin keyed by entry-point name.

    Plugins that fail to import, that aren't a :class:`BaseConverter`
    subclass, or that declare a higher ``MIN_HUMEX_API_VERSION`` than the
    installed humex are skipped with a warning rather than raising —
    one broken plugin shouldn't take down `humex convert` for the rest.
    """
    found: dict[str, type[BaseConverter]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        cls = _load_one(ep)
        if cls is not None:
            found[ep.name] = cls
    return found


def pick(path: Path) -> Optional[type[BaseConverter]]:
    """Return the first installed converter that claims ``path``, or None.

    Resolution order is *insertion order* of the entry-point group, which
    matches the order packages got installed. Conflicting handlers are
    rare in practice — if they happen, the user can disambiguate by
    naming the converter explicitly on the CLI.
    """
    p = Path(path)
    for cls in converters().values():
        try:
            if cls.can_handle(p):
                return cls
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(
                "Converter %s raised in can_handle(%s): %s",
                cls.__name__, p, e,
            )
    return None


def refresh() -> None:
    """Drop the cached lookup. Call after installing a plugin in-process."""
    converters.cache_clear()


def _load_one(ep: EntryPoint) -> Optional[type[BaseConverter]]:
    try:
        cls = ep.load()
    except Exception as e:
        warnings.warn(
            f"humex: skipping converter plugin {ep.name!r} — "
            f"failed to import ({type(e).__name__}: {e})",
            stacklevel=2,
        )
        return None

    if not isinstance(cls, type) or not issubclass(cls, BaseConverter):
        warnings.warn(
            f"humex: skipping converter plugin {ep.name!r} — "
            f"{ep.value!r} is not a BaseConverter subclass",
            stacklevel=2,
        )
        return None

    min_api = getattr(cls, "MIN_HUMEX_API_VERSION", 1)
    if min_api > __api_version__:
        warnings.warn(
            f"humex: skipping converter plugin {ep.name!r} — "
            f"requires humex API >= {min_api}, current is {__api_version__}",
            stacklevel=2,
        )
        return None

    return cls
