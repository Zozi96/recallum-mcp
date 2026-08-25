"""Cheap, deterministic project-memory bootstrap: no repo walk, no LLM.

Scans a fixed, bounded allowlist of well-known project files (README,
AGENTS.md, CLAUDE.md, pyproject.toml, package.json, Dockerfile,
docker-compose.yml) plus the mere presence of a handful of conventional
directories, and turns what it finds into a short list of candidate atomic
memories. Everything here is a pure read: parsing uses only ``tomllib`` and
``json``, plus a couple of markdown heuristics -- never a recursive source
walk, never an LLM, never the whole file contents. Candidates are printed for
review by ``recallum-admin bootstrap``; persisting them is a separate,
explicit step through ``MemoryService.remember_batch``.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Category = Literal["preference", "decision", "constraint", "fact"]

# "Cap the total at 10, preferring structured files (pyproject, package.json)
# over prose." Small on purpose: a bootstrap is a handful of high-signal
# starting points for an agent to confirm, not a repo summary.
MAX_CANDIDATES = 10

# How much of a heuristic-extracted markdown line (a heading or a "Requires"
# line) is kept. Well under `MemoryLimits.max_content_chars` (4000): the goal
# is a short atom, not a maximally-long one that merely happens to fit.
_MARKDOWN_EXCERPT_CHARS = 200

# How many bytes of a markdown file are read before heuristics run. Bounds
# memory use against an oversized or binary file sharing an allowlisted name;
# a heading or "Requires" line worth surfacing appears near the top or not at
# all.
_MARKDOWN_READ_CAP_BYTES = 8_000

# How many dependency names a "declared dependencies" candidate lists.
_MAX_DEPENDENCY_NAMES = 10

_DEPENDENCY_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_REQUIRES_RE = re.compile(r"(?i)\brequires?\b\s*[:\-]\s*(.+)")

# Presence-only: examined, never walked or parsed further.
_PRESENCE_DIRECTORIES: tuple[str, ...] = ("src", "tests", "docs", "migrations")


@dataclass(frozen=True, slots=True)
class BootstrapCandidate:
    """One proposed atomic memory, not yet persisted.

    Shape mirrors ``RememberBatchItem`` closely enough to build one directly:
    ``category`` and ``content`` are the claim; ``source_ref`` is the
    allowlisted file (or directory) it came from, carried through as
    provenance (``source_type="bootstrap"``) rather than stuffed into
    ``metadata``.
    """

    category: Category
    content: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class BootstrapScan:
    """Result of scanning one project directory.

    ``candidates`` is already capped at ``MAX_CANDIDATES``, highest-priority
    first. ``omitted`` is how many additional candidates were found but
    dropped by the cap, so the CLI can tell the operator when the list is not
    the whole picture.
    """

    candidates: list[BootstrapCandidate]
    omitted: int


def _dependency_name(requirement: str) -> str | None:
    match = _DEPENDENCY_NAME_RE.match(requirement)
    return match.group(1) if match else None


def _scan_pyproject(path: Path) -> list[BootstrapCandidate]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError, tomllib.TOMLDecodeError, UnicodeDecodeError:
        return []
    candidates: list[BootstrapCandidate] = []
    project = data.get("project")
    if not isinstance(project, dict):
        return candidates
    requires_python = project.get("requires-python")
    if isinstance(requires_python, str) and requires_python.strip():
        candidates.append(
            BootstrapCandidate(
                category="fact",
                content=(
                    f"This project's Python runtime requirement is "
                    f"`{requires_python.strip()}` (from pyproject.toml)."
                ),
                source_ref="pyproject.toml",
            )
        )
    dependencies = project.get("dependencies")
    if isinstance(dependencies, list):
        names = [
            name for req in dependencies if isinstance(req, str) and (name := _dependency_name(req))
        ][:_MAX_DEPENDENCY_NAMES]
        if names:
            candidates.append(
                BootstrapCandidate(
                    category="fact",
                    content=("Declared dependencies (pyproject.toml): " + ", ".join(names) + "."),
                    source_ref="pyproject.toml",
                )
            )
    return candidates


def _scan_package_json(path: Path) -> list[BootstrapCandidate]:
    try:
        with path.open("rb") as handle:
            data = json.load(handle)
    except OSError, json.JSONDecodeError, UnicodeDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    candidates: list[BootstrapCandidate] = []
    engines = data.get("engines")
    node_version = engines.get("node") if isinstance(engines, dict) else None
    if isinstance(node_version, str) and node_version.strip():
        candidates.append(
            BootstrapCandidate(
                category="fact",
                content=(
                    f"This project's Node.js runtime requirement is "
                    f"`{node_version.strip()}` (from package.json)."
                ),
                source_ref="package.json",
            )
        )
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict):
        names = [name for name in dependencies if isinstance(name, str)][:_MAX_DEPENDENCY_NAMES]
        if names:
            candidates.append(
                BootstrapCandidate(
                    category="fact",
                    content=("Declared dependencies (package.json): " + ", ".join(names) + "."),
                    source_ref="package.json",
                )
            )
    return candidates


def _scan_markdown(path: Path, filename: str) -> list[BootstrapCandidate]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MARKDOWN_READ_CAP_BYTES)
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return []
    candidates: list[BootstrapCandidate] = []
    lines = text.splitlines()
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            excerpt = heading.group(1).strip()[:_MARKDOWN_EXCERPT_CHARS]
            if excerpt:
                candidates.append(
                    BootstrapCandidate(
                        category="fact",
                        content=f"Project title (from {filename}): {excerpt}",
                        source_ref=filename,
                    )
                )
            break
    for line in lines:
        requires = _REQUIRES_RE.search(line)
        if requires:
            excerpt = requires.group(0).strip()[:_MARKDOWN_EXCERPT_CHARS]
            if excerpt:
                candidates.append(
                    BootstrapCandidate(
                        category="fact",
                        content=f"Requirement noted in {filename}: {excerpt}",
                        source_ref=filename,
                    )
                )
            break
    return candidates


def _scan_agent_instructions(path: Path, filename: str) -> BootstrapCandidate | None:
    if not path.is_file():
        return None
    return BootstrapCandidate(
        category="fact",
        content=f"This project has agent-specific instructions in {filename}.",
        source_ref=filename,
    )


def scan_project(root: Path) -> BootstrapScan:
    """Scan ``root`` for the fixed allowlist and return capped candidates.

    Structured, cheap-to-trust sources (pyproject.toml, package.json,
    Dockerfile/docker-compose.yml presence, directory presence) come before
    prose (README heuristics), so when the cap trims the list it drops prose
    first.
    """
    found: list[BootstrapCandidate] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        found.extend(_scan_pyproject(pyproject))

    package_json = root / "package.json"
    if package_json.is_file():
        found.extend(_scan_package_json(package_json))

    dockerfile = root / "Dockerfile"
    if dockerfile.is_file():
        found.append(
            BootstrapCandidate(
                category="fact",
                content="This project provides a Dockerfile for containerized builds.",
                source_ref="Dockerfile",
            )
        )

    compose = root / "docker-compose.yml"
    if compose.is_file():
        found.append(
            BootstrapCandidate(
                category="fact",
                content="This project defines a Docker Compose stack (docker-compose.yml).",
                source_ref="docker-compose.yml",
            )
        )

    for name in _PRESENCE_DIRECTORIES:
        if (root / name).is_dir():
            found.append(
                BootstrapCandidate(
                    category="fact",
                    content=f"This project has a `{name}/` directory.",
                    source_ref=f"{name}/",
                )
            )

    for filename in ("AGENTS.md", "CLAUDE.md"):
        candidate = _scan_agent_instructions(root / filename, filename)
        if candidate is not None:
            found.append(candidate)

    readme_md = root / "README.md"
    readme = root / "README"
    if readme_md.is_file():
        found.extend(_scan_markdown(readme_md, "README.md"))
    elif readme.is_file():
        found.extend(_scan_markdown(readme, "README"))

    capped = found[:MAX_CANDIDATES]
    omitted = max(0, len(found) - len(capped))
    return BootstrapScan(candidates=capped, omitted=omitted)
