from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class TopTermsWebServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port

        self._lock = threading.Lock()
        self._payload: dict[str, object] = {
            "ts": 0.0,
            "window_sec": 60,
            "top_k": 60,
            "terms": [],
        }

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def update(self, payload: dict[str, object]) -> None:
        with self._lock:
            self._payload = payload

    def get_payload(self) -> dict[str, object]:
        with self._lock:
            return dict(self._payload)

    def start(self) -> None:
        if self._httpd is not None:
            return

        static_dir = Path(__file__).resolve().parent / "static"
        html_cache: dict[str, bytes] = {}
        for p in static_dir.glob("wordcloud*.html"):
            html_cache[f"/{p.name}"] = p.read_bytes()
        html_cache["/"] = html_cache.get("/wordcloud.html", b"")

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path

                if path in html_cache:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(html_cache[path])
                    return

                if path == "/terms":
                    body = json.dumps(owner.get_payload(), ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"ok")
                    return

                self.send_error(404, "Not Found")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._httpd = None

    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
