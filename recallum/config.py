"""Validated application settings, loaded from environment variables.

Environment variables use the ``RECALLUM__<GROUP>__<FIELD>`` convention,
e.g. ``RECALLUM__DATABASE__URL`` or ``RECALLUM__OLLAMA__MODEL``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from recallum.memory.limits import MemoryLimits

EMBEDDING_DIMENSIONS = 768


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
            },
            "limits": self.limits,
        }


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
