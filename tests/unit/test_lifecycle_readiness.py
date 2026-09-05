"""Executable contracts for lifecycle cleanup and bounded readiness."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient
from fastmcp import FastMCP
from pydantic import ValidationError

from recallum.app import create_app
from recallum.config import Settings
from recallum.container import _LazyProvider, init_container_resources, shutdown_container
from tests.fakes import FakeDatabaseReadiness, build_test_container


class _SlowDatabase:
    async def is_ready(self) -> bool:
        await asyncio.sleep(10)
        return True


class _SlowEmbeddings:
    async def is_available(self) -> bool:
        await asyncio.sleep(10)
        return True


class _ReadyDatabase:
    async def is_ready(self) -> bool:
        return True


class _BarrierProbes:
    def __init__(self) -> None:
        self.active = 0
        self.both_reached = asyncio.Event()

    async def _probe(self) -> bool:
        self.active += 1
        try:
            if self.active == 2:
                self.both_reached.set()
            await self.both_reached.wait()
            return True
        finally:
            self.active -= 1

    async def is_ready(self) -> bool:
        return await self._probe()

    async def is_available(self) -> bool:
        return await self._probe()


class _TrackedHang:
    def __init__(self) -> None:
        self.active = 0

    async def _probe(self) -> bool:
        self.active += 1
        try:
            await asyncio.sleep(10)
            return True
        finally:
            self.active -= 1

    async def is_ready(self) -> bool:
        return await self._probe()

    async def is_available(self) -> bool:
        return await self._probe()


class _Closeable:
    def __init__(self, events: list[str], label: str) -> None:
        self._events = events
        self._label = label

    async def aclose(self) -> None:
        self._events.append(self._label)

    async def dispose(self) -> None:
        self._events.append(self._label)


class _YieldingCloseable(_Closeable):
    async def aclose(self) -> None:
        await asyncio.sleep(0)
        await super().aclose()

    async def dispose(self) -> None:
        await asyncio.sleep(0)
        await super().dispose()


class _CancelOnce:
    def __init__(self, events: list[str], label: str, method: str) -> None:
        self._events = events
        self._label = label
        self._method = method
        self._cancelled = False

    async def aclose(self) -> None:
        self._events.append(self._label)
        if self._method == "aclose" and not self._cancelled:
            self._cancelled = True
            raise asyncio.CancelledError

    async def dispose(self) -> None:
        self._events.append(self._label)
        if self._method == "dispose" and not self._cancelled:
            self._cancelled = True
            raise asyncio.CancelledError


class _Telemetry:
    def __init__(
        self,
        events: list[str],
        start_error: BaseException | None = None,
        stop_error: BaseException | None = None,
    ) -> None:
        self._events = events
        self._start_error = start_error
        self._stop_error = stop_error

    async def start(self) -> None:
        self._events.append("telemetry-start")
        if self._start_error is not None:
            raise self._start_error

    async def stop(self) -> None:
        self._events.append("telemetry-stop")
        if self._stop_error is not None:
            raise self._stop_error


class _LifecycleResource:
    def __init__(self, events: list[str], label: str, error: BaseException | None = None) -> None:
        self._events = events
        self._label = label
        self._error = error

    async def aclose(self) -> None:
        self._events.append(self._label)
        if self._error is not None:
            raise self._error

    async def dispose(self) -> None:
        self._events.append(self._label)
        if self._error is not None:
            raise self._error


class _RecursiveCloseable:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.container = None

    async def aclose(self) -> None:
        self.events.append("http-enter")
        await shutdown_container(self.container)
        self.events.append("http-exit")


class _NoopDisposable:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def dispose(self) -> None:
        self.events.append("engine")


def _resources(events: list[str], telemetry=None):
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_LifecycleResource(events, "http")))
    container.engine.override(providers.Object(_LifecycleResource(events, "engine")))
    container.telemetry_buffer.override(providers.Object(telemetry or _Telemetry(events)))
    return container


def test_readiness_settings_have_bounded_cross_field_budgets() -> None:
    settings = Settings()
    assert settings.readiness.per_dependency_timeout_seconds == 2
    assert settings.readiness.aggregate_timeout_seconds == 3

    with pytest.raises(ValidationError):
        Settings(readiness={"per_dependency_timeout_seconds": 0})
    with pytest.raises(ValidationError):
        Settings(readiness={"aggregate_timeout_seconds": 1})
    with pytest.raises(ValidationError):
        Settings(
            readiness={
                "per_dependency_timeout_seconds": 1,
                "database_command_timeout_seconds": 2,
            }
        )


def test_readiness_probes_run_concurrently_and_return_stable_503() -> None:
    container, _ = build_test_container()
    container.database_readiness.override(providers.Object(_SlowDatabase()))
    container.embedding_client.override(providers.Object(_SlowEmbeddings()))
    settings = Settings(
        readiness={
            "per_dependency_timeout_seconds": 0.05,
            "aggregate_timeout_seconds": 0.08,
            "database_pool_timeout_seconds": 0.05,
            "database_connect_timeout_seconds": 0.05,
            "database_command_timeout_seconds": 0.05,
            "database_statement_timeout_seconds": 0.05,
        }
    )
    app = create_app(settings, container)

    with TestClient(app) as client:
        started = time.monotonic()
        response = client.get("/readyz")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "embeddings": "unavailable"},
    }
    # Bound against the 10s probe sleeps, not TestClient lifespan (extra workers).
    assert elapsed < 1.0


def test_readiness_barrier_proves_both_probes_start_concurrently() -> None:
    container, _ = build_test_container()
    probes = _BarrierProbes()
    container.database_readiness.override(providers.Object(probes))
    container.embedding_client.override(providers.Object(probes))
    settings = Settings(
        readiness={
            "per_dependency_timeout_seconds": 0.2,
            "aggregate_timeout_seconds": 0.25,
            "database_pool_timeout_seconds": 0.2,
            "database_connect_timeout_seconds": 0.2,
            "database_command_timeout_seconds": 0.2,
            "database_statement_timeout_seconds": 0.2,
        }
    )
    app = create_app(settings, container)
    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert probes.both_reached.is_set()
    assert probes.active == 0


def test_repeated_readiness_timeouts_leave_no_probe_active() -> None:
    container, _ = build_test_container()
    database = _TrackedHang()
    embeddings = _TrackedHang()
    container.database_readiness.override(providers.Object(database))
    container.embedding_client.override(providers.Object(embeddings))
    settings = Settings(
        readiness={
            "per_dependency_timeout_seconds": 0.01,
            "aggregate_timeout_seconds": 0.02,
            "database_pool_timeout_seconds": 0.01,
            "database_connect_timeout_seconds": 0.01,
            "database_command_timeout_seconds": 0.01,
            "database_statement_timeout_seconds": 0.01,
        }
    )
    with TestClient(create_app(settings, container)) as client:
        for _ in range(10):
            assert client.get("/readyz").status_code == 503
        remaining = client.portal.call(
            lambda: [
                task.get_name()
                for task in asyncio.all_tasks()
                if task.get_name().startswith("recallum-readiness-")
            ]
        )

    assert database.active == 0
    assert embeddings.active == 0
    assert remaining == []


def test_readiness_aggregate_timeout_preserves_completed_dependency() -> None:
    container, _ = build_test_container()
    container.database_readiness.override(providers.Object(_ReadyDatabase()))
    container.embedding_client.override(providers.Object(_SlowEmbeddings()))
    settings = Settings(
        readiness={
            "per_dependency_timeout_seconds": 0.04,
            "aggregate_timeout_seconds": 0.05,
            "database_pool_timeout_seconds": 0.04,
            "database_connect_timeout_seconds": 0.04,
            "database_command_timeout_seconds": 0.04,
            "database_statement_timeout_seconds": 0.04,
        }
    )

    with TestClient(create_app(settings, container)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "database": "ok",
        "embeddings": "unavailable",
    }


@pytest.mark.asyncio
async def test_shutdown_container_closes_http_before_engine_once() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_Closeable(events, "http")))
    container.engine.override(providers.Object(_Closeable(events, "engine")))

    await shutdown_container(container)
    await shutdown_container(container)

    assert events == ["http", "engine"]


@pytest.mark.asyncio
async def test_uninitialized_shutdown_remains_pending_for_later_acquisition() -> None:
    events: list[str] = []
    container, _ = build_test_container()

    await shutdown_container(container)
    container.http_client.override(providers.Object(_Closeable(events, "http")))
    container.engine.override(providers.Object(_Closeable(events, "engine")))
    await shutdown_container(container)
    await shutdown_container(container)

    assert events == ["http", "engine"]


@pytest.mark.asyncio
async def test_cancellation_precedes_http_error_and_retry_is_deterministic() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    container.engine.override(providers.Object(_CancelOnce(events, "engine", "dispose")))

    with pytest.raises(asyncio.CancelledError):
        await shutdown_container(container)
    with pytest.raises(RuntimeError):
        await shutdown_container(container)
    assert events == ["http", "engine", "http", "engine"]


@pytest.mark.asyncio
async def test_cancellation_precedes_engine_error_and_retry_is_deterministic() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_CancelOnce(events, "http", "aclose")))
    container.engine.override(
        providers.Object(_LifecycleResource(events, "engine", RuntimeError("engine")))
    )

    with pytest.raises(asyncio.CancelledError):
        await shutdown_container(container)
    with pytest.raises(RuntimeError):
        await shutdown_container(container)
    assert events == ["http", "engine", "http", "engine"]


@pytest.mark.asyncio
async def test_concurrent_shutdown_is_serialized_and_exactly_once() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_YieldingCloseable(events, "http")))
    container.engine.override(providers.Object(_YieldingCloseable(events, "engine")))

    await asyncio.gather(shutdown_container(container), shutdown_container(container))

    assert events == ["http", "engine"]


@pytest.mark.asyncio
async def test_same_task_recursive_shutdown_returns_without_deadlock() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    recursive = _RecursiveCloseable(events)
    recursive.container = container
    container.http_client.override(providers.Object(recursive))
    container.engine.override(providers.Object(_NoopDisposable(events)))

    await asyncio.wait_for(shutdown_container(container), timeout=0.5)

    assert events == ["http-enter", "http-exit", "engine"]


@pytest.mark.asyncio
async def test_shutdown_retries_cancelled_callback_without_repeating_completed_cleanup() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_CancelOnce(events, "http", "aclose")))
    container.engine.override(providers.Object(_Closeable(events, "engine")))

    with pytest.raises(asyncio.CancelledError):
        await shutdown_container(container)
    await shutdown_container(container)

    assert events == ["http", "engine", "http"]


@pytest.mark.asyncio
async def test_shutdown_retries_cancelled_engine_without_repeating_http_cleanup() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_Closeable(events, "http")))
    container.engine.override(providers.Object(_CancelOnce(events, "engine", "dispose")))

    with pytest.raises(asyncio.CancelledError):
        await shutdown_container(container)
    await shutdown_container(container)

    assert events == ["http", "engine", "engine"]


@pytest.mark.asyncio
async def test_shutdown_does_not_create_uninitialized_resources() -> None:
    container, _ = build_test_container()
    assert container.http_client.initialized is False
    assert container.engine.initialized is False

    await shutdown_container(container)

    assert container.http_client.initialized is False
    assert container.engine.initialized is False


@pytest.mark.asyncio
async def test_init_resources_resolves_http_client_to_async_client() -> None:
    """Resource init must yield AsyncClient so _LazyProvider can call ``.post``."""
    container, _ = build_test_container()
    await init_container_resources(container)
    try:
        client = container.http_client()
        assert isinstance(client, httpx.AsyncClient)
        lazy = _LazyProvider(container.http_client)
        assert callable(lazy.post)
    finally:
        await shutdown_container(container)


@pytest.mark.asyncio
@pytest.mark.parametrize("validator", ["first", "second"])
async def test_each_exposure_validator_failure_yields_nothing_and_cleans_up(validator: str) -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_LifecycleResource(events, "http")))
    container.engine.override(providers.Object(_LifecycleResource(events, "engine")))
    container.telemetry_buffer.override(providers.Object(_Telemetry(events)))
    error = RuntimeError(validator)

    app = create_app(Settings(), container)

    async def fail_first(*_args):
        raise error

    async def fail_second(*_args):
        raise error

    async def noop(*_args):
        return None

    first_validator = fail_first if validator == "first" else noop
    second_validator = fail_second if validator == "second" else noop
    with patch("recallum.app.validate_no_user_inputs", new=first_validator):
        with patch("recallum.app.validate_only_tools_are_exposed", new=second_validator):
            with pytest.raises(RuntimeError):
                async with app.router.lifespan_context(app):
                    pytest.fail("failed startup yielded")
    assert events == ["http", "engine"]


@pytest.mark.asyncio
async def test_validator_failure_does_not_create_untouched_http_or_engine() -> None:
    container, _ = build_test_container()
    app = create_app(Settings(), container)

    async def fail(*_args):
        raise RuntimeError("validator")

    with patch("recallum.app.validate_no_user_inputs", new=fail):
        with pytest.raises(RuntimeError):
            async with app.router.lifespan_context(app):
                pytest.fail("failed startup yielded")

    assert container.http_client.initialized is False
    assert container.engine.initialized is False


@pytest.mark.asyncio
@pytest.mark.parametrize("start_error", [RuntimeError("start"), asyncio.CancelledError()])
async def test_telemetry_start_failure_or_cancellation_does_not_stop_telemetry(start_error) -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(providers.Object(_LifecycleResource(events, "http")))
    container.engine.override(providers.Object(_LifecycleResource(events, "engine")))
    container.telemetry_buffer.override(
        providers.Object(_Telemetry(events, start_error=start_error))
    )
    app = create_app(Settings(), container)

    with pytest.raises(type(start_error)):
        async with app.router.lifespan_context(app):
            pytest.fail("failed telemetry startup yielded")
    assert events == ["telemetry-start", "http", "engine"]


@pytest.mark.asyncio
async def test_normal_shutdown_is_telemetry_http_engine_and_stop_failure_still_closes() -> None:
    for stop_error in (None, RuntimeError("stop")):
        events: list[str] = []
        container, _ = build_test_container()
        container.http_client.override(providers.Object(_LifecycleResource(events, "http")))
        container.engine.override(providers.Object(_LifecycleResource(events, "engine")))
        container.telemetry_buffer.override(
            providers.Object(_Telemetry(events, stop_error=stop_error))
        )
        app = create_app(Settings(), container)
        context = app.router.lifespan_context(app)
        if stop_error is None:
            async with context:
                pass
        else:
            with pytest.raises(RuntimeError):
                async with context:
                    pass
        assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_telemetry_stop_cancellation_still_closes_container() -> None:
    events: list[str] = []
    telemetry = _Telemetry(events, stop_error=asyncio.CancelledError())
    container = _resources(events, telemetry=telemetry)
    app = create_app(Settings(), container)

    with pytest.raises(asyncio.CancelledError):
        async with app.router.lifespan_context(app):
            pass
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mounted_error", [RuntimeError("mounted"), asyncio.CancelledError()])
async def test_mounted_lifespan_failure_or_cancellation_closes_started_resources(
    mounted_error,
) -> None:
    events: list[str] = []
    container = _resources(events)
    original_http_app = FastMCP.http_app

    def failing_http_app(server, *args, **kwargs):
        mounted = original_http_app(server, *args, **kwargs)

        @asynccontextmanager
        async def fail_mounted(_app):
            yield
            raise mounted_error

        mounted.router.lifespan_context = fail_mounted
        return mounted

    with patch.object(FastMCP, "http_app", new=failing_http_app):
        app = create_app(Settings(), container)
    with pytest.raises(type(mounted_error)):
        async with app.router.lifespan_context(app):
            pass
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_incoming_mounted_error_with_telemetry_cancellation_and_http_failure_prefers_cancel() -> None:  # noqa: E501
    events: list[str] = []
    telemetry = _Telemetry(events, stop_error=asyncio.CancelledError())
    container = _resources(events, telemetry=telemetry)
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    original_http_app = FastMCP.http_app

    def failing_http_app(server, *args, **kwargs):
        mounted = original_http_app(server, *args, **kwargs)

        @asynccontextmanager
        async def fail_mounted(_app):
            yield
            raise RuntimeError("mounted")

        mounted.router.lifespan_context = fail_mounted
        return mounted

    with patch.object(FastMCP, "http_app", new=failing_http_app):
        app = create_app(Settings(), container)
    with pytest.raises(asyncio.CancelledError):
        async with app.router.lifespan_context(app):
            pass
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_incoming_body_cancellation_precedes_later_cleanup_failures() -> None:
    events: list[str] = []
    container = _resources(
        events,
        telemetry=_Telemetry(events, stop_error=RuntimeError("telemetry")),
    )
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    container.engine.override(
        providers.Object(_LifecycleResource(events, "engine", RuntimeError("engine")))
    )
    app = create_app(Settings(), container)

    with pytest.raises(asyncio.CancelledError):
        async with app.router.lifespan_context(app):
            raise asyncio.CancelledError()
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_incoming_body_error_with_telemetry_cancel_and_http_failure_prefers_cancel() -> None:
    events: list[str] = []
    container = _resources(
        events,
        telemetry=_Telemetry(events, stop_error=asyncio.CancelledError()),
    )
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    app = create_app(Settings(), container)

    with pytest.raises(asyncio.CancelledError):
        async with app.router.lifespan_context(app):
            raise RuntimeError("body")
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_coordinator_aggregates_incoming_and_cleanup_runtime_errors() -> None:
    events: list[str] = []
    container = _resources(
        events,
        telemetry=_Telemetry(events, stop_error=RuntimeError("telemetry")),
    )
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    app = create_app(Settings(), container)

    with pytest.raises(ExceptionGroup) as grouped:
        async with app.router.lifespan_context(app):
            raise RuntimeError("body")
    assert len(grouped.value.exceptions) == 3
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_telemetry_cancellation_precedes_http_failure_without_incoming_error() -> None:
    events: list[str] = []
    container = _resources(
        events,
        telemetry=_Telemetry(events, stop_error=asyncio.CancelledError()),
    )
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    app = create_app(Settings(), container)

    with pytest.raises(asyncio.CancelledError):
        async with app.router.lifespan_context(app):
            pass
    assert events == ["telemetry-start", "telemetry-stop", "http", "engine"]


@pytest.mark.asyncio
async def test_shutdown_aggregates_multiple_non_cancellation_errors_and_preserves_one() -> None:
    events: list[str] = []
    container, _ = build_test_container()
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    container.engine.override(
        providers.Object(_LifecycleResource(events, "engine", RuntimeError("engine")))
    )
    with pytest.raises(ExceptionGroup) as grouped:
        await shutdown_container(container)
    assert len(grouped.value.exceptions) == 2

    events.clear()
    container, _ = build_test_container()
    container.http_client.override(
        providers.Object(_LifecycleResource(events, "http", RuntimeError("http")))
    )
    container.engine.override(providers.Object(_Closeable(events, "engine")))
    with pytest.raises(RuntimeError, match="http"):
        await shutdown_container(container)


@pytest.mark.asyncio
async def test_failing_http_factory_override_still_disposes_engine() -> None:
    """Unresolved HTTP Factory override must not skip engine disposal."""
    events: list[str] = []
    container, _ = build_test_container()

    def boom() -> object:
        raise RuntimeError("http-factory")

    container.http_client.override(providers.Factory(boom))
    container.engine.override(providers.Object(_Closeable(events, "engine")))

    with pytest.raises(RuntimeError, match="http-factory"):
        await shutdown_container(container)

    assert events == ["engine"]
    assert container.http_client.initialized is False
    assert container._recallum_shutdown_state["http_resource"] is None
    assert container._recallum_shutdown_state["engine"] is True


@pytest.mark.asyncio
async def test_failing_http_factory_override_aggregates_with_engine_failure() -> None:
    events: list[str] = []
    container, _ = build_test_container()

    def boom() -> object:
        raise RuntimeError("http-factory")

    container.http_client.override(providers.Factory(boom))
    container.engine.override(
        providers.Object(_LifecycleResource(events, "engine", RuntimeError("engine")))
    )

    with pytest.raises(ExceptionGroup) as grouped:
        await shutdown_container(container)

    assert {type(exc) for exc in grouped.value.exceptions} == {RuntimeError}
    assert {str(exc) for exc in grouped.value.exceptions} == {"http-factory", "engine"}
    assert events == ["engine"]
    assert container.http_client.initialized is False
    assert container._recallum_shutdown_state["http_resource"] is None


def test_default_readiness_deadlines_are_wired_without_waiting_for_them() -> None:
    container, _ = build_test_container()
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    observed: list[float] = []
    original_wait_for = asyncio.wait_for

    async def record_wait_for(awaitable, timeout):
        observed.append(timeout)
        return await original_wait_for(awaitable, timeout)

    with patch("recallum.app.asyncio.wait_for", new=record_wait_for):
        with TestClient(create_app(Settings(), container)) as client:
            assert client.get("/readyz").status_code == 200
    assert sorted(observed) == [2.0, 2.0, 3.0]
