"""``humex lane-map`` — re-run only the sidecar stages on an already-converted scenario.

``humex convert <input>`` runs enhance + lane_map + role inline. This
command is the back door for re-running just lane_map + role over an
existing ``<scenario_dir>``, useful when iterating on the lane_map / role
algorithm without re-extracting the source data.
"""

from pathlib import Path

import click
from rich.console import Console

from humex.convert import run_sidecars_only

console = Console()


@click.command()
@click.argument("scenario_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing lane_map.pb / role.pb if they already exist.",
)
def lane_map(scenario_dir: Path, force: bool) -> None:
    """Re-build lane_map.pb + role.pb sidecars for an extracted scenario.

    SCENARIO_DIR must contain scenario.pb and map.pb (produced by an earlier
    ``humex convert`` run).

    \b
    Example:
        humex lane-map converted/segment-1234 --force
    """
    result = run_sidecars_only(scenario_dir, force=force)
    for line in result.summary_lines():
        tag = "[green]OK[/green]" if line.startswith("OK") else "[yellow]FAIL[/yellow]"
        console.print(f"  {tag} {line.split(maxsplit=1)[1]}")
    if not result.lane_map_ok or not result.role_ok:
        raise SystemExit(1)
