"""Dump the FastAPI OpenAPI schema to a committed `backend/openapi.json`.

The frontend's `pnpm gen:api` reads this file to generate its typed client, so
the build never needs the backend running. The schema is built purely from the
route signatures — no network, DB, or AWS credentials required.

Run from the repo root or `backend/`:

    uv run python scripts/dump_openapi.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the `app` package importable when run as a plain script (the project is
# configured with `package = false`, so `app` isn't installed on the path).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import app  # noqa: E402

_OUT = _BACKEND_ROOT / "openapi.json"


def main() -> None:
    schema = app.openapi()
    _OUT.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    paths = ", ".join(sorted(schema.get("paths", {})))
    print(f"Wrote {_OUT} ({len(schema.get('paths', {}))} paths: {paths})")


if __name__ == "__main__":
    main()
