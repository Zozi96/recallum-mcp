"""Dependency Injector wiring: concrete providers, app-scoped engine, test overrides.

Tests replace providers with ``container.<provider>.override(...)`` to isolate
PostgreSQL and Ollama; production paths resolve the same graph.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from recallum.auth.api_keys import ApiKeyService
from recallum.auth.middleware import TokenAuthenticator
from recallum.auth.passwords import PasswordService
from recallum.auth.web_sessions import WebSessionService
from recallum.config import Settings
from recallum.db.readiness import DatabaseReadiness
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.memory_repo import MemoryRepository
from recallum.db.repositories.skill_repo import SkillRepository
from recallum.db.repositories.user_repo import UserRepository
from recallum.db.repositories.web_session_repo import WebSessionRepository
from recallum.db.session import SessionProvider
from recallum.embeddings.ollama import OllamaEmbeddingClient
from recallum.memory.profile_rebuild import ProfileRebuildQueue
from recallum.memory.service import MemoryService
from recallum.skills.service import SkillService
from recallum.telemetry.buffer import TelemetryBuffer
from recallum.telemetry.repository import TelemetryRepository
from recallum.web.admin_service import AdminService


def _database_connect_args(
    connect_timeout_seconds: float,
    command_timeout_seconds: float,
    statement_timeout_seconds: float,
) -> dict[str, object]:
    """Build asyncpg connection options from validated settings."""
    return {
        "timeout": connect_timeout_seconds,
        "command_timeout": command_timeout_seconds,
        "server_settings": {
            "statement_timeout": str(max(1, round(statement_timeout_seconds * 1000))),
        },
    }


class _LazyProvider:
    """Resolve a provider only when one of its methods is actually used."""

    def __init__(self, provider) -> None:
        self._provider = provider

    def __call__(self, *args, **kwargs):
        return self._provider()(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._provider(), name)


class Container(containers.DeclarativeContainer):
    """Application graph. The engine is app-scoped; sessions are per operation."""

    config = providers.Configuration()

    # Resource providers expose initialization state, allowing lifecycle
    # cleanup to avoid creating clients merely to close them.
    http_client = providers.Resource(httpx.AsyncClient)

    engine = providers.Resource(
        create_async_engine,
        url=config.database.url,
        echo=config.database.echo.as_bool(),
        pool_size=config.database.pool_size.as_int(),
        max_overflow=config.database.max_overflow.as_int(),
        pool_timeout=config.readiness.database_pool_timeout_seconds.as_float(),
        connect_args=providers.Callable(
            _database_connect_args,
            connect_timeout_seconds=config.readiness.database_connect_timeout_seconds.as_float(),
            command_timeout_seconds=config.readiness.database_command_timeout_seconds.as_float(),
            statement_timeout_seconds=config.readiness.database_statement_timeout_seconds.as_float(),
        ),
    )

    session_factory = providers.Singleton(
        async_sessionmaker,
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    sessions = providers.Singleton(
        SessionProvider,
        session_factory=providers.Factory(_LazyProvider, provider=session_factory.provider),
    )

    embedding_client = providers.Singleton(
        OllamaEmbeddingClient,
        base_url=config.ollama.url,
        model=config.ollama.model,
        http_client=providers.Factory(_LazyProvider, provider=http_client.provider),
        timeout_seconds=config.ollama.timeout_seconds.as_float(),
        dimensions=config.ollama.dimensions.as_int(),
    )

    user_repository = providers.Singleton(
        UserRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    api_key_repository = providers.Singleton(
        ApiKeyRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    web_session_repository = providers.Singleton(
        WebSessionRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    memory_repository = providers.Singleton(
        MemoryRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    skill_repository = providers.Singleton(
        SkillRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    telemetry_repository = providers.Singleton(
        TelemetryRepository, sessions=providers.Factory(_LazyProvider, provider=sessions.provider)
    )
    database_readiness = providers.Singleton(
        DatabaseReadiness,
        engine=providers.Factory(_LazyProvider, provider=engine.provider),
        timeout_seconds=config.readiness.per_dependency_timeout_seconds.as_float(),
    )

    api_key_service = providers.Singleton(
        ApiKeyService,
        user_repository=user_repository,
        api_key_repository=api_key_repository,
        key_prefix=config.auth.key_prefix,
        key_entropy_bytes=config.auth.key_entropy_bytes.as_int(),
    )

    authenticator = providers.Singleton(
        TokenAuthenticator,
        # FastMCP construction must not open the database before startup
        # validators run; authentication resolves the repository on demand.
        api_key_repository=providers.Factory(_LazyProvider, provider=api_key_repository.provider),
        # Singleton on purpose: the identity cache lives on the instance, so a
        # per-call authenticator would cache nothing.
        cache_ttl=providers.Callable(
            timedelta, seconds=config.auth.identity_cache_seconds.as_float()
        ),
    )
    password_service = providers.Singleton(
        PasswordService,
        users=user_repository,
        memory_cost=config.web.argon2_memory_cost.as_int(),
        time_cost=config.web.argon2_time_cost.as_int(),
        parallelism=config.web.argon2_parallelism.as_int(),
        hash_len=config.web.argon2_hash_len.as_int(),
        salt_len=config.web.argon2_salt_len.as_int(),
        max_password_chars=config.boundary.request.password_max_chars.as_int(),
    )
    web_session_service = providers.Singleton(
        WebSessionService,
        repository=web_session_repository,
        idle_window=providers.Callable(timedelta, seconds=config.web.idle_seconds.as_int()),
        absolute_window=providers.Callable(timedelta, seconds=config.web.absolute_seconds.as_int()),
        rotation_threshold=config.web.rotation_threshold.as_float(),
        rotation_grace=providers.Callable(
            timedelta, seconds=config.web.rotation_grace_seconds.as_int()
        ),
    )
    admin_service = providers.Singleton(
        AdminService,
        users=user_repository,
        keys=api_key_repository,
        memories=memory_repository,
        api_keys=api_key_service,
        passwords=password_service,
        database=database_readiness,
        embeddings=embedding_client,
    )

    profile_rebuild_queue = providers.Singleton(
        ProfileRebuildQueue,
        batch_size=16,
        buffer_limit=1024,
    )
    memory_service = providers.Singleton(
        MemoryService,
        repository=memory_repository,
        embeddings=embedding_client,
        limits=config.limits,
        profile_rebuild_queue=profile_rebuild_queue,
    )
    skill_service = providers.Singleton(
        SkillService,
        repository=skill_repository,
        embeddings=embedding_client,
        limits=config.limits,
    )
    telemetry_buffer = providers.Singleton(
        TelemetryBuffer,
        repository=telemetry_repository,
        batch_size=config.telemetry.batch_size.as_int(),
        flush_interval_seconds=config.telemetry.flush_interval_seconds.as_float(),
        buffer_limit=config.telemetry.buffer_limit.as_int(),
        retention_days=config.telemetry.retention_days.as_int(),
    )


def create_container(settings: Settings) -> Container:
    """Build a container from validated settings (secrets revealed once here)."""
    container = Container()
    container.config.from_dict(settings.for_container())
    # AsyncClient construction is sync; DI enables async mode from
    # __aenter__/__aexit__, which makes provider() return a Future/Task and
    # breaks _LazyProvider attribute access (e.g. ``.post``).
    container.http_client.disable_async_mode()
    return container


async def init_container_resources(container: Container) -> None:
    """Initialize Resource providers (engine, HTTP client) before first use."""
    resources = container.init_resources()
    if resources is not None:
        await resources


async def shutdown_container(container: Container) -> None:
    """Release app-scoped resources.

    Cleanup is retryable after cancellation/failure and only touches resources
    that dependency-injector reports as initialized (or explicit overrides).
    """
    state = getattr(container, "_recallum_shutdown_state", None)
    if state is None:
        state = {
            "http": False,
            "engine": False,
            "http_resource": None,
            "engine_resource": None,
            "lock": asyncio.Lock(),
            "lock_owner": None,
        }
        container._recallum_shutdown_state = state
    else:
        state.setdefault("lock_owner", None)

    async def close_one(name: str, provider, method_name: str) -> BaseException | None:
        if state[name]:
            return None
        # Resolve/getattr failures must stay inside this boundary so later
        # resources (e.g. engine after a failing HTTP override) still run.
        try:
            resource = state[f"{name}_resource"]
            if resource is None:
                initialized = getattr(provider, "initialized", False)
                overridden = provider.last_overriding is not None
                if not initialized and not overridden:
                    return None
                # Only cache after a successful acquire; a raising Factory
                # override must not skip remaining cleanup or look acquired.
                resource = provider()
                state[f"{name}_resource"] = resource
            close = getattr(resource, method_name, None)
            if close is None:
                state[name] = True
                return None
            await close()
        except BaseException as exc:
            return exc
        state[name] = True
        return None

    current = asyncio.current_task()
    if state["lock_owner"] is current:
        return
    async with state["lock"]:
        state["lock_owner"] = current
        try:
            errors: list[BaseException] = []
            cancellation: asyncio.CancelledError | None = None
            # HTTP must drain before the engine it may still use. Always
            # attempt the engine even when HTTP fails or is cancelled.
            for name, provider, method in (
                ("http", container.http_client, "aclose"),
                ("engine", container.engine, "dispose"),
            ):
                error = await close_one(name, provider, method)
                if error is None:
                    continue
                if isinstance(error, asyncio.CancelledError):
                    cancellation = cancellation or error
                else:
                    errors.append(error)
            if cancellation is not None:
                raise cancellation
            if len(errors) == 1:
                raise errors[0]
            if errors:
                if all(isinstance(error, Exception) for error in errors):
                    raise ExceptionGroup("container cleanup failed", errors)
                raise BaseExceptionGroup("container cleanup failed", errors)
        finally:
            state["lock_owner"] = None
