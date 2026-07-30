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
from recallum.db.models import ApiKey, Memory, User, WebSession
from recallum.db.repositories.memory_repo import (
    MAX_CANDIDATES,
    BucketMismatchError,
    CandidatePools,
    GraphPair,
    GraphSnapshot,
    ScoredMemory,
)
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryVisibility
from recallum.telemetry.repository import ActivityAggregate, project_bucket_label

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


def _trigrams(word: str) -> set[str]:
    """pg_trgm-style padded trigrams: two leading blanks, one trailing."""
    padded = f"  {word.lower()} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _word_similarity(query: str, content: str) -> float:
    """Approximate pg_trgm ``word_similarity``: query vs best content extent.

    Models the promise at the seam -- an exact word in the content scores
    1.0, close spellings score high, unrelated text scores near 0 -- via
    trigram Jaccard over word windows. It is not pg_trgm's exact extent
    algorithm; behaviour that depends on pg_trgm internals (precise typo
    thresholds) is pinned Postgres-only in the integration suite, like
    stemming.
    """
    query_words = _WORD_RE.findall(query.lower())
    content_words = _WORD_RE.findall(content.lower())
    if not query_words or not content_words:
        return 0.0
    query_grams: set[str] = set().union(*(_trigrams(w) for w in query_words))
    best = 0.0
    for size in range(1, len(query_words) + 1):
        for start in range(len(content_words) - size + 1):
            extent: set[str] = set().union(
                *(_trigrams(w) for w in content_words[start : start + size])
            )
            union = len(query_grams | extent)
            if union:
                best = max(best, len(query_grams & extent) / union)
    return best


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
            # ORM column defaults only apply at flush time, so the fake must
            # supply what PostgreSQL would.
            reconfirmed_at=None,
            last_recalled_at=None,
            recall_count=0,
            context_count=0,
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
        stale_before: datetime | None = None,
        fresh_since: datetime | None = None,
    ) -> tuple[Sequence[Memory], int]:
        self.last_list_offset = offset
        rows = self._filtered(user_id, visibility, category)
        # Mirrors the adapter's COALESCE(reconfirmed_at, created_at) filter.
        if stale_before is not None:
            rows = [m for m in rows if (m.reconfirmed_at or m.created_at) < stale_before]
        if fresh_since is not None:
            rows = [m for m in rows if (m.reconfirmed_at or m.created_at) >= fresh_since]
        # Matches Postgres' ORDER BY created_at DESC, id ASC: stable-sort by
        # id ascending first, then stable-sort by created_at descending so
        # ties on created_at keep id-ascending order.
        rows = sorted(rows, key=lambda m: str(m.id))
        rows.sort(key=lambda m: m.created_at, reverse=True)
        return rows[offset : offset + limit], len(rows)

    async def search_candidates(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        embedding: list[float] | None,
        embedding_model: str | None,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
        trigram_min_word_similarity: float | None = None,
    ) -> CandidatePools:
        capped = min(limit, MAX_CANDIDATES)
        return CandidatePools(
            vector=(
                self._vector_pool(
                    user_id, embedding, embedding_model, visibility, category, capped
                )
                if embedding is not None
                else []
            ),
            text=self._text_pool(user_id, query, visibility, category, capped),
            trigram=(
                self._trigram_pool(
                    user_id, query, trigram_min_word_similarity, visibility, category, capped
                )
                if trigram_min_word_similarity is not None
                else []
            ),
        )

    async def graph_snapshot(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
        min_similarity: float,
    ) -> GraphSnapshot:
        rows = sorted(
            self._filtered(user_id, visibility, category),
            key=lambda memory: str(memory.id),
        )
        rows.sort(key=lambda memory: memory.created_at, reverse=True)
        rows.sort(key=lambda memory: memory.importance, reverse=True)
        selected = rows[:limit]
        pairs = []
        for index, left in enumerate(selected):
            for right in selected[index + 1 :]:
                if (
                    left.embedding_model is None
                    or left.embedding_model != right.embedding_model
                ):
                    continue
                similarity = _cosine(left.embedding, right.embedding)
                if similarity >= min_similarity:
                    source_id, target_id = sorted((left.id, right.id), key=str)
                    pairs.append(GraphPair(source_id, target_id, similarity))
        pairs.sort(key=lambda pair: (-pair.similarity, str(pair.source_id), str(pair.target_id)))
        models = {memory.embedding_model for memory in selected if memory.embedding_model}
        mismatch = any(memory.embedding_model is None for memory in selected) or len(models) > 1
        return GraphSnapshot(selected, pairs, len(rows), mismatch)

    def _vector_pool(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        embedding_model: str | None,
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        # Mirrors the adapter's provenance rule: NULL stays eligible, a
        # positively different model never votes (its cosine would be noise).
        scored = [
            ScoredMemory(memory=m, score=_cosine(m.embedding, embedding))
            for m in self._filtered(user_id, visibility, category)
            if m.embedding_model in (None, embedding_model)
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

    def _trigram_pool(
        self,
        user_id: uuid.UUID,
        query: str,
        min_word_similarity: float,
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        scored = []
        for memory in self._filtered(user_id, visibility, category):
            score = _word_similarity(query, memory.content)
            if score >= min_word_similarity:
                scored.append(ScoredMemory(memory=memory, score=score))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def similar_active(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        embedding_model: str,
        scope: str,
        project: str | None,
        min_similarity: float,
        limit: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Sequence[ScoredMemory]:
        # Deliberately category-blind, matching the adapter: a near-duplicate
        # filed under another category is exactly what must surface. Only
        # vectors from the probe's model (or NULL provenance) are compared.
        scored = [
            ScoredMemory(memory=m, score=_cosine(m.embedding, embedding))
            for m in self._active(user_id)
            if m.scope == scope
            and (m.project or "") == (project or "")
            and m.id != exclude_id
            and m.embedding_model in (None, embedding_model)
        ]
        scored = [s for s in scored if s.score >= min_similarity]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    async def merge_memories(
        self,
        user_id: uuid.UUID,
        source_ids: Sequence[uuid.UUID],
        *,
        content: str,
        content_hash: str,
        embedding: list[float],
        embedding_model: str | None,
        category: str,
        importance: int | None,
        source_client: str | None,
        metadata: dict[str, Any],
    ) -> tuple[Memory, list[uuid.UUID]] | None:
        unique_ids = list(dict.fromkeys(source_ids))
        found = [
            row
            for row in (self.rows.get(source_id) for source_id in unique_ids)
            if row is not None and row.user_id == user_id and not row.is_deleted
        ]
        if len(found) != len(unique_ids):
            return None
        if len({(row.scope, row.project or "") for row in found}) != 1:
            raise BucketMismatchError("sources span different scopes or projects")
        # Sources retire first, so merging onto one source's exact wording is
        # legal; only an unrelated active row collides.
        source_id_set = {row.id for row in found}
        for other in self._active(user_id):
            if (
                other.id not in source_id_set
                and other.scope == found[0].scope
                and (other.project or "") == (found[0].project or "")
                and other.content_hash == content_hash
            ):
                raise IntegrityError("merge_memories", {}, Exception("duplicate key"))
        replacement = Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            scope=found[0].scope,
            project=found[0].project,
            category=category,
            content=content,
            content_hash=content_hash,
            embedding=embedding,
            embedding_model=embedding_model,
            importance=(
                importance if importance is not None else max(row.importance for row in found)
            ),
            source_client=source_client,
            metadata_=metadata,
            created_at=datetime.now(UTC),
            deleted_at=None,
            reconfirmed_at=None,
            last_recalled_at=None,
            recall_count=0,
            context_count=0,
        )
        self.rows[replacement.id] = replacement
        now = datetime.now(UTC)
        for row in found:
            row.deleted_at = now
            row.superseded_by = replacement.id
        return replacement, [row.id for row in found]

    async def mark_reconfirmed(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        memory = self.rows.get(memory_id)
        if memory is None or memory.user_id != user_id or memory.is_deleted:
            return None
        memory.reconfirmed_at = datetime.now(UTC)
        return memory

    async def mark_recalled(self, user_id: uuid.UUID, memory_ids: Sequence[uuid.UUID]) -> None:
        now = datetime.now(UTC)
        for memory_id in memory_ids:
            memory = self.rows.get(memory_id)
            if memory is None or memory.user_id != user_id or memory.is_deleted:
                continue
            memory.recall_count = (memory.recall_count or 0) + 1
            memory.last_recalled_at = now

    async def mark_seen_in_context(
        self, user_id: uuid.UUID, memory_ids: Sequence[uuid.UUID]
    ) -> None:
        for memory_id in memory_ids:
            memory = self.rows.get(memory_id)
            if memory is None or memory.user_id != user_id or memory.is_deleted:
                continue
            memory.context_count = (memory.context_count or 0) + 1

    async def stale_embeddings_batch(
        self,
        user_id: uuid.UUID,
        *,
        model: str,
        after: uuid.UUID | None,
        limit: int,
    ) -> Sequence[Memory]:
        # None != model is True, matching the adapter's "NULL or another model".
        rows = [
            m
            for m in self._active(user_id)
            if m.embedding_model != model and (after is None or str(m.id) > str(after))
        ]
        # Matches Postgres' ORDER BY id over canonical lowercase hex uuids.
        rows.sort(key=lambda m: str(m.id))
        return rows[:limit]

    async def replace_embedding(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        embedding: list[float],
        model: str,
    ) -> bool:
        memory = self.rows.get(memory_id)
        if memory is None or memory.user_id != user_id or memory.is_deleted:
            return False
        memory.embedding = embedding
        memory.embedding_model = model
        return True

    async def count_active_visible(
        self, user_id: uuid.UUID, *, visibility: MemoryVisibility
    ) -> int:
        return len(self._filtered(user_id, visibility, None))

    async def reassign_project(
        self,
        user_id: uuid.UUID,
        *,
        from_project: str,
        to_project: str,
    ) -> tuple[int, list[uuid.UUID]]:
        target_hashes = {
            m.content_hash
            for m in self._active(user_id)
            if m.scope == "project" and m.project == to_project
        }
        source = [
            m
            for m in self._active(user_id)
            if m.scope == "project" and m.project == from_project
        ]
        conflicts = sorted(
            (m for m in source if m.content_hash in target_hashes),
            key=lambda m: (m.created_at, str(m.id)),
        )
        conflicts.sort(key=lambda m: m.created_at, reverse=True)
        moved = 0
        for memory in source:
            if memory.content_hash in target_hashes:
                continue
            memory.project = to_project
            moved += 1
        return moved, [m.id for m in conflicts]

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
            source_client=(source_client if source_client is not None else original.source_client),
            metadata_=metadata if metadata is not None else dict(original.metadata_ or {}),
            created_at=datetime.now(UTC),
            deleted_at=None,
            reconfirmed_at=None,
            last_recalled_at=None,
            recall_count=0,
            context_count=0,
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

    async def count_active(self, user_id: uuid.UUID) -> int:
        return len(self._active(user_id))

    async def history(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Sequence[Memory] | None:
        anchor = self.rows.get(memory_id)
        if anchor is None or anchor.user_id != user_id:
            return None
        # Ancestry is a tree since merge_memories: walk level by level,
        # flatten by age, exactly like the adapter.
        ancestors: dict[uuid.UUID, Memory] = {}
        frontier: list[uuid.UUID] = [memory_id]
        while frontier:
            level = [
                row
                for row in self.rows.values()
                if row.user_id == user_id and row.superseded_by in frontier
            ]
            frontier = [row.id for row in level if row.id not in ancestors]
            for row in level:
                ancestors.setdefault(row.id, row)
        return sorted(ancestors.values(), key=lambda m: (m.created_at, str(m.id)))

    async def statistics(self, user_id: uuid.UUID) -> dict[str, Any]:
        from recallum.config import EMBEDDING_DIMENSIONS

        rows = [row for row in self.rows.values() if row.user_id == user_id]
        active = [row for row in rows if not row.is_deleted]

        def counts(values):
            result = {}
            for value in values:
                key = str(value) if value is not None else "none"
                result[key] = result.get(key, 0) + 1
            return result

        return {
            "active": len(active),
            "superseded": sum(row.superseded_by is not None for row in rows),
            "retired": sum(row.is_deleted and row.superseded_by is None for row in rows),
            "by_category": counts([row.category for row in active]),
            "by_scope": counts([row.scope for row in active]),
            "by_project": counts([row.project for row in active]),
            "by_importance": counts([row.importance for row in active]),
            "created_by_day": counts([row.created_at.date().isoformat() for row in rows]),
            "volume_bytes": sum(
                len(row.content.encode("utf-8")) + EMBEDDING_DIMENSIONS * 4 for row in rows
            ),
        }

    async def has_model_mismatch(self, user_id: uuid.UUID, model: str) -> bool:
        return any(
            memory.embedding_model is not None and memory.embedding_model != model
            for memory in self._active(user_id)
        )


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}

    async def create_user(self, email: str) -> User | None:
        if await self.get_by_email(email) is not None:
            return None
        user = User(
            id=uuid.uuid4(),
            email=email,
            created_at=datetime.now(UTC),
            password_hash=None,
            is_admin=False,
        )
        self.users[user.id] = user
        return user

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)

    async def set_password(self, user_id: uuid.UUID, password_hash: str) -> None:
        self.users[user_id].password_hash = password_hash

    async def set_admin(self, user_id: uuid.UUID, is_admin: bool) -> None:
        self.users[user_id].is_admin = is_admin

    async def list_users(self) -> Sequence[User]:
        return sorted(self.users.values(), key=lambda user: (user.created_at, str(user.id)))

    async def count_admins(self) -> int:
        return sum(user.is_admin for user in self.users.values())

    async def set_admin_preserving_last(self, user_id: uuid.UUID, is_admin: bool):
        from recallum.db.repositories.user_repo import LastAdminError

        user = self.users.get(user_id)
        if user is None:
            return None
        if user.is_admin and not is_admin and await self.count_admins() == 1:
            raise LastAdminError
        user.is_admin = is_admin
        return user


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

    async def revoke_for_user(self, user_id: uuid.UUID, key_id: uuid.UUID) -> bool:
        key = self.keys.get(key_id)
        if key is None or key.user_id != user_id or key.revoked_at is not None:
            return False
        key.revoked_at = datetime.now(UTC)
        return True

    async def count_by_status(self) -> tuple[int, int]:
        return (
            sum(key.revoked_at is None for key in self.keys.values()),
            sum(key.revoked_at is not None for key in self.keys.values()),
        )

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[ApiKey]:
        return [k for k in self.keys.values() if k.user_id == user_id]


class FakeWebSessionRepository:
    def __init__(self, users: FakeUserRepository) -> None:
        self.users = users
        self.sessions: dict[uuid.UUID, WebSession] = {}

    async def create(
        self, user_id, token_hash, now, idle_expires_at, absolute_expires_at
    ) -> WebSession:
        row = WebSession(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
            rotated_to_id=None,
            revoked_at=None,
        )
        self.sessions[row.id] = row
        return row

    async def find_by_hash(self, token_hash):
        row = next((row for row in self.sessions.values() if row.token_hash == token_hash), None)
        return (row, self.users.users[row.user_id]) if row else None

    async def rotate(
        self, previous_id, user_id, token_hash, now, idle_expires_at, absolute_expires_at
    ):
        previous = self.sessions[previous_id]
        if previous.rotated_to_id is not None or previous.revoked_at is not None:
            return None
        replacement = await self.create(
            user_id, token_hash, now, idle_expires_at, absolute_expires_at
        )
        previous.rotated_to_id = replacement.id
        return replacement

    async def revoke(self, session_id, now):
        self.sessions[session_id].revoked_at = now

    async def revoke_chain(self, session_id, now):
        current = self.sessions.get(session_id)
        while current:
            current.revoked_at = now
            current = self.sessions.get(current.rotated_to_id)


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


class FakeTelemetryRepository:
    def __init__(self) -> None:
        self.events = []
        self.insert_calls = 0
        self.purged_before: list[datetime] = []

    async def insert_batch(self, events) -> None:
        self.insert_calls += 1
        self.events.extend(events)

    async def aggregate(self, user_id, start, end) -> ActivityAggregate:
        rows = [
            event
            for event in self.events
            if event.user_id == user_id and start <= event.created_at < end
        ]

        def counts(values):
            result = {}
            for value in values:
                key = str(value) if value is not None else "none"
                result[key] = result.get(key, 0) + 1
            return result

        return ActivityAggregate(
            total_calls=len(rows),
            total_results=sum(event.result_count for event in rows),
            failed_calls=sum(event.failed for event in rows),
            degraded_calls=sum(event.degraded for event in rows),
            by_day=counts(event.created_at.date().isoformat() for event in rows),
            by_tool=counts(event.tool_name for event in rows),
            by_project=counts(project_bucket_label(event.project) for event in rows),
        )

    async def purge_before(self, cutoff) -> int:
        self.purged_before.append(cutoff)
        before = len(self.events)
        self.events = [event for event in self.events if event.created_at >= cutoff]
        return before - len(self.events)


def build_test_container(
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
    engine: FakeEngine | None = None,
) -> tuple[Container, dict[str, Any]]:
    """A container fully isolated from PostgreSQL and Ollama."""
    container = create_container(Settings())
    users = FakeUserRepository()
    keys = FakeApiKeyRepository(users)
    web_sessions = FakeWebSessionRepository(users)
    memories = FakeMemoryRepository()
    telemetry = FakeTelemetryRepository()
    embedder = embedder if embedder is not None else FakeEmbeddingClient()
    container.user_repository.override(providers.Object(users))
    container.api_key_repository.override(providers.Object(keys))
    container.web_session_repository.override(providers.Object(web_sessions))
    container.memory_repository.override(providers.Object(memories))
    container.telemetry_repository.override(providers.Object(telemetry))
    container.embedding_client.override(providers.Object(embedder))
    if engine is not None:
        container.engine.override(providers.Object(engine))
    fakes = {
        "users": users,
        "keys": keys,
        "web_sessions": web_sessions,
        "memories": memories,
        "embedder": embedder,
        "telemetry": telemetry,
    }
    return container, fakes
