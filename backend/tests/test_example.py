"""The example project (backend/example.py, scripts/demo/build_example.py).

One real build per run (about a minute): the month is played with the clock
ending yesterday into an empty data root. Then: every part of the product
has something in the example, the dates are recent, nothing global was
written, and switching the example off leaves the root as it was.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import example
from backend.server import create_app

REPO = Path(__file__).resolve().parents[2]
CODE = example.CODE
# The last played day, handed to the builder: the parent and the child agree
# on it whatever zone each reads "today" in.
END = date.today() - timedelta(days=1)

pytestmark = pytest.mark.slow


def _rows(root: Path, name: str) -> list[dict[str, str]]:
    path = root / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _mine(root: Path, name: str) -> list[dict[str, str]]:
    return [r for r in _rows(root, name) if r.get("project") == CODE]


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("example") / "data"
    root.mkdir()
    done = subprocess.run(
        [sys.executable, str(example.BUILDER), "--root", str(root), "--end", END.isoformat()],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        # The whole environment (Windows needs SYSTEMROOT and the like), with
        # the home folder moved so nothing global of the user's is read.
        env={**os.environ, "HOME": str(root.parent), "USERPROFILE": str(root.parent),
             "SHELL": "/bin/sh", "SP_LOG_FILE": "0"},
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return root


def test_every_part_of_the_product_has_an_example(built: Path) -> None:
    root = built
    statuses = {r["status"] for r in _mine(root, "tasks.csv")}
    assert {"backlog", "todo", "next", "doing", "review", "done", "done-archived", "parked"} <= statuses
    for ledger in ("scans.csv", "files.csv", "architecture.csv", "standups.csv", "decisions.csv",
                   "visions.csv", "rules.csv", "problems.csv", "skills.csv", "artifacts.csv",
                   "prompts.csv", "marks.csv", "done.csv", "agent_links.csv", "milestones.csv",
                   "calendar_entries.csv", "time_entries.csv", "task_evidence.csv", "task_notes.csv",
                   "docs.csv"):
        assert _mine(root, ledger), f"the example has no {ledger}"
    assert any(r.get("status") == "resolved" for r in _mine(root, "problems.csv"))
    assert [r for r in _rows(root, "sprints.csv") if r.get("projects") == CODE]
    docs = {r["id"] for r in _mine(root, "docs.csv")}
    versions = [r for r in _rows(root, "doc_versions.csv") if r.get("doc_id") in docs]
    assert len(versions) >= 2, "a storyboard document with more than one version"
    assert len(list((root / "projects" / CODE / "chats").iterdir())) >= 10
    assert len(list((root / "projects" / CODE / "architecture").glob("v*.md"))) >= 2
    assert len(list((root / "projects" / CODE / "map").glob("v*.json"))) >= 2
    assert (root / example.REPO_DIR / CODE / ".git").is_dir()
    assert [r for r in _rows(root, "integrations.csv") if r["project"] == CODE]
    # Browsing the example counts no time and asks nothing about the timer.
    assert json.loads((root / "timer" / "modes.json").read_text())[CODE] == "manual"


def test_the_month_ends_yesterday(built: Path) -> None:
    def day(r: dict[str, str]) -> date:
        d = r["created_date"]
        return date(2000 + int(d[:2]), int(d[2:4]), int(d[5:7]))
    days = sorted(day(r) for r in _mine(built, "standups.csv") + _mine(built, "tasks.csv") if r.get("created_date"))
    yesterday = END
    assert days[-1] <= yesterday and days[-1] >= yesterday - timedelta(days=2)
    assert days[0] >= yesterday - timedelta(days=30)
    # No date of the old September demo is left in the text.
    for r in _mine(built, "standups.csv") + _mine(built, "decisions.csv"):
        text = json.dumps(r)
        if END.year != 2026 or END.month not in (9, 10, 11):
            assert "September" not in text and "2026-09" not in text, text[:200]


def test_every_date_in_the_text_is_filled_in(built: Path) -> None:
    """The content writes its dates as {dm:22}, {iso:22} …, filled in when
    the month is played (engine.dated). None is left in any file."""
    import re
    token = re.compile(r"\{(iso|ymd|dm|dsh):\d+\}")
    left = [str(p.relative_to(built)) for p in built.rglob("*")
            if p.is_file() and ".git" not in p.parts and p.suffix in (".md", ".json", ".jsonl", ".csv")
            and token.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert left == []


def test_nothing_global_is_written(built: Path) -> None:
    """Only the project's rows and files: no preferences, boards or other
    projects' state reach the user's root."""
    assert not (built / "ui_prefs.json").exists()
    assert not (built / "boards.json").exists()
    assert not (built / ".trash").exists()
    projects = {r.get("project") for name in ("tasks.csv", "scans.csv", "decisions.csv") for r in _rows(built, name)}
    assert projects == {CODE}


def test_switching_it_off_removes_everything_and_on_offers_it_again(built: Path, tmp_path: Path, monkeypatch) -> None:
    import shutil
    root = tmp_path / "data"
    shutil.copytree(built, root, symlinks=True)
    monkeypatch.setenv("SP_EXAMPLE", "0")
    app = create_app(data_root=root, watch=False, run_monitor=False)
    with TestClient(app) as c:
        assert c.get("/api/example").json()["present"] is True
        started: list[bool] = []
        monkeypatch.setattr(example, "build", lambda a: started.append(True) or True)
        r = c.post("/api/settings", json={"values": {"example.enabled": False}})
        assert r.status_code == 200, r.text
        state = c.get("/api/example").json()
        assert state["present"] is False and state["enabled"] is False
        for name in ("tasks.csv", "scans.csv", "standups.csv", "docs.csv", "marks.csv", "done.csv",
                     "integrations.csv", "calendar_entries.csv", "agent_links.csv"):
            assert not _mine(root, name), name
        assert not [r for r in _rows(root, "sprints.csv") if r.get("projects") == CODE]
        assert not (root / example.REPO_DIR).exists() and not (root / ".trash").exists()
        assert not (root / "projects" / CODE).exists()
        assert CODE not in json.loads((root / "timer" / "modes.json").read_text())
        # On again: the month is played anew (the build itself is the test above).
        c.post("/api/settings", json={"values": {"example.enabled": True}})
        assert started == [True]


def test_a_root_made_empty_gets_it_once_and_a_root_with_projects_never(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SP_EXAMPLE", "1")
    started: list[Path] = []
    monkeypatch.setattr(example, "build", lambda a: started.append(a.state.store.data_root) or True)

    empty = tmp_path / "empty"
    empty.mkdir()
    with TestClient(create_app(data_root=empty, watch=False, run_monitor=False)):
        pass
    assert started == [empty]
    assert example.chosen(empty) is True
    # Chosen once: a second start (the example hidden since) builds nothing.
    from backend import app_settings
    app_settings.save(empty, {"example.enabled": False})
    with TestClient(create_app(data_root=empty, watch=False, run_monitor=False)):
        pass
    assert started == [empty]

    busy = tmp_path / "busy"
    (busy / "projects" / "mine").mkdir(parents=True)
    with TestClient(create_app(data_root=busy, watch=False, run_monitor=False)):
        pass
    assert started == [empty] and example.chosen(busy) is None
