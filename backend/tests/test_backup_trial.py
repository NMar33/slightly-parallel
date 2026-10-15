"""A backup is proved by restoring it: into a temporary folder, read as the dashboard reads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend import backup
from backend.server import create_app


def _root_with_tasks(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for t in ("one", "two", "three"):
            assert c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                                              "agent_id": "operator", "title": t, "status": "todo"}).status_code == 201
    return root


def test_a_good_archive_restores_and_reads(tmp_path: Path) -> None:
    root = _root_with_tasks(tmp_path)
    dest = tmp_path / "backups"
    made = backup.create(root, dest, kind="manual", now=datetime(2026, 9, 25, 12, 0))
    got = backup.trial(dest, made.name)
    assert got["ok"], got["problems"]
    assert got["counts"]["task"] == 3
    assert backup.last_trial(dest)["name"] == made.name


def test_a_damaged_archive_fails_and_says_why(tmp_path: Path) -> None:
    root = _root_with_tasks(tmp_path)
    dest = tmp_path / "backups"
    made = backup.create(root, dest, kind="manual", now=datetime(2026, 9, 25, 12, 0))
    data = made.path.read_bytes()
    made.path.write_bytes(data[: len(data) // 2])          # a disk that lost the second half
    got = backup.trial(dest, made.name)
    assert not got["ok"] and got["problems"]
    assert backup.last_trial(dest)["ok"] is False


def test_a_python_without_the_unpack_filter_never_unpacks_unfiltered(tmp_path: Path, monkeypatch) -> None:
    """The trial fell back to a plain extractall, which writes a member
    named ../x wherever it points."""
    import tarfile

    root = _root_with_tasks(tmp_path)
    dest = tmp_path / "backups"
    made = backup.create(root, dest, kind="manual", now=datetime(2026, 9, 25, 12, 0))
    unfiltered: list[bool] = []

    def old_python(self, path=".", members=None, *, numeric_owner=False, **kw):
        if "filter" in kw:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        unfiltered.append(True)

    monkeypatch.setattr(tarfile.TarFile, "extractall", old_python)
    got = backup.trial(dest, made.name)
    assert unfiltered == []
    assert not got["ok"] and "3.11.4" in got["problems"][0]
