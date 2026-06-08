"""``humex evaluate`` — run a metric DAG against a scenario directory."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("scenario_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--metric",
    "metric_yaml",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to a metric DAG YAML config.",
)
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to write metric_result.pb. Defaults to <scenario_dir>/results/.",
)
def evaluate(scenario_dir: Path, metric_yaml: Path, output_dir: Optional[Path]) -> None:
    """Compute a metric DAG over a converted scenario.

    SCENARIO_DIR must contain a scenario.pb (and optionally map.pb / lane_map.pb /
    role.pb sidecars — auto-discovered by ScenarioAPI).

    \b
    Example:
        humex evaluate converted/segment-1234 --metric configs/front_distance.yaml
    """
    from humex.api import ComputeDagMetricsAPI

    scenario_pb = scenario_dir / "scenario.pb"
    if not scenario_pb.exists():
        console.print(f"[red]Missing scenario.pb in {scenario_dir}[/red]")
        raise SystemExit(1)

    out = output_dir or scenario_dir / "results"
    out.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Loading[/dim] {scenario_dir}")
    console.print(f"[dim]Running DAG[/dim] {metric_yaml}")
    # ComputeDagMetricsAPI loads the scenario (+ map / signal / sidecars) from
    # the folder itself and evaluates the DAG directly. We write the result
    # ourselves, so leave save_metrics_result=False.
    result = ComputeDagMetricsAPI().compute(
        dag_yaml_path=str(metric_yaml),
        scenario_folder_path=str(scenario_dir),
    )
    result_pb = result["metric_result"]

    result_path = out / "metric_result.pb"
    with open(result_path, "wb") as f:
        f.write(result_pb.SerializeToString())
    console.print(f"[green]Wrote[/green] {result_path}")
