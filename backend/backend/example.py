"""The example project: one project in the user's own data root, built at
install, that shows how every part of Slightly Parallel works.

It is played by ``scripts/demo/build_example.py`` in a process of its own
(the month is played on a fake clock, which must never touch this server's
modules), with the clock ending yesterday, and lands in the data root as an
ordinary project: chats, a board, scans, standups, the architecture page,
its git repository at ``<data root>/example/shopfront``.

``example.enabled`` (Settings) decides whether it is there. A data root
made empty gets it once: the setting is unset and the root holds no
project, so it is switched on and built. Switching it off removes the
project and everything that names it; switching it on again plays the
month anew, ending on the new yesterday. A root that already holds the
user's projects never gets it unasked.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from . import app_settings
from .file_safety import safe_read_json

log = logging.getLogger("sp.example")

CODE = "shopfront"
SETTING = "example.enabled"
REPO_DIR = "example"
_REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = _REPO_ROOT / "scripts" / "demo" / "build_example.py"
BUILD_SECONDS = 1800


def _state(app: Any) -> dict[str, Any]:
    st = getattr(app.state, "example", None)
    if st is None:
        st = {"building": False, "error": "", "lock": threading.Lock()}
        app.state.example = st
    return st


def present(root: Path) -> bool:
    return (Path(root) / "projects" / CODE).is_dir()


def chosen(root: Path) -> bool | None:
    """The stored choice, or None when nobody has made one in this root."""
    path = Path(root) / app_settings.SETTINGS_FILENAME
    try:
        raw = safe_read_json(path) if path.exists() else {}
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    value = (raw.get("example") or {}).get("enabled") if isinstance(raw.get("example"), dict) else raw.get(SETTING)
    return value if isinstance(value, bool) else None


def holds_projects(root: Path) -> bool:
    projects = Path(root) / "projects"
    return projects.is_dir() and any(p.is_dir() for p in projects.iterdir())


def describe(app: Any) -> dict[str, Any]:
    root = app.state.store.data_root
    st = _state(app)
    return {
        "project": CODE,
        "enabled": bool(app_settings.load(root).get(SETTING)),
        "present": present(root),
        "building": st["building"],
        "error": st["error"],
    }


def on_start(app: Any) -> None:
    """A root nobody has chosen for and that holds no project gets the
    example, once."""
    if os.environ.get("SP_EXAMPLE", "1") == "0":
        return
    root = app.state.store.data_root
    if chosen(root) is not None or holds_projects(root):
        return
    app_settings.save(root, {SETTING: True})
    build(app)


def apply(app: Any, enabled: bool) -> None:
    """The setting just changed: build or remove."""
    if enabled:
        if not present(app.state.store.data_root):
            build(app)
    elif present(app.state.store.data_root) or (app.state.store.data_root / REPO_DIR).exists():
        remove(app)


def _play(root: Path) -> str:
    """Play the month into ``root`` in a process of its own; '' when it
    worked, else the last line it said."""
    env = {**os.environ, "SHELL": os.environ.get("SHELL") or "/bin/sh", "SP_LOG_FILE": "0"}
    env.pop("SP_DATA_ROOT", None)
    try:
        done = subprocess.run(
            [sys.executable, str(BUILDER), "--root", str(root)],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=BUILD_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("example project not built: %s", exc)
        return str(exc)[:300]
    if done.returncode != 0:
        log.warning("example project not built: %s", (done.stderr or "")[-2000:])
        tail = (done.stderr or done.stdout or "").strip().splitlines()[-1:] or ["no output"]
        return tail[0][:300]
    log.info("example project built: %s", (done.stdout or "").strip()[:300])
    return ""


def _claim(app: Any) -> bool:
    st = _state(app)
    with st["lock"]:
        if st["building"]:
            return False
        st["building"], st["error"] = True, ""
    return True


def build(app: Any) -> bool:
    """Play the month in the background. False when a build is running."""
    if not _claim(app):
        return False
    st = _state(app)
    root = app.state.store.data_root

    def run() -> None:
        try:
            if not present(root):
                st["error"] = _play(root)
            app.state.store.rebuild()
        finally:
            st["building"] = False

    threading.Thread(target=run, name="example-build", daemon=True).start()
    return True


def replay(app: Any) -> str:
    """Remove the example and play it again, now, ending yesterday; ''
    when it worked. The tour photographs a fresh copy this way: a beat that
    drags a card leaves the board changed for the next capture."""
    if not _claim(app):
        return "the example project is being played already"
    st = _state(app)
    try:
        remove(app)
        app_settings.save(app.state.store.data_root, {SETTING: True})
        st["error"] = _play(app.state.store.data_root)
        app.state.store.rebuild()
        return st["error"]
    finally:
        st["building"] = False


def _rmtree(path: Path | str) -> None:
    """Remove a tree with a git repository in it. Git keeps its objects
    read-only, and Windows refuses to delete a read-only file: make it
    writable and try once more. Errors beyond that are let go."""
    import stat

    def writable_then(fn: Any, p: str, _exc: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            fn(p)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable_then)
    else:
        shutil.rmtree(path, onerror=writable_then)


def remove(app: Any) -> dict[str, Any]:
    """Everything the example owns goes: its rows and files (archived by
    the server's own delete, then the archive dropped — the example is
    played again on demand, nothing in it is the user's), its registry row
    and its repository."""
    from .csvio import rewrite_rows
    from .project_admin import delete_project_data, known_projects

    store = app.state.store
    root = store.data_root
    out: dict[str, Any] = {"removed": False}
    if any(p.get("code") == CODE for p in known_projects(store)) or present(root):
        moved = delete_project_data(store, CODE)
        _rmtree(moved["trash"])
        try:
            Path(moved["trash"]).parent.rmdir()  # .trash, when nothing else is in it
        except OSError:
            pass
        out = {"removed": True, "moved": moved["moved"]}
    reg = root / "integrations.csv"
    if reg.exists():
        def drop(rows: list[dict[str, str]]) -> bool:
            keep = [r for r in rows if r.get("project") != CODE]
            changed = len(keep) != len(rows)
            rows[:] = keep
            return changed
        rewrite_rows(reg, ("project", "path", "created_date"), drop)
    modes = root / "timer" / "modes.json"
    try:
        got = json.loads(modes.read_text(encoding="utf-8"))
        if isinstance(got, dict) and got.pop(CODE, None) is not None:
            from .file_safety import atomic_write
            atomic_write(modes, json.dumps(got, indent=1, sort_keys=True))
    except (OSError, ValueError):
        pass
    _rmtree(root / REPO_DIR / CODE)
    try:
        (root / REPO_DIR).rmdir()
    except OSError:
        pass
    store.rebuild()
    return out


_TAG_RE = re.compile(r"(?<![\w#])#[a-z][a-z-]*(?:\([^)]*\))?")


# The command that writes each kind of entry.
COMMANDS = {"scan": "#scan", "decision": "#decision", "standup": "#standup", "task": "#task"}


def source(store: Any, agent_id: str, created_date: str, created_time: str, kind: str = "") -> dict[str, Any] | None:
    """The chat message an entry was written after: the agent's last turn
    begun at or before the entry's minute, and the command for that kind of
    entry when the message holds it (#scan for a scan). Shown on the example
    project's entries, so a new user sees what to type to get the same."""
    from datetime import datetime, timedelta

    from .routers.deps import iso_moment
    from .sessions import chat_path, parse_turns

    moment = iso_moment(created_date, created_time)
    path = chat_path(store, agent_id) if agent_id else None
    if not moment or path is None:
        return None
    at = datetime.fromisoformat(moment) + timedelta(seconds=59)
    before = [t for t in parse_turns(path) if t.at <= at]
    if not before:
        return None
    turn = before[-1]
    text = " ".join((turn.user_summary or "").split())
    want = COMMANDS.get(kind, "")
    tags = [m.group(0).split("(")[0] for m in _TAG_RE.finditer(text)]
    row = store.query_one(
        "SELECT id, project FROM sessions WHERE agent_id = ? AND chat_start_line <= ? AND chat_end_line >= ?",
        (agent_id, turn.line, turn.line),
    ) or {}
    return {
        "agent_id": agent_id, "project": str(row.get("project") or ""), "session_id": str(row.get("id") or ""),
        "turn": turn.number, "command": want if want and want in tags else "",
        "excerpt": text[:160] + ("…" if len(text) > 160 else ""),
    }
