"""``humex package`` — wrap a converted scenario directory into an .hpkg tarball."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from humex.converters.hpkg_packager import load_meta_for_manifest, package_as_hpkg

console = Console()


@click.command()
@click.argument("scenario_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output .hpkg path. Defaults to <scenario_dir>.hpkg next to the source.",
)
def package(scenario_dir: Path, output_path: Optional[Path]) -> None:
    """Package a scenario directory as a portable .hpkg tarball.

    The directory must contain at minimum scenario.pb + map.pb + meta.json. lane_map.pb
    and role.pb sidecars are included if present.

    \b
    Example:
        humex package converted/segment-1234
        humex package converted/segment-1234 -o out/segment-1234.hpkg
    """
    target = output_path or scenario_dir.parent / f"{scenario_dir.name}.hpkg"
    target.parent.mkdir(parents=True, exist_ok=True)

    package_as_hpkg(
        scenario_dir,
        target,
        name=scenario_dir.name,
        source={"converter": "humex.cli.package"},
        scenario_metadata=load_meta_for_manifest(scenario_dir),
    )
    console.print(f"[green]Wrote[/green] {target}")
