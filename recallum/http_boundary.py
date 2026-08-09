"""Small, testable ASGI seams for public request boundaries."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send


def _peer_ip(peer: str | None) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(peer or "")
    except ValueError:
        return None


def _as_network(value: IPv4Network | IPv6Network | str) -> IPv4Network | IPv6Network:
    return value if not isinstance(value, str) else ip_network(value, strict=False)


def attributed_client_ip(scope: Scope) -> str:
    """Return the TrustedClientResolver attribution, or ``unknown`` if absent."""
    return scope.get("client_ip") or scope.get("recallum.client_ip") or "unknown"


def resolve_client_ip(
    peer: str | None,
    forwarded_for: str | None,
    trusted_cidrs: tuple[IPv4Network | IPv6Network | str, ...] = (),
) -> str | None:
    """Resolve a client address without trusting headers from an untrusted peer."""
    immediate = _peer_ip(peer)
    if immediate is None:
        return peer
    trusted_networks = tuple(_as_network(item) for item in trusted_cidrs)
    if not any(immediate in network for network in trusted_networks) or not forwarded_for:
        return str(immediate)
    raw_addresses = [item.strip() for item in forwarded_for.split(",")]
    if not raw_addresses or any(not item for item in raw_addresses):
        return str(immediate)
    try:
        chain = [ip_address(item) for item in raw_addresses]
    except ValueError:
        return str(immediate)
    for address in reversed(chain):
        if not any(address in network for network in trusted_networks):
            return str(address)
    return str(immediate)


class TrustedClientResolver:
    """ASGI adapter that exposes the resolved address in request scope."""

    def __init__(
        self, app: ASGIApp, trusted_cidrs: tuple[IPv4Network | IPv6Network | str, ...] = ()
    ) -> None:
        self.app = app
        self.trusted_cidrs = trusted_cidrs

    def resolve(self, peer: str | None, forwarded_for: str | None) -> str | None:
        return resolve_client_ip(peer, forwarded_for, self.trusted_cidrs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            values = [
                value.decode("latin-1")
                for name, value in scope.get("headers", [])
                if name.lower() == b"x-forwarded-for"
            ]
            forwarded_for = ",".join(values) or None
            peer = scope.get("client", (None, 0))[0]
            scope = dict(scope)
            client_ip = self.resolve(peer, forwarded_for)
            scope["recallum.client_ip"] = client_ip
            scope["client_ip"] = client_ip
        await self.app(scope, receive, send)


@dataclass(frozen=True, slots=True)
class RateReservation:
    key: str
    generation: int


@dataclass(slots=True)
class _Bucket:
    count: int
    expires_at: float
    generation: int


class RateLimitExceeded(Exception):
    """Raised when a fixed-window bucket has no reservation available."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("rate limit exceeded")


class FixedWindowLimiter:
    """Bounded async-safe fixed-window reservations with an injectable clock."""

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def size(self) -> int:
        return len(self._buckets)

    @property
    def bucket_count(self) -> int:
        return self.size

    async def reserve(self, key: str, limit: int, window_seconds: int) -> RateReservation:
        return (await self.reserve_many(((key, limit, window_seconds),)))[0]

    async def reserve_many(
        self, specifications: Iterable[tuple[str, int, int]]
    ) -> tuple[RateReservation, ...]:
        specs = tuple(specifications)
        if not specs or any(limit <= 0 or window <= 0 for _, limit, window in specs):
            raise ValueError("rate limits and windows must be positive")
        unique_keys = {key for key, _, _ in specs}
        if len(unique_keys) > self.max_entries:
            raise ValueError("reservation exceeds limiter capacity")
        async with self._lock:
            now = self._clock()
            self._evict_expired(now)
            existing = {key for key in unique_keys if key in self._buckets}
            occurrences = Counter(key for key, _, _ in specs)
            retry_after = 0
            for key, limit, window in specs:
                if key in existing:
                    bucket = self._buckets[key]
                    if bucket.count + occurrences[key] > limit:
                        retry_after = max(
                            retry_after,
                            math.ceil(max(0.0, bucket.expires_at - now)),
                        )
                elif occurrences[key] > limit:
                    retry_after = max(retry_after, window)
            if retry_after:
                raise RateLimitExceeded(max(1, retry_after))
            needed = unique_keys - existing
            self._evict_for_capacity(len(needed), protected=unique_keys)
            reservations: list[RateReservation] = []
            for key, limit, window in specs:
                bucket = self._buckets.get(key)
                if bucket is None:
                    self._generation += 1
                    bucket = _Bucket(0, now + window, self._generation)
                    self._buckets[key] = bucket
                if bucket.count >= limit:
                    retry_after = max(retry_after, math.ceil(max(0.0, bucket.expires_at - now)))
                    break
                bucket.count += 1
                reservations.append(RateReservation(key, bucket.generation))
            else:
                return tuple(reservations)
            for reservation in reservations:
                self._release_locked(reservation)
            raise RateLimitExceeded(max(1, retry_after))

    async def release(self, reservation: RateReservation) -> None:
        async with self._lock:
            self._release_locked(reservation)

    def _release_locked(self, reservation: RateReservation) -> None:
        bucket = self._buckets.get(reservation.key)
        if bucket is None or bucket.generation != reservation.generation:
            return
        bucket.count -= 1
        if bucket.count <= 0:
            self._buckets.pop(reservation.key, None)

    def _evict_expired(self, now: float) -> None:
        for key, bucket in tuple(self._buckets.items()):
            if now >= bucket.expires_at:
                self._buckets.pop(key, None)

    def _evict_for_capacity(self, needed: int, *, protected: set[str]) -> None:
        while len(self._buckets) + needed > self.max_entries and self._buckets:
            # Expiry then generation gives deterministic oldest-expiry eviction.
            candidates = [key for key in self._buckets if key not in protected]
            if not candidates:
                raise ValueError("reservation exceeds limiter capacity")
            key = min(
                candidates,
                key=lambda item: (
                    self._buckets[item].expires_at,
                    self._buckets[item].generation,
                    item,
                ),
            )
            self._buckets.pop(key, None)


class RequestBodyLimitMiddleware:
    """Reject oversized bodies before FastAPI parsing or MCP session work."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        general_body_bytes: int,
        login_body_bytes: int,
        password_max_chars: int = 256,
    ) -> None:
        self.app = app
        self.general_body_bytes = general_body_bytes
        self.login_body_bytes = login_body_bytes
        self.password_max_chars = password_max_chars

    def _limit_for(self, path: str) -> int | None:
        if path == "/api/v1/auth/login":
            return self.login_body_bytes
        if path == "/api/v1" or path.startswith("/api/v1/"):
            return self.general_body_bytes
        if path == "/mcp" or path.startswith("/mcp/"):
            return self.general_body_bytes
        return None

    @staticmethod
    def _declared_length(scope: Scope) -> int | None:
        values = [
            value.decode("latin-1")
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if len(values) != 1 or not values[0].isdigit():
            return None
        return int(values[0])

    def _password_exceeds_limit(self, scope: Scope, messages: list[dict]) -> bool:
        path = scope.get("path", "")
        if not (path == "/api/v1" or path.startswith("/api/v1/")):
            return False
        content_type = next(
            (
                value.decode("latin-1").lower()
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-type"
            ),
            "",
        )
        if "application/json" not in content_type:
            return False
        try:
            payload = json.loads(
                b"".join(
                    message.get("body", b"")
                    for message in messages
                    if message.get("type") == "http.request"
                )
            )
        except TypeError, ValueError, UnicodeDecodeError:
            return False
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("password"), str)
            and len(payload["password"]) > self.password_max_chars
        )

    @staticmethod
    async def _reject_oversized(scope: Scope, receive: Receive, send: Send) -> None:
        await PlainTextResponse("Request body too large", status_code=413)(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = self._declared_length(scope)
        if declared is not None and declared > limit:
            await self._reject_oversized(scope, receive, send)
            return

        messages: list[dict] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                total += len(body)
                if total > limit:
                    await self._reject_oversized(scope, receive, send)
                    return
                messages.append(message)
                if not message.get("more_body", False):
                    break
            elif message.get("type") == "http.disconnect":
                messages.append(message)
                break
        if self._password_exceeds_limit(scope, messages):
            await JSONResponse({"detail": "password is too long"}, status_code=422)(
                scope, receive, send
            )
            return
        replay = iter(messages)
        response_complete = asyncio.Event()

        async def replay_receive() -> dict:
            try:
                return next(replay)
            except StopIteration:
                await response_complete.wait()
                return {"type": "http.disconnect"}

        async def tracked_send(message: dict) -> None:
            await send(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                response_complete.set()

        try:
            await self.app(scope, replay_receive, tracked_send)
        finally:
            response_complete.set()


class MCPAuthRateLimitMiddleware:
    """Throttle invalid MCP auth before FastMCP's verifier reaches the DB."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: FixedWindowLimiter,
        attempts: int,
        window_seconds: int,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.attempts = attempts
        self.window_seconds = window_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not (
            scope.get("path") == "/mcp" or scope.get("path", "").startswith("/mcp/")
        ):
            await self.app(scope, receive, send)
            return
        client_ip = attributed_client_ip(scope)
        try:
            reservation = await self.limiter.reserve(
                f"mcp-auth-ip:{client_ip}", self.attempts, self.window_seconds
            )
        except RateLimitExceeded as exc:
            await PlainTextResponse(
                "Too Many Requests",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            )(scope, receive, send)
            return
        status_code: int | None = None

        async def capture(message: dict) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            if status_code != 401:
                await self.limiter.release(reservation)


def _parse_host(value: str) -> tuple[str, int | None] | None:
    if not value or value != value.strip() or any(char in value for char in ",@/;?#"):
        return None
    value = value.lower()
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or value[end + 1 :].count(":") > 1:
            return None
        host = value[1:end]
        suffix = value[end + 1 :]
        if not host or (suffix and not suffix.startswith(":")):
            return None
        try:
            address = ip_address(host)
            if not isinstance(address, IPv6Address):
                return None
            port = int(suffix[1:]) if suffix else None
        except ValueError, TypeError:
            return None
        if port is not None and not 1 <= port <= 65535:
            return None
        return str(address), port
    if value.count(":") > 1:
        return None
    host, separator, raw_port = value.partition(":")
    try:
        ip = ip_address(host)
    except ValueError:
        ip = None
    if ip is None:
        labels = host.split(".")
        if not host or any(
            not label
            or label[0] == "-"
            or label[-1] == "-"
            or not all(char.isalnum() or char == "-" for char in label)
            for label in labels
        ):
            return None
    else:
        host = str(ip)
    if not separator:
        return host, None
    if not raw_port.isdigit():
        return None
    port = int(raw_port)
    return (host, port) if 1 <= port <= 65535 else None


def _origin(value: str) -> str | None:
    if value != value.strip() or any(char in value for char in ",@"):
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError, UnicodeError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    try:
        host = str(ip_address(hostname))
    except ValueError:
        host = hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme.lower()}://{host}{f':{port}' if port else ''}"


class MCPBoundaryMiddleware:
    """Guard MCP Host/Origin and redirect only the exact missing slash."""

    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)
        self.allowed_origins = frozenset(allowed_origins)

    def _host_allowed(self, value: str) -> bool:
        parsed = _parse_host(value)
        if parsed is None:
            return False
        host, _port = parsed
        for item in self.allowed_hosts:
            allowed = _parse_host(item)
            if allowed is None:
                continue
            if parsed == allowed or (allowed[0] == host and allowed[1] is None):
                return True
        return False

    def _origin_allowed(self, value: str | None) -> bool:
        if value is None:
            return True
        parsed_origin = _origin(value)
        return parsed_origin in self.allowed_origins

    @staticmethod
    def _raw_header_values(scope: Scope, name: bytes) -> list[str]:
        """Return every case-insensitive raw ASGI occurrence of one header."""
        return [
            value.decode("latin-1")
            for header_name, value in scope.get("headers", [])
            if header_name.lower() == name
        ]

    @staticmethod
    def _canonical_scope(scope: Scope) -> Scope:
        canonical_headers = []
        for name, value in scope.get("headers", []):
            lowered = name.lower()
            text = value.decode("latin-1")
            if lowered == b"host":
                parsed = _parse_host(text)
                if parsed is not None:
                    host, port = parsed
                    text = f"[{host}]" if ":" in host else host
                    if port is not None:
                        text += f":{port}"
                    value = text.encode("latin-1")
            elif lowered == b"origin":
                origin = _origin(text)
                if origin is not None:
                    value = origin.encode("latin-1")
            canonical_headers.append((name, value))
        canonical = dict(scope)
        canonical["headers"] = canonical_headers
        return canonical

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or (path != "/mcp" and not path.startswith("/mcp/")):
            await self.app(scope, receive, send)
            return
        hosts = self._raw_header_values(scope, b"host")
        if len(hosts) != 1 or not self._host_allowed(hosts[0]):
            await PlainTextResponse("Misdirected Request", status_code=421)(scope, receive, send)
            return
        origins = self._raw_header_values(scope, b"origin")
        if len(origins) > 1 or not self._origin_allowed(origins[0] if origins else None):
            await PlainTextResponse("Forbidden Origin", status_code=403)(scope, receive, send)
            return
        if scope["path"] == "/mcp":
            response: Response = Response(status_code=308, headers={"location": "/mcp/"})
            await response(scope, receive, send)
            return
        await self.app(self._canonical_scope(scope), receive, send)


__all__ = [
    "FixedWindowLimiter",
    "MCPAuthRateLimitMiddleware",
    "MCPBoundaryMiddleware",
    "RateLimitExceeded",
    "RateReservation",
    "RequestBodyLimitMiddleware",
    "TrustedClientResolver",
    "attributed_client_ip",
    "resolve_client_ip",
]
