"""Convert commands for transforming raw data to humex format."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

CONVERTED_DIR = Path("converted")


def _find_tfrecords(directory: Path) -> list[Path]:
    """Find all TFRecord files in a directory."""
    return sorted([f for f in directory.iterdir() if f.is_file() and ".tfrecord" in f.name.lower()])


def _find_parquets(directory: Path) -> list[Path]:
    """Find all .parquet files in a directory tree.

    Walks recursively because DROID-100 ships in chunked layout
    (data/chunk-NNN/file-NNN.parquet) and we want `hume convert <root>`
    to discover everything under it. Skips hidden dirs (e.g. .cache).
    """
    matches: list[Path] = []
    for f in directory.rglob("*.parquet"):
        if any(p.startswith(".") for p in f.relative_to(directory).parts):
            continue
        if f.is_file():
            matches.append(f)
    return sorted(matches)


def _find_lafan_csvs(directory: Path) -> list[Path]:
    """Find LAFAN1-shaped CSVs in a directory tree (recursive, skip hidden)."""
    from humex.converters.lafan import is_lafan_csv

    matches: list[Path] = []
    for f in directory.rglob("*.csv"):
        if any(p.startswith(".") for p in f.relative_to(directory).parts):
            continue
        if f.is_file() and is_lafan_csv(f):
            matches.append(f)
    return sorted(matches)


def _is_tfrecord(path: Path) -> bool:
    return path.is_file() and ".tfrecord" in path.name.lower()


def _is_parquet(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".parquet"


def _is_lafan_csv(path: Path) -> bool:
    from humex.converters.lafan import is_lafan_csv

    return path.is_file() and is_lafan_csv(path)


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for converted files. Defaults to ./converted/.",
)
@click.option(
    "--ego-id",
    type=int,
    default=None,
    help="[Waymo] ID of the ego vehicle. If unset, uses default selection.",
)
@click.option(
    "--episode",
    type=int,
    default=None,
    help="[DROID] Convert only this episode_index. If unset, converts every episode in the parquet.",
)
@click.option(
    "--hpkg",
    "produce_hpkg",
    is_flag=True,
    default=False,
    help="Also write a .hpkg package alongside each converted scenario (uploadable in zeno).",
)
def convert(
    path: Path,
    output_dir: Optional[Path],
    ego_id: Optional[int],
    episode: Optional[int],
    produce_hpkg: bool,
) -> None:
    """Convert a raw dataset file (or directory) to humex format.

    Auto-detects the source by file extension:

    \b
      .tfrecord  -> Waymo Open Dataset
      .parquet   -> DROID-100 (lerobot/droid_100)
      .csv (26 cols, no header) -> LAFAN1 retargeted Unitree H1

    PATH can be a single file or a directory containing supported files.
    For a directory, every supported file is processed; you'll be prompted first.

    \b
    Examples:
        hume convert scenario1.tfrecord
        hume convert ../waymo_raw_data/
        hume convert file-000.parquet                # all episodes
        hume convert file-000.parquet --episode 0    # one episode
        hume convert file-000.parquet --episode 0 --hpkg   # also produce .hpkg
        hume convert h1/walk1_subject1.csv --hpkg          # one H1 motion
        hume convert ../lafan_raw_data/h1/                 # every H1 motion
    """
    out = output_dir or CONVERTED_DIR

    if path.is_file():
        if _is_tfrecord(path):
            _convert_one_waymo(path, out, ego_id, produce_hpkg=produce_hpkg)
            return
        if _is_parquet(path):
            _convert_one_droid(path, out, episode, produce_hpkg=produce_hpkg)
            return
        if _is_lafan_csv(path):
            _convert_one_lafan(path, out, produce_hpkg=produce_hpkg)
            return
        console.print(
            f"[red]Unsupported file:[/red] {path.name}\n"
            "Expected .tfrecord (Waymo), .parquet (DROID), or .csv (LAFAN1)."
        )
        raise SystemExit(1)

    tfrecords = _find_tfrecords(path)
    parquets = _find_parquets(path)
    lafan_csvs = _find_lafan_csvs(path)

    if not tfrecords and not parquets and not lafan_csvs:
        console.print(f"[yellow]No supported dataset files found in {path}[/yellow]")
        return

    if tfrecords:
        console.print(f"\nFound [bold]{len(tfrecords)}[/bold] Waymo scenario(s) in {path}:\n")
        for f in tfrecords:
            console.print(f"  [dim]-[/dim] {f.name}")
    if parquets:
        console.print(f"\nFound [bold]{len(parquets)}[/bold] DROID parquet(s) in {path}:\n")
        for f in parquets:
            console.print(f"  [dim]-[/dim] {f.name}")
    if lafan_csvs:
        console.print(f"\nFound [bold]{len(lafan_csvs)}[/bold] LAFAN1 CSV(s) in {path}:\n")
        for f in lafan_csvs:
            console.print(f"  [dim]-[/dim] {f.name}")
    console.print()

    if not click.confirm("Convert all?"):
        console.print("[dim]Aborted.[/dim]")
        return

    succeeded = 0
    failed = 0

    for tfrecord in tfrecords:
        console.print(f"\n[bold]{tfrecord.name}[/bold]")
        try:
            _convert_one_waymo(tfrecord, out, ego_id, summary=True, produce_hpkg=produce_hpkg)
            succeeded += 1
        except SystemExit:
            failed += 1

    for parquet in parquets:
        console.print(f"\n[bold]{parquet.name}[/bold]")
        try:
            _convert_one_droid(parquet, out, episode, summary=True, produce_hpkg=produce_hpkg)
            succeeded += 1
        except SystemExit:
            failed += 1

    for csv in lafan_csvs:
        console.print(f"\n[bold]{csv.name}[/bold]")
        try:
            _convert_one_lafan(csv, out, summary=True, produce_hpkg=produce_hpkg)
            succeeded += 1
        except SystemExit:
            failed += 1

    console.print(f"\n[bold]Results:[/bold] {succeeded} converted, {failed} failed")


def _convert_one_waymo(
    path: Path,
    out: Path,
    ego_id: Optional[int],
    summary: bool = False,
    produce_hpkg: bool = False,
) -> None:
    from humex.converters.waymo import WaymoConverter, WaymoConverterError
    from humex.converters.hpkg_packager import (
        load_meta_for_manifest,
        package_as_hpkg,
    )

    if not summary:
        console.print(f"[dim]Input:[/dim] {path}")
    try:
        converter = WaymoConverter(path)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Converting...", total=None)
            result = converter.convert(output_dir=out, ego_id=ego_id)
        episode_dir = result.scenario_path.parent
        if produce_hpkg:
            hpkg_path = episode_dir.parent / f"{episode_dir.name}.hpkg"
            package_as_hpkg(
                episode_dir,
                hpkg_path,
                name=episode_dir.name,
                source={"converter": "waymo", "input_file": path.name},
                scenario_metadata=load_meta_for_manifest(episode_dir),
            )
            console.print(f"  [cyan]hpkg[/cyan] → {hpkg_path}")
        prefix = "  [green]Done[/green]" if summary else "\n[green]Conversion complete![/green]"
        console.print(f"{prefix} → {episode_dir}")
    except (WaymoConverterError, FileNotFoundError, ValueError) as e:
        prefix = "  [red]Failed:[/red]" if summary else "[red]Error:[/red]"
        console.print(f"{prefix} {e}")
        raise SystemExit(1)


def _convert_one_lafan(
    path: Path,
    out: Path,
    summary: bool = False,
    produce_hpkg: bool = False,
) -> None:
    from humex.converters.lafan import LafanConverter, LafanConverterError
    from humex.converters.hpkg_packager import (
        load_meta_for_manifest,
        package_as_hpkg,
    )

    if not summary:
        console.print(f"[dim]Input:[/dim] {path}")
    try:
        converter = LafanConverter(path)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Converting...", total=None)
            result = converter.convert(output_dir=out)
        episode_dir = result.scenario_path.parent
        if produce_hpkg:
            hpkg_path = episode_dir.parent / f"{episode_dir.name}.hpkg"
            package_as_hpkg(
                episode_dir,
                hpkg_path,
                name=episode_dir.name,
                source={"converter": "lafan", "input_file": path.name},
                scenario_metadata=load_meta_for_manifest(episode_dir),
            )
            console.print(f"  [cyan]hpkg[/cyan] → {hpkg_path}")
        prefix = "  [green]Done[/green]" if summary else "\n[green]Conversion complete![/green]"
        console.print(f"{prefix} → {episode_dir}")
    except (LafanConverterError, FileNotFoundError, ValueError) as e:
        prefix = "  [red]Failed:[/red]" if summary else "[red]Error:[/red]"
        console.print(f"{prefix} {e}")
        raise SystemExit(1)


def _convert_one_droid(
    path: Path,
    out: Path,
    episode: Optional[int],
    summary: bool = False,
    produce_hpkg: bool = False,
) -> None:
    from humex.converters.droid import DroidConverter, DroidConverterError
    from humex.converters.hpkg_packager import (
        load_meta_for_manifest,
        package_as_hpkg,
    )

    if not summary:
        ep_label = f"episode {episode}" if episode is not None else "all episodes"
        console.print(f"[dim]Input:[/dim] {path}  [dim]({ep_label})[/dim]")
    try:
        converter = DroidConverter(path)
        # When packaging into hpkg, we need to know which episodes were touched
        # (one or many) to package each separately. Derive that here so the
        # batch case still produces one .hpkg per episode.
        if produce_hpkg:
            from humex.converters.droid import DroidConverter as _DC  # noqa: F401
            episodes = (
                [episode]
                if episode is not None
                else converter._list_episode_indices()
            )
        else:
            episodes = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Converting...", total=None)
            result = converter.convert(output_dir=out, episode=episode)
        if produce_hpkg:
            source_stem = path.stem  # mirrors DroidConverter._convert_one_episode
            for ep in episodes:
                ep_dir = Path(out) / source_stem / f"episode_{ep:04d}"
                hpkg_path = ep_dir.parent / f"{ep_dir.name}.hpkg"
                package_as_hpkg(
                    ep_dir,
                    hpkg_path,
                    name=ep_dir.name,
                    source={
                        "converter": "droid",
                        "input_file": path.name,
                        "episode_index": ep,
                    },
                    scenario_metadata=load_meta_for_manifest(ep_dir),
                )
                console.print(f"  [cyan]hpkg[/cyan] → {hpkg_path}")
        prefix = "  [green]Done[/green]" if summary else "\n[green]Conversion complete![/green]"
        # `result.scenario_path` points at the last episode written. Surface the
        # source-file root (parent's parent) so batch runs print the dir containing
        # every episode_NNNN/ subfolder.
        target = result.scenario_path.parent if episode is not None else result.scenario_path.parent.parent
        console.print(f"{prefix} → {target}")
    except (DroidConverterError, FileNotFoundError, ValueError) as e:
        prefix = "  [red]Failed:[/red]" if summary else "[red]Error:[/red]"
        console.print(f"{prefix} {e}")
        raise SystemExit(1)
