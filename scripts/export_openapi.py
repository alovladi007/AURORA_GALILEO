#!/usr/bin/env python3
"""Export the API gateway's OpenAPI specification to docs/api/openapi.json.

The spec is the API contract of record (MASTER_BUILD_PROMPT_18_MONTHS.md
Phase 2 W2.4): the UI client and the contract tests are checked against
it, which prevents the endpoint-name-drift bug class permanently.

Usage: python3 scripts/export_openapi.py
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    os.environ.setdefault("AUTH_MODE", "optional")
    sys.path.insert(0, str(REPO_ROOT / "services/api-gateway/src"))
    sys.path.insert(
        0, str(REPO_ROOT / "services/api-gateway/src/gen/python/proto")
    )

    from main import app  # noqa: E402

    spec = app.openapi()
    out = REPO_ROOT / "docs" / "api" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
