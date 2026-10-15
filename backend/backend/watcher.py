"""Watchdog observer with a coalescing 200ms debounce.

Editors (nvim, VSCode) do write-to-temp+rename which fires several events for
one save. Debounce swallows the storm and calls ``on_change`` at most once per
quiet window.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import (
    DirCreatedEvent, DirDeletedEvent, DirModifiedEvent, DirMovedEvent, FileCreatedEvent, FileDeletedEvent,
    FileModifiedEvent, FileMovedEvent, FileSystemEvent, FileSystemEventHandler,
)
from watchdog.observers import Observer

log = logging.getLogger("sp.watcher")


class DebouncedHandler(FileSystemEventHandler):
    """Fires ``on_change`` once, ``delay_ms`` after the last event."""

    def __init__(self, on_change: Callable[[], None], delay_ms: int = 200,
                 root: Path | str | None = None):
        super().__init__()
        # The watched folder: the filters below read the path inside it. The
        # data root itself may sit under a dot folder (~/.slightly-parallel
        # is the default) or one named like an ignored folder.
        self._root = Path(root) if root is not None else None
        self._on_change = on_change
        self._delay = delay_ms / 1000.0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # Folders whose contents are pictures the server itself writes. A tour
    # capture drops seventeen screenshots into the data root in a minute;
    # rebuilding every view for each of them starves the app the capture is
    # photographing, and the shots come back missing what they aimed at.
    IGNORED_DIRS = frozenset({"tour_shots", "monitor", ".capture", "terminal", "timer"})

    # Filter noise: swap files, lock files, anything under a dot folder
    # (the hook's own .sessions registry, which no view reads), obvious junk.
    @staticmethod
    def _inside(path: str | bytes, root: Path | None) -> tuple[str, ...]:
        """The parts of ``path`` below ``root`` (all of them with no root)."""
        target = Path(os.fsdecode(path))
        if root is None:
            return target.parts
        for here, top in ((target, root), (target.resolve(), root.resolve())):
            try:
                return here.relative_to(top).parts
            except ValueError:
                continue
        return target.parts

    @classmethod
    def _ignored(cls, parts: tuple[str, ...], root: Path | None) -> bool:
        """Is this inside one of the server's own picture folders? They sit
        at the top of the data root; a project that happens to be called
        timer or monitor is not one of them. With no root to measure from,
        any part counts."""
        if root is None:
            return bool(cls.IGNORED_DIRS.intersection(parts))
        return bool(parts) and parts[0] in cls.IGNORED_DIRS

    @classmethod
    def _relevant(cls, path: str | bytes, root: Path | None = None) -> bool:
        target = Path(os.fsdecode(path))
        parts = cls._inside(path, root)
        if cls._ignored(parts, root):
            return False
        if any(part.startswith(".") for part in parts if part not in (".", "..")):
            return False
        p = target.name
        if not p:
            return False
        if p.endswith(("~", ".swp", ".swo", ".tmp", ".lock")):
            return False
        return True

    def _schedule(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        try:
            self._on_change()
        except Exception:  # never let a callback crash the observer thread
            log.exception("watcher on_change failed")

    # What counts as a change. watchdog also reports every open and every
    # close-without-write, and the rebuild reads the CSVs it watches: each
    # rebuild's own reads scheduled the next one, once a second, forever,
    # with the server at full CPU and nobody asking it anything.
    CHANGES = frozenset({"created", "modified", "deleted", "moved"})

    def on_any_event(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        if event.event_type not in self.CHANGES:
            return
        if event.is_directory:
            # Directory events are useful (new project folder) — pass them,
            # unless they are inside a folder we deliberately ignore.
            if not self._ignored(self._inside(event.src_path, self._root), self._root):
                self._schedule()
            return
        # An atomic write renames a dot-prefixed temp file into place: the
        # move's source is noise, where it lands is the write.
        if self._relevant(event.src_path, self._root):
            self._schedule()
        elif event.event_type == "moved" and self._relevant(getattr(event, "dest_path", "") or "", self._root):
            self._schedule()


#: The events ``on_any_event`` acts on (``DebouncedHandler.CHANGES``), as the
#: observer's filter. Without one, inotify also reported every open and every
#: close-without-write: each file a request read woke the observer thread
#: twice, and on a page that reads the chat folders the request ran three
#: times slower beside it (75 ms alone, 180-280 ms with the watcher).
CHANGE_EVENTS = [
    FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, FileMovedEvent,
    DirCreatedEvent, DirModifiedEvent, DirDeletedEvent, DirMovedEvent,
]


class Watcher:
    """Thin wrapper managing the observer lifecycle."""

    def __init__(
        self,
        path: Path,
        on_change: Callable[[], None],
        delay_ms: int = 200,
        recursive: bool = True,
    ):
        self.path = Path(path)
        self.recursive = recursive
        self._handler = DebouncedHandler(on_change, delay_ms=delay_ms, root=self.path)
        self._observer: Observer | None = None

    def start(self) -> None:
        if self._observer is not None:
            return
        if not self.path.exists():
            log.warning("watch path does not exist: %s", self.path)
            return
        obs = Observer()
        obs.schedule(self._handler, str(self.path), recursive=self.recursive, event_filter=CHANGE_EVENTS)
        obs.start()
        self._observer = obs
        log.info("watching %s (recursive=%s)", self.path, self.recursive)

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2.0)
        self._observer = None
