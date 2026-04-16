"""Local web app for the Production Planning Game dashboard."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from main import generate_plan_results
from utils import project_root

HOST = "127.0.0.1"
PORT = 8000
STATIC_DIR = project_root() / "web"
OUTPUTS_DIR = project_root() / "outputs"


class DashboardState:
    """Keep the most recently generated planning snapshot in memory."""

    def __init__(self) -> None:
        self.bundle = generate_plan_results(write_outputs=True, print_summary=False)

    def refresh(self) -> dict:
        self.bundle = generate_plan_results(write_outputs=True, print_summary=False)
        return self.bundle


STATE = DashboardState()


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the planning dashboard frontend and lightweight JSON API."""

    server_version = "ProductionPlanningApp/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if path == "/api/dashboard":
            self._send_json(STATE.bundle)
            return
        if path.startswith("/outputs/"):
            self._serve_file(OUTPUTS_DIR / path.removeprefix("/outputs/"))
            return
        if path == "/" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html")
            return

        static_target = STATIC_DIR / path.lstrip("/")
        if static_target.is_file():
            self._serve_file(static_target)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            bundle = STATE.refresh()
            self._send_json(bundle)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        """Keep console output concise while still useful during local runs."""
        print(f"{self.address_string()} - {format % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the local planning dashboard server."""
    with ThreadingHTTPServer((HOST, PORT), DashboardHandler) as httpd:
        print(f"Production Planning app running at http://{HOST}:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
