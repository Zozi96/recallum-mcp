"""The shared MemoryRepository contract, run against the in-memory fake."""

from __future__ import annotations

import uuid

import pytest

from tests.contract.memory_repository import MemoryRepositoryContract
from tests.fakes import FakeMemoryRepository


class TestInMemoryAdapter(MemoryRepositoryContract):
    @pytest.fixture
    def repo(self) -> FakeMemoryRepository:
        return FakeMemoryRepository()

    @pytest.fixture
    def user_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture
    def other_user_id(self) -> uuid.UUID:
        return uuid.uuid4()
