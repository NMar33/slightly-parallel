"""Task levels decide where an agent's tasks may go (tk_d1d25a4d step 3,
note nt_258a7ed7 §3 «Levels»).

A table: level 1–3 × the agent's own task / a task on the operator's #task ×
home / member / non-member project × named in braces or not. A non-member is
refused by the gate at every level; level 1 takes the home only, unless the
operator named the project in braces; levels 2 and 3 take any member project.
Every refusal writes nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp
from backend.server import create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}
LEVEL_ONE = (f"agent {A} may create tasks only in its home ALPHA (level 1). "
             "Name the project in braces, or the operator raises the level on the agent card")
NOT_MEMBER = (f"agent {A} is not a member of GAMMA; its projects: ALPHA, BETA. "
              "The operator adds it on the agent card")
WHERE = {"home": "ALPHA", "member": "BETA", "non-member": "GAMMA"}


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def expected(level: int, where: str, named: bool) -> tuple[int, str]:
    if where == "non-member":
        return 403, NOT_MEMBER
    if level == 1 and where == "member" and not named:
        return 403, LEVEL_ONE
    return 201, ""


def message(whose: str, where: str, named: bool) -> str:
    if whose == "own":
        return "look into the login"
    return "#task " + (f"{{{WHERE[where]}}} " if named else "") + "check the login timeout"


@pytest.fixture()
def world(data_root: Path):
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok")])
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
        yield c, data_root


CASES = [(level, whose, where, named)
         for level in (1, 2, 3) for whose in ("own", "operator") for where in WHERE
         for named in (False, True) if not (named and whose == "own")]


@pytest.mark.parametrize("level,whose,where,named", CASES)
def test_the_level_table(world, level: int, whose: str, where: str, named: bool) -> None:
    c, root = world
    if level != 2:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": level}).status_code == 200
    make_chat(root, "ALPHA", A, [("2026-11-20T10:00:00", "start", "ok"),
                                  ("2026-11-20T10:05:00", message(whose, where, named), "on it")])
    c.app.state.store.rebuild()
    before = tree(root)
    r = c.post("/api/tasks", json={"agent_id": A, "project": WHERE[where], "created_date": "2611-20",
                                   "created_time": "10:06", "title": "Check the login timeout",
                                   "tags": "ag_bug"}, headers=VIA)
    status, line = expected(level, where, named)
    assert r.status_code == status, (level, whose, where, named, r.text)
    if status == 201:
        assert r.json()["metadata"]["project"] == WHERE[where]
    else:
        assert r.json()["detail"] == line
        assert tree(root) == before


def test_level_one_refuses_a_member_code_in_projects(world) -> None:
    c, root = world
    assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": 1}).status_code == 200
    before = tree(root)
    r = c.post("/api/tasks", json={"agent_id": A, "project": "ALPHA", "projects": "ALPHA,BETA",
                                   "created_date": "2611-20", "created_time": "10:06",
                                   "title": "x", "tags": "ag_bug"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, LEVEL_ONE)
    assert tree(root) == before
