"""Fixes from the memory and latency audit (tk_8d57ac45): one rebuild at a
time from the watcher, a ceiling on JSON bodies, the first commit read
without the whole log."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import server
from backend.watcher import DebouncedHandler


def test_a_burst_during_a_slow_callback_runs_it_once_more_not_in_parallel(tmp_path: Path) -> None:
    running, most, calls = 0, 0, 0
    lock = threading.Lock()

    def slow() -> None:
        nonlocal running, most, calls
        with lock:
            running += 1
            calls += 1
            most = max(most, running)
        time.sleep(0.3)
        with lock:
            running -= 1

    h = DebouncedHandler(slow, delay_ms=20, root=tmp_path)
    for _ in range(6):            # six quiet windows inside one slow call
        threading.Thread(target=h._fire).start()
        time.sleep(0.05)
    time.sleep(1.0)
    assert most == 1 and calls == 2       # the first, and one for everything after
    h.close()
    h._fire()
    assert calls == 2                     # closed: no callback


def test_a_json_body_past_the_ceiling_is_refused(monkeypatch, data_root: Path) -> None:
    monkeypatch.setattr(server, "MAX_JSON_BODY", 1000)
    with TestClient(server.create_app(data_root=data_root, watch=False, run_monitor=False),
                    base_url="http://127.0.0.1:8123") as c:
        r = c.post("/api/decisions", content=b'{"x": "' + b"a" * 2000 + b'"}',
                   headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_the_first_commit_is_the_root_commits_date(tmp_path: Path) -> None:
    from backend import projectfacts
    import os
    run = lambda *a, **env: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path,  # noqa: E731
                                           check=True, capture_output=True,
                                           env={"PATH": os.environ["PATH"], "HOME": str(tmp_path), **env})
    run("init", "-q")
    for i, day in enumerate(("2026-01-02", "2026-03-04", "2026-05-06")):
        (tmp_path / f"f{i}").write_text(str(i))
        run("add", ".")
        run("commit", "-qm", f"c{i}", GIT_AUTHOR_DATE=f"{day}T10:00:00", GIT_COMMITTER_DATE=f"{day}T10:00:00")
    assert projectfacts._repo_facts(tmp_path, 3)["first_commit"] == ["2026-01-02"]
