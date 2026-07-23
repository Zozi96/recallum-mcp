"""Memory service unit tests with repository/embedding overrides (task 3.7)."""

from __future__ import annotations

import uuid

import pytest

from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.service import MemoryService
from tests.fakes import FakeEmbeddingClient, FakeMemoryRepository, ScriptedEmbeddingClient


def make_service(
    repo: FakeMemoryRepository | None = None,
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
) -> tuple[MemoryService, FakeMemoryRepository, object]:
    repo = repo or FakeMemoryRepository()
    embedder = embedder or FakeEmbeddingClient(dimensions=8)
    return (
        MemoryService(repository=repo, embeddings=embedder),
        repo,
        embedder,
    )


USER = uuid.uuid4()


async def test_remember_creates_global_memory():
    service, repo, _ = make_service()
    result = await service.remember(USER, content="prefiero tabs", category="preference")
    assert result.created is True
    assert result.memory.scope == "global"
    assert result.memory.project is None
    assert result.memory.content == "prefiero tabs"
    assert len(repo.rows) == 1


async def test_remember_project_scope():
    service, repo, _ = make_service()
    result = await service.remember(
        USER, content="usamos FastAPI", category="decision", project="recallum"
    )
    assert result.created is True
    assert result.memory.scope == "project"
    assert result.memory.project == "recallum"


async def test_remember_exact_duplicate_returns_existing():
    service, repo, _ = make_service()
    first = await service.remember(USER, content="  me gusta   el café  ", category="preference")
    second = await service.remember(USER, content="me gusta el café", category="preference")
    assert first.created is True
    assert second.created is False
    assert second.memory.id == first.memory.id
    assert len(repo.rows) == 1


async def test_remember_duplicate_scoped_per_project():
    service, repo, _ = make_service()
    await service.remember(USER, content="misma nota", category="fact", project="a")
    other = await service.remember(USER, content="misma nota", category="fact", project="b")
    assert other.created is True
    assert len(repo.rows) == 2


async def test_remember_rejects_invalid_input_before_embedding():
    service, _, embedder = make_service()
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="  ", category="preference")
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="mood")
    assert embedder.embedded_texts == []


async def test_remember_normalizes_content_and_project():
    service, _, _ = make_service()
    result = await service.remember(
        USER,
        content="  hello\n\n  world \t ",
        category="fact",
        project="  mi-proyecto  ",
    )
    assert result.memory.content == "hello world"
    assert result.memory.project == "mi-proyecto"

    blank = await service.remember(USER, content="global", category="fact", project="   ")
    assert blank.memory.scope == "global"
    assert blank.memory.project is None


async def test_remember_enforces_content_and_project_limits():
    service = MemoryService(
        repository=FakeMemoryRepository(),
        embeddings=FakeEmbeddingClient(dimensions=8),
        max_content_chars=10,
        max_project_chars=4,
    )
    with pytest.raises(MemoryValidationError, match="content exceeds"):
        await service.remember(USER, content="x" * 11, category="fact")
    with pytest.raises(MemoryValidationError, match="project exceeds"):
        await service.remember(USER, content="ok", category="fact", project="longer")


@pytest.mark.parametrize("importance", [-1, 11, True])
async def test_remember_rejects_invalid_importance(importance):
    service, _, _ = make_service()
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="fact", importance=importance)


async def test_remember_accepts_importance_bounds_and_flat_metadata():
    service, _, _ = make_service()
    low = await service.remember(
        USER,
        content="low",
        category="fact",
        importance=0,
        metadata={"k": "v", "n": 1, "f": True, "empty": None},
    )
    high = await service.remember(USER, content="high", category="fact", importance=10)
    assert low.memory.importance == 0
    assert low.memory.metadata == {"k": "v", "n": 1, "f": True, "empty": None}
    assert high.memory.importance == 10
    assert high.memory.metadata == {}


@pytest.mark.parametrize(
    ("metadata", "max_bytes", "max_keys"),
    [
        ({"k": {"nested": 1}}, 1024, 10),
        ({"": "value"}, 1024, 10),
        ({"a": 1, "b": 2}, 1024, 1),
        ({"k": "x" * 100}, 50, 10),
        (["not", "an", "object"], 1024, 10),
    ],
)
async def test_remember_rejects_invalid_metadata(metadata, max_bytes, max_keys):
    service = MemoryService(
        repository=FakeMemoryRepository(),
        embeddings=FakeEmbeddingClient(dimensions=8),
        max_metadata_bytes=max_bytes,
        max_metadata_keys=max_keys,
    )
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="fact", metadata=metadata)


async def test_remember_fails_without_embedding_and_stores_nothing():
    service, repo, _ = make_service(embedder=FakeEmbeddingClient(available=False))
    with pytest.raises(EmbeddingError):
        await service.remember(USER, content="algo", category="fact")
    assert repo.rows == {}


async def test_recall_hybrid_fusion_ranks_consensus_first():
    vectors = {
        "query about deploy": [1.0, 0.0],
        "we deploy with dokploy": [0.99, 0.1],
        "unrelated favorite color": [0.0, 1.0],
    }
    service, _, _ = make_service(embedder=ScriptedEmbeddingClient(vectors, available=True))
    await service.remember(USER, content="we deploy with dokploy", category="decision")
    await service.remember(USER, content="unrelated favorite color", category="preference")

    result = await service.recall(USER, query="query about deploy")
    assert result.mode == "hybrid"
    assert result.results[0].content == "we deploy with dokploy"
    # The text signal also ranks the dokploy memory first ("deploy" matches).
    assert all(r.score > 0 for r in result.results)


async def test_recall_degrades_to_textual_when_embeddings_fail():
    repo = FakeMemoryRepository()
    good = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(dimensions=8))
    await good.remember(USER, content="la base de datos es postgres", category="fact")

    degraded = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(available=False))
    result = await degraded.recall(USER, query="postgres")
    assert result.mode == "degraded_textual"
    assert [r.content for r in result.results] == ["la base de datos es postgres"]


async def test_recall_category_filter():
    service, _, _ = make_service()
    await service.remember(USER, content="decisión de api rest", category="decision")
    await service.remember(USER, content="restricción de api rest", category="constraint")
    result = await service.recall(USER, query="api rest", category="decision")
    assert all(r.category == "decision" for r in result.results)
    assert len(result.results) == 1


async def test_recall_project_includes_global_and_excludes_other_projects():
    service, _, _ = make_service()
    await service.remember(USER, content="global nota sobre tests", category="fact")
    await service.remember(USER, content="proyecto nota sobre tests", category="fact", project="a")
    await service.remember(USER, content="otro proyecto tests", category="fact", project="b")

    result = await service.recall(USER, query="tests", project="a", limit=10)
    contents = {r.content for r in result.results}
    assert "global nota sobre tests" in contents
    assert "proyecto nota sobre tests" in contents
    assert "otro proyecto tests" not in contents


async def test_recall_respects_limit():
    service, _, _ = make_service()
    for i in range(5):
        await service.remember(USER, content=f"nota compartida {i}", category="fact")
    result = await service.recall(USER, query="nota compartida", limit=2)
    assert len(result.results) == 2


async def test_context_groups_by_category_and_truncates():
    service, _, _ = make_service()
    await service.remember(USER, content="prefiero oscuro", category="preference", importance=9)
    await service.remember(USER, content="usar ruff", category="decision", project="x")
    await service.remember(
        USER, content="no tocar producción", category="constraint", importance=10
    )

    result = await service.context(USER, project="x", max_items=2, max_chars=6000)
    assert result.total_items == 2
    assert result.truncated is True
    categories = [g.category for g in result.groups]
    expected_order = ("preference", "constraint", "decision", "fact")
    assert categories == sorted(categories, key=expected_order.index)


async def test_context_without_project_returns_only_global():
    service, _, _ = make_service()
    await service.remember(USER, content="global solamente", category="preference")
    await service.remember(USER, content="solo proyecto", category="decision", project="x")
    result = await service.context(USER)
    contents = [item.content for group in result.groups for item in group.items]
    assert contents == ["global solamente"]


async def test_context_never_exceeds_max_chars():
    service, _, _ = make_service()
    await service.remember(USER, content="demasiado largo", category="preference")
    result = await service.context(USER, max_chars=5)
    assert result.total_items == 0
    assert result.truncated is True


async def test_context_checks_budget_across_categories():
    service, _, _ = make_service()
    await service.remember(USER, content="1234", category="preference")
    await service.remember(USER, content="5678", category="constraint")
    result = await service.context(USER, max_chars=6)
    contents = [item.content for group in result.groups for item in group.items]
    assert contents == ["1234"]
    assert sum(map(len, contents)) <= 6


async def test_list_memories_filters_and_paginates():
    service, _, _ = make_service()
    for i in range(4):
        await service.remember(
            USER, content=f"hecho {i}", category="fact", project="p" if i % 2 else None
        )
    page = await service.list_memories(USER, scope="global", limit=10)
    assert page.total == 2
    project_page = await service.list_memories(USER, project="p", limit=1, offset=0)
    assert len(project_page.items) == 1
    assert project_page.total == 4  # global + project "p"

    scoped_project = await service.list_memories(USER, scope="project", project="p", limit=10)
    assert scoped_project.total == 2
    assert all(item.scope == "project" and item.project == "p" for item in scoped_project.items)

    scoped_global = await service.list_memories(USER, scope="global", project="p", limit=10)
    assert scoped_global.total == 2
    assert all(item.scope == "global" for item in scoped_global.items)


async def test_list_visibility_semantics_and_project_scope_validation():
    service, _, _ = make_service()
    await service.remember(USER, content="global", category="fact")
    await service.remember(USER, content="project a", category="fact", project="a")
    await service.remember(USER, content="project b", category="fact", project="b")

    all_memories = await service.list_memories(USER, limit=10)
    assert {item.content for item in all_memories.items} == {
        "global",
        "project a",
        "project b",
    }
    project_window = await service.list_memories(USER, project="a", limit=10)
    assert {item.content for item in project_window.items} == {"global", "project a"}
    global_only = await service.list_memories(
        USER, scope="global", project="a", limit=10
    )
    assert [item.content for item in global_only.items] == ["global"]
    project_only = await service.list_memories(
        USER, scope="project", project="a", limit=10
    )
    assert [item.content for item in project_only.items] == ["project a"]
    with pytest.raises(MemoryValidationError, match="project is required"):
        await service.list_memories(USER, scope="project")
    with pytest.raises(MemoryValidationError, match="project is required"):
        await service.recall(USER, query="anything", scope="project")


async def test_forget_own_then_foreign_indistinguishable():
    service, _, _ = make_service()
    result = await service.remember(USER, content="borrable", category="fact")
    memory_id = result.memory.id

    forgotten = await service.forget(USER, memory_id)
    assert forgotten.forgotten is True

    again = await service.forget(USER, memory_id)
    assert again.forgotten is False

    foreign = await service.forget(USER, uuid.uuid4())
    assert foreign.forgotten is False

    listing = await service.list_memories(USER)
    assert listing.total == 0
