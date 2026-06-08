"""``humex convert`` — format-agnostic dispatch to installed converter plugins.

The CLI no longer knows about Waymo, DROID, LAFAN, or any specific format.
It walks :mod:`humex.converters.registry` to find converter plugins
(installed as separate pip packages, registered via the
``humex.converters`` entry-point group) and asks each one whether it
:meth:`~humex.converters.base.BaseConverter.can_handle` the input.

Per-converter knobs (Waymo's ``ego_id``, DROID's ``episode``, …) pass
through as ``-O key=value`` options that are forwarded to the
converter's ``.convert(**kwargs)``. New converters work without changes
here — the CLI is generic.
"""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from humex.converters.base import BaseConverter
from humex.converters.registry import converters as installed_converters
from humex.converters.registry import pick as pick_converter

console = Console()

CONVERTED_DIR = Path("converted")


def _parse_options(raw: tuple[str, ...]) -> dict[str, object]:
    """Parse ``-O key=value`` repeats into a kwargs dict.

    Tries int / float coercion; falls back to string. ``true``/``false``
    map to bools. Unknown keys are passed through — the converter is
    responsible for ignoring or validating them.
    """
    out: dict[str, object] = {}
    for entry in raw:
        if "=" not in entry:
            raise click.BadParameter(
                f"-O expects key=value, got {entry!r}", param_hint="-O / --opt"
            )
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        # Type coercion in order: bool, int, float, string.
        if value.lower() in ("true", "false"):
            out[key] = value.lower() == "true"
            continue
        try:
            out[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            out[key] = float(value)
            continue
        except ValueError:
            pass
        out[key] = value
    return out


def _discover_files(directory: Path) -> dict[type[BaseConverter], list[Path]]:
    """Walk ``directory`` and group files by the converter that claims them.

    Each converter's ``can_handle`` may be expensive (e.g. parquet column
    sniffing), so we ask each candidate per file only once.
    """
    by_converter: dict[type[BaseConverter], list[Path]] = {}
    available = list(installed_converters().values())
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        # Skip hidden directories (`.cache/`, `.git/`, …).
        if any(p.startswith(".") for p in path.relative_to(directory).parts):
            continue
        for cls in available:
            try:
                if cls.can_handle(path):
                    by_converter.setdefault(cls, []).append(path)
                    break
            except Exception:
                # A flaky can_handle on one converter shouldn't block discovery
                # for siblings; surface but keep walking.
                continue
    return by_converter


def _run_one(
    path: Path,
    out: Path,
    cls: type[BaseConverter],
    options: dict[str, object],
    skip_pack: bool,
    summary: bool,
    skip_pipeline: bool = False,
) -> bool:
    """Convert a single file end-to-end. Returns True on success.

    Runs the plugin extraction (stage 1), then enhance → lane_map → role
    (stages 2–4) via :func:`humex.convert.run_pipeline`, then packages the
    resulting directory into a ``<name>.hpkg`` archive next to it. Stages
    2–4 are best-effort: per-stage failures are printed but don't fail the
    command overall, mirroring hume's stage-2 semantics.

    Pass ``skip_pipeline=True`` (CLI ``--raw``) to leave the plugin's output
    untouched. Pass ``skip_pack=True`` (CLI ``--no-pack``) to skip the
    ``.hpkg`` packaging step and keep only the unpacked directory.
    """
    from humex.converters.hpkg_packager import load_meta_for_manifest, package_as_hpkg
    from humex.convert import run_pipeline

    if not summary:
        console.print(f"[dim]Input:[/dim] {path}  [dim]→ {cls.__name__}[/dim]")
    try:
        converter = cls(path)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Extracting...", total=None)
            result = converter.convert(output_dir=out, **options)
        episode_dir = result.scenario_path.parent if result.scenario_path else None

        # Stages 2-4: enhance + lane_map + role.
        if episode_dir is not None and not skip_pipeline:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Enhancing + building sidecars...", total=None)
                pipeline_result = run_pipeline(episode_dir, force=True)
            for line in pipeline_result.summary_lines():
                tag = "[green]OK[/green]" if line.startswith("OK") else "[yellow]FAIL[/yellow]"
                console.print(f"  {tag} {line.split(maxsplit=1)[1]}")

        # Default: pack the result into a portable .hpkg file. Disabled
        # by --no-pack or --raw (raw output isn't worth packaging).
        hpkg_path: Optional[Path] = None
        if episode_dir is not None and not skip_pack and not skip_pipeline:
            hpkg_path = episode_dir.parent / f"{episode_dir.name}.hpkg"
            package_as_hpkg(
                episode_dir,
                hpkg_path,
                name=episode_dir.name,
                source={"converter": converter.name, "input_file": path.name},
                scenario_metadata=load_meta_for_manifest(episode_dir),
            )
            console.print(f"  [cyan].hpkg[/cyan] → {hpkg_path}")

        prefix = (
            "  [green]Done[/green]"
            if summary
            else "\n[green]Conversion complete![/green]"
        )
        console.print(f"{prefix} → {hpkg_path or episode_dir or out}")
        return True
    except (FileNotFoundError, ValueError) as e:
        prefix = "  [red]Failed:[/red]" if summary else "[red]Error:[/red]"
        console.print(f"{prefix} {e}")
        return False
    except Exception as e:
        prefix = "  [red]Failed:[/red]" if summary else "[red]Error:[/red]"
        console.print(f"{prefix} {type(e).__name__}: {e}")
        return False


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
    "-O",
    "--opt",
    "options_raw",
    multiple=True,
    metavar="KEY=VALUE",
    help=(
        "Converter-specific option, e.g. `-O ego_id=1` (Waymo), "
        "`-O episode=0` (DROID). Repeat for multiple. Unknown keys are "
        "ignored by the converter."
    ),
)
@click.option(
    "--converter",
    "converter_name",
    default=None,
    help=(
        "Pin to a specific converter by entry-point name (e.g. `waymo`, "
        "`droid`, `lafan`). Bypasses `can_handle` detection. Useful when "
        "multiple installed plugins claim the same extension."
    ),
)
@click.option(
    "--no-pack",
    "skip_pack",
    is_flag=True,
    default=False,
    help=(
        "Skip packaging the result into a .hpkg archive — leave only the "
        "unpacked output directory. By default each converted scenario is "
        "packaged into a <name>.hpkg file next to the directory."
    ),
)
@click.option(
    "--raw",
    "skip_pipeline",
    is_flag=True,
    default=False,
    help=(
        "Skip post-extraction processing (enhance / lane_map / role) AND "
        ".hpkg packaging. Outputs only what the converter plugin produced. "
        "Useful for debugging plugin output or doing your own post-processing."
    ),
)
def convert(
    path: Path,
    output_dir: Optional[Path],
    options_raw: tuple[str, ...],
    converter_name: Optional[str],
    skip_pack: bool,
    skip_pipeline: bool,
) -> None:
    """Convert a raw dataset file (or directory) to humex format.

    The set of supported formats depends on which converter plugins are
    installed. Run `humex plugins` to list them.

    \b
    Examples:
        humex convert scenario1.tfrecord
        humex convert file-000.parquet -O episode=0
        humex convert h1/walk1_subject1.csv --no-pack
        humex convert ../waymo_raw_data/
        humex convert foo.tfrecord --converter waymo -O ego_id=42

    \b
    Install converter plugins:
        pip install humex-converter-waymo
        pip install humex-converter-droid
        pip install humex-converter-lafan
        pip install humex[all]                # all of the above
    """
    out = output_dir or CONVERTED_DIR
    options = _parse_options(options_raw)
    available = installed_converters()

    if not available:
        console.print(
            "[red]No converter plugins installed.[/red]\n"
            "Install one or more:\n"
            "  pip install humex-converter-waymo\n"
            "  pip install humex-converter-droid\n"
            "  pip install humex-converter-lafan\n"
            "Or install all at once: [bold]pip install humex\\[all][/bold]"
        )
        raise SystemExit(1)

    # Explicit --converter pin overrides extension/header detection.
    if converter_name:
        cls = available.get(converter_name)
        if cls is None:
            console.print(
                f"[red]Unknown converter:[/red] {converter_name}\n"
                f"Installed: {', '.join(sorted(available)) or '(none)'}"
            )
            raise SystemExit(1)
        if path.is_dir():
            console.print(
                "[red]--converter not supported for directory inputs.[/red] "
                "Point it at a single file."
            )
            raise SystemExit(1)
        ok = _run_one(path, out, cls, options, skip_pack, summary=False, skip_pipeline=skip_pipeline)
        if not ok:
            raise SystemExit(1)
        return

    # Single file: detection via registry.
    if path.is_file():
        cls = pick_converter(path)
        if cls is None:
            console.print(
                f"[red]No installed converter recognizes:[/red] {path.name}\n"
                f"Installed converters: {', '.join(sorted(available)) or '(none)'}"
            )
            raise SystemExit(1)
        ok = _run_one(path, out, cls, options, skip_pack, summary=False, skip_pipeline=skip_pipeline)
        if not ok:
            raise SystemExit(1)
        return

    # Directory: group files by the converter that claims each, batch.
    grouped = _discover_files(path)
    if not grouped:
        console.print(
            f"[yellow]No supported files found in {path}[/yellow]\n"
            f"Installed converters: {', '.join(sorted(available)) or '(none)'}"
        )
        return

    total_count = sum(len(files) for files in grouped.values())
    console.print(
        f"\nFound [bold]{total_count}[/bold] file(s) across "
        f"{len(grouped)} converter(s):\n"
    )
    for cls, files in grouped.items():
        console.print(f"  [cyan]{cls.__name__}[/cyan] ({len(files)}):")
        for f in files[:5]:
            console.print(f"    [dim]-[/dim] {f.name}")
        if len(files) > 5:
            console.print(f"    [dim]… and {len(files) - 5} more[/dim]")
    console.print()

    if not click.confirm("Convert all?"):
        console.print("[dim]Aborted.[/dim]")
        return

    succeeded = failed = 0
    for cls, files in grouped.items():
        for f in files:
            console.print(f"\n[bold]{f.name}[/bold]")
            if _run_one(f, out, cls, options, skip_pack, summary=True, skip_pipeline=skip_pipeline):
                succeeded += 1
            else:
                failed += 1

    console.print(f"\n[bold]Results:[/bold] {succeeded} converted, {failed} failed")
    if failed:
        raise SystemExit(1)
