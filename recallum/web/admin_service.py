"""Count-only system administration workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from recallum.auth.api_keys import ApiKeyService, IssuedKey
from recallum.auth.passwords import PasswordService
from recallum.db.models import User
from recallum.db.readiness import DatabaseReadiness
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.memory_repo import MemoryRepository
from recallum.db.repositories.user_repo import LastAdminError, UserRepository


class AdminNotFoundError(LookupError):
    pass


class AdminPasswordError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class UserView:
    user: User
    active_key_count: int


class AdminService:
    def __init__(
        self,
        users: UserRepository,
        keys: ApiKeyRepository,
        memories: MemoryRepository,
        api_keys: ApiKeyService,
        passwords: PasswordService,
        database: DatabaseReadiness,
        embeddings,
    ) -> None:
        self._users = users
        self._keys = keys
        self._memories = memories
        self._api_keys = api_keys
        self._passwords = passwords
        self._database = database
        self._embeddings = embeddings

    async def list_users(self) -> list[UserView]:
        return [
            UserView(
                user,
                sum(key.revoked_at is None for key in await self._api_keys.list_keys(user.id)),
            )
            for user in await self._users.list_users()
        ]

    async def create_user(self, email: str, is_admin: bool) -> UserView:
        user = await self._api_keys.create_user(email)
        if is_admin:
            await self._users.set_admin(user.id, True)
            user.is_admin = True
        return UserView(user, 0)

    async def set_admin(self, user_id: uuid.UUID, is_admin: bool) -> User:
        user = await self._users.set_admin_preserving_last(user_id, is_admin)
        if user is None:
            raise AdminNotFoundError
        return user

    async def list_keys(self, user_id: uuid.UUID):
        await self._require_user(user_id)
        return await self._api_keys.list_keys(user_id)

    async def issue_key(
        self,
        user_id: uuid.UUID,
        admin: User,
        password: str,
        name: str | None,
    ) -> IssuedKey:
        if admin.password_hash is None or not await self._passwords.verify(
            admin.password_hash, password
        ):
            raise AdminPasswordError
        await self._require_user(user_id)
        return await self._api_keys.issue_key(user_id, name)

    async def revoke_key(self, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
        await self._require_user(user_id)
        if not await self._keys.revoke_for_user(user_id, key_id):
            raise AdminNotFoundError

    async def aggregates(self) -> tuple[int, int, int, dict[uuid.UUID, int]]:
        users = await self._users.list_users()
        active, revoked = await self._keys.count_by_status()
        counts = {user.id: await self._memories.count_active(user.id) for user in users}
        return len(users), active, revoked, counts

    async def status(self) -> tuple[bool, bool, str, bool]:
        database_ok = await self._database.is_ready()
        embeddings_ok = await self._embeddings.is_available()
        model = self._embeddings.model
        mismatch = False
        if database_ok:
            mismatch = any(
                [
                    await self._memories.has_model_mismatch(user.id, model)
                    for user in await self._users.list_users()
                ]
            )
        return database_ok, embeddings_ok, model, mismatch

    async def _require_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AdminNotFoundError
        return user


__all__ = [
    "AdminNotFoundError",
    "AdminPasswordError",
    "AdminService",
    "LastAdminError",
]
