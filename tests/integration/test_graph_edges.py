"""S007: response-level graph edge parity between the pairwise and scalable paths.

Runs against the real PostgreSQL+pgvector adapter via the ``container``
fixture, so both edge strategies are the real SQL implementations and the
assertions compare their responses (edge sets, ordering, and the
``edge_total``/``edges_truncated`` signals) exactly.
"""

from __future__ import annotations

import hashlib
import math
import uuid

import pytest

from recallum.memory.limits import MemoryLimits
from recallum.memory.service import MemoryService

pytestmark = pytest.mark.integration


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _vector(*components: float) -> list[float]:
    vector = [0.0] * 768
    for index, value in enumerate(components):
        vector[index] = value
    return vector


def _angled(angle_degrees: float) -> list[float]:
    radians = math.radians(angle_degrees)
    return _vector(math.cos(radians), math.sin(radians))


async def _user(container) -> uuid.UUID:
    user = await container.api_key_service().create_user(
        f"graph-{uuid.uuid4().hex[:8]}@example.com"
    )
    return user.id


async def _seed(repo, user_id, content, embedding, *, model="contract-model"):
    return await repo.create_memory(
        user_id,
        scope="global",
        project=None,
        category="fact",
        content=content,
        content_hash=_hash(content),
        embedding=embedding,
        embedding_model=model,
        importance=5,
        source_client=None,
        metadata={},
    )


def _service(repo, embeddings, **limits) -> MemoryService:
    return MemoryService(
        repository=repo,
        embeddings=embeddings,
        limits=MemoryLimits(**limits),
    )


def _edges(graph) -> set[frozenset[uuid.UUID]]:
    return {frozenset((edge.source_id, edge.target_id)) for edge in graph.edges}


def _edge_rows(graph) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    return [(edge.source_id, edge.target_id, edge.similarity) for edge in graph.edges]


async def test_graph_response_parity_across_routing_paths(container):
    repo = container.memory_repository()
    user_id = await _user(container)
    for index, angle in enumerate([0, 10, 20, 30, 40, 50]):
        await _seed(repo, user_id, f"parity {index}", _angled(angle))

    pairwise = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=10, graph_min_similarity=0.8,
    )
    flag_only = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=10, graph_min_similarity=0.8,
        graph_scalable_enabled=True, graph_scalable_min_nodes=1000,
    )
    threshold_only = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=10, graph_min_similarity=0.8,
        graph_scalable_enabled=False, graph_scalable_min_nodes=3,
    )

    reference = await pairwise.memory_graph(user_id)
    for routed in (flag_only, threshold_only):
        graph = await routed.memory_graph(user_id)
        assert _edges(graph) == _edges(reference)
        assert _edge_rows(graph) == _edge_rows(reference)
        assert graph.edge_total == reference.edge_total
        assert graph.edges_truncated == reference.edges_truncated
        assert (graph.total, graph.truncated) == (reference.total, reference.truncated)
    assert reference.edge_total == 12
    assert reference.edges_truncated is False


async def test_graph_dense_hub_truncation_parity_across_paths(container):
    repo = container.memory_repository()
    user_id = await _user(container)
    hub = await _seed(repo, user_id, "dense hub", _vector(1.0))
    near_ids = [
        (await _seed(repo, user_id, "dense near 1", _vector(0.8660254, 0.5))).id,
        (await _seed(repo, user_id, "dense near 2", _vector(0.8660254, 0.0, 0.5))).id,
        (await _seed(repo, user_id, "dense near 3", _vector(0.8660254, 0.0, -0.5))).id,
    ]
    hub_pairs = {
        frozenset((hub.id, near_id)) for near_id in near_ids
    }

    pairwise = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=2, graph_min_similarity=0.8,
    )
    scalable = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=2, graph_min_similarity=0.8,
        graph_scalable_enabled=True, graph_scalable_min_nodes=1000,
    )

    pairwise_result = await pairwise.memory_graph(user_id)
    scalable_result = await scalable.memory_graph(user_id)

    assert _edges(pairwise_result) == _edges(scalable_result)
    assert len(pairwise_result.edges) == 2
    assert _edges(pairwise_result) <= hub_pairs
    assert pairwise_result.edge_total == scalable_result.edge_total == 3
    assert pairwise_result.edge_total > len(pairwise_result.edges)
    assert pairwise_result.edges_truncated is scalable_result.edges_truncated is True


async def test_graph_scalable_invents_no_neighbours_below_threshold(container):
    repo = container.memory_repository()
    user_id = await _user(container)
    seed = await _seed(repo, user_id, "seed", _vector(1.0, 0.0))
    close = await _seed(repo, user_id, "close", _vector(0.99, 0.1))
    distant = await _seed(repo, user_id, "distant", _vector(-0.9, 0.44))

    service = _service(
        repo, container.embedding_client(),
        graph_min_similarity=0.7, graph_scalable_enabled=True,
    )
    graph = await service.memory_graph(user_id)

    assert _edges(graph) == {frozenset((seed.id, close.id))}
    assert distant.id not in {node for pair in _edges(graph) for node in pair}
    assert graph.edge_total == 1
    assert graph.edges_truncated is False


async def test_graph_scalable_excludes_cross_model_pairs(container):
    repo = container.memory_repository()
    user_id = await _user(container)
    first = await _seed(repo, user_id, "first", _vector(1.0, 0.0))
    second = await _seed(repo, user_id, "second", _vector(1.0, 0.0))
    await _seed(repo, user_id, "other model", _vector(1.0, 0.0), model="other-model")

    service = _service(
        repo, container.embedding_client(),
        graph_min_similarity=0.7, graph_scalable_enabled=True,
    )
    graph = await service.memory_graph(user_id)

    assert _edges(graph) == {frozenset((first.id, second.id))}
    assert graph.edge_total == 1
    assert graph.edges_truncated is False
    assert graph.model_mismatch is True


async def test_related_memories_unchanged_by_activation_state(container):
    repo = container.memory_repository()
    user_id = await _user(container)
    seed = await _seed(repo, user_id, "related seed", _vector(1.0, 0.0))
    neighbours = [
        await _seed(repo, user_id, f"related neighbour {index}", _vector(1.0, 0.0))
        for index in range(3)
    ]
    await _seed(repo, user_id, "foreign model", _vector(1.0, 0.0), model="other-model")

    pairwise = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=2, graph_min_similarity=0.7,
    )
    scalable = _service(
        repo, container.embedding_client(),
        graph_max_neighbours=2, graph_min_similarity=0.7,
        graph_scalable_enabled=True, graph_scalable_min_nodes=1,
    )

    pairwise_result = await pairwise.related_memories(user_id, seed.id, limit=999)
    scalable_result = await scalable.related_memories(user_id, seed.id, limit=999)

    assert [(item.id, item.similarity) for item in pairwise_result.related] == [
        (item.id, item.similarity) for item in scalable_result.related
    ]
    assert len(pairwise_result.related) == 2
    assert {item.id for item in pairwise_result.related} <= {
        neighbour.id for neighbour in neighbours
    }
    assert all(item.similarity >= 0.7 for item in pairwise_result.related)
