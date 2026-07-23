"""In-memory fakes isolating PostgreSQL and Ollama for unit tests."""

from __future__ import annotations

import math
import random
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from dependency_injector import providers
from sqlalchemy.exc import IntegrityError

from recallum.config import EMBEDDING_DIMENSIONS, Settings
from recallum.container import Container, create_container
from recallum.db.models import ApiKey, Memory, User
from recallum.db.repositories.memory_repo import ScoredMemory
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryVisibility


class FakeEmbeddingClient:
    """Deterministic hash-seeded vectors; availability is configurable."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS, available: bool = True) -> None:
        self.dimensions = dimensions
        self.available = available
        self.embedded_texts: list[str] = []

    async def embed(self, text: str) -> list[float]:
        if not self.available:
            raise EmbeddingError("fake ollama is down")
        self.embedded_texts.append(text)
        seed = int.from_bytes(text.encode("utf-8")[:8].ljust(8, b"0"), "big")
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    async def is_available(self) -> bool:
        return self.available


class ScriptedEmbeddingClient:
    """Returns preset vectors per exact text; unknown texts raise."""

    def __init__(self, vectors: dict[str, list[float]], available: bool = True) -> None:
        self.vectors = vectors
        self.available = available
        self.embedded_texts: list[str] = []

    async def embed(self, text: str) -> list[float]:
        if not self.available:
            raise EmbeddingError("fake ollama is down")
        self.embedded_texts.append(text)
        try:
            return list(self.vectors[text])
        except KeyError as exc:
            raise EmbeddingError(f"no scripted vector for {text!r}") from exc

    async def is_available(self) -> bool:
        return self.available


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class FakeMemoryRepository:
    """Dict-backed repository implementing the real interface."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Memory] = {}

    def _active(self, user_id: uuid.UUID) -> list[Memory]:
        return [m for m in self.rows.values() if m.user_id == user_id and not m.is_deleted]

    def _filtered(
        self,
        user_id: uuid.UUID,
        visibility: MemoryVisibility,
        category: str | None,
    ) -> list[Memory]:
        rows = [m for m in self._active(user_id) if visibility.includes(m)]
        if category is not None:
            rows = [m for m in rows if m.category == category]
        return rows

    async def create_memory(self, user_id: uuid.UUID, **kwargs: Any) -> Memory:
        scope = kwargs["scope"]
        project = kwargs["project"]
        digest = kwargs["content_hash"]
        for existing in self._active(user_id):
            if (
                existing.scope == scope
                and (existing.project or "") == (project or "")
                and existing.content_hash == digest
            ):
                raise IntegrityError("create_memory", {}, Exception("duplicate key"))
        metadata = kwargs.pop("metadata", {})
        memory = Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            created_at=datetime.now(UTC),
            deleted_at=None,
            metadata_=metadata,
            **kwargs,
        )
        self.rows[memory.id] = memory
        return memory

    async def find_active_by_hash(
        self, user_id: uuid.UUID, *, scope: str, project: str | None, content_hash: str
    ) -> Memory | None:
        for memory in self._active(user_id):
            if (
                memory.scope == scope
                and (memory.project or "") == (project or "")
                and memory.content_hash == content_hash
            ):
                return memory
        return None

    async def get_active(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        memory = self.rows.get(memory_id)
        if memory is None or memory.user_id != user_id or memory.is_deleted:
            return None
        return memory

    async def list_active(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
        offset: int = 0,
    ) -> tuple[Sequence[Memory], int]:
        rows = sorted(
            self._filtered(user_id, visibility, category),
            key=lambda m: (m.created_at, str(m.id)),
            reverse=True,
        )
        return rows[offset : offset + limit], len(rows)

    async def search_vector(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        scored = [
            ScoredMemory(memory=m, score=_cosine(m.embedding, embedding))
            for m in self._filtered(user_id, visibility, category)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def search_text(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        words = [w for w in query.lower().split() if len(w) > 1]
        scored = []
        for memory in self._filtered(user_id, visibility, category):
            haystack = memory.content.lower()
            score = sum(1.0 for w in words if w in haystack)
            if score > 0:
                scored.append(ScoredMemory(memory=memory, score=score))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def most_important_active(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        limit: int,
    ) -> Sequence[Memory]:
        rows = self._filtered(user_id, visibility, None)
        rows.sort(key=lambda m: (m.importance, m.created_at), reverse=True)
        return rows[:limit]

    async def soft_delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> bool:
        memory = self.rows.get(memory_id)
        if memory is None or memory.user_id != user_id or memory.is_deleted:
            return False
        memory.deleted_at = datetime.now(UTC)
        return True


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}

    async def create_user(self, email: str) -> User:
        user = User(id=uuid.uuid4(), email=email, created_at=datetime.now(UTC))
        self.users[user.id] = user
        return user

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)


class FakeApiKeyRepository:
    def __init__(self, users: FakeUserRepository) -> None:
        self.users = users
        self.keys: dict[uuid.UUID, ApiKey] = {}

    async def create_key(self, user_id: uuid.UUID, key_hash: str, name: str | None) -> ApiKey:
        key = ApiKey(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            created_at=datetime.now(UTC),
            last_used_at=None,
            revoked_at=None,
        )
        self.keys[key.id] = key
        return key

    async def find_active_by_hash(self, key_hash: str) -> tuple[ApiKey, User] | None:
        for key in self.keys.values():
            if key.key_hash == key_hash and key.revoked_at is None:
                user = self.users.users.get(key.user_id)
                if user is not None:
                    return key, user
        return None

    async def touch(self, key_id: uuid.UUID) -> None:
        if key := self.keys.get(key_id):
            key.last_used_at = datetime.now(UTC)

    async def revoke(self, key_id: uuid.UUID) -> bool:
        key = self.keys.get(key_id)
        if key is None or key.revoked_at is not None:
            return False
        key.revoked_at = datetime.now(UTC)
        return True

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[ApiKey]:
        return [k for k in self.keys.values() if k.user_id == user_id]


class FakeEngine:
    """Async engine stand-in for readiness probes and shutdown tests."""

    def __init__(self, available: bool = True, ready: bool = True) -> None:
        self.available = available
        self.ready = ready
        self.disposed = False

    def connect(self):
        repo = self

        class _Connection:
            async def __aenter__(self):
                if not repo.available:
                    raise ConnectionError("fake database is down")
                return self

            async def __aexit__(self, *exc_info):
                return None

            async def execute(self, *_args, **_kwargs):
                class _Result:
                    def scalar_one(self):
                        return repo.ready

                return _Result()

        return _Connection()

    async def dispose(self) -> None:
        self.disposed = True


class FakeDatabaseReadiness:
    """Configurable adapter at the database-readiness seam."""

    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    async def is_ready(self) -> bool:
        return self.ready


def build_test_container(
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
    engine: FakeEngine | None = None,
) -> tuple[Container, dict[str, Any]]:
    """A container fully isolated from PostgreSQL and Ollama."""
    container = create_container(Settings())
    users = FakeUserRepository()
    keys = FakeApiKeyRepository(users)
    memories = FakeMemoryRepository()
    embedder = embedder if embedder is not None else FakeEmbeddingClient()
    container.user_repository.override(providers.Object(users))
    container.api_key_repository.override(providers.Object(keys))
    container.memory_repository.override(providers.Object(memories))
    container.embedding_client.override(providers.Object(embedder))
    if engine is not None:
        container.engine.override(providers.Object(engine))
    fakes = {"users": users, "keys": keys, "memories": memories, "embedder": embedder}
    return container, fakes
