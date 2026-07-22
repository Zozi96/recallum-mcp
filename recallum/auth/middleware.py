"""FastMCP middleware enforcing ``Authorization: Bearer`` on every tool call."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext

from recallum.auth.api_keys import hash_token
from recallum.auth.identity import Identity, identity_scope
from recallum.db.repositories.api_key_repo import ApiKeyRepository

logger = logging.getLogger("recallum.auth")


class TokenAuthenticator:
    """Resolves a raw bearer token to an ``Identity`` via its stored hash."""

    def __init__(self, api_key_repository: ApiKeyRepository) -> None:
        self._keys = api_key_repository

    async def authenticate(self, token: str) -> Identity | None:
        if not token:
            return None
        found = await self._keys.find_active_by_hash(hash_token(token))
        if found is None:
            return None
        key, user = found
        await self._keys.touch(key.id)
        return Identity(user_id=user.id, email=user.email, api_key_id=key.id)


def _extract_bearer(headers: dict[str, str]) -> str | None:
    value = headers.get("authorization")
    if value is None:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


class BearerAuthMiddleware(Middleware):
    """Validates the bearer token before any tool executes and binds identity.

    Rejected calls raise ``ToolError`` so no memory logic runs. The header is
    read with ``include={"authorization"}`` because FastMCP strips it from the
    default header view to avoid accidental forwarding.
    """

    def __init__(self, authenticator: TokenAuthenticator) -> None:
        self._authenticator = authenticator

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        identity = await self._resolve_identity()
        with identity_scope(identity):
            return await call_next(context)

    async def _resolve_identity(self) -> Identity:
        headers = get_http_headers(include={"authorization"})
        token = _extract_bearer(headers)
        if token is None:
            raise ToolError("authentication required: send 'Authorization: Bearer <api-key>'")
        identity = await self._authenticator.authenticate(token)
        if identity is None:
            logger.info("rejected request with invalid or revoked api key")
            raise ToolError("invalid or revoked API key")
        return identity
