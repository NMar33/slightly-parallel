"""The world the tour is photographed in.

A film that is put on a page has to show the example project and nothing
else: no other project in the sidebar, on the home page or in the lists.
So the capture does not open the operator's data. It plays the example
month into a folder of its own (the same builder the example project uses),
starts a second server on that folder, and the photographing browser takes
its data from there. The operator's data root is only read for where the
pictures go.

The month is played once a day (its dates end yesterday) into a clean copy,
and every capture photographs a fresh duplicate of it: a beat that drags a
card changes the board, and the next capture starts from the clean board.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from . import example

STAMP = "tour_world.json"
START_SECONDS = 60


def world_home(port: int) -> Path:
    """Outside the data root, so the running server never watches it."""
    return Path(tempfile.gettempdir()) / f"slightly-parallel-tour-world-{port}"


def _clean(home: Path, fresh: bool) -> str:
    """The clean copy, played today; '' when it is there, else the last
    line the builder said."""
    clean = home / "clean"
    stamp = clean / STAMP
    if not fresh:
        try:
            if json.loads(stamp.read_text(encoding="utf-8")).get("day") == date.today().isoformat():
                return ""
        except (OSError, ValueError):
            pass
    shutil.rmtree(clean, ignore_errors=True)
    error = example._play(clean)
    if error:
        return error
    stamp.write_text(json.dumps({"day": date.today().isoformat()}), encoding="utf-8")
    return ""


def prepare(home: Path, fresh: bool = False) -> tuple[Path, str]:
    """A fresh duplicate of today's clean copy to photograph: (its folder,
    '') or (folder, what went wrong). ``fresh`` plays the month again."""
    work = home / "work"
    error = _clean(home, fresh)
    if error:
        return work, error
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(home / "clean", work, symlinks=True)
    _answer_first_visit(work)
    return work, ""


# What a first visit would be asked, answered for the pictures: the board
# asks each morning which of yesterday's cards to plan for today, over the
# board the film is about.
def _answer_first_visit(root: Path) -> None:
    file = root / "ui_prefs.json"
    try:
        prefs = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prefs = {}
    prefs["sp-today-carry-seen"] = date.today().isoformat()
    file.write_text(json.dumps(prefs), encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 — this computer only
            return r.status == 200
    except OSError:
        return False


@contextmanager
def server(root: Path) -> Iterator[str]:
    """A server on ``root`` for as long as the block runs; yields its address.

    A sandbox server: it installs no skills and runs no system monitor, so
    it leaves nothing outside ``root``.
    """
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("SCAN_DATA_ROOT", "DATA_ROOT", "SCAN_PORT", "PORT")}
    env.update({
        "SP_DATA_ROOT": str(root), "SP_PORT": str(port), "SP_SANDBOX": "1",
        "SP_LOG_FILE": "0", "SHELL": env.get("SHELL") or "/bin/sh",
    })
    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(backend), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + START_SECONDS
        while not _up(base + "/api/snapshot"):
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("the server for the tour's pictures did not start")
            time.sleep(0.3)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
