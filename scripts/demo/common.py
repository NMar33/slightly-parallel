"""Shared scenario helpers: commits that touch files plausibly."""

from __future__ import annotations

from typing import Callable

import codegen
from engine import Repo

_counter = {"n": 0, "mig": {}}


def change(subject: str, *paths: str) -> Callable[[Repo], None]:
    """A change function for ``Chat.turn(commits=…)``: each path gets a
    plausible addition; ``-path`` deletes; ``mig:<name>`` adds an alembic
    migration under backend/alembic/versions; ``=path::text`` writes text."""

    def run(repo: Repo) -> None:
        for p in paths:
            _counter["n"] += 1
            n = _counter["n"]
            if p.startswith("-"):
                repo.remove(p[1:])
            elif p.startswith("mig:"):
                key = str(repo.path)
                k = _counter["mig"].get(key, 1)
                _counter["mig"][key] = k + 1
                rev, down = f"{k:04d}", f"{k - 1:04d}" if k > 1 else "None"
                name = codegen.snake(p[4:])[:40]
                repo.write(f"backend/alembic/versions/{rev}_{name}.py", codegen.migration(p[4:], rev, down))
            elif p.startswith("="):
                path, _, text = p[1:].partition("::")
                repo.write(path, text)
            else:
                # A change to a grown file also rewrites a few of its lines,
                # as real edits do: the diff then has deletions too.
                full = repo.path / p
                if full.exists() and n % 3 == 0:
                    lines = full.read_text(encoding="utf-8").split("\n")
                    if len(lines) > 30:
                        start = 6 + (n * 7) % (len(lines) - 14)
                        del lines[start:start + 3 + n % 4]
                        full.write_text("\n".join(lines), encoding="utf-8")
                repo.append(p, codegen.snippet(p, subject, n))

    return run


def C(off: float, subject: str, *paths: str):
    """One commit inside a turn: (minute offset, subject, change)."""
    return (off, subject, change(subject, *paths))
