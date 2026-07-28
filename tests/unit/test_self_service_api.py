"""HTTP-boundary tests for the session-authenticated self-service API."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.config import Settings
from recallum.telemetry.events import ToolActivityEvent
from tests.fakes import FakeEmbeddingClient, build_test_container


def _login(client: TestClient, email: str, password: str = "secret") -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def _user(container, email: str, password: str = "secret"):
    user = asyncio.run(container.api_key_service().create_user(email))
    asyncio.run(container.password_service().set_password(user, password))
    return user


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
        assert "embedding" not in created.text
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
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "embeddings_unavailable"
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
        _login(client, user.email)
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
    assert "/healthz" not in schema["paths"]
    assert "/readyz" not in schema["paths"]
    assert "/mcp" not in schema["paths"]
    serialized = json.dumps(schema)
    assert "content_hash" not in serialized
    assert "key_hash" not in serialized
    assert Path(OUTPUT).name == "web-v1.json"
