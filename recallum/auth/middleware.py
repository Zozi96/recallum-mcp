"""FastMCP middleware enforcing ``Authorization: Bearer`` on every tool call."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
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

# How long a successful authentication may be reused without asking PostgreSQL
# again. Disabled by default: this is a security parameter before it is a
# performance one, and the default must not quietly trade away the property
# that revoking a key stops it on the very next call. Operators who would
# rather spend that guarantee on a saved round trip per tool call opt in with
# ``RECALLUM__AUTH__IDENTITY_CACHE_SECONDS``, accepting a revocation window of
# exactly that many seconds.
IDENTITY_CACHE_TTL = timedelta(0)

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

    It is off by default because the price is paid in a different currency:
    a key revoked through the admin CLI keeps working until its entry expires,
    and since the cache lives in the process, each worker expires on its own
    schedule. That turns revocation from immediate into eventually-consistent,
    which is a call for whoever runs the server, not a default worth assuming.

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
