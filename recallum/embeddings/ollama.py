"""Ollama embedding client with bounded timeouts and bounded errors."""

from __future__ import annotations

import time
from collections import OrderedDict

import httpx


class EmbeddingError(Exception):
    """Raised when Ollama cannot produce an embedding for a text."""


class OllamaEmbeddingClient:
    """Calls the local Ollama ``/api/embed`` endpoint.

    Writes (``embed`` / ``embed_batch``) use the full timeout and always try.
    Reads (``embed_read``) use a shorter timeout, skip HTTP during a short
    window after a read failure, and reuse a bounded LRU of successful vectors.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 30.0,
        dimensions: int = 768,
        read_timeout_seconds: float = 3.0,
        read_negative_window_seconds: float = 5.0,
        read_cache_size: int = 256,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = http_client
        self._timeout = timeout_seconds
        self._read_timeout = read_timeout_seconds
        self._negative_window = read_negative_window_seconds
        self._read_cache_size = read_cache_size
        self._dimensions = dimensions
        self._read_failed_until = 0.0
        self._read_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    @property
    def model(self) -> str:
        """The model id recorded alongside every vector this client produces.

        Vectors from different models share no coordinate space, so callers
        persist this to detect a silent model swap later.
        """
        return self._model

    @property
    def dimensions(self) -> int:
        """The expected dimensionality of every vector this client produces."""
        return self._dimensions

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text or raise ``EmbeddingError``."""
        if not texts:
            return []
        return await self._post(texts, self._timeout)

    async def embed(self, text: str) -> list[float]:
        """Write-path embed: full timeout, no read window and no read cache."""
        return (await self.embed_batch([text]))[0]

    async def embed_read(self, text: str) -> list[float]:
        """Read-path embed for recall, context focus and match_skills."""
        key = (self._model, text)
        cached = self._read_cache.get(key)
        if cached is not None:
            self._read_cache.move_to_end(key)
            # A hit is not evidence Ollama recovered; leave the window alone.
            return list(cached)
        if time.monotonic() < self._read_failed_until:
            raise EmbeddingError("embedding read skipped during negative window")
        try:
            vector = (await self._post([text], self._read_timeout))[0]
        except EmbeddingError:
            self._read_failed_until = time.monotonic() + self._negative_window
            raise
        self._read_failed_until = 0.0
        stored = list(vector)
        self._read_cache[key] = stored
        self._read_cache.move_to_end(key)
        while len(self._read_cache) > self._read_cache_size:
            self._read_cache.popitem(last=False)
        return list(stored)

    async def _post(self, texts: list[str], timeout_seconds: float) -> list[list[float]]:
        try:
            response = await self._http.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingError(f"embedding request timed out after {timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding service unavailable: {exc}") from exc
        except ValueError as exc:
            raise EmbeddingError("embedding service returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise EmbeddingError("embedding service returned a non-object JSON payload")
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingError(
                f"expected {len(texts)} vectors, got "
                f"{len(embeddings) if isinstance(embeddings, list) else 'none'}"
            )
        for index, vector in enumerate(embeddings):
            if not isinstance(vector, list) or len(vector) != self._dimensions:
                raise EmbeddingError(
                    f"expected {self._dimensions} dimensions for vector {index}, got "
                    f"{len(vector) if isinstance(vector, list) else 'none'}"
                )
            try:
                [float(x) for x in vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingError(
                    f"embedding service returned non-numeric values for vector {index}"
                ) from exc
        return [[float(x) for x in vector] for vector in embeddings]

    async def is_available(self) -> bool:
        """Cheap readiness probe against Ollama's version endpoint."""
        try:
            response = await self._http.get(f"{self._base_url}/api/version", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
