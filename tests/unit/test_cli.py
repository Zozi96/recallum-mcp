"""CLI (Identity Administration) unit tests: parser + `_run` dispatch."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from recallum.auth.api_keys import hash_token
from recallum.cli import _run, build_parser
from recallum.evaluation import EvalReport, QueryOutcome
from tests.fakes import FakeEmbeddingClient, ScriptedEmbeddingClient, build_test_container


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


async def test_create_user_success_normalizes_email_and_persists(capsys):
    container, fakes = build_test_container()
    args = parse(["create-user", "--email", "Alice@Example.com"])

    code = await _run(args, container)

    assert code == 0
    out = capsys.readouterr().out
    assert out.endswith(" (alice@example.com)\n")
    stored = list(fakes["users"].users.values())
    assert len(stored) == 1
    assert stored[0].email == "alice@example.com"


async def test_create_user_duplicate_raises_value_error_uncaught(capsys):
    # `_run` does not catch ValueError for create-user (only `main()` does);
    # this pins that observed behaviour rather than asserting a nicer one.
    container, _ = build_test_container()
    args = parse(["create-user", "--email", "bob@example.com"])
    assert await _run(args, container) == 0
    capsys.readouterr()

    with pytest.raises(ValueError, match="already exists"):
        await _run(args, container)


async def test_issue_key_success_shows_plaintext_exactly_once(capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "carol@example.com"]), container)
    capsys.readouterr()

    code = await _run(
        parse(["issue-key", "--email", "carol@example.com", "--name", "laptop"]), container
    )

    assert code == 0
    out = capsys.readouterr().out
    stored_keys = list(fakes["keys"].keys.values())
    assert len(stored_keys) == 1
    stored = stored_keys[0]

    plaintext = out.splitlines()[2].split("api key:   ", 1)[1]

    assert out.count(plaintext) == 1
    assert "shown only once" in out
    assert plaintext != stored.key_hash
    assert stored.key_hash == hash_token(plaintext)


async def test_issue_key_unknown_email_exits_1_and_prints_nothing_to_stdout(capsys):
    container, _ = build_test_container()

    code = await _run(
        parse(["issue-key", "--email", "ghost@example.com"]), container
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not exist" in captured.err


async def test_revoke_key_lifecycle(capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "dave@example.com"]), container)
    capsys.readouterr()
    await _run(parse(["issue-key", "--email", "dave@example.com"]), container)
    capsys.readouterr()
    key_id = next(iter(fakes["keys"].keys))

    code = await _run(parse(["revoke-key", "--key-id", str(key_id)]), container)
    assert code == 0
    assert f"key revoked: {key_id}" in capsys.readouterr().out

    code_again = await _run(parse(["revoke-key", "--key-id", str(key_id)]), container)
    assert code_again == 1
    assert "not found or already revoked" in capsys.readouterr().err

    code_unknown = await _run(parse(["revoke-key", "--key-id", str(uuid.uuid4())]), container)
    assert code_unknown == 1
    assert "not found or already revoked" in capsys.readouterr().err


async def test_list_keys_no_keys(capsys):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "erin@example.com"]), container)
    capsys.readouterr()

    code = await _run(parse(["list-keys", "--email", "erin@example.com"]), container)

    assert code == 0
    assert capsys.readouterr().out == "no keys\n"


async def test_list_keys_never_leaks_plaintext_or_hash(capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "frank@example.com"]), container)
    capsys.readouterr()
    await _run(
        parse(["issue-key", "--email", "frank@example.com", "--name", "phone"]), container
    )
    issued_out = capsys.readouterr().out
    plaintext = issued_out.splitlines()[2].split("api key:   ", 1)[1]
    stored_hash = next(iter(fakes["keys"].keys.values())).key_hash

    code = await _run(parse(["list-keys", "--email", "frank@example.com"]), container)

    assert code == 0
    listed = capsys.readouterr().out
    assert "(phone)" in listed
    assert "active" in listed
    assert plaintext not in listed
    assert stored_hash not in listed


async def test_list_keys_unknown_email_exits_1(capsys):
    container, _ = build_test_container()

    code = await _run(parse(["list-keys", "--email", "nobody@example.com"]), container)

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not exist" in captured.err


def test_revoke_key_rejects_non_uuid():
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["revoke-key", "--key-id", "not-a-uuid"])

    assert exc_info.value.code == 2


async def test_set_password_is_interactive_and_admin_commands(monkeypatch, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "admin@example.com"]), container)
    capsys.readouterr()
    prompts = iter(["strong password", "strong password"])
    monkeypatch.setattr("recallum.cli.getpass.getpass", lambda _prompt: next(prompts))

    assert await _run(parse(["set-password", "--email", "admin@example.com"]), container) == 0
    user = next(iter(fakes["users"].users.values()))
    assert user.password_hash.startswith("$argon2id$")
    assert await _run(parse(["grant-admin", "--email", user.email]), container) == 0
    assert user.is_admin is True
    assert await _run(parse(["revoke-admin", "--email", user.email]), container) == 0
    assert user.is_admin is False


async def test_web_admin_commands_reject_unknown_user(monkeypatch, capsys):
    container, fakes = build_test_container()
    monkeypatch.setattr(
        "recallum.cli.getpass.getpass",
        lambda _prompt: pytest.fail("unknown user must fail before prompting"),
    )
    for command in ("grant-admin", "revoke-admin"):
        assert await _run(parse([command, "--email", "ghost@example.com"]), container) == 1
    prompts = iter(["strong", "strong"])
    monkeypatch.setattr("recallum.cli.getpass.getpass", lambda _prompt: next(prompts))
    assert await _run(parse(["set-password", "--email", "ghost@example.com"]), container) == 1
    assert not fakes["users"].users
    assert capsys.readouterr().err.count("does not exist") == 3


async def test_cli_oversized_password_stops_before_lookup_argon_and_persistence(
    monkeypatch, capsys
):
    container, fakes = build_test_container()
    container.config.boundary.request.password_max_chars.from_value(8)
    lookup_calls: list[str] = []
    argon_calls: list[str] = []
    persistence_calls: list[tuple[object, str]] = []
    users = fakes["users"]
    original_lookup = users.get_by_email

    async def counted_lookup(email):
        lookup_calls.append(email)
        return await original_lookup(email)

    def fail_hash(_hasher, password):
        argon_calls.append(password)
        raise AssertionError("Argon2 must not run for an oversized CLI password")

    async def counted_persistence(user_id, encoded):
        persistence_calls.append((user_id, encoded))
        raise AssertionError("persistence must not run for an oversized CLI password")

    monkeypatch.setattr(users, "get_by_email", counted_lookup)
    passwords = container.password_service()
    assert passwords._max_password_chars == 8
    monkeypatch.setattr(type(passwords._hasher), "hash", fail_hash)
    monkeypatch.setattr(users, "set_password", counted_persistence)
    oversized = "x" * 9
    prompts = iter([oversized, oversized])
    monkeypatch.setattr("recallum.cli.getpass.getpass", lambda _prompt: next(prompts))

    code = await _run(parse(["set-password", "--email", "cli-cap@example.com"]), container)

    assert code == 1
    assert capsys.readouterr().err == "error: password exceeds configured maximum length (8)\n"
    assert lookup_calls == []
    assert argon_calls == []
    assert persistence_calls == []


def test_eval_usage_weight_parses_as_float_and_defaults_to_none():
    args = parse(["eval", "--email", "a@b.c", "--dataset", "dataset.json"])
    assert args.usage_weight is None
    assert args.vector_min_similarity is None

    args = parse(
        ["eval", "--email", "a@b.c", "--dataset", "dataset.json", "--usage-weight", "0.3"]
    )
    assert args.usage_weight == 0.3


def test_eval_vector_min_similarity_parses_and_rejects_out_of_range():
    args = parse(
        [
            "eval",
            "--email",
            "a@b.c",
            "--dataset",
            "dataset.json",
            "--vector-min-similarity",
            "0.7",
        ]
    )
    assert args.vector_min_similarity == 0.7
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(
            [
                "eval",
                "--email",
                "a@b.c",
                "--dataset",
                "dataset.json",
                "--vector-min-similarity",
                "1.1",
            ]
        )
    assert exc_info.value.code == 2
    with pytest.raises(SystemExit) as out_of_range:
        build_parser().parse_args(
            [
                "eval",
                "--email",
                "a@b.c",
                "--dataset",
                "dataset.json",
                "--vector-min-similarity",
                "-0.1",
            ]
        )
    assert out_of_range.value.code == 2


async def test_eval_unknown_email_exits_1(capsys):
    container, _ = build_test_container()

    code = await _run(
        parse(["eval", "--email", "ghost@example.com", "--dataset", "missing.json"]), container
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not exist" in captured.err


async def test_eval_usage_weight_reaches_service_limits_and_report_tunables(
    monkeypatch, capsys
):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "eval@example.com"]), container)
    capsys.readouterr()

    captured: dict[str, object] = {}

    async def fake_run_eval(service, user_id, dataset, *, k):
        captured["service"] = service
        return EvalReport(outcomes=[], k=k)

    monkeypatch.setattr("recallum.cli.run_eval", fake_run_eval)
    dataset = Path(__file__).resolve().parents[2] / "scripts" / "eval_dataset.json"

    code = await _run(
        parse(
            [
                "eval",
                "--email",
                "eval@example.com",
                "--dataset",
                str(dataset),
                "--usage-weight",
                "0.3",
            ]
        ),
        container,
    )

    assert code == 0
    assert captured["service"]._limits.recall_usage_weight == 0.3
    out = capsys.readouterr().out
    assert "tunables: recall_usage_weight=0.3" in out


async def test_eval_vector_min_similarity_reaches_service_limits_and_report_tunables(
    monkeypatch, capsys
):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "eval@example.com"]), container)
    capsys.readouterr()

    captured: dict[str, object] = {}

    async def fake_run_eval(service, user_id, dataset, *, k):
        captured["service"] = service
        return EvalReport(outcomes=[], k=k)

    monkeypatch.setattr("recallum.cli.run_eval", fake_run_eval)
    dataset = Path(__file__).resolve().parents[2] / "scripts" / "eval_dataset.json"

    code = await _run(
        parse(
            [
                "eval",
                "--email",
                "eval@example.com",
                "--dataset",
                str(dataset),
                "--vector-min-similarity",
                "0.7",
            ]
        ),
        container,
    )

    assert code == 0
    assert captured["service"]._limits.recall_vector_min_similarity == 0.7
    out = capsys.readouterr().out
    assert "tunables: recall_vector_min_similarity=0.7" in out


async def test_eval_stdout_includes_explicit_zero_and_unjudged_diagnostics(
    monkeypatch, capsys
):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "eval@example.com"]), container)
    capsys.readouterr()

    async def fake_run_eval(service, user_id, dataset, *, k):
        return EvalReport(
            outcomes=[
                QueryOutcome(
                    query="who handles billing",
                    tag="semantic",
                    expected=["beta"],
                    returned=["beta", "noise", "alpha"],
                    reciprocal_rank=1.0,
                    recall_at_k=1.0,
                    graded=True,
                    ndcg_at_5=1.0,
                    essential_recall_at_3=1.0,
                    irrelevant_rate_at_5=2 / 3,
                    explicit_zero_rate_at_5=1 / 3,
                    unjudged_rate_at_5=1 / 3,
                    useful_token_density=0.5,
                )
            ],
            k=k,
        )

    monkeypatch.setattr("recallum.cli.run_eval", fake_run_eval)
    dataset = Path(__file__).resolve().parents[2] / "scripts" / "eval_dataset.json"
    code = await _run(
        parse(["eval", "--email", "eval@example.com", "--dataset", str(dataset)]),
        container,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "irr@5" in out
    assert "exp0@5" in out
    assert "unj@5" in out
    assert "diagnostic" in out


def test_bootstrap_requires_project_even_in_dry_run(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["bootstrap", "--email", "a@b.c", "--path", str(tmp_path)])
    assert exc_info.value.code == 2


def test_bootstrap_requires_project_with_apply(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(
            ["bootstrap", "--email", "a@b.c", "--path", str(tmp_path), "--apply"]
        )
    assert exc_info.value.code == 2


async def test_bootstrap_unknown_email_exits_1(tmp_path, capsys):
    container, _ = build_test_container()

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "ghost@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
            ]
        ),
        container,
    )

    assert code == 1
    assert "does not exist" in capsys.readouterr().err


async def test_bootstrap_nonexistent_path_exits_1(tmp_path, capsys):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "path@example.com"]), container)
    capsys.readouterr()
    missing = tmp_path / "does-not-exist"

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "path@example.com",
                "--project",
                "demo",
                "--path",
                str(missing),
            ]
        ),
        container,
    )

    assert code == 1
    assert "not a directory" in capsys.readouterr().err


async def test_bootstrap_no_candidates_prints_message_and_exits_0(tmp_path, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "empty@example.com"]), container)
    capsys.readouterr()

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "empty@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
            ]
        ),
        container,
    )

    assert code == 0
    assert capsys.readouterr().out == "no candidates found\n"
    assert fakes["memories"].rows == {}


async def test_bootstrap_dry_run_succeeds_without_llm(tmp_path, capsys):
    """Scenario: Sin LLM -- dry-run scan produces candidates with Ollama down."""
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(available=False))
    await _run(parse(["create-user", "--email", "nollm@example.com"]), container)
    capsys.readouterr()
    _write_bootstrap_fixture(tmp_path)

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "nollm@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
            ]
        ),
        container,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "pyproject.toml" in out
    assert fakes["memories"].rows == {}


def _write_bootstrap_fixture(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11"\ndependencies = ["fastapi"]\n'
    )
    (tmp_path / "AGENTS.md").write_text("# Agents\n")


async def test_bootstrap_dry_run_creates_zero_memories_and_exits_0(tmp_path, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "dry@example.com"]), container)
    capsys.readouterr()
    _write_bootstrap_fixture(tmp_path)

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "dry@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
            ]
        ),
        container,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "pyproject.toml" in out
    assert "AGENTS.md" in out
    assert fakes["memories"].rows == {}


async def test_bootstrap_apply_persists_via_remember_batch(tmp_path, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "apply@example.com"]), container)
    capsys.readouterr()
    user = next(iter(fakes["users"].users.values()))
    _write_bootstrap_fixture(tmp_path)

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "apply@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
                "--apply",
            ]
        ),
        container,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "created:" in out
    stored = [m for m in fakes["memories"].rows.values() if m.user_id == user.id]
    assert len(stored) >= 2
    assert all(m.source_type == "bootstrap" for m in stored)
    assert all(m.project == "demo" for m in stored)
    assert {m.source_ref for m in stored} == {"pyproject.toml", "AGENTS.md"}


async def test_bootstrap_apply_reports_similar_pre_existing_memory(tmp_path, capsys):
    runtime_content = "This project's Python runtime requirement is `>=3.11` (from pyproject.toml)."
    shared = [1.0] + [0.0] * 7
    near = [0.999, 0.0447] + [0.0] * 6
    embedder = ScriptedEmbeddingClient(
        vectors={
            "Existing note about Python 3.11 support": shared,
            runtime_content: near,
        }
    )
    container, fakes = build_test_container(embedder=embedder)
    await _run(parse(["create-user", "--email", "similar@example.com"]), container)
    capsys.readouterr()
    user = next(iter(fakes["users"].users.values()))
    await container.memory_service().remember(
        user.id,
        content="Existing note about Python 3.11 support",
        category="fact",
        project="demo",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "similar@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
                "--apply",
            ]
        ),
        container,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "similar:" in out


async def test_bootstrap_apply_second_pass_creates_no_duplicates(tmp_path, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "twice@example.com"]), container)
    capsys.readouterr()
    user = next(iter(fakes["users"].users.values()))
    _write_bootstrap_fixture(tmp_path)
    args = parse(
        [
            "bootstrap",
            "--email",
            "twice@example.com",
            "--project",
            "demo",
            "--path",
            str(tmp_path),
            "--apply",
        ]
    )

    assert await _run(args, container) == 0
    capsys.readouterr()
    first_count = len([m for m in fakes["memories"].rows.values() if m.user_id == user.id])

    assert await _run(args, container) == 0
    second_out = capsys.readouterr().out
    second_count = len([m for m in fakes["memories"].rows.values() if m.user_id == user.id])

    assert second_count == first_count
    assert "deduplicated:" in second_out
    assert "created:" not in second_out


async def test_bootstrap_apply_invisible_to_other_user(tmp_path, capsys):
    container, fakes = build_test_container()
    await _run(parse(["create-user", "--email", "owner@example.com"]), container)
    await _run(parse(["create-user", "--email", "other@example.com"]), container)
    capsys.readouterr()
    owner = next(u for u in fakes["users"].users.values() if u.email == "owner@example.com")
    other = next(u for u in fakes["users"].users.values() if u.email == "other@example.com")
    _write_bootstrap_fixture(tmp_path)

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "owner@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
                "--apply",
            ]
        ),
        container,
    )

    assert code == 0
    owner_rows = [m for m in fakes["memories"].rows.values() if m.user_id == owner.id]
    other_rows = [m for m in fakes["memories"].rows.values() if m.user_id == other.id]
    assert owner_rows
    assert other_rows == []


async def test_bootstrap_cap_truncation_reports_note_to_operator(tmp_path, capsys):
    container, _ = build_test_container()
    await _run(parse(["create-user", "--email", "cap@example.com"]), container)
    capsys.readouterr()
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

    code = await _run(
        parse(
            [
                "bootstrap",
                "--email",
                "cap@example.com",
                "--project",
                "demo",
                "--path",
                str(tmp_path),
            ]
        ),
        container,
    )

    assert code == 0
    err = capsys.readouterr().err
    assert "omitted" in err
    assert "cap is 10" in err
