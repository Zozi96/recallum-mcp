from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from recallum.workflow_evaluation import load_scenarios, validate_runs
from scripts.agent_workflow_benchmark import (
    FIXTURES,
    MAX_REQUEST_BYTES,
    ProbeServer,
    main,
    run_once,
)

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "scripts" / "fake_workflow_agent.py"
SCENARIOS = ROOT / "scripts" / "agent_workflow_scenarios.json"


@pytest.fixture
def probe_server() -> Iterator[tuple[ProbeServer, str]]:
    probe = ProbeServer(FIXTURES["session-rotation-pivot"], "token")
    thread = threading.Thread(target=probe.serve_forever, daemon=True)
    thread.start()
    try:
        yield probe, f"http://127.0.0.1:{probe.server_address[1]}/mcp"
    finally:
        probe.shutdown()
        probe.server_close()
        thread.join(timeout=1)


def test_fake_agent_observation_records_pivot_and_objective_check() -> None:
    run = run_once(
        "session-rotation-pivot",
        "codex",
        "checkpoints",
        [sys.executable, str(FAKE)],
    )
    assert run["status"] == "complete"
    assert run["source"] == "observed"
    assert [event["tool"] for event in run["events"]] == ["context", "recall", "checks"]
    assert run["events"][-1]["applied_criterion_keys"] == [
        "criterion:preserve-session-ttl"
    ]
    assert all("query" not in event for event in run["events"])
    assert validate_runs({"version": "1", "runs": [run]}, load_scenarios(SCENARIOS))[0].run_id


@pytest.mark.parametrize(
    ("scenario", "criteria"),
    [
        ("covered-by-initial-context", ["criterion:use-hashed-keys"]),
        (
            "repeated-checkpoint-results",
            ["criterion:use-dokploy", "criterion:respect-release-window"],
        ),
        ("cold-start-pivot", ["criterion:use-feature-toggle"]),
    ],
)
def test_fake_agent_objective_checks_cover_each_fixture(
    scenario: str, criteria: list[str]
) -> None:
    run = run_once(scenario, "fake", "checkpoints", [sys.executable, str(FAKE)])
    assert run["status"] == "complete"
    assert run["events"][-1]["applied_criterion_keys"] == criteria


def test_unavailable_agent_is_incomplete_without_fabricated_memory_events() -> None:
    run = run_once(
        "covered-by-initial-context", "claude", "baseline", ["not-a-client"], timeout=0.1
    )
    assert run["status"] == "incomplete"
    assert run["events"] == []


def test_failed_launch_removes_the_temporary_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "scripts.agent_workflow_benchmark.tempfile.mkdtemp", lambda **_kwargs: str(workspace)
    )
    run = run_once("covered-by-initial-context", "codex", "baseline", ["not-a-client"])
    assert run["status"] == "incomplete"
    assert not workspace.exists()


def test_fixtures_cover_the_four_versioned_scenarios() -> None:
    assert set(FIXTURES) == {
        "session-rotation-pivot",
        "covered-by-initial-context",
        "repeated-checkpoint-results",
        "cold-start-pivot",
    }


def test_probe_negotiates_with_fastmcp_and_separates_initial_from_pivot_memory(
    probe_server: tuple[ProbeServer, str],
) -> None:
    probe, url = probe_server

    async def exercise():
        transport = StreamableHttpTransport(
            url=url, headers={"Authorization": "Bearer token"}
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            context = await client.call_tool("context", {"project": "synthetic"})
            recall = await client.call_tool(
                "recall", {"project": "synthetic", "query": "session-rotation-ttl"}
            )
            return tools, context, recall

    tools, context, recall = asyncio.run(exercise())
    assert {tool.name for tool in tools} == {"context", "recall"}
    assert context.structured_content["memory_keys"] == ["memory:api-auth"]
    assert recall.structured_content["memory_keys"] == ["memory:session-rotation-ttl"]
    assert "preserve the existing TTL" not in context.content[0].text
    assert "preserve the existing TTL" in recall.content[0].text
    assert [event["served_chars"] for event in probe.events] == [
        len(context.content[0].text),
        len(recall.content[0].text),
    ]


def test_probe_does_not_rewind_phase_when_context_is_called_after_pivot(
    probe_server: tuple[ProbeServer, str],
) -> None:
    probe, url = probe_server

    async def exercise():
        transport = StreamableHttpTransport(
            url=url, headers={"Authorization": "Bearer token"}
        )
        async with Client(transport) as client:
            await client.call_tool("context", {"project": "synthetic"})
            await client.call_tool(
                "recall", {"project": "synthetic", "query": "session-rotation-ttl"}
            )
            await client.call_tool("context", {"project": "synthetic"})

    asyncio.run(exercise())
    assert [event["phase"] for event in probe.events] == [
        "triage",
        "session-rotation",
        "session-rotation",
    ]
    assert [event["tool"] for event in probe.events] == [
        "context",
        "recall",
        "context",
    ]
    payload = {
        "version": "1",
        "runs": [
            {
                "run_id": "post-pivot-context",
                "source": "observed",
                "client": "grok-build",
                "policy": "checkpoints",
                "scenario": "session-rotation-pivot",
                "status": "complete",
                "events": probe.events,
            }
        ],
    }
    assert validate_runs(payload, load_scenarios(SCENARIOS))[0].run_id == "post-pivot-context"


def test_probe_rejects_bad_auth_and_bounded_or_nonobject_requests(
    probe_server: tuple[ProbeServer, str],
) -> None:
    probe, url = probe_server

    def rejected(
        body: bytes, token: str, status: int, content_length: int | None = None
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310
        assert error.value.code == status

    rejected(b"{}", "wrong", 401)
    rejected(b"[]", "token", 400)
    rejected(b"x", "token", 413, MAX_REQUEST_BYTES + 1)
    assert probe.events == []


def test_environment_is_minimal_unless_explicitly_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "env_agent.py"
    script.write_text(
        "import os; raise SystemExit(0 if 'BENCHMARK_SENTINEL' not in os.environ else 2)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_SENTINEL", "secret")
    run = run_once(
        "covered-by-initial-context", "codex", "baseline", [sys.executable, str(script)]
    )
    assert run["status"] == "complete"
    explicit = run_once(
        "covered-by-initial-context",
        "codex",
        "baseline",
        [sys.executable, str(script)],
        pass_env=("BENCHMARK_SENTINEL",),
    )
    assert explicit["status"] == "incomplete"


def test_incomplete_run_keeps_observed_cost_but_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BENCHMARK_PAUSE_AFTER_CONTEXT", "2")
    run = run_once(
        "session-rotation-pivot",
        "codex",
        "checkpoints",
        [sys.executable, str(FAKE)],
        timeout=0.5,
        pass_env=("BENCHMARK_PAUSE_AFTER_CONTEXT",),
    )
    assert run["status"] == "incomplete"
    assert [event["tool"] for event in run["events"]] == ["context"]
    assert run["events"][0]["served_chars"] > 0


def test_redundant_recall_is_observed_and_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHMARK_REDUNDANT", "1")
    run = run_once(
        "session-rotation-pivot",
        "codex",
        "checkpoints",
        [sys.executable, str(FAKE)],
        pass_env=("BENCHMARK_REDUNDANT",),
    )
    assert [event["tool"] for event in run["events"]].count("recall") == 2


def test_verifier_failure_and_absent_checkpoint_are_not_success(tmp_path: Path) -> None:
    script = tmp_path / "no_checkpoint.py"
    script.write_text("pass\n", encoding="utf-8")
    run = run_once(
        "session-rotation-pivot", "codex", "baseline", [sys.executable, str(script)]
    )
    assert run["status"] == "complete"
    assert [event["tool"] for event in run["events"]] == ["checks"]
    assert run["events"][-1]["applied_criterion_keys"] == []


def test_dry_run_emits_clean_omission_payload(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "1"
    assert payload["runs"] == []
    with pytest.raises(SystemExit):
        main(["--dry-run", "--", sys.executable, "not-run"])


def test_agent_output_cannot_corrupt_cli_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "noisy.py"
    script.write_text(
        "print('SECRET_STDOUT'); import sys; print('SECRET_STDERR', file=sys.stderr)\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--scenario",
                "session-rotation-pivot",
                "--client",
                "codex",
                "--policy",
                "checkpoints",
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["runs"][0]["status"] == "complete"
    assert "SECRET_" not in captured.out + captured.err


def test_exact_argv_placeholders_use_temporary_configs_and_workspace(tmp_path: Path) -> None:
    script = tmp_path / "inspect.py"
    record_path = tmp_path / "record.json"
    script.write_text(
        "import json, os, pathlib, sys\n"
        "record, prompt, prompt_file, workspace, mcp, grok, plugin, url_cfg, token_cfg = "
        "sys.argv[1:]\n"
        "mcp_data = json.loads(pathlib.Path(mcp).read_text())\n"
        "grok_text = pathlib.Path(grok).read_text()\n"
        "checks = [\n"
        " prompt == os.environ['RECALLUM_BENCHMARK_PROMPT'],\n"
        " pathlib.Path(prompt_file).read_text().strip() == prompt,\n"
        " pathlib.Path(workspace).resolve() == pathlib.Path.cwd().resolve(),\n"
        " mcp_data['mcpServers']['recallum']['url'] == os.environ['RECALLUM_BENCHMARK_URL'],\n"
        " mcp_data['mcpServers']['recallum']['headers']['Authorization'] == "
        "'Bearer ${RECALLUM_BENCHMARK_TOKEN}',\n"
        " os.environ['RECALLUM_BENCHMARK_TOKEN'] in grok_text,\n"
        " pathlib.Path(plugin).is_dir(),\n"
        " json.loads((pathlib.Path(plugin) / '.mcp.json').read_text())"
        "['mcpServers']['recallum']['url'] == os.environ['RECALLUM_BENCHMARK_URL'],\n"
        " os.environ['RECALLUM_BENCHMARK_TOKEN'] not in "
        "(pathlib.Path(plugin) / '.mcp.json').read_text(),\n"
        " os.environ['RECALLUM_BENCHMARK_URL'] in url_cfg,\n"
        " 'RECALLUM_BENCHMARK_TOKEN' in token_cfg,\n"
        "]\n"
        "pathlib.Path(record).write_text(json.dumps({'ok': all(checks), "
        "'workspace': workspace}))\n",
        encoding="utf-8",
    )
    run = run_once(
        "covered-by-initial-context",
        "codex",
        "baseline",
        [
            sys.executable,
            str(script),
            str(record_path),
            "{prompt}",
            "{prompt_file}",
            "{workspace}",
            "{mcp_config}",
            "{grok_config}",
            "{plugin_dir}",
            "{codex_mcp_url_config}",
            "{codex_mcp_token_config}",
        ],
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert run["status"] == "complete"
    assert record["ok"] is True
    assert not Path(record["workspace"]).exists()


def test_grok_build_child_sees_disposable_grok_home_with_probe_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_home = tmp_path / "real-grok-home"
    (real_home / "marketplaces" / "recallum-local").mkdir(parents=True)
    (real_home / "marketplaces" / "recallum-local" / "state").write_text(
        "plugin-state", encoding="utf-8"
    )
    (real_home / "config.toml").write_text("real-secret-config", encoding="utf-8")
    monkeypatch.setenv("GROK_HOME", str(real_home))
    record_path = tmp_path / "record.json"
    script = tmp_path / "inspect_grok.py"
    script.write_text(
        "import json, os, pathlib, sys\n"
        "record_path = sys.argv[1]\n"
        "home = pathlib.Path(os.environ['GROK_HOME'])\n"
        "config = (home / 'config.toml').read_text(encoding='utf-8')\n"
        "checks = [\n"
        " 'plugin-state' == (home / 'marketplaces' / 'recallum-local' / 'state').read_text(\n"
        "     encoding='utf-8'),\n"
        " os.environ['RECALLUM_BENCHMARK_URL'] in config,\n"
        " os.environ['RECALLUM_BENCHMARK_TOKEN'] in config,\n"
        " 'real-secret-config' not in config,\n"
        " home.parent.name.startswith('recallum-benchmark-'),\n"
        "]\n"
        "pathlib.Path(record_path).write_text(\n"
        "    json.dumps({'ok': all(checks), 'home': str(home)}), encoding='utf-8'\n"
        ")\n",
        encoding="utf-8",
    )
    run = run_once(
        "covered-by-initial-context",
        "grok-build",
        "baseline",
        [sys.executable, str(script), str(record_path)],
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert run["status"] == "complete"
    assert record["ok"] is True
    assert not Path(record["home"]).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups only")
def test_timeout_terminates_descendant_that_ignores_sigterm(tmp_path: Path) -> None:
    ready = tmp_path / "descendant-ready"
    marker = tmp_path / "descendant-alive"
    child = (
        "import pathlib,signal,time;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(ready)!r}).write_text('ready');"
        "time.sleep(1);"
        f"pathlib.Path({str(marker)!r}).write_text('alive')"
    )
    script = tmp_path / "spawn.py"
    script.write_text(
        "import pathlib,subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        f"ready = pathlib.Path({str(ready)!r})\n"
        "for _ in range(100):\n"
        "    if ready.exists():\n"
        "        break\n"
        "    time.sleep(0.01)\n"
        "time.sleep(2)\n",
        encoding="utf-8",
    )
    run = run_once(
        "covered-by-initial-context",
        "codex",
        "baseline",
        [sys.executable, str(script)],
        timeout=0.5,
    )
    time.sleep(0.8)
    assert run["status"] == "incomplete"
    assert ready.exists()
    assert not marker.exists()
