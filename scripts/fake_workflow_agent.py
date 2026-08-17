#!/usr/bin/env python3
"""Tiny offline agent used by benchmark integration tests."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path


def call(
    url: str, token: str, name: str, method: str = "tools/call", **arguments: object
) -> dict:
    params = {"name": name, "arguments": arguments} if method == "tools/call" else {}
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
        return json.loads(response.read())


def update_config(workspace: Path, name: str, **values: object) -> None:
    path = workspace / name
    config = json.loads(path.read_text(encoding="utf-8"))
    config.update(values)
    path.write_text(json.dumps(config), encoding="utf-8")


def main() -> int:
    url = os.environ["RECALLUM_BENCHMARK_URL"]
    token = os.environ["RECALLUM_BENCHMARK_TOKEN"]
    workspace = Path(os.environ["RECALLUM_BENCHMARK_WORKSPACE"])
    prompt = os.environ["RECALLUM_BENCHMARK_PROMPT"]
    call(url, token, "", method="initialize")
    call(url, token, "", method="tools/list")
    call(url, token, "context", project=os.environ["RECALLUM_BENCHMARK_PROJECT"])
    if pause := os.environ.get("BENCHMARK_PAUSE_AFTER_CONTEXT"):
        time.sleep(float(pause))
    redundant = os.environ.get("BENCHMARK_REDUNDANT") == "1"
    if "session-rotation" in prompt:
        call(
            url,
            token,
            "recall",
            project=os.environ["RECALLUM_BENCHMARK_PROJECT"],
            query="session-rotation-ttl",
        )
        if redundant:
            call(
                url,
                token,
                "recall",
                project=os.environ["RECALLUM_BENCHMARK_PROJECT"],
                query="session-rotation-ttl",
            )
        update_config(workspace, "session_config.json", preserve_ttl=True)
    elif "release-window" in prompt:
        call(
            url,
            token,
            "recall",
            project=os.environ["RECALLUM_BENCHMARK_PROJECT"],
            query="release-window",
        )
        update_config(
            workspace,
            "deploy_config.json",
            provider="dokploy",
            window="Sunday 02:00 UTC",
        )
    elif "feature-toggle" in prompt:
        call(
            url,
            token,
            "recall",
            project=os.environ["RECALLUM_BENCHMARK_PROJECT"],
            query="feature-toggle",
        )
        update_config(workspace, "feature_config.json", enabled=True)
    else:
        update_config(workspace, "auth_config.json", key_storage="hashed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
