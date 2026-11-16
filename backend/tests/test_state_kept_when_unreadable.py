"""A timer file that is there and cannot be read is never taken as empty and
written back (P17, docs/testing.md case 6).

On Windows a file another program holds open without sharing (an editor, a
backup tool, an antivirus scan) cannot be read for a moment. ``modes()``
took that as "no modes", and ``set_mode`` then wrote modes.json back with
one project: every other project's mode was lost. ``_load`` took state.json
as empty, and the next ``_save`` wrote the open spans away.

The patched reads run everywhere; the held-open file is real on Windows.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import timeauto
from backend.server import create_app


def _app(root: Path):
    app = create_app(data_root=root, watch=False)
    app.state.timer = timeauto.AutoTimer(app.state.store, read_idle=lambda: (0.0, "test"))
    return app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    timer = root / "timer"
    timer.mkdir()
    (timer / "modes.json").write_text(json.dumps({"beta": "auto", "gamma": "manual"}), encoding="utf-8")
    (timer / "state.json").write_text(json.dumps({"spans": {"beta": {
        "entry_id": "te_1", "project": "beta", "top": 0, "task_id": "", "last": "2026-11-11T10:00:00"}},
        "paused": {"te_2": "2026-11-11T09:00:00"}, "away": {}}), encoding="utf-8")
    return root


@contextmanager
def _unreadable(name: str, monkeypatch):
    real = Path.read_text

    def read_text(self, *a, **k):
        if self.name == name:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(timeauto.time, "sleep", lambda s: None)
    try:
        yield
    finally:
        monkeypatch.setattr(Path, "read_text", real)


def test_a_mode_set_while_modes_json_cannot_be_read_is_refused_and_the_file_kept(root, monkeypatch) -> None:
    before = (root / "timer" / "modes.json").read_bytes()
    with TestClient(_app(root), raise_server_exceptions=False) as c:
        assert c.get("/api/time/auto").json()["modes"] == {"beta": "auto", "gamma": "manual"}
        with _unreadable("modes.json", monkeypatch):
            r = c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
            assert r.status_code == 409, r.text
            assert "nothing was changed" in r.json()["detail"]
            # A read meanwhile gives the modes last read, not none.
            assert c.get("/api/time/auto").json()["modes"] == {"beta": "auto", "gamma": "manual"}
        assert (root / "timer" / "modes.json").read_bytes() == before
        ok = c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
        assert ok.status_code == 200
    assert json.loads((root / "timer" / "modes.json").read_text(encoding="utf-8")) == {
        "alpha": "auto", "beta": "auto", "gamma": "manual"}


def test_state_json_unreadable_at_start_is_not_written_over(root, monkeypatch) -> None:
    before = (root / "timer" / "state.json").read_bytes()
    with _unreadable("state.json", monkeypatch):
        app = _app(root)
        timer = app.state.timer
        assert timer.spans == {}
        timer.paused["te_9"] = "2026-11-11T11:00:00"
        timer._save()
        assert (root / "timer" / "state.json").read_bytes() == before
    # Readable again: the next save keeps what the file held and adds the new.
    timer._save()
    saved = json.loads((root / "timer" / "state.json").read_text(encoding="utf-8"))
    assert set(saved["spans"]) == {"beta"}
    assert saved["paused"] == {"te_2": "2026-11-11T09:00:00", "te_9": "2026-11-11T11:00:00"}


def test_a_missing_file_is_still_empty(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(_app(root)) as c:
        assert c.get("/api/time/auto").json()["modes"] == {}
        assert c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "manual"}).status_code == 200


@pytest.mark.skipif(sys.platform != "win32", reason="a file held open without sharing exists on Windows only")
def test_windows_a_file_held_open_by_another_handle_is_kept(root) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    path = root / "timer" / "modes.json"
    before = path.read_bytes()
    GENERIC_READ, OPEN_EXISTING = 0x80000000, 3
    handle = kernel32.CreateFileW(str(path), GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
    assert handle not in (None, wintypes.HANDLE(-1).value), ctypes.get_last_error()
    try:
        with pytest.raises(PermissionError):
            path.read_text(encoding="utf-8")   # the hold is real
        with TestClient(_app(root), raise_server_exceptions=False) as c:
            r = c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
            assert r.status_code == 409, r.text
    finally:
        kernel32.CloseHandle(handle)
    assert path.read_bytes() == before


def test_answering_an_away_notice_that_is_not_there_writes_nothing(root) -> None:
    """A 404 rewrote timer/state.json (round 5, the fuzzer's refused writes)."""
    path = root / "timer" / "state.json"
    with TestClient(_app(root), raise_server_exceptions=False) as c:
        before = (path.read_bytes(), path.stat().st_mtime_ns)   # after the start's own recovery
        assert c.post("/api/time/auto/away/te_none", json={"action": "dismiss"}).status_code == 404
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
