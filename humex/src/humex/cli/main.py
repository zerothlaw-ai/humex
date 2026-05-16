"""Entry point for the ``humex`` CLI."""

import click

from humex import __version__
from .convert import convert
from .evaluate import evaluate
from .lane_map import lane_map
from .package import package


@click.group()
@click.version_option(version=__version__, prog_name="humex")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """humex — behavioral metrics for AV / physical-AI scenarios."""
    ctx.ensure_object(dict)


cli.add_command(convert)
cli.add_command(evaluate)
cli.add_command(lane_map, name="lane-map")
cli.add_command(package)


if __name__ == "__main__":
    cli()
