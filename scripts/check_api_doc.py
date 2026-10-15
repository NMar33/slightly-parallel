#!/usr/bin/env python3
"""Check docs/api.md against the routes the server actually publishes.

Two checks, both shape-normalised (``{anything}`` → ``{}``):

- **missing** — a published route the document never names.
- **stale**   — a path the document names that the server does not publish.

The spec comes from the running server (``GET /openapi.json`` on
``http://127.0.0.1:8123``) when it matches the working tree, and from the
working tree itself otherwise — a long-running server can be behind the
code. Run it from the repository root::

    backend/.venv/bin/python scripts/check_api_doc.py

The last line of docs/api.md records the result of the last run.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "api.md"
LIVE = "http://127.0.0.1:8123/openapi.json"


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


def _live() -> set[str] | None:
    try:
        with urllib.request.urlopen(LIVE, timeout=5) as r:
            return set(json.load(r)["paths"])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def _tree() -> set[str] | None:
    sys.path.insert(0, str(REPO / "backend"))
    try:
        from backend.server import create_app  # type: ignore
    except Exception:
        return None
    app = create_app(data_root=Path(tempfile.mkdtemp()))
    return set(app.openapi()["paths"])


def main() -> int:
    live, tree = _live(), _tree()
    paths = tree or live
    if paths is None:
        print("no spec: the server is down and the tree would not import")
        return 2
    source = "the working tree" if tree else "the running server"
    if live is not None and tree is not None and live != tree:
        behind = sorted(_norm(p) for p in tree - live)
        print(f"note: the server on :8123 is behind the tree — {behind}")

    real = {_norm(p) for p in paths}
    doc = DOC.read_text(encoding="utf-8")
    named = {_norm(p) for p in re.findall(r"/api/[A-Za-z0-9_{}:/-]+", doc)}
    named = {p for p in named if not p.endswith("/")}

    missing = sorted(real - named)
    stale = sorted(named - real)
    print(
        f"Checked against /openapi.json ({source}) on {date.today().isoformat()}: "
        f"{len(real)} routes, {len(missing)} missing, {len(stale)} stale"
    )
    for p in missing:
        print("  missing:", p)
    for p in stale:
        print("  stale:  ", p)
    return 1 if (missing or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
