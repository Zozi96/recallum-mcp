"""Entrypoint contract: explicit commands pass through; bare runs migrate then serve."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "deploy" / "entrypoint.sh"


def _uv_stub(tmp_path: Path) -> dict[str, str]:
    """A `uv` on PATH that prints its argv and exits 0, so nothing real launches."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "uv"
    stub.write_text('#!/bin/sh\necho "uv-stub: $@"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return env


def test_explicit_command_is_exec_d_without_migrating(tmp_path):
    env = _uv_stub(tmp_path)
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "/bin/echo", "one-shot-ok"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout == "one-shot-ok\n"
    # The migrate/serve path never ran: no `uv` invocation at all.
    assert "uv-stub" not in result.stdout
    assert "uv-stub" not in result.stderr


def test_no_args_runs_migrations_then_serves(tmp_path):
    env = _uv_stub(tmp_path)
    result = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        env={**env, "RECALLUM_MIGRATION_RETRY_SECONDS": "0"},
    )
    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if line.startswith("uv-stub:")]
    assert lines == [
        "uv-stub: run --no-sync alembic upgrade head",
        "uv-stub: run --no-sync granian --interface asgi --factory"
        " --host 0.0.0.0 --port 8000 --workers 1 recallum.app:create_app",
    ]


def test_skip_migrations_env_still_serves(tmp_path):
    env = _uv_stub(tmp_path)
    result = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        env={**env, "RECALLUM_SKIP_MIGRATIONS": "1"},
    )
    assert result.returncode == 0
    assert "uv-stub: run --no-sync granian" in result.stdout
    assert "alembic" not in result.stdout
    assert "skipping alembic" in result.stderr


def test_workers_other_than_one_fails_closed(tmp_path):
    env = _uv_stub(tmp_path)
    result = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        env={
            **env,
            "RECALLUM_SKIP_MIGRATIONS": "1",
            "RECALLUM__RUNTIME__WORKERS": "2",
        },
    )
    assert result.returncode == 1
    assert "WORKERS=1" in result.stderr
    assert "uv-stub" not in result.stdout
