"""Stable interface for skill-domain errors."""

from __future__ import annotations


class SkillValidationError(ValueError):
    """Raised when a skill input violates a domain rule."""


__all__ = ["SkillValidationError"]
