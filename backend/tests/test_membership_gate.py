"""An agent writes in its member projects only (tk_d1d25a4d step 3, note
nt_258a7ed7 §2; the operator's answer 1, dc_f59e2918).

Fixture: chat A from ALPHA joins BETA; GAMMA is no project of A's. A create
naming GAMMA (``project`` or a code in ``projects``) is refused at the gate
with one line, through the MCP and over plain HTTP alike; a write on a
GAMMA task by its id is refused, whatever its kind; the operator is never
refused. Each refusal leaves the data folder as it was (docs/testing.md #9).
"""

from __future__ import annotations

import hashlib
import itertools
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import memberships, mcp
from backend import server as _server
from backend.server import _MCP_WRITE_PATHS, MCP_WITHOUT_AGENT, create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
STRANGER = "cc-ffff0000"   # no chat anywhere
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}
GAMMA_TASK = "tk_gamma_one"
PROJECT_SHAPE = "project is one project code, as text"
PROJECTS_SHAPE = "projects is project codes: comma-separated text or a list of texts"
UNINDEXED = ("agent {agent} is not a chat Slightly Parallel has recorded; nothing was written. "
             "Tell the operator")


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def not_member(project: str) -> str:
    return (f"agent {A} is not a member of {project}; its projects: ALPHA, BETA. "
            "The operator adds it on the agent card")


def not_member_task(project: str) -> str:
    return (f"agent {A} is not a member of {project}; this task is {project}'s. "
            "The operator adds it on the agent card")


@pytest.fixture()
def root(data_root: Path) -> Path:
    make_chat(data_root, "ALPHA", A, [("2026-11-20T10:00:00", "work", "ok")])
    (data_root / "projects" / "GAMMA").mkdir(parents=True)
    with (data_root / "tasks.csv").open("a", encoding="utf-8") as fh:
        fh.write(f"{GAMMA_TASK},2611-20,10:00,GAMMA,operator,Gamma task,todo,med,"
                 ",,,,10,,,,,GAMMA,,,,,,,,,,,\n")
    return data_root


@pytest.fixture()
def op(root: Path):
    with TestClient(create_app(data_root=root, watch=False)) as c:
        r = c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"})
        assert r.status_code == 200, r.text
        yield c


def decision(project: str, agent: str = A) -> dict:
    return {"agent_id": agent, "project": project, "created_date": "2611-20", "created_time": "10:00",
            "decision": "chose sqlite", "why": "small"}


# -- the helper ---------------------------------------------------------------

def test_may_write_answers_home_member_and_refuses_the_rest(op: TestClient) -> None:
    store = op.app.state.store
    assert memberships.may_write(store, A, "ALPHA") == (True, "")
    assert memberships.may_write(store, A, "BETA") == (True, "")
    assert memberships.may_write(store, A, "GAMMA") == (False, not_member("GAMMA"))
    ok, line = memberships.may_write(store, STRANGER, "ALPHA")
    assert not ok and line == UNINDEXED.format(agent=STRANGER)


def test_whoami_names_home_members_and_level(op: TestClient, root: Path, tmp_path: Path) -> None:
    import importlib.util
    hooks = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "claude-code-capture.py"
    spec = importlib.util.spec_from_file_location("cc_capture_gate", hooks)
    assert spec and spec.loader
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    work = tmp_path / "work"
    work.mkdir()
    cc.write_breadcrumb(str(root), "ALPHA", "sess-gate", str(work))
    who = op.get("/api/whoami", params={"cwd": str(work)}).json()
    agent = who["agent_id"]
    # A chat of its own with the joined project: whoami reads the ledger.
    make_chat(root, "ALPHA", agent, [("2026-11-20T10:00:00", "work", "ok")])
    op.app.state.store.rebuild()
    assert op.post(f"/api/agents/{agent}/membership", json={"op": "join", "project": "BETA"}).status_code == 200
    who = op.get("/api/whoami", params={"cwd": str(work)}).json()
    assert (who["project"], who["home"], who["members"], who["level"]) == ("ALPHA", "ALPHA", ["ALPHA", "BETA"], 2)


def test_a_code_spelled_another_case_is_the_same_folder_where_case_folds(op: TestClient, monkeypatch) -> None:
    # Windows and macOS: projects/alpha is the folder projects/ALPHA (CI found
    # it, test_audit_round3: a chat written under «alpha» filed in «ALPHA»).
    store = op.app.state.store
    if not memberships.folds_case(store.data_root):
        assert memberships.may_write(store, A, "alpha")[0] is False    # Linux: two folders
    monkeypatch.setattr(memberships, "folds_case", lambda root: True)
    assert memberships.may_write(store, A, "alpha") == (True, "")
    assert memberships.may_write_row(store, A, "beta", "task") == (True, "")
    assert memberships.may_write(store, A, "gamma")[0] is False


def test_folds_case_reads_the_file_system(op: TestClient, tmp_path: Path) -> None:
    import os
    (tmp_path / "projects").mkdir()
    probe = tmp_path / "Probe"
    probe.mkdir()
    folds = (tmp_path / "PROBE").exists() and os.path.samefile(probe, tmp_path / "PROBE")
    assert memberships.folds_case(tmp_path) is folds


# -- creates, at the gate ----------------------------------------------------

@pytest.mark.parametrize("via", [VIA, {}], ids=["mcp", "http-mcp_only-off"])
def test_a_create_in_a_member_project_passes_and_elsewhere_is_refused(op: TestClient, root: Path, via) -> None:
    for code in ("ALPHA", "BETA"):
        r = op.post("/api/decisions", json=decision(code), headers=via)
        assert r.status_code == 201, r.text
        assert r.json()["metadata"]["project"] == code
    before = tree(root)
    r = op.post("/api/decisions", json=decision("GAMMA"), headers=via)
    assert (r.status_code, r.json()["detail"]) == (403, not_member("GAMMA"))
    assert tree(root) == before


def test_the_gate_holds_with_mcp_only_on_too(op: TestClient, root: Path, monkeypatch) -> None:
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    before = tree(root)
    r = op.post("/api/decisions", json=decision("GAMMA"), headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member("GAMMA"))
    assert tree(root) == before


@pytest.mark.parametrize("projects", ["ALPHA,GAMMA", ["ALPHA", "GAMMA"], " GAMMA "])
def test_a_foreign_code_in_projects_is_refused(op: TestClient, root: Path, projects) -> None:
    before = tree(root)
    r = op.post("/api/tasks", json={"agent_id": A, "project": "ALPHA", "projects": projects,
                                    "created_date": "2611-20", "created_time": "10:00",
                                    "title": "x", "tags": "ag_bug"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member("GAMMA"))
    assert tree(root) == before


def test_an_agent_nobody_recorded_is_refused(op: TestClient, root: Path) -> None:
    before = tree(root)
    r = op.post("/api/decisions", json=decision("ALPHA", STRANGER), headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, UNINDEXED.format(agent=STRANGER))
    assert tree(root) == before


@pytest.mark.parametrize("body,words", [
    ({"project": ["ALPHA"]}, PROJECT_SHAPE),
    ({"project": {"code": "ALPHA"}}, PROJECT_SHAPE),
    ({"project": 5}, PROJECT_SHAPE),
    ({"project": "ALPHA", "projects": 5}, PROJECTS_SHAPE),
    ({"project": "ALPHA", "projects": ["ALPHA", 5]}, PROJECTS_SHAPE),
    ({"project": "ALPHA", "projects": {"a": 1}}, PROJECTS_SHAPE),
])
def test_the_right_value_in_the_wrong_shape(op: TestClient, root: Path, body, words) -> None:
    before = tree(root)
    r = op.post("/api/decisions", json={**decision("ALPHA"), **body}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (422, words)
    assert tree(root) == before


def _samples(pattern: str) -> list[str]:
    """Concrete paths for one gate pattern: each alternative of each group,
    an id where the pattern takes one."""
    pattern = pattern.replace("[^/]+", "zz_none")
    groups = re.findall(r"\(([^()]*)\)", pattern)
    out = []
    for pick in itertools.product(*(g.split("|") for g in groups)):
        path = pattern
        for g, p in zip(groups, pick):
            path = path.replace(f"({g})", p, 1)
        out.append(path)
    return out


WRITE_PATHS = sorted({p for pat in _MCP_WRITE_PATHS for p in _samples(pat)} - MCP_WITHOUT_AGENT)


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_every_mcp_write_path_checks_the_project_it_names(op: TestClient, root: Path, path: str) -> None:
    before = tree(root)
    r = op.post(path, json={"agent_id": A, "project": "GAMMA"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member("GAMMA")), path
    assert tree(root) == before


@pytest.mark.parametrize("path", sorted({p.replace("zz_none", GAMMA_TASK) for p in WRITE_PATHS
                                         if p.startswith("/api/tasks/zz_none/")}))
def test_every_write_on_a_task_by_id_checks_the_tasks_project(op: TestClient, root: Path, path: str) -> None:
    before = tree(root)
    r = op.post(path, json={"agent_id": A}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA")), path
    assert tree(root) == before


# -- agents' updates on tasks (answer 1) --------------------------------------

UPDATES = {
    "status": ("update", {"status": "doing"}),
    "tags": ("update", {"tags": "ag_bug"}),
    "comment": ("update", {"comment": "seen it"}),
    "report": ("report", {"text": "done it", "outcome": "done"}),
    "evidence": ("evidence", {"items": [{"kind": "note", "text": "ran it"}]}),
    "story": ("story", {"request_id": "sr_none", "body": "x"}),
    "commits": ("commits", {"shas": ["abc1234"]}),
    "topic": ("topic", {"entrypoint_id": ""}),
}


@pytest.mark.parametrize("kind", sorted(UPDATES))
def test_an_agents_update_on_a_non_member_task_is_refused(op: TestClient, root: Path, kind: str) -> None:
    verb, body = UPDATES[kind]
    before = tree(root)
    r = op.post(f"/api/tasks/{GAMMA_TASK}/{verb}", json={"agent_id": A, **body}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA")), kind
    assert tree(root) == before


@pytest.mark.parametrize("kind", sorted(UPDATES))
@pytest.mark.parametrize("task", ["tk_alpha_auth", "tk_beta_x"])
def test_an_agents_update_on_a_member_task_passes_the_gate(op: TestClient, kind: str, task: str) -> None:
    verb, body = UPDATES[kind]
    r = op.post(f"/api/tasks/{task}/{verb}", json={"agent_id": A, **body}, headers=VIA)
    # The router may refuse it for its own reasons (no story request): not for membership.
    assert "is not a member of" not in str(r.json().get("detail", "")), (kind, r.text)


def test_the_operator_is_never_refused(op: TestClient) -> None:
    r = op.post(f"/api/tasks/{GAMMA_TASK}/update", json={"actor": "operator", "status": "doing"})
    assert r.status_code == 200, r.text
    r = op.post("/api/decisions", json={**decision("GAMMA"), "agent_id": "operator"})
    assert r.status_code == 201, r.text


def test_update_entry_on_a_non_member_row_is_refused(op: TestClient, root: Path) -> None:
    made = op.post("/api/decisions", json={**decision("GAMMA"), "agent_id": "operator"}).json()
    did = made["metadata"]["id"]
    before = tree(root)
    r = op.post(f"/api/decisions/{did}/update", json={"agent_id": A, "why": "changed"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (
        403, f"agent {A} is not a member of GAMMA; this decision is GAMMA's. The operator adds it on the agent card")
    assert tree(root) == before
    mine = op.post("/api/decisions", json=decision("BETA"), headers=VIA).json()["metadata"]["id"]
    r = op.post(f"/api/decisions/{mine}/update", json={"agent_id": A, "why": "changed"}, headers=VIA)
    assert r.status_code == 200, r.text


# -- one helper, no copies ---------------------------------------------------

def test_no_copy_of_the_old_same_project_check_is_left() -> None:
    backend = Path(__file__).resolve().parents[1] / "backend"
    found = [f"{p.name}:{i}" for p in backend.rglob("*.py")
             for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"def _same_project|def _agent_project|this chat works in|this chat is in \{", line)]
    assert not found, found
    for name in ("notelib.py", "publishlib.py", "entrypointlib.py", "routers/lenses.py"):
        assert "memberships.may_write_row(" in (backend / name).read_text(encoding="utf-8"), name
