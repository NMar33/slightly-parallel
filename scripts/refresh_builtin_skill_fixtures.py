#!/usr/bin/env python3
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

    from backend.db import FIXTURES, ViewStore
    from backend.skilllib import seed_builtin_skills

    updated = seed_builtin_skills(ViewStore(FIXTURES))
    print(f"Built-in fixture skills updated: {', '.join(updated) or 'none'}")


if __name__ == "__main__":
    main()
