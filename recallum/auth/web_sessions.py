"""Creation, renewal, rotation, reuse detection, and revocation of web sessions."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from recallum.auth.api_keys import hash_token
from recallum.db.models import User, WebSession
from recallum.db.repositories.web_session_repo import WebSessionRepository


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session: WebSession


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    user: User
    session: WebSession
    rotated_token: str | None = None


class WebSessionService:
    def __init__(
        self,
        repository: WebSessionRepository,
        *,
        idle_window: timedelta,
        absolute_window: timedelta,
        rotation_threshold: float,
        rotation_grace: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._idle = idle_window
        self._absolute = absolute_window
        self._threshold = rotation_threshold
        self._grace = rotation_grace
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def idle_window(self) -> timedelta:
        """How long a cookie stays useful, so the browser can be told to keep it."""
        return self._idle

    async def create(self, user_id) -> IssuedSession:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        absolute = now + self._absolute
        row = await self._repository.create(
            user_id, hash_token(token), now, min(now + self._idle, absolute), absolute
        )
        return IssuedSession(token, row)

    async def resolve(self, token: str) -> ResolvedSession | None:
        found = await self._repository.find_by_hash(hash_token(token))
        if found is None:
            return None
        row, user = found
        now = self._clock()
        if row.rotated_to_id is not None:
            successor = await self._still_rotating(row, now)
            if successor is not None:
                return ResolvedSession(user, successor)
            await self._repository.revoke_chain(row.id, now)
            return None
        if (
            row.revoked_at is not None
            or now >= row.idle_expires_at
            or now >= row.absolute_expires_at
        ):
            return None
        if now - row.created_at < self._idle * self._threshold:
            return ResolvedSession(user, row)

        token = secrets.token_urlsafe(32)
        replacement = await self._repository.rotate(
            row.id,
            row.user_id,
            hash_token(token),
            now,
            min(now + self._idle, row.absolute_expires_at),
            row.absolute_expires_at,
        )
        if replacement is None:
            # A concurrent request won the rotation race. Treat the old token
            # as reused and invalidate the successor it just created.
            await self._repository.revoke_chain(row.id, now)
            return None
        return ResolvedSession(user, replacement, token)

    async def _still_rotating(self, row: WebSession, now: datetime) -> WebSession | None:
        """The successor, while the browser may legitimately still hold the old token.

        A single page load fires several requests at once and every one carries
        the same cookie. One of them rotates; the others were already in flight
        and land holding a token that went stale on the wire. Treating those as
        replay revoked the whole chain -- including the successor just minted --
        and logged the user out roughly every ``idle_window * rotation_threshold``,
        which is what "I have to sign in again every few days" actually was.

        Inside the grace window the request is served on the successor and no
        cookie is re-issued: the sibling that won the rotation already sent it,
        and only that one holds the new token in the clear. Past the window an
        old token is a genuine reuse signal and the caller still burns the chain.
        """
        if row.revoked_at is not None:
            return None
        successor = await self._repository.find_by_id(row.rotated_to_id)
        if successor is None or successor.revoked_at is not None:
            return None
        if now - successor.created_at > self._grace:
            return None
        if now >= successor.idle_expires_at or now >= successor.absolute_expires_at:
            return None
        return successor

    async def revoke(self, session_id) -> None:
        await self._repository.revoke(session_id, self._clock())
