"""A rebuild never makes a request wait, and never runs twice for one write.

The store used to hold its read lock for the whole rebuild — three seconds
when a chat log moved — and every request, health included, stood still
behind it. Now the views are made on a connection of their own and swapped
in at the end.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import duckdb

from backend.db import ViewStore
from backend.watcher import DebouncedHandler


def _root(tmp: Path) -> Path:
    root = tmp / "data"
    (root / "projects" / "p1" / "chats" / "cc-1").mkdir(parents=True)
    (root / "projects" / "p1" / "chats" / "cc-1" / "meta.json").write_text(
        '{"agent_id": "cc-1", "project": "p1", "cwd": ""}', encoding="utf-8"
    )
    (root / "projects" / "p1" / "chats" / "cc-1" / "chat.md").write_text(
        "## Turn 1 · 2026-09-01T10:00:00\n**User**: hello\n**Agent**: hi\n", encoding="utf-8"
    )
    return root


def test_a_read_does_not_wait_for_a_build(tmp_path, monkeypatch):
    store = ViewStore(_root(tmp_path))
    hold = threading.Event()
    building = threading.Event()
    real = store._build_views

    def slow(con):
        building.set()
        hold.wait(30)
        return real(con)

    monkeypatch.setattr(store, "_build_views", slow)
    builder = threading.Thread(target=store.rebuild)
    builder.start()
    assert building.wait(10), "the build never started"
    # The read runs while the build is held; it must come back before the
    # build is let go. The condition is the order, not a number of seconds:
    # a read that waits on the build never returns until hold is set.
    rows: list = []
    read = threading.Thread(target=lambda: rows.extend(store.query("SELECT count(*) AS n FROM sessions")))
    read.start()
    read.join(25)
    returned_during_build = not read.is_alive() and not hold.is_set()
    hold.set()
    builder.join()
    read.join()
    assert returned_during_build, "a read waited on a build in progress"
    assert rows[0]["n"] == 1


def test_a_rebuild_asked_during_a_build_is_one_more_build_and_returns_after_it(tmp_path, monkeypatch):
    store = ViewStore(_root(tmp_path))
    builds: list[float] = []
    gate = threading.Event()
    building = threading.Event()
    real = store._build_views

    def counting(con):
        builds.append(time.perf_counter())
        if len(builds) == 1:
            building.set()
            gate.wait(30)
        return real(con)

    monkeypatch.setattr(store, "_build_views", counting)
    first = threading.Thread(target=store.rebuild)
    first.start()
    assert building.wait(10), "the first build never started"
    # Three callers land while the first build runs: a hook write, a scan,
    # a task update. They get one build between them, and each returns
    # only once that build — started after their call — is in.
    returned: list[float] = []

    def ask():
        store.rebuild()
        returned.append(time.perf_counter())

    with store._build_cv:
        before = store._requested
    askers = [threading.Thread(target=ask) for _ in range(3)]
    for t in askers:
        t.start()
    # The askers have reached the store (each counted its request) while the
    # first build holds: a condition, not a sleep that a slow machine outruns.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with store._build_cv:
            if store._requested == before + 3:
                break
        time.sleep(0.01)
    with store._build_cv:
        assert store._requested == before + 3, f"the askers never reached the store ({store._requested - before} of 3)"
    gate.set()
    first.join()
    for t in askers:
        t.join()
    assert len(builds) == 2, f"expected the first build and one more, got {len(builds)}"
    assert all(r > builds[1] for r in returned), "a caller returned before its build started"


def test_the_derived_rows_come_back_as_written(tmp_path):
    con = duckdb.connect(":memory:")
    cols = {"a": "VARCHAR", "n": "INTEGER", "b": "VARCHAR"}
    con.execute("CREATE TABLE t (a VARCHAR, n INTEGER, b VARCHAR)")
    ViewStore._bulk_insert(con, "t", cols, [
        ("", 1, "one\nline two, \"quoted\"\n"),
        (None, 2, "плюс юникод"),
    ])
    rows = con.execute("SELECT a, n, b FROM t ORDER BY n").fetchall()
    assert rows == [("", 1, "one\nline two, \"quoted\"\n"), (None, 2, "плюс юникод")]


def test_the_watcher_ignores_locks_and_dot_folders_but_not_the_data():
    ok = DebouncedHandler._relevant
    assert not ok("/data/projects/p1/chats/cc-1/meta.json.lock")
    assert not ok("/data/tasks.csv.lock")
    assert not ok("/data/.sessions/abc.json")
    assert not ok("/data/tour_shots/1.png")
    assert ok("/data/projects/p1/chats/cc-1/chat.md")
    assert ok("/data/tasks.csv")
    assert ok("/data/task_details/260924-1200__p1__cc-1__tk_1.md")


def test_an_open_or_a_close_without_write_is_not_a_change(monkeypatch):
    from watchdog.events import (
        FileClosedNoWriteEvent, FileModifiedEvent, FileOpenedEvent,
    )

    fired: list[str] = []
    h = DebouncedHandler(lambda: None)
    monkeypatch.setattr(h, "_schedule", lambda: fired.append("x"))
    h.on_any_event(FileOpenedEvent("/data/tasks.csv"))
    h.on_any_event(FileClosedNoWriteEvent("/data/tasks.csv"))
    assert fired == [], "the rebuild's own reads must not schedule the next rebuild"
    h.on_any_event(FileModifiedEvent("/data/tasks.csv"))
    assert fired == ["x"]


def test_a_rebuild_that_found_nothing_new_keeps_the_stamp(tmp_path):
    store = ViewStore(_root(tmp_path))
    before = store.view_mtime
    store.rebuild()
    store.rebuild()
    assert store.view_mtime == before
    chat = tmp_path / "data" / "projects" / "p1" / "chats" / "cc-1" / "chat.md"
    chat.write_text(chat.read_text(encoding="utf-8") + "## Turn 2 · 2026-09-01T10:05:00\n**User**: more\n", encoding="utf-8")
    import os
    os.utime(chat, (time.time() + 1, time.time() + 1))
    store.rebuild()
    assert store.view_mtime > before


def test_a_tag_keyed_on_an_area_survives_a_change_elsewhere(tmp_path):
    import os

    from backend.routers.deps import etag_for

    root = _root(tmp_path)
    (root / "tasks.csv").write_text("id,project,title,status\ntk_1,p1,one,todo\n", encoding="utf-8")
    (root / "scans.csv").write_text("id,created_date,project\n", encoding="utf-8")
    store = ViewStore(root)
    tasks_tag = etag_for("tasks:list", store, "tasks", "chats")
    whole_tag = etag_for("tasks:list", store)
    # A scan lands: the whole-store tag moves, the tasks tag does not.
    (root / "scans.csv").write_text("id,created_date,project\nsn_1,2609-01,p1\n", encoding="utf-8")
    os.utime(root / "scans.csv", (time.time() + 5, time.time() + 5))
    store.rebuild()
    assert etag_for("tasks:list", store) != whole_tag
    assert etag_for("tasks:list", store, "tasks", "chats") == tasks_tag
    # A task lands: the tasks tag moves.
    (root / "tasks.csv").write_text("id,project,title,status\ntk_1,p1,one,done\n", encoding="utf-8")
    os.utime(root / "tasks.csv", (time.time() + 10, time.time() + 10))
    store.rebuild()
    assert etag_for("tasks:list", store, "tasks", "chats") != tasks_tag
