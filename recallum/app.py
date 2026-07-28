"""FastAPI application factory.

FastAPI hosts operational endpoints (liveness/readiness) and mounts the
FastMCP HTTP app at ``/mcp``; both lifespans are composed so the MCP session
manager and the DI-owned engine/HTTP client start and stop in order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans
from pydantic import BaseModel

from recallum.config import Settings, get_settings
from recallum.container import Container, create_container, shutdown_container
from recallum.logging_setup import setup_logging
from recallum.mcp.server import (
    build_mcp_server,
    validate_no_user_inputs,
    validate_only_tools_are_exposed,
)
from recallum.web.admin import create_admin_router
from recallum.web.auth import WebAuthenticator, create_auth_router


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


def create_health_router(container: Container) -> APIRouter:
    """Operational endpoints: /healthz and /readyz."""
    router = APIRouter(tags=["health"])

    @router.get("/healthz", summary="Liveness probe")
    async def healthz() -> LivenessResponse:
        return LivenessResponse(status="alive")

    @router.get(
        "/readyz",
        summary="Readiness probe (PostgreSQL and Ollama)",
        responses={503: {"model": ReadinessResponse}},
    )
    async def readyz() -> ReadinessResponse:
        database_ok = await container.database_readiness().is_ready()
        embeddings_ok = await container.embedding_client().is_available()
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

    mcp_server = build_mcp_server(resolved_container)
    mcp_app = mcp_server.http_app(path="/")

    @asynccontextmanager
    async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = resolved_container
        app.state.mcp_server = mcp_server
        await validate_no_user_inputs(mcp_server)
        # Bearer auth only guards on_call_tool, so any other surface would be
        # unauthenticated. Fail closed at startup rather than in production.
        await validate_only_tools_are_exposed(mcp_server)
        yield
        await shutdown_container(resolved_container)

    app = FastAPI(
        title="Recallum",
        version="0.3.0",
        summary="Private persistent memory for AI coding agents over MCP.",
        lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
    )
    app.state.container = resolved_container
    app.state.mcp_server = mcp_server
    app.include_router(create_health_router(resolved_container))
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
            )
        return await call_next(request)

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.web.allowed_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )
    web_authenticator = WebAuthenticator(
        resolved_container.web_session_service(), resolved_settings.web.cookie_name
    )
    web_app.include_router(
        create_auth_router(
            resolved_container.password_service(),
            resolved_container.web_session_service(),
            resolved_settings.web.cookie_name,
            web_authenticator,
        )
    )
    web_app.include_router(
        create_admin_router(resolved_container.admin_service(), web_authenticator)
    )
    app.mount("/api/v1", web_app)
    app.mount("/mcp", mcp_app)
    return app
