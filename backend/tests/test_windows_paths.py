"""What changes on Windows, checked on any system: the lock, the hook and MCP lines."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from backend import file_safety
from backend.routers import setup


class FakeMsvcrt:
    """msvcrt.locking as Windows answers it: one holder per byte range."""
    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self) -> None:
        self.held: set[int] = set()
        self.calls: list[tuple[int, int]] = []

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        self.calls.append((mode, nbytes))
        if mode == self.LK_NBLCK:
            if self.held:
                raise OSError("locked")
            self.held.add(fd)
        else:
            self.held.discard(fd)


def test_the_lock_uses_msvcrt_where_there_is_no_fcntl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMsvcrt()
    monkeypatch.setattr(file_safety, "fcntl", None)
    monkeypatch.setattr(file_safety, "msvcrt", fake)
    p = tmp_path / "x.lock"
    with file_safety.acquire_flock(p) as fh:
        fh.write("a")
        with pytest.raises(file_safety.FileSafetyError):
            with file_safety.acquire_flock(p, timeout_s=0.05):
                pass
    assert fake.held == set() and (fake.LK_NBLCK, 1) in fake.calls
    assert p.read_text() == "a"


def test_windows_hook_and_mcp_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "nt")
    assert setup._venv_python().parts[-2:] == ("Scripts", "python.exe")
    cmd = setup._hook_command("alpha", Path("/data"))
    assert not cmd.startswith("python3 ")
    line = setup._codex_notify_line(Path("C:\\Users\\n\\data"))
    # TOML reads the backslashes back as they were written.
    assert tomllib.loads(line)["notify"][-1] == "C:\\Users\\n\\data"


def test_linux_and_macos_lines_stay_as_they_were() -> None:
    if os.name == "nt":
        pytest.skip("POSIX lines")
    assert setup._hook_command("alpha", Path("/data")).startswith('python3 "')
    assert tomllib.loads(setup._codex_notify_line(Path("/d x")))["notify"][0] == "python3"
