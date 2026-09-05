"""ASGI application test: startup, health checks, clean shutdown (task 5.4)."""

from __future__ import annotations

import uuid
from importlib.metadata import version as package_version

from dependency_injector import providers
from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.config import Settings
from recallum.db.readiness import DatabaseReadiness
from recallum.telemetry.events import ToolActivityEvent
from tests.fakes import (
    FakeDatabaseReadiness,
    FakeEmbeddingClient,
    FakeEngine,
    build_test_container,
)


def test_lifespan_health_and_clean_shutdown():
    engine = FakeEngine(available=True)
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(available=True))
    container.engine.override(providers.Object(engine))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    app = create_app(Settings(), container)

    with TestClient(app) as client:
        alive = client.get("/healthz")
        assert alive.status_code == 200
        assert alive.json() == {"status": "alive"}

        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "checks": {"database": "ok", "embeddings": "ok"},
        }

        # MCP mount is present.
        assert app.state.mcp_server is not None
        client.portal.call(
            client.app.state.container.telemetry_buffer().record,
            ToolActivityEvent(
                user_id=uuid.uuid4(),
                tool_name="context",
                project=None,
                duration_ms=1,
                result_count=0,
                degraded=False,
                failed=False,
            ),
        )

    # Shutdown disposed the engine (resource cleanup verified).
    assert engine.disposed is True
    assert len(fakes["telemetry"].events) == 1


def test_public_version_matches_package_metadata():
    container, _ = build_test_container()
    assert create_app(Settings(), container).version == package_version("recallum")


def test_readiness_reports_unavailable_with_503_and_no_secrets():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(available=False))
    container.engine.override(providers.Object(FakeEngine(available=False)))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(False)))
    app = create_app(Settings(), container)

    with TestClient(app) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 503
        body = ready.json()
        assert body["status"] == "unavailable"
        assert body["checks"] == {"database": "unavailable", "embeddings": "unavailable"}
        # Nothing sensitive leaks in the payload.
        assert "url" not in ready.text.lower()
        assert "password" not in ready.text.lower()


def test_readiness_rejects_missing_schema_or_unsafe_role():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(available=True))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(False)))
    app = create_app(Settings(), container)

    with TestClient(app) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert ready.json()["checks"] == {"database": "unavailable", "embeddings": "ok"}


def test_liveness_independent_of_dependencies():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(available=False))
    container.engine.override(providers.Object(FakeEngine(available=False)))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(False)))
    app = create_app(Settings(), container)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


async def test_database_readiness_maps_connection_errors_to_false():
    readiness = DatabaseReadiness(FakeEngine(available=False))
    assert await readiness.is_ready() is False


def test_metrics_rejects_agent_token_and_serves_operator_snapshot():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(available=True))
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    settings = Settings(telemetry={"metrics_token": "operator-secret"})
    app = create_app(settings, container)
    agent_token = "rcl_agent-not-an-operator"
    sentinel_query = "secret-query-value"

    with TestClient(app) as client:
        denied = client.get(
            f"/metrics?q={sentinel_query}",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        assert denied.status_code == 401
        assert denied.json() == {"detail": "Not authenticated"}
        assert agent_token not in denied.text
        assert sentinel_query not in denied.text

        missing = client.get("/metrics")
        assert missing.status_code == 401

        client.portal.call(
            client.app.state.container.telemetry_buffer().record,
            ToolActivityEvent(
                user_id=uuid.uuid4(),
                tool_name="recall",
                project=None,
                duration_ms=4,
                result_count=1,
                degraded=True,
                failed=False,
            ),
        )
        allowed = client.get(
            "/metrics",
            headers={"Authorization": "Bearer operator-secret"},
        )
        assert allowed.status_code == 200
        body = allowed.json()
        assert body["dropped_events"] == 0
        assert body["flush_failures"] == 0
        assert body["degraded_calls"] == 1
        assert body["degraded_ratio"] == 1.0
        assert body["tools"][0]["tool_name"] == "recall"
        assert body["readiness"] == {"database": "ok", "embeddings": "ok"}
        assert "user_id" not in body
        assert "query" not in body
        assert "content" not in body
        assert agent_token not in allowed.text


def test_metrics_ignores_forwarded_loopback_and_allows_tcp_loopback():
    settings = Settings(
        telemetry={"metrics_token": ""},
        boundary={"proxy": {"trusted_cidrs": ["10.0.1.0/24"]}},
    )
    forwarded, _ = build_test_container(embedder=FakeEmbeddingClient(available=True))
    forwarded.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    with TestClient(
        create_app(settings, forwarded), client=("10.0.1.9", 50000)
    ) as client:
        denied = client.get("/metrics", headers={"X-Forwarded-For": "127.0.0.1"})
        assert denied.status_code == 401
        assert "127.0.0.1" not in denied.text

    loopback, _ = build_test_container(embedder=FakeEmbeddingClient(available=True))
    loopback.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    with TestClient(
        create_app(settings, loopback), client=("127.0.0.1", 50000)
    ) as client:
        allowed = client.get("/metrics")
        assert allowed.status_code == 200
        assert allowed.json()["dropped_events"] == 0
