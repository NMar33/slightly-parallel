"""Read-only snapshots of terminal state, saved only in local diagnostics."""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from . import termlib
from .file_safety import DURABLE, atomic_write
from .terminal_diagnostic_name import snapshot_filename

MAX_BROWSER_BYTES = 8 * 1024 * 1024
BROWSER_SECTIONS = ("xterm", "dom", "scrollLayer")
PANE_FIELDS = ("pane_tty", "pane_height", "pane_width", "history_size", "scroll_position", "cursor_y", "cursor_x")
PANE_FLAGS = (
    "alternate_on", "mouse_any_flag", "mouse_all_flag", "mouse_button_flag", "mouse_standard_flag",
    "mouse_utf8_flag", "mouse_sgr_flag", "pane_in_mode",
)
TTY_PATH = re.compile(r"/dev/(?:pts/[0-9]+|ttys[0-9A-Za-z]+)")
CAPTURE_HEADER = "\nSP terminal snapshot:\n"


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def read_browser(request: Request) -> dict[str, Any]:
    """Bound the upload and retain only the sections the operator captured."""
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > MAX_BROWSER_BYTES:
            raise HTTPException(status_code=413, detail="the browser terminal snapshot is too large")
        body.extend(part)
    try:
        got = json.loads(body)
        if not isinstance(got, dict):
            raise ValueError
        captured_at = got.get("capturedAt")
        if not isinstance(captured_at, str) or len(captured_at) > 48:
            raise ValueError
        if any(not isinstance(got.get(name), dict) for name in BROWSER_SECTIONS):
            raise ValueError
        return {name: got[name] for name in ("capturedAt", *BROWSER_SECTIONS)}
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status_code=422, detail="expected a browser terminal snapshot") from exc


def fd_size(fd: int) -> dict[str, int] | None:
    if os.name == "nt" or fd < 0:
        return None
    import termios

    try:
        rows, cols = termios.tcgetwinsize(fd)
    except (OSError, termios.error):
        return None
    return {"rows": rows, "cols": cols}


def tty_size(tty: str) -> dict[str, int] | None:
    if os.name == "nt" or not TTY_PATH.fullmatch(tty):
        return None
    try:
        fd = os.open(tty, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        return fd_size(fd)
    finally:
        os.close(fd)


def _number(value: str) -> int:
    return int(value) if value.isascii() and value.isdecimal() else 0


def _tmux_snapshot(root: Path, sid: str) -> dict[str, Any]:
    target = termlib.PREFIX + sid
    pane_format = "\t".join(f"#{{{name}}}" for name in (*PANE_FIELDS, *PANE_FLAGS))
    # One tmux request keeps the flags, clients and ANSI capture together.
    result = termlib.tmux_read(
        root, "display-message", "-p", "-t", target, pane_format, ";",
        "list-clients", "-t", target, "-F", "#{client_tty}\t#{client_height}\t#{client_width}", ";",
        "display-message", "-p", "-t", target, CAPTURE_HEADER.strip(), ";",
        "capture-pane", "-p", "-e", "-t", target,
        timeout=termlib.WRITE_TIMEOUT,
    )
    meta, separator, capture = result.stdout.partition(CAPTURE_HEADER)
    lines = meta.split("\n")
    pane_tty, *values = lines[0].split("\t")
    if result.returncode or not separator or len(values) != len(PANE_FIELDS) + len(PANE_FLAGS) - 1:
        raise HTTPException(status_code=409, detail="the tmux pane could not be captured")
    fields = dict(zip((*PANE_FIELDS[1:], *PANE_FLAGS), map(_number, values), strict=True))
    clients = []
    for line in lines[1:]:
        tty, rows, cols = line.split("\t")
        clients.append({"tty": tty, "rows": _number(rows), "cols": _number(cols), "pty": tty_size(tty)})
    return {
        "pane": {
            "tty": pane_tty, "rows": fields["pane_height"], "cols": fields["pane_width"],
            "history": fields["history_size"], "scroll": fields["scroll_position"],
            "cursorY": fields["cursor_y"], "cursorX": fields["cursor_x"],
            "flags": {name: bool(fields[name]) for name in PANE_FLAGS},
        },
        "panePty": tty_size(pane_tty),
        "tmuxClients": clients,
        "tmuxCapture": capture,
    }


def _verify_folder(folder: Path, opened: os.stat_result) -> None:
    current = folder.stat(follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or not os.path.samestat(opened, current):
        raise HTTPException(status_code=409, detail="the diagnostics folder changed during capture")


def _write_at(folder: Path, dir_fd: int, name: str, text: str) -> None:
    """Stage and publish relative to the same directory, even if its path moves."""
    opened = os.fstat(dir_fd)
    _verify_folder(folder, opened)
    temporary = f".{name}.tmp"
    mode = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(temporary, mode, 0o600, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(text)
            stream.flush()
            if DURABLE:
                os.fsync(stream.fileno())
        _verify_folder(folder, opened)
        os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        try:
            _verify_folder(folder, opened)
        except (HTTPException, OSError):
            os.unlink(name, dir_fd=dir_fd)
            raise
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=dir_fd)


def save(
    root: Path, sid: str, backend: str, browser: dict[str, Any], plain_size: dict[str, int] | None,
) -> Path:
    folder = root.resolve() / "diagnostics"
    if folder.is_symlink() or folder.resolve() != folder:
        raise HTTPException(status_code=409, detail="the diagnostics folder must be inside the data folder")
    if folder.exists() and not folder.is_dir():
        raise HTTPException(status_code=409, detail="the diagnostics folder is not a directory")
    folder.mkdir(mode=0o700, exist_ok=True)
    dir_fd = None
    if os.open in os.supports_dir_fd and os.rename in os.supports_dir_fd:
        dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = folder.stat(follow_symlinks=False) if dir_fd is None else None
        started = timestamp()
        server = _tmux_snapshot(root, sid) if backend == "tmux" else {
            "pane": None, "panePty": plain_size, "tmuxClients": [], "tmuxCapture": None,
        }
        server.update(startedAt=started, finishedAt=timestamp())
        path = folder / snapshot_filename(sid)
        try:
            text = json.dumps({"version": 1, "terminal": sid, "backend": backend, "browser": browser, "server": server},
                              allow_nan=False, indent=2) + "\n"
        except (ValueError, RecursionError) as exc:
            raise HTTPException(status_code=422, detail="the browser snapshot has invalid values") from exc
        if dir_fd is not None:
            _write_at(folder, dir_fd, path.name, text)
        else:
            assert opened is not None
            _verify_folder(folder, opened)
            if folder.resolve() != folder:
                raise HTTPException(status_code=409, detail="the diagnostics folder changed during capture")
            # POSIX mode 0600 limits access. On Windows the file inherits its folder ACL.
            atomic_write(path, text, mode=0o600)
        return path
    finally:
        if dir_fd is not None:
            os.close(dir_fd)
