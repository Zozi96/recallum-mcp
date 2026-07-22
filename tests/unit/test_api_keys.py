"""API key lifecycle unit tests (task 4.1)."""

from __future__ import annotations

import pytest

from recallum.auth.api_keys import ApiKeyService, hash_token
from recallum.auth.middleware import TokenAuthenticator
from tests.fakes import FakeApiKeyRepository, FakeUserRepository


def make_service() -> tuple[ApiKeyService, TokenAuthenticator, FakeApiKeyRepository]:
    users = FakeUserRepository()
    keys = FakeApiKeyRepository(users)
    service = ApiKeyService(user_repository=users, api_key_repository=keys)
    return service, TokenAuthenticator(api_key_repository=keys), keys


def test_hash_token_is_sha256_hex():
    digest = hash_token("rcl_secret")
    assert len(digest) == 64
    assert digest == hash_token("rcl_secret")
    assert digest != hash_token("rcl_other")


async def test_issue_key_never_stores_plaintext():
    service, _, keys = make_service()
    user = await service.create_user("alice@example.com")
    issued = await service.issue_key(user.id, name="laptop")

    assert issued.plaintext.startswith("rcl_")
    assert issued.key.key_hash == hash_token(issued.plaintext)
    stored = keys.keys[issued.key.id]
    assert issued.plaintext not in (stored.key_hash, stored.name)
    assert stored.name == "laptop"


async def test_create_user_normalizes_and_rejects_case_insensitive_duplicates():
    service, _, _ = make_service()
    user = await service.create_user("Bob@Example.COM")
    assert user.email == "bob@example.com"
    with pytest.raises(ValueError):
        await service.create_user("BOB@example.com")


async def test_create_user_rejects_invalid_email():
    service, _, _ = make_service()
    with pytest.raises(ValueError):
        await service.create_user("not-an-email")


async def test_authenticate_valid_invalid_revoked():
    service, authenticator, _ = make_service()
    user = await service.create_user("carol@example.com")
    issued = await service.issue_key(user.id)

    identity = await authenticator.authenticate(issued.plaintext)
    assert identity is not None
    assert identity.user_id == user.id
    assert identity.email == "carol@example.com"
    assert identity.api_key_id == issued.key.id

    assert await authenticator.authenticate("rcl_wrong") is None
    assert await authenticator.authenticate("") is None

    assert await service.revoke_key(issued.key.id) is True
    assert await authenticator.authenticate(issued.plaintext) is None
    assert await service.revoke_key(issued.key.id) is False


async def test_multiple_keys_per_user_independent():
    service, authenticator, _ = make_service()
    user = await service.create_user("dave@example.com")
    first = await service.issue_key(user.id)
    second = await service.issue_key(user.id)

    assert await authenticator.authenticate(second.plaintext) is not None
    await service.revoke_key(first.key.id)
    assert await authenticator.authenticate(first.plaintext) is None
    assert await authenticator.authenticate(second.plaintext) is not None
