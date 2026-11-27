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
import json
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
    # Unclear lanes make the card in the default lane and ask after (ASKS below).
    ("#task {release} x", ("", "", "")),
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
    ("#task {ui2} x", ("", "", "")),
    ("#task {writing-tracker} {doc} x", (MEMBER, "", "")),
    # An ask drops the lanes: the card really goes to the default lane, as
    # the ask says (the critic: {ui} {ui2} landed in ui).
    ("#now {ui} {ui2} x", ("", "", "")),
    # A both-name is no target: the other groups read the home's board, so
    # {ui2} is a near miss of ui there, not a new lane of writing-tracker's.
    ("#now {release} {ui2} x", ("", "", "")),
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
    # Every refusal at once (tk_90c1ba5f), joined by "; " for the notice.
    ("#task {merkht} {writing-tracer} x",
     ("", "", near("merkht", "merkhet") + "; " + near("writing-tracer", "writing-tracker"))),
    ("#task {project:nowhere} {lane:} x",
     ("", "", "{project:nowhere}: nowhere is not a project of this agent; {lane:} names no lane")),
    ("#task {merkhet} {writing-tracker} {ui} {backend} x",
     ("", "", "two projects in braces (merkhet, writing-tracker): name one; "
              "two lanes in braces (ui, backend): name one")),
    # No access is said alone: nothing about the rest of the braces.
    ("#task {shopfront} {ui} {backend} x", ("", "", NOT_SHOPFRONT)),
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
    assert server["ask"] == hook["ask"] == ASKS.get(text, ""), (server, hook)


# A lane the braces leave unclear (tk_970d6b2d): no refusal, the card is made
# in the default lane, and the agent asks the operator this line after.
ASKS: dict[str, str] = {
    "#task {release} x": "{release} is both a project and a lane — did you mean project writing-tracker "
                         "or lane release? (to name one: {project:release} or {lane:release})",
    "#task {ui2} x": "{ui2} is not a lane of merkhet's board — did you mean ui, or a new lane ui2? "
                     "(choose on the card)",
    "#now {ui} {ui2} x": "{ui2} is not a lane of merkhet's board — did you mean ui, or a new lane ui2? "
                         "(choose on the card)",
    "#now {release} {ui2} x": "{release} is both a project and a lane — did you mean project writing-tracker "
                              "or lane release? (to name one: {project:release} or {lane:release}) Also: "
                              "{ui2} is not a lane of merkhet's board — did you mean ui, or a new lane ui2? "
                              "(choose on the card)",
    "#task {writing-tracker} {doc} x": "{doc} is not a lane of writing-tracker's board — did you mean docs, "
                                       "or a new lane doc? (choose on the card)",
}


def test_the_hook_says_write_now_and_ask_after_for_an_unclear_lane(world) -> None:
    """The notice never asks before writing: the card is written at once,
    and the question comes after it (tk_970d6b2d)."""
    _c, root = world
    for text, ask in ASKS.items():
        notice = capture.where_notice(capture.task_where(root, HOME, A, text))
        assert "Refused" not in notice and "No card" not in notice, notice
        if "lane_choice" in capture.task_where(root, HOME, A, text):
            assert "Write it now" in notice and "use its lane chip" in notice, notice
        else:
            assert "write it now" in notice and notice.endswith("ask the operator in one line: " + ask), notice
    # A new lane the operator names: written there, nothing to ask.
    notice = capture.where_notice(capture.task_where(root, HOME, A, "#now-todo {Growth} plan the launch"))
    assert notice.startswith(f"→ {HOME} · lane Growth") and "ask the operator" not in notice, notice


def test_a_now_todo_with_an_unclear_lane_is_written_at_once_by_the_server(world) -> None:
    """The agent wrote nothing (it was told to ask first, before step 3):
    the server's card arrives all the same, in the default lane, and its
    history says what to ask."""
    c, root = world
    _say(root, "#now-todo {ui2} make the timeline readable", minutes_ago=5)
    c.app.state.store.rebuild()
    cards = [t for t in c.get("/api/tasks", params={"project": HOME}).json()["tasks"]
             if "timeline" in t["title"]]
    assert len(cards) == 1 and cards[0]["status"] == "todo" and cards[0]["lane"] == "Now", cards
    events = json.dumps(c.get(f"/api/tasks/{cards[0]['id']}/events").json())
    assert "did you mean ui" in events


def test_a_now_todo_with_a_new_lane_makes_the_lane_and_the_agents_card(world) -> None:
    c, root = world
    _ask(root, "#now-todo {Growth} plan the launch posts")
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME, "created_date": "2611-20",
                                   "created_time": "10:06", "title": "Plan the launch posts",
                                   "status": "todo", "tags": "ag_idea"}, headers=VIA)
    assert r.status_code == 201, r.text
    meta = r.json()["metadata"]
    assert meta["status"] == "todo" and meta["lane"] == "Growth" and "ask" not in r.json()


def test_an_agents_now_todo_with_an_unclear_lane_is_made_and_says_ask(world) -> None:
    c, root = world
    _ask(root, "#now-todo {ui2} make the timeline readable")
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME, "created_date": "2611-20",
                                   "created_time": "10:06", "title": "Readable timeline",
                                   "status": "todo", "tags": "ag_idea"}, headers=VIA)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["metadata"]["lane"] == "Now" and out["metadata"]["status"] == "todo"
    assert out["lane_notice"] == "Card created, lane not chosen: use its lane chip to create new „ui2“ or pick one of: ui."
    assert "make the timeline readable" in json.dumps(c.get(f"/api/tasks/{out['metadata']['id']}").json())


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


def _ask(root: Path, text: str) -> None:
    """The operator's message, the agent's turn still open: it writes the card now."""
    at = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    make_chat(root, HOME, A, [("2026-11-20T10:00:00", "start", "ok"), (at, text, "")])


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


def test_the_hook_notice_and_the_servers_refusal_name_the_project_alike(world) -> None:
    """Both say where the project goes, in the same words (tk_0b8a32d2): the
    notice said only «send that project», and agents put it in `fields`."""
    from backend import mcp_args

    c, root = world
    want = mcp_args.send_project(MEMBER)
    assert '"project": "writing-tracker" next to lens: {"lens":"task","project":"writing-tracker"' in want
    cap = capture.TurnCapture(root, HOME, A)
    line = next(x for x in capture.format_signals(cap.open_turn("#task {wt} {docs} fix it")).splitlines()
                if x.startswith("[slightly-parallel] #task"))
    assert want in line and "send that project" not in line
    cap.complete_turn("ok")
    _say(root, "#task {writing-tracker} {docs} check the login timeout")
    c.app.state.store.rebuild()
    r = _agent_task(c, HOME)
    assert r.status_code == 403 and r.json()["detail"].endswith(want), r.text


# -- every reason at once (tk_90c1ba5f) ---------------------------------------

def test_the_braces_give_each_refusal_as_a_reason(world) -> None:
    c, root = world
    text = "#task {merkht} {writing-tracer} x"
    server = tasklib.task_braces(c.app.state.store, A, text)
    hook = capture.task_where(root, HOME, A, text)
    assert server["reasons"] == hook["reasons"] == [near("merkht", "merkhet"),
                                                    near("writing-tracer", "writing-tracker")]
    assert tasklib.task_braces(c.app.state.store, A, "#task {wt} x")["reasons"] == []


def test_two_refused_braces_refuse_the_agents_create_with_both(world) -> None:
    c, root = world
    _say(root, "#task {merkht} {writing-tracer} check it")
    c.app.state.store.rebuild()
    before = tree(root)
    r = _agent_task(c, HOME)
    assert r.status_code == 403
    assert r.json()["detail"] == near("merkht", "merkhet") + "\n" + near("writing-tracer", "writing-tracker")
    assert len(r.json()["reasons"]) == 2
    assert tree(root) == before


def test_the_agents_create_names_status_lane_title_and_tags_together(world) -> None:
    c, root = world
    _say(root, "#task check the login timeout")
    c.app.state.store.rebuild()
    before = tree(root)
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME, "created_date": "2611-20",
                                   "created_time": "10:06", "title": "", "tags": "nonsense",
                                   "status": "doing", "lane": "ui2"}, headers=VIA)
    assert r.status_code == 422, r.text
    got = r.json()["detail"].split("\n")
    assert len(got) == 4, got
    assert got[0].startswith("an agent creates tasks only in the `agent` column")
    assert got[1].startswith("the lane 'ui2' is not on the board")
    assert got[2] == "an agent task needs a title"
    assert got[3].startswith("unknown tag(s) nonsense")
    assert tree(root) == before


def test_a_long_title_and_too_many_tags_are_both_named(world) -> None:
    c, root = world
    _say(root, "#task check the login timeout")
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME, "created_date": "2611-20",
                                   "created_time": "10:06", "title": "t" * 81,
                                   "tags": ",".join(tasklib.AGENT_TAGS)}, headers=VIA)
    assert r.status_code == 422, r.text
    assert r.json()["detail"].split("\n") == [
        f"an agent task title is at most {tasklib.AGENT_TITLE_MAX} characters (81 sent)",
        f"an agent task carries at most {tasklib.AGENT_TAGS_MAX} tags ({len(tasklib.AGENT_TAGS)} sent)"]


def test_one_bad_field_of_the_agents_create_reads_as_before(world) -> None:
    c, root = world
    _say(root, "#task check the login timeout")
    c.app.state.store.rebuild()
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME, "created_date": "2611-20",
                                   "created_time": "10:06", "title": "", "tags": "ag_bug"}, headers=VIA)
    assert (r.status_code, r.json()["detail"]) == (422, "an agent task needs a title")


def test_typo_suggestions_cover_keyboard_layout_and_transpositions(world) -> None:
    c, root = world
    for typed, expected in (("гш", "ui"), ("relase", "release"), ("phsae-1", "phase-1")):
        text = f"#now {{lane:{typed}}} task"
        server = tasklib.task_braces(c.app.state.store, A, text)
        hook = capture.task_where(root, HOME, A, text)
        assert hook is not None
        assert server["lane_choice"] == hook["lane_choice"]
        assert server["lane"] == "" and expected in server["lane_choice"]["options"]


def test_agent_lane_can_be_used_refused_as_typo_and_promoted(world) -> None:
    c, root = world
    _ask(root, "#task check the login")
    c.app.state.store.rebuild()

    def create(title: str, lane: str):
        return c.post("/api/tasks", json={"agent_id": A, "project": HOME,
                      "title": title, "tags": "ag_idea", "lane": lane}, headers=VIA)

    first = create("First issue", "bug")
    assert first.status_code == 201, first.text
    assert first.json()["metadata"]["lane_kind"] == "agent"
    other = create("Second issue", "bugs")
    assert other.status_code == 422 and "did you mean bug" in other.text
    exact = create("Use the board spelling", "UI")
    assert exact.status_code == 201 and exact.json()["metadata"]["lane"] == "ui"

    where = capture.task_where(root, HOME, A, "#now {bug} classify the issues")
    assert where and "moves lane „bug“ from agents to the board" in capture.where_notice(where)
    _ask(root, "#now-todo {bug} classify the issues")
    c.app.state.store.rebuild()
    r = create("Classify the issues", "")
    assert r.status_code == 201, r.text
    assert r.json()["metadata"]["lane"] == "bug"
    assert not c.get(f"/api/tasks/{first.json()['metadata']['id']}").json()["metadata"]["lane_kind"]


def test_choose_lane_in_place_after_the_operator_writes_again(world) -> None:
    c, root = world
    _say(root, "#now-todo {ui2} make the timeline readable", minutes_ago=5)
    c.app.state.store.rebuild()
    cards = c.get("/api/tasks", params={"project": HOME}).json()["tasks"]
    card = next(t for t in cards if "timeline" in t["title"])
    assert json.loads(card["lane_choice"]) == {"name": "ui2", "options": ["ui"]}
    _ask(root, "Use the existing lane")
    path = f"/api/tasks/{card['id']}/lane-choice"
    assert c.post(path, json={"lane": "elsewhere"}).status_code == 422
    assert c.post(path, json={"lane": "ui"}).status_code == 200
    kept = c.get(f"/api/tasks/{card['id']}").json()
    assert kept["metadata"]["lane"] == "ui" and not kept["metadata"]["lane_choice"]
    assert "#now-todo {ui2} make the timeline readable" in json.dumps(kept)


def test_empty_operator_lane_is_known_to_both_writers(world) -> None:
    c, root = world
    path = "/api/tasks/lanes"
    assert c.post(path, json={"project": HOME, "lane": "Design system", "op": "add"}).status_code == 200
    assert "Design system" in c.get(path, params={"project": HOME}).json()["lanes"]
    text = "#task {design systm} create tokens"
    server = tasklib.task_braces(c.app.state.store, A, text)
    hook = capture.task_where(root, HOME, A, text)
    assert hook and hook["lane_choice"] == server["lane_choice"]
    assert server["lane_choice"]["options"] == ["Design system"]


@pytest.mark.parametrize("actor", ["operator", A])
def test_moving_a_card_inherits_only_the_destination_lane_kind(world, actor: str) -> None:
    c, root = world
    _ask(root, "file the sound tasks")
    c.app.state.store.rebuild()
    assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": 3}).status_code == 200
    incoming = c.post("/api/tasks", json={"project": HOME, "title": "Move sound", "lane": "Audio"})
    existing = c.post("/api/tasks", json={"agent_id": A, "project": MEMBER,
                      "title": "Agent sound", "lane": "audio", "tags": "ag_bug"}, headers=VIA)
    assert incoming.status_code == existing.status_code == 201, (incoming.text, existing.text)
    task_id = incoming.json()["metadata"]["id"]
    moved = c.post(f"/api/tasks/{task_id}/move", json={"actor": actor, "to": MEMBER},
                   headers=VIA if actor == A else {})
    assert moved.status_code == 200, moved.text
    metadata = c.get(f"/api/tasks/{task_id}").json()["metadata"]
    assert (metadata["lane"], metadata["lane_kind"]) == ("audio", "agent")
    assert tasklib._board_lanes(c.app.state.store, MEMBER)["audio"] == "agent"


def test_a_lane_only_brace_cannot_promote_in_another_member_project(world) -> None:
    c, root = world
    _ask(root, "file the sound tasks")
    c.app.state.store.rebuild()
    assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": 3}).status_code == 200
    for project in (HOME, MEMBER):
        card = c.post("/api/tasks", json={"agent_id": A, "project": project,
                      "title": "Agent sound", "lane": "audio", "tags": "ag_bug"}, headers=VIA)
        assert card.status_code == 201, card.text
    _ask(root, "#task {audio} retake sound")
    card = {"agent_id": A, "title": "Retake sound", "tags": "ag_bug"}
    wrong = c.post("/api/tasks", json={**card, "project": MEMBER}, headers=VIA)
    assert wrong.status_code == 403 and HOME in wrong.text
    right = c.post("/api/tasks", json={**card, "project": HOME}, headers=VIA)
    assert right.status_code == 201, right.text
    assert "moved from agents" in right.json()["lane_notice"]
    assert tasklib._board_lanes(c.app.state.store, MEMBER)["audio"] == "agent"


def test_project_question_survives_a_lane_typo_in_the_same_message(world) -> None:
    c, root = world
    text = "#now-todo {release} {ui2} check the player"
    where = capture.task_where(root, HOME, A, text)
    assert where is not None
    notice = capture.where_notice(where)
    question = "did you mean project writing-tracker or lane release?"
    assert question in notice and notice.index(question) < notice.index("use its lane chip")

    _ask(root, text)
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME,
              "title": "Check the player", "tags": "ag_bug"}, headers=VIA)
    assert r.status_code == 201, r.text
    out = r.json()
    assert question in out["ask"]
    assert "use its lane chip" in out["lane_notice"]
    assert out["metadata"]["lane"] == "Now"


def test_two_distinct_fuzzy_lane_groups_are_refused_without_filing(world) -> None:
    c, root = world
    text = "#now-todo {ui2} {lane:relase} check two lanes"
    where = capture.task_where(root, HOME, A, text)
    assert where and "two lanes in braces" in where["refusal"]
    _ask(root, text)
    r = c.post("/api/tasks", json={"agent_id": A, "project": HOME,
              "title": "Check two lanes", "tags": "ag_bug"}, headers=VIA)
    assert r.status_code == 403 and "two lanes in braces" in r.text


@pytest.mark.parametrize(("canonical", "alternative"), [("Straße", "STRASSE"), ("Café", "Cafe\u0301")])
def test_lane_matching_folds_case_and_unicode_for_braces_and_fields(world, canonical, alternative) -> None:
    c, root = world
    r = c.post("/api/tasks/lanes", json={"project": HOME, "lane": canonical, "op": "add"})
    assert r.status_code == 200, r.text
    where = capture.task_where(root, HOME, A, f"#task {{lane:{alternative}}} check the lane")
    assert where and where["lane"] == canonical
    _ask(root, "file where it belongs")
    created = c.post("/api/tasks", json={"agent_id": A, "project": HOME,
                     "title": "Check the lane", "tags": "ag_bug", "lane": alternative}, headers=VIA)
    assert created.status_code == 201, created.text
    assert created.json()["metadata"]["lane"] == canonical
    assert not created.json()["metadata"]["lane_kind"]


def test_legacy_empty_lane_preferences_migrate_to_project_lanes(tmp_path: Path) -> None:
    root = tmp_path / "data"
    for code in (HOME, MEMBER):
        (root / "projects" / code).mkdir(parents=True)
    (root / "boards.json").write_text(json.dumps({"boards": [
        {"id": "bd_demo", "projects": [MEMBER, HOME]},
    ]}), encoding="utf-8")
    (root / "ui_prefs.json").write_text(json.dumps({
        f"sp-lanes:{HOME}": '["Empty studio"]',
        "sp-lanes:bd_demo": '["Sound review"]',
    }), encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for code, lane in ((HOME, "Empty studio"), (MEMBER, "Sound review")):
            assert c.get("/api/tasks/lanes", params={"project": code}).json()["lanes"] == [lane]
        imported = c.post("/api/prefs", json={"values": {f"sp-lanes:{MEMBER}": '["Local notes"]'}})
        assert imported.status_code == 200
        assert set(c.get("/api/tasks/lanes", params={"project": MEMBER}).json()["lanes"]) == {"Sound review", "Local notes"}
        assert c.post("/api/tasks/lanes", json={"project": HOME, "lane": "Empty studio", "op": "remove"}).status_code == 200
    with TestClient(create_app(data_root=root, watch=False)) as c:
        assert c.get("/api/tasks/lanes", params={"project": HOME}).json()["lanes"] == []


def test_an_agent_cannot_import_operator_lane_preferences(world) -> None:
    c, _root = world
    assert c.post("/api/settings", json={"values": {"agents.mcp_only": False}}).status_code == 200
    key = f"sp-lanes:{HOME}"
    r = c.post("/api/prefs", json={"agent_id": A, "values": {key: '["An agent lane"]'}}, headers=VIA)
    assert r.status_code in (403, 422), r.text
    assert key not in c.get("/api/prefs").json()["prefs"]



def test_cross_project_move_retires_a_lane_choice_from_the_old_board(world) -> None:
    c, root = world
    _ask(root, "#now-todo {ui2} make the player readable")
    posted = c.post("/api/tasks", json={"agent_id": A, "project": HOME,
                    "title": "Readable player", "tags": "ag_bug"}, headers=VIA)
    assert posted.status_code == 201, posted.text
    metadata = posted.json()["metadata"]
    assert metadata["lane_choice"]
    path = f"/api/tasks/{metadata['id']}"
    moved = c.post(f"{path}/move", json={"to": MEMBER})
    assert moved.status_code == 200, moved.text
    stored = c.get(path).json()["metadata"]
    assert stored["project"] == MEMBER
    assert not stored["lane_choice"]
    assert c.post(f"{path}/lane-choice", json={"lane": "ui2"}).status_code == 409
