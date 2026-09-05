"""HTTP-boundary tests for the session-authenticated self-service API."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.config import Settings
from recallum.telemetry.events import ToolActivityEvent
from tests.fakes import FakeEmbeddingClient, ScriptedEmbeddingClient, build_test_container


def _login(client: TestClient, email: str, password: str = "secret") -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def _user(container, email: str, password: str = "secret"):
    user = asyncio.run(container.api_key_service().create_user(email))
    asyncio.run(container.password_service().set_password(user, password))
    return user


def _backdate(fakes, memory_id: str) -> None:
    fakes["memories"].rows[uuid.UUID(memory_id)].created_at = datetime.now(UTC) - timedelta(
        days=200
    )


def test_query_integer_contract_accepts_canonical_values_and_rejects_json_forms(monkeypatch):
    container, _fakes = build_test_container()
    user = _user(container, "strict-query@example.com")
    service = container.memory_service()
    calls = 0
    original = service.list_memories

    async def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "list_memories", counted)
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        assert client.get("/api/v1/me/memories", params={"limit": "7"}).status_code == 200
        assert calls == 1


def test_json_importance_rejects_ambiguous_and_out_of_range_values_before_service(
    monkeypatch,
):
    container, _fakes = build_test_container()
    user = _user(container, "strict-json@example.com")
    service = container.memory_service()
    calls = 0
    original = service.remember

    async def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "remember", counted)
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        for value in (True, 1.0, "7", -1, 11):
            response = client.post(
                "/api/v1/me/memories",
                json={"content": "strict", "category": "fact", "importance": value},
            )
            assert response.status_code == 422
        assert calls == 0
        assert (
            client.post(
                "/api/v1/me/memories",
                json={"content": "strict-valid", "category": "fact", "importance": 7},
            ).status_code
            == 201
        )
        assert calls == 1
        for value in ('"7"', "true", "1.0"):
            assert client.get("/api/v1/me/memories", params={"limit": value}).status_code == 422
        assert calls == 1


def test_memories_are_session_scoped_and_responses_are_filtered():
    container, fakes = build_test_container()
    alice = _user(container, "alice@example.com")
    bob = _user(container, "bob@example.com")
    app = create_app(Settings(), container)

    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        created = client.post(
            "/api/v1/me/memories",
            json={
                "content": "Use dark mode",
                "category": "preference",
                "project": "ui",
                "importance": 7,
                "metadata": {"source": "settings"},
                "user_id": str(bob.id),
            },
        )
        assert created.status_code == 201
        body = created.json()
        memory_id = body["memory"]["id"]
        assert fakes["memories"].rows[uuid.UUID(memory_id)].user_id == alice.id
        assert "embedding" not in body["memory"]
        assert "hash" not in created.text
        assert (
            client.post(
                "/api/v1/me/memories",
                json={
                    "content": "Invalid location",
                    "category": "fact",
                    "scope": "project",
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/me/memories",
                json={
                    "content": "Blank project",
                    "category": "fact",
                    "scope": "project",
                    "project": "   ",
                },
            ).status_code
            == 422
        )

        listed = client.get(
            "/api/v1/me/memories",
            params={"project": "ui", "category": "preference", "limit": 10_000},
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["limit"] == Settings().limits.list_max_limit

        profile = client.get(
            "/api/v1/me/memory-profile",
            params={"project": "ui"},
        )
        assert profile.status_code == 200
        profile_body = profile.json()
        assert profile_body["available"] is True
        assert profile_body["project"] == "ui"
        assert [item["id"] for item in profile_body["static"]] == [memory_id]
        assert "embedding" not in profile.text
        assert "content_hash" not in profile.text

        corrected = client.patch(
            f"/api/v1/me/memories/{memory_id}",
            json={
                "importance": 9,
                "metadata": {"corrected": True},
                "user_id": str(bob.id),
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["id"] == memory_id
        assert corrected.json()["content"] == "Use dark mode"
        assert (
            client.patch(f"/api/v1/me/memories/{memory_id}", json={"scope": "global"}).status_code
            == 422
        )

        _login(client, bob.email)
        assert client.get(f"/api/v1/me/memories/{memory_id}").status_code == 404
        assert client.delete(f"/api/v1/me/memories/{memory_id}").status_code == 404
        assert client.get("/api/v1/me/memories").json()["total"] == 0
        assert client.get("/api/v1/me/memory-graph").json()["total"] == 0
        assert (
            client.get(
                "/api/v1/me/memory-profile",
                params={"project": "ui"},
            ).json()["source_memory_ids"]
            == []
        )


def test_supersession_history_duplicate_and_statistics():
    container, _ = build_test_container()
    user = _user(container, "history@example.com")
    app = create_app(Settings(), container)

    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        first = client.post(
            "/api/v1/me/memories",
            json={"content": "Version one", "category": "fact"},
        ).json()["memory"]
        duplicate = client.post(
            "/api/v1/me/memories",
            json={"content": "Version one", "category": "fact"},
        )
        assert duplicate.status_code == 409
        second_response = client.post(
            f"/api/v1/me/memories/{first['id']}/supersede",
            json={"content": "Version two"},
        )
        assert second_response.status_code == 200
        second = second_response.json()["memory"]
        third = client.post(
            f"/api/v1/me/memories/{second['id']}/supersede",
            json={"content": "Version three"},
        ).json()["memory"]
        fourth = client.post(
            f"/api/v1/me/memories/{third['id']}/supersede",
            json={"content": "Version four"},
        ).json()["memory"]
        history = client.get(f"/api/v1/me/memories/{fourth['id']}/history").json()["items"]
        assert [item["content"] for item in history] == [
            "Version one",
            "Version two",
            "Version three",
        ]
        assert fourth["id"] not in {first["id"], second["id"], third["id"]}

        stats = client.get("/api/v1/me/stats").json()
        assert stats["active"] == 1
        assert stats["superseded"] == 3
        assert stats["retired"] == 0
        assert stats["volume_bytes"] > 0


def test_embedding_degradation_and_key_ownership():
    embedder = FakeEmbeddingClient()
    container, _ = build_test_container(embedder=embedder)
    alice = _user(container, "keys@example.com")
    bob = _user(container, "other@example.com")
    app = create_app(Settings(), container)

    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        created = client.post(
            "/api/v1/me/memories",
            json={"content": "Searchable phrase", "category": "fact"},
        ).json()["memory"]
        replaceable = client.post(
            "/api/v1/me/memories",
            json={"content": "Replaceable phrase", "category": "fact"},
        ).json()["memory"]
        collision_target = client.post(
            "/api/v1/me/memories",
            json={"content": "Collision target", "category": "fact"},
        ).json()["memory"]
        collision = client.post(
            f"/api/v1/me/memories/{replaceable['id']}/supersede",
            json={"content": collision_target["content"]},
        )
        assert collision.status_code == 409
        issued = client.post("/api/v1/me/api-keys", json={"password": "secret", "name": "laptop"})
        assert issued.status_code == 201
        assert issued.json()["secret"].startswith("rcl_")
        key_id = issued.json()["id"]
        assert "secret" not in client.get("/api/v1/me/api-keys").text
        assert client.post("/api/v1/me/api-keys", json={"password": "wrong"}).status_code == 403

        embedder.available = False
        recall = client.get("/api/v1/me/memories/search", params={"query": "Searchable phrase"})
        assert recall.status_code == 200
        assert recall.json()["mode"] == "degraded_textual"
        assert recall.headers["Deprecation"] == "true"
        assert recall.headers["Sunset"]
        assert recall.headers["Cache-Control"] == "no-store"
        assert recall.headers["Pragma"] == "no-cache"
        post_recall = client.post("/api/v1/me/memories/search", json={"query": "Searchable phrase"})
        assert post_recall.status_code == 200
        assert post_recall.json()["mode"] == recall.json()["mode"]
        assert [item["id"] for item in post_recall.json()["results"]] == [
            item["id"] for item in recall.json()["results"]
        ]
        assert post_recall.headers["Cache-Control"] == "no-store"
        assert client.get(f"/api/v1/me/memories/{created['id']}").status_code == 200
        assert (
            client.patch(
                f"/api/v1/me/memories/{created['id']}", json={"importance": 10}
            ).status_code
            == 200
        )
        assert client.get("/api/v1/me/memories").status_code == 200
        assert client.get("/api/v1/me/stats").status_code == 200
        assert (
            client.post(
                f"/api/v1/me/memories/{replaceable['id']}/supersede",
                json={"content": "Needs replacement vector"},
            ).status_code
            == 503
        )
        assert client.delete(f"/api/v1/me/memories/{created['id']}").status_code == 204
        unavailable = client.post(
            "/api/v1/me/memories",
            json={"content": "Needs vector", "category": "fact"},
        )
        assert unavailable.status_code == 201
        assert unavailable.json()["embedding_degraded"] is True
        assert "ollama" not in unavailable.text.lower()
        assert "http://" not in unavailable.text.lower()

        _login(client, bob.email)
        assert client.delete(f"/api/v1/me/api-keys/{key_id}").status_code == 404
        _login(client, alice.email)
        assert client.delete(f"/api/v1/me/api-keys/{key_id}").status_code == 204


def test_router_requires_session_and_empty_statistics_are_zeroed():
    container, _ = build_test_container()
    user = _user(container, "empty@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        assert client.get("/api/v1/me/memories").status_code == 401
        assert client.get("/api/v1/me/memory-graph").status_code == 401
        assert client.get("/api/v1/me/memory-profile").status_code == 401
        _login(client, user.email)
        assert client.get("/api/v1/me/memory-graph").json() == {
            "nodes": [],
            "edges": [],
            "total": 0,
            "truncated": False,
            "model_mismatch": False,
            "edge_total": 0,
            "edges_truncated": False,
        }
        assert client.get("/api/v1/me/stats").json() == {
            "active": 0,
            "superseded": 0,
            "retired": 0,
            "by_category": {},
            "by_scope": {},
            "by_project": {},
            "by_importance": {},
            "created_by_day": {},
            "volume_bytes": 0,
        }
        activity = client.get("/api/v1/me/activity")
        assert activity.status_code == 200
        assert activity.json()["total_calls"] == 0
        assert activity.json()["failure_rate"] == 0.0
        assert activity.json()["degradation_rate"] == 0.0
        assert activity.json()["by_day"] == {}


def test_memory_graph_contract_filters_and_omits_vectors():
    vectors = {
        "global graph": [1.0, 0.0],
        "project graph": [1.0, 0.0],
        "other project": [1.0, 0.0],
    }
    container, fakes = build_test_container(embedder=ScriptedEmbeddingClient(vectors))
    user = _user(container, "graph@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        client.post(
            "/api/v1/me/memories",
            json={"content": "global graph", "category": "fact", "importance": 8},
        )
        client.post(
            "/api/v1/me/memories",
            json={
                "content": "project graph",
                "category": "preference",
                "project": "alpha",
                "importance": 7,
            },
        )
        other = client.post(
            "/api/v1/me/memories",
            json={"content": "other project", "category": "fact", "project": "beta"},
        )
        fakes["memories"].rows[
            uuid.UUID(other.json()["memory"]["id"])
        ].embedding_model = "legacy-model"

        response = client.get(
            "/api/v1/me/memory-graph",
            params={"project": "alpha", "limit": 10_000},
        )

        assert response.status_code == 200
        body = response.json()
        assert {node["content"] for node in body["nodes"]} == {
            "global graph",
            "project graph",
        }
        assert len(body["edges"]) == 1
        assert body["edges"][0]["source_id"] < body["edges"][0]["target_id"]
        assert body["total"] == 2
        assert body["truncated"] is False
        assert body["model_mismatch"] is False
        assert "embedding" not in response.text
        assert "metadata" not in response.text

        whole_graph = client.get("/api/v1/me/memory-graph").json()
        connected_ids = {edge["source_id"] for edge in whole_graph["edges"]} | {
            edge["target_id"] for edge in whole_graph["edges"]
        }
        assert other.json()["memory"]["id"] not in connected_ids
        assert whole_graph["model_mismatch"] is True

        truncated = client.get("/api/v1/me/memory-graph", params={"limit": 1}).json()
        assert len(truncated["nodes"]) == 1
        assert truncated["total"] == 3
        assert truncated["truncated"] is True


def test_activity_endpoint_is_authenticated_and_user_scoped():
    container, fakes = build_test_container()
    alice = _user(container, "activity@example.com")
    bob = _user(container, "other-activity@example.com")
    now = datetime.now(UTC)
    fakes["telemetry"].events = [
        ToolActivityEvent(
            user_id=alice.id,
            tool_name="recall",
            project="alpha",
            duration_ms=2,
            result_count=3,
            degraded=True,
            failed=False,
            created_at=now,
        ),
        ToolActivityEvent(
            user_id=bob.id,
            tool_name="remember",
            project="secret",
            duration_ms=2,
            result_count=1,
            degraded=False,
            failed=True,
            created_at=now,
        ),
    ]
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        assert client.get("/api/v1/me/activity").status_code == 401
        _login(client, alice.email)
        response = client.get("/api/v1/me/activity")
        assert response.status_code == 200
        body = response.json()
        assert body["total_calls"] == 1
        assert body["total_results"] == 3
        assert body["degraded_calls"] == 1
        assert body["degradation_rate"] == 1.0
        assert body["by_tool"] == {"recall": 1}
        assert body["by_project"] == {"alpha": 1}
        assert "secret" not in response.text
        too_wide = client.get(
            "/api/v1/me/activity",
            params={
                "start": "2025-01-01T00:00:00Z",
                "end": "2026-01-01T00:00:00Z",
            },
        )
        assert too_wide.status_code == 422
        assert "90 days" in too_wide.text


def test_versioned_openapi_matches_web_app_only():
    from scripts.export_web_openapi import OUTPUT, rendered_contract

    expected = rendered_contract()
    assert OUTPUT.read_text() == expected
    schema = json.loads(expected)
    assert "/me/memories" in schema["paths"]
    assert "/me/memory-profile" in schema["paths"]
    assert "/healthz" not in schema["paths"]
    assert "/readyz" not in schema["paths"]
    assert "/mcp" not in schema["paths"]
    serialized = json.dumps(schema)
    assert "content_hash" not in serialized
    assert "key_hash" not in serialized
    assert Path(OUTPUT).name == "web-v1.json"

    schemes = schema["components"]["securitySchemes"]
    cookie = next(iter(schemes.values()))
    assert cookie["type"] == "apiKey"
    assert cookie["in"] == "cookie"
    login = schema["paths"]["/auth/login"]["post"]
    assert login.get("security") in ([], None) or login["security"] == []
    protected = schema["paths"]["/auth/me"]["get"]
    assert protected.get("security")
    search = schema["paths"]["/me/memories/search"]
    assert "post" in search
    assert search["get"]["deprecated"] is True
    documented = set()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            documented.update(operation.get("responses", {}))
    for code in ("401", "403", "413", "422", "429", "503"):
        assert code in documented


def test_search_post_rejects_invalid_bodies_and_get_keeps_query_out_of_logs(caplog):
    container, _ = build_test_container()
    alice = _user(container, "search-contract@example.com")
    app = create_app(Settings(), container)
    sentinel = "SENTINEL_SEARCH_QUERY_SHOULD_NOT_LOG"
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        assert client.post("/api/v1/me/memories/search", json={}).status_code == 422
        assert client.post("/api/v1/me/memories/search", json={"query": ""}).status_code == 422
        assert client.post("/api/v1/me/memories/search", json={"query": 1}).status_code == 422
        with caplog.at_level("DEBUG"):
            response = client.get("/api/v1/me/memories/search", params={"query": sentinel})
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert response.headers["Sunset"] == Settings().web.get_search_sunset
        assert sentinel not in caplog.text
        assert all(sentinel not in record.getMessage() for record in caplog.records)


def test_auth_and_private_responses_set_no_store_cache_headers():
    container, _ = build_test_container()
    alice = _user(container, "cache@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": alice.email, "password": "secret"},
        )
        assert login.status_code == 200
        assert login.headers["Cache-Control"] == "no-store"
        assert login.headers["Pragma"] == "no-cache"
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.headers["Cache-Control"] == "no-store"
        assert me.headers["Pragma"] == "no-cache"
        denied = TestClient(app, base_url="https://recallum.test").get("/api/v1/auth/me")
        assert denied.status_code == 401
        assert denied.headers["Cache-Control"] == "no-store"


def test_reassign_project_moves_memories_and_reports_conflicts():
    container, fakes = build_test_container()
    alice = _user(container, "alice@example.com")
    app = create_app(Settings(), container)

    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)

        def create(content: str, project: str) -> str:
            response = client.post(
                "/api/v1/me/memories",
                json={"content": content, "category": "fact", "project": project},
            )
            assert response.status_code == 201
            return response.json()["memory"]["id"]

        moved_id = create("only in the old key", "local:old")
        conflict_id = create("present in both keys", "local:old")
        create("present in both keys", "remote:new")

        result = client.post(
            "/api/v1/me/memories/reassign-project",
            json={"from_project": "local:old", "to_project": "remote:new"},
        )
        assert result.status_code == 200
        body = result.json()
        assert body["moved"] == 1
        assert body["conflicts"] == [conflict_id]
        assert fakes["memories"].rows[uuid.UUID(moved_id)].project == "remote:new"

        rejected = client.post(
            "/api/v1/me/memories/reassign-project",
            json={"from_project": "remote:new", "to_project": "remote:new"},
        )
        assert rejected.status_code == 422

        # Freshness and usage signals are part of the memory payload now.
        detail = client.get(f"/api/v1/me/memories/{moved_id}")
        assert detail.status_code == 200
        assert detail.json()["recall_count"] == 0
        assert "reconfirmed_at" in detail.json()


def test_related_neighbours_are_bounded_vector_free_and_delegate(monkeypatch):
    vectors = {
        "seed phrase": [1.0, 0.0],
        "related one": [1.0, 0.05],
        "related two": [1.0, 0.1],
        "related three": [1.0, 0.15],
        "related four": [1.0, 0.2],
        "related five": [1.0, 0.25],
        "unrelated topic": [0.0, 1.0],
    }
    container, _fakes = build_test_container(embedder=ScriptedEmbeddingClient(vectors))
    user = _user(container, "related@example.com")
    service = container.memory_service()
    calls = []
    original = service.related_memories

    async def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "related_memories", counted)
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)

        def create(content: str) -> dict:
            return client.post(
                "/api/v1/me/memories", json={"content": content, "category": "fact"}
            ).json()["memory"]

        seed = create("seed phrase")
        related_ids = {
            create(content)["id"]
            for content in (
                "related one",
                "related two",
                "related three",
                "related four",
                "related five",
            )
        }
        create("unrelated topic")

        response = client.get(f"/api/v1/me/memories/{seed['id']}/related")
        assert response.status_code == 200
        body = response.json()
        assert body["memory_id"] == seed["id"]
        assert len(body["related"]) <= Settings().limits.graph_max_neighbours
        assert {item["id"] for item in body["related"]} <= related_ids
        assert body["related"][0]["content"] == "related one"
        assert "embedding" not in response.text
        assert "hash" not in response.text
        assert calls[-1][0][0] == user.id
        assert calls[-1][0][1] == uuid.UUID(seed["id"])
        assert calls[-1][1] == {"limit": None}

        bounded = client.get(f"/api/v1/me/memories/{seed['id']}/related", params={"limit": 2})
        assert bounded.status_code == 200
        assert len(bounded.json()["related"]) == 2
        assert calls[-1][1] == {"limit": 2}
        assert (
            client.get(f"/api/v1/me/memories/{seed['id']}/related", params={"limit": 0}).status_code
            == 422
        )
        assert (
            client.get(
                f"/api/v1/me/memories/{seed['id']}/related", params={"limit": "two"}
            ).status_code
            == 422
        )
        assert calls[-1][1] == {"limit": 2}


def test_related_neighbours_of_unknown_foreign_and_retired_seeds_are_indistinguishable():
    container, _ = build_test_container()
    alice = _user(container, "alice-related@example.com")
    bob = _user(container, "bob-related@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        client.post(
            "/api/v1/me/memories", json={"content": "alice active seed", "category": "fact"}
        )
        retired = client.post(
            "/api/v1/me/memories", json={"content": "alice to retire", "category": "fact"}
        ).json()["memory"]
        client.post(
            f"/api/v1/me/memories/{retired['id']}/supersede",
            json={"content": "alice replacement"},
        )
        _login(client, bob.email)
        foreign = client.post(
            "/api/v1/me/memories", json={"content": "bob secret seed", "category": "constraint"}
        ).json()["memory"]
        _login(client, alice.email)

        for seed_id in (str(uuid.uuid4()), foreign["id"], retired["id"]):
            response = client.get(f"/api/v1/me/memories/{seed_id}/related")
            assert response.status_code == 200
            assert response.json() == {"memory_id": seed_id, "related": []}
            assert "bob secret seed" not in response.text


def test_reconfirm_flips_stale_status_and_is_visible_on_read():
    container, fakes = build_test_container()
    user = _user(container, "reconfirm@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        memory = client.post(
            "/api/v1/me/memories", json={"content": "still true", "category": "fact"}
        ).json()["memory"]
        _backdate(fakes, memory["id"])

        stale_before = client.get("/api/v1/me/memories", params={"stale": "true"}).json()
        assert [item["id"] for item in stale_before["items"]] == [memory["id"]]
        assert "embedding" not in client.get("/api/v1/me/memories", params={"stale": "true"}).text

        response = client.post(f"/api/v1/me/memories/{memory['id']}/reconfirm")
        assert response.status_code == 200
        body = response.json()
        assert body["reconfirmed"] is True
        assert body["memory"]["id"] == memory["id"]
        assert body["memory"]["content"] == "still true"
        stamped = datetime.fromisoformat(body["memory"]["reconfirmed_at"])
        assert abs((datetime.now(UTC) - stamped).total_seconds()) < 60
        assert "embedding" not in response.text
        assert "hash" not in response.text

        detail = client.get(f"/api/v1/me/memories/{memory['id']}").json()
        assert detail["reconfirmed_at"] == body["memory"]["reconfirmed_at"]
        assert detail["content"] == "still true"
        stale_ids = {
            item["id"]
            for item in client.get("/api/v1/me/memories", params={"stale": "true"}).json()["items"]
        }
        fresh_ids = {
            item["id"]
            for item in client.get("/api/v1/me/memories", params={"stale": "false"}).json()["items"]
        }
        assert memory["id"] not in stale_ids
        assert memory["id"] in fresh_ids


def test_reconfirm_rejects_unknown_foreign_and_retired_without_changes():
    container, fakes = build_test_container()
    alice = _user(container, "alice-rec@example.com")
    bob = _user(container, "bob-rec@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        client.post("/api/v1/me/memories", json={"content": "alice stays", "category": "fact"})
        retired = client.post(
            "/api/v1/me/memories", json={"content": "alice retires", "category": "fact"}
        ).json()["memory"]
        client.post(
            f"/api/v1/me/memories/{retired['id']}/supersede",
            json={"content": "alice next"},
        )
        _login(client, bob.email)
        bob_memory = client.post(
            "/api/v1/me/memories", json={"content": "bob rec stays", "category": "constraint"}
        ).json()["memory"]
        _login(client, alice.email)

        outcomes = [
            client.post(f"/api/v1/me/memories/{str(uuid.uuid4())}/reconfirm"),
            client.post(f"/api/v1/me/memories/{bob_memory['id']}/reconfirm"),
            client.post(f"/api/v1/me/memories/{retired['id']}/reconfirm"),
        ]
        for response in outcomes:
            assert response.status_code == 404
            assert response.json() == {"detail": "Memory not found"}

        _login(client, bob.email)
        bob_detail = client.get(f"/api/v1/me/memories/{bob_memory['id']}").json()
        assert bob_detail["reconfirmed_at"] is None


def test_merge_retires_sources_links_history_and_is_idempotent():
    container, _ = build_test_container()
    user = _user(container, "merge@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        first = client.post(
            "/api/v1/me/memories", json={"content": "merge source one", "category": "fact"}
        ).json()["memory"]
        second = client.post(
            "/api/v1/me/memories", json={"content": "merge source two", "category": "fact"}
        ).json()["memory"]

        response = client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [first["id"], second["id"]],
                "content": "merged claim",
                "category": "fact",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["merged"] is True
        assert set(body["superseded_ids"]) == {first["id"], second["id"]}
        survivor = body["memory"]
        assert survivor["id"] not in {first["id"], second["id"]}
        assert survivor["content"] == "merged claim"
        assert "embedding" not in response.text
        assert "hash" not in response.text

        assert client.get(f"/api/v1/me/memories/{first['id']}").status_code == 404
        assert client.get(f"/api/v1/me/memories/{second['id']}").status_code == 404
        history = client.get(f"/api/v1/me/memories/{survivor['id']}/history").json()["items"]
        assert {item["content"] for item in history} == {"merge source one", "merge source two"}

        again = client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [first["id"], second["id"]],
                "content": "merged claim",
                "category": "fact",
            },
        )
        assert again.status_code == 404
        assert client.get("/api/v1/me/stats").json()["active"] == 1


def test_merge_validation_matrix_is_rejected_without_mutation():
    container, _ = build_test_container()
    user = _user(container, "merge-validation@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)

        def create(content: str, project: str | None = None) -> dict:
            payload = {"content": content, "category": "fact"}
            if project is not None:
                payload["project"] = project
            return client.post("/api/v1/me/memories", json=payload).json()["memory"]

        a = create("mv source a")
        b = create("mv source b")
        project_x = create("mv x one", project="x")
        project_y = create("mv y one", project="y")
        many = [create(f"mv many {index}") for index in range(11)]

        invalid = [
            {"source_ids": [a["id"]], "content": "x", "category": "fact"},
            {"source_ids": [a["id"], a["id"]], "content": "x", "category": "fact"},
            {"source_ids": [m["id"] for m in many], "content": "x", "category": "fact"},
            {"source_ids": [a["id"], b["id"]], "content": "   ", "category": "fact"},
            {"source_ids": [project_x["id"], project_y["id"]], "content": "x", "category": "fact"},
        ]
        for payload in invalid:
            assert client.post("/api/v1/me/memories/merge", json=payload).status_code == 422
        assert (
            client.post(
                "/api/v1/me/memories/merge",
                json={"source_ids": [a["id"], b["id"]], "content": "x", "category": "nonsense"},
            ).status_code
            == 422
        )
        for memory in (a, b, project_x, project_y):
            assert client.get(f"/api/v1/me/memories/{memory['id']}").status_code == 200
        assert client.get("/api/v1/me/stats").json()["active"] == 15


def test_merge_with_foreign_source_fails_for_both_users():
    container, _ = build_test_container()
    alice = _user(container, "alice-merge@example.com")
    bob = _user(container, "bob-merge@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, alice.email)
        alice_memory = client.post(
            "/api/v1/me/memories", json={"content": "alice merge", "category": "fact"}
        ).json()["memory"]
        _login(client, bob.email)
        bob_memory = client.post(
            "/api/v1/me/memories", json={"content": "bob merge", "category": "fact"}
        ).json()["memory"]
        _login(client, alice.email)

        response = client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [alice_memory["id"], bob_memory["id"]],
                "content": "cross user merge",
                "category": "fact",
            },
        )
        assert response.status_code == 404
        assert client.get(f"/api/v1/me/memories/{alice_memory['id']}").status_code == 200
        _login(client, bob.email)
        assert client.get(f"/api/v1/me/memories/{bob_memory['id']}").status_code == 200


def test_merge_literal_route_is_not_captured_by_parametrized_routes(monkeypatch):
    container, _ = build_test_container()
    user = _user(container, "ordering@example.com")
    service = container.memory_service()
    calls = []
    original = service.merge

    async def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "merge", counted)
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        memory = client.post(
            "/api/v1/me/memories", json={"content": "literal route", "category": "fact"}
        ).json()["memory"]
        response = client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [str(uuid.uuid4()), memory["id"]],
                "content": "x",
                "category": "fact",
            },
        )
        # The literal path matched: the service was reached with the real body,
        # never an invalid-uuid 422 for a captured ``{memory_id}`` route.
        assert response.status_code == 404
        assert len(calls) == 1
        assert calls[0][0][0] == user.id
        assert str(calls[0][1]["source_ids"][1]) == memory["id"]


def test_stale_filter_reaches_service_with_the_authenticated_user(monkeypatch):
    container, fakes = build_test_container()
    user = _user(container, "stale-queue@example.com")
    service = container.memory_service()
    calls = []
    original = service.list_memories

    async def counted(user_id, **kwargs):
        calls.append((user_id, kwargs))
        return await original(user_id, **kwargs)

    monkeypatch.setattr(service, "list_memories", counted)
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        fresh = client.post(
            "/api/v1/me/memories", json={"content": "fresh memory", "category": "fact"}
        ).json()["memory"]
        stale = client.post(
            "/api/v1/me/memories", json={"content": "old memory", "category": "fact"}
        ).json()["memory"]
        _backdate(fakes, stale["id"])

        stale_response = client.get("/api/v1/me/memories", params={"stale": "true"})
        assert stale_response.status_code == 200
        assert [item["id"] for item in stale_response.json()["items"]] == [stale["id"]]
        assert "embedding" not in stale_response.text
        assert calls[-1][0] == user.id
        assert calls[-1][1]["stale"] is True

        fresh_response = client.get("/api/v1/me/memories", params={"stale": "false"})
        assert [item["id"] for item in fresh_response.json()["items"]] == [fresh["id"]]
        assert calls[-1][1]["stale"] is False

        unfiltered = client.get("/api/v1/me/memories")
        assert len(unfiltered.json()["items"]) == 2
        assert calls[-1][1]["stale"] is None


def test_reconfirm_merge_and_related_delegate_with_forwarded_params(monkeypatch):
    container, _ = build_test_container()
    user = _user(container, "delegation@example.com")
    service = container.memory_service()
    calls = {"related": [], "reconfirm": [], "merge": []}
    originals = {
        "related": service.related_memories,
        "reconfirm": service.reconfirm,
        "merge": service.merge,
    }

    def make_spy(name: str):
        async def spy(*args, **kwargs):
            calls[name].append((args, kwargs))
            return await originals[name](*args, **kwargs)

        return spy

    monkeypatch.setattr(service, "related_memories", make_spy("related"))
    monkeypatch.setattr(service, "reconfirm", make_spy("reconfirm"))
    monkeypatch.setattr(service, "merge", make_spy("merge"))
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        first = client.post(
            "/api/v1/me/memories", json={"content": "delegate first", "category": "fact"}
        ).json()["memory"]
        second = client.post(
            "/api/v1/me/memories", json={"content": "delegate second", "category": "fact"}
        ).json()["memory"]

        client.get(f"/api/v1/me/memories/{first['id']}/related", params={"limit": 2})
        client.post(f"/api/v1/me/memories/{second['id']}/reconfirm")
        client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [first["id"], second["id"]],
                "content": "delegated merge",
                "category": "fact",
                "importance": 7,
                "metadata": {"k": "v"},
                "source_client": "test",
            },
        )

        assert calls["related"] == [((user.id, uuid.UUID(first["id"])), {"limit": 2})]
        assert calls["reconfirm"] == [((user.id, uuid.UUID(second["id"])), {})]
        args, kwargs = calls["merge"][0]
        assert args == (user.id,)
        assert kwargs == {
            "source_ids": [uuid.UUID(first["id"]), uuid.UUID(second["id"])],
            "content": "delegated merge",
            "category": "fact",
            "importance": 7,
            "metadata": {"k": "v"},
            "source_client": "test",
        }


def test_create_search_list_and_patch_accept_optional_kind():
    container, _ = build_test_container()
    user = _user(container, "kind@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        omitted = client.post(
            "/api/v1/me/memories",
            json={"content": "no kind stated", "category": "fact"},
        )
        assert omitted.status_code == 201
        assert omitted.json()["memory"]["kind"] is None

        created = client.post(
            "/api/v1/me/memories",
            json={
                "content": "clearing the cache fixed the build",
                "category": "fact",
                "kind": "solution",
            },
        )
        assert created.status_code == 201
        memory = created.json()["memory"]
        assert memory["kind"] == "solution"

        searched = client.post(
            "/api/v1/me/memories/search",
            json={"query": "clearing the cache", "kind": "solution"},
        )
        assert searched.status_code == 200
        assert any(item["id"] == memory["id"] for item in searched.json()["results"])

        searched_wrong_kind = client.post(
            "/api/v1/me/memories/search",
            json={"query": "clearing the cache", "kind": "failure"},
        )
        assert searched_wrong_kind.status_code == 200
        assert searched_wrong_kind.json()["results"] == []

        listed = client.get("/api/v1/me/memories", params={"kind": "solution"})
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        listed_unfiltered = client.get("/api/v1/me/memories")
        assert listed_unfiltered.status_code == 200
        assert listed_unfiltered.json()["total"] == 2

        patched = client.patch(
            f"/api/v1/me/memories/{memory['id']}",
            json={"kind": "architecture"},
        )
        assert patched.status_code == 200
        assert patched.json()["kind"] == "architecture"

        rejected = client.post(
            "/api/v1/me/memories",
            json={"content": "a durable todo", "category": "fact", "kind": "todo"},
        )
        assert rejected.status_code == 422


def test_create_and_patch_accept_optional_source_provenance():
    container, _ = build_test_container()
    user = _user(container, "provenance@example.com")
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.test") as client:
        _login(client, user.email)
        omitted = client.post(
            "/api/v1/me/memories",
            json={"content": "no provenance", "category": "fact"},
        )
        assert omitted.status_code == 201
        omitted_memory = omitted.json()["memory"]
        assert omitted_memory["source_type"] == "unknown"
        assert omitted_memory["source_ref"] is None

        created = client.post(
            "/api/v1/me/memories",
            json={
                "content": "agent asserted",
                "category": "fact",
                "source_type": "agent",
                "source_ref": "src/app.py",
            },
        )
        assert created.status_code == 201
        memory = created.json()["memory"]
        assert memory["source_type"] == "agent"
        assert memory["source_ref"] == "src/app.py"

        patched = client.patch(
            f"/api/v1/me/memories/{memory['id']}",
            json={"source_type": "user", "source_ref": "src/web.py"},
        )
        assert patched.status_code == 200
        assert patched.json()["id"] == memory["id"]
        assert patched.json()["source_type"] == "user"
        assert patched.json()["source_ref"] == "src/web.py"

        fetched = client.get(f"/api/v1/me/memories/{memory['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["source_type"] == "user"
        assert fetched.json()["source_ref"] == "src/web.py"
