"""ASGI application test: startup, health checks, clean shutdown (task 5.4)."""

from __future__ import annotations

import uuid

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
