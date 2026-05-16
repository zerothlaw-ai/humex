"""``humex lane-map`` — (re)build lane_map.pb + role.pb sidecars for a scenario."""

from pathlib import Path

import click
from rich.console import Console

from humex.hmap import build_lane_map, build_role_table
from humex.hmap.road_map_loader import RoadMapLoader
from humex.proto import lane_map_pb2, role_pb2

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
    """Build lane_map.pb and role.pb from <scenario_dir>/scenario.pb + map.pb.

    \b
    Example:
        humex lane-map converted/segment-1234 --force
    """
    map_pb_path = scenario_dir / "map.pb"
    scenario_pb_path = scenario_dir / "scenario.pb"
    if not map_pb_path.exists() or not scenario_pb_path.exists():
        console.print(f"[red]Both scenario.pb and map.pb must exist in {scenario_dir}[/red]")
        raise SystemExit(1)

    lane_map_out = scenario_dir / "lane_map.pb"
    role_out = scenario_dir / "role.pb"

    if (lane_map_out.exists() or role_out.exists()) and not force:
        console.print(f"[yellow]Existing sidecars present. Pass --force to overwrite.[/yellow]")
        raise SystemExit(1)

    console.print(f"[dim]Loading[/dim] {map_pb_path}")
    road_map = RoadMapLoader.create_road_map(str(map_pb_path), map_name=scenario_dir.name)

    console.print("[dim]Building lane map…[/dim]")
    lm = build_lane_map(road_map)
    with open(lane_map_out, "wb") as f:
        f.write(lm.to_proto().SerializeToString())
    console.print(f"[green]Wrote[/green] {lane_map_out}")

    console.print("[dim]Building role table…[/dim]")
    from humex.api import ScenarioAPI

    scenario = ScenarioAPI().load_from_proto_files(str(scenario_pb_path))
    rt = build_role_table(scenario, lm)
    with open(role_out, "wb") as f:
        f.write(rt.to_proto().SerializeToString())
    console.print(f"[green]Wrote[/green] {role_out}")
