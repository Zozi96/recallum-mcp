"""Validated application settings, loaded from environment variables.

Environment variables use the ``RECALLUM__<GROUP>__<FIELD>`` convention,
e.g. ``RECALLUM__DATABASE__URL`` or ``RECALLUM__OLLAMA__MODEL``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, model_validator
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
    # worst-case delay before a revoked key stops working, so it defaults to 0
    # (no caching, revocation is immediate) and is capped at five minutes.
    identity_cache_seconds: float = Field(default=0.0, ge=0.0, le=300.0)


class TelemetrySettings(BaseModel):
    """Bounded, deferred tool-activity collection settings."""

    batch_size: int = Field(default=100, ge=1, le=10_000)
    flush_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    buffer_limit: int = Field(default=1_000, ge=1, le=100_000)
    retention_days: int = Field(default=90, ge=1, le=366)

    @model_validator(mode="after")
    def validate_buffer_capacity(self) -> TelemetrySettings:
        if self.buffer_limit < self.batch_size:
            raise ValueError("buffer_limit must be greater than or equal to batch_size")
        return self


class WebSettings(BaseModel):
    """Browser-session and password settings."""

    allowed_origin: str = "https://memory.zozbit.com"
    cookie_name: str = Field(default="recallum_session", min_length=1, max_length=64)
    idle_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0, le=31 * 24 * 60 * 60)
    absolute_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0, le=366 * 24 * 60 * 60)
    rotation_threshold: float = Field(default=0.5, gt=0, lt=1)
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


class Settings(BaseSettings):
    """Top-level Recallum settings."""

    model_config = SettingsConfigDict(
        env_prefix="RECALLUM__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    database: DatabaseSettings = DatabaseSettings()
    ollama: OllamaSettings = OllamaSettings()
    auth: AuthSettings = AuthSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    web: WebSettings = WebSettings()
    limits: MemoryLimits = MemoryLimits()

    def for_container(self) -> dict[str, Any]:
        """Plain nested dict with secrets revealed, suitable for the DI container."""
        return {
            "database": {
                "url": self.database.url.get_secret_value(),
                "echo": self.database.echo,
                "pool_size": self.database.pool_size,
                "max_overflow": self.database.max_overflow,
            },
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
            "telemetry": self.telemetry.model_dump(),
            "web": self.web.model_dump(),
            "limits": self.limits,
        }


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
