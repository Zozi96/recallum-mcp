"""ASGI factory loaded by an external Granian process for vertical tests."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from dependency_injector import providers
from fastapi import APIRouter

from recallum.app import create_app as build_recallum_app
from recallum.config import Settings, get_settings
from tests.fakes import (
    FakeDatabaseReadiness,
    FakeEmbeddingClient,
    build_test_container,
)

_STATE_ENV = "RECALLUM_VERTICAL_STATE"


def create_app():  # noqa: A001 — Granian --factory entrypoint
    get_settings.cache_clear()
    state_path = Path(os.environ[_STATE_ENV])
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    cache_seconds = float(raw.get("identity_cache_seconds", 0.0))
    settings = Settings(auth={"identity_cache_seconds": cache_seconds})
    container, _ = build_test_container(
        settings=settings,
        embedder=FakeEmbeddingClient(dimensions=16),
    )
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))

    async def _seed() -> dict[str, str]:
        keys = container.api_key_service()
        alice = await keys.create_user("vertical-alice@example.com")
        bob = await keys.create_user("vertical-bob@example.com")
        alice_token = (await keys.issue_key(alice.id)).plaintext
        bob_token = (await keys.issue_key(bob.id)).plaintext
        revoke_me = await keys.issue_key(alice.id)
        return {
            "alice_token": alice_token,
            "bob_token": bob_token,
            "revoke_token": revoke_me.plaintext,
            "revoke_key_id": str(revoke_me.key.id),
        }

    tokens = asyncio.run(_seed())
    raw.update(tokens)
    raw["ready"] = True
    state_path.write_text(json.dumps(raw), encoding="utf-8")

    app = build_recallum_app(settings, container)
    router = APIRouter()

    @router.post("/__vertical__/revoke/{key_id}")
    async def revoke(key_id: str) -> dict[str, bool]:
        ok = await container.api_key_service().revoke_key(uuid.UUID(key_id))
        return {"revoked": bool(ok)}

    @router.post("/__vertical__/arm-sentinel")
    async def arm_sentinel() -> dict[str, bool]:
        class Boom:
            async def list_memories(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def remember(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def recall(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def context(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def forget(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def get_profile(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def get_memory(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def update(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def merge_memories(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

            async def remember_batch(self, *_a, **_k):
                raise RuntimeError("VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK")

        container.memory_service.override(providers.Object(Boom()))
        return {"armed": True}

    app.include_router(router)
    return app
