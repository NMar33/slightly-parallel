"""A document kept in numbered versions, in the project's own folder.

The architecture page and the map are both written again and again, each
version replacing the whole document and none replacing what came before.
They each grew their own store — the same folder listing, the same
``vNNN`` pattern, the same "next number", the same fingerprint for the
ETag — differing only in the folder, the file extension and how a version
is read. One store now; each caller says where its versions live and how
to read one.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .db import ViewStore
from .file_safety import acquire_flock, atomic_write

_NAME_RE = re.compile(r"^v(\d{3,})\.[a-z]+$")


def folder(store: ViewStore, project: str, kind: str) -> Path:
    """Where this kind of document keeps its versions."""
    return store.data_root / "projects" / project / kind


def versions(store: ViewStore, project: str, kind: str, read: Callable[[str], dict[str, Any]]) -> list[dict[str, Any]]:
    """Every version, oldest first. ``read`` turns one file's text into the
    fields that version carries; a file that cannot be read is skipped."""
    out: list[dict[str, Any]] = []
    d = folder(store, project, kind)
    if not d.is_dir():
        return out
    for path in sorted(d.iterdir()):
        m = _NAME_RE.match(path.name)
        if not m:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            fields = read(text)
        except ValueError:
            continue
        out.append({"n": int(m.group(1)), **fields})
    # By number: by name, v1000 came before v999.
    out.sort(key=lambda v: v["n"])
    return out


@contextmanager
def numbering(store: ViewStore, project: str, kind: str) -> Iterator[None]:
    """Hold while reading the last version and writing the next: two
    writers at once both took the same number, and the second file replaced
    the first."""
    d = folder(store, project, kind)
    d.mkdir(parents=True, exist_ok=True)
    with acquire_flock(d / ".lock"):
        yield


def next_number(prior: list[dict[str, Any]]) -> int:
    return (prior[-1]["n"] + 1) if prior else 1




def write(store: ViewStore, project: str, kind: str, n: int, suffix: str, text: str) -> Path:
    """Write version ``n``. The folder is made if this is the first."""
    d = folder(store, project, kind)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"v{n:03d}.{suffix}"
    atomic_write(path, text)
    return path


def fingerprint(store: ViewStore, kind: str) -> str:
    """For ETags: these versions are files, so no view moves when one lands."""
    root = store.data_root / "projects"
    parts: list[str] = []
    if root.is_dir():
        for path in sorted(root.glob(f"*/{kind}/v*.*")):
            try:
                parts.append(f"{path}:{path.stat().st_mtime_ns}")
            except OSError:
                pass
    return "|".join(parts)


def note_of(text: str) -> str:
    """A note as it is stored: one line, quotes and newlines out."""
    return " ".join((text or "").split())[:200].replace('"', "'")
