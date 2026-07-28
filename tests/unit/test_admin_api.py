"""Administrator API authorization, contract, and credential workflows."""

from __future__ import annotations

import asyncio

from dependency_injector import providers
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.config import Settings
from tests.fakes import FakeDatabaseReadiness, build_test_container


def _app_with_users():
    container, fakes = build_test_container()
    service = container.api_key_service()
    admin = asyncio.run(service.create_user("admin@example.com"))
    ordinary = asyncio.run(service.create_user("ordinary@example.com"))
    asyncio.run(container.user_repository().set_admin(admin.id, True))
    asyncio.run(container.password_service().set_password(admin, "admin password"))
    asyncio.run(container.password_service().set_password(ordinary, "user password"))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    return create_app(Settings(), container), container, fakes, admin, ordinary


def _login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200


def test_every_admin_route_requires_an_admin_session():
    app, _, _, _, _ = _app_with_users()
    web_app = next(
        route.app for route in app.routes if getattr(route, "path", None) == "/api/v1"
    )
    admin_router = next(
        route.original_router
        for route in web_app.routes
        if getattr(getattr(route, "original_router", None), "prefix", None) == "/admin"
    )
    admin_routes = [
        route for route in admin_router.routes if isinstance(route, APIRoute)
    ]
    assert admin_routes
    assert all(route.dependant.dependencies for route in admin_routes)

    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        assert client.get("/api/v1/admin/users").status_code == 401
        _login(client, "ordinary@example.com", "user password")
        assert client.get("/api/v1/admin/users").status_code == 403


def test_user_creation_listing_duplicate_and_last_admin_guard():
    app, _, _, admin, _ = _app_with_users()
    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        _login(client, "admin@example.com", "admin password")
        created = client.post(
            "/api/v1/admin/users", json={"email": "new@example.com"}
        )
        assert created.status_code == 201
        assert created.json()["is_admin"] is False
        assert created.json()["web_access"] is False
        assert created.json()["active_key_count"] == 0
        assert client.post(
            "/api/v1/admin/users", json={"email": "new@example.com"}
        ).status_code == 409

        listed = client.get("/api/v1/admin/users")
        assert listed.status_code == 200
        assert "password" not in listed.text
        assert "hash" not in listed.text
        assert client.put(
            f"/api/v1/admin/users/{admin.id}/admin", json={"is_admin": False}
        ).status_code == 409
        new_id = created.json()["id"]
        assert client.put(
            f"/api/v1/admin/users/{new_id}/admin", json={"is_admin": True}
        ).json()["is_admin"] is True
        assert client.put(
            f"/api/v1/admin/users/{admin.id}/admin", json={"is_admin": False}
        ).status_code == 200


def test_key_issue_requires_admin_password_and_revoke_is_target_scoped():
    app, container, fakes, admin, ordinary = _app_with_users()
    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        _login(client, "admin@example.com", "admin password")
        path = f"/api/v1/admin/users/{ordinary.id}/keys"
        denied = client.post(path, json={"password": "wrong", "name": "laptop"})
        assert denied.status_code == 403
        assert not fakes["keys"].keys

        issued = client.post(
            path, json={"password": "admin password", "name": "laptop"}
        )
        assert issued.status_code == 201
        plaintext = issued.json()["api_key"]
        key_id = issued.json()["id"]
        listed = client.get(path)
        assert listed.status_code == 200
        assert plaintext not in listed.text
        assert next(iter(fakes["keys"].keys.values())).key_hash not in listed.text
        users = client.get("/api/v1/admin/users").json()
        assert next(row for row in users if row["id"] == str(ordinary.id))[
            "active_key_count"
        ] == 1

        wrong_target = client.post(
            f"/api/v1/admin/users/{admin.id}/keys/{key_id}/revoke"
        )
        assert wrong_target.status_code == 404
        assert asyncio.run(container.authenticator().authenticate(plaintext)) is not None
        assert client.post(
            f"/api/v1/admin/users/{ordinary.id}/keys/{key_id}/revoke"
        ).status_code == 204
        assert asyncio.run(container.authenticator().authenticate(plaintext)) is None


def test_aggregates_status_openapi_and_no_destructive_or_content_routes():
    app, container, _, _, ordinary = _app_with_users()
    asyncio.run(
        container.memory_service().remember(
            ordinary.id, content="private content", category="fact"
        )
    )
    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        _login(client, "admin@example.com", "admin password")
        aggregates = client.get("/api/v1/admin/aggregates")
        assert aggregates.status_code == 200
        assert aggregates.json()["total_users"] == 2
        assert {row["user_id"]: row["count"] for row in aggregates.json()["memories"]}[
            str(ordinary.id)
        ] == 1
        assert "content" not in aggregates.text.lower()
        assert "private content" not in aggregates.text

        detailed = client.get("/api/v1/admin/status")
        assert detailed.status_code == 200
        assert detailed.json()["embedding_model"] == "fake-embedding-model"
        assert not any(
            secret in detailed.text.lower()
            for secret in ("postgresql", "password", "database_url", "recallum:recallum")
        )
        container.database_readiness().ready = False
        container.embedding_client().available = False
        unavailable = client.get("/api/v1/admin/status").json()
        assert unavailable["database"] is False
        assert unavailable["embeddings"] is False

        contract = client.get("/api/v1/openapi.json").json()
        paths = contract["paths"]
        assert "/admin/users" in paths
        assert "/admin/aggregates" in paths
        assert "/admin/status" in paths
        assert "delete" not in paths["/admin/users/{user_id}/admin"]
        assert not any("memories" in path for path in paths if path.startswith("/admin"))


def test_untrusted_origin_cannot_write_admin_state():
    app, _, _, admin, _ = _app_with_users()
    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        _login(client, "admin@example.com", "admin password")
        response = client.put(
            f"/api/v1/admin/users/{admin.id}/admin",
            json={"is_admin": False},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
