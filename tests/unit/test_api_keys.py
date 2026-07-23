"""API key lifecycle unit tests (task 4.1)."""

from __future__ import annotations

import argparse

import pytest

from recallum.auth.api_keys import ApiKeyService, UserNotFoundError, hash_token
from recallum.auth.middleware import TokenAuthenticator
from recallum.cli import _run
from tests.fakes import FakeApiKeyRepository, FakeUserRepository, build_test_container


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


async def test_email_administration_flows_resolve_users_and_missing_policy():
    service, _, _ = make_service()
    user = await service.create_user("Admin@Example.COM")

    issued = await service.issue_key_for_email("ADMIN@example.com", "deploy")
    assert issued.user == user
    assert issued.key.user_id == user.id

    listing = await service.list_keys_for_email("admin@example.com")
    assert listing.user == user
    assert [key.id for key in listing.keys] == [issued.key.id]

    with pytest.raises(UserNotFoundError, match="user 'missing@example.com' does not exist"):
        await service.issue_key_for_email("missing@example.com")
    with pytest.raises(UserNotFoundError):
        await service.list_keys_for_email("missing@example.com")


async def test_email_administration_uses_canonical_unicode_normalization():
    service, _, _ = make_service()
    user = await service.create_user("U\u0308SER@例え.テスト")

    issued = await service.issue_key_for_email("ÜSER@例え.テスト")
    listing = await service.list_keys_for_email("üser@例え.テスト")

    assert user.email == "üser@例え.テスト"
    assert issued.user == user
    assert listing.user == user
    assert [key.id for key in listing.keys] == [issued.key.id]


async def test_invalid_email_lookup_preserves_original_input_in_domain_error():
    service, _, _ = make_service()
    invalid = "Not An Email"

    with pytest.raises(UserNotFoundError) as issue_error:
        await service.issue_key_for_email(invalid)
    with pytest.raises(UserNotFoundError) as list_error:
        await service.list_keys_for_email(invalid)

    assert issue_error.value.email == invalid
    assert list_error.value.email == invalid
    assert str(issue_error.value) == f"user '{invalid}' does not exist"


async def test_cli_email_workflows_preserve_output_and_codes(capsys):
    container, _ = build_test_container()
    assert await _run(
        argparse.Namespace(command="create-user", email="cli@example.com"), container
    ) == 0
    created = capsys.readouterr()
    assert created.out.startswith("user created: ")
    assert created.out.endswith(" (cli@example.com)\n")

    assert await _run(
        argparse.Namespace(
            command="issue-key", email="CLI@example.com", name="laptop"
        ),
        container,
    ) == 0
    issued = capsys.readouterr()
    assert "user:      cli@example.com\n" in issued.out
    assert "api key:   rcl_" in issued.out
    assert "warning:   this secret is shown only once; store it now.\n" in issued.out

    assert await _run(
        argparse.Namespace(command="list-keys", email="cli@example.com"), container
    ) == 0
    listed = capsys.readouterr()
    assert " (laptop)  active  created=" in listed.out

    assert await _run(
        argparse.Namespace(command="list-keys", email="missing@example.com"), container
    ) == 1
    missing = capsys.readouterr()
    assert missing.out == ""
    assert missing.err == "error: user 'missing@example.com' does not exist\n"

    assert await _run(
        argparse.Namespace(command="list-keys", email="Not An Email"), container
    ) == 1
    invalid = capsys.readouterr()
    assert invalid.out == ""
    assert invalid.err == "error: user 'Not An Email' does not exist\n"
