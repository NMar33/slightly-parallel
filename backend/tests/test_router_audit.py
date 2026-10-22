"""The router audit of 2026-10-04: one test per bug it found.

Each of these failed before its fix. They are kept together because they
share one small data root and because the list is the audit's record.
"""

from __future__ import annotations

import csv
import json
import threading
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import csvio
from backend.server import create_app
from tests.conftest import make_task


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent(root: Path, aid: str, chat: str = "") -> None:
    folder = root / "projects" / "alpha" / "chats" / aid
    _write(folder / "meta.json", json.dumps({
        "agent_id": aid, "agent_name": aid, "project": "alpha",
        "created_date": "2608-20", "last_active": "2026-08-21T12:00:00",
        "tool": "claude-code", "cwd": "/work/alpha", "session_ref": "abc-123",
    }))
    _write(folder / "chat.md", chat or f"# Chat log — {aid}\n\n---\n")


CHAT = """# Chat log — cc-one
*Started 2026-08-20T09:00:00. Verbatim captured turns.*

---

## Turn 1 · 2026-08-20T09:00:00
**User**: please look at the "sidebar" first
**Agent**: on it, task-id noted

## Turn 2 · 2026-08-20T09:20:00
**User**: and then the footer
**Agent**: done
"""


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def client(root: Path):
    _agent(root, "cc-one", chat=CHAT)
    _agent(root, "cc-two")
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# 1 — an update of one level keeps the others ------------------------------


def test_update_of_one_level_keeps_the_levels_not_sent(client: TestClient) -> None:
    r = client.post("/api/decisions", json={
        "created_date": "2610-04", "created_time": "10:00", "project": "alpha",
        "agent_id": "operator", "l1": "Pick A", "l2": "because",
        "l3": ["B — rejected: slow"], "l4": "the long text",
    })
    did = r.json()["metadata"]["id"]
    assert client.post(f"/api/decisions/{did}/update", json={"l2": "because, reworded"}).status_code == 200
    got = client.get(f"/api/decisions/{did}").json()
    assert got["l2"] == "because, reworded"
    assert got["l3"] == ["B — rejected: slow"]
    assert got["l4"] == "the long text"


# 2 — two scans in one minute ----------------------------------------------


def test_two_scans_in_one_minute_keep_their_own_text(client: TestClient) -> None:
    body = {"created_date": "2610-04", "created_time": "11:00", "project": "alpha",
            "agent_id": "cc-one", "l1": "first summary", "l2": "why one", "l3": ["d1"], "l4": "p1"}
    one = client.post("/api/scans", json=body).json()["metadata"]
    two = client.post("/api/scans", json={**body, "l1": "second summary", "l2": "why two"}).json()["metadata"]
    assert one["id"] != two["id"]
    assert one["md_ref"] != two["md_ref"]
    assert client.get(f"/api/scans/{one['id']}").json()["l2"] == "why one"
    assert client.get(f"/api/scans/{two['id']}").json()["l2"] == "why two"


# 3 — the MCP gate reads every body FastAPI reads as JSON -------------------


@pytest.mark.parametrize("content_type", ["application/json", "application/vnd.x+json", "application/JSON; charset=utf-8", None])
def test_gate_refuses_an_agent_under_any_json_content_type(client: TestClient, monkeypatch, content_type) -> None:
    from backend import server as _server

    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: True)
    client.headers.pop("X-SP-Via", None)
    tid = make_task(client, "gated")
    req = client.build_request("POST", f"/api/tasks/{tid}/archive", content=json.dumps({"actor": "cc-agent"}))
    req.headers.pop("content-type", None)
    if content_type:
        req.headers["content-type"] = content_type
    r = client.send(req)
    assert r.status_code == 422, r.text
    assert "MCP" in r.json()["detail"]
    assert not client.get(f"/api/tasks/{tid}").json()["metadata"].get("archived_at")


def test_gate_leaves_a_body_that_is_not_json_alone() -> None:
    from backend.server import _json_body

    assert _json_body(b"text/plain") is False
    assert _json_body(b"multipart/form-data; boundary=x") is False
    assert _json_body(b"application/problem+json") is True


# 4 — a refused update writes nothing, the stack's event included ----------


def test_refused_update_leaves_no_stack_event(client: TestClient, root: Path) -> None:
    a, b = make_task(client, "one", position="0"), make_task(client, "two", position="1", created_time="10:01")
    for t in (a, b):
        assert client.post(f"/api/tasks/{t}/update", json={"stack_id": "s1"}).status_code == 200
    r = client.post(f"/api/tasks/{a}/update", json={"status": "doing", "l2": "x"})
    assert r.status_code == 422
    assert "description" in r.json()["detail"]
    assert client.get(f"/api/tasks/{a}").json()["metadata"]["status"] == "todo"
    assert not [e for e in _rows(root / "task_events.csv") if e["field"] == "stack_head_at"]
    # And a move that stands still stamps the next card, once.
    assert client.post(f"/api/tasks/{a}/update", json={"status": "doing"}).status_code == 200
    heads = [e for e in _rows(root / "task_events.csv") if e["field"] == "stack_head_at"]
    assert [(e["task_id"], e["actor"]) for e in heads] == [(b, "stack")]
    assert client.get(f"/api/tasks/{b}").json()["metadata"]["stack_head_at"]


# 5 — a report decides on the row under the lock, and advances the stack ----


def test_report_that_moves_a_card_advances_its_stack(client: TestClient, root: Path) -> None:
    a = make_task(client, "one", status="doing", position="0")
    b = make_task(client, "two", status="doing", position="1", created_time="10:01")
    for t in (a, b):
        client.post(f"/api/tasks/{t}/update", json={"stack_id": "s1"})
    client.post(f"/api/tasks/{a}/update", json={"auto_manage": "yes"})
    r = client.post(f"/api/tasks/{a}/report", json={"agent_id": "cc-one", "summary": "shipped"})
    assert r.status_code == 200 and r.json()["moved"] is True and r.json()["status"] == "review"
    assert client.get(f"/api/tasks/{b}").json()["metadata"]["stack_head_at"]
    assert [e["task_id"] for e in _rows(root / "task_events.csv") if e["field"] == "stack_head_at"] == [b]


def test_report_reads_the_row_not_the_view(client: TestClient, root: Path, monkeypatch) -> None:
    """The operator finished the card after the view was read: the report
    must not pull it back to review."""
    from backend.routers import evidence

    a = make_task(client, "one", status="doing")
    client.post(f"/api/tasks/{a}/update", json={"auto_manage": "yes"})
    real = evidence._task

    def stale(store, task_id):
        row = real(store, task_id)          # the view, as the report read it
        csvio.rewrite_rows(root / "tasks.csv", tuple(row), lambda rows: [
            r.__setitem__("status", "done") for r in rows if r["id"] == task_id] != [])
        return row

    monkeypatch.setattr(evidence, "_task", stale)
    r = client.post(f"/api/tasks/{a}/report", json={"agent_id": "cc-one", "summary": "shipped"})
    assert r.status_code == 200
    assert r.json()["moved"] is False and r.json()["status"] == "done"
    assert client.get(f"/api/tasks/{a}").json()["metadata"]["status"] == "done"


# 6 — the Codex hook is a top-level key, and remove takes the server too ----


def test_codex_notify_is_top_level_and_remove_takes_the_mcp_block(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from backend.routers import setup as setup_router

    cfg = tmp_path / "codex-config.toml"
    monkeypatch.setattr(setup_router, "CODEX_CONFIG_PATH", cfg)
    cfg.write_text('model = "o4"\n\n[projects."/home/x/app"]\ntrust_level = "trusted"\n', encoding="utf-8")

    assert client.post("/api/setup/codex", json={"action": "install"}).status_code == 200
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert any("codex-capture.py" in part for part in data["notify"])
    assert "notify" not in data["projects"]["/home/x/app"]
    assert data["projects"]["/home/x/app"]["trust_level"] == "trusted"
    assert "slightly-parallel" in data["mcp_servers"]
    # A second install changes nothing.
    assert client.post("/api/setup/codex", json={"action": "install"}).json()["file_action"] == "unchanged"

    assert client.post("/api/setup/codex", json={"action": "remove"}).status_code == 200
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert "notify" not in data and "mcp_servers" not in data
    assert data["model"] == "o4" and data["projects"]["/home/x/app"]["trust_level"] == "trusted"


def test_codex_reinstall_lifts_a_notify_written_under_a_table(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from backend.routers import setup as setup_router

    cfg = tmp_path / "codex-config.toml"
    monkeypatch.setattr(setup_router, "CODEX_CONFIG_PATH", cfg)
    line = setup_router._codex_notify_line(client.app.state.settings.data_root)
    cfg.write_text(f'[projects."/x"]\ntrust_level = "trusted"\n\n{line}\n', encoding="utf-8")
    assert client.post("/api/setup/codex", json={"action": "install"}).status_code == 200
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert "notify" in data and "notify" not in data["projects"]["/x"]


# 7 — one post per story request -------------------------------------------


def _story_request(client: TestClient, tid: str) -> str:
    r = client.post(f"/api/tasks/{tid}/story-requests", json={"type": "release", "focus": "the point"})
    assert r.status_code == 201, r.text
    return r.json()["request"]["id"]


def test_story_post_on_a_request_cancelled_meanwhile_writes_nothing(client: TestClient, root: Path, monkeypatch) -> None:
    from backend.routers import story_release

    tid = make_task(client, "story")
    rid = _story_request(client, tid)
    real = story_release._task

    def cancel_then_read(store, task_id):
        # Runs after the post looked at the request in the view: the
        # operator cancels it in that gap.
        story_release._set_request(store, rid, lambda r: r.update(status="cancelled"))
        return real(store, task_id)

    monkeypatch.setattr(story_release, "_task", cancel_then_read)
    r = client.post(f"/api/tasks/{tid}/story", json={"request_id": rid, "agent_id": "cc-one", "body": "the piece"})
    assert r.status_code == 409, r.text
    assert _rows(root / "task_notes.csv") == []
    assert [x["status"] for x in _rows(root / "story_requests.csv")] == ["cancelled"]


def test_story_post_fulfils_once_and_a_failed_write_reopens(client: TestClient, root: Path, monkeypatch) -> None:
    from backend.routers import story_release

    tid = make_task(client, "story")
    rid = _story_request(client, tid)
    body = {"request_id": rid, "agent_id": "cc-one", "body": "the piece"}

    def boom(*a, **k):
        raise OSError("disk full")

    with monkeypatch.context() as mp:
        mp.setattr(story_release, "_write_story", boom)
        with pytest.raises(OSError):
            client.post(f"/api/tasks/{tid}/story", json=body)
    assert [x["status"] for x in _rows(root / "story_requests.csv")] == ["open"]

    assert client.post(f"/api/tasks/{tid}/story", json=body).status_code == 201
    assert client.post(f"/api/tasks/{tid}/story", json=body).status_code == 409
    assert len(_rows(root / "task_notes.csv")) == 1


# 8 — the look and the append are one locked step ---------------------------


def test_append_if_absent_writes_one_row_for_many_writers(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    row = {"id": "x1", "v": "a"}
    out: list = []
    barrier = threading.Barrier(12)

    def post() -> None:
        barrier.wait()
        out.append(csvio.append_if_absent(path, ("id", "v"), row))

    threads = [threading.Thread(target=post) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(_rows(path)) == 1
    assert sum(1 for o in out if o is None) == 1          # one wrote it
    assert all(o == row for o in out if o is not None)     # the rest read it back


def test_append_if_absent_matches_by_what_the_caller_says(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    assert csvio.append_if_absent(path, ("id", "a", "b"), {"id": "1", "a": "x", "b": "y"}) is None
    hit = csvio.append_if_absent(path, ("id", "a", "b"), {"id": "2", "a": "x", "b": "y"},
                                 lambda r: r.get("a") == "x" and r.get("b") == "y")
    assert hit is not None and hit["id"] == "1"
    assert len(_rows(path)) == 1


def test_creates_look_under_the_lock(client: TestClient, root: Path) -> None:
    """Each create is refused its own pre-check (a stale view, a file read a
    moment ago) by writing the row behind its back first: one row stays."""
    a, b = make_task(client, "one"), make_task(client, "two", created_time="10:01")
    # A task link written by the other request between this one's read and its append.
    from backend.routers import task_links
    real = task_links._link_refusal

    def other_request_wins(rows, x, y, kind, store):
        csvio.append_row(root / "task_links.csv", task_links.TASK_LINK_COLUMNS,
                         {"id": "lk_other", "from_id": x, "to_id": y, "kind": kind, "created_at": "t", "actor": "operator"})
        return real(rows, x, y, kind, store)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(task_links, "_link_refusal", other_request_wins)
        r = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks"})
    assert r.status_code == 200 and r.json()["existing"] is True and r.json()["link"]["id"] == "lk_other"
    assert len(_rows(root / "task_links.csv")) == 1

    # The same note twice is one note, and the same evidence twice one item.
    note = {"type": "report", "body": "what shipped"}
    assert client.post(f"/api/tasks/{a}/notes", json=note).status_code == 201
    assert client.post(f"/api/tasks/{a}/notes", json=note).json()["existing"] is True
    assert len(_rows(root / "task_notes.csv")) == 1
    ev = {"agent_id": "cc-one", "items": [{"kind": "text", "title": "t", "body": "proof"}]}
    assert client.post(f"/api/tasks/{a}/evidence", json=ev).status_code == 201
    assert client.post(f"/api/tasks/{a}/evidence", json=ev).status_code == 200
    assert len(_rows(root / "task_evidence.csv")) == 1


# 9 — an agent link's id follows its kind -----------------------------------


def test_agent_link_kind_change_moves_its_id(client: TestClient, root: Path) -> None:
    kinds = client.get("/api/agents/links?project=alpha").json()["kinds"]
    k1, k2 = kinds[0], kinds[1]
    first = client.post("/api/agents/links", json={"from": "cc-one", "to": "cc-two", "kind": k1}).json()["link"]
    moved = client.post(f"/api/agents/links/{first['id']}/update", json={"kind": k2})
    assert moved.status_code == 200
    assert moved.json()["link"]["id"] != first["id"]
    again = client.post("/api/agents/links", json={"from": "cc-one", "to": "cc-two", "kind": k1})
    assert again.status_code == 201
    ids = [r["id"] for r in _rows(root / "agent_links.csv")]
    assert len(ids) == 2 and len(set(ids)) == 2
    # And a change into a shape that exists is refused.
    clash = client.post(f"/api/agents/links/{again.json()['link']['id']}/update", json={"kind": k2})
    assert clash.status_code == 409


# 10 — a filter matches a whole member --------------------------------------


def test_sprint_project_filter_is_a_whole_code(client: TestClient) -> None:
    for name, projects in (("Mine", "p1"), ("Other", "p10"), ("Both", "p10, p1")):
        r = client.post("/api/sprints", json={"name": name, "projects": projects, "started_date": "2610-01",
                                              "status": "active", "created_date": "2610-01"})
        assert r.status_code == 201, r.text
    names = {s["name"] for s in client.get("/api/sprints?project=p1").json()["sprints"]}
    assert names == {"Mine", "Both"}


def test_library_tag_filter_is_a_whole_tag(client: TestClient) -> None:
    for i, tags in enumerate(("ui", "ui-kit", "backend,ui", "docs ui")):
        r = client.post("/api/ideas", json={"created_date": "2610-04", "created_time": f"10:0{i}", "project": "alpha",
                                            "agent_id": "operator", "l1": f"idea {i}", "tags": tags})
        assert r.status_code == 201, r.text
    got = {i["tags"] for i in client.get("/api/ideas?tag=ui").json()["ideas"]}
    assert got == {"ui", "backend,ui", "docs ui"}


# 11 — the find reads what was said -----------------------------------------


def test_sessions_find_reads_the_turns_not_their_json(client: TestClient) -> None:
    def find(q: str) -> list[dict]:
        return client.get("/api/sessions", params={"q": q}).json()["sessions"]

    assert find("user") == []                      # a key of the JSON, said by nobody
    assert find("task_id") == []                   # `_` is a letter here, not a wildcard
    hit = find('the "sidebar" first')              # a quote in the text is found
    assert len(hit) == 1 and hit[0]["matches"] == 1
    assert [s["matches"] for s in find("footer")] == [1]
    assert all("turns_json" not in s for s in hit)


# 12 — the smart timer follows the data root --------------------------------


def test_data_root_swap_moves_the_smart_timer(client: TestClient, tmp_path: Path) -> None:
    from backend import timeauto

    app = client.app
    old = timeauto.of(app)
    new_root = tmp_path / "new-root"
    new_root.mkdir()
    app.state.swap_data_root(new_root)
    timer = timeauto.of(app)
    assert timer is not old
    assert timer.root == new_root and timer.store is app.state.store


# 13 — a stop counts the pause written since the row was read ---------------


def test_stop_counts_a_pause_written_after_the_row_was_read(client: TestClient, root: Path, monkeypatch) -> None:
    from backend.routers import time_tracking

    eid = client.post("/api/time/start", json={"project": "alpha"}).json()["id"]
    now = datetime.now().replace(microsecond=0)
    started, paused = now - timedelta(hours=2), now - timedelta(hours=1)
    cols = time_tracking.ENT.columns
    csvio.rewrite_rows(root / time_tracking.ENT.csv, cols, lambda rows: [
        r.__setitem__("started_at", started.isoformat()) for r in rows] != [])
    client.app.state.store.rebuild()
    real = time_tracking._load

    def stale(store, entry_id):
        row = real(store, entry_id)      # running, as the request read it
        # The smart timer's thread pauses the entry in that gap.
        csvio.rewrite_rows(root / time_tracking.ENT.csv, cols, lambda rows: [
            r.__setitem__("paused_at", paused.isoformat()) for r in rows if r["id"] == entry_id] != [])
        return row

    with monkeypatch.context() as mp:
        mp.setattr(time_tracking, "_load", stale)
        r = client.post(f"/api/time/{eid}/stop", json={})
    assert r.status_code == 200, r.text
    row = next(x for x in _rows(root / time_tracking.ENT.csv) if x["id"] == eid)
    # One hour worked, one hour away: not two hours of work.
    assert 59 <= int(row["duration_min"]) <= 61
    assert int(row["paused_total_sec"]) >= 3590


# 20 — small ones -----------------------------------------------------------


def test_unmark_of_a_task_that_is_not_there_removes_nothing(client: TestClient) -> None:
    r = client.post("/api/marks/unmark", json={"kind": "task", "target": "tk_nope"})
    assert r.status_code == 200 and r.json() == {"removed": 0}
    tid = make_task(client, "starred")
    client.post("/api/marks", json={"kind": "task", "target": tid})
    assert client.post("/api/marks/unmark", json={"kind": "task", "target": tid}).json()["removed"] == 1


# 15, 18 — what is kept between requests is dropped when the data moves -----


def test_adoption_runs_once_per_state_of_the_data(client: TestClient, monkeypatch) -> None:
    from backend import keeplib

    calls: list[int] = []
    real = keeplib.adopt
    monkeypatch.setattr(keeplib, "adopt", lambda store: calls.append(1) or real(store))
    client.get("/api/visions")
    client.get("/api/rules")
    client.get("/api/visions")
    assert len(calls) == 1                      # the same data: adopted once
    make_task(client, "anything")                   # a file moved
    client.get("/api/visions")
    assert len(calls) == 2


def test_a_list_with_its_text_follows_an_edit(client: TestClient) -> None:
    r = client.post("/api/visions", json={"created_date": "2610-04", "created_time": "10:00", "project": "alpha",
                                          "agent_id": "operator", "l1": "A vision", "l2": "first wording"})
    vid = r.json()["metadata"]["id"]

    def listed() -> str:
        return next(v["l2"] for v in client.get("/api/visions?with_l2=1").json()["visions"] if v["id"] == vid)

    assert listed() == "first wording"
    assert listed() == "first wording"          # from the kept parse
    assert client.post(f"/api/visions/{vid}/update", json={"l2": "second wording"}).status_code == 200
    assert listed() == "second wording"


def test_profiles_read_together_equal_profiles_read_alone(client: TestClient) -> None:
    tid = make_task(client, "named")
    client.post("/api/agents/links", json={"from": "cc-one", "to": "cc-two",
                                           "kind": client.get("/api/agents/links?project=alpha").json()["kinds"][0]})
    client.post("/api/decisions", json={"created_date": "2610-04", "created_time": "10:00", "project": "alpha",
                                        "agent_id": "cc-one", "l1": f"about {tid}"})
    roster = {p["agent"]["agent_id"]: p for p in client.get("/api/agents/profiles?project=alpha").json()["profiles"]}
    assert set(roster) == {"cc-one", "cc-two"}
    for aid, together in roster.items():
        assert client.get(f"/api/agents/{aid}/profile").json() == together
    assert roster["cc-one"]["totals"]["decisions_n"] == 1 and roster["cc-two"]["totals"]["decisions_n"] == 0
    assert roster["cc-one"]["totals"]["links_n"] == 1 and roster["cc-two"]["totals"]["links_n"] == 1
