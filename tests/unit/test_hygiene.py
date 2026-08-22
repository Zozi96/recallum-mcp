"""Unit tests for the read-only corpus-hygiene report."""

from __future__ import annotations

import hashlib
import uuid

from recallum.cli import _run, build_parser
from recallum.hygiene import build_hygiene_report, render_hygiene_report
from tests.fakes import build_test_container

USER_ID = uuid.uuid4()


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


async def _seed(memories, *, content, embedding, scope="global", project=None, **kwargs):
    return await memories.create_memory(
        USER_ID,
        scope=scope,
        project=project,
        category=kwargs.pop("category", "fact"),
        content=content,
        content_hash=_hash(content),
        embedding=embedding,
        embedding_model=kwargs.pop("embedding_model", "test-model"),
        importance=kwargs.pop("importance", 5),
        source_client=None,
        metadata={},
    )


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


async def test_clusters_similar_memories_within_one_bucket():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    v = [1.0, 0.0, 0.0]
    await _seed(memories, content="user prefers dark mode", embedding=v)
    await _seed(memories, content="user likes dark mode enabled", embedding=v)
    await _seed(memories, content="totally unrelated fact about pizza", embedding=[0.0, 1.0, 0.0])

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9)

    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert len(cluster.members) == 2
    assert cluster.bucket == ("global", None)
    assert cluster.min_similarity == cluster.max_similarity == 1.0
    text = render_hygiene_report(report)
    assert "merge candidates (same-bucket)" in text
    assert "cluster 1 [global]" in text


async def test_clusters_never_cross_scope_project_buckets():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    v = [1.0, 0.0, 0.0]
    # Two memories in the global bucket, one in project "alpha" -- all three
    # share the same embedding (similarity 1.0 across every pair), so a
    # bucket-blind clusterer would merge all three into one cluster.
    m1 = await _seed(memories, content="use pnpm for installs", embedding=v)
    m2 = await _seed(memories, content="use pnpm, not npm, for installs", embedding=v)
    await _seed(
        memories, content="use pnpm for installs", embedding=v, scope="project", project="alpha"
    )

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9)

    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.bucket == ("global", None)
    assert {m.id for m in cluster.members} == {m1.id, m2.id}


async def test_contradiction_candidate_flags_asymmetric_negation_cue():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    v = [1.0, 0.0, 0.0]
    await _seed(memories, content="user prefers dark mode", embedding=v)
    await _seed(memories, content="user no longer prefers dark mode", embedding=v)

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9)

    assert len(report.contradictions) == 1
    candidate = report.contradictions[0]
    assert candidate.cue == "no longer"
    assert "no longer" in candidate.with_cue.content
    assert "no longer" not in candidate.without_cue.content
    text = render_hygiene_report(report)
    assert "contradiction candidates" in text
    assert "cue='no longer'" in text


async def test_no_contradiction_when_cues_appear_on_both_sides_or_neither():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    v = [1.0, 0.0, 0.0]
    await _seed(memories, content="user prefers dark mode always", embedding=v)
    await _seed(memories, content="user prefers dark mode consistently", embedding=v)

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9)

    assert report.contradictions == []


async def test_cap_is_applied_and_reported_when_hit():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    for i in range(3):
        await _seed(memories, content=f"fact number {i}", embedding=[float(i), 1.0, 0.0])

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9, limit=2)

    assert report.scanned == 2
    assert report.capped is True
    assert report.cap == 2
    text = render_hygiene_report(report)
    assert "capped at 2" in text


async def test_no_cap_reported_when_under_limit():
    container, fakes = build_test_container()
    memories = fakes["memories"]
    await _seed(memories, content="one fact", embedding=[1.0, 0.0, 0.0])

    report = await build_hygiene_report(memories, USER_ID, min_similarity=0.9, limit=500)

    assert report.capped is False
    assert "capped" not in render_hygiene_report(report)


async def test_cli_hygiene_command_performs_no_writes(capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "hygiene@example.com"]), container)
    user = await fakes["users"].get_by_email("hygiene@example.com")
    v = [1.0, 0.0, 0.0]
    await fakes["memories"].create_memory(
        user.id,
        scope="global",
        project=None,
        category="fact",
        content="dark mode on",
        content_hash=_hash("dark mode on"),
        embedding=v,
        embedding_model="test-model",
        importance=5,
        source_client=None,
        metadata={},
    )
    await fakes["memories"].create_memory(
        user.id,
        scope="global",
        project=None,
        category="fact",
        content="dark mode is no longer on",
        content_hash=_hash("dark mode is no longer on"),
        embedding=v,
        embedding_model="test-model",
        importance=5,
        source_client=None,
        metadata={},
    )
    before = {
        memory_id: (row.deleted_at, row.content, row.superseded_by)
        for memory_id, row in fakes["memories"].rows.items()
    }
    capsys.readouterr()

    code = await _run(parse(["hygiene", "--email", "hygiene@example.com"]), container)

    assert code == 0
    out = capsys.readouterr().out
    assert "merge candidates" in out
    assert "contradiction candidates" in out
    after = {
        memory_id: (row.deleted_at, row.content, row.superseded_by)
        for memory_id, row in fakes["memories"].rows.items()
    }
    assert before == after
    assert set(before) == set(after)


async def test_cli_hygiene_command_unknown_email_exits_1(capsys):
    container, _ = build_test_container()

    code = await _run(parse(["hygiene", "--email", "ghost@example.com"]), container)

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not exist" in captured.err
