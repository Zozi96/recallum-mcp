#!/usr/bin/env bash
# Run pytest for a required CI lane and fail if nothing executed or any case skipped.
set -euo pipefail

report="$(mktemp /tmp/recallum-pytest.XXXXXX.xml)"
cleanup() { rm -f "$report"; }
trap cleanup EXIT

uv run pytest "$@" --junitxml="$report"
python3 - "$report" <<'PY'
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
tests = skipped = failures = errors = 0
for suite in suites:
    tests += int(suite.attrib.get("tests", 0))
    skipped += int(suite.attrib.get("skipped", 0))
    failures += int(suite.attrib.get("failures", 0))
    errors += int(suite.attrib.get("errors", 0))
passed = tests - skipped - failures - errors
if tests == 0 or skipped > 0 or passed < 1:
    print(
        f"required suite incomplete: tests={tests} skipped={skipped} "
        f"failures={failures} errors={errors} passed={passed}",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(f"required suite ok: passed={passed} tests={tests}")
PY
