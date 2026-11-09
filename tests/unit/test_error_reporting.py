"""Sentry-compatible error reporting configuration and privacy contracts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import Mock, call

import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from recallum import __version__, error_reporting
from recallum.config import Settings

DSN = "https://public-key@o0.ingest.sentry.io/0"
SENTINEL = "private memory content bearer-token internal-host"


def test_error_reporting_is_disabled_without_a_dsn(monkeypatch) -> None:
    init = Mock()
    monkeypatch.setattr(error_reporting.sentry_sdk, "init", init)

    error_reporting.configure_error_reporting(Settings())

    init.assert_not_called()


def test_dsn_initializes_error_only_reporting(monkeypatch) -> None:
    init = Mock()
    monkeypatch.setattr(error_reporting.sentry_sdk, "init", init)

    error_reporting.configure_error_reporting(
        Settings(environment="staging", error_reporting={"dsn": DSN})
    )

    kwargs = init.call_args.kwargs
    assert kwargs["dsn"] == DSN
    assert kwargs["environment"] == "staging"
    assert kwargs["release"] == f"recallum@{__version__}"
    assert kwargs["default_integrations"] is False
    assert kwargs["auto_enabling_integrations"] is False
    assert kwargs["send_default_pii"] is False
    assert kwargs["include_local_variables"] is False
    assert kwargs["include_source_context"] is False
    assert kwargs["max_breadcrumbs"] == 0
    assert kwargs["traces_sample_rate"] == 0.0
    assert kwargs["auto_session_tracking"] is False
    assert kwargs["before_send"] is error_reporting._sanitize_event
    integrations = kwargs["integrations"]
    assert len(integrations) == 2
    assert isinstance(integrations[0], StarletteIntegration)
    assert isinstance(integrations[1], FastApiIntegration)
    assert all(
        integration.failed_request_status_codes == set() for integration in integrations
    )


def test_event_sanitizer_removes_content_and_keeps_diagnostic_structure() -> None:
    event = {
        "request": {"url": f"https://example.test/?q={SENTINEL}"},
        "user": {"username": SENTINEL},
        "contexts": {"private": SENTINEL},
        "extra": {"arguments": SENTINEL},
        "breadcrumbs": [{"message": SENTINEL}],
        "message": SENTINEL,
        "transaction": f"/memories/{SENTINEL}",
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": SENTINEL,
                    "stacktrace": {
                        "frames": [
                            {
                                "function": "remember",
                                "vars": {"content": SENTINEL},
                                "context_line": SENTINEL,
                                "pre_context": [SENTINEL],
                                "post_context": [SENTINEL],
                            }
                        ]
                    },
                }
            ]
        },
        "threads": {
            "values": [
                {
                    "stacktrace": {"frames": [{"function": "worker", "vars": {"x": SENTINEL}}]}
                }
            ]
        },
        "tags": {
            "surface": "mcp",
            "correlation_id": "mcp-0123456789abcdef0123456789abcdef",
            "unrelated": SENTINEL,
        },
    }

    sanitized = error_reporting._sanitize_event(event, {})

    assert SENTINEL not in json.dumps(sanitized)
    exception = sanitized["exception"]["values"][0]
    assert exception["type"] == "RuntimeError"
    assert exception["value"] == "[redacted]"
    assert exception["stacktrace"]["frames"] == [{"function": "remember"}]
    assert sanitized["threads"]["values"][0]["stacktrace"]["frames"] == [
        {"function": "worker"}
    ]
    assert sanitized["tags"] == {
        "surface": "mcp",
        "correlation_id": "mcp-0123456789abcdef0123456789abcdef",
    }


def test_mcp_capture_adds_only_safe_correlation_tags(monkeypatch) -> None:
    scope = Mock()
    captured = []

    @contextmanager
    def new_scope():
        yield scope

    monkeypatch.setattr(error_reporting.sentry_sdk, "new_scope", new_scope)
    monkeypatch.setattr(
        error_reporting.sentry_sdk, "capture_exception", lambda error: captured.append(error)
    )
    error = RuntimeError(SENTINEL)
    correlation_id = "mcp-0123456789abcdef0123456789abcdef"

    error_reporting.capture_unexpected_error(error, correlation_id=correlation_id)

    assert captured == [error]
    assert scope.set_tag.call_args_list == [
        call("surface", "mcp"),
        call("correlation_id", correlation_id),
    ]


def test_mcp_capture_failure_does_not_replace_the_original_error(monkeypatch) -> None:
    def fail_capture():
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(error_reporting.sentry_sdk, "new_scope", fail_capture)

    error_reporting.capture_unexpected_error(
        RuntimeError("original"), correlation_id="mcp-safe-reference"
    )


def test_real_fastapi_integration_captures_sanitized_unhandled_errors(monkeypatch) -> None:
    events = []
    original_init = sentry_sdk.init

    def init_with_test_transport(*args, **kwargs):
        return original_init(*args, **kwargs, transport=events.append)

    monkeypatch.setattr(error_reporting.sentry_sdk, "init", init_with_test_transport)
    sentry_sdk.get_client().close()
    try:
        error_reporting.configure_error_reporting(Settings(error_reporting={"dsn": DSN}))
        app = FastAPI()

        @app.get("/failure")
        async def failure():
            raise RuntimeError(SENTINEL)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/failure?q={SENTINEL}")
            assert response.status_code == 500
        sentry_sdk.get_client().flush(timeout=2)

        assert len(events) == 1
        assert SENTINEL not in json.dumps(events[0])
        assert "request" not in events[0]
        exception = events[0]["exception"]["values"][0]
        assert exception["type"] == "RuntimeError"
        assert exception["value"] == "[redacted]"
    finally:
        sentry_sdk.get_client().close()
