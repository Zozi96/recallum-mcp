"""Focused checks for password and browser-session authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from recallum.app import create_app
from recallum.auth.api_keys import hash_token
from recallum.auth.passwords import PasswordService
from recallum.auth.web_sessions import WebSessionService
from recallum.config import Settings
from tests.fakes import FakeUserRepository, FakeWebSessionRepository, build_test_container


async def test_passwords_are_argon2id_and_unknown_users_do_equivalent_work(monkeypatch):
    users = FakeUserRepository()
    user = await users.create_user("alice@example.com")
    service = PasswordService(users)
    encoded = await service.hash("correct horse")
    assert encoded.startswith("$argon2id$")
    await users.set_password(user.id, encoded)
    assert await service.authenticate(user.email, "correct horse") == user
    assert await service.authenticate(user.email, "wrong") is None

    calls = 0
    original = service.hash

    async def counted(password):
        nonlocal calls
        calls += 1
        return await original(password)

    monkeypatch.setattr(service, "hash", counted)
    assert await service.authenticate("unknown@example.com", "wrong") is None
    assert calls == 1


async def test_session_expiry_rotation_reuse_and_logout():
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    users = FakeUserRepository()
    user = await users.create_user("alice@example.com")
    repository = FakeWebSessionRepository(users)
    service = WebSessionService(
        repository,
        idle_window=timedelta(days=7),
        absolute_window=timedelta(days=30),
        rotation_threshold=0.5,
        clock=lambda: now[0],
    )
    issued = await service.create(user.id)
    assert issued.session.token_hash == hash_token(issued.token)
    assert issued.token not in issued.session.token_hash

    now[0] += timedelta(days=3)
    assert (await service.resolve(issued.token)).rotated_token is None
    assert len(repository.sessions) == 1
    now[0] += timedelta(days=1)
    rotated = await service.resolve(issued.token)
    assert rotated.rotated_token is not None
    assert rotated.session.absolute_expires_at == issued.session.absolute_expires_at

    assert await service.resolve(issued.token) is None
    assert await service.resolve(rotated.rotated_token) is None

    fresh = await service.create(user.id)
    await service.revoke(fresh.session.id)
    assert await service.resolve(fresh.token) is None

    idle = await service.create(user.id)
    now[0] += timedelta(days=7)
    assert await service.resolve(idle.token) is None

    absolute = await service.create(user.id)
    absolute.session.absolute_expires_at = now[0] + timedelta(hours=1)
    now[0] += timedelta(hours=1)
    assert await service.resolve(absolute.token) is None


async def test_losing_rotation_race_revokes_the_winning_successor():
    class RacingRepository(FakeWebSessionRepository):
        async def rotate(
            self,
            previous_id,
            user_id,
            token_hash,
            now,
            idle_expires_at,
            absolute_expires_at,
        ):
            previous = self.sessions[previous_id]
            successor = await self.create(
                user_id, token_hash, now, idle_expires_at, absolute_expires_at
            )
            previous.rotated_to_id = successor.id
            return None

    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    users = FakeUserRepository()
    user = await users.create_user("race@example.com")
    repository = RacingRepository(users)
    service = WebSessionService(
        repository,
        idle_window=timedelta(days=7),
        absolute_window=timedelta(days=30),
        rotation_threshold=0.5,
        clock=lambda: now[0],
    )
    issued = await service.create(user.id)
    now[0] += timedelta(days=4)

    assert await service.resolve(issued.token) is None
    assert all(row.revoked_at == now[0] for row in repository.sessions.values())


def test_web_endpoints_cookie_scope_and_cors():
    container, fakes = build_test_container()
    user = __import__("asyncio").run(container.api_key_service().create_user("web@example.com"))
    __import__("asyncio").run(container.password_service().set_password(user, "secret"))
    app = create_app(Settings(), container)

    with TestClient(app, base_url="https://recallum.zozbit.com") as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "web@example.com", "password": "secret"},
        )
        assert login.status_code == 200
        cookie = login.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/api/v1" in cookie
        assert "Domain=" not in cookie
        assert client.get("/api/v1/auth/me").json()["email"] == "web@example.com"
        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": "web@example.com", "password": "wrong"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "password": "wrong"},
        )
        assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "web@example.com", "password": ""},
        ).status_code == 422
        assert client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "https://evil.zozbit.com"},
        ).status_code == 403
        assert client.get("/api/v1/auth/me").status_code == 200
        assert "cookie" not in client.build_request("GET", "/mcp").headers
        assert "cookie" not in client.build_request(
            "GET", "https://other.zozbit.com/api/v1/auth/me"
        ).headers

        preflight = client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://memory.zozbit.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == "https://memory.zozbit.com"
        assert preflight.headers["access-control-allow-credentials"] == "true"
        rejected = client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in rejected.headers
        mcp = client.options(
            "/mcp",
            headers={
                "Origin": "https://memory.zozbit.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in mcp.headers

        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


def test_api_key_does_not_authenticate_web_api():
    container, _ = build_test_container()
    app = create_app(Settings(), container)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer rcl_not_web_auth"}
        )
        assert response.status_code == 401
