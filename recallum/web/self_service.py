"""Session-authenticated self-service memory and credential API."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from recallum.auth.api_keys import ApiKeyService
from recallum.auth.passwords import PasswordService
from recallum.boundary_types import (
    Password,
    StrictImportanceInput,
    StrictPositiveLimit,
    StrictQueryNonNegativeOffset,
    StrictQueryPositiveLimit,
    password_model,
)
from recallum.db.models import ApiKey, Memory
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.memory_repo import MemoryRepository
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.schemas import (
    ListResult,
    MemoryGraphResponse,
    MemoryOut,
    MergeResult,
    ProfileBlock,
    ReassignResult,
    RecallResult,
    ReconfirmResult,
    RelatedMemoriesResult,
    RememberResult,
    SourceType,
)
from recallum.memory.service import MemoryService
from recallum.telemetry.repository import TelemetryRepository
from recallum.web.auth import WebAuthenticator, WebIdentity
from recallum.web.openapi_responses import PROTECTED_RESPONSES

Category = Literal["preference", "decision", "constraint", "fact"]
Scope = Literal["global", "project"]
Metadata = dict[str, str | int | float | bool | None]
logger = logging.getLogger(__name__)
DEFAULT_GET_SEARCH_SUNSET = "Tue, 01 Dec 2026 00:00:00 GMT"


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
    importance: StrictImportanceInput = 5
    metadata: Metadata | None = None
    source_client: str | None = None
    ttl_seconds: int | None = None
    source_type: SourceType | None = None
    source_ref: str | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope == "global" and self.project is not None:
            raise ValueError("global scope cannot include a project")
        if self.scope == "project" and (self.project is None or not self.project.strip()):
            raise ValueError("project scope requires a project")
        return self


class ReassignProjectRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_project: str = Field(min_length=1)
    to_project: str = Field(min_length=1)


class MergeMemoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_ids: list[uuid.UUID] = Field(min_length=2)
    content: str
    category: Category
    importance: StrictImportanceInput | None = None
    metadata: Metadata | None = None
    source_client: str | None = None


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
    importance: StrictImportanceInput | None = None
    metadata: Metadata | None = None
    ttl_seconds: int | None = None
    clear_expiry: bool = False
    source_type: SourceType | None = None
    source_ref: str | None = None


class SupersedeMemoryRequest(MemoryLocationImmutableRequest):
    content: str
    category: Category | None = None
    importance: StrictImportanceInput | None = None
    metadata: Metadata | None = None
    source_client: str | None = None
    source_type: SourceType | None = None
    source_ref: str | None = None


class SearchMemoriesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(min_length=1)
    project: str | None = None
    scope: Scope | None = None
    category: Category | None = None
    limit: StrictPositiveLimit | None = None
    max_tokens: StrictPositiveLimit | None = None
    strategy: Literal["coding", "debugging", "planning", "review", "architecture"] | None = None


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
    password: Password
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


class ActivityResponse(BaseModel):
    start: datetime
    end: datetime
    total_calls: int
    total_results: int
    failed_calls: int
    failure_rate: float
    degraded_calls: int
    degradation_rate: float
    by_day: dict[str, int]
    by_tool: dict[str, int]
    by_project: dict[str, int]


def _memory(row: Memory) -> MemoryOut:
    return MemoryOut(
        id=row.id,
        scope=row.scope,
        project=row.project,
        category=row.category,
        content=row.content,
        importance=row.importance,
        source_client=row.source_client,
        source_type=getattr(row, "source_type", None) or "unknown",
        source_ref=getattr(row, "source_ref", None),
        metadata=dict(row.metadata_ or {}),
        created_at=row.created_at,
        expires_at=row.expires_at,
        reconfirmed_at=row.reconfirmed_at,
        last_recalled_at=row.last_recalled_at,
        recall_count=row.recall_count,
        context_count=row.context_count,
        reconfirm_count=row.reconfirm_count,
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
    activity: TelemetryRepository,
    authenticate: WebAuthenticator,
    activity_retention_days: int,
    *,
    password_max_chars: int = 256,
    get_search_sunset: str = DEFAULT_GET_SEARCH_SUNSET,
) -> APIRouter:
    identity = Annotated[WebIdentity, Depends(authenticate)]
    router = APIRouter(
        prefix="/me",
        tags=["self-service"],
        dependencies=[Depends(authenticate)],
        route_class=DomainRoute,
        responses=PROTECTED_RESPONSES,
    )
    configured_issue_api_key = password_model(IssueApiKeyRequest, password_max_chars)

    async def _search(
        current: WebIdentity,
        *,
        query: str,
        project: str | None,
        scope: Scope | None,
        category: Category | None,
        limit: int | None,
        max_tokens: int | None = None,
        strategy: str | None = None,
    ) -> RecallResult:
        return await memories.recall(
            current.user.id,
            query=query,
            project=project,
            scope=scope,
            category=category,
            limit=limit,
            max_tokens=max_tokens,
            strategy=strategy,
        )

    @router.get("/memories", response_model=ListResult)
    async def list_memories(
        current: identity,
        scope: Annotated[Scope | None, Query()] = None,
        project: Annotated[str | None, Query()] = None,
        category: Annotated[Category | None, Query()] = None,
        stale: Annotated[bool | None, Query()] = None,
        limit: Annotated[StrictQueryPositiveLimit | None, Query()] = None,
        offset: Annotated[StrictQueryNonNegativeOffset, Query()] = 0,
    ) -> ListResult:
        return await memories.list_memories(
            current.user.id,
            scope=scope,
            project=project,
            category=category,
            stale=stale,
            limit=limit,
            offset=offset,
        )

    @router.get("/memory-graph", response_model=MemoryGraphResponse)
    async def memory_graph(
        current: identity,
        scope: Annotated[Scope | None, Query()] = None,
        project: Annotated[str | None, Query()] = None,
        category: Annotated[Category | None, Query()] = None,
        limit: Annotated[StrictQueryPositiveLimit | None, Query()] = None,
    ) -> MemoryGraphResponse:
        return await memories.memory_graph(
            current.user.id,
            scope=scope,
            project=project,
            category=category,
            limit=limit,
        )

    @router.get("/memory-profile", response_model=ProfileBlock)
    async def memory_profile(
        current: identity,
        project: Annotated[str | None, Query()] = None,
    ) -> ProfileBlock:
        return await memories.get_profile(current.user.id, project=project)

    @router.post("/memories/search", response_model=RecallResult)
    async def search_memories(
        body: SearchMemoriesRequest, current: identity
    ) -> RecallResult:
        return await _search(
            current,
            query=body.query,
            project=body.project,
            scope=body.scope,
            category=body.category,
            limit=body.limit,
            max_tokens=body.max_tokens,
            strategy=body.strategy,
        )

    @router.get(
        "/memories/search",
        response_model=RecallResult,
        deprecated=True,
        summary="Deprecated: use POST /me/memories/search",
        description=(
            "Legacy search endpoint retained for one release. Prefer POST with "
            "the query in the JSON body. Emits Deprecation and Sunset headers. "
            f"Published sunset: {get_search_sunset} "
            "(override with RECALLUM__WEB__GET_SEARCH_SUNSET)."
        ),
        responses={
            **PROTECTED_RESPONSES,
            200: {
                "description": "Search results",
                "headers": {
                    "Deprecation": {
                        "description": "Present when the operation is deprecated",
                        "schema": {"type": "string"},
                    },
                    "Sunset": {
                        "description": (
                            "HTTP-date when this operation will be removed. "
                            f"Default published value: {DEFAULT_GET_SEARCH_SUNSET}."
                        ),
                        "schema": {"type": "string"},
                    },
                },
            },
        },
    )
    async def search_memories_get(
        response: Response,
        current: identity,
        query: Annotated[str, Query(min_length=1)],
        project: Annotated[str | None, Query()] = None,
        scope: Annotated[Scope | None, Query()] = None,
        category: Annotated[Category | None, Query()] = None,
        limit: Annotated[StrictQueryPositiveLimit | None, Query()] = None,
        max_tokens: Annotated[StrictQueryPositiveLimit | None, Query()] = None,
        strategy: Annotated[
            Literal["coding", "debugging", "planning", "review", "architecture"] | None,
            Query(),
        ] = None,
    ) -> RecallResult:
        # Query text must never be logged (URL query is itself a migration risk).
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = get_search_sunset
        return await _search(
            current,
            query=query,
            project=project,
            scope=scope,
            category=category,
            limit=limit,
            max_tokens=max_tokens,
            strategy=strategy,
        )

    @router.post("/memories", response_model=RememberResult, status_code=201)
    async def create_memory(body: CreateMemoryRequest, current: identity) -> RememberResult:
        result = await memories.remember(current.user.id, **body.model_dump(exclude={"scope"}))
        if not result.created:
            raise HTTPException(status_code=409, detail="Memory already exists")
        return result

    @router.post("/memories/reassign-project", response_model=ReassignResult)
    async def reassign_project(
        body: ReassignProjectRequest, current: identity
    ) -> ReassignResult:
        # Registered before the ``{memory_id}`` routes so the literal path can
        # never be captured by the parametrized ones.
        return await memories.reassign_project(
            current.user.id,
            from_project=body.from_project,
            to_project=body.to_project,
        )

    @router.post("/memories/merge", response_model=MergeResult)
    async def merge_memories(body: MergeMemoriesRequest, current: identity) -> MergeResult:
        # Registered before the ``{memory_id}`` routes so the literal path can
        # never be captured by the parametrized ones.
        result = await memories.merge(
            current.user.id,
            source_ids=body.source_ids,
            content=body.content,
            category=body.category,
            importance=body.importance,
            metadata=body.metadata,
            source_client=body.source_client,
        )
        if not result.merged or result.memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
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

    @router.post("/memories/{memory_id}/reconfirm", response_model=ReconfirmResult)
    async def reconfirm_memory(memory_id: uuid.UUID, current: identity) -> ReconfirmResult:
        result = await memories.reconfirm(current.user.id, memory_id)
        if not result.reconfirmed or result.memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return result

    @router.get("/memories/{memory_id}/related", response_model=RelatedMemoriesResult)
    async def related_memories(
        memory_id: uuid.UUID,
        current: identity,
        limit: Annotated[StrictQueryPositiveLimit | None, Query()] = None,
    ) -> RelatedMemoriesResult:
        return await memories.related_memories(current.user.id, memory_id, limit=limit)

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
    async def issue_api_key(
        body: configured_issue_api_key, current: identity
    ) -> IssuedApiKeyResponse:
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

    @router.get("/activity", response_model=ActivityResponse)
    async def own_activity(
        current: identity,
        start: Annotated[datetime | None, Query()] = None,
        end: Annotated[datetime | None, Query()] = None,
    ) -> ActivityResponse:
        resolved_end = end or datetime.now(UTC)
        resolved_start = start or (resolved_end - timedelta(days=min(30, activity_retention_days)))
        if resolved_start.tzinfo is None or resolved_end.tzinfo is None:
            raise HTTPException(status_code=422, detail="activity range must include a timezone")
        if resolved_start >= resolved_end:
            raise HTTPException(status_code=422, detail="activity start must be before end")
        if resolved_end - resolved_start > timedelta(days=activity_retention_days):
            raise HTTPException(
                status_code=422,
                detail=f"activity range cannot exceed {activity_retention_days} days",
            )
        aggregate = await activity.aggregate(current.user.id, resolved_start, resolved_end)
        total = aggregate.total_calls
        return ActivityResponse(
            start=resolved_start,
            end=resolved_end,
            total_calls=total,
            total_results=aggregate.total_results,
            failed_calls=aggregate.failed_calls,
            failure_rate=aggregate.failed_calls / total if total else 0.0,
            degraded_calls=aggregate.degraded_calls,
            degradation_rate=aggregate.degraded_calls / total if total else 0.0,
            by_day=aggregate.by_day,
            by_tool=aggregate.by_tool,
            by_project=aggregate.by_project,
        )

    return router


__all__ = ["create_self_service_router"]
