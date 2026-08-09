"""HTTP request telemetry and request-ID privacy contracts."""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.config import RuntimeSettings, Settings
from recallum.telemetry.http import (
    RequestTelemetryMiddleware,
    normalize_route_template,
    resolve_request_id,
)
from tests.fakes import build_test_container


def test_normalize_route_template_strips_uuids():
    memory_id = uuid.uuid4()
    assert normalize_route_template(f"/api/v1/admin/users/{memory_id}/keys") == (
        "/api/v1/admin/users/{id}/keys"
    )
    assert normalize_route_template("/mcp/") == "/mcp/"


def test_resolve_request_id_accepts_valid_and_replaces_invalid():
    assert resolve_request_id("abc-123_OK") == "abc-123_OK"
    replaced = resolve_request_id("bad id with spaces")
    assert " " not in replaced
    assert resolve_request_id("x" * 200) != "x" * 200
    assert resolve_request_id(None)


def test_runtime_rejects_stateful_multi_worker_and_accepts_one():
    assert RuntimeSettings(workers=1).workers == 1
    assert RuntimeSettings(workers=1, mcp_stateless_http=True).workers == 1
    with pytest.raises(ValueError, match="WORKERS=1"):
        RuntimeSettings(workers=2)
    with pytest.raises(ValueError, match="MCP_STATELESS_HTTP"):
        RuntimeSettings(workers=2, mcp_stateless_http=True)
    with pytest.raises(ValueError, match="WORKERS=1"):
        Settings(runtime={"workers": 3})
    with pytest.raises(ValueError, match="WORKERS=1"):
        Settings(runtime={"workers": 2, "mcp_stateless_http": True})


def test_http_middleware_emits_one_redacted_record_per_request(caplog):
    records: list[dict] = []
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(item_id: uuid.UUID):
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("explode")

    app.add_middleware(RequestTelemetryMiddleware, emit=records.append)
    client = TestClient(app, raise_server_exceptions=False)

    item_id = uuid.uuid4()
    sentinel_email = "leak@example.com"
    sentinel_token = "Bearer rcl_supersecrettokenvalue"
    response = client.get(
        f"/items/{item_id}?q=secret-query&email={sentinel_email}",
        headers={
            "Authorization": sentinel_token,
            "Cookie": "session=cookie-secret",
            "X-Request-ID": "valid-request-id-1",
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "valid-request-id-1"
    assert len(records) == 1
    record = records[0]
    assert record == {
        "method": "GET",
        "route": "/items/{id}",
        "status": 200,
        "latency_ms": record["latency_ms"],
        "request_id": "valid-request-id-1",
    }
    assert record["latency_ms"] >= 0
    serialized = repr(record)
    for forbidden in (
        str(item_id),
        "secret-query",
        sentinel_email,
        "cookie-secret",
        "rcl_supersecrettokenvalue",
        "Authorization",
    ):
        assert forbidden not in serialized

    invalid = client.get("/items/plain", headers={"X-Request-ID": "no spaces allowed!"})
    assert invalid.headers["X-Request-ID"] != "no spaces allowed!"
    assert len(records) == 2
    assert records[1]["request_id"] == invalid.headers["X-Request-ID"]

    with caplog.at_level(logging.INFO, logger="recallum.http"):
        errored = client.get("/boom")
    assert errored.status_code == 500
    assert len(records) == 3
    assert records[2]["status"] == 500
    assert records[2]["route"] == "/boom"


def test_create_app_emits_one_record_for_fastapi_and_mounts(monkeypatch):
    records: list[dict] = []

    def capture(_self, record: dict) -> None:
        records.append(record)

    monkeypatch.setattr(
        RequestTelemetryMiddleware,
        "_log_record",
        capture,
    )
    container, _ = build_test_container()
    app = create_app(Settings(), container)
    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert "X-Request-ID" in health.headers
        assert len(records) == 1
        assert records[0]["route"] == "/healthz"
        assert records[0]["status"] == 200

        client.post("/mcp/")
        assert len(records) == 2
        assert records[1]["route"].startswith("/mcp")
