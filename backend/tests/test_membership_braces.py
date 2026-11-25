"""Braces after #task / #now name the project and the lane (tk_d1d25a4d
step 3, note nt_258a7ed7 §3 «Braces»), read by one rule in the hook and the
server (hookshared.task_braces / resolve_braces).

World: chat A from merkhet (home) joined writing-tracker; shopfront is no
project of A's. merkhet's board has the lanes ui, merkhet-ui and release;
writing-tracker's has docs. Aliases: WT → writing-tracker, release →
writing-tracker. One table goes through the hook and the server and both
must give its answer; the agent's create is checked against the braces; the
#now card resolves them once; aliases are unique and race-safe.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import mcp, memberships, tasklib
from backend import membership_fold as mf
from backend.server import create_app
from tests.conftest import make_chat

pytestmark = pytest.mark.strict_membership

A = "cc-aaaa1111"
HOME, MEMBER, OTHER = "merkhet", "writing-tracker", "shopfront"
VIA = {mcp.VIA_HEADER: mcp.VIA_VALUE}
_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _load_capture():
    spec = importlib.util.spec_from_file_location("sp_capture_braces", _HOOKS / "capture.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_capture_braces"] = mod
    spec.loader.exec_module(mod)
    return mod


capture = _load_capture()


def tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")}


def _task_row(i: int, project: str, lane: str) -> list[str]:
    return [f"tk_lane{i:04d}", project, f"card {i}", "todo", lane, lane, ""]


@pytest.fixture()
def world(tmp_path: Path):
    root = tmp_path / "data"
    for code in (HOME, MEMBER, OTHER):
        (root / "projects" / code).mkdir(parents=True)
    with open(root / "tasks.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "project", "title", "status", "lane", "assignee", "archived_at"])
        for i, (code, lane) in enumerate([(HOME, "ui"), (HOME, "merkhet-ui"), (HOME, "release"), (MEMBER, "docs"),
                                              (HOME, "phase-1"), (HOME, "sprint1"), (HOME, "bugs-ui")]):
            w.writerow(_task_row(i, code, lane))
    make_chat(root, HOME, A, [("2026-11-20T10:00:00", "start", "ok")])
    # Tags older than this are history (nowlib); the tests' chats are newer.
    (root / "now.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.post(f"/api/agents/{A}/membership", json={"op": "join", "project": MEMBER}).status_code == 200
        for alias in ("WT", "release"):
            r = c.post(f"/api/projects/{MEMBER}/aliases", json={"op": "add", "alias": alias})
            assert r.status_code == 200, r.text
        yield c, root


def near(name: str, hint: str) -> str:
    return f"{{{name}}} is not a project of this agent — did you mean {hint}?"


NOT_SHOPFRONT = (f"agent {A} is not a member of shopfront; its projects: merkhet, writing-tracker. "
                 "The operator adds it on the agent card")

# message → (project, lane, refusal); project "" is the home.
TABLE: list[tuple[str, tuple[str, str, str]]] = [
    ("#task {writing-tracker} {docs} x", (MEMBER, "docs", "")),
    ("#task {docs} {writing-tracker} x", (MEMBER, "docs", "")),                      # any order
    ("#task {Writing-Tracker} x", (MEMBER, "", "")),                                 # any case
    ("#task {wt} x", (MEMBER, "", "")),                                              # an alias
    ("#task {WT}{DOCS} x", (MEMBER, "docs", "")),                                    # no space between
    ("#task {project:writing-tracker} {lane:ui} x", (MEMBER, "ui", "")),             # prefixes
    ("#task {project:release} x", (MEMBER, "", "")),
    ("#task {lane:release} x", ("", "release", "")),
    ("#task {release} x", ("", "", "{release} is a project and a lane: write {project:release} or {lane:release}")),
    ("#task {ui} x", ("", "ui", "")),
    ("#task {UI} x", ("", "ui", "")),                                                # the board's spelling
    ("#task {merkhet-ui} x", ("", "merkhet-ui", "")),                                # a live lane beats a near miss
    ("#task {merkht} x", ("", "", near("merkht", "merkhet"))),
    ("#task {writing-tracer} x", ("", "", near("writing-tracer", "writing-tracker"))),
    ("#task {merkhet} {writing-tracker} x", ("", "", "two projects in braces (merkhet, writing-tracker): name one")),
    ("#task {ui} {backend} x", ("", "", "two lanes in braces (ui, backend): name one")),
    ("#task {shopfront} x", ("", "", NOT_SHOPFRONT)),
    ("#task {project:nowhere} x", ("", "", "{project:nowhere}: nowhere is not a project of this agent")),
    ("#task {brand new lane} x", ("", "brand new lane", "")),
    ("#task {ui2} x", ("", "", "{ui2} is not a lane of merkhet's board — did you mean ui? or write {lane:ui2}")),
    ("#task {writing-tracker} {doc} x",
     ("", "", "{doc} is not a lane of writing-tracker's board — did you mean docs? or write {lane:doc}")),
    # A numbered or suffixed sibling of a live lane is a new lane, not a typo.
    ("#task {phase-2} x", ("", "phase-2", "")),
    ("#task {sprint2} x", ("", "sprint2", "")),
    ("#task {bugs-ux} x", ("", "bugs-ux", "")),
    ("#task {relase} x", ("", "", near("relase", "release"))),                        # an alias's near miss first
    ("#task {" + "a" * 80 + "} x", ("", "a" * 80, "")),                               # 80 characters
    ("#task {" + "a" * 81 + "} x", ("", "", "")),                                    # 81: not a group
    ("#task fix the {writing-tracker} parser", ("", "", "")),                         # a { in the title
    ("#now-todo {writing-tracker} later", (MEMBER, "", "")),
    ("#mute #task {writing-tracker} x", None),                                       # muted: no command
    ("#task {ui} x ###now {writing-tracker} y", (MEMBER, "", "")),                    # ### reads that one
]


def _server(c: TestClient, text: str):
    got = tasklib.task_braces(c.app.state.store, A, text)
    return got


@pytest.mark.parametrize("text,want", TABLE, ids=[t for t, _ in TABLE])
def test_the_hook_and_the_server_read_braces_alike(world, text: str, want) -> None:
    c, root = world
    server = _server(c, text)
    hook = capture.task_where(root, HOME, A, text)
    if want is None:
        assert hook is None and server == tasklib.NO_BRACES
        return
    project, lane, refusal = want
    assert (server["project"], server["lane"], server["refusal"]) == (project, lane, refusal), server
    assert (hook["project"], hook["lane"], hook["refusal"]) == (
        (project or HOME) if not refusal else "", lane, refusal), hook


# Each tag reads its own braces (the critic of c1: the #task's were lost).
KINDS = [
    ("#now {ui} x and #task {writing-tracker} y", "now", ("", "ui", "")),
    ("#now {ui} x and #task {writing-tracker} y", "task", (MEMBER, "", "")),
    ("#task {writing-tracker} y and #now x", "now", ("", "", "")),
    ("#task {writing-tracker} y and #now x", "task", (MEMBER, "", "")),
    ("#now-todo {docs} {writing-tracker} x", "task", None),
]


@pytest.mark.parametrize("text,kind,want", KINDS, ids=[f"{k}:{t}" for t, k, _w in KINDS])
def test_each_tag_reads_its_own_braces(world, text: str, kind: str, want) -> None:
    c, root = world
    server = tasklib.task_braces(c.app.state.store, A, text, kind)
    hook = capture.task_where(root, HOME, A, text, kind=kind)
    if want is None:
        assert hook is None and server == tasklib.NO_BRACES
        return
    project, lane, refusal = want
    assert (server["project"], server["lane"], server["refusal"]) == want, server
    assert (hook["project"], hook["lane"], hook["refusal"]) == ((project or HOME), lane, refusal), hook


def test_a_task_beside_a_written_now_goes_where_its_braces_say(world) -> None:
    c, root = world
    _say(root, "#now {ui} fix the timeout and #task {writing-tracker} {docs} write it up", minutes_ago=5)
    c.app.state.store.rebuild()
    c.get("/api/tasks", params={"project": HOME})            # the server writes the #now card
    r = _agent_task(c, HOME)
    assert r.status_code == 403 and "the operator named writing-tracker in braces" in r.json()["detail"], r.text
    r = _agent_task(c, MEMBER)
    assert r.status_code == 201, r.text
    assert (r.json()["metadata"]["project"], r.json()["metadata"]["lane"]) == (MEMBER, "docs")


def test_the_hook_notice_names_each_tags_place(world) -> None:
    _c, root = world
    cap = capture.TurnCapture(root, HOME, A)
    out = capture.format_signals(cap.open_turn("#now {ui} fix it and #task {wt} write it up")).splitlines()
    assert "→ merkhet · lane ui" in next(x for x in out if x.startswith("[slightly-parallel] #now"))
    assert "→ writing-tracker (" in next(x for x in out if x.startswith("[slightly-parallel] #task"))


def _say(root: Path, text: str, minutes_ago: int = 1) -> None:
    at = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    make_chat(root, HOME, A, [("2026-11-20T10:00:00", "start", "ok"), (at, text, "on it")])


def _agent_task(c: TestClient, project: str):
    return c.post("/api/tasks", json={"agent_id": A, "project": project, "created_date": "2611-20",
                                      "created_time": "10:06", "title": "Check the login timeout",
                                      "tags": "ag_bug"}, headers=VIA)


def test_the_agents_create_follows_the_braces(world) -> None:
    c, root = world
    _say(root, "#task {writing-tracker} {docs} check the login timeout")
    c.app.state.store.rebuild()
    before = tree(root)
    r = _agent_task(c, HOME)
    assert r.status_code == 403 and r.json()["detail"].startswith(
        "the operator named writing-tracker in braces: this task goes to writing-tracker, not merkhet"), r.text
    assert tree(root) == before
    r = _agent_task(c, MEMBER)
    assert r.status_code == 201, r.text
    assert (r.json()["metadata"]["project"], r.json()["metadata"]["lane"]) == (MEMBER, "docs")


def test_a_refused_brace_refuses_the_agents_create(world) -> None:
    c, root = world
    _say(root, "#task {merkht} check it")
    c.app.state.store.rebuild()
    before = tree(root)
    r = _agent_task(c, HOME)
    assert (r.status_code, r.json()["detail"]) == (403, near("merkht", "merkhet"))
    assert tree(root) == before


def test_the_now_card_resolves_the_braces_once(world) -> None:
    c, root = world
    _say(root, "#now {writing-tracker} {docs} build the export", minutes_ago=5)
    c.app.state.store.rebuild()
    cards = [t for t in c.get("/api/tasks", params={"project": MEMBER}).json()["tasks"]
             if "build the export" in str(t.get("title") or "")]
    assert len(cards) == 1, cards
    assert (cards[0]["project"], cards[0]["lane"], cards[0]["status"]) == (MEMBER, "docs", "doing")
    # The server's card in a project other than home says so (the critic of 54c217ee).
    events = c.app.state.store.query(
        "SELECT new_value FROM task_events_mutual WHERE task_id = ? AND field = 'created_in'", (cards[0]["id"],))
    assert [e["new_value"] for e in events] == [f"{MEMBER} (home {HOME})"]


def test_a_refused_now_makes_no_card(world) -> None:
    c, root = world
    _say(root, "#now {shopfront} build the export", minutes_ago=5)
    c.app.state.store.rebuild()
    for code in (HOME, MEMBER, OTHER):
        got = c.get("/api/tasks", params={"project": code}).json()["tasks"]
        assert not [t for t in got if "build the export" in str(t.get("title") or "")], code


def test_the_hook_notice_says_where_or_why_not(world) -> None:
    _c, root = world
    cap = capture.TurnCapture(root, HOME, A)
    line = next(x for x in capture.format_signals(cap.open_turn("#task {wt} {docs} fix it")).splitlines()
                if x.startswith("[slightly-parallel] #task"))
    assert "→ writing-tracker · lane docs" in line
    cap.complete_turn("ok")
    line = next(x for x in capture.format_signals(cap.open_turn("#task {merkht} fix it")).splitlines()
                if x.startswith("[slightly-parallel] #task"))
    assert "Refused: " + near("merkht", "merkhet") in line


# -- aliases -------------------------------------------------------------------

@pytest.mark.parametrize("project,alias,status,words", [
    (MEMBER, "wt", 409, "«WT» is an alias of writing-tracker already"),       # any case
    (HOME, "WT", 409, "«WT» is an alias of writing-tracker already"),
    (HOME, "Shopfront", 409, "«Shopfront» is a project's code"),
    (HOME, "bad alias", 422, "an alias is 1–40"),
    ("nowhere", "nw", 404, "no project «nowhere»"),
])
def test_an_alias_is_unique_across_codes_and_aliases(world, project, alias, status, words) -> None:
    c, root = world
    before = tree(root)
    r = c.post(f"/api/projects/{project}/aliases", json={"op": "add", "alias": alias})
    assert r.status_code == status and words in r.json()["detail"], r.text
    assert tree(root) == before


def test_aliases_are_listed_and_removed(world) -> None:
    c, _root = world
    got = c.get("/api/project-aliases").json()["aliases"]
    assert got == [{"alias": "release", "project": MEMBER}, {"alias": "WT", "project": MEMBER}]
    r = c.post(f"/api/projects/{HOME}/aliases", json={"op": "remove", "alias": "WT"})
    assert r.status_code == 409 and "is not an alias of merkhet" in r.json()["detail"]
    r = c.post(f"/api/projects/{MEMBER}/aliases", json={"op": "remove", "alias": "wt"})
    assert r.status_code == 200, r.text
    assert [a["alias"] for a in r.json()["aliases"]] == ["release"]


def test_an_agent_cannot_name_aliases(world) -> None:
    c, root = world
    before = tree(root)
    r = c.post(f"/api/projects/{HOME}/aliases", json={"op": "add", "alias": "mk", "agent_id": A}, headers=VIA)
    assert r.status_code >= 400 and "the operator's" in r.json()["detail"], r.text
    assert tree(root) == before


_RACER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from backend import memberships
root, project, alias, start = sys.argv[2:6]
while time.time() < float(start):
    pass
try:
    memberships.write_alias(root, "add", project, alias)
    print("ok")
except memberships.Refused as r:
    print("refused:" + r.detail)
"""


def test_two_processes_race_on_one_alias(world) -> None:
    _c, root = world
    backend_dir = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    seen: dict[str, int] = {}
    for _ in range(50):
        (root / mf.ALIASES).unlink(missing_ok=True)
        start = str(time.time() + 0.4)
        procs = [subprocess.Popen([sys.executable, "-c", _RACER, backend_dir, str(root), code, "SP", start],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                 for code in (HOME, MEMBER)]
        outs = []
        for p in procs:
            out, err = p.communicate(timeout=60)
            assert p.returncode == 0, err
            outs.append(out.strip())
        assert sorted(o.split(":")[0] for o in outs) == ["ok", "refused"], outs
        winner = HOME if outs[0] == "ok" else MEMBER
        seen[winner] = seen.get(winner, 0) + 1
        rows, _cut = mf.read(root / mf.ALIASES)
        assert len(rows) == 1 and mf.aliases(rows, {HOME, MEMBER, OTHER}) == {"SP": winner}
    print("one alias, two processes, the winner:", seen)
    assert sum(seen.values()) == 50


def test_memberships_alias_map_reads_the_file(world) -> None:
    c, _root = world
    assert memberships.alias_map(c.app.state.store) == {"WT": MEMBER, "release": MEMBER}
