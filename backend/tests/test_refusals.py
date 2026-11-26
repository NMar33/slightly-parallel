"""The file inventory for refusal checks includes every relevant file."""

import os
from types import SimpleNamespace

import pytest

from tests import refusals


def test_snapshot_uses_directory_metadata_without_losing_files(monkeypatch, tmp_path):
    root = tmp_path / "data"
    names = ("root.txt", "nested/file.txt", "nested.lock/kept.txt", "logs-also.txt")
    expected = {}
    for name in (*names, "nested/excluded.lock", "logs/detail.log", "nested/quiet/detail.log"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(name, encoding="utf-8")
        if name in names:
            st = target.stat()
            expected[name] = st.st_size, st.st_mtime_ns

    old_inventory_calls = []

    def stat(path):
        old_inventory_calls.append("stat")
        return os.stat(path)

    def relpath(path, root):
        old_inventory_calls.append("relpath")
        return os.path.relpath(path, root)

    # Patch only the snapshot module, leaving filesystem calls by pytest and
    # pathlib outside the measurement.
    monkeypatch.setattr(refusals, "os", SimpleNamespace(
        fspath=os.fspath,
        scandir=os.scandir,
        walk=os.walk,
        sep=os.sep,
        stat=stat,
        path=SimpleNamespace(join=os.path.join, relpath=relpath),
    ))
    assert refusals.snapshot(root, skip=("logs/", "nested/quiet/")) == expected
    assert old_inventory_calls == []


def test_snapshot_follows_file_links_but_does_not_walk_directory_links(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    outside = tmp_path / "other"
    outside.mkdir()
    (outside / "must-not-be-walked").touch()
    try:
        (root / "file-link").symlink_to(target)
        (root / "dangling").symlink_to(tmp_path / "missing")
        (root / "directory-link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("a symlink needs privileges on Windows")
        raise
    st = target.stat()
    assert refusals.snapshot(root) == {"file-link": (st.st_size, st.st_mtime_ns)}
