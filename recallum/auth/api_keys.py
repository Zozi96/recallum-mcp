"""API key lifecycle: generation with cryptographic entropy, SHA-256 storage,
single-time display, validation and individual revocation."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email

from recallum.db.models import ApiKey, User
from recallum.db.repositories.api_key_repo import ApiKeyRepository
from recallum.db.repositories.user_repo import UserRepository


@dataclass(slots=True)
class IssuedKey:
    """A freshly issued key. ``plaintext`` is shown once and never persisted."""

    plaintext: str
    key: ApiKey


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a raw bearer token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiKeyService:
    """Issues and revokes keys without ever storing the original secret."""

    def __init__(
        self,
        user_repository: UserRepository,
        api_key_repository: ApiKeyRepository,
        key_prefix: str = "rcl_",
        key_entropy_bytes: int = 32,
    ) -> None:
        self._users = user_repository
        self._keys = api_key_repository
        self._prefix = key_prefix
        self._entropy_bytes = key_entropy_bytes

    async def create_user(self, email: str) -> User:
        try:
            email = validate_email(email, check_deliverability=False).normalized.lower()
        except EmailNotValidError as exc:
            raise ValueError(str(exc)) from exc
        if await self._users.get_by_email(email) is not None:
            raise ValueError(f"user '{email}' already exists")
        return await self._users.create_user(email)

    async def issue_key(self, user_id: uuid.UUID, name: str | None = None) -> IssuedKey:
        """Generate a key, persist only its hash, return the plaintext once."""
        plaintext = self._prefix + secrets.token_urlsafe(self._entropy_bytes)
        key = await self._keys.create_key(user_id, hash_token(plaintext), name)
        return IssuedKey(plaintext=plaintext, key=key)

    async def revoke_key(self, key_id: uuid.UUID) -> bool:
        return await self._keys.revoke(key_id)

    async def list_keys(self, user_id: uuid.UUID):
        return await self._keys.list_for_user(user_id)
