"""FastAPI application factory.

FastAPI hosts operational endpoints (liveness/readiness) and mounts the
FastMCP HTTP app at ``/mcp``; both lifespans are composed so the MCP session
manager and the DI-owned engine/HTTP client start and stop in order.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans
from pydantic import BaseModel

from recallum import __version__
from recallum.config import Settings, get_settings
from recallum.container import (
    Container,
    create_container,
    init_container_resources,
    shutdown_container,
)
from recallum.http_boundary import (
    FixedWindowLimiter,
    MCPAuthRateLimitMiddleware,
    MCPBoundaryMiddleware,
    RequestBodyLimitMiddleware,
    TrustedClientResolver,
)
from recallum.logging_setup import setup_logging
from recallum.mcp.server import (
    build_mcp_server,
    validate_no_user_inputs,
    validate_only_tools_are_exposed,
)
from recallum.telemetry.http import RequestTelemetryMiddleware
from recallum.web.admin import create_admin_router
from recallum.web.auth import build_web_authenticator, create_auth_router
from recallum.web.self_service import create_self_service_router


class LivenessResponse(BaseModel):
    """Liveness never touches dependencies."""

    status: Literal["alive"]


class CheckStatus(BaseModel):
    """One readiness probe result, free of sensitive details."""

    database: Literal["ok", "unavailable"]
    embeddings: Literal["ok", "unavailable"]


class ReadinessResponse(BaseModel):
    """Aggregate readiness."""

    status: Literal["ready", "unavailable"]
    checks: CheckStatus


def _find_cancellation(error: BaseException) -> asyncio.CancelledError | None:
    if isinstance(error, asyncio.CancelledError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            cancellation = _find_cancellation(nested)
            if cancellation is not None:
                return cancellation
    return None


def _raise_lifecycle_failures(failures: list[BaseException]) -> None:
    cancellation = next(
        (found for error in failures if (found := _find_cancellation(error)) is not None),
        None,
    )
    if cancellation is not None:
        raise cancellation
    if len(failures) == 1:
        raise failures[0]
    if all(isinstance(error, Exception) for error in failures):
        raise ExceptionGroup("application lifecycle cleanup failed", failures)
    raise BaseExceptionGroup("application lifecycle cleanup failed", failures)


class _LifecycleCoordinator:
    """One async-exit callback preserving incoming and cleanup failures."""

    def __init__(self, container: Container) -> None:
        self._container = container
        self._telemetry = None
        self._telemetry_attempted = False

    def register_telemetry(self, telemetry) -> None:
        self._telemetry = telemetry

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        failures: list[BaseException] = []
        if exc is not None:
            failures.append(exc)
        if self._telemetry is not None and not self._telemetry_attempted:
            self._telemetry_attempted = True
            try:
                await self._telemetry.stop()
            except BaseException as error:
                failures.append(error)
        try:
            await shutdown_container(self._container)
        except BaseException as error:
            failures.append(error)
        if not failures:
            return False
        # An incoming exception alone should retain its original traceback.
        if len(failures) == 1 and failures[0] is exc:
            return False
        _raise_lifecycle_failures(failures)
        return False  # pragma: no cover - _raise_lifecycle_failures always raises


async def _bounded_probe(probe, timeout_seconds: float) -> bool:
    """Return a safe boolean while bounding one dependency probe."""
    try:
        return bool(await asyncio.wait_for(probe(), timeout_seconds))
    except Exception:
        return False


def create_health_router(container: Container, settings: Settings | None = None) -> APIRouter:
    """Operational endpoints: /healthz and /readyz."""
    router = APIRouter(tags=["health"])
    readiness = settings.readiness if settings is not None else Settings().readiness

    @router.get("/healthz", summary="Liveness probe")
    async def healthz() -> LivenessResponse:
        return LivenessResponse(status="alive")

    @router.get(
        "/readyz",
        summary="Readiness probe (PostgreSQL and Ollama)",
        responses={503: {"model": ReadinessResponse}},
    )
    async def readyz() -> ReadinessResponse:
        async def database_probe() -> bool:
            return await container.database_readiness().is_ready()

        async def embeddings_probe() -> bool:
            return await container.embedding_client().is_available()

        tasks = {
            "database": asyncio.create_task(
                _bounded_probe(database_probe, readiness.per_dependency_timeout_seconds),
                name="recallum-readiness-database",
            ),
            "embeddings": asyncio.create_task(
                _bounded_probe(embeddings_probe, readiness.per_dependency_timeout_seconds),
                name="recallum-readiness-embeddings",
            ),
        }
        try:
            database_ok, embeddings_ok = await asyncio.wait_for(
                asyncio.gather(tasks["database"], tasks["embeddings"]),
                readiness.aggregate_timeout_seconds,
            )
        except Exception:
            def completed(name: str) -> bool:
                task = tasks[name]
                if not task.done() or task.cancelled():
                    return False
                try:
                    return bool(task.result())
                except BaseException:
                    return False

            # Preserve a completed healthy result when the other dependency
            # exhausts the aggregate budget; only unfinished checks are down.
            database_ok = completed("database")
            embeddings_ok = completed("embeddings")
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

        checks = CheckStatus(
            database="ok" if database_ok else "unavailable",
            embeddings="ok" if embeddings_ok else "unavailable",
        )
        body = ReadinessResponse(
            status="ready" if (database_ok and embeddings_ok) else "unavailable",
            checks=checks,
        )
        if body.status != "ready":
            return JSONResponse(content=body.model_dump(), status_code=503)
        return body

    return router

def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Build the ASGI application with composed lifespans and the /mcp mount."""
    setup_logging()
    resolved_settings = settings if settings is not None else get_settings()
    resolved_container = container if container is not None else create_container(resolved_settings)
    limiter = FixedWindowLimiter(max_entries=resolved_settings.boundary.rate.max_buckets)

    mcp_server = build_mcp_server(resolved_container)
    # FastMCP's fnmatch-based origin matcher treats IPv6 brackets as a pattern;
    # escape literal brackets while retaining the canonical public settings.
    mcp_origins = []
    for origin in resolved_settings.boundary.mcp.allowed_origins:
        if ":" not in (urlsplit(origin).hostname or ""):
            mcp_origins.append(origin)
            continue
        mcp_origins.append(origin.translate(str.maketrans({"[": "[[]", "]": "[]]"})))
    mcp_app = mcp_server.http_app(
        path="/",
        host_origin_protection=True,
        allowed_hosts=list(resolved_settings.boundary.mcp.allowed_hosts),
        allowed_origins=mcp_origins,
    )

    @asynccontextmanager
    async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = resolved_container
        app.state.mcp_server = mcp_server
        coordinator = _LifecycleCoordinator(resolved_container)
        async with AsyncExitStack() as stack:
            # Register one coordinator before validators so mounted/body
            # exceptions remain available while all cleanup is attempted.
            stack.push_async_exit(coordinator)
            await validate_no_user_inputs(mcp_server)
            # Only the profile resource (and its project template) may be
            # exposed; fail closed before accepting traffic.
            await validate_only_tools_are_exposed(mcp_server)
            # Resource providers must be initialized before traffic; otherwise
            # _LazyProvider resolves a Task/Future instead of AsyncClient/engine.
            await init_container_resources(resolved_container)
            telemetry = resolved_container.telemetry_buffer()
            await telemetry.start()
            # Registration is synchronous immediately after successful start.
            coordinator.register_telemetry(telemetry)
            yield

    app = FastAPI(
        title="Recallum",
        version=__version__,
        summary="Private persistent memory for AI coding agents over MCP.",
        lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
    )
    app.add_middleware(
        MCPAuthRateLimitMiddleware,
        limiter=limiter,
        attempts=resolved_settings.boundary.rate.invalid_mcp_auth_attempts,
        window_seconds=resolved_settings.boundary.rate.invalid_mcp_auth_window_seconds,
    )
    app.add_middleware(
        MCPBoundaryMiddleware,
        allowed_hosts=resolved_settings.boundary.mcp.allowed_hosts,
        allowed_origins=resolved_settings.boundary.mcp.allowed_origins,
    )
    app.add_middleware(
        TrustedClientResolver,
        trusted_cidrs=resolved_settings.boundary.proxy.trusted_cidrs,
    )
    # Middleware is wrapped in reverse registration order: body acceptance is
    # outermost, then client attribution must precede rate limiting.
    app.add_middleware(
        RequestBodyLimitMiddleware,
        general_body_bytes=resolved_settings.boundary.request.general_body_bytes,
        login_body_bytes=resolved_settings.boundary.request.login_body_bytes,
        password_max_chars=resolved_settings.boundary.request.password_max_chars,
    )
    # Registered last so it is outermost: one record per request including mounts.
    app.add_middleware(RequestTelemetryMiddleware)
    app.state.container = resolved_container
    app.state.mcp_server = mcp_server
    app.state.mcp_app = mcp_app
    app.include_router(create_health_router(resolved_container, resolved_settings))
    web_app = FastAPI(title="Recallum Web API", docs_url=None, redoc_url=None)

    @web_app.middleware("http")
    async def reject_untrusted_write_origins(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin is not None
            and origin != resolved_settings.web.allowed_origin
        ):
            return JSONResponse(
                {"detail": "Origin not allowed"},
                status_code=status.HTTP_403_FORBIDDEN,
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        return await call_next(request)

    @web_app.middleware("http")
    async def private_responses_are_uncacheable(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.web.allowed_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    web_authenticator = build_web_authenticator(
        resolved_container.web_session_service(), resolved_settings.web.cookie_name
    )
    web_app.include_router(
        create_auth_router(
            resolved_container.password_service(),
            resolved_container.web_session_service(),
            resolved_settings.web.cookie_name,
            web_authenticator,
            limiter=limiter,
            login_ip_attempts=resolved_settings.boundary.rate.login_ip_attempts,
            login_ip_window_seconds=resolved_settings.boundary.rate.login_ip_window_seconds,
            login_account_attempts=resolved_settings.boundary.rate.login_account_attempts,
            login_account_window_seconds=resolved_settings.boundary.rate.login_account_window_seconds,
            password_max_chars=resolved_settings.boundary.request.password_max_chars,
        )
    )
    web_app.include_router(
        create_admin_router(
            resolved_container.admin_service(),
            web_authenticator,
            password_max_chars=resolved_settings.boundary.request.password_max_chars,
        )
    )
    web_app.include_router(
        create_self_service_router(
            resolved_container.memory_service(),
            resolved_container.memory_repository(),
            resolved_container.api_key_service(),
            resolved_container.api_key_repository(),
            resolved_container.password_service(),
            resolved_container.telemetry_repository(),
            web_authenticator,
            resolved_settings.telemetry.retention_days,
            password_max_chars=resolved_settings.boundary.request.password_max_chars,
            get_search_sunset=resolved_settings.web.get_search_sunset,
        )
    )
    app.mount("/api/v1", web_app)
    app.mount("/mcp", mcp_app)
    return app
