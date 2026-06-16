"""Local HTTP server for ``humex serve``.

A dependency-light (stdlib :mod:`http.server`) JSON API that lets a zeno
frontend — including one deployed over HTTPS (e.g. zeno.dev.zerothlaw.io) —
run ``simulate`` / ``evaluate`` against the user's *local* humex install.

Why stdlib and not Flask: humex core stays free of a web-framework dep, and a
threaded loopback server is plenty for a single developer's tabs.

Cross-origin notes (the whole reason this server is careful about headers):
  * An HTTPS page fetching ``http://localhost`` is normally blocked as mixed
    content, but Chrome/Firefox exempt loopback. Safari does NOT — Safari users
    on an HTTPS site can't reach a plain-HTTP local server.
  * Chrome's Private Network Access sends a CORS *preflight* for requests from a
    public site to a loopback address and requires
    ``Access-Control-Allow-Private-Network: true`` on the response.
Both are handled below.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import urlparse

import humex

from .operations import Session

__all__ = ["run_server", "DEFAULT_PORT", "DEFAULT_HOST"]

DEFAULT_PORT = 8900
DEFAULT_HOST = "127.0.0.1"

_SESSION_HEADER = "X-Humex-Session"
_DEFAULT_SESSION = "_default"

# Routes that read/return raw bytes rather than JSON.
_AVAILABLE_APIS = ["ComputeDagMetricsAPI", "RunSimulationAPI", "TestDagMetricsAPI"]


class _SessionRegistry:
    """Thread-safe map of session-id -> :class:`Session`."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, sid: Optional[str]) -> Session:
        key = sid or _DEFAULT_SESSION
        with self._lock:
            sess = self._sessions.get(key)
            if sess is None:
                sess = Session()
                self._sessions[key] = sess
            return sess


def _make_handler(allow_origin: str) -> type:
    registry = _SessionRegistry()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"humex-serve/{humex.__version__}"

        # -- low-level helpers --------------------------------------------
        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if allow_origin == "*":
                self.send_header("Access-Control-Allow-Origin", origin or "*")
                self.send_header("Vary", "Origin")
            else:
                self.send_header("Access-Control-Allow-Origin", allow_origin)
                self.send_header("Vary", "Origin")
            self.send_header(
                "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
            )
            self.send_header(
                "Access-Control-Allow-Headers",
                f"Content-Type, {_SESSION_HEADER}",
            )
            # Chrome Private Network Access: required when a public/secure origin
            # calls a loopback address.
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _read_bytes(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length) if length else b""

        def _session(self) -> Session:
            return registry.get(self.headers.get(_SESSION_HEADER))

        # quieter logs — one line per request, no stderr noise.
        def log_message(self, fmt: str, *args) -> None:  # noqa: A002
            print(f"humex serve: {self.address_string()} - {fmt % args}")

        # -- HTTP verbs ----------------------------------------------------
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/health", "/"):
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "humex_version": humex.__version__,
                        "available_apis": _AVAILABLE_APIS,
                        "cold_start_seconds": 0,
                    },
                )
                return
            self._send_json(404, {"success": False, "error": f"not found: {path}"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                self._route_post(path)
            except Exception as exc:  # noqa: BLE001 — never 500 silently
                self._send_json(500, {"success": False, "error": str(exc)})

        def _route_post(self, path: str) -> None:
            session = self._session()

            if path == "/parse-yaml":
                body = self._read_json()
                self._send_json(200, session.parse_yaml(body.get("yaml_text", "")))
                return
            if path == "/test-dag":
                body = self._read_json()
                self._send_json(200, session.test_dag(body.get("dag_yaml", "")))
                return
            if path == "/import-package":
                # Raw .hpkg bytes in the request body (Content-Type ignored).
                result = session.import_package(self._read_bytes())
                self._send_json(200, {"success": True, **result})
                return
            if path == "/run-simulation":
                body = self._read_json()
                self._send_json(
                    200, session.run_simulation(body.get("config_json", {}))
                )
                return
            if path == "/evaluate-metrics":
                body = self._read_json()
                self._send_json(
                    200,
                    session.evaluate_metrics(body.get("metric_yaml_content", "")),
                )
                return
            if path == "/build-hpkg":
                body = self._read_json()
                data = session.build_hpkg(
                    name=body.get("name") or "scenario",
                    config_json=body.get("config_json"),
                    metric_yaml=body.get("metric_yaml_content"),
                    have_scenario=bool(body.get("have_scenario")),
                )
                self._send_bytes(200, data, "application/octet-stream")
                return

            self._send_json(404, {"success": False, "error": f"not found: {path}"})

    return Handler


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    allow_origin: str = "*",
) -> None:
    """Start the blocking local server. Ctrl-C to stop."""
    handler = _make_handler(allow_origin)
    httpd = ThreadingHTTPServer((host, port), handler)
    origin_note = "any origin" if allow_origin == "*" else allow_origin
    print(f"humex {humex.__version__} — local server", flush=True)
    print(f"  listening on http://{host}:{port}", flush=True)
    print(f"  CORS origin: {origin_note}", flush=True)
    print(
        "  endpoints: /health /parse-yaml /test-dag /import-package "
        "/run-simulation /evaluate-metrics /build-hpkg",
        flush=True,
    )
    print("  press Ctrl-C to stop", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nhumex serve: shutting down")
    finally:
        httpd.server_close()
