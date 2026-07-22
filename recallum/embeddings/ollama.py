"""Ollama embedding client with bounded timeouts and bounded errors."""

from __future__ import annotations

import httpx


class EmbeddingError(Exception):
    """Raised when Ollama cannot produce an embedding for a text."""


class OllamaEmbeddingClient:
    """Calls the local Ollama ``/api/embed`` endpoint synchronously per text.

    Memories are short and initial volume is low, so one blocking-style async
    call per operation is enough; failures raise ``EmbeddingError``.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 30.0,
        dimensions: int = 768,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = http_client
        self._timeout = timeout_seconds
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for ``text`` or raise ``EmbeddingError``."""
        try:
            response = await self._http.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": [text]},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingError(f"embedding request timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding service unavailable: {exc}") from exc
        except ValueError as exc:
            raise EmbeddingError("embedding service returned invalid JSON") from exc

        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise EmbeddingError("embedding service returned no vectors")
        vector = embeddings[0]
        if not isinstance(vector, list) or len(vector) != self._dimensions:
            raise EmbeddingError(
                f"expected {self._dimensions} dimensions, got "
                f"{len(vector) if isinstance(vector, list) else 'none'}"
            )
        return [float(x) for x in vector]

    async def is_available(self) -> bool:
        """Cheap readiness probe against Ollama's version endpoint."""
        try:
            response = await self._http.get(f"{self._base_url}/api/version", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
