"""Privacy-safe failure diagnostics shared across service boundaries."""

from __future__ import annotations

import contextvars
import logging
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from os.path import basename

EMBEDDING_UNAVAILABLE_MESSAGE = "embedding service unavailable"

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "diagnostic_correlation_id", default="unavailable"
)


@contextmanager
def diagnostic_correlation(correlation_id: str) -> Iterator[None]:
    """Bind a safe request correlation for diagnostics in lower layers."""
    token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def record_sanitized_failure(
    logger: logging.Logger, exc: BaseException, *, message: str
) -> None:
    """Log class, correlation, and frames without exception text or arguments."""
    failure_class = f"{type(exc).__module__}.{type(exc).__qualname__}"
    extracted = traceback.extract_tb(exc.__traceback__)[-3:]
    frames = (
        " > ".join(
            f"{basename(frame.filename)}:{frame.lineno}:{frame.name}" for frame in extracted
        )
        if extracted
        else "unavailable"
    )
    correlation_id = _correlation_id.get()
    logger.error(
        f"{message} class=%s correlation=%s frames=%s",
        failure_class,
        correlation_id,
        frames,
        extra={
            "failure_class": failure_class,
            "correlation_id": correlation_id,
            "frames": frames,
            "stack": frames,
        },
    )


__all__ = [
    "EMBEDDING_UNAVAILABLE_MESSAGE",
    "diagnostic_correlation",
    "record_sanitized_failure",
]
