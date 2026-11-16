"""The task window's full view: each turn that named the task, once, whole."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app

AGENT = "cc-full0001"


def test_full_gives_each_turn_once_with_both_sides_whole(tmp_path: Path) -> None:
    root = tmp_path / "data"
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    long = "line one\n" + "x" * 500
    (d / "chat.md").write_text(
        f"# Chat log — {AGENT}\n"
        "\n## Turn 1 · 2026-09-01T10:01:00\n**User**: look at tk_abcd1234 please\n"
        f"**Agent**: tk_abcd1234 is about the switch. {long}\n"
        "\n## Turn 2 · 2026-09-01T10:02:00\n**User**: nothing here\n**Agent**: ok\n"
        "\n## Turn 3 · 2026-09-01T10:03:00\n**User**: and tk_abcd1234 again\n**Agent**: fine\n",
        encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        plain = c.get("/api/tasks/tk_abcd1234/mentions").json()
        assert plain["total"] == 3 and "turns" not in plain
        turns = c.get("/api/tasks/tk_abcd1234/mentions?full=1").json()["turns"]
    got = {t["turn"]: (t["why"], sorted(t["roles"])) for t in turns}
    assert got == {1: ("mention", ["agent", "user"]), 2: ("next", []), 3: ("mention", ["user"])}
    first = next(t for t in turns if t["turn"] == 1)
    assert first["said"] == "look at tk_abcd1234 please"
    assert first["reply"].endswith("x" * 500) and "line one" in first["reply"]
    assert first["agent"]["agent_id"] == AGENT


def _chat(root: Path, turns: list[tuple[str, str]]) -> None:
    d = root / "projects" / "alpha" / "chats" / AGENT
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        "agent_id": AGENT, "agent_name": "lead", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T11:00:00",
    }), encoding="utf-8")
    body = [f"# Chat log — {AGENT}\n"]
    for i, (user, agent) in enumerate(turns, start=1):
        body.append(f"\n## Turn {i} · 2026-09-01T10:{i:02d}:00\n**User**: {user}\n**Agent**: {agent}\n")
    (d / "chat.md").write_text("".join(body), encoding="utf-8")


def _thread(root: Path, task: str) -> dict:
    with TestClient(create_app(data_root=root, watch=False)) as c:
        c.get(f"/api/done-tags?agent_id={AGENT}")
        return c.get(f"/api/tasks/{task}/mentions?full=1").json()


def test_the_done_stretch_and_the_turns_up_to_the_next_task(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    with TestClient(create_app(data_root=root, watch=False)) as c:
        a, b = (c.post("/api/tasks", json={"created_date": "2609-01", "created_time": f"09:0{i}", "project": "alpha",
                                          "agent_id": "operator", "title": n, "status": "doing"}).json()["metadata"]["id"]
                for i, n in enumerate(("A", "B")))
    _chat(root, [
        (f"{a} build it", "on it"), ("more", "done"), ("#done", "closed"),       # 1–3: A's stretch
        (f"{b} next one", f"ok; {a} was easier"),                                # 4: B; A named only by the agent
        ("go on", "ok"), (f"back to {a}", "sure"), ("tweak", "done"),            # 6: A again, no #done after
        (f"{b} again", "ok"), ("more on B", "ok"),                               # 8: the operator names B
    ])
    got = _thread(root, a)
    why = {t["turn"]: t["why"] for t in got["turns"]}
    assert why == {1: "mention", 2: "done", 3: "done", 4: "mention", 6: "mention", 7: "next"}
    assert (got["done_turns"], got["next_turns"], got["has_done"]) == (2, 1, True)


def test_no_done_means_no_done_stretch(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    _chat(root, [("look at tk_abcd1234", "ok"), ("and this", "ok")])
    got = _thread(root, "tk_abcd1234")
    assert (got["done_turns"], got["next_turns"], got["has_done"]) == (0, 1, False)


def test_the_full_thread_answers_anew_when_done_or_now_csv_changes(tmp_path: Path) -> None:
    """The thread reads done.csv and now.csv: a write to either is a new
    answer, not a 304 with the old stretches."""
    import os
    import time

    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    _chat(root, [("look at tk_abcd1234", "ok")])
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for name in ("done.csv", "now.csv"):
            url = "/api/tasks/tk_abcd1234/mentions?full=1"
            tag = c.get(url).headers["etag"]
            assert c.get(url, headers={"If-None-Match": tag}).status_code == 304
            f = root / name
            f.write_text("id\n", encoding="utf-8")
            later = time.time() + 5
            os.utime(f, (later, later))
            c.app.state.store.rebuild()
            assert c.get(url, headers={"If-None-Match": tag}).status_code == 200, name
