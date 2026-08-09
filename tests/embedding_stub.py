"""Deterministic local Ollama HTTP stub for integration and vertical lanes."""

from __future__ import annotations

import json
import math
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from recallum.config import EMBEDDING_DIMENSIONS


def deterministic_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    seed = int.from_bytes(text.encode("utf-8")[:8].ljust(8, b"0"), "big")
    rng = random.Random(seed)
    vector = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class EmbeddingStubServer:
    """Tiny Ollama-shaped HTTP server with hash-seeded vectors."""

    def __init__(
        self, *, dimensions: int = EMBEDDING_DIMENSIONS, model: str = "stub-embed"
    ) -> None:
        self.dimensions = dimensions
        self.model = model
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("embedding stub is not running")
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> str:
        dimensions = self.dimensions
        model = self.model

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") == "/api/version":
                    self._json(200, {"version": "stub"})
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                if self.path.rstrip("/") != "/api/embed":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    self._json(400, {"error": "invalid json"})
                    return
                inputs = payload.get("input") or []
                if isinstance(inputs, str):
                    inputs = [inputs]
                if not isinstance(inputs, list) or not inputs:
                    self._json(400, {"error": "missing input"})
                    return
                embeddings = [deterministic_embedding(str(text), dimensions) for text in inputs]
                self._json(200, {"model": payload.get("model") or model, "embeddings": embeddings})

            def _json(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                del format, args

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
