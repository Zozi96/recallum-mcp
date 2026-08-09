"""FastMCP private-API compatibility seam contracts."""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from recallum.mcp import compatibility as compat
from recallum.mcp.compatibility import (
    list_local_prompts,
    list_local_resource_templates,
    list_local_resources,
)
from recallum.mcp.server import build_mcp_server, validate_only_tools_are_exposed
from tests.fakes import FakeEmbeddingClient, build_test_container

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_METHODS = ("_list_resources", "_list_resource_templates", "_list_prompts")
SUPPORTED = SpecifierSet(">=3.4,<4")


def test_locked_fastmcp_version_is_within_supported_range():
    version = Version(importlib.metadata.version("fastmcp"))
    assert version in SUPPORTED


def test_private_list_calls_live_only_in_compatibility_seam():
    offenders: list[str] = []
    seam = Path(compat.__file__).resolve()
    for path in (ROOT / "recallum").rglob("*.py"):
        if path.resolve() == seam:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in PRIVATE_METHODS:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.attr}")
    assert offenders == []


async def test_compatibility_seam_lists_and_is_idempotent():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    mcp = build_mcp_server(container)
    first = await list_local_resources(mcp)
    second = await list_local_resources(mcp)
    assert {str(item.uri) for item in first} == {str(item.uri) for item in second}
    await list_local_resource_templates(mcp)
    await list_local_prompts(mcp)
    await validate_only_tools_are_exposed(mcp)


async def test_missing_private_api_fails_startup_diagnostically():
    mcp = FastMCP(name="broken")
    mcp._list_resources = AsyncMock(side_effect=AttributeError("gone"))  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="FastMCP compatibility failure"):
        await list_local_resources(mcp)


async def test_absent_private_method_fails_diagnostically():
    mcp = FastMCP(name="broken")
    mcp._list_prompts = "not-callable"  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="_list_prompts"):
        await list_local_prompts(mcp)
