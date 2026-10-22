"""Agent profiles, groups and the links drawn between lanes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent(root: Path, aid: str, chat: str = "", **meta: object) -> None:
    folder = root / "projects" / "alpha" / "chats" / aid
    _write(folder / "meta.json", json.dumps({
        "agent_id": aid, "agent_name": aid, "project": "alpha",
        "created_date": "2608-20", "last_active": "2026-08-21T12:00:00",
        "message_count": 3, "tool": "claude-code", "cwd": "/work/alpha",
        "session_ref": "abc-123", **meta,
    }))
    _write(folder / "chat.md", chat or f"# Chat log — {aid}\n\n---\n")


CHAT = """# Chat log — cc-one
*Started 2026-08-20T09:00:00. Verbatim captured turns.*

---

## Turn 1 · 2026-08-20T09:00:00
**User**: please do tk_aaaa1111 first
**Agent**: on it

## Turn 2 · 2026-08-20T09:20:00
**User**: and then tk_bbbb2222
**Agent**: tk_aaaa1111 is done, starting tk_bbbb2222

## Turn 3 · 2026-08-21T22:10:00
**User**: how is it going
**Agent**: tk_bbbb2222 shipped
"""


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def client(root: Path):
    _agent(root, "cc-one", chat=CHAT)
    _agent(root, "cc-two", parent_agent_id="cc-one", created_date="2608-21")
    _agent(root, "cc-three")
    (root / "projects" / "beta").mkdir(parents=True)
    _write(root / "projects" / "beta" / "chats" / "cc-beta" / "meta.json", json.dumps({
        "agent_id": "cc-beta", "project": "beta", "created_date": "2608-20",
    }))
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, tid_title: str, status: str) -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2608-19", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "title": tid_title, "status": status,
    })
    assert r.status_code == 201
    return r.json()["metadata"]["id"]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def test_profile_joins_everything_the_agent_left_behind(client: TestClient, root: Path) -> None:
    # Entries under the agent's id. Tasks named in its turns need to exist
    # to count as mentions — mint two with the ids the chat uses.
    for body in (
        {"lens": "scans", "l1": "first checkpoint", "files_n": 4, "lines_add": 120, "lines_del": 30},
        {"lens": "scans", "l1": "second checkpoint", "files_n": 2, "lines_add": 10, "lines_del": 5},
    ):
        r = client.post("/api/scans", json={
            "created_date": "2608-20", "created_time": "10:00", "project": "alpha",
            "agent_id": "cc-one", "l1": body["l1"], "files_n": body["files_n"],
            "lines_add": body["lines_add"], "lines_del": body["lines_del"],
            "decisions_n": 0, "l2": "x", "l3": ["y"], "l4": "z",
        })
        assert r.status_code == 201, r.text
    r = client.post("/api/architecture", json={
        "created_date": "2608-20", "created_time": "11:00", "project": "alpha",
        "agent_id": "cc-one",
        "checked": ["owes", "runs", "stores", "talks", "built with", "faces", "holds"],
        "changes": [{"op": "add", "type": "feature", "name": "Timeline links",
                     "path": ["frontend/src/x.tsx"], "surface": "timeline"}],
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/problems", json={
        "created_date": "2608-20", "created_time": "11:30", "project": "alpha",
        "agent_id": "cc-one", "l1": "Stop hook lost the reply", "severity": "high",
        "status": "resolved", "resolved_date": "2608-20", "l2": "x", "l3": ["y"], "l4": "z",
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/decisions", json={
        "created_date": "2608-20", "created_time": "12:00", "project": "alpha",
        "agent_id": "cc-one", "l1": "Links live in a ledger", "decision_text": "Links live in a ledger",
        "rationale": "append-only", "l2": "x", "l3": ["y"], "l4": "z",
    })
    assert r.status_code == 201, r.text

    # The tasks the chat names must exist to count as mentions. Ids are
    # minted by the API, so mint two, then write the chat with those ids and
    # trigger a rebuild (the watcher is off in tests) through a write.
    a = _task(client, "A", "done")
    b = _task(client, "B", "doing")
    chat_path = root / "projects" / "alpha" / "chats" / "cc-one" / "chat.md"
    chat_path.write_text(CHAT.replace("tk_aaaa1111", a).replace("tk_bbbb2222", b), encoding="utf-8")
    assert client.post("/api/agents/cc-three/group", json={"group": "tmp"}).status_code == 200

    p = client.get("/api/agents/cc-one/profile")
    assert p.status_code == 200, p.text
    d = p.json()
    t = d["totals"]
    assert d["agent"]["agent_id"] == "cc-one"
    assert d["origin"]["cwd"] == "/work/alpha" and d["origin"]["tool"] == "claude-code"
    # Two sessions: the 22:10 turn is a day later than the 09:00–09:20 block.
    assert t["sessions_n"] == 2 and t["turns"] == 3 and t["days_active"] == 2
    # Session wall clock 20 + 1; no answer's end is known, so the agent's
    # minutes are an estimate (turn 1 to turn 2) and say so.
    assert (t["session_minutes"], t["minutes"], t["minutes_approx"]) == (20 + 1, 20, True)
    assert (t["scans_n"], t["files_n"], t["lines_add"], t["lines_del"]) == (2, 6, 130, 35)
    assert t["features_n"] == 1 and t["bugs_resolved_n"] == 1 and t["decisions_n"] == 1
    assert d["architecture_kinds"] == {"feature": 1}
    assert d["by_hour"][9] == 2 and d["by_hour"][22] == 1
    assert [x["date"] for x in d["by_day"]] == ["2608-20", "2608-21"]
    assert [c["agent_id"] for c in d["children"]] == ["cc-two"]
    assert d["parent"] is None

    ids = {x["id"]: x for x in d["tasks"]}
    assert set(ids) == {a, b}
    assert ids[a]["handed_n"] == 1 and ids[a]["replied_n"] == 1 and ids[a]["status"] == "done"
    assert ids[b]["handed_n"] == 1 and ids[b]["replied_n"] == 2
    assert t["tasks_n"] == 2 and t["tasks_handed_n"] == 2 and t["tasks_done_n"] == 1


def test_profiles_are_the_whole_roster_and_child_sees_its_parent(client: TestClient) -> None:
    r = client.get("/api/agents/profiles?project=alpha")
    assert r.status_code == 200
    ids = [p["agent"]["agent_id"] for p in r.json()["profiles"]]
    assert ids == ["cc-one", "cc-three", "cc-two"]
    two = next(p for p in r.json()["profiles"] if p["agent"]["agent_id"] == "cc-two")
    assert two["parent"]["agent_id"] == "cc-one"
    assert client.get("/api/agents/nope/profile").status_code == 404


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_group_is_a_label_in_meta_and_members_see_each_other(client: TestClient) -> None:
    for aid in ("cc-one", "cc-two"):
        r = client.post(f"/api/agents/{aid}/group", json={"group": "task turns"})
        assert r.status_code == 200 and r.json()["agent_group"] == "task turns"
    p = client.get("/api/agents/cc-one/profile").json()
    assert p["group"]["name"] == "task turns"
    assert [m["agent_id"] for m in p["group"]["members"]] == ["cc-two"]
    g = client.get("/api/agents/groups?project=alpha").json()["groups"]
    assert [x["name"] for x in g] == ["task turns"]
    assert sorted(m["agent_id"] for m in g[0]["members"]) == ["cc-one", "cc-two"]
    # The project payload carries it too — the timeline reads that.
    agents = client.get("/api/project/alpha").json()["agents"]
    assert {a["agent_id"]: a.get("agent_group") for a in agents}["cc-one"] == "task turns"
    # Empty clears.
    r = client.post("/api/agents/cc-one/group", json={"group": ""})
    assert r.status_code == 200
    assert client.get("/api/agents/cc-one/profile").json()["group"]["name"] == ""
    assert client.post("/api/agents/cc-one/group", json={"group": "x" * 81}).status_code == 422
    assert client.post("/api/agents/nope/group", json={"group": "g"}).status_code == 404


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_link_lifecycle(client: TestClient) -> None:
    r = client.post("/api/agents/links", json={
        "from": "cc-one", "to": "cc-two", "kind": "branch", "note": "branched at /branch minors",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True
    link = body["link"]
    assert link["style"] == "solid"  # the kind's default
    assert link["from"]["agent_id"] == "cc-one" and link["to"]["agent_id"] == "cc-two"
    assert link["id"].startswith("al_")

    # Idempotent on (from, to, kind).
    # A repeat writes nothing, so it answers 200 — the one rule every
    # create follows (routers/deps.create_answer).
    again = client.post("/api/agents/links", json={"from": "cc-one", "to": "cc-two", "kind": "branch"})
    assert again.status_code == 200
    assert again.json()["created"] is False and again.json()["existing"] is True

    # Another kind between the same pair is a second link.
    r2 = client.post("/api/agents/links", json={
        "from": "cc-one", "to": "cc-two", "kind": "same-work", "style": "dashed",
    })
    assert r2.status_code == 201 and r2.json()["created"] is True
    assert r2.json()["link"]["style"] == "dashed"

    listed = client.get("/api/agents/links?project=alpha").json()
    assert listed["total"] == 2
    assert listed["kinds"] == ["branch", "subagent", "handoff", "same-work", "relates"]
    assert listed["styles"] == ["solid", "dashed", "dotted"]

    # Both profiles see them.
    assert client.get("/api/agents/cc-two/profile").json()["totals"]["links_n"] == 2

    # Update style + note; the ends stay.
    u = client.post(f"/api/agents/links/{link['id']}/update", json={"style": "dotted", "note": "n2"})
    assert u.status_code == 200 and u.json()["link"]["style"] == "dotted"
    assert u.json()["link"]["note"] == "n2" and u.json()["link"]["from_id"] == "cc-one"

    d = client.post(f"/api/agents/links/{link['id']}/delete")
    assert d.status_code == 200 and d.json()["deleted"] == link["id"]
    assert client.get("/api/agents/links?project=alpha").json()["total"] == 1
    assert client.post(f"/api/agents/links/{link['id']}/delete").status_code == 404
    assert client.post(f"/api/agents/links/{link['id']}/update", json={"note": "x"}).status_code == 404


def test_link_without_note_reads_back_as_empty_strings(client: TestClient) -> None:
    """An empty CSV cell is NULL to the view; the API must hand pages ""."""
    r = client.post("/api/agents/links", json={"from": "cc-one", "to": "cc-two", "kind": "branch"})
    assert r.status_code == 201
    l = client.get("/api/agents/links?project=alpha").json()["links"][0]
    assert (l["note"], l["from_at"], l["to_at"]) == ("", "", "")
    p = client.get("/api/agents/cc-one/profile").json()["links"][0]
    assert p["note"] == ""


def test_subagent_link_runs_from_the_spawner(client: TestClient) -> None:
    r = client.post("/api/agents/links", json={
        "from": "cc-one", "to": "cc-two", "kind": "subagent", "note": "Agent tool, worktree",
    })
    assert r.status_code == 201, r.text
    assert r.json()["link"]["style"] == "solid"
    assert client.get("/api/agents/cc-two/profile").json()["links"][0]["kind"] == "subagent"


def test_link_validation(client: TestClient) -> None:
    post = lambda **b: client.post("/api/agents/links", json=b)  # noqa: E731
    assert post(**{"from": "cc-one", "to": "cc-one", "kind": "branch"}).status_code == 422
    assert post(**{"from": "cc-one", "to": "cc-two", "kind": "friends"}).status_code == 422
    assert post(**{"from": "cc-one", "to": "cc-two", "kind": "branch", "style": "wavy"}).status_code == 422
    assert post(**{"from": "cc-one", "to": "cc-nope", "kind": "branch"}).status_code == 404
    assert post(**{"from": "cc-one", "to": "cc-beta", "kind": "branch"}).status_code == 422
    assert post(**{"from": "cc-one", "to": "cc-two", "kind": "branch", "note": "x" * 501}).status_code == 422
    assert client.get("/api/agents/links?project=alpha").json()["total"] == 0
