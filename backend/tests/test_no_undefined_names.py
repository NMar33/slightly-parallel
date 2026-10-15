"""No name used that is never defined, and no function that hides another.

Both shipped once: a query built from a list a refactor never defined (the
sprints page answered 500), and a variable named after the function it then
called (the sprint dossier). pyflakes sees both without running a line.
Unused imports and the like are left to taste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
SERIOUS = ("undefined name", "redefinition of unused", "used before assignment", "shadowed by loop variable")


def test_no_undefined_or_shadowed_names() -> None:
    api = pytest.importorskip("pyflakes.api")
    reporter_mod = pytest.importorskip("pyflakes.reporter")
    import io

    out = io.StringIO()
    reporter = reporter_mod.Reporter(out, out)
    for folder in (BACKEND, HOOKS):
        for path in sorted(folder.rglob("*.py")):
            api.checkPath(str(path), reporter)
    found = [ln for ln in out.getvalue().splitlines() if any(s in ln for s in SERIOUS)]
    assert not found, "\n".join(found)
