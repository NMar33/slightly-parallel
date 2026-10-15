"""The second audit of 2026-10-05: one test per bug it found.

Each of these failed before its fix. They share one small data root, as
the first audit's tests do (test_router_audit.py), and the list is the
audit's record.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from tests.conftest import make_task


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _short(d: date) -> str:
    return d.strftime("%y%m-%d")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    return root


@pytest.fixture()
def client(root: Path):
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# 1 — the deck's flow counts a task from the day it joined ------------------


def test_deck_bands_count_a_task_from_its_join(client: TestClient) -> None:
    today = date.today()
    r = client.post("/api/sprints", json={
        "created_date": _short(today - timedelta(days=10)), "started_date": _short(today - timedelta(days=10)),
        "name": "S1", "projects": "alpha", "status": "active", "agent_id": "operator", "project": "alpha",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["metadata"]["id"]
    make_task(client, "old", created_date=_short(today - timedelta(days=10)), sprint_id=sid)
    make_task(client, "new", created_date=_short(today), sprint_id=sid)
    block = client.get("/api/sprints/deck?days=7").json()["blocks"][0]
    bands = {d["date"]: sum(d["bands"].values()) for d in block["series"]}
    # The new task was not on the block a week ago; the old one was.
    assert bands[(today - timedelta(days=6)).isoformat()] == 1
    assert bands[today.isoformat()] == 2


# 2 — a link update decides on the rows under the lock ----------------------


def test_link_update_of_a_link_deleted_meanwhile_is_404(client: TestClient, root: Path, monkeypatch) -> None:
    from backend.routers import tasks_extra

    a, b = make_task(client, "a"), make_task(client, "b")
    lid = client.post(f"/api/tasks/{a}/link", json={"to": b, "kind": "blocks"}).json()["link"]["id"]
    stale = _rows(root / "task_links.csv")
    assert client.post(f"/api/tasks/links/{lid}/delete", json={}).status_code == 200
    # The handler's own read is a moment old: the link is still in it.
    monkeypatch.setattr(tasks_extra, "read_rows", lambda path, *a, **k: [dict(r) for r in stale])
    r = client.post(f"/api/tasks/links/{lid}/update", json={"kind": "relates"})
    assert r.status_code == 404, r.text
    assert _rows(root / "task_links.csv") == []
    events = [e for e in _rows(root / "task_events.csv") if e["field"] == "link"]
    assert all("relates" not in e["new_value"] for e in events)


# 3 — an append after a last line with no line break starts a new line ------


def test_append_after_a_line_with_no_break_keeps_both_rows(tmp_path: Path) -> None:
    from backend import csvio

    p = tmp_path / "t.csv"
    p.write_text("id,a\nx,1", encoding="utf-8")
    csvio.append_row(p, ["id", "a"], {"id": "y", "a": "2"})
    assert csvio.read_rows(p) == [{"id": "x", "a": "1"}, {"id": "y", "a": "2"}]
    q = tmp_path / "e.csv"
    q.write_text("id,a\nx,1", encoding="utf-8")
    csvio.append_rows_raw(q, ["id", "a"], [["y", "2"]])
    assert csvio.read_rows(q) == [{"id": "x", "a": "1"}, {"id": "y", "a": "2"}]


def test_header_upgrade_is_written_like_a_rewrite(tmp_path: Path, monkeypatch) -> None:
    from backend import csvio, file_safety

    p = tmp_path / "t.csv"
    p.write_text("id,a\nx,1\n", encoding="utf-8")
    calls: list = []
    real = file_safety.replace_file
    monkeypatch.setattr(file_safety, "replace_file", lambda a, b: (calls.append(b), real(a, b)))
    csvio.append_row(p, ["id", "a", "b"], {"id": "y", "a": "2", "b": "3"})
    assert calls == [p]
    assert b"\r\n" not in p.read_bytes()
    assert csvio.read_rows(p) == [{"id": "x", "a": "1", "b": ""}, {"id": "y", "a": "2", "b": "3"}]


# 4 — capture health reads past a line that is JSON but not a record ---------


def test_capture_errors_skip_json_that_is_not_an_object(client: TestClient, root: Path) -> None:
    from datetime import datetime

    from backend import capturewatch

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _write(root / ".capture" / "errors.jsonl", f'[]\n"x"\n{{"at": "{now}", "error": "boom"}}\n')
    got = capturewatch.errors_since(root, 0)
    assert [e["error"] for e in got] == ["boom"]
    r = client.get("/api/capture/health")
    assert r.status_code == 200, r.text


# 5 — a chat's "produced" counts the evidence it posted ----------------------


def test_posts_count_evidence_by_its_stamp(client: TestClient, root: Path) -> None:
    from backend import produced
    from backend.csvio import append_row
    from backend.entities import TASK_EVIDENCE_COLUMNS

    store = client.app.state.store
    append_row(root / "task_evidence.csv", TASK_EVIDENCE_COLUMNS, {
        "id": "tev_1", "task_id": "tk_1", "project": "alpha", "agent_id": "a1",
        "created_at": "2026-08-20T09:10:00", "kind": "text", "title": "t", "body": "b",
    })
    store.rebuild()
    assert produced.posts(store)["evidence"] == [("a1", "2608-20", "09:10")]
    assert produced.count_in(store, "a1", "2608-20", "09:00", "09:30") == {"evidence": 1}


# 6 — a refused artifact registration writes nothing --------------------------


def test_refused_registration_leaves_no_draft(client: TestClient, root: Path) -> None:
    folder = root / "projects" / "alpha" / "artifacts" / "notes"
    _write(folder / "data.csv", "a,b\n1,2\n")
    r = client.post("/api/artifacts/new", json={"project": "alpha", "name": "notes", "kind": "dataset",
                                                "description": "   "})
    assert r.status_code == 422, r.text
    _write(root / "projects" / "alpha" / "artifacts" / "bare" / "ARTIFACT.md", "---\nname: bare\n---\n")
    r = client.post("/api/artifacts/new", json={"project": "alpha", "name": "bare", "kind": "dataset",
                                                "description": "a table"})
    assert r.status_code == 422, r.text
    assert _rows(root / "artifacts.csv") == []
    assert not list((root / "artifact_details").glob("*.md"))


def test_artifact_answers_are_built_off_the_event_loop(client: TestClient, root: Path, monkeypatch) -> None:
    import asyncio

    from backend import artifactlib

    seen: list[bool] = []
    real = artifactlib.enrich

    def enrich(*a, **k):
        try:
            asyncio.get_running_loop()
            seen.append(False)
        except RuntimeError:
            seen.append(True)
        return real(*a, **k)

    monkeypatch.setattr(artifactlib, "enrich", enrich)
    _write(root / "projects" / "alpha" / "artifacts" / "notes" / "notes.md", "# Notes\n")
    r = client.post("/api/artifacts/new", json={"project": "alpha", "name": "notes", "kind": "document",
                                                "description": "Notes."})
    assert r.status_code == 201, r.text
    assert seen and all(seen)


# 7 — search: one build for many readers, and a stable "near" list -----------


def test_search_index_is_built_once_for_readers_at_once(client: TestClient, monkeypatch) -> None:
    import threading
    import time as _time

    from backend import searchlib

    store = client.app.state.store
    searchlib.forget()
    builds: list[int] = []
    real = searchlib.build

    def slow(s):
        builds.append(1)
        _time.sleep(0.2)
        return real(s)

    monkeypatch.setattr(searchlib, "build", slow)
    threads = [threading.Thread(target=searchlib.index, args=(store,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(builds) == 1


def test_search_near_words_tie_in_word_order(client: TestClient) -> None:
    from backend import searchlib

    words = "zeta yak xenon walrus violet umber tango sierra romeo quartz"
    for i in range(2):
        make_task(client, f"checkout {words} {i}")
    searchlib.forget()
    near = client.get("/api/search/overview?q=checkout").json()["near"]
    tied = [w for w in near if w["word"] in words.split()]
    assert len(tied) == 10
    assert [w["word"] for w in tied] == sorted(w["word"] for w in tied)


# 8 — kept entries: the document follows its versions; one rule per click ---


@pytest.fixture()
def kept(root: Path):
    from backend.db import ViewStore

    d = root / "projects" / "alpha" / "chats" / "cc-k"
    _write(d / "meta.json", json.dumps({
        "agent_id": "cc-k", "agent_name": "cc-k", "project": "alpha",
        "created_date": "2609-01", "last_active": "2026-09-01T10:00:00",
    }))
    _write(d / "chat.md", "# Chat log — cc-k\n\n## Turn 1 · 2026-09-01T10:00:00\n"
           "**User**: #vision Everything runs on the laptop.\n**Agent**: noted\n\n"
           "## Turn 2 · 2026-09-01T10:01:00\n**User**: #problem The build is red.\n**Agent**: looking\n")
    store = ViewStore(data_root=root)
    store.rebuild()
    from backend import keeplib

    keeplib.adopt(store)
    return store


def test_interpretations_at_once_leave_the_document_on_the_last_version(kept, monkeypatch) -> None:
    import threading

    from backend import keeplib

    row = kept.query_one("SELECT * FROM visions_mutual")
    inside, b_done = threading.Event(), threading.Event()
    real = keeplib.read_detail

    def held(*a, **k):
        if threading.current_thread().name == "A":
            inside.set()
            b_done.wait(1.0)  # with the fix B waits on the lock instead
        return real(*a, **k)

    monkeypatch.setattr(keeplib, "read_detail", held)
    a = threading.Thread(name="A", target=keeplib.interpret,
                         args=(kept, "vision", row, "text from A"), kwargs={"by_agent": True})
    a.start()
    assert inside.wait(2)
    b = threading.Thread(name="B", target=lambda: (keeplib.interpret(
        kept, "vision", row, "text from B", by_agent=False), b_done.set()))
    b.start()
    a.join()
    b.join()
    kept.rebuild()
    versions = keeplib.read_versions(kept, row["id"])
    fresh = kept.query_one("SELECT * FROM visions_mutual WHERE id = ?", (row["id"],))
    l2, _l3, _l4 = real(kept.data_root, fresh["md_ref"])
    assert l2 == versions[-1].text
    assert int(fresh["versions_n"]) == len(versions) == 2


def test_rule_from_a_problem_twice_at_once_is_one_row(kept, monkeypatch) -> None:
    import threading

    from backend import keeplib

    problem = kept.query_one("SELECT * FROM problems_mutual")
    gate = threading.Barrier(2, timeout=2)
    real = keeplib.read_rows

    def both_look(path, *a, **k):
        rows = real(path, *a, **k)
        if path.name == "rules.csv":
            try:
                gate.wait()
            except threading.BrokenBarrierError:
                pass
        return rows

    monkeypatch.setattr(keeplib, "read_rows", both_look)
    threads = [threading.Thread(target=keeplib.rule_from_problem, args=(kept, problem, "Keep main green."))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = [r["id"] for r in _rows(kept.data_root / "rules.csv")]
    assert len(ids) == len(set(ids)) == 1


# 9 — a prompt's marks merge with the row as the file holds it ----------------


def test_prompt_marks_merge_with_the_row_not_a_stale_view(client: TestClient, monkeypatch) -> None:
    r = client.post("/api/prompt-library", json={"text": "Summarise the diff.", "project": "alpha"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["prompt"]["id"]
    assert client.post(f"/api/prompt-library/{pid}/update", json={"marks": {"worked": "yes"}}).status_code == 200
    store = client.app.state.store
    real = store.query_one

    def stale(sql, params=()):
        if sql.startswith("SELECT marks FROM prompts_mutual"):
            return {"marks": "{}"}
        return real(sql, params)

    monkeypatch.setattr(store, "query_one", stale)
    assert client.post(f"/api/prompt-library/{pid}/update", json={"marks": {"cheap": "yes"}}).status_code == 200
    monkeypatch.undo()
    marks = json.loads(store.query_one("SELECT marks FROM prompts_mutual WHERE id = ?", (pid,))["marks"])
    assert marks == {"worked": "yes", "cheap": "yes"}


def test_skill_detail_is_built_off_the_event_loop(client: TestClient, monkeypatch) -> None:
    import asyncio

    from backend import skilllib

    seen: list[bool] = []
    real = skilllib.enrich

    def enrich(*a, **k):
        try:
            asyncio.get_running_loop()
            seen.append(False)
        except RuntimeError:
            seen.append(True)
        return real(*a, **k)

    monkeypatch.setattr(skilllib, "enrich", enrich)
    r = client.post("/api/skills/new", json={
        "skill_md": "---\nname: cut-release\ndescription: Cut a release.\n---\n\nSteps.\n", "project": "alpha",
    })
    assert r.status_code == 201, r.text
    assert seen and all(seen)


# 10 — a monitor event id SQLite cannot hold is a 422 ------------------------


def test_monitor_event_id_past_sqlite_is_refused(client: TestClient) -> None:
    big = "99999999999999999999999"
    assert client.get(f"/api/monitor/events/{big}").status_code == 422
    assert client.post(f"/api/monitor/events/{big}/seen", json={}).status_code == 422
    assert client.get("/api/monitor/events/5").status_code == 404


# 11 — the time-lapse counts every file a large commit touched ---------------


def test_timelapse_files_total_counts_past_the_page_cut() -> None:
    from backend.routers import timelapse

    lines = ["Cabc\t2026-09-01T10:00:00"] + [f"1\t0\tsrc/f{i}.py" for i in range(60)]
    lines += ["Cdef\t2026-09-02T10:00:00", "2\t1\tsrc/f0.py", "1\t1\tREADME.md"]
    detail = timelapse._git_detail(lines)
    assert timelapse._git_stats(detail, lines)["files"] == 61


# 12 — deleting a project's data takes its side ledgers too ------------------


def test_delete_data_takes_dates_milestones_and_docs(client: TestClient, root: Path) -> None:
    tid = make_task(client, "a task")
    assert client.post("/api/calendar/entries", json={
        "project": "alpha", "kind": "meeting", "date": "2026-09-01", "title": "review"}).status_code == 201
    ms = client.post("/api/milestones", json={"project": "alpha", "title": "ship it", "tasks": [tid]})
    assert ms.status_code == 201, ms.text
    doc = client.post("/api/docs", json={"project": "alpha", "kind": "article", "title": "story"})
    assert doc.status_code == 201, doc.text
    r = client.post("/api/setup/delete-data", json={"project_code": "alpha", "confirm": "alpha"})
    assert r.status_code == 200, r.text
    for name in ("calendar_entries.csv", "milestones.csv", "milestone_tasks.csv", "docs.csv"):
        assert _rows(root / name) == [], name
    trash = Path(r.json()["trash"])
    assert len(_rows(trash / "calendar_entries.csv")) == 1
    assert client.get("/api/milestones?project=alpha").json()["milestones"] == []


# 13 — a file entry over a missing commit, and a file named outside ASCII ---


def _repo(tmp_path: Path) -> Path:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (repo / "plain.py").write_text("a\n", encoding="utf-8")
    (repo / "café.py").write_text("a\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "one")
    (repo / "plain.py").write_text("b\nc\n", encoding="utf-8")
    (repo / "café.py").write_text("b\nc\nd\n", encoding="utf-8")
    return repo


def test_git_fill_over_a_missing_commit_does_not_call_files_new(tmp_path: Path) -> None:
    from backend.file_entries import git_fill

    repo = _repo(tmp_path)
    paths = [{"path": "plain.py"}]
    git_fill(repo, paths, "0" * 40, None)
    assert paths[0].get("action") != "created"
    assert paths[0].get("lines_del") != 0


def test_git_fill_reads_a_file_named_outside_ascii(tmp_path: Path) -> None:
    from backend.file_entries import git_fill

    repo = _repo(tmp_path)
    head = subprocess_out(repo, "rev-parse", "HEAD")
    paths = [{"path": "café.py"}, {"path": "plain.py"}]
    out = git_fill(repo, paths, head, None)
    assert out["filled"] == 2
    assert paths[0]["lines_add"] == 3 and paths[0]["lines_del"] == 1


def subprocess_out(repo: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


# 14 — "inside the project folder" means inside, not a shared prefix ---------


def test_a_sibling_folder_is_not_inside_the_project(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from backend import archpage, projectfacts, repomap

    proj = tmp_path / "work" / "proj"
    proj.mkdir(parents=True)
    _write(tmp_path / "work" / "proj-secret" / "x.py", "x = 1\n")
    store = client.app.state.store
    for mod in (archpage, repomap, projectfacts):
        monkeypatch.setattr(mod, "project_path", lambda s, p: proj)
    sections = [{"claims": [{"where": "`../proj-secret/x.py`"}]}]
    counts = archpage.check(store, "alpha", sections)
    assert counts["missing"] == 1 and sections[0]["claims"][0]["path_found"] is False
    warnings = repomap.check(store, "alpha", {"rows": [
        {"kind": "module", "name": "secret", "where": "../proj-secret/x.py", "evidence": "opened it"}]})
    assert any("not in the project folder" in w for w in warnings)
    # The data root is <tmp>/data; a project folder <tmp>/da only shares its prefix.
    (tmp_path / "da").mkdir()
    monkeypatch.setattr(projectfacts, "project_path", lambda s, p: tmp_path / "da")
    projectfacts.forget()
    out = projectfacts.facts(store, "alpha")
    assert out["slightly_parallel"]["data_root_is_inside_the_folder"] is False


# 15 — an L3 item with a line break reads back whole -------------------------


def test_l3_item_with_a_line_break_round_trips() -> None:
    from backend.docs_md import build_detail, parse_sections

    l2, l3, l4 = parse_sections(build_detail({"l2": "x", "l3": ["first line\nsecond line", "b", "c\n\nd"]}, "e1"))
    assert l3 == ["first line\nsecond line", "b", "c\n\nd"]
    assert parse_sections("---\nid: e1\n---\n## L3\n- a\n\n- b\n")[1] == ["a", "b"]


# 16 — scan marks keep the newest, not every scan ever -----------------------


def test_scan_marks_stop_growing(client: TestClient, root: Path, monkeypatch) -> None:
    from backend import gitwork, scanlib

    store = client.app.state.store
    monkeypatch.setattr(scanlib, "_repo", lambda s, p, a: root)
    monkeypatch.setattr(scanlib, "_uncommitted", lambda repo: [])
    monkeypatch.setattr(gitwork, "head", lambda repo: "abc")
    monkeypatch.setattr(gitwork, "git", lambda repo, *a, **k: "")
    monkeypatch.setattr(scanlib, "MARKS_KEPT", 20)
    for i in range(30):
        scanlib.mark(store, f"sc_{i:03d}", "alpha", "a1")
    data = json.loads((root / scanlib.MARKS_FILE).read_text(encoding="utf-8"))
    assert len(data) == 20 and "sc_029" in data and "sc_000" not in data


# 17 — an ISO day that is no day is not read as one ---------------------------


def test_day_of_refuses_a_day_that_is_not_one() -> None:
    from backend.date_utils import day_of

    assert day_of("2026-02-30") == ""
    assert day_of("1999-12-31") == ""
    assert day_of("2026-09-21T10:00:00") == "2609-21"


# 18 — a scan posted twice at once is one row ---------------------------------


def test_scan_repeat_against_a_stale_view_writes_no_second_row(client: TestClient, root: Path) -> None:
    from backend.csvio import append_row
    from backend.models import ScanCreate
    from backend.routers import scans

    body = {"created_date": "2610-04", "created_time": "11:00", "project": "alpha",
            "agent_id": "cc-one", "l1": "a summary", "l2": "why", "l3": ["d1"], "l4": "p1"}
    sid = scans._mint_scan_id(ScanCreate(**body))
    # The other request has appended its row; the view has not rebuilt yet.
    append_row(root / "scans.csv", scans._SCAN_COLUMNS, {
        "id": sid, "created_date": "2610-04", "created_time": "11:00", "project": "alpha",
        "agent_id": "cc-one", "l1": "a summary", "files_n": 0, "lines_add": 0, "lines_del": 0,
        "decisions_n": 0, "md_ref": "",
    })
    r = client.post("/api/scans", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["existing"] is True
    assert [x["id"] for x in _rows(root / "scans.csv")] == [sid]


# 19 — the all-rules sync keeps what another set recorded meanwhile ----------


def test_all_rules_sync_keeps_a_set_recorded_meanwhile(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from backend.routers import integrate

    store = client.app.state.store
    folder = tmp_path / "proj"
    folder.mkdir()
    monkeypatch.setattr(integrate, "_targets", lambda s: {"alpha": str(folder)})
    monkeypatch.setattr(integrate, "all_rules_set", lambda s: {"items": [{"id": "ru_1"}]})
    monkeypatch.setattr(integrate, "compose", lambda s, x: "the block")
    real = integrate.upsert

    def meanwhile(text, block, set_id):
        integrate._edit_ledger(store, lambda rows: rows.append(
            {"set_id": "st_other", "project": "alpha", "path": str(folder), "written_at": "x"}))
        return real(text, block, set_id)

    monkeypatch.setattr(integrate, "upsert", meanwhile)
    integrate.sync_all_rules(store)
    ids = [e["set_id"] for e in integrate._ledger(store)]
    assert "st_other" in ids and integrate.ALL_RULES in ids


# 20 — hook settings of an odd but valid shape are answered, not a 500 -------


@pytest.mark.parametrize("text", ['{"hooks": null}', '{"hooks": []}', '{"hooks": {"Stop": {}}}',
                                  '{"hooks": {"Stop": [{"hooks": null}]}}'])
def test_hook_settings_of_another_shape(text: str) -> None:
    from fastapi import HTTPException

    from backend.routers import setup

    try:
        new, action = setup._upsert_hooks(text, "python3 claude-code-capture.py")
        assert "claude-code-capture.py" in new
    except HTTPException as exc:
        assert exc.status_code == 422
    assert setup._remove_hooks(text)[1] in ("unchanged", "updated")


# 21 — what is typed into a terminal is written off the event loop ------------


@pytest.mark.skipif(__import__("os").name == "nt", reason="the terminal needs macOS or Linux")
def test_terminal_input_is_written_off_the_event_loop(tmp_path: Path, monkeypatch) -> None:
    import asyncio
    import time as _time

    from backend import termlib
    from backend.routers import terminal

    monkeypatch.setenv("SHELL", "/bin/sh")
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    (root / "integrations.csv").write_text(f"project,path\nalpha,{work}\n", encoding="utf-8")
    seen: list[bool] = []

    def write(self, data: bytes) -> None:
        try:
            asyncio.get_running_loop()
            seen.append(False)
        except RuntimeError:
            seen.append(True)

    monkeypatch.setattr(terminal.PtySession, "write", write)
    try:
        with TestClient(create_app(data_root=root, watch=False)) as c:
            assert c.post("/api/settings", json={"values": {"terminal.enabled": True}}).status_code == 200
            sid = c.post("/api/terminal/sessions", json={"kind": "shell", "project": "alpha"}).json()["session"]["id"]
            tok = c.get("/api/terminal/state").json()["token"]
            with c.websocket_connect(f"/ws/terminal/{sid}?token={tok}") as ws:
                ws.send_text(json.dumps({"type": "input", "data": "echo hi"}))
                ws.send_bytes(b"x")
                deadline = _time.time() + 5
                while len(seen) < 2 and _time.time() < deadline:
                    _time.sleep(0.05)
            c.post(f"/api/terminal/sessions/{sid}/close", json={})
    finally:
        if termlib.tmux_path() is not None:
            termlib.tmux(root, "kill-server")
    assert len(seen) >= 2 and all(seen)


# 22 — the one-shot adapters: an empty reply closes its turn; a completion
#      with no chat behind it leaves no folder ------------------------------

_HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _run_hook(script: str, *args: str) -> None:
    import subprocess
    import sys

    proc = subprocess.run([sys.executable, str(_HOOKS / script), *args], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_codex_turn_with_an_empty_reply_is_closed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    proj = tmp_path / "app"
    proj.mkdir()
    root.mkdir()
    (root / "integrations.csv").write_text(f"project,path,created_date\napp,{proj},2608-29\n", encoding="utf-8")
    for turn, (q, a) in enumerate([("continue", ""), ("continue", "two")], 1):
        _run_hook("codex-capture.py", "--data-root", str(root), json.dumps({
            "type": "agent-turn-complete", "thread-id": "thread-abcdef12", "turn-id": f"turn-{turn}",
            "cwd": str(proj), "input-messages": [q], "last-assistant-message": a,
        }))
    chat = root / "projects" / "app" / "chats" / "codex-thread-a"
    text = (chat / "chat.md").read_text(encoding="utf-8")
    assert text.count("## Turn ") == 2
    assert json.loads((chat / "meta.json").read_text(encoding="utf-8"))["message_count"] == 2


def test_a_completion_with_no_chat_leaves_no_agent_folder(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    _run_hook("capture-cli.py", "--phase", "complete", "--project", "alpha", "--data-root", str(root),
              "--agent", "oc-child123", "--tool", "opencode", "--session", "ses_1", "--cwd", str(tmp_path),
              "--text", "", "--close-if-missing")
    assert not (root / "projects" / "alpha" / "chats" / "oc-child123").exists()


# 23 — the operator's files are written through their links, keeping their mode


def test_operator_files_keep_their_links_and_mode(client: TestClient, tmp_path: Path) -> None:
    import os
    import stat

    from backend import project_admin
    from backend.file_safety import write_in_place

    folder = tmp_path / "proj"
    folder.mkdir()
    agents = folder / "AGENTS.md"
    agents.write_text("# Notes\n\nbridge line\n", encoding="utf-8")
    (folder / "CLAUDE.md").symlink_to("AGENTS.md")
    project_admin.strip_file(folder / "CLAUDE.md", lambda t: project_admin.remove_bridge(t, "bridge line"))
    assert (folder / "CLAUDE.md").is_symlink()
    assert "bridge line" not in agents.read_text(encoding="utf-8")
    # The all-rules block is written into a project whose AGENTS.md is a link.
    from backend.routers import integrate

    shared = tmp_path / "shared.md"
    shared.write_text("# Shared\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / "AGENTS.md").symlink_to(shared)
    store = client.app.state.store
    mp = pytest.MonkeyPatch()
    mp.setattr(integrate, "_targets", lambda s: {"alpha": str(other)})
    mp.setattr(integrate, "all_rules_set", lambda s: {"items": [{"id": "ru_1"}]})
    mp.setattr(integrate, "compose", lambda s, x: "the block")
    try:
        integrate.sync_all_rules(store)
    finally:
        mp.undo()
    assert (other / "AGENTS.md").is_symlink() and "the block" in shared.read_text(encoding="utf-8")
    secret = folder / ".env"
    secret.write_text("A=1\n", encoding="utf-8")
    os.chmod(secret, 0o600)
    write_in_place(secret, "A=2\n")
    if os.name != "nt":  # Windows has no owner-only mode bits to keep
        assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert secret.read_text(encoding="utf-8") == "A=2\n"


# 24 — Setup registers a folder once, whatever its own look saw ---------------


def test_setup_registers_a_folder_once(tmp_path: Path, monkeypatch) -> None:
    from backend.routers import setup

    data_root = tmp_path / "data"
    data_root.mkdir()
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    with TestClient(create_app(data_root=data_root, watch=False)) as c:
        body = {"project_code": "my-app", "project_dir": str(project_dir)}
        assert c.post("/api/setup/integrate", json=body).status_code == 200
        # A second post whose look was taken before the first one's write.
        monkeypatch.setattr(setup, "read_rows", lambda path, *a, **k: [])
        assert c.post("/api/setup/integrate", json=body).status_code == 200
    assert len(_rows(data_root / "integrations.csv")) == 1


# 25 — two map versions written at once are two versions ---------------------


def test_two_maps_written_at_once_take_two_numbers(client: TestClient, monkeypatch) -> None:
    import copy
    import threading

    from backend import repomap
    from tests.test_repomap import MAP

    store = client.app.state.store
    gate = threading.Barrier(2, timeout=1)
    real = repomap.versions

    def both_look(s, p):
        got = real(s, p)
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass  # with the fix the other writer waits on the lock instead
        return got

    monkeypatch.setattr(repomap, "versions", both_look)
    maps = [copy.deepcopy(MAP), copy.deepcopy(MAP)]
    maps[1]["notes"]["shape"] = "Another shape."
    threads = [threading.Thread(target=repomap.write, args=(store, "alpha", "cc-m", m)) for m in maps]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    names = sorted(p.name for p in (store.data_root / "projects" / "alpha" / "map").glob("v*.json"))
    assert names == ["v001.json", "v002.json"]


def test_versions_are_read_in_number_order(client: TestClient) -> None:
    from backend import versioned

    store = client.app.state.store
    for n in (999, 1000):
        versioned.write(store, "alpha", "map", n, "json", "{}")
    assert [v["n"] for v in versioned.versions(store, "alpha", "map", lambda t: {})] == [999, 1000]


# ---------------------------------------------------------------- the default data folder


def test_a_new_install_keeps_its_data_outside_the_clone(tmp_path, monkeypatch) -> None:
    """With nothing named, the data lives in ~/.slightly-parallel, made empty
    once; the server adds the example project on its first start (example.py)."""
    from backend import db
    from backend.config import Settings
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows reads this one
    for name in ("SP_DATA_ROOT", "SCAN_DATA_ROOT", "DATA_ROOT"):
        monkeypatch.delenv(name, raising=False)
    root = Settings.from_env().data_root
    assert root == tmp_path / ".slightly-parallel"
    assert root.is_dir() and not any(root.iterdir())
    # The user's folder from then on: a second start leaves it as it is.
    (root / "tasks.csv").write_text("mine\n", encoding="utf-8")
    assert not db.make_data_root(root)
    assert Settings.from_env().data_root == root and (root / "tasks.csv").read_text(encoding="utf-8") == "mine\n"
    # A folder that is there, even empty, is theirs too.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "other"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "other"))  # Windows reads this one
    monkeypatch.setenv("SP_DATA_ROOT", str(empty))
    assert Settings.from_env().data_root == empty and not any(empty.iterdir())
