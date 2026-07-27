"""The shared MemoryRepository contract, run against the real PostgreSQL adapter."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from tests.contract.memory_repository import MemoryRepositoryContract

pytestmark = pytest.mark.integration


class TestPostgresAdapter(MemoryRepositoryContract):
    @pytest.fixture
    def repo(self, container):
        return container.memory_repository()

    @pytest_asyncio.fixture
    async def user_id(self, container) -> uuid.UUID:
        user = await container.api_key_service().create_user(
            f"contract-{uuid.uuid4().hex[:8]}@example.com"
        )
        return user.id

    @pytest_asyncio.fixture
    async def other_user_id(self, container) -> uuid.UUID:
        user = await container.api_key_service().create_user(
            f"contract-other-{uuid.uuid4().hex[:8]}@example.com"
        )
        return user.id
