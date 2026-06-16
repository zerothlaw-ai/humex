"""``humex serve`` — run a local HTTP server for zeno's ``local`` mode."""

import click
from rich.console import Console

from humex.server import DEFAULT_HOST, DEFAULT_PORT, run_server

console = Console()


@click.command()
@click.option(
    "--host",
    default=DEFAULT_HOST,
    show_default=True,
    help="Interface to bind. Keep the loopback default unless you know why "
    "you're exposing it on the network.",
)
@click.option(
    "--port",
    default=DEFAULT_PORT,
    show_default=True,
    type=int,
    help="Port to listen on.",
)
@click.option(
    "--cors-origin",
    default="*",
    show_default=True,
    help="Allowed browser origin (e.g. https://zeno.dev.zerothlaw.io). "
    "Default '*' echoes the request origin — convenient for local dev.",
)
def serve(host: str, port: int, cors_origin: str) -> None:
    """Serve simulate / evaluate over HTTP for a zeno frontend.

    Point zeno at this server with ``?mode=local`` (and ``?localUrl=`` if you
    changed the host/port). Works from an HTTPS-deployed zeno in Chrome and
    Firefox via the loopback mixed-content exemption; Safari blocks it.

    \b
    Example:
        humex serve
        humex serve --port 9100 --cors-origin https://zeno.dev.zerothlaw.io
    """
    run_server(host=host, port=port, allow_origin=cors_origin)
