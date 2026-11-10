"""A list or an object sent for a text column is refused on create, in every
lens, and nothing is written. Before, ``{"source": ["chat"]}`` was stored as
the text ``['chat']`` (round 5: the agent-shaped writes found it in 50 columns
of 13 lenses)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def client(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


@pytest.mark.parametrize("base,body", [
    ("decisions", {"decision": "chose sqlite", "source": ["chat"]}),
    ("problems", {"problem": "the login times out", "severity": {"level": "high"}}),
    ("ideas", {"title": ["an idea"]}),
    ("snippets", {"label": "build", "command": ["npm", "run", "build"]}),
])
def test_a_list_for_a_text_column_is_refused_and_nothing_written(client, base, body) -> None:
    c, root = client
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    r = c.post(f"/api/{base}", json={"project": "alpha", "created_date": "2611-11", "created_time": "10:00", **body})
    assert r.status_code == 422, r.text
    assert "is text, not a list or an object" in r.json()["detail"]
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                   and not p.relative_to(root).as_posix().startswith("logs/"))
    assert [p for p in after if p not in before] == []


def test_a_task_still_takes_its_projects_as_a_list(client) -> None:
    c, _ = client
    r = c.post("/api/tasks", json={"project": "alpha", "created_date": "2611-11", "created_time": "10:00",
                                   "title": "shared", "status": "todo", "projects": ["alpha"]})
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("base,field,value", [("problems", "status", ["open"]), ("decisions", "weight", ["major"])])
def test_an_allowed_value_in_a_list_is_refused_by_its_shape(client, base, field, value) -> None:
    """``status: ["open"]`` was refused as "['open'] is not a known value —
    use one of: open, resolved": the refused value named as allowed."""
    c, _ = client
    head = {"problems": "problem", "decisions": "decision"}[base]
    made = c.post(f"/api/{base}", json={"project": "alpha", "created_date": "2611-11", "created_time": "10:00",
                                        head: "a first line"})
    assert made.status_code in (200, 201), made.text
    eid = made.json()["metadata"]["id"]
    r = c.post(f"/api/{base}/{eid}/update", json={field: value})
    assert r.status_code == 422 and "is one text value, not list" in r.json()["detail"], r.text
