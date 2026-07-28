"""In-memory fakes isolating PostgreSQL and Ollama for unit tests."""

from __future__ import annotations

import math
import random
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from dependency_injector import providers
from sqlalchemy.exc import IntegrityError

from recallum.config import EMBEDDING_DIMENSIONS, Settings
from recallum.container import Container, create_container
from recallum.db.models import ApiKey, Memory, User
from recallum.db.repositories.memory_repo import (
    MAX_CANDIDATES,
    CandidatePools,
    ScoredMemory,
)
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryVisibility

_WORD_RE = re.compile(r"[a-z0-9]+")

# Stopwords carry no weight, matching what PostgreSQL's TEXT_SEARCH_CONFIG
# does. Only words that are uncontroversially stopwords in both this list and
# PostgreSQL's are exercised by the contract.
#
# Deliberately absent: a stemmer. Collapsing inflections is a capability of the
# Postgres adapter's Snowball dictionary, not a promise the interface can make
# portably, and a toy stemmer here would make this fake claim behaviour it does
# not have -- the exact class of fake/adapter divergence that let the old AND
# semantics ship unnoticed. Stemming is pinned in the Postgres integration
# tests instead.
_STOPWORDS = frozenset(
    """a an and are as at be by do does for from had has have how i if in is it
    its me my no not of on or our so than that the their them then there these
    they this to too very was we were what when where which who why will with
    you your""".split()
)


class FakeEmbeddingClient:
    """Deterministic hash-seeded vectors; availability is configurable."""

    def __init__(
        self,
        dimensions: int = EMBEDDING_DIMENSIONS,
        available: bool = True,
        model: str = "fake-embedding-model",
    ) -> None:
        self.dimensions = dimensions
        self.available = available
        self.model = model
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

    def __init__(
        self,
        vectors: dict[str, list[float]],
        available: bool = True,
        model: str = "scripted-embedding-model",
    ) -> None:
        self.vectors = vectors
        self.available = available
        self.model = model
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
        self.last_list_offset: int | None = None

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
        self.last_list_offset = offset
        # Matches Postgres' ORDER BY created_at DESC, id ASC: stable-sort by
        # id ascending first, then stable-sort by created_at descending so
        # ties on created_at keep id-ascending order.
        rows = sorted(self._filtered(user_id, visibility, category), key=lambda m: str(m.id))
        rows.sort(key=lambda m: m.created_at, reverse=True)
        return rows[offset : offset + limit], len(rows)

    async def search_candidates(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        embedding: list[float] | None,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> CandidatePools:
        capped = min(limit, MAX_CANDIDATES)
        return CandidatePools(
            vector=(
                self._vector_pool(user_id, embedding, visibility, category, capped)
                if embedding is not None
                else []
            ),
            text=self._text_pool(user_id, query, visibility, category, capped),
        )

    def _vector_pool(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        scored = [
            ScoredMemory(memory=m, score=_cosine(m.embedding, embedding))
            for m in self._filtered(user_id, visibility, category)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    def _text_pool(
        self,
        user_id: uuid.UUID,
        query: str,
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        # Models the promise the textual signal makes at the seam, not
        # Postgres' implementation of it: whole-word matching ("cat" must not
        # match "concatenate"), ANY query term counts rather than all of them,
        # and stopwords carry no weight. Score is term coverage, so a row
        # sharing more query terms outranks one sharing fewer.
        words = set(_WORD_RE.findall(query.lower())) - _STOPWORDS
        scored = []
        for memory in self._filtered(user_id, visibility, category):
            tokens = set(_WORD_RE.findall(memory.content.lower())) - _STOPWORDS
            score = float(len(words & tokens))
            if score > 0:
                scored.append(ScoredMemory(memory=memory, score=score))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def similar_active(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        category: str,
        min_similarity: float,
        limit: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Sequence[ScoredMemory]:
        scored = [
            ScoredMemory(memory=m, score=_cosine(m.embedding, embedding))
            for m in self._active(user_id)
            if m.scope == scope
            and (m.project or "") == (project or "")
            and m.category == category
            and m.id != exclude_id
        ]
        scored = [s for s in scored if s.score >= min_similarity]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def update_attributes(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        importance: int | None,
        category: str | None,
        metadata: dict[str, Any] | None,
    ) -> Memory | None:
        memory = self.rows.get(memory_id)
        if memory is None or memory.user_id != user_id or memory.is_deleted:
            return None
        if importance is not None:
            memory.importance = importance
        if category is not None:
            memory.category = category
        if metadata is not None:
            memory.metadata_ = metadata
        return memory

    async def supersede(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        content: str,
        content_hash: str,
        embedding: list[float],
        embedding_model: str | None,
        category: str | None,
        importance: int | None,
        metadata: dict[str, Any] | None,
        source_client: str | None,
    ) -> Memory | None:
        original = self.rows.get(memory_id)
        if original is None or original.user_id != user_id or original.is_deleted:
            return None
        for other in self._active(user_id):
            if (
                other.id != original.id
                and other.scope == original.scope
                and (other.project or "") == (original.project or "")
                and other.content_hash == content_hash
            ):
                raise IntegrityError("supersede", {}, Exception("duplicate key"))
        replacement = Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            scope=original.scope,
            project=original.project,
            category=category if category is not None else original.category,
            content=content,
            content_hash=content_hash,
            embedding=embedding,
            embedding_model=embedding_model,
            importance=importance if importance is not None else original.importance,
            source_client=(
                source_client if source_client is not None else original.source_client
            ),
            metadata_=metadata if metadata is not None else dict(original.metadata_ or {}),
            created_at=datetime.now(UTC),
            deleted_at=None,
        )
        self.rows[replacement.id] = replacement
        original.deleted_at = datetime.now(UTC)
        original.superseded_by = replacement.id
        return replacement

    async def most_important_active(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        limit: int,
    ) -> Sequence[Memory]:
        # Matches Postgres' ORDER BY importance DESC, created_at DESC, id ASC.
        rows = sorted(self._filtered(user_id, visibility, None), key=lambda m: str(m.id))
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

    async def create_user(self, email: str) -> User | None:
        if await self.get_by_email(email) is not None:
            return None
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
