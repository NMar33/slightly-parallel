"""Refresh the built-in skills in the repository's shipped fixtures.

Run explicitly from the repository root after changing a built-in skill
or its contract part:

    backend/.venv/bin/python scripts/refresh_builtin_skill_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "backend"))

    from backend.csvio import read_rows
    from backend.db import FIXTURES, ViewStore
    from backend.docs_md import resolve_under
    from backend.skilllib import BUILTIN_SOURCE, seed_builtin_skills

    from backend import frontmatter, keeplib

    store = ViewStore(FIXTURES)

    def check_versions() -> None:
        problems = []
        for row in read_rows(FIXTURES / "skills.csv"):
            if row.get("source") != BUILTIN_SOURCE:
                continue
            kid = row["id"]
            versions = keeplib.read_versions(store, kid)
            history = str(versions[-1].n) if versions else "missing"
            csv = row.get("versions_n") or "missing"
            detail = resolve_under(FIXTURES, row.get("md_ref", ""))
            meta, _ = frontmatter.meta(detail.read_text(encoding="utf-8")) if detail and detail.is_file() else (None, "")
            card = str((meta or {}).get("versions_n") or "missing")
            if not versions or csv != history or card != history:
                problems.append(f"{kid}: history={history}, skills.csv={csv}, card={card}")
        if problems:
            raise SystemExit("Built-in fixture skill versions disagree:\n" + "\n".join(problems))

    check_versions()
    updated = seed_builtin_skills(store)
    check_versions()
    print(f"Built-in fixture skills updated: {', '.join(updated) or 'none'}")


if __name__ == "__main__":
    main()
