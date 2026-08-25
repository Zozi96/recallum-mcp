"""Bootstrap parser unit tests: fixtures only, no network, no LLM (task 3.1)."""

from __future__ import annotations

from recallum.bootstrap import MAX_CANDIDATES, scan_project


def test_typical_python_project_yields_runtime_and_agent_instructions_candidates(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nrequires-python = ">=3.11"\n'
        'dependencies = ["fastapi>=0.100", "pydantic"]\n'
    )
    agents_body = "# Agent Instructions\n\n" + ("Follow these rules carefully.\n" * 50)
    (tmp_path / "AGENTS.md").write_text(agents_body)

    scan = scan_project(tmp_path)

    runtime = next(
        c for c in scan.candidates if c.source_ref == "pyproject.toml" and "3.11" in c.content
    )
    assert "runtime" in runtime.content.lower()
    assert runtime.category == "fact"

    agent_fact = next(c for c in scan.candidates if c.source_ref == "AGENTS.md")
    assert "AGENTS.md" in agent_fact.content
    assert agents_body not in agent_fact.content
    assert "Follow these rules carefully." not in agent_fact.content

    deps = next(
        c for c in scan.candidates if c.source_ref == "pyproject.toml" and "fastapi" in c.content
    )
    assert "pydantic" in deps.content


def test_long_readme_is_not_dumped_wholesale(tmp_path):
    paragraph = "Lorem ipsum dolor sit amet. " * 300
    readme = "# Demo Project\n\n" + paragraph + "\n\nRequires: a running Postgres instance.\n"
    (tmp_path / "README.md").write_text(readme)

    scan = scan_project(tmp_path)

    assert scan.candidates
    for candidate in scan.candidates:
        assert candidate.source_ref == "README.md"
        assert len(candidate.content) < 300
        assert paragraph not in candidate.content
        assert candidate.content != readme


def test_cap_of_ten_enforced_and_prefers_structured_over_prose(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\ndependencies = ["fastapi", "sqlalchemy"]\n'
    )
    (tmp_path / "package.json").write_text(
        '{"engines": {"node": ">=20"}, "dependencies": {"react": "^18", "next": "^14"}}'
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n")
    for name in ("src", "tests", "docs", "migrations"):
        (tmp_path / name).mkdir()
    (tmp_path / "AGENTS.md").write_text("# Agents\n")
    (tmp_path / "CLAUDE.md").write_text("# Claude\n")
    (tmp_path / "README.md").write_text("# Demo\n\nRequires: something.\n")

    scan = scan_project(tmp_path)

    assert len(scan.candidates) == MAX_CANDIDATES
    assert scan.omitted > 0
    kept_refs = {c.source_ref for c in scan.candidates}
    assert "README.md" not in kept_refs
    assert "AGENTS.md" not in kept_refs
    assert "CLAUDE.md" not in kept_refs
    assert "pyproject.toml" in kept_refs
    assert "package.json" in kept_refs


def test_directory_presence_flags(tmp_path):
    for name in ("src", "tests", "docs", "migrations"):
        (tmp_path / name).mkdir()

    scan = scan_project(tmp_path)

    refs = {c.source_ref for c in scan.candidates}
    assert refs == {"src/", "tests/", "docs/", "migrations/"}
    assert scan.omitted == 0


def test_empty_directory_yields_no_candidates(tmp_path):
    scan = scan_project(tmp_path)

    assert scan.candidates == []
    assert scan.omitted == 0


def test_malformed_pyproject_toml_is_skipped_without_crashing(tmp_path):
    (tmp_path / "pyproject.toml").write_text("this is [not valid toml")
    (tmp_path / "AGENTS.md").write_text("# Agents\n")

    scan = scan_project(tmp_path)

    assert all(c.source_ref != "pyproject.toml" for c in scan.candidates)
    assert any(c.source_ref == "AGENTS.md" for c in scan.candidates)


def test_malformed_package_json_is_skipped_without_crashing(tmp_path):
    (tmp_path / "package.json").write_bytes(b"{not: valid json,,,")

    scan = scan_project(tmp_path)

    assert scan.candidates == []


def test_binary_pyproject_toml_is_skipped_without_crashing(tmp_path):
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00\x01binary garbage")

    scan = scan_project(tmp_path)

    assert scan.candidates == []


def test_binary_package_json_is_skipped_without_crashing(tmp_path):
    (tmp_path / "package.json").write_bytes(b"\xff\xfe\x00\x01binary garbage")

    scan = scan_project(tmp_path)

    assert scan.candidates == []


def test_allowlisted_name_that_is_a_directory_is_skipped_without_crashing(tmp_path):
    (tmp_path / "pyproject.toml").mkdir()
    (tmp_path / "package.json").mkdir()
    (tmp_path / "AGENTS.md").mkdir()
    (tmp_path / "README.md").mkdir()

    scan = scan_project(tmp_path)

    assert scan.candidates == []
    assert scan.omitted == 0


def test_huge_readme_is_read_capped_and_does_not_crash(tmp_path):
    huge = "x" * 2_000_000
    (tmp_path / "README.md").write_text(f"# Big\n\n{huge}\n")

    scan = scan_project(tmp_path)

    assert len(scan.candidates) <= 2
    for candidate in scan.candidates:
        assert len(candidate.content) < 300


def test_unreadable_pyproject_toml_is_skipped_without_crashing(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "AGENTS.md").write_text("# Agents\n")
    pyproject.chmod(0o000)
    try:
        scan = scan_project(tmp_path)
    finally:
        pyproject.chmod(0o644)

    assert all(c.source_ref != "pyproject.toml" for c in scan.candidates)
    assert any(c.source_ref == "AGENTS.md" for c in scan.candidates)


def test_symlinked_readme_does_not_crash(tmp_path):
    target = tmp_path / "actual_readme.md"
    target.write_text("# Linked Title\n\nRequires: nothing special.\n")
    link = tmp_path / "README.md"
    link.symlink_to(target)

    scan = scan_project(tmp_path)

    assert any(c.source_ref == "README.md" and "Linked Title" in c.content for c in scan.candidates)


def test_broken_symlink_allowlisted_name_does_not_crash(tmp_path):
    link = tmp_path / "AGENTS.md"
    link.symlink_to(tmp_path / "does-not-exist.md")

    scan = scan_project(tmp_path)

    assert scan.candidates == []
