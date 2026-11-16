"""Review of d08b7f4 (a task's stretch is the operator's): edge cases."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_commit_tasks import _commit, _project, _talk, _task


def _subjects(client: TestClient, tid: str) -> list[str]:
    return sorted(c["subject"] for c in client.get(f"/api/tasks/{tid}/work").json()["work"]["commit_list"])


def test_a_filing_turn_after_a_pause_does_not_carry_the_stretch_on(client: TestClient, data_root: Path) -> None:
    """A turn that only files a task "opens no stretch and closes none" — yet
    its mention puts the session into named_in, so after a pause the old
    stretch goes on into it."""
    repo = _project(client, data_root)
    a = _task(client, "A")
    t0 = datetime.now() - timedelta(hours=6)
    later = t0 + timedelta(hours=4)
    _commit(repo, "x.py", "unrelated work after the pause", later + timedelta(minutes=12), data_root.parent)
    _talk(data_root, "cc-f", repo, [
        (t0, f"take {a}", "on it"),
        (later, f"#task a follow-up to {a}: write the docs", "filed"),
        (later + timedelta(minutes=10), "now fix the css", "on it"),
        (later + timedelta(minutes=20), "thanks", "done"),
    ])
    client.app.state.store.rebuild()
    assert _subjects(client, a) == []


def test_an_old_now_task_named_in_a_now_turn_opens_no_stretch(client: TestClient, data_root: Path) -> None:
    """_now_started takes every task ever started with #now, not the one this
    #now turn started: the agent naming an older one in its answer opens it."""
    from backend.taskevents import append_events

    repo = _project(client, data_root)
    old = _task(client, "Old")
    append_events(client.app.state.store, old, "operator",
                  [("started", "", "in the chat, with #now (written by cc-elsewhere)")])
    t0 = datetime.now() - timedelta(minutes=40)
    _commit(repo, "f.py", "footer work", t0 + timedelta(minutes=3), data_root.parent)
    _talk(data_root, "cc-o", repo, [
        (t0, "#now fix the footer", f"filed tk_newcard; related: {old}"),
        (t0 + timedelta(minutes=10), "ok", "done"),
    ])
    client.app.state.store.rebuild()
    assert _subjects(client, old) == []


def test_a_server_written_now_card_for_another_task_closes_the_stretch(client: TestClient, data_root: Path) -> None:
    """The #now that started task B (card written by the server, so no
    mention) should close A's stretch; only task_mentions rows are boundaries."""
    repo = _project(client, data_root)
    a, b = _task(client, "A"), _task(client, "B")
    # Yesterday at noon: a chat built around "now" crossed midnight in a run
    # after 00:00, split into two sessions, and the now.csv row below named
    # the wrong one.
    t0 = datetime.combine(datetime.now().date() - timedelta(days=1), datetime.min.time()).replace(hour=12)
    _commit(repo, "a.py", "A work", t0 + timedelta(minutes=3), data_root.parent)
    _commit(repo, "b.py", "B work", t0 + timedelta(minutes=13), data_root.parent)
    _talk(data_root, "cc-s", repo, [
        (t0, f"take {a}", "on it"),
        (t0 + timedelta(minutes=10), "#now fix the header", "working"),
        (t0 + timedelta(minutes=20), "ok", "done"),
    ])
    client.app.state.store.rebuild()
    sid = client.app.state.store.query("SELECT id FROM sessions WHERE agent_id = 'cc-s'")[0]["id"]
    (data_root / "now.csv").write_text(
        "id,task_id,project,agent_id,session_id,turn,at,applied_at,column,result\n"
        f"nw_1,{b},ALPHA,cc-s,{sid},2,,,doing,\n", encoding="utf-8")
    client.app.state.store.rebuild()
    assert _subjects(client, a) == ["A work"]
