"""``humex evaluate`` — run a metric DAG against a scenario directory."""
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
console = Console()


@click.command()
@click.argument("scenario_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--metric", "metric_yaml", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True, help="Path to a metric DAG YAML config.")
@click.option("-o", "--output", "output_dir", type=click.Path(path_type=Path), default=None, help="Where to write metric_result.pb.")
def evaluate(scenario_dir: Path, metric_yaml: Path, output_dir: Optional[Path]) -> None:
    """Compute a metric DAG over a converted scenario."""
    from humex.api.metrics_api import ComputeDagMetricsAPI
    out = output_dir or scenario_dir / "results"
    out.mkdir(parents=True, exist_ok=True)
    compute = ComputeDagMetricsAPI()
    results = compute.compute(dag_yaml_path=str(metric_yaml), scenario_folder_path=str(scenario_dir), save_metrics_result=True)
    result_path = out / "metric_result.pb"
    with open(result_path, "wb") as f:
        f.write(results["metric_result"].SerializeToString())
    meta = results.get("evaluation_metadata", {})
    console.print(f"[green]Wrote[/green] {result_path}")
    console.print(f"[bold]Final Result:[/bold] {results['metric_result'].final_result}")
    console.print(f"[bold]Nodes:[/bold] {meta.get('nodes_evaluated')}/{meta.get('total_nodes')}")
