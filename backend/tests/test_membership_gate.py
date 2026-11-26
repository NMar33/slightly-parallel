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


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_every_by_id_write_path_knows_how_its_row_is_checked(path: str) -> None:
    # The critic's case: a path that names a row by id and no project in its
    # body was not checked at all (/api/cores/{id}/notes on a GAMMA core).
    if "zz_none" not in path:
        return
    known = any(p.fullmatch(path) for p, _w, _r in _server._ROW_WRITES)
    assert known or path.startswith(_server.ROW_CHECKED_IN_LIBRARIES), path


def _gamma_rows(op: TestClient) -> dict[str, str]:
    """One row of each kind written by id, in GAMMA, made by the operator."""
    out: dict[str, str] = {}
    r = op.post("/api/cores", json={"project": "GAMMA", "name": "Gamma core", "type": "capability",
                                    "agent_id": "operator", "text": "#core-new Gamma core"})
    assert r.status_code in (200, 201), r.text
    out["core"] = r.json()["core"]["id"] if "core" in r.json() else r.json()["id"]
    r = op.post("/api/docs", json={"project": "GAMMA", "kind": "article", "title": "gamma doc"})
    assert r.status_code == 201, r.text
    out["doc"] = r.json()["doc"]["id"]
    r = op.post("/api/visions", json={"created_date": "2611-20", "created_time": "10:00", "project": "GAMMA",
                                      "agent_id": "operator", "l1": "A gamma vision", "l2": "wording"})
    assert r.status_code == 201, r.text
    out["vision"] = r.json()["metadata"]["id"]
    r = op.post(f"/api/tasks/{GAMMA_TASK}/notes", json={"type": "article", "body": "1) Gamma note"})
    assert r.status_code == 201, r.text
    out["task_note"] = r.json()["note"]["id"] if "note" in r.json() else r.json()["id"]
    r = op.post(f"/api/tasks/{GAMMA_TASK}/link", json={"to": "tk_beta_x", "kind": "relates"})
    assert r.status_code == 201, r.text
    out["task_link"] = r.json()["link"]["id"]
    return out


def test_writes_by_id_with_no_project_are_checked_against_the_row(op: TestClient, root: Path) -> None:
    rows = _gamma_rows(op)
    cases = [
        (f"/api/cores/{rows['core']}/notes", {"text": "x", "comment": "y"}, "core"),
        (f"/api/cores/{rows['core']}/off", {}, "core"),
        (f"/api/docs/{rows['doc']}/versions", {"body": "x", "note": "y"}, "document"),
        (f"/api/visions/{rows['vision']}/interpretation", {"text": "x"}, "vision"),
    ]
    for path, body, what in cases:
        before = tree(root)
        r = op.post(path, json={"agent_id": A, **body}, headers=VIA)
        assert (r.status_code, r.json()["detail"]) == (403, (
            f"agent {A} is not a member of GAMMA; this {what} is GAMMA's. "
            "The operator adds it on the agent card")), path
        assert tree(root) == before, path


def test_three_segment_task_paths_are_checked_with_mcp_only_off(op: TestClient, root: Path) -> None:
    rows = _gamma_rows(op)
    for path in (f"/api/tasks/notes/{rows['task_note']}/update", f"/api/tasks/notes/{rows['task_note']}/delete",
                 f"/api/tasks/links/{rows['task_link']}/delete"):
        before = tree(root)
        r = op.post(path, json={"agent_id": A, "body": "x"})      # plain HTTP, mcp_only off
        assert (r.status_code, r.json().get("detail")) == (403, not_member_task("GAMMA")), (path, r.text)
        assert tree(root) == before, path


def test_a_link_to_a_task_of_a_non_member_project_is_refused(op: TestClient, root: Path) -> None:
    # The critic of c2: the delete checks both tasks; the create checked only its own.
    before = tree(root)
    r = op.post("/api/tasks/tk_alpha_auth/link", json={"agent_id": A, "to": GAMMA_TASK, "kind": "relates"},
                headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA"))
    assert tree(root) == before
    # Over plain HTTP with agents.mcp_only off too (the critic's probe got 201).
    r = op.post("/api/tasks/tk_alpha_auth/link", json={"agent_id": A, "to": GAMMA_TASK, "kind": "blocks"})
    assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA"))
    assert tree(root) == before
    r = op.post("/api/tasks/tk_alpha_auth/link", json={"agent_id": A, "to": "tk_beta_x", "kind": "relates"},
                headers=VIA)
    assert r.status_code == 201, r.text


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


def test_after_done_closes_a_foreign_task_its_report_and_evidence_pass(op: TestClient, root: Path) -> None:
    # Answer 2: the id next to #done closes the task in any project; the
    # finish-a-task report and evidence that follow must not be refused.
    from datetime import datetime, timedelta
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    at = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    make_chat(root, "ALPHA", A, [("2026-11-20T10:00:00", "work", "ok"), (at, f"#done {GAMMA_TASK}", "closed")])
    op.app.state.store.rebuild()
    got = op.get("/api/done-tags", params={"agent_id": A}).json()
    assert [t["result"] for t in got["tasks"]] == ["moved"], got
    for verb, body in (("report", {"text": "done it", "outcome": "done"}),
                       ("evidence", {"items": [{"kind": "note", "text": "ran it"}]}),
                       ("story", {"request_id": "sr_none", "body": "x"})):
        r = op.post(f"/api/tasks/{GAMMA_TASK}/{verb}", json={"agent_id": A, **body}, headers=VIA)
        assert "is not a member of" not in str(r.json().get("detail", "")), (verb, r.text)
    # Only those: anything else on that task is still refused.
    for verb, body in (("update", {"status": "doing"}), ("commits", {"shas": ["abc1234"]})):
        r = op.post(f"/api/tasks/{GAMMA_TASK}/{verb}", json={"agent_id": A, **body}, headers=VIA)
        assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA")), verb
    # Another chat that did not close it is refused the report.
    other = "cc-bbbb2222"
    make_chat(root, "ALPHA", other, [("2026-11-20T10:00:00", "work", "ok")])
    op.app.state.store.rebuild()
    r = op.post(f"/api/tasks/{GAMMA_TASK}/report", json={"agent_id": other, "text": "x", "outcome": "done"}, headers=VIA)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("task,result", [("tk_alpha_cyr", "already"), ("tk_alpha_old", "archived")])
def test_a_done_that_closed_nothing_gives_no_rights(op: TestClient, root: Path, task: str, result: str) -> None:
    # The critic of 54c217ee: #done naming a task already done or archived
    # gave that chat lasting report rights on it. A task of a project the
    # chat is not in: move ALPHA's closed task to GAMMA first.
    import csv
    from datetime import datetime, timedelta
    with open(root / "tasks.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        if row["id"] == task:
            row["project"] = row["projects"] = "GAMMA"
    with open(root / "tasks.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    at = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    make_chat(root, "ALPHA", A, [("2026-11-20T10:00:00", "work", "ok"), (at, f"#done {task}", "closed")])
    op.app.state.store.rebuild()
    got = op.get("/api/done-tags", params={"agent_id": A}).json()
    assert [t["result"] for t in got["tasks"]] == [result], got
    before = tree(root)
    r = op.post(f"/api/tasks/{task}/report", json={"agent_id": A, "text": "x", "outcome": "done"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, not_member_task("GAMMA"))
    assert tree(root) == before


def test_a_task_shown_on_a_member_project_is_the_members_to_work_on(op: TestClient, root: Path) -> None:
    # The operator's answer (a) to B3: a member of any project in a task's
    # projects works on it, as one of its main project does.
    shared = "tk_gamma_shared"
    with (root / "tasks.csv").open("a", encoding="utf-8") as fh:
        fh.write(f'{shared},2611-20,10:00,GAMMA,operator,Shared,todo,med,,,,,10,,,,,"GAMMA,BETA",,,,,,,,,,,\n')
    (root / "projects" / "DELTA").mkdir()
    delta = "cc-dddd4444"
    make_chat(root, "DELTA", delta, [("2026-11-20T10:00:00", "work", "ok")])
    op.app.state.store.rebuild()
    for verb, body in UPDATES.values():
        r = op.post(f"/api/tasks/{shared}/{verb}", json={"agent_id": A, **body}, headers=VIA)
        assert "is not a member of" not in str(r.json().get("detail", "")), (verb, r.text)
    before = tree(root)
    r = op.post(f"/api/tasks/{shared}/update", json={"agent_id": delta, "status": "doing"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (403, (
        f"agent {delta} is not a member of GAMMA or BETA; this task is on GAMMA, BETA. The operator adds it on the agent card"))
    assert tree(root) == before
    # A link to it, from a member's task: the other end is the member's too.
    r = op.post("/api/tasks/tk_alpha_auth/link", json={"agent_id": A, "to": shared, "kind": "relates"}, headers=VIA)
    assert r.status_code == 201, r.text


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
