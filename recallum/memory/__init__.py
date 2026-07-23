"""Stable interface for memory-domain errors and visibility policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

VisibilityMode = Literal["all", "global", "project", "global_and_project"]


class MemoryValidationError(ValueError):
    """Raised when a memory input violates a domain rule."""


class _VisibleMemory(Protocol):
    scope: str
    project: str | None


@dataclass(frozen=True, slots=True)
class MemoryVisibility:
    """Canonical owner-relative visibility shared by repository adapters."""

    mode: VisibilityMode
    project: str | None = None

    @classmethod
    def from_filters(cls, *, scope: str | None, project: str | None) -> MemoryVisibility:
        if scope == "global":
            return cls("global")
        if scope == "project":
            if project is None:
                raise MemoryValidationError("project is required when scope is 'project'")
            return cls("project", project)
        if scope is not None:
            raise MemoryValidationError("scope must be 'global' or 'project'")
        if project is not None:
            return cls("global_and_project", project)
        return cls("all")

    @classmethod
    def global_only(cls) -> MemoryVisibility:
        return cls("global")

    @classmethod
    def project_only(cls, project: str) -> MemoryVisibility:
        return cls("project", project)

    def includes(self, memory: _VisibleMemory) -> bool:
        """Apply the canonical policy in an in-memory adapter."""
        if self.mode == "all":
            return True
        if self.mode == "global":
            return memory.scope == "global"
        if self.mode == "project":
            return memory.scope == "project" and memory.project == self.project
        return memory.scope == "global" or (
            memory.scope == "project" and memory.project == self.project
        )


__all__ = ["MemoryValidationError", "MemoryVisibility"]
