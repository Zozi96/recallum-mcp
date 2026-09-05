"""MCP tool-surface documentation gate (S001).

The public docs must name exactly the canonical fifteen MCP tools. This module
checks ``README.md`` and ``docs/clients.md`` against ``EXPECTED_TOOLS`` — the
same constant the live-server discovery test uses — so the docs gate and the
runtime gate share one allowlist and cannot drift apart. The check is pure
text logic over backtick tool tokens: no network, clock, or services, so the
``unit-plugin`` fast lane collects it.

Rules:
- README must name all fifteen canonical tools and must not claim a count
  other than fifteen.
- README and ``docs/clients.md`` must render every explicit tool enumeration
  (a contiguous list of >=2 canonical names) as exactly the canonical set.
- Usage guidance that names a subset (e.g. one tool per bullet followed by
  prose, or ``X / Y`` shorthand) is not an enumeration and must not fail.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.unit.test_mcp_tools import EXPECTED_TOOLS

# Reuse the runtime surface constant directly; no second literal to drift.
ALLOWLIST = EXPECTED_TOOLS

ALLOWLIST_TOKENS = ", ".join(f"`{name}`" for name in sorted(ALLOWLIST))

REPO_ROOT = Path(__file__).resolve().parents[2]

TOKEN_RE = re.compile(r"`([A-Za-z][A-Za-z0-9_]*)")

# Allowed text between two tools of one enumeration: whitespace/commas, an
# "and"/"or" connective, or a markdown list marker. The enclosing backticks of
# the two tokens frame the gap. A slash (e.g. "X / Y" shorthand) and any
# prose break a run, so usage guidance never reads as a list.
_SEPARATOR_RE = re.compile(
    r"^`?(?:[\s,]+|[\s,]*(?:and|or)[\s,]+|[\s,]*[-*][\s,]*)`?$", re.IGNORECASE
)

_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
}
_COUNT_CLAIM_RE = re.compile(
    r"\b(?P<count>" + "|".join([*_NUMBER_WORDS, r"\d+"]) + r")\s+MCP\s+tools?\b",
    re.IGNORECASE,
)


class _Token(NamedTuple):
    start: int
    end: int
    name: str


class _Run(NamedTuple):
    tokens: list[_Token]
    has_comma: bool


def _runs(text: str) -> list[_Run]:
    """Maximal contiguous backtick-token runs; each with a comma-separator flag."""
    tokens = [
        _Token(match.start(), match.end(), match.group(1)) for match in TOKEN_RE.finditer(text)
    ]
    runs: list[_Run] = []
    current: list[_Token] = []
    has_comma = False
    for token in tokens:
        if current:
            gap = text[current[-1].end : token.start]
            if _SEPARATOR_RE.match(gap) is None:
                runs.append(_Run(current, has_comma))
                current = []
                has_comma = False
            elif "," in gap:
                has_comma = True
        current.append(token)
    if current:
        runs.append(_Run(current, has_comma))
    return runs


def _enumeration_issues(text: str) -> list[str]:
    """Mismatches for explicit enumerations (contiguous runs of >=2 tools).

    A run counts as an enumeration when it holds at least three canonical
    names, or exactly two separated by a comma. Prose like "use ``a`` and
    ``b``" stays below that bar.
    """
    issues: list[str] = []
    for run in _runs(text):
        names = {token.name for token in run.tokens}
        canonical = names & ALLOWLIST
        if len(canonical) < 2 or (len(canonical) == 2 and not run.has_comma):
            continue
        problems: list[str] = []
        missing = ALLOWLIST - canonical
        if missing:
            problems.append(f"missing canonical tools: {sorted(missing)}")
        extra = names - ALLOWLIST
        if extra:
            problems.append(f"tools outside the canonical set: {sorted(extra)}")
        if problems:
            issues.append("; ".join(problems))
    return issues


def _count_claim_issues(text: str) -> list[str]:
    issues: list[str] = []
    for match in _COUNT_CLAIM_RE.finditer(text):
        raw = match.group("count").lower()
        count = _NUMBER_WORDS[raw] if raw in _NUMBER_WORDS else int(raw)
        if count != len(ALLOWLIST):
            claim = text[match.start() : match.end()]
            issues.append(f"claims {claim!r}, but the canonical surface has {len(ALLOWLIST)} tools")
    return issues


def _doc_issues(path: Path, label: str, require_all_names: bool) -> list[str]:
    """Mismatches for one document; ``label`` prefixes each issue."""
    if not path.exists():
        return [f"{label}: document is missing"]
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    if require_all_names:
        missing = ALLOWLIST - {match.group(1) for match in TOKEN_RE.finditer(text)}
        if missing:
            issues.append(f"{label} does not name the canonical tools: {sorted(missing)}")
    issues.extend(_enumeration_issues(text))
    issues.extend(_count_claim_issues(text))
    return [f"{label}: {issue}" for issue in issues]


def check_tool_surface_docs(repo_root: Path) -> list[str]:
    """Human-readable issues; empty when the documented surface is aligned.

    Never touches the network or a live server: the canonical surface is the
    allowlist, so the check is deterministic and safe for the fast lane.
    """
    return [
        *_doc_issues(repo_root / "README.md", "README.md", require_all_names=True),
        *_doc_issues(
            repo_root / "docs" / "clients.md",
            "docs/clients.md",
            require_all_names=False,
        ),
    ]


def _check(tmp_path: Path, readme: str = "", clients: str = "") -> list[str]:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (docs_dir / "clients.md").write_text(clients, encoding="utf-8")
    return check_tool_surface_docs(tmp_path)


def _copy_real_docs(tmp_path: Path) -> Path:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy2(REPO_ROOT / "README.md", tmp_path / "README.md")
    shutil.copy2(REPO_ROOT / "docs" / "clients.md", docs_dir / "clients.md")
    return tmp_path


def test_aligned_docs_pass_the_surface_check():
    """The real README and clients guide render exactly the canonical set."""
    assert check_tool_surface_docs(REPO_ROOT) == []


def test_allowlist_is_the_runtime_source_of_truth():
    """No duplicated literal: the gate uses EXPECTED_TOOLS by identity."""
    import tests.unit.test_mcp_tools as runtime

    assert ALLOWLIST is runtime.EXPECTED_TOOLS


def test_remember_tool_docs_declare_degraded_embedding_result():
    """Drift gate: remember/remember_batch docs must advertise write degradation."""
    source = (REPO_ROOT / "recallum" / "mcp" / "server.py").read_text(encoding="utf-8")
    remember_doc = source.split("async def remember(", 1)[1].split("async def remember_batch(", 1)[
        0
    ]
    batch_doc = source.split("async def remember_batch(", 1)[1].split("async def recall(", 1)[0]
    for doc in (remember_doc, batch_doc):
        assert "embedding_degraded" in doc
        assert "degraded" in doc


def test_reverting_readme_to_nine_tools_fails_naming_document_and_mismatch(tmp_path):
    root = _copy_real_docs(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = text.replace("Fifteen MCP tools", "Nine MCP tools")
    text = text.replace("`related_memories`, `reconfirm`, ", "")
    readme.write_text(text, encoding="utf-8")

    issues = check_tool_surface_docs(root)
    combined = "\n".join(issues)
    assert issues
    assert "README.md" in combined
    assert "related_memories" in combined
    assert "reconfirm" in combined
    assert "Nine MCP tools" in combined


@pytest.mark.parametrize("removed", ["related_memories", "reconfirm"])
def test_removing_one_canonical_tool_from_readme_fails_naming_it(tmp_path, removed):
    root = _copy_real_docs(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8").replace(f"`{removed}`, ", "")
    readme.write_text(text, encoding="utf-8")

    combined = "\n".join(check_tool_surface_docs(root))
    assert "README.md" in combined
    assert removed in combined


def test_adding_a_twelfth_tool_to_readme_fails_naming_extra(tmp_path):
    root = _copy_real_docs(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8").replace(
        "`get_skill`, `forget_skill`.", "`get_skill`, `forget_skill`, `hibernate`."
    )
    readme.write_text(text, encoding="utf-8")

    combined = "\n".join(check_tool_surface_docs(root))
    assert "README.md" in combined
    assert "hibernate" in combined


def test_dropping_one_tool_to_ten_in_readme_fails_naming_missing(tmp_path):
    root = _copy_real_docs(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8").replace("`get_memory`, ", "")
    readme.write_text(text, encoding="utf-8")

    issues = check_tool_surface_docs(root)
    assert any("README.md" in issue and "get_memory" in issue for issue in issues)


@pytest.mark.parametrize("removed", ["related_memories", "reconfirm"])
def test_clients_enumeration_omitting_canonical_tool_fails_naming_guide(tmp_path, removed):
    root = _copy_real_docs(tmp_path)
    clients = root / "docs" / "clients.md"
    text = clients.read_text(encoding="utf-8").replace(f"`{removed}`, ", "")
    clients.write_text(text, encoding="utf-8")

    combined = "\n".join(check_tool_surface_docs(root))
    assert "docs/clients.md" in combined
    assert removed in combined


def test_clients_enumeration_including_extra_tool_fails_naming_guide(tmp_path):
    root = _copy_real_docs(tmp_path)
    clients = root / "docs" / "clients.md"
    text = clients.read_text(encoding="utf-8").replace(
        "and `forget_skill`.", "and `forget_skill`, `hibernate`."
    )
    clients.write_text(text, encoding="utf-8")

    combined = "\n".join(check_tool_surface_docs(root))
    assert "docs/clients.md" in combined
    assert "hibernate" in combined


def test_deleting_clients_guide_fails_naming_guide(tmp_path):
    root = _copy_real_docs(tmp_path)
    (root / "docs" / "clients.md").unlink()

    issues = check_tool_surface_docs(root)
    assert any("docs/clients.md" in issue and "missing" in issue for issue in issues)


def test_aligned_copy_passes_and_is_idempotent(tmp_path):
    root = _copy_real_docs(tmp_path)
    assert check_tool_surface_docs(root) == []
    assert check_tool_surface_docs(root) == []


def test_clients_without_enumeration_passes(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    assert _check(tmp_path, readme=readme, clients="# Clients\n\nNo tool list here.") == []


@pytest.mark.parametrize("count", ["nine", "Nine", "9", "ten", "10", "twelve", "12"])
def test_boundary_incorrect_count_claims_fail(tmp_path, count):
    issues = _check(tmp_path, readme=f"- **{count} MCP tools**: {ALLOWLIST_TOKENS}.")
    assert any("README.md" in issue and "MCP tools" in issue for issue in issues)


@pytest.mark.parametrize("count", ["fifteen", "15"])
def test_boundary_correct_count_claims_pass(tmp_path, count):
    assert _check(tmp_path, readme=f"- **{count} MCP tools**: {ALLOWLIST_TOKENS}.") == []


def test_boundary_ten_tool_enumeration_fails(tmp_path):
    names = ", ".join(f"`{name}`" for name in sorted(EXPECTED_TOOLS - {"reconfirm"}))
    issues = _check(tmp_path, readme=f"- **Fifteen MCP tools**: {names}.")
    assert any("reconfirm" in issue for issue in issues)


def test_boundary_twelve_tool_enumeration_fails(tmp_path):
    issues = _check(tmp_path, readme=f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}, `hibernate`.")
    assert any("hibernate" in issue for issue in issues)


def test_boundary_duplicate_name_with_omission_fails(tmp_path):
    tokens = re.sub(
        r"`reconfirm`, ", "", ALLOWLIST_TOKENS.replace("`forget`", "`forget`, `forget`", 1)
    )
    issues = _check(tmp_path, readme=f"- **Fifteen MCP tools**: {tokens}.")
    assert any("reconfirm" in issue for issue in issues)


def test_boundary_duplicate_name_with_complete_set_passes(tmp_path):
    tokens = ALLOWLIST_TOKENS.replace("`forget`", "`forget`, `forget`", 1)
    assert _check(tmp_path, readme=f"- **Fifteen MCP tools**: {tokens}.") == []


def test_boundary_name_split_across_lines_fails(tmp_path):
    tokens = ALLOWLIST_TOKENS.replace("`reconfirm`", "`reconf\nirm`")
    issues = _check(tmp_path, readme=f"- **Fifteen MCP tools**: {tokens}.")
    assert any("reconfirm" in issue for issue in issues)


def test_boundary_case_variant_fails(tmp_path):
    tokens = ALLOWLIST_TOKENS.replace("`remember`", "`Remember`")
    issues = _check(tmp_path, readme=f"- **Fifteen MCP tools**: {tokens}.")
    assert any("remember" in issue for issue in issues)


def test_boundary_bare_names_are_not_detected(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS.replace('`', '')}."
    issues = _check(tmp_path, readme=readme)
    assert any("README.md" in issue for issue in issues)


def test_boundary_name_in_heading_counts_as_present(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}.\n\n## `related_memories`\n"
    assert _check(tmp_path, readme=readme) == []


def test_boundary_heading_only_mentions_are_not_enumerations(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    assert _check(tmp_path, readme=readme, clients="## `recall`\n\nUse the memory tools.") == []


def test_boundary_subset_usage_guidance_is_not_an_enumeration(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    clients = """## Agent usage guidance

Put a short instruction in each project's AGENTS.md:
- remember: store durable preferences, decisions, constraints, facts.
- recall: search memory by meaning or exact terms before asking again.
- context: call at the start of a session on a project.
- list_memories / forget: browse and remove your own memories.
"""
    assert _check(tmp_path, readme=readme, clients=clients) == []


def test_boundary_clients_complete_enumeration_passes(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    assert _check(tmp_path, readme=readme, clients=f"The tools are {ALLOWLIST_TOKENS}.") == []


def test_boundary_clients_incomplete_enumeration_fails(tmp_path):
    names = ", ".join(
        f"`{name}`" for name in sorted(EXPECTED_TOOLS - {"related_memories", "reconfirm"})
    )
    issues = _check(tmp_path, clients=f"The tools are {names}.")
    assert any("docs/clients.md" in issue and "related_memories" in issue for issue in issues)


def test_boundary_two_name_prose_is_not_an_enumeration(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    assert _check(tmp_path, readme=readme, clients="Use `remember` and `recall` regularly.") == []


def test_boundary_two_name_comma_list_is_an_enumeration(tmp_path):
    readme = f"- **Fifteen MCP tools**: {ALLOWLIST_TOKENS}."
    issues = _check(tmp_path, readme=readme, clients="Use `remember`, `recall` regularly.")
    assert any("docs/clients.md" in issue for issue in issues)
