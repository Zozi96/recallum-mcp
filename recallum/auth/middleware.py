"""FastMCP authentication and request-scoped identity binding."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext

from recallum.auth.api_keys import hash_token
from recallum.auth.identity import Identity, identity_scope
from recallum.db.repositories.api_key_repo import ApiKeyRepository

logger = logging.getLogger("recallum.auth")


# How stale ``last_used_at`` may get before authentication refreshes it. Every
# refresh is a write on a row that a busy agent hits on every single tool call,
# so the timestamp trades exactness for not serialising the hot path.
LAST_USED_REFRESH_INTERVAL = timedelta(seconds=60)

# How long a successful authentication may be reused without asking PostgreSQL
# again. Defaults to five seconds: a small window that still removes the
# per-call database round trip for a busy agent while keeping the revocation
# window small. Set ``RECALLUM__AUTH__IDENTITY_CACHE_SECONDS`` to 0 to restore
# immediate revocation at the cost of a database hit on every call.
IDENTITY_CACHE_TTL = timedelta(seconds=5)

# Only successful authentications are cached, so the ceiling is the number of
# real, valid keys rather than anything an unauthenticated caller controls. It
# exists so a large key population cannot grow the process without bound.
MAX_CACHED_IDENTITIES = 1024


class TokenAuthenticator:
    """Resolves a raw bearer token to an ``Identity`` via its stored hash.

    Authenticating refreshes ``last_used_at``, but at most once per
    ``refresh_interval`` — the timestamp answers "is this key still in use?",
    not "when exactly was the last call?".

    With ``cache_ttl`` above zero a successful resolution is reused for that
    long. Every tool call authenticates, and each authentication costs a pool
    checkout, a transaction and a query — against a pool of five, before the
    call's own work starts — so caching removes a round trip from the hot path.

    It defaults to five seconds, a small window that removes the per-call
    database round trip for a busy agent while keeping the revocation window
    small. Set the TTL to zero to restore immediate revocation at the cost of
    a database hit on every call.

    Failures are never cached, so an unknown, malformed or already-revoked
    token always reaches the database and always fails closed. Only the window
    after a *successful* authentication is affected.
    """

    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        refresh_interval: timedelta = LAST_USED_REFRESH_INTERVAL,
        cache_ttl: timedelta = IDENTITY_CACHE_TTL,
        max_cached: int = MAX_CACHED_IDENTITIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._keys = api_key_repository
        self._refresh_interval = refresh_interval
        self._cache_ttl = max(cache_ttl.total_seconds(), 0.0)
        self._max_cached = max_cached
        self._clock = clock
        # Keyed by token hash, never by the raw token.
        self._cache: dict[str, tuple[Identity, float]] = {}

    async def authenticate(self, token: str) -> Identity | None:
        if not token:
            return None
        key_hash = hash_token(token)

        cached = self._cached(key_hash)
        if cached is not None:
            return cached

        found = await self._keys.find_active_by_hash(key_hash)
        if found is None:
            return None
        key, user = found
        if self._needs_refresh(key.last_used_at):
            await self._keys.touch(key.id)
        identity = Identity(user_id=user.id, email=user.email, api_key_id=key.id)
        self._remember(key_hash, identity)
        return identity

    def _cached(self, key_hash: str) -> Identity | None:
        entry = self._cache.get(key_hash)
        if entry is None:
            return None
        identity, expires_at = entry
        if self._clock() >= expires_at:
            self._cache.pop(key_hash, None)
            return None
        return identity

    def _remember(self, key_hash: str, identity: Identity) -> None:
        if self._cache_ttl <= 0:
            return
        if len(self._cache) >= self._max_cached:
            self._evict_expired()
        if len(self._cache) >= self._max_cached:
            # Still full of live entries: drop the one closest to expiring, so
            # the cache stays bounded without ever extending anyone's window.
            soonest = min(self._cache, key=lambda h: self._cache[h][1])
            self._cache.pop(soonest, None)
        self._cache[key_hash] = (identity, self._clock() + self._cache_ttl)

    def _evict_expired(self) -> None:
        now = self._clock()
        for key_hash in [h for h, (_, expires) in self._cache.items() if now >= expires]:
            self._cache.pop(key_hash, None)

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
    """Bind the identity already verified by FastMCP's HTTP auth middleware."""

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def on_read_resource(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def on_list_tools(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def on_list_resources(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def on_list_resource_templates(
        self, context: MiddlewareContext, call_next: Any
    ) -> Any:
        return await self._with_identity(context, call_next)

    async def on_list_prompts(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def on_get_prompt(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._with_identity(context, call_next)

    async def _with_identity(self, context: MiddlewareContext, call_next: Any) -> Any:
        identity = self._identity_from_access_token()
        with identity_scope(identity):
            return await call_next(context)

    @staticmethod
    def _identity_from_access_token() -> Identity:
        access_token = get_access_token()
        if access_token is None:
            raise ToolError("authentication required")
        try:
            subject = access_token.subject
            client_id = access_token.client_id
            claims = access_token.claims or {}
            email = claims.get("email")
            if (
                not isinstance(subject, str)
                or not isinstance(client_id, str)
                or not isinstance(email, str)
                or not email
                or not isinstance(claims, dict)
            ):
                raise ValueError("malformed access token claims")
            return Identity(
                user_id=uuid.UUID(subject),
                email=email,
                api_key_id=uuid.UUID(client_id),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.warning("rejected request with malformed auth claims")
            raise ToolError("invalid authenticated identity") from exc


class RecallumTokenVerifier(TokenVerifier):
    """Expose the repository-backed API-key verifier to FastMCP's HTTP layer."""

    def __init__(self, authenticator: TokenAuthenticator) -> None:
        super().__init__()
        self._authenticator = authenticator

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = await self._authenticator.authenticate(token)
        if identity is None:
            return None
        return AccessToken(
            token=token,
            client_id=str(identity.api_key_id),
            scopes=[],
            subject=str(identity.user_id),
            claims={"email": identity.email},
        )


__all__ = [
    "BearerAuthMiddleware",
    "IDENTITY_CACHE_TTL",
    "MAX_CACHED_IDENTITIES",
    "RecallumTokenVerifier",
    "TokenAuthenticator",
    "_extract_bearer",
]
