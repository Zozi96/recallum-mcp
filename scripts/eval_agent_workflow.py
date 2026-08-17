#!/usr/bin/env python3
"""Score bounded workflow traces without an LLM or running server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SCENARIOS = ROOT / "scripts" / "agent_workflow_scenarios.json"
DEFAULT_RUNS = ROOT / "scripts" / "agent_workflow_runs.json"


def main() -> int:
    from recallum.workflow_evaluation import (
        compare_policies,
        load_matrix,
        load_runs,
        load_scenarios,
        matrix_report,
        render_comparison,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument(
        "--matrix",
        type=Path,
        help=(
            "versioned benchmark matrix; reports every declared client/policy cell, "
            "marking unconfigured or all-incomplete cells as gaps"
        ),
    )
    args = parser.parse_args()
    scenarios = load_scenarios(args.scenarios)
    runs = load_runs(args.runs, scenarios)
    if args.matrix:
        matrix = load_matrix(args.matrix)
        report = matrix_report(scenarios, runs, matrix)
    else:
        report = compare_policies(scenarios, runs)
    print(render_comparison(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
