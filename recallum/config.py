"""Validated application settings, loaded from environment variables.

Environment variables use the ``RECALLUM__<GROUP>__<FIELD>`` convention,
e.g. ``RECALLUM__DATABASE__URL`` or ``RECALLUM__OLLAMA__MODEL``.
"""

from __future__ import annotations

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Address, ip_address
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, IPvAnyNetwork, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from recallum.memory.limits import MemoryLimits

EMBEDDING_DIMENSIONS = 768

# PostgreSQL text-search configuration used for BOTH the stored ``content_tsv``
# generated column and the query built in the memory repository. The two must
# agree: a mismatch silently stops text retrieval from matching anything, so
# ``tests/integration/test_db.py`` asserts the live column expression uses this
# value. Changing it requires a migration that rebuilds the column and its GIN
# index (see ``0003_text_search_provenance``).
#
# ``english`` (rather than ``simple``) buys stemming and stopword removal. It
# is not accent-insensitive: that would need the ``unaccent`` extension, which
# a non-superuser migration role cannot create on every deployment.
TEXT_SEARCH_CONFIG = "english"


class DatabaseSettings(BaseModel):
    """PostgreSQL connection settings."""

    url: SecretStr = SecretStr(
        "postgresql+asyncpg://recallum:recallum@localhost:5432/recallum"
    )
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=50)


class ReadinessSettings(BaseModel):
    """Deadlines shared by dependency probes and database operations."""

    per_dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=60.0)
    aggregate_timeout_seconds: float = Field(default=3.0, gt=0, le=120.0)
    database_pool_timeout_seconds: float = Field(default=1.0, gt=0, le=60.0)
    database_connect_timeout_seconds: float = Field(default=1.0, gt=0, le=60.0)
    database_command_timeout_seconds: float = Field(default=1.0, gt=0, le=60.0)
    database_statement_timeout_seconds: float = Field(default=1.0, gt=0, le=60.0)

    @model_validator(mode="after")
    def validate_budgets(self) -> ReadinessSettings:
        if self.aggregate_timeout_seconds < self.per_dependency_timeout_seconds:
            raise ValueError(
                "aggregate_timeout_seconds must be greater than or equal to "
                "per_dependency_timeout_seconds"
            )
        database_budgets = (
            self.database_pool_timeout_seconds,
            self.database_connect_timeout_seconds,
            self.database_command_timeout_seconds,
            self.database_statement_timeout_seconds,
        )
        if any(timeout > self.per_dependency_timeout_seconds for timeout in database_budgets):
            raise ValueError("database timeouts must fit within the per-dependency timeout")
        return self


class OllamaSettings(BaseModel):
    """Local Ollama embedding service settings."""

    url: str = "http://localhost:11434"
    model: str = "embeddinggemma:300m-qat-q4_0"
    timeout_seconds: float = Field(default=30.0, gt=0)
    dimensions: int = Field(default=EMBEDDING_DIMENSIONS, gt=0)


class AuthSettings(BaseModel):
    """API key authentication settings."""

    key_prefix: str = "rcl_"
    key_entropy_bytes: int = Field(default=32, ge=16, le=64)
    # Seconds a successful authentication is reused before PostgreSQL is asked
    # again, saving a round trip on every tool call. This is also exactly the
    # worst-case delay before a revoked key stops working, so it is capped at
    # five minutes. The default (5s) removes one authentication query per MCP
    # tool call burst while keeping the revocation window small; set it to 0 to
    # restore immediate revocation at the cost of a database hit on every call.
    identity_cache_seconds: float = Field(default=5.0, ge=0.0, le=300.0)


class TelemetrySettings(BaseModel):
    """Bounded, deferred tool-activity collection settings."""

    batch_size: int = Field(default=100, ge=1, le=10_000)
    flush_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    buffer_limit: int = Field(default=1_000, ge=1, le=100_000)
    retention_days: int = Field(default=90, ge=1, le=366)
    # Empty: GET /metrics is TCP-loopback only. Compose sets a token so
    # docker-bridge and private-network scrapes can authenticate.
    metrics_token: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_buffer_capacity(self) -> TelemetrySettings:
        if self.buffer_limit < self.batch_size:
            raise ValueError("buffer_limit must be greater than or equal to batch_size")
        return self


class WebSettings(BaseModel):
    """Browser-session and password settings."""

    allowed_origin: str = "https://memory.zozbit.com"
    cookie_name: str = Field(default="recallum_session", min_length=1, max_length=64)
    # HTTP-date for the one-release GET /me/memories/search Sunset header.
    # Release notes publish the concrete retirement date (task 10.3).
    get_search_sunset: str = Field(
        default="Tue, 01 Dec 2026 00:00:00 GMT",
        min_length=16,
        max_length=64,
    )
    idle_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0, le=31 * 24 * 60 * 60)
    absolute_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0, le=366 * 24 * 60 * 60)
    rotation_threshold: float = Field(default=0.5, gt=0, lt=1)
    # How long the just-superseded token keeps working after a rotation. A page
    # load fires several requests at once, all carrying the same cookie: one
    # rotates and the rest land holding a token that went stale in flight. That
    # is concurrency, not replay, so it must not trip reuse detection.
    rotation_grace_seconds: int = Field(default=30, ge=0, le=300)
    argon2_memory_cost: int = Field(default=19456, ge=8192, le=1048576)
    argon2_time_cost: int = Field(default=2, ge=1, le=10)
    argon2_parallelism: int = Field(default=1, ge=1, le=16)
    argon2_hash_len: int = Field(default=32, ge=16, le=64)
    argon2_salt_len: int = Field(default=16, ge=16, le=64)

    @model_validator(mode="after")
    def validate_web_policy(self) -> WebSettings:
        origin = urlsplit(self.allowed_origin)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
        ):
            raise ValueError("allowed_origin must be an exact HTTP origin")
        if self.absolute_seconds <= self.idle_seconds:
            raise ValueError("absolute_seconds must exceed idle_seconds")
        return self


class RuntimeSettings(BaseModel):
    """Process topology for Granian while MCP session state stays in-memory."""

    model_config = ConfigDict(frozen=True)

    workers: int = Field(default=1, ge=1, le=64)
    # Reserved only: must not unlock workers>1 until FastMCP is actually wired
    # for validated stateless HTTP (or sticky/shared session state).
    mcp_stateless_http: bool = False

    @model_validator(mode="after")
    def stateful_mcp_requires_one_worker(self) -> RuntimeSettings:
        if self.workers != 1:
            raise ValueError(
                "stateful MCP requires RECALLUM__RUNTIME__WORKERS=1 "
                f"(got {self.workers}); keep one Granian worker and one replica "
                "until FastMCP is wired for validated stateless HTTP, sticky "
                "sessions, or shared session state "
                "(RECALLUM__RUNTIME__MCP_STATELESS_HTTP alone is not enough)"
            )
        return self


def _validate_host(value: str) -> str:
    """Normalize one exact Host allowlist entry (without a wildcard)."""
    if value != value.strip():
        raise ValueError("MCP allowed hosts must not contain whitespace")
    value = value.lower()
    if not value or any(char in value for char in "*/?#,@"):
        raise ValueError("MCP allowed hosts must be non-empty exact host names")
    if "://" in value or any(char.isspace() for char in value):
        raise ValueError("MCP allowed hosts must not contain a scheme or whitespace")
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or value[end + 1 :] not in {""} and not value[end + 1 :].startswith(":"):
            raise ValueError("MCP allowed hosts must use a valid IPv6 host")
        host = value[1:end]
        try:
            address = ip_address(host)
            if not isinstance(address, IPv6Address):
                raise ValueError
            suffix = value[end + 1 :]
            if suffix and (not suffix[1:].isdigit() or not 1 <= int(suffix[1:]) <= 65535):
                raise ValueError
        except ValueError as exc:
            raise ValueError("MCP allowed hosts must use valid IP addresses") from exc
        return f"[{address}]{suffix}"
    if value.count(":") > 1:
        raise ValueError("IPv6 MCP hosts must be enclosed in brackets")
    host, separator, port = value.partition(":")
    if separator and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise ValueError("MCP allowed hosts must use valid ports")
    try:
        IPv4Network(f"{host}/32")
    except ValueError:
        labels = host.split(".")
        if any(not label or len(label) > 63 for label in labels):
            raise ValueError("MCP allowed hosts must use exact DNS names") from None
        if any(not (label[0].isalnum() and label[-1].isalnum()) for label in labels):
            raise ValueError("MCP allowed hosts must use exact DNS names") from None
        if any(not all(char.isalnum() or char == "-" for char in label) for label in labels):
            raise ValueError("MCP allowed hosts must use exact DNS names") from None
    return value


def _validate_origin(value: str) -> str:
    """Normalize one exact HTTP origin for FastMCP's host/origin guard."""
    value = value.strip()
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError("MCP allowed origins must be exact HTTP origins") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "*" in value
    ):
        raise ValueError("MCP allowed origins must be exact HTTP origins")
    try:
        address = ip_address(hostname)
    except ValueError:
        host = hostname.lower()
    else:
        host = str(address)
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme.lower()}://{host}{f':{port}' if port else ''}"


class MCPBoundarySettings(BaseModel):
    """Exact MCP Host/Origin allowlists used at the transport boundary."""

    model_config = ConfigDict(frozen=True)

    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]", "testserver")
    allowed_origins: tuple[str, ...] = (
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
        "http://testserver",
    )

    @model_validator(mode="after")
    def validate_allowlists(self) -> MCPBoundarySettings:
        if not self.allowed_hosts or not self.allowed_origins:
            raise ValueError("MCP allowed hosts and origins must not be empty")
        object.__setattr__(
            self, "allowed_hosts", tuple(_validate_host(item) for item in self.allowed_hosts)
        )
        object.__setattr__(
            self,
            "allowed_origins",
            tuple(_validate_origin(item) for item in self.allowed_origins),
        )
        return self


class ProxyBoundarySettings(BaseModel):
    """Networks whose immediate peer may supply X-Forwarded-For."""

    model_config = ConfigDict(frozen=True)

    trusted_cidrs: tuple[IPvAnyNetwork, ...] = ()


class RequestBoundarySettings(BaseModel):
    """Validated request/password ceilings consumed by the enforcement story."""

    model_config = ConfigDict(frozen=True)

    general_body_bytes: int = Field(default=1 << 20, gt=0, le=100 << 20)
    login_body_bytes: int = Field(default=16 << 10, gt=0, le=10 << 20)
    password_max_chars: int = Field(default=256, gt=0, le=256)


class RateLimitSettings(BaseModel):
    """Validated rate budgets consumed by the enforcement story."""

    model_config = ConfigDict(frozen=True)

    login_ip_attempts: int = Field(default=30, gt=0, le=1_000_000)
    login_ip_window_seconds: int = Field(default=300, gt=0, le=86_400)
    login_account_attempts: int = Field(default=5, gt=0, le=1_000_000)
    login_account_window_seconds: int = Field(default=300, gt=0, le=86_400)
    invalid_mcp_auth_attempts: int = Field(default=60, gt=0, le=1_000_000)
    invalid_mcp_auth_window_seconds: int = Field(default=60, gt=0, le=86_400)
    max_buckets: int = Field(default=10_000, gt=0, le=10_000_000)


class BoundarySettings(BaseModel):
    """Public network boundary settings shared by FastAPI and FastMCP."""

    model_config = ConfigDict(frozen=True)

    mcp: MCPBoundarySettings = MCPBoundarySettings()
    proxy: ProxyBoundarySettings = ProxyBoundarySettings()
    request: RequestBoundarySettings = RequestBoundarySettings()
    rate: RateLimitSettings = RateLimitSettings()


class Settings(BaseSettings):
    """Top-level Recallum settings."""

    model_config = SettingsConfigDict(
        env_prefix="RECALLUM__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    database: DatabaseSettings = DatabaseSettings()
    readiness: ReadinessSettings = ReadinessSettings()
    ollama: OllamaSettings = OllamaSettings()
    auth: AuthSettings = AuthSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    web: WebSettings = WebSettings()
    limits: MemoryLimits = MemoryLimits()
    boundary: BoundarySettings = BoundarySettings()
    runtime: RuntimeSettings = RuntimeSettings()

    @model_validator(mode="before")
    @classmethod
    def align_boundary_environment(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        boundary = values.get("boundary")
        top_environment = values.get("environment")
        if isinstance(boundary, dict) and "environment" in boundary:
            nested_environment = boundary["environment"]
            if top_environment is None:
                raise ValueError("environment must be configured at the top level")
            if nested_environment != top_environment:
                raise ValueError("top-level environment is authoritative")
            values["boundary"] = {
                key: value for key, value in boundary.items() if key != "environment"
            }
        return values

    @model_validator(mode="after")
    def validate_boundary(self) -> Settings:
        if self.environment != "production":
            return self
        boundary = self.boundary
        if not boundary.mcp.model_fields_set >= {"allowed_hosts", "allowed_origins"}:
            raise ValueError("production requires explicit MCP allowed hosts and origins")
        if (
            "trusted_cidrs" not in boundary.proxy.model_fields_set
            or not boundary.proxy.trusted_cidrs
        ):
            raise ValueError("production requires explicit trusted proxy CIDRs")
        if any(network.prefixlen == 0 for network in boundary.proxy.trusted_cidrs):
            raise ValueError("production trusted proxy CIDRs must not be wildcard networks")
        if not boundary.request.model_fields_set >= {
            "general_body_bytes", "login_body_bytes", "password_max_chars"
        }:
            raise ValueError("production requires explicit request limits")
        if not boundary.rate.model_fields_set >= {
            "login_ip_attempts", "login_ip_window_seconds", "login_account_attempts",
            "login_account_window_seconds", "invalid_mcp_auth_attempts",
            "invalid_mcp_auth_window_seconds", "max_buckets",
        }:
            raise ValueError("production requires explicit rate budgets")
        return self

    def for_container(self) -> dict[str, Any]:
        """Plain nested dict with secrets revealed, suitable for the DI container."""
        return {
            "environment": self.environment,
            "database": {
                "url": self.database.url.get_secret_value(),
                "echo": self.database.echo,
                "pool_size": self.database.pool_size,
                "max_overflow": self.database.max_overflow,
            },
            "readiness": self.readiness.model_dump(),
            "ollama": {
                "url": self.ollama.url,
                "model": self.ollama.model,
                "timeout_seconds": self.ollama.timeout_seconds,
                "dimensions": self.ollama.dimensions,
            },
            "auth": {
                "key_prefix": self.auth.key_prefix,
                "key_entropy_bytes": self.auth.key_entropy_bytes,
                "identity_cache_seconds": self.auth.identity_cache_seconds,
            },
            "telemetry": self.telemetry.model_dump(exclude={"metrics_token"}),
            "web": self.web.model_dump(),
            "limits": self.limits,
            "boundary": self.boundary.model_dump(),
            "runtime": self.runtime.model_dump(),
        }


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
