"""FastAPI application factory.

FastAPI hosts operational endpoints (liveness/readiness) and mounts the
FastMCP HTTP app at ``/mcp``; both lifespans are composed so the MCP session
manager and the DI-owned engine/HTTP client start and stop in order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans
from pydantic import BaseModel

from recallum.config import Settings, get_settings
from recallum.container import Container, create_container, shutdown_container
from recallum.logging_setup import setup_logging
from recallum.mcp.server import build_mcp_server, validate_no_user_inputs


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
        yield
        await shutdown_container(resolved_container)

    app = FastAPI(
        title="Recallum",
        version="0.1.0",
        summary="Private persistent memory for AI coding agents over MCP.",
        lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
    )
    app.state.container = resolved_container
    app.state.mcp_server = mcp_server
    app.include_router(create_health_router(resolved_container))
    app.mount("/mcp", mcp_app)
    return app
