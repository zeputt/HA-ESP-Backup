import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

LOG = logging.getLogger("esphome-backup")
UI_FILE = Path("/ui.html")


def start_web_server(
    status_provider: Callable[[], dict[str, Any]],
    manual_backup: Callable[[], bool],
    log_provider: Callable[[int, int], dict[str, Any]],
    git_history_provider: Callable[[int], dict[str, Any]],
    port: int = 8099,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ESPHomeBackup/0.3.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.debug("Web: " + fmt, *args)

        def _ingress_allowed(self) -> bool:
            # Home Assistant Supervisor Ingress proxy. Do not expose the UI to
            # arbitrary container-network clients.
            return self.client_address[0] == "172.30.32.2"

        def _deny_non_ingress(self) -> bool:
            if self._ingress_allowed():
                return False
            self.send_json({"error": "Ingress only"}, 403)
            return True

        def send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self._deny_non_ingress():
                return
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/api/status" or path.endswith("/api/status"):
                self.send_json(status_provider())
                return
            if path == "/api/log" or path.endswith("/api/log"):
                query = urlparse(self.path).query
                params = {}
                for item in query.split("&") if query else []:
                    if "=" in item:
                        k, v = item.split("=", 1); params[k] = v
                try:
                    after = int(params.get("after", "0"))
                except ValueError:
                    after = 0
                self.send_json(log_provider(after, 300))
                return
            if path == "/api/git-history" or path.endswith("/api/git-history"):
                self.send_json(git_history_provider(40))
                return
            if path == "/health" or path.endswith("/health"):
                self.send_json({"status": "ok", "version": "0.3.1"})
                return
            try:
                body = UI_FILE.read_bytes()
            except OSError as exc:
                self.send_json({"error": f"UI saknas: {exc}"}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self._deny_non_ingress():
                return
            path = urlparse(self.path).path.rstrip("/")
            if not (path == "/api/backup" or path.endswith("/api/backup")):
                self.send_json({"error": "Not found"}, 404)
                return
            if not manual_backup():
                self.send_json({"error": "En backup körs redan"}, 409)
                return
            self.send_json({"accepted": True, "message": "Backup startad"}, 202)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="ingress-web", daemon=True)
    thread.start()
    LOG.info("Ingress GUI lyssnar på port %s", port)
    return server
