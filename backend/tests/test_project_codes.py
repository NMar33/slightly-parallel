"""One reading of a comma-separated project list (tk_d1d25a4d step 2).

A task's ``projects`` and, from step 2, an agent's are read in Python, in
SQL and in TypeScript. testdata/project_codes/table.json holds the odd
strings once; each reader is held to it (the TypeScript one in
frontend/src/lib/projectCodes.test.ts)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from backend.entitylib import project_code_param, project_codes, project_codes_sql, project_lists

TABLE = json.loads((Path(__file__).resolve().parents[2] / "testdata" / "project_codes" / "table.json")
                   .read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", TABLE, ids=lambda c: repr(c["value"]))
def test_python_reads_the_table(case):
    assert project_codes(case["value"]) == case["codes"]
    for code, want in case["has"].items():
        assert project_lists(case["value"], code) is want, (case["value"], code)


def test_sql_agrees_with_python_on_every_row():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t (i INTEGER, projects VARCHAR)")
    rows = [(i, c["value"]) for i, c in enumerate(TABLE) if not isinstance(c["value"], list)]
    con.executemany("INSERT INTO t VALUES (?, ?)", rows)
    seen = 0
    for i, case in enumerate(TABLE):
        if isinstance(case["value"], list):
            continue
        for code, want in case["has"].items():
            got = con.execute(
                f"SELECT count(*) FROM t WHERE i = ? AND {project_codes_sql('projects')}",
                (i, project_code_param(code)),
            ).fetchone()
            assert got is not None
            assert bool(got[0]) is want, (case["value"], code)
            seen += 1
    assert seen > 40


def test_the_calendar_and_the_deck_read_through_it():
    """No second copy of the reading: calendar and sprint_deck call it."""
    root = Path(__file__).resolve().parents[1] / "backend" / "routers"
    cal = (root / "calendar.py").read_text(encoding="utf-8")
    deck = (root / "sprint_deck.py").read_text(encoding="utf-8")
    assert "def _lists_code" not in cal
    assert "LIKE ? ESCAPE" not in cal
    assert "project_lists" in cal and "project_codes_sql" in cal
    assert 'code in str(r.get("projects") or "").split(",")' not in deck and "project_lists" in deck
