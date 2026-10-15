"""The data-root watcher: a write rebuilds, a read does not wake it."""

from __future__ import annotations

import os
import sys
import threading
import time

from backend.watcher import DebouncedHandler, Watcher


def _wait(cond, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_writes_fire_and_reads_never_reach_the_handler(tmp_path, monkeypatch):
    (tmp_path / "chats").mkdir()
    f = tmp_path / "chats" / "chat.md"
    f.write_text("one\n", encoding="utf-8")
    seen: list[str] = []
    real = DebouncedHandler.on_any_event

    t0 = time.monotonic()

    def counting(self, event):
        # What arrived, on what, and when: a failure here names the event.
        seen.append(f"{event.event_type} {'dir' if event.is_directory else 'file'} {os.path.basename(event.src_path)} +{time.monotonic() - t0:.2f}s")
        return real(self, event)

    monkeypatch.setattr(DebouncedHandler, "on_any_event", counting)
    fired = threading.Event()
    w = Watcher(tmp_path, on_change=fired.set, delay_ms=50)
    w.start()
    try:
        # macOS and Windows deliver the file's creation above late, after the start: let it land, then count from here.
        time.sleep(1.0 if sys.platform in ("darwin", "win32") else 0.2)
        seen.clear()
        for _ in range(20):                      # what a request does
            f.read_text(encoding="utf-8")
            list(os.scandir(tmp_path / "chats"))
        time.sleep(0.3)
        assert seen == [] and not fired.is_set()

        with f.open("a", encoding="utf-8") as fh:  # a captured turn
            fh.write("two\n")
        assert _wait(fired.is_set)
        fired.clear()
        os.utime(f, None)                          # a touch still counts
        assert _wait(fired.is_set)
        fired.clear()
        f.rename(tmp_path / "chats" / "moved.md")
        assert _wait(fired.is_set)
        fired.clear()
        (tmp_path / "chats" / "moved.md").unlink()
        assert _wait(fired.is_set)
        fired.clear()
        (tmp_path / "new-project").mkdir()
        assert _wait(fired.is_set)
    finally:
        w.stop()


def test_a_data_root_under_a_dot_folder_or_an_ignored_name_still_fires(tmp_path):
    """The filters read the path inside the watched folder. Read over the
    whole path, the default ~/.slightly-parallel dropped every file event,
    and so did a data root kept under a folder named monitor or timer."""
    for name in (".sp-root", "monitor"):
        root = tmp_path / name / "data"
        h = DebouncedHandler(lambda: None, root=root)
        assert h._relevant(str(root / "tasks.csv"), root)
        assert h._relevant(str(root / "projects" / "p1" / "chats" / "cc-1" / "chat.md"), root)
        assert not h._relevant(str(root / ".sessions" / "abc.json"), root)
        assert not h._relevant(str(root / "monitor" / "x.json"), root)

    root = tmp_path / ".sp-root" / "data"
    (root / "chats").mkdir(parents=True)
    f = root / "chats" / "chat.md"
    f.write_text("one\n", encoding="utf-8")
    seen: list[bool] = []
    h = DebouncedHandler(lambda: None, root=root)
    h._schedule = lambda: seen.append(True)  # type: ignore[method-assign]
    from watchdog.events import FileModifiedEvent
    h.on_any_event(FileModifiedEvent(str(f)))
    assert seen == [True]


def test_an_atomic_write_counts_by_where_it_lands(tmp_path):
    """A hook writes meta.json by renaming a dot-prefixed temp file into
    place. The move's source is filtered as a dot file; the destination is
    the write. On Linux the folder's own event hid this; on macOS and
    Windows the rename was the only event, and the views never refreshed."""
    from watchdog.events import FileMovedEvent
    root = tmp_path / "data"
    (root / "projects" / "p1" / "chats" / "cc-1").mkdir(parents=True)
    src = root / "projects" / "p1" / "chats" / "cc-1" / ".meta.json.ab12"
    dest = root / "projects" / "p1" / "chats" / "cc-1" / "meta.json"
    seen: list[bool] = []
    h = DebouncedHandler(lambda: None, root=root)
    h._schedule = lambda: seen.append(True)  # type: ignore[method-assign]
    h.on_any_event(FileMovedEvent(str(src), str(dest)))
    assert seen == [True]
    # A move that lands in the ignored folder is still noise.
    h.on_any_event(FileMovedEvent(str(src), str(root / "monitor" / "x.json")))
    assert seen == [True]


def test_only_the_top_level_folders_are_ignored(tmp_path):
    """tour_shots, monitor, terminal and timer are folders at the top of the
    data root. A project whose code is timer is a project."""
    root = tmp_path / "data"
    h = DebouncedHandler(lambda: None, root=root)
    assert not h._relevant(str(root / "timer" / "modes.json"), root)
    assert h._relevant(str(root / "projects" / "timer" / "chats" / "cc-1" / "chat.md"), root)
    assert h._relevant(str(root / "projects" / "monitor" / "tasks.csv"), root)
