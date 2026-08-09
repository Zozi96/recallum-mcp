"""Shared OpenAPI response metadata for the browser API contract."""

from __future__ import annotations

UNAUTHORIZED = {"description": "Not authenticated"}
FORBIDDEN = {"description": "Forbidden"}
PAYLOAD_TOO_LARGE = {"description": "Request body too large"}
VALIDATION_ERROR = {"description": "Validation error"}
RATE_LIMITED = {"description": "Too many requests"}
UNAVAILABLE = {"description": "Dependency unavailable"}

LOGIN_RESPONSES = {
    401: UNAUTHORIZED,
    413: PAYLOAD_TOO_LARGE,
    422: VALIDATION_ERROR,
    429: RATE_LIMITED,
}

PROTECTED_RESPONSES = {
    401: UNAUTHORIZED,
    403: FORBIDDEN,
    413: PAYLOAD_TOO_LARGE,
    422: VALIDATION_ERROR,
    503: UNAVAILABLE,
}

# Admin routes share the same documented status set as other protected routes.
ADMIN_RESPONSES = PROTECTED_RESPONSES

__all__ = [
    "ADMIN_RESPONSES",
    "LOGIN_RESPONSES",
    "PROTECTED_RESPONSES",
]
