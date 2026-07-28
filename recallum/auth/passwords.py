"""Argon2id password derivation and credential verification."""

from __future__ import annotations

import asyncio

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from recallum.db.models import User
from recallum.db.repositories.user_repo import UserRepository


class PasswordService:
    def __init__(
        self,
        users: UserRepository,
        *,
        memory_cost: int = 19456,
        time_cost: int = 2,
        parallelism: int = 1,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._users = users
        self._hasher = PasswordHasher(
            memory_cost=memory_cost,
            time_cost=time_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=Type.ID,
        )

    async def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, encoded: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(self._hasher.verify, encoded, password)
        except (InvalidHashError, VerifyMismatchError):
            return False

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self._users.get_by_email(email.lower())
        if user is None or user.password_hash is None:
            # One Argon2 operation for every failed attempt, including unknown users.
            await self.hash(password)
            return None
        return user if await self.verify(user.password_hash, password) else None

    async def set_password(self, user: User, password: str) -> None:
        await self._users.set_password(user.id, await self.hash(password))
