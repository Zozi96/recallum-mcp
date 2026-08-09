"""Password login and cookie-backed web identity endpoints."""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, EmailStr

from recallum.auth.passwords import PasswordService
from recallum.auth.web_sessions import WebSessionService
from recallum.boundary_types import Password, password_model
from recallum.db.models import User
from recallum.http_boundary import (
    FixedWindowLimiter,
    RateLimitExceeded,
    attributed_client_ip,
)
from recallum.web.openapi_responses import LOGIN_RESPONSES, PROTECTED_RESPONSES

COOKIE_PATH = "/api/v1"


class LoginRequest(BaseModel):
    email: EmailStr
    password: Password


class IdentityResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    is_admin: bool


@dataclass(frozen=True, slots=True)
class WebIdentity:
    user: User
    session_id: uuid.UUID

    @property
    def response(self) -> IdentityResponse:
        return IdentityResponse(
            id=self.user.id, email=self.user.email, is_admin=self.user.is_admin
        )


def _set_cookie(response: Response, name: str, token: str, max_age: timedelta) -> None:
    response.set_cookie(
        name,
        token,
        # Without Max-Age this is a session cookie: the browser drops it on
        # quit, so a server-side session good for days died at the end of the
        # afternoon. It tracks the idle window and is re-issued on rotation,
        # so the cookie expires alongside the session it stands for.
        max_age=int(max_age.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path=COOKIE_PATH,
    )


class WebAuthenticator:
    """Shared cookie dependency for every authenticated web route."""

    def __init__(
        self,
        sessions: WebSessionService,
        cookie_name: str,
        scheme: APIKeyCookie | None = None,
    ) -> None:
        self._sessions = sessions
        self._cookie_name = cookie_name
        self.scheme = scheme or APIKeyCookie(name=cookie_name, auto_error=False)

    async def resolve(self, token: str | None, response: Response) -> WebIdentity:
        resolved = await self._sessions.resolve(token) if token else None
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        if resolved.rotated_token:
            _set_cookie(
                response, self._cookie_name, resolved.rotated_token, self._sessions.idle_window
            )
        return WebIdentity(resolved.user, resolved.session.id)

    async def __call__(self, request: Request, response: Response) -> WebIdentity:
        # Fallback signature; ``build_web_authenticator`` replaces this class
        # with a Security-bound subclass for OpenAPI.
        return await self.resolve(request.cookies.get(self._cookie_name), response)


def build_web_authenticator(
    sessions: WebSessionService, cookie_name: str
) -> WebAuthenticator:
    """Bind ``APIKeyCookie``/``Security`` so OpenAPI marks protected routes."""
    scheme = APIKeyCookie(name=cookie_name, auto_error=False)

    class BoundWebAuthenticator(WebAuthenticator):
        async def __call__(
            self,
            response: Response,
            api_key: Annotated[str | None, Security(scheme)] = None,
        ) -> WebIdentity:
            return await self.resolve(api_key, response)

    return BoundWebAuthenticator(sessions, cookie_name, scheme)


def create_auth_router(
    passwords: PasswordService,
    sessions: WebSessionService,
    cookie_name: str,
    authenticate: WebAuthenticator,
    *,
    limiter: FixedWindowLimiter | None = None,
    login_ip_attempts: int = 30,
    login_ip_window_seconds: int = 300,
    login_account_attempts: int = 5,
    login_account_window_seconds: int = 300,
    password_max_chars: int = 256,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    configured_login_request = password_model(LoginRequest, password_max_chars)

    @router.post(
        "/login",
        response_model=IdentityResponse,
        responses=LOGIN_RESPONSES,
        openapi_extra={"security": []},
    )
    async def login(
        request: Request, body: configured_login_request, response: Response
    ) -> IdentityResponse:
        if len(body.password) > password_max_chars:
            raise HTTPException(status_code=422, detail="password is too long")
        reservations = ()

        async def release_reservations() -> None:
            if limiter is None:
                return
            for reservation in reservations:
                await asyncio.shield(limiter.release(reservation))

        if limiter is not None:
            client_ip = attributed_client_ip(request.scope)
            normalized_email = str(body.email).strip().lower()
            account_hash = hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()
            try:
                reservations = await limiter.reserve_many(
                    (
                        (f"login-ip:{client_ip}", login_ip_attempts, login_ip_window_seconds),
                        (
                            f"login-account:{client_ip}:{account_hash}",
                            login_account_attempts,
                            login_account_window_seconds,
                        ),
                    )
                )
            except RateLimitExceeded as exc:
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts",
                    headers={"Retry-After": str(exc.retry_after)},
                ) from None
        try:
            user = await passwords.authenticate(str(body.email), body.password)
        except BaseException:
            await release_reservations()
            raise
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        await release_reservations()
        issued = await sessions.create(user.id)
        _set_cookie(response, cookie_name, issued.token, sessions.idle_window)
        return IdentityResponse(id=user.id, email=user.email, is_admin=user.is_admin)

    @router.post(
        "/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=PROTECTED_RESPONSES,
    )
    async def logout(
        identity: Annotated[WebIdentity, Depends(authenticate)], response: Response
    ) -> None:
        await sessions.revoke(identity.session_id)
        response.delete_cookie(cookie_name, path=COOKIE_PATH, secure=True, httponly=True)

    @router.get("/me", response_model=IdentityResponse, responses=PROTECTED_RESPONSES)
    async def me(
        identity: Annotated[WebIdentity, Depends(authenticate)],
    ) -> IdentityResponse:
        return identity.response

    return router
