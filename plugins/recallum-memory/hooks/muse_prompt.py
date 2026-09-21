#!/usr/bin/env python3
"""Muse Code UserPromptSubmit entrypoint for the Recallum hook.

Muse Code requires every hook capability to declare a unique source script,
so SessionStart and UserPromptSubmit cannot share ``recallum_hook.py`` as
their command source even with different arguments. This wrapper is the
UserPromptSubmit source; it marks the Muse client and delegates to the
shared implementation. Must stay compatible with Python 3.9.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    os.environ.setdefault("MUSE_PLUGIN_ROOT", os.path.dirname(here))
    target = os.path.join(here, "recallum_hook.py")
    completed = subprocess.run(
        [sys.executable, target, "prompt"],
        stdin=sys.stdin,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
