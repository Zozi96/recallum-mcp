"""Password login and cookie-backed web identity endpoints."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from recallum.auth.passwords import PasswordService
from recallum.auth.web_sessions import WebSessionService
from recallum.db.models import User

COOKIE_PATH = "/api/v1"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


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


def _set_cookie(response: Response, name: str, token: str) -> None:
    response.set_cookie(
        name,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        path=COOKIE_PATH,
    )


class WebAuthenticator:
    """Shared cookie dependency for every authenticated web route."""

    def __init__(
        self, sessions: WebSessionService, cookie_name: str
    ) -> None:
        self._sessions = sessions
        self._cookie_name = cookie_name

    async def __call__(self, request: Request, response: Response) -> WebIdentity:
        token = request.cookies.get(self._cookie_name)
        resolved = await self._sessions.resolve(token) if token else None
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        if resolved.rotated_token:
            _set_cookie(response, self._cookie_name, resolved.rotated_token)
        return WebIdentity(resolved.user, resolved.session.id)


def create_auth_router(
    passwords: PasswordService,
    sessions: WebSessionService,
    cookie_name: str,
    authenticate: WebAuthenticator,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/login", response_model=IdentityResponse)
    async def login(body: LoginRequest, response: Response) -> IdentityResponse:
        user = await passwords.authenticate(str(body.email), body.password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        issued = await sessions.create(user.id)
        _set_cookie(response, cookie_name, issued.token)
        return IdentityResponse(id=user.id, email=user.email, is_admin=user.is_admin)

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        identity: Annotated[WebIdentity, Depends(authenticate)], response: Response
    ) -> None:
        await sessions.revoke(identity.session_id)
        response.delete_cookie(cookie_name, path=COOKIE_PATH, secure=True, httponly=True)

    @router.get("/me", response_model=IdentityResponse)
    async def me(
        identity: Annotated[WebIdentity, Depends(authenticate)],
    ) -> IdentityResponse:
        return identity.response

    return router
