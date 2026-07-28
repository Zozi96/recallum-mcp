"""PostgreSQL checks for separation and RLS around web identity."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_api_keys_and_web_sessions_are_independent(container):
    user = await container.api_key_service().create_user("separate@example.com")
    key = await container.api_key_service().issue_key(user.id)
    session = await container.web_session_service().create(user.id)

    assert await container.authenticator().authenticate(session.token) is None
    assert await container.web_session_service().resolve(key.plaintext) is None

    await container.api_key_service().revoke_key(key.key.id)
    assert await container.web_session_service().resolve(session.token) is not None

    await container.web_session_service().revoke(session.session.id)
    second_key = await container.api_key_service().issue_key(user.id)
    assert await container.authenticator().authenticate(second_key.plaintext) is not None


async def test_admin_status_does_not_bypass_memory_rls(container):
    admin = await container.api_key_service().create_user("admin@example.com")
    owner = await container.api_key_service().create_user("owner@example.com")
    await container.user_repository().set_admin(admin.id, True)
    memory = await container.memory_service().remember(
        owner.id, content="owner only", category="fact"
    )

    assert await container.memory_repository().get_active(admin.id, memory.memory.id) is None
