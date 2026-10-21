"""When storage misbehaves: a ledger damaged by hand, a full disk, a
read-only data folder. Nothing already there is lost, the answer says what
to do, and the next write works once the fault is gone."""

from __future__ import annotations

import csv
import errno
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import file_safety
from backend.server import FIXTURES, create_app


def _client(root: Path) -> TestClient:
    c = TestClient(create_app(data_root=root, watch=False, run_monitor=False, autoinstall_skills=False),
                   base_url="http://127.0.0.1:8123")
    c.__enter__()
    c.get("/api/health", headers={"Sec-Fetch-Site": "same-origin"})      # the page's cookie
    return c


def _ids(root: Path) -> list[str]:
    with open(root / "tasks.csv", encoding="utf-8", newline="") as fh:
        return [r["id"] for r in csv.DictReader(fh)]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    shutil.copytree(FIXTURES, r)
    return r


def test_a_ledger_with_a_quote_left_open_is_not_rewritten_and_the_data_check_names_it(root: Path) -> None:
    """One stray quote made the reader take four tasks as one field; a task
    edit then wrote the file back without them, for good."""
    raw = (root / "tasks.csv").read_text(encoding="utf-8").split("\n")
    raw[len(raw) // 2] = raw[len(raw) // 2].replace(",", ',"left open', 1)
    (root / "tasks.csv").write_text("\n".join(raw), encoding="utf-8")
    before = (root / "tasks.csv").read_bytes()
    c = _client(root)
    tid = _ids(root)[0]
    r = c.post(f"/api/tasks/{tid}/update", json={"title": "an edit", "actor": "operator"})
    assert r.status_code == 409 and "quote is left open" in r.json()["detail"], r.text
    assert (root / "tasks.csv").read_bytes() == before                     # not a byte lost
    issues = c.get("/api/doctor").json()["issues"]
    assert any(i["kind"] == "swallowed-rows" and i["file"] == "tasks.csv" for i in issues)


def test_a_full_disk_says_so_and_changes_nothing(root: Path, monkeypatch) -> None:
    c = _client(root)
    before = (root / "tasks.csv").read_bytes()

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(file_safety, "replace_file", full)
    r = c.post("/api/tasks", json={"project": "alpha-labs", "title": "no space", "status": "todo", "actor": "operator"})
    assert r.status_code == 507 and "disk is full" in r.json()["detail"]
    tid = _ids(root)[0]
    r = c.post(f"/api/tasks/{tid}/update", json={"title": "no space either", "actor": "operator"})
    assert r.status_code == 507
    assert (root / "tasks.csv").read_bytes() == before
    monkeypatch.undo()
    r = c.post("/api/tasks", json={"project": "alpha-labs", "title": "space again", "status": "todo", "actor": "operator"})
    assert r.status_code in (200, 201), r.text


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="read-only by permissions: POSIX, not as root")
def test_a_read_only_data_folder_says_so_and_changes_nothing(root: Path) -> None:
    c = _client(root)
    before = (root / "tasks.csv").read_bytes()
    paths = [root, *root.rglob("*")]
    try:
        for p in paths:
            os.chmod(p, 0o555 if p.is_dir() else 0o444)
        r = c.post("/api/tasks", json={"project": "alpha-labs", "title": "read only", "status": "todo", "actor": "operator"})
        assert r.status_code == 503 and "cannot be written" in r.json()["detail"], r.text
        assert c.get("/api/health").status_code == 200
        assert (root / "tasks.csv").read_bytes() == before
    finally:
        for p in paths:
            os.chmod(p, 0o755 if p.is_dir() else 0o644)
    r = c.post("/api/tasks", json={"project": "alpha-labs", "title": "writable again", "status": "todo", "actor": "operator"})
    assert r.status_code in (200, 201), r.text
