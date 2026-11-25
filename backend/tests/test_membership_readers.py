"""The readers that list a project's chats include its members (tk_d1d25a4d
step 2, note nt_9de63b9e §4, §6).

Fixture: chat A from ALPHA joins BETA. Every LIST route shows A in both
projects, pins and starred messages included; the calendar and the
timelapse of BETA show A's sessions «from ALPHA» and add none of its
minutes; every ACCOUNT answer is the same before and after, and the sum over
projects equals the total (docs/testing.md #4); commit ownership is
unchanged. A join is read per request: the sessions list and its ETag
change with no chat file written.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import gitwork
from backend.server import create_app
from tests.conftest import git_env, git_repo, make_chat

A = "cc-aaaa1111"
B = "cc-bbbb2222"
TURNS_A = [("2026-11-20T10:00:00", "start the work on tk_alpha_auth", "started"),
           ("2026-11-20T10:05:00", "go on", "done")]
TURNS_B = [("2026-11-20T11:00:00", "beta work", "ok"),
           ("2026-11-20T11:20:00", "more", "ok")]
RANGE = {"from": "2026-11-19", "to": "2026-11-21"}


def tree(root: Path, part: str = "") -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")
            and part in p.relative_to(root).as_posix()}


@pytest.fixture()
def root(data_root: Path, tmp_path: Path) -> Path:
    make_chat(data_root, "ALPHA", A, TURNS_A)
    make_chat(data_root, "BETA", B, TURNS_B)
    # A's chat ran in a repository with one commit inside its session.
    repo = git_repo(tmp_path / "repo-a")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    env = git_env(GIT_AUTHOR_DATE="2026-11-20T10:02:00", GIT_COMMITTER_DATE="2026-11-20T10:02:00")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "work"], cwd=repo, check=True, env=env)
    meta = data_root / "projects" / "ALPHA" / "chats" / A / "meta.json"
    m = json.loads(meta.read_text(encoding="utf-8"))
    m.update({"cwd": str(repo), "agent_group": "g1", "tool": "claude-code",
              "session_ref": "11111111-2222-3333-4444-555555555555"})
    meta.write_text(json.dumps(m), encoding="utf-8")
    gitwork.forget()
    return data_root


@pytest.fixture()
def op(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def join(op: TestClient) -> None:
    r = op.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "BETA"})
    assert r.status_code == 200, r.text


def ids(rows, key: str = "agent_id") -> set[str]:
    return {str(r.get(key) or "") for r in rows}


def lists(op: TestClient, project: str) -> dict[str, set[str]]:
    """Every LIST route's chats for one project."""
    out: dict[str, set[str]] = {}
    out["sessions"] = ids(op.get("/api/sessions", params={"project": project}).json()["sessions"])
    prof = op.get("/api/agents/profiles", params={"project": project}).json()
    out["roster"] = {p["agent"]["agent_id"] for p in prof["profiles"]}
    out["groups"] = {m["agent_id"] for g in op.get("/api/agents/groups", params={"project": project}).json()["groups"]
                     for m in g["members"]}
    bundle = op.get(f"/api/project/{project}").json()
    out["bundle.agents"] = ids(bundle["agents"])
    out["bundle.activity"] = ids(bundle["activity"])
    snap = op.get("/api/snapshot").json()
    summary = next(p for p in snap["projects"] if p["code"] == project)
    out["snapshot.active"] = {str(summary["active_agents"])}
    out["timeline.lanes"] = ids(op.get("/api/timeline", params={"project": project}).json()["lanes"])
    out["timeline.activities"] = {a["agent_id"] for lane in op.get("/api/timeline", params={"project": project}).json()["lanes"]
                                  for a in lane["activities"]}
    out["mentions"] = set(op.get("/api/tasks/mentions/by-agent", params={"project": project}).json()["agents"])
    out["pins"] = ids(op.get("/api/pins", params={"project": project}).json()["items"])
    out["marks"] = {m.get("agent_id") or m.get("target") for m in op.get("/api/marks", params={"project": project}).json()["marks"]
                    if m["kind"] in ("agent", "message")}
    cal = op.get("/api/calendar", params={"project": project, **RANGE}).json()
    out["calendar"] = ids(cal["sessions"])
    out["resumable"] = ids(op.get("/api/terminal/resumable", params={"project": project}).json()["chats"])
    out["timelapse"] = ids(op.get("/api/timelapse", params={"project": project}).json()["sessions"])
    return out


def account(op: TestClient) -> dict[str, object]:
    """What the ACCOUNT readers answer, for every project and for all."""
    snap = op.get("/api/snapshot").json()
    out: dict[str, object] = {
        "snapshot.hours": {p["code"]: (p["est_hours_30d"], p["last_activity"]) for p in snap["projects"]},
        "kpi": snap["kpi"],
        "time.summary": op.get("/api/time/summary").json(),
        "usage": op.get("/api/usage").json(),
        "heatmap": op.get("/api/heatmap", params={"project": "BETA"}).json(),
        "overview": op.get("/api/search/overview").json().get("projects"),
    }
    for code in ("ALPHA", "BETA"):
        bundle = op.get(f"/api/project/{code}").json()["summary"]
        out[f"bundle.{code}"] = (bundle["est_hours_30d"], bundle["last_activity"])
        out[f"calendar.{code}"] = op.get("/api/calendar", params={"project": code, **RANGE}).json()["days"]
    out["calendar.all"] = op.get("/api/calendar", params={"project": "all", **RANGE}).json()["days"]
    out["git"] = {s["id"]: s["git"] for s in op.get("/api/calendar", params={"project": "ALPHA", **RANGE}).json()["sessions"]}
    return out


def test_a_member_is_listed_in_both_projects(op: TestClient, root: Path) -> None:
    op.post("/api/pins", json={"chat_agent": A, "turn": 1, "project": "ALPHA"})
    op.post("/api/marks", json={"kind": "agent", "target": A, "project": "ALPHA"})
    before_alpha, before_beta = lists(op, "ALPHA"), lists(op, "BETA")
    for name, got in before_beta.items():
        if name != "snapshot.active":
            assert A not in got, (name, got)
    join(op)
    after_alpha, after_beta = lists(op, "ALPHA"), lists(op, "BETA")
    assert after_alpha == before_alpha
    for name, got in after_beta.items():
        if name == "snapshot.active":
            assert got == {str(int(next(iter(before_beta[name]))) + 1)}
            continue
        if name in ("groups",):
            assert A in got, name  # its group, g1, is listed in BETA too
            continue
        assert A in got, (name, got)
        assert before_beta[name] <= got, name


def test_member_sessions_come_from_home_and_add_no_minutes(op: TestClient) -> None:
    before = account(op)
    join(op)
    cal = op.get("/api/calendar", params={"project": "BETA", **RANGE}).json()
    mine = [s for s in cal["sessions"] if s["agent_id"] == A]
    assert mine and all(s["from"] == "ALPHA" and s["project"] == "ALPHA" for s in mine)
    assert all("from" not in s for s in cal["sessions"] if s["agent_id"] == B)
    lapse = op.get("/api/timelapse", params={"project": "BETA"}).json()
    assert [s["from"] for s in lapse["sessions"] if s["agent_id"] == A] == ["ALPHA"] * len(mine)
    assert lapse["stats"]["turns"] == sum(s["turns"] for s in cal["sessions"] if s["agent_id"] == B)
    after = account(op)
    assert after == before
    # The parts add up to the whole (#4): per day, ALPHA + BETA = all.
    days_all = after["calendar.all"]
    for day, counts in days_all.items():  # type: ignore[union-attr]
        for k in ("minutes", "turns", "sessions", "commits"):
            parts = sum(after[f"calendar.{c}"].get(day, {}).get(k, 0) for c in ("ALPHA", "BETA"))  # type: ignore[union-attr]
            assert parts == counts[k], (day, k)
    # Commit ownership: A's commit stays with A's session in ALPHA.
    assert sum(g["commits"] for g in after["git"].values()) == 1  # type: ignore[union-attr]


def test_a_join_lists_the_chat_per_request(op: TestClient, root: Path) -> None:
    """join BETA changes /api/sessions?project=BETA and its ETag; no chat
    file and no table of sessions is written for it."""
    first = op.get("/api/sessions", params={"project": "BETA"})
    assert first.status_code == 200
    assert all(s["agent_id"] != A for s in first.json()["sessions"])
    tag = first.headers["etag"]
    assert op.get("/api/sessions", params={"project": "BETA"}, headers={"if-none-match": tag}).status_code == 304
    chats_before = tree(root, "/chats/")
    join(op)
    after = op.get("/api/sessions", params={"project": "BETA"}, headers={"if-none-match": tag})
    assert after.status_code == 200, "the ETag did not move with the join"
    assert after.headers["etag"] != tag
    rows = [s for s in after.json()["sessions"] if s["agent_id"] == A]
    assert rows and all(s["project"] == "ALPHA" and s["projects"] == "ALPHA,BETA" for s in rows)
    assert tree(root, "/chats/") == chats_before
    alpha = op.get("/api/sessions", params={"project": "ALPHA"}).json()["sessions"]
    assert sum(1 for s in alpha if s["agent_id"] == A) == len(rows)
    # A leave takes it out again, per request too.
    r = op.post(f"/api/agents/{A}/membership", json={"op": "leave", "project": "BETA"})
    assert r.status_code == 200, r.text
    assert all(s["agent_id"] != A for s in op.get("/api/sessions", params={"project": "BETA"}).json()["sessions"])


def test_agents_and_sessions_carry_projects(op: TestClient) -> None:
    join(op)
    snap = op.get("/api/snapshot").json()
    by = {a["agent_id"]: a for a in snap["agents"]}
    assert by[A]["projects"] == "ALPHA,BETA" and by[A]["project"] == "ALPHA"
    assert by[B]["projects"] == "BETA"
    assert op.get(f"/api/agent/{A}").json()["agent"]["projects"] == "ALPHA,BETA"
    assert op.get(f"/api/agents/{A}/profile").json()["agent"]["projects"] == "ALPHA,BETA"
    hits = op.get("/api/search", params={"q": "beta work"}).json()["hits"]
    assert hits and all(h["projects"] == "BETA" for h in hits if h.get("agent_id") == B)
    hits = op.get("/api/search", params={"q": "go on"}).json()["hits"]
    assert any(h.get("agent_id") == A and h["projects"] == "ALPHA,BETA" for h in hits), hits


def test_many_member_blocks_never_push_the_projects_own_out(op: TestClient, root: Path) -> None:
    """The bundle lists at most 500 blocks; members' blocks are newer than
    the project's own here and more than 500, and still the minutes and the
    last activity (ACCOUNT) are the project's own."""
    from datetime import datetime, timedelta
    now = datetime.now().replace(microsecond=0, second=0, minute=0)
    own_at = now - timedelta(days=25)
    make_chat(root, "ALPHA", "cc-own00001", [(own_at.isoformat(), "own work", "ok"),
                                            ((own_at + timedelta(minutes=20)).isoformat(), "more", "ok")])
    turns = []
    for i in range(520):
        at = now - timedelta(days=22) + timedelta(hours=i)
        turns += [(at.isoformat(), f"member {i}", "ok"), ((at + timedelta(minutes=5)).isoformat(), "go", "ok")]
    make_chat(root, "BETA", "cc-many0001", turns)
    op.app.state.store.rebuild()
    before = op.get("/api/project/ALPHA").json()["summary"]
    assert before["est_hours_30d"] > 0
    r = op.post("/api/agents/cc-many0001/membership", json={"op": "join", "project": "ALPHA"})
    assert r.status_code == 200, r.text
    bundle = op.get("/api/project/ALPHA").json()
    assert len(bundle["activity"]) == 500
    assert "cc-many0001" in {a["agent_id"] for a in bundle["activity"]}
    after = bundle["summary"]
    assert (after["est_hours_30d"], after["last_activity"]) == (before["est_hours_30d"], before["last_activity"])


def _projects_everywhere(op: TestClient) -> list[tuple[str, str, str, str]]:
    """(route, project, agent, projects) of every row that carries projects."""
    out: list[tuple[str, str, str, str]] = []

    def take(route: str, rows, key: str = "agent_id") -> None:
        for r in rows:
            out.append((route, str(r.get("project") or ""), str(r.get(key) or ""), str(r.get("projects"))))

    take("sessions", op.get("/api/sessions").json()["sessions"])
    take("snapshot", op.get("/api/snapshot").json()["agents"])
    for code in ("ALPHA", "BETA"):
        take(f"bundle {code}", op.get(f"/api/project/{code}").json()["agents"])
        take(f"profiles {code}", [p["agent"] for p in op.get("/api/agents/profiles", params={"project": code}).json()["profiles"]])
    take("agent", [op.get(f"/api/agent/{A}").json()["agent"]])
    take("pins", op.get("/api/pins").json()["items"])
    take("search", op.get("/api/search", params={"q": "resumed elsewhere"}).json()["hits"])
    return out


def test_an_empty_ledger_changes_no_list(op: TestClient, root: Path) -> None:
    """A chat with folders in two projects lists each folder's rows where
    they are, as before the ledger: every row's projects is its own project."""
    make_chat(root, "BETA", A, [("2026-11-21T09:00:00", "resumed elsewhere", "ok")])
    op.app.state.store.rebuild()
    op.post("/api/pins", json={"chat_agent": A, "turn": 1, "project": "BETA"})
    beta = op.get("/api/sessions", params={"project": "BETA"}).json()["sessions"]
    assert {s["project"] for s in beta} == {"BETA"}
    alpha = op.get("/api/sessions", params={"project": "ALPHA"}).json()["sessions"]
    assert {s["project"] for s in alpha} == {"ALPHA"}
    rows = _projects_everywhere(op)
    assert any(r[2] == A and r[1] == "BETA" for r in rows) and any(r[0] == "pins" for r in rows)
    wrong = [r for r in rows if r[3] != r[1]]
    assert not wrong, wrong


def test_a_member_of_two_folders_carries_its_folder_and_its_joins(op: TestClient, root: Path) -> None:
    """With a join, each folder's rows carry their own project and the joined
    one — never the other folder's project."""
    make_chat(root, "BETA", A, [("2026-11-21T09:00:00", "resumed elsewhere", "ok")])
    (root / "projects" / "GAMMA").mkdir(parents=True)
    op.app.state.store.rebuild()
    r = op.post(f"/api/agents/{A}/membership", json={"op": "join", "project": "GAMMA"})
    assert r.status_code == 200, r.text
    mine = {(x[0], x[1], x[3]) for x in _projects_everywhere(op) if x[2] == A}
    assert {p for _r, own, p in mine if own == "ALPHA"} == {"ALPHA,GAMMA"}
    assert {p for _r, own, p in mine if own == "BETA"} == {"BETA,GAMMA"}
    # In GAMMA the chat is listed once, not once per folder.
    roster = op.get("/api/agents/profiles", params={"project": "GAMMA"}).json()["profiles"]
    assert [p["agent"]["agent_id"] for p in roster].count(A) == 1
    bundle = op.get("/api/project/GAMMA").json()["agents"]
    assert [a["agent_id"] for a in bundle].count(A) == 1
