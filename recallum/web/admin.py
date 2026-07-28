"""Administrator-only HTTP contract."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from recallum.db.repositories.user_repo import LastAdminError
from recallum.web.admin_service import (
    AdminNotFoundError,
    AdminPasswordError,
    AdminService,
    UserView,
)
from recallum.web.auth import WebAuthenticator, WebIdentity


class UserCreate(BaseModel):
    email: EmailStr
    is_admin: bool = False


class AdminUpdate(BaseModel):
    is_admin: bool


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    created_at: datetime
    is_admin: bool
    web_access: bool
    active_key_count: int


class KeyIssue(BaseModel):
    password: str = Field(min_length=1)
    name: str | None = None


class KeyResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class IssuedKeyResponse(KeyResponse):
    api_key: str


class MemoryVolume(BaseModel):
    user_id: uuid.UUID
    count: int


class AggregatesResponse(BaseModel):
    total_users: int
    active_keys: int
    revoked_keys: int
    memories: list[MemoryVolume]


class AdminStatusResponse(BaseModel):
    database: bool
    embeddings: bool
    embedding_model: str
    model_mismatch: bool


def _user_response(view: UserView) -> UserResponse:
    return UserResponse(
        id=view.user.id,
        email=view.user.email,
        created_at=view.user.created_at,
        is_admin=view.user.is_admin,
        web_access=view.user.password_hash is not None,
        active_key_count=view.active_key_count,
    )


def _key_response(key, **extra):
    return {
        "id": key.id,
        "name": key.name,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked": key.revoked_at is not None,
        **extra,
    }


def create_admin_router(
    service: AdminService, authenticate: WebAuthenticator
) -> APIRouter:
    async def require_admin(
        identity: Annotated[WebIdentity, Depends(authenticate)],
    ) -> WebIdentity:
        if not identity.user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return identity

    router = APIRouter(
        prefix="/admin",
        tags=["admin"],
        dependencies=[Depends(require_admin)],
    )
    AdminIdentity = Annotated[WebIdentity, Depends(require_admin)]

    @router.get("/users", response_model=list[UserResponse])
    async def list_users() -> list[UserResponse]:
        return [_user_response(view) for view in await service.list_users()]

    @router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
    async def create_user(body: UserCreate) -> UserResponse:
        try:
            return _user_response(await service.create_user(str(body.email), body.is_admin))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.put("/users/{user_id}/admin", response_model=UserResponse)
    async def set_admin(user_id: uuid.UUID, body: AdminUpdate) -> UserResponse:
        try:
            user = await service.set_admin(user_id, body.is_admin)
            active = sum(key.revoked_at is None for key in await service.list_keys(user.id))
            return _user_response(UserView(user, active))
        except LastAdminError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one administrator is required",
            ) from exc
        except AdminNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc

    @router.get("/users/{user_id}/keys", response_model=list[KeyResponse])
    async def list_keys(user_id: uuid.UUID):
        try:
            return [_key_response(key) for key in await service.list_keys(user_id)]
        except AdminNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc

    @router.post(
        "/users/{user_id}/keys",
        response_model=IssuedKeyResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def issue_key(
        user_id: uuid.UUID, body: KeyIssue, admin: AdminIdentity
    ) -> dict:
        try:
            issued = await service.issue_key(
                user_id, admin.user, body.password, body.name
            )
            return _key_response(issued.key, api_key=issued.plaintext)
        except AdminPasswordError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
        except AdminNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc

    @router.post(
        "/users/{user_id}/keys/{key_id}/revoke",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def revoke_key(user_id: uuid.UUID, key_id: uuid.UUID) -> None:
        try:
            await service.revoke_key(user_id, key_id)
        except AdminNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc

    @router.get("/aggregates", response_model=AggregatesResponse)
    async def aggregates() -> AggregatesResponse:
        total, active, revoked, counts = await service.aggregates()
        return AggregatesResponse(
            total_users=total,
            active_keys=active,
            revoked_keys=revoked,
            memories=[
                MemoryVolume(user_id=user_id, count=count)
                for user_id, count in counts.items()
            ],
        )

    @router.get("/status", response_model=AdminStatusResponse)
    async def detailed_status() -> AdminStatusResponse:
        database, embeddings, model, mismatch = await service.status()
        return AdminStatusResponse(
            database=database,
            embeddings=embeddings,
            embedding_model=model,
            model_mismatch=mismatch,
        )

    return router
