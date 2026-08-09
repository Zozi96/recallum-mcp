"""Strict, shared types for values whose coercion changes security semantics."""

import re
from collections.abc import Callable
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    Strict,
    TypeAdapter,
    create_model,
)
from pydantic_core import PydanticUndefined

ADMIN_PAGE_DEFAULT = 100
ADMIN_PAGE_MAX = 200


def _positive_limit(value: int) -> int:
    if value <= 0:
        raise ValueError("limit must be positive")
    return value


def _admin_page_limit(value: int) -> int:
    if not 1 <= value <= ADMIN_PAGE_MAX:
        raise ValueError(f"limit must be between 1 and {ADMIN_PAGE_MAX}")
    return value


def _importance(value: int) -> int:
    if not 0 <= value <= 10:
        raise ValueError("importance must be between 0 and 10")
    return value


def _query_integer(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("integer query values must not be boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)
    raise ValueError("integer query values must be canonical integers")


def _nonnegative_offset(value: int) -> int:
    if value < 0:
        raise ValueError("offset must be nonnegative")
    return value


def _positive_size(value: int) -> int:
    if value <= 0:
        raise ValueError("size must be positive")
    return value


def _password_max(max_chars: int) -> Callable[[str], str]:
    def _check(value: str) -> str:
        if len(value) > max_chars:
            raise ValueError("password is too long")
        return value

    return _check


_password = _password_max(256)


StrictImportance = Annotated[int, Strict()]
StrictImportanceInput = Annotated[int, Strict(), AfterValidator(_importance)]
StrictPositiveLimit = Annotated[int, Strict(), AfterValidator(_positive_limit)]
StrictNonNegativeOffset = Annotated[int, Strict(), AfterValidator(_nonnegative_offset)]
StrictPositiveSize = Annotated[int, Strict(), AfterValidator(_positive_size)]
StrictQueryPositiveLimit = Annotated[
    int, BeforeValidator(_query_integer), AfterValidator(_positive_limit)
]
StrictQueryAdminLimit = Annotated[
    int,
    BeforeValidator(_query_integer),
    Field(ge=1, le=ADMIN_PAGE_MAX),
    AfterValidator(_admin_page_limit),
]
StrictQueryNonNegativeOffset = Annotated[
    int, BeforeValidator(_query_integer), AfterValidator(_nonnegative_offset)
]
Password = Annotated[str, Field(min_length=1), AfterValidator(_password)]


def password_model(base: type[BaseModel], max_chars: int) -> type[BaseModel]:
    """Create a request model whose password field uses the configured cap."""
    # Cap lives only in AfterValidator so the public message stays
    # "password is too long" and OpenAPI does not advertise maxLength.
    return create_model(
        base.__name__,
        __base__=base,
        __module__=base.__module__,
        password=(
            Annotated[
                str,
                Field(min_length=1),
                AfterValidator(_password_max(max_chars)),
            ],
            PydanticUndefined,
        ),
    )


def validate_strict(value: object, annotation: object) -> object:
    """Validate a domain argument with the same rules as transport schemas."""
    return TypeAdapter(annotation).validate_python(value)


__all__ = [
    "ADMIN_PAGE_DEFAULT",
    "ADMIN_PAGE_MAX",
    "Password",
    "StrictImportance",
    "StrictImportanceInput",
    "StrictNonNegativeOffset",
    "StrictPositiveLimit",
    "StrictPositiveSize",
    "StrictQueryAdminLimit",
    "StrictQueryNonNegativeOffset",
    "StrictQueryPositiveLimit",
    "password_model",
    "validate_strict",
]
