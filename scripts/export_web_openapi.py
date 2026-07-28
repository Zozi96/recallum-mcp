"""Export or verify the versioned browser API contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from starlette.routing import Mount

from recallum.app import create_app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "openapi" / "web-v1.json"


def rendered_contract() -> str:
    app = create_app()
    web = next(
        route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/v1"
    )
    return json.dumps(web.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_contract()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != rendered:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; regenerate it")
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
