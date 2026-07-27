"""FastMCP middleware enforcing ``Authorization: Bearer`` on every tool call."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext

from recallum.auth.api_keys import hash_token
from recallum.auth.identity import Identity, identity_scope
from recallum.db.repositories.api_key_repo import ApiKeyRepository

logger = logging.getLogger("recallum.auth")


# How stale ``last_used_at`` may get before authentication refreshes it. Every
# refresh is a write on a row that a busy agent hits on every single tool call,
# so the timestamp trades exactness for not serialising the hot path.
LAST_USED_REFRESH_INTERVAL = timedelta(seconds=60)


class TokenAuthenticator:
    """Resolves a raw bearer token to an ``Identity`` via its stored hash.

    Authenticating refreshes ``last_used_at``, but at most once per
    ``refresh_interval`` — the timestamp answers "is this key still in use?",
    not "when exactly was the last call?".
    """

    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        refresh_interval: timedelta = LAST_USED_REFRESH_INTERVAL,
    ) -> None:
        self._keys = api_key_repository
        self._refresh_interval = refresh_interval

    async def authenticate(self, token: str) -> Identity | None:
        if not token:
            return None
        found = await self._keys.find_active_by_hash(hash_token(token))
        if found is None:
            return None
        key, user = found
        if self._needs_refresh(key.last_used_at):
            await self._keys.touch(key.id)
        return Identity(user_id=user.id, email=user.email, api_key_id=key.id)

    def _needs_refresh(self, last_used_at: datetime | None) -> bool:
        if last_used_at is None:
            return True
        return datetime.now(UTC) - last_used_at >= self._refresh_interval


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
