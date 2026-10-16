"""Filesystem safety utilities for Slightly Parallel.

Parallel agents all write into the same ``projects/`` tree. Two agents
in the same project can update the
same ``meta.json`` concurrently; a naive ``open(...).write(...)`` will corrupt
it. Two more can append to ``chat.md`` at the same time and interleave lines.

This module provides the primitives that make those writes safe:

1. ``atomic_write(path, content)`` — write-to-temp + fsync + rename.
2. ``safe_read_json(path, retries=1)`` — retry on ``ENOENT`` once, so a reader
   that races the rename doesn't fail spuriously.
3. ``acquire_flock(path)`` — an exclusive lock as a context manager.
4. ``edit_json(path, change)`` — read, change and write one JSON file under
   one lock.

Cross-platform note: the lock is ``fcntl.flock`` on Linux and macOS and
``msvcrt.locking`` on the first byte on Windows; ``replace_file`` waits out
the moment Windows refuses a replace.
"""

from __future__ import annotations

import copy
import errno
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Union

try:  # pragma: no cover — non-Unix platforms
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]
try:  # pragma: no cover — Windows: the same lock, spelled msvcrt.locking
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]


# ``os.replace``, patient on Windows. The capture hook replaces files the
# same way, so the one copy is in hookshared.py.
from .hookshared import replace_file  # noqa: E402


def _try_lock(fh: Any) -> bool:
    """One non-blocking try at an exclusive lock; True when held."""
    if fcntl is not None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            if exc.errno == errno.EWOULDBLOCK:
                return False
            raise
    # Windows: lock the first byte; a lock may lie past the end of an empty file.
    fh.seek(0)  # pragma: no cover
    try:  # pragma: no cover
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:  # pragma: no cover
        return False


def _unlock(fh: Any) -> None:
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        else:  # pragma: no cover
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass

__all__ = [
    "atomic_write",
    "atomic_write_json",
    "safe_read_json",
    "acquire_flock",
    "edit_json",
    "lock_path",
    "replace_file",
    "FileSafetyError",
]


PathLike = Union[str, os.PathLike]


class FileSafetyError(OSError):
    """Raised when a filesystem-safety primitive cannot be honored."""


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


# Whether writes wait for the disk. On by default — a power cut must not
# leave a half-written ledger. SP_FSYNC=0 turns it off where nothing
# outlives the run: the test suite, which starts ~800 data roots.
DURABLE = os.environ.get("SP_FSYNC", "1") != "0"


def atomic_write(
    path: PathLike,
    content: Union[str, bytes],
    *,
    encoding: str = "utf-8",
    mode: int = 0o644,
    fsync: bool = True,
) -> None:
    """Atomically write ``content`` to ``path``.

    Writes to a sibling tempfile (same directory ⇒ same filesystem ⇒
    ``os.replace`` is atomic on POSIX), fsyncs the temp file, then renames
    it into place. Readers see either the old or new content — never a
    partial write.

    ``fsync=True`` guarantees durability on power-loss; disable for tests
    that hammer the filesystem.
    """
    p = Path(path)
    parent = p.parent
    parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, str):
        data = content.encode(encoding)
    elif isinstance(content, (bytes, bytearray)):
        data = bytes(content)
    else:
        raise TypeError(f"content must be str or bytes, got {type(content).__name__}")

    # Cyrillic filenames: Path/os.replace/tempfile all accept unicode paths.
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{p.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            if fsync and DURABLE:
                os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        replace_file(tmp_path, str(p))
    except BaseException:
        # cleanup the temp on any failure (including KeyboardInterrupt)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_in_place(path: PathLike, text: str) -> None:
    """Write a file of the operator's (AGENTS.md, CLAUDE.md, a tool's
    settings) atomically and as it stands: through a symlink to the file it
    names, and with the file's own permissions.

    A plain ``atomic_write`` renames a new file over the path. Where
    CLAUDE.md is a link to AGENTS.md, that replaced the link with a copy,
    and a settings file kept private (0600) came back readable by all.
    """
    p = Path(path)
    target = Path(os.path.realpath(p)) if p.is_symlink() else p
    try:
        mode = target.stat().st_mode & 0o7777
    except OSError:
        mode = 0o644
    # The file's own line ends: text read in Python came in with \n, and a
    # CRLF file written back as LF showed every line changed in git.
    try:
        with open(target, "rb") as fh:
            crlf = b"\r\n" in fh.read(65536)
    except OSError:
        crlf = False
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    atomic_write(target, text, mode=mode)


def atomic_write_json(
    path: PathLike,
    obj: Any,
    *,
    indent: int = 2,
    fsync: bool = True,
) -> None:
    """Atomic JSON dump — convenience wrapper around ``atomic_write``.

    ``ensure_ascii=False`` so Cyrillic keys/values write as UTF-8 (not \\uXXXX).
    """
    payload = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=False)
    # Trailing newline is a filesystem convention; grep, diff, cat behave better.
    atomic_write(path, payload + "\n", fsync=fsync)


# ---------------------------------------------------------------------------
# Reads that race atomic writes
# ---------------------------------------------------------------------------


def safe_read_json(
    path: PathLike,
    *,
    retries: int = 1,
    retry_delay_s: float = 0.01,
) -> Any:
    """Read + ``json.loads`` a file, retrying on ``ENOENT`` and truncated JSON.

    Between an atomic-writer's ``unlink(old)`` and ``rename(tmp, dst)`` there
    is a microsecond window where a reader can see ``FileNotFoundError``.
    Retrying once resolves it. We also retry on ``json.JSONDecodeError``: on
    some kernels the reader can observe the file *during* the write to the
    temp path if the temp path was mistaken for the final path (belt +
    suspenders; costs nothing when the file is well-formed).

    ``retries`` is retry *count* — a value of 1 means "up to 2 total attempts".
    """
    p = Path(path)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with open(p, "rb") as f:
                data = f.read()
            if not data:
                # empty file — likely mid-write; retry
                raise json.JSONDecodeError("empty file", "", 0)
            return json.loads(data.decode("utf-8"))
        except FileNotFoundError as exc:
            last_exc = exc
        except json.JSONDecodeError as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(retry_delay_s)
    assert last_exc is not None  # for the type-checker
    raise last_exc


# ---------------------------------------------------------------------------
# File locks
# ---------------------------------------------------------------------------


def lock_path(path: PathLike) -> Path:
    """The lock beside a state file: ``boards.json`` → ``boards.json.lock``.

    One spelling, so two writers of the same file never take two different
    locks and both think they hold it.
    """
    p = Path(path)
    return p.with_name(p.name + ".lock")


def edit_json(path: PathLike, change: Any, *, default: Any = None) -> Any:
    """Read, change and write one JSON state file under one lock.

    Fourteen JSON files at the data root are load-mutate-save cycles inside
    request handlers. Four of them took a lock; the rest did not, so two
    concurrent posts each read the file, each added a row and the second
    write forgot the first — never a corrupt file, just a missing row. Half
    of them also read with a bare ``json.loads``, which sees an empty file
    if it lands in an atomic writer's rename window and then writes a
    document with everything else dropped.

    This is the one cycle: the lock beside the file, ``safe_read_json``'s
    retry, the caller's change, and an atomic write. ``change(data)`` may
    mutate ``data`` in place and return ``None``, or return the document to
    write instead. Returns what was written.

    A file that is missing, empty, unreadable or of the wrong shape reads as
    ``default`` (``{}`` unless given) — the same tolerance every one of
    these readers already had, in one place.
    """
    p = Path(path)
    base = {} if default is None else default
    with acquire_flock(lock_path(p)):
        try:
            data = safe_read_json(p)
        except (OSError, ValueError):
            data = None
        if data is None or not isinstance(data, type(base)):
            data = copy.deepcopy(base)
        out = change(data)
        if out is None:
            out = data
        atomic_write_json(p, out)
    return out


@contextmanager
def acquire_flock(
    path: PathLike,
    *,
    mode: str = "a",
    timeout_s: float = 5.0,
    poll_s: float = 0.01,
) -> Iterator[Any]:
    """Acquire an exclusive ``fcntl.flock`` on ``path`` (context manager).

    Yields the open file handle. On exit, the lock is released automatically
    when the fd closes.

    ``mode`` is passed to ``open()``; ``"a"`` for appenders (chat.md), ``"r+"``
    for read-modify-write.

    ``timeout_s`` bounds the wait; raises ``FileSafetyError`` if the lock
    can't be acquired in time (prevents one wedged agent from stalling
    another indefinitely).

    Usage::

        with acquire_flock("chat.md") as f:
            f.write("--- turn ---\\n")

    Note: ``flock`` is advisory — code that ignores it can still corrupt.
    All Slightly Parallel writers (the capture hooks, migrate.py) must cooperate.
    """
    if fcntl is None and msvcrt is None:  # pragma: no cover
        raise FileSafetyError("no file locking on this platform")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Ensure the file exists so open("a") + LOCK_EX has something to lock.
    if not p.exists():
        p.touch()

    fh = open(p, mode, encoding="utf-8")
    try:
        deadline = time.monotonic() + timeout_s
        while not _try_lock(fh):
            if time.monotonic() >= deadline:
                raise FileSafetyError(
                    f"could not acquire flock on {p} within {timeout_s}s"
                )
            time.sleep(poll_s)
        if fcntl is None:  # pragma: no cover — the Windows lock moved the position
            fh.seek(0, os.SEEK_END)
        yield fh
    finally:
        _unlock(fh)
        fh.close()
