"""#undo: the operator archives entries made by mistake, only on #undo-yes (undolib.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.keeplib import keep_id
from backend.routers.integrate import compose
from backend.server import create_app
from backend.undolib import UNDO_TAG_RE

AGENT = "cc-undo0001"
PASTE = "Announcement draft: we keep the vision with #vision and the rules with #rule, see the post."


def _chat(root: Path, turns: list[str]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, user in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: ok\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root


VS = keep_id("vision", "alpha", AGENT, 1)
RL = keep_id("rule", "alpha", AGENT, 1)


@pytest.mark.parametrize("text,kinds", [
    ("#undo the paste", {"ask"}), ("#UNDO-yes", {"yes"}), ("ok #undo-yes.", {"yes"}),
    ("##undo", set()), ("#undone", set()), ("#undo-yes-please", set()), ("x#undo", set()),
])
def test_the_tags(text, kinds):
    found = {"yes" if m.group(1) else "ask" for m in UNDO_TAG_RE.finditer(text)}
    assert found == kinds


def test_nothing_is_proposed_or_archived_without_a_request(env) -> None:
    c, root = env
    _chat(root, [PASTE, "thanks"])
    r = c.get(f"/api/undo/candidates?agent_id={AGENT}")
    assert r.status_code == 409 and "#undo" in r.json()["detail"]
    assert c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [VS]}).status_code == 409
    assert c.post("/api/undo/apply", json={"agent_id": AGENT}).status_code == 409


def test_ask_choose_confirm_archive_restore(env) -> None:
    c, root = env
    turns = [PASTE, "#undo the tags in the pasted announcement were a mistake"]
    _chat(root, turns)
    got = c.get(f"/api/undo/candidates?agent_id={AGENT}").json()
    assert got["request"]["said"].startswith("the tags in the pasted announcement")
    ids = [e["id"] for e in got["candidates"]]
    assert VS in ids and RL in ids and all(e["this_chat"] for e in got["candidates"][:2])
    assert [e["n"] for e in got["candidates"]] == list(range(1, len(ids) + 1))

    prop = c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [VS, RL]}).json()
    assert "#undo-yes" in prop["confirm"] and VS in prop["confirm"] and "⚠" in prop["confirm"]
    # Not answered yet: refused, and nothing moves.
    r = c.post("/api/undo/apply", json={"agent_id": AGENT})
    assert r.status_code == 409 and "not confirmed" in r.json()["detail"]
    assert VS in [v["id"] for v in c.get("/api/visions?project=alpha").json()["visions"]]

    _chat(root, turns + ["#undo-yes"])
    done = c.post("/api/undo/apply", json={"agent_id": AGENT}).json()
    assert {(a["kind"], a["id"]) for a in done["archived"]} == {("vision", VS), ("rule", RL)}
    assert VS not in [v["id"] for v in c.get("/api/visions?project=alpha").json()["visions"]]
    assert VS in [v["id"] for v in c.get("/api/visions?project=alpha&include_archived=1").json()["visions"]]
    assert c.get(f"/api/rules/{RL}").json()["metadata"]["status"] == "archived"
    # The request is finished: a second apply is refused.
    assert c.post("/api/undo/apply", json={"agent_id": AGENT}).status_code == 409

    c.post("/api/undo/restore", json={"id": VS})
    c.post("/api/undo/restore", json={"id": RL})
    assert VS in [v["id"] for v in c.get("/api/visions?project=alpha").json()["visions"]]
    assert c.get(f"/api/rules/{RL}").json()["metadata"]["status"] == "active"


def test_any_other_answer_cancels(env) -> None:
    c, root = env
    turns = [PASTE, "#undo the paste"]
    _chat(root, turns)
    c.get(f"/api/undo/candidates?agent_id={AGENT}")
    c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [VS]})
    _chat(root, turns + ["yes, go"])
    r = c.post("/api/undo/apply", json={"agent_id": AGENT})
    assert r.status_code == 409 and "cancelled" in r.json()["detail"]
    # A #undo-yes later does not revive it: the operator starts again with #undo.
    _chat(root, turns + ["yes, go", "#undo-yes"])
    assert c.post("/api/undo/apply", json={"agent_id": AGENT}).status_code == 409
    assert VS in [v["id"] for v in c.get("/api/visions?project=alpha").json()["visions"]]


def test_an_archived_vision_leaves_its_set(env) -> None:
    c, root = env
    turns = [PASTE, "#undo the paste"]
    _chat(root, turns)
    c.get(f"/api/undo/candidates?agent_id={AGENT}")
    store = c.app.state.store
    s = {"id": "set_x", "kind": "vision", "name": "Visions", "items": [VS]}
    assert "This set is empty." not in compose(store, s)
    c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [VS]})
    _chat(root, turns + ["#undo-yes"])
    c.post("/api/undo/apply", json={"agent_id": AGENT})
    assert "This set is empty." in compose(store, s)


def test_a_task_made_by_mistake_is_archived(env) -> None:
    c, root = env
    tid = c.post("/api/tasks", json={
        "created_date": "2609-01", "created_time": "10:00", "project": "alpha",
        "agent_id": AGENT, "title": "A card from a pasted #now", "status": "agent", "tags": "ag_idea",
    }).json()["metadata"]["id"]
    turns = ["#undo the card from the paste"]
    _chat(root, turns)
    got = c.get(f"/api/undo/candidates?agent_id={AGENT}").json()
    assert tid in [e["id"] for e in got["candidates"]]
    c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [tid]})
    _chat(root, turns + ["#undo-yes"])
    c.post("/api/undo/apply", json={"agent_id": AGENT})
    assert c.get(f"/api/tasks/{tid}").json()["metadata"]["archived_at"]


def test_an_unknown_or_archived_id_is_refused(env) -> None:
    c, root = env
    _chat(root, [PASTE, "#undo the paste"])
    c.get(f"/api/undo/candidates?agent_id={AGENT}")
    r = c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": ["dc_12345678"]})
    assert r.status_code == 409 and "not an entry" in r.json()["detail"]
    r = c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": ["vs_00000000"]})
    assert r.status_code == 409 and "no such" in r.json()["detail"]


def test_a_now_card_taken_back_with_undo_is_not_written_again(env) -> None:
    """A pasted reply said #now: the agent's card goes with #undo, and the
    server's fallback does not write another for that turn."""
    from datetime import datetime, timedelta
    c, root = env
    (root / "now.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    d = root / "projects" / "alpha" / "chats" / AGENT

    def chat(turns: list[tuple[int, str]]) -> None:
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"agent_id": AGENT, "agent_name": "lead", "project": "alpha",
                                                 "created_date": "2609-01"}), encoding="utf-8")
        at = lambda m: (datetime.now() + timedelta(minutes=m)).isoformat(timespec="seconds")  # noqa: E731
        (d / "chat.md").write_text(f"# Chat log — {AGENT}\n" + "".join(
            f"\n## Turn {i} · {at(m)}\n**User**: {said}\n**Agent**: ok\n" for i, (m, said) in enumerate(turns, 1)),
            encoding="utf-8")

    turns = [(-5, "explain <pasted_content>the #now card</pasted_content>")]
    chat(turns)
    c.app.state.store.rebuild()
    tid = c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:01", "project": "alpha",
                                     "agent_id": AGENT, "title": "the #now card", "tags": "ag_idea"}).json()["metadata"]["id"]
    turns += [(1, "#undo the card from the paste")]
    chat(turns)
    r = c.post("/api/undo/propose", json={"agent_id": AGENT, "ids": [tid]})
    assert r.status_code == 200, r.text
    chat(turns + [(2, "#undo-yes")])
    r = c.post("/api/undo/apply", json={"agent_id": AGENT})
    assert r.status_code == 200 and r.json()["archived"], r.text
    c.app.state.store.rebuild()
    live = [t for t in c.get("/api/tasks?project=alpha").json()["tasks"] if not t.get("archived_at")]
    assert [(t["id"], t["title"]) for t in live] == []
