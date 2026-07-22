"""Validation and normalization for memory inputs (task 3.2).

Content is NFC-normalized, trimmed and whitespace-collapsed; the normalized
form feeds both storage and the deduplication hash so trivial rewordings of
whitespace never create duplicate rows.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Literal, get_args

Category = Literal["preference", "decision", "constraint", "fact"]
Scope = Literal["global", "project"]

CATEGORIES: tuple[str, ...] = get_args(Category)

_WHITESPACE = re.compile(r"\s+")

MetadataValue = str | int | float | bool | None


class MemoryValidationError(ValueError):
    """Raised when a memory input violates validation rules."""


def normalize_content(content: str, max_chars: int) -> str:
    """Trim, NFC-normalize and collapse internal whitespace runs."""
    if content is None:
        raise MemoryValidationError("content must not be empty")
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", content)).strip()
    if not normalized:
        raise MemoryValidationError("content must not be empty")
    if len(normalized) > max_chars:
        raise MemoryValidationError(f"content exceeds {max_chars} characters")
    return normalized


def normalize_project(project: str | None, max_chars: int) -> str | None:
    """Normalize an optional project name; empty strings become None."""
    if project is None:
        return None
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", project)).strip()
    if not normalized:
        return None
    if len(normalized) > max_chars:
        raise MemoryValidationError(f"project exceeds {max_chars} characters")
    return normalized


def validate_category(category: str) -> Category:
    if category not in CATEGORIES:
        raise MemoryValidationError(
            f"unknown category '{category}'; expected one of {', '.join(CATEGORIES)}"
        )
    return category  # type: ignore[return-value]


def scope_for(project: str | None) -> Scope:
    return "project" if project is not None else "global"


def validate_importance(importance: int) -> int:
    if not isinstance(importance, int) or isinstance(importance, bool):
        raise MemoryValidationError("importance must be an integer")
    if not 0 <= importance <= 10:
        raise MemoryValidationError("importance must be between 0 and 10")
    return importance


def validate_metadata(
    metadata: dict[str, Any] | None, max_bytes: int, max_keys: int
) -> dict[str, Any]:
    """Accept only flat JSON-primitive metadata within size limits."""
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise MemoryValidationError("metadata must be a JSON object")
    if len(metadata) > max_keys:
        raise MemoryValidationError(f"metadata exceeds {max_keys} keys")
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            raise MemoryValidationError("metadata keys must be non-empty strings")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise MemoryValidationError(
                f"metadata value for '{key}' must be a JSON primitive"
            )
    serialized = json.dumps(metadata, ensure_ascii=True, sort_keys=True)
    if len(serialized.encode("utf-8")) > max_bytes:
        raise MemoryValidationError(f"metadata exceeds {max_bytes} bytes")
    return dict(metadata)


def content_hash(normalized_content: str) -> str:
    """SHA-256 of the normalized content, used for exact-duplicate detection."""
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
