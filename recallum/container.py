"""Dependency Injector wiring: concrete providers, app-scoped engine, test overrides.

Tests replace providers with ``container.<provider>.override(...)`` to isolate
PostgreSQL and Ollama; production paths resolve the same graph.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from recallum.auth.api_keys import ApiKeyService
from recallum.auth.middleware import TokenAuthenticator
from recallum.config import Settings
from recallum.db.readiness import DatabaseReadiness
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.memory_repo import MemoryRepository
from recallum.db.repositories.user_repo import UserRepository
from recallum.db.session import SessionProvider
from recallum.embeddings.ollama import OllamaEmbeddingClient
from recallum.memory.service import MemoryService


class Container(containers.DeclarativeContainer):
    """Application graph. The engine is app-scoped; sessions are per operation."""

    config = providers.Configuration()

    http_client = providers.Singleton(httpx.AsyncClient)

    engine = providers.Singleton(
        create_async_engine,
        url=config.database.url,
        echo=config.database.echo.as_bool(),
        pool_size=config.database.pool_size.as_int(),
        max_overflow=config.database.max_overflow.as_int(),
    )

    session_factory = providers.Singleton(
        async_sessionmaker,
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    sessions = providers.Singleton(SessionProvider, session_factory=session_factory)

    embedding_client = providers.Singleton(
        OllamaEmbeddingClient,
        base_url=config.ollama.url,
        model=config.ollama.model,
        http_client=http_client,
        timeout_seconds=config.ollama.timeout_seconds.as_float(),
        dimensions=config.ollama.dimensions.as_int(),
    )

    user_repository = providers.Singleton(UserRepository, sessions=sessions)
    api_key_repository = providers.Singleton(ApiKeyRepository, sessions=sessions)
    memory_repository = providers.Singleton(MemoryRepository, sessions=sessions)
    database_readiness = providers.Singleton(DatabaseReadiness, engine=engine)

    api_key_service = providers.Singleton(
        ApiKeyService,
        user_repository=user_repository,
        api_key_repository=api_key_repository,
        key_prefix=config.auth.key_prefix,
        key_entropy_bytes=config.auth.key_entropy_bytes.as_int(),
    )

    authenticator = providers.Singleton(
        TokenAuthenticator,
        api_key_repository=api_key_repository,
        # Singleton on purpose: the identity cache lives on the instance, so a
        # per-call authenticator would cache nothing.
        cache_ttl=providers.Callable(
            timedelta, seconds=config.auth.identity_cache_seconds.as_float()
        ),
    )

    memory_service = providers.Singleton(
        MemoryService,
        repository=memory_repository,
        embeddings=embedding_client,
        limits=config.limits,
    )

def create_container(settings: Settings) -> Container:
    """Build a container from validated settings (secrets revealed once here)."""
    container = Container()
    container.config.from_dict(settings.for_container())
    return container


async def shutdown_container(container: Container) -> None:
    """Release app-scoped resources.

    Providers are lazy: if the engine/HTTP client were never used, resolving
    them here creates and immediately closes them, which is cheap.
    """
    engine = container.engine()
    dispose = getattr(engine, "dispose", None)
    if dispose is not None:
        await dispose()
    client = container.http_client()
    aclose = getattr(client, "aclose", None)
    if aclose is not None:
        await aclose()
