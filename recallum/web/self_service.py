"""Session-authenticated self-service memory and credential API."""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from recallum.auth.api_keys import ApiKeyService
from recallum.auth.passwords import PasswordService
from recallum.db.models import ApiKey, Memory
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.memory_repo import MemoryRepository
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.schemas import (
    ListResult,
    MemoryOut,
    RecallResult,
    RememberResult,
)
from recallum.memory.service import MemoryService
from recallum.web.auth import WebAuthenticator, WebIdentity

Category = Literal["preference", "decision", "constraint", "fact"]
Scope = Literal["global", "project"]
Metadata = dict[str, str | int | float | bool | None]
logger = logging.getLogger(__name__)


class DomainRoute(APIRoute):
    """Translate stable domain failures at the HTTP boundary."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except MemoryValidationError as exc:
                code = 409 if "already has that content" in str(exc) else 422
                raise HTTPException(status_code=code, detail=str(exc)) from exc
            except EmbeddingError:
                logger.warning("embedding operation unavailable", exc_info=True)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "embeddings_unavailable",
                        "message": "Embedding service unavailable",
                    },
                ) from None

        return handler


class CreateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str
    category: Category
    scope: Scope | None = None
    project: str | None = None
    importance: int = 5
    metadata: Metadata | None = None
    source_client: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope == "global" and self.project is not None:
            raise ValueError("global scope cannot include a project")
        if self.scope == "project" and (
            self.project is None or not self.project.strip()
        ):
            raise ValueError("project scope requires a project")
        return self


class MemoryLocationImmutableRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def reject_location_changes(cls, value):
        if isinstance(value, dict) and {"scope", "project"} & value.keys():
            raise ValueError("scope and project cannot be changed")
        return value


class CorrectMemoryRequest(MemoryLocationImmutableRequest):
    category: Category | None = None
    importance: int | None = None
    metadata: Metadata | None = None


class SupersedeMemoryRequest(MemoryLocationImmutableRequest):
    content: str
    category: Category | None = None
    importance: int | None = None
    metadata: Metadata | None = None
    source_client: str | None = None


class SupersedeResponse(BaseModel):
    superseded_id: uuid.UUID
    memory: MemoryOut


class HistoryItem(BaseModel):
    id: uuid.UUID
    content: str
    category: Category
    importance: int
    created_at: datetime
    retired_at: datetime


class HistoryResponse(BaseModel):
    items: list[HistoryItem]


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class IssueApiKeyRequest(BaseModel):
    password: str = Field(min_length=1)
    name: str | None = None


class IssuedApiKeyResponse(ApiKeyResponse):
    secret: str


class StatisticsResponse(BaseModel):
    active: int
    superseded: int
    retired: int
    by_category: dict[str, int]
    by_scope: dict[str, int]
    by_project: dict[str, int]
    by_importance: dict[str, int]
    created_by_day: dict[str, int]
    volume_bytes: int


def _memory(row: Memory) -> MemoryOut:
    return MemoryOut(
        id=row.id,
        scope=row.scope,
        project=row.project,
        category=row.category,
        content=row.content,
        importance=row.importance,
        source_client=row.source_client,
        metadata=dict(row.metadata_ or {}),
        created_at=row.created_at,
    )


def _key(row: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def create_self_service_router(
    memories: MemoryService,
    repository: MemoryRepository,
    api_keys: ApiKeyService,
    key_repository: ApiKeyRepository,
    passwords: PasswordService,
    authenticate: WebAuthenticator,
) -> APIRouter:
    identity = Annotated[WebIdentity, Depends(authenticate)]
    router = APIRouter(
        prefix="/me",
        tags=["self-service"],
        dependencies=[Depends(authenticate)],
        route_class=DomainRoute,
    )

    @router.get("/memories", response_model=ListResult)
    async def list_memories(
        current: identity,
        scope: Annotated[Scope | None, Query()] = None,
        project: Annotated[str | None, Query()] = None,
        category: Annotated[Category | None, Query()] = None,
        limit: Annotated[int | None, Query()] = None,
        offset: Annotated[int, Query()] = 0,
    ) -> ListResult:
        return await memories.list_memories(
            current.user.id,
            scope=scope,
            project=project,
            category=category,
            limit=limit,
            offset=offset,
        )

    @router.get("/memories/search", response_model=RecallResult)
    async def search_memories(
        current: identity,
        query: Annotated[str, Query(min_length=1)],
        project: Annotated[str | None, Query()] = None,
        scope: Annotated[Scope | None, Query()] = None,
        category: Annotated[Category | None, Query()] = None,
        limit: Annotated[int | None, Query()] = None,
    ) -> RecallResult:
        return await memories.recall(
            current.user.id,
            query=query,
            project=project,
            scope=scope,
            category=category,
            limit=limit,
        )

    @router.post("/memories", response_model=RememberResult, status_code=201)
    async def create_memory(body: CreateMemoryRequest, current: identity) -> RememberResult:
        result = await memories.remember(
            current.user.id, **body.model_dump(exclude={"scope"})
        )
        if not result.created:
            raise HTTPException(status_code=409, detail="Memory already exists")
        return result

    @router.get("/memories/{memory_id}", response_model=MemoryOut)
    async def get_memory(memory_id: uuid.UUID, current: identity) -> MemoryOut:
        row = await repository.get_active(current.user.id, memory_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return _memory(row)

    @router.patch("/memories/{memory_id}", response_model=MemoryOut)
    async def correct_memory(
        memory_id: uuid.UUID, body: CorrectMemoryRequest, current: identity
    ) -> MemoryOut:
        result = await memories.update(
            current.user.id, memory_id, **body.model_dump(exclude_unset=True)
        )
        if not result.updated or result.memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return result.memory

    @router.post("/memories/{memory_id}/supersede", response_model=SupersedeResponse)
    async def supersede_memory(
        memory_id: uuid.UUID, body: SupersedeMemoryRequest, current: identity
    ) -> SupersedeResponse:
        result = await memories.update(
            current.user.id,
            memory_id,
            **body.model_dump(exclude_unset=True),
        )
        if not result.updated or result.memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return SupersedeResponse(superseded_id=memory_id, memory=result.memory)

    @router.delete("/memories/{memory_id}", status_code=204)
    async def forget_memory(memory_id: uuid.UUID, current: identity) -> None:
        result = await memories.forget(current.user.id, memory_id)
        if not result.forgotten:
            raise HTTPException(status_code=404, detail="Memory not found")

    @router.get("/memories/{memory_id}/history", response_model=HistoryResponse)
    async def memory_history(memory_id: uuid.UUID, current: identity) -> HistoryResponse:
        rows = await repository.history(current.user.id, memory_id)
        if rows is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return HistoryResponse(
            items=[
                HistoryItem(
                    id=row.id,
                    content=row.content,
                    category=row.category,
                    importance=row.importance,
                    created_at=row.created_at,
                    retired_at=row.deleted_at,
                )
                for row in rows
                if row.deleted_at is not None
            ]
        )

    @router.get("/api-keys", response_model=list[ApiKeyResponse])
    async def list_api_keys(current: identity) -> list[ApiKeyResponse]:
        return [_key(row) for row in await api_keys.list_keys(current.user.id)]

    @router.post("/api-keys", response_model=IssuedApiKeyResponse, status_code=201)
    async def issue_api_key(body: IssueApiKeyRequest, current: identity) -> IssuedApiKeyResponse:
        password_hash = current.user.password_hash
        if password_hash is None or not await passwords.verify(password_hash, body.password):
            raise HTTPException(status_code=403, detail="Invalid password")
        issued = await api_keys.issue_key(current.user.id, body.name)
        return IssuedApiKeyResponse(**_key(issued.key).model_dump(), secret=issued.plaintext)

    @router.delete("/api-keys/{key_id}", status_code=204)
    async def revoke_api_key(key_id: uuid.UUID, current: identity) -> None:
        if not await key_repository.revoke_for_user(current.user.id, key_id):
            raise HTTPException(status_code=404, detail="API key not found")

    @router.get("/stats", response_model=StatisticsResponse)
    async def statistics(current: identity) -> StatisticsResponse:
        return StatisticsResponse.model_validate(await repository.statistics(current.user.id))

    return router


__all__ = ["create_self_service_router"]
