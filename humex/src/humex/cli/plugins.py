"""``humex plugins`` — show installed converter plugins.

Walks :mod:`humex.converters.registry` and queries
:mod:`importlib.metadata` for the package each plugin lives in. Useful
for verifying that a `pip install humex-converter-foo` actually wired
the entry point correctly.
"""

from importlib.metadata import distributions

import click
from rich.console import Console
from rich.table import Table

from humex import __api_version__, __version__
from humex.converters.registry import ENTRY_POINT_GROUP, converters

console = Console()


def _package_for_entry_point(group: str, ep_name: str) -> tuple[str, str]:
    """Return ``(distribution name, version)`` for the entry point.

    Falls back to ``("?", "?")`` when the metadata can't be matched —
    rare in practice but possible with editable installs in weird shapes.
    """
    for dist in distributions():
        try:
            eps = dist.entry_points
        except Exception:
            continue
        for ep in eps:
            if ep.group == group and ep.name == ep_name:
                return dist.name or "?", dist.version or "?"
    return "?", "?"


@click.command(name="plugins")
def plugins() -> None:
    """Show every installed converter plugin (and its source package)."""
    console.print(
        f"\n[bold]humex[/bold] {__version__}  "
        f"[dim](API v{__api_version__})[/dim]\n"
    )

    found = converters()
    if not found:
        console.print(
            "[yellow]No converter plugins installed.[/yellow]\n\n"
            "Install one or more:\n"
            "  pip install humex-converter-waymo\n"
            "  pip install humex-converter-droid\n"
            "  pip install humex-converter-lafan\n"
            "Or all at once: [bold]pip install humex\\[all][/bold]\n"
        )
        return

    table = Table(title=f"Installed converters (group: {ENTRY_POINT_GROUP})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Class")
    table.add_column("Package")
    table.add_column("Version")
    table.add_column("Extensions")

    for ep_name in sorted(found):
        cls = found[ep_name]
        pkg, ver = _package_for_entry_point(ENTRY_POINT_GROUP, ep_name)
        exts = ", ".join(cls.EXTENSIONS) if cls.EXTENSIONS else "[dim](custom)[/dim]"
        table.add_row(
            ep_name,
            f"{cls.__module__}.{cls.__name__}",
            pkg,
            ver,
            exts,
        )
    console.print(table)
    console.print()
