"""Structured JSON logging with redaction of secrets.

Nothing here ever logs memory content, metadata or full tokens: log lines
carry ids and categories, and the formatter scrubs API keys and bearer tokens
from any message as a second barrier.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

# Recallum API keys ("rcl_" + urlsafe token) and Authorization bearers.
_REDACTIONS = (
    re.compile(r"rcl_[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{8,}"),
)


def redact(text: str) -> str:
    """Replace anything that looks like a credential with ``[REDACTED]``."""
    for pattern in _REDACTIONS:
        text = pattern.sub(
            lambda m: m.group(1) + "[REDACTED]" if m.groups() else "[REDACTED]", text
        )
    return text


class JsonFormatter(logging.Formatter):
    """Single-line JSON records with redaction applied to the rendered message."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Install JSON structured logging on the root logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Keep noisy access logs consistent with the same format/level policy.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
