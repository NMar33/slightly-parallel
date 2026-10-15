"""The smart timer: time that counts itself while you work, and a clock
that stops while you are away.

Two jobs, one background tick (every 15 s):

**Away.** The server reads how long the computer has had no keyboard or
mouse (idle.py — any app, not only Slightly Parallel). Past the Away setting
(10 min), every running manual timer pauses *back-dated to the last
input*, so the idle minutes never count. On return a timer away for up
to three hours resumes by itself and the page says "Away 23 min, not
counted · Count it anyway"; a longer absence stays paused and asks.

**Working.** A project whose timer mode is ``auto`` counts time while
any signal says you are on it:
- a Slightly Parallel page, task window or terminal of the project is in front with
  input (the page sends a beat, ``beat(…, "page")``);
- you type in one of its terminals (``beat(…, "terminal")``);
- files change in its folder while you are at the keyboard (git status,
  read each tick — editors outside the browser).
A pause shorter than the grace (60 s) does not break the span. The span is
a time entry of its own, ``source: auto``, whose share is the *top-up*
above the manual timers running on that project: with a manual 10 %, auto
time adds 90 %, so every sum over entries stays right without knowing
about auto time at all. The span lands on the task in focus.

State that must survive a restart (open spans, timers this paused, the
notices) lives in ``timer/`` in the data root, which the watcher ignores.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import app_settings, idle
from .db import ViewStore
from .file_safety import atomic_write

log = logging.getLogger("sp.timeauto")

TICK_SEC = 15
MODES = ("remind", "auto", "manual")
#: Away this long or less: the timer resumes by itself on return.
RESUME_WITHIN_SEC = 3 * 3600
#: Files changing count only while someone is at the keyboard.
AT_KEYBOARD_SEC = 120
#: A task named this recently is still the one files and pages work on.
FOCUS_KEEP_SEC = 30 * 60


def _iso(t: datetime) -> str:
    return t.replace(microsecond=0).isoformat()


def _parse(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@dataclass
class Span:
    """An auto entry being written: its row, the top-up it carries, the
    task it counts for, and the last moment a signal was seen."""
    entry_id: str
    project: str
    top: int
    task_id: str
    last: str


class AutoTimer:
    def __init__(self, store: ViewStore, *, read_idle: Callable[[], tuple[float | None, str]] = idle.reading,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.root = Path(store.data_root)
        self.read_idle = read_idle
        self.clock = clock   # tests move time by hand
        self._lock = threading.RLock()
        self._beats: dict[str, dict[str, Any]] = {}      # project → {at, task_id, source}
        self._focus: dict[str, tuple[str, float]] = {}   # project → (task_id, at)
        self._files: dict[str, tuple[str, float]] = {}   # project → (fingerprint, changed at)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.spans: dict[str, Span] = {}
        self.paused: dict[str, str] = {}                  # entry id → paused_at this wrote
        self.away: dict[str, dict[str, Any]] = {}         # entry id → the notice
        self._load()

    # ------------------------------------------------------------ storage

    @property
    def folder(self) -> Path:
        return self.root / "timer"

    def _load(self) -> None:
        try:
            raw = json.loads((self.folder / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self.spans = {k: Span(**v) for k, v in (raw.get("spans") or {}).items()}
        self.paused = dict(raw.get("paused") or {})
        self.away = dict(raw.get("away") or {})

    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        state = {"spans": {k: asdict(v) for k, v in self.spans.items()},
                 "paused": self.paused, "away": self.away}
        atomic_write(self.folder / "state.json", json.dumps(state, indent=1))

    def modes(self) -> dict[str, str]:
        try:
            got = json.loads((self.folder / "modes.json").read_text(encoding="utf-8"))
            return {k: v for k, v in got.items() if v in MODES}
        except (OSError, ValueError, AttributeError):
            return {}

    def mode_of(self, project: str, cfg: dict[str, Any] | None = None) -> str:
        cfg = cfg or self._cfg()
        return self.modes().get(project) or str(cfg.get("time.default_mode") or "remind")

    def set_mode(self, project: str, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        with self._lock:
            modes = self.modes()
            modes[project] = mode
            # Whole or not at all: a half-written file reads as "no modes",
            # and the tick then closes every auto span that was open.
            atomic_write(self.folder / "modes.json", json.dumps(modes, indent=1, sort_keys=True))
            if mode != "auto" and project in self.spans:
                self._close(project, _parse(self.spans[project].last) or datetime.now())
                self._save()

    def _cfg(self) -> dict[str, Any]:
        try:
            return app_settings.load(self.root)
        except Exception:  # noqa: BLE001 — a bad settings file must not stop the clock
            return app_settings.defaults()

    # ------------------------------------------------------------ signals

    def beat(self, project: str, task_id: str = "", source: str = "page") -> None:
        """Someone is working on `project` right now (and on `task_id`)."""
        if not project:
            return
        now = self.clock()
        with self._lock:
            self._beats[project] = {"at": now, "task_id": task_id, "source": source}
            if task_id:
                self._focus[project] = (task_id, now)

    def _task_in_focus(self, project: str, now: float) -> str:
        got = self._focus.get(project)
        return got[0] if got and now - got[1] <= FOCUS_KEEP_SEC else ""

    def _files_changed_at(self, project: str, folder: Path) -> float:
        """When files in the project's folder last changed (0: not seen)."""
        from .gitwork import git
        out = git(folder, "status", "--porcelain=v1", "-uall")
        if out is None:
            return 0.0
        h = hashlib.sha1()
        for line in out.splitlines()[:500]:
            h.update(line.encode())
            try:
                h.update(str((folder / line[3:].split(" -> ")[-1].strip('"')).stat().st_mtime_ns).encode())
            except OSError:
                pass
        fp = h.hexdigest()
        prev = self._files.get(project)
        at = prev[1] if prev else 0.0
        if prev is not None and prev[0] != fp:
            at = self.clock()
        self._files[project] = (fp, at)
        return at

    def _file_signals(self, cfg: dict[str, Any], idle_sec: float | None) -> dict[str, float]:
        """project → when its files last changed, for every auto project,
        while someone is at the keyboard. Asked of git, so never under the
        lock: a page's beat waits on that lock, and git may take seconds."""
        from .termlib import registered_project_dirs
        if idle_sec is None or idle_sec >= AT_KEYBOARD_SEC:
            return {}
        modes = self.modes()
        default = str(cfg.get("time.default_mode") or "remind")
        return {
            project: self._files_changed_at(project, folder)
            for project, folder in registered_project_dirs(self.root).items()
            if (modes.get(project) or default) == "auto"
        }

    # ------------------------------------------------------------ the rows

    def _running_manual(self, project: str = "") -> list[dict[str, Any]]:
        from .entities import ENTITIES
        view = ENTITIES["time_entry"].view
        where = "COALESCE(ended_at, '') = '' AND COALESCE(CAST(source AS VARCHAR), '') <> 'auto'"
        if project:
            return self.store.query(f"SELECT * FROM {view} WHERE {where} AND project = ?", (project,))
        return self.store.query(f"SELECT * FROM {view} WHERE {where}")

    def _sprint_of(self, task_id: str) -> str:
        if not task_id:
            return ""
        from .entities import ENTITIES
        rows = self.store.query(f"SELECT sprint_id FROM {ENTITIES['task'].view} WHERE id = ?", (task_id,))
        return str((rows[0].get("sprint_id") if rows else "") or "")

    def _open(self, project: str, top: int, task_id: str, start: datetime) -> None:
        from .date_utils import today_yymm_dd
        from .entities import ENTITIES
        from .routers.lenses import create_entity
        payload = {
            "created_date": today_yymm_dd(), "created_time": start.strftime("%H:%M"),
            "project": project, "agent_id": "operator",
            "started_at": _iso(start), "ended_at": "", "paused_at": "",
            "paused_total_sec": 0, "duration_min": 0, "share_pct": top,
            "goal_id": "", "sprint_id": self._sprint_of(task_id), "note": "",
            "task_id": task_id, "source": "auto",
        }
        made = create_entity(self.store, ENTITIES["time_entry"], payload)
        self.spans[project] = Span(str(made["metadata"]["id"]), project, top, task_id, _iso(start))

    def _close(self, project: str, end: datetime) -> None:
        from .routers.time_tracking import _delete, _patch
        span = self.spans.pop(project, None)
        if span is None:
            return
        start = next((_parse(str(r.get("started_at") or "")) for r in self._rows(span.entry_id)), None)
        mins = round(max(0.0, (end - start).total_seconds()) / 60) if start else 0
        try:
            if mins < 1:
                _delete(self.store, span.entry_id)   # a glance is not work
            else:
                _patch(self.store, span.entry_id, {"ended_at": _iso(end), "duration_min": str(mins)})
        except Exception as exc:  # noqa: BLE001 — a vanished row is closed already
            log.info("auto span %s: %s", span.entry_id, exc)

    def _rows(self, entry_id: str) -> list[dict[str, Any]]:
        from .entities import ENTITIES
        return self.store.query(f"SELECT * FROM {ENTITIES['time_entry'].view} WHERE id = ?", (entry_id,))

    def recover(self) -> None:
        """After a restart: spans left open close where they were last seen;
        an auto row nobody holds any more is removed (it cannot be timed)."""
        from .entities import ENTITIES
        from .routers.time_tracking import _delete
        with self._lock:
            for project, span in list(self.spans.items()):
                self._close(project, _parse(span.last) or datetime.now())
            held = {s.entry_id for s in self.spans.values()}
            for r in self.store.query(
                f"SELECT id FROM {ENTITIES['time_entry'].view} WHERE COALESCE(ended_at, '') = '' "
                "AND CAST(source AS VARCHAR) = 'auto'"
            ):
                if r["id"] not in held:
                    try:
                        _delete(self.store, str(r["id"]))
                    except Exception:  # noqa: BLE001
                        pass
            self._save()

    # ------------------------------------------------------------ the tick

    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.fromtimestamp(self.clock()).replace(microsecond=0)
        cfg = self._cfg()
        idle_sec, _how = self.read_idle()
        changed = self._file_signals(cfg, idle_sec)
        with self._lock:
            before = json.dumps([{k: asdict(v) for k, v in self.spans.items()}, self.paused, self.away], sort_keys=True)
            self._away(now, cfg, idle_sec)
            self._working(now, cfg, idle_sec, changed)
            after = json.dumps([{k: asdict(v) for k, v in self.spans.items()}, self.paused, self.away], sort_keys=True)
            if before != after:
                self._save()

    def _away(self, now: datetime, cfg: dict[str, Any], idle_sec: float | None) -> None:
        from .routers.time_tracking import _patch, time_resume_row
        if not cfg.get("time.idle_pause", True) or idle_sec is None:
            return
        limit = int(cfg.get("time.idle_minutes") or 10) * 60
        if idle_sec >= limit:
            last_input = now - timedelta(seconds=int(idle_sec))
            for r in self._running_manual():
                if str(r.get("paused_at") or "") or r["id"] in self.paused:
                    continue
                started = _parse(str(r.get("started_at") or "")) or last_input
                at = _iso(max(last_input, started))
                _patch(self.store, str(r["id"]), {"paused_at": at})
                self.paused[str(r["id"])] = at
            return
        if idle_sec >= 60 or not self.paused:
            return
        back = now - timedelta(seconds=int(idle_sec))
        for entry_id, at in list(self.paused.items()):
            self.paused.pop(entry_id)
            rows = self._rows(entry_id)
            if not rows or str(rows[0].get("ended_at") or "") or str(rows[0].get("paused_at") or "") != at:
                continue   # stopped, resumed or moved by hand meanwhile
            gap = int((back - (_parse(at) or back)).total_seconds())
            long = gap > RESUME_WITHIN_SEC
            if not long:
                time_resume_row(self.store, rows[0], now)
            self.away[entry_id] = {"entry_id": entry_id, "project": rows[0].get("project"),
                                   "from": at, "to": _iso(back), "sec": gap, "long": long}

    def _working(self, now: datetime, cfg: dict[str, Any], idle_sec: float | None,
                 changed: dict[str, float] | None = None) -> None:
        from .termlib import registered_project_dirs
        grace = int(cfg.get("time.grace_seconds") or 60)
        limit = int(cfg.get("time.idle_minutes") or 10) * 60
        wall = self.clock()
        present = idle_sec is None or idle_sec < limit
        if changed is None:
            changed = self._file_signals(cfg, idle_sec)
        modes = self.modes()
        default = str(cfg.get("time.default_mode") or "remind")
        folders = registered_project_dirs(self.root)
        projects = set(self._beats) | set(self.spans) | {p for p in folders if (modes.get(p) or default) == "auto"}
        for project in sorted(projects):
            auto = (modes.get(project) or default) == "auto"
            signal = 0.0
            b = self._beats.get(project)
            if b:
                signal = b["at"]
            if auto and project in folders:
                signal = max(signal, changed.get(project, 0.0))
            live = auto and present and signal > 0 and wall - signal <= grace
            span = self.spans.get(project)
            if not live:
                if span:
                    self._close(project, _parse(span.last) or now)
                continue
            base = sum(int(r.get("share_pct") or 100) for r in self._running_manual(project)
                       if not str(r.get("paused_at") or ""))
            top = max(0, 100 - base)
            task = (b or {}).get("task_id") or self._task_in_focus(project, wall)
            seen = datetime.fromtimestamp(signal).replace(microsecond=0)
            if span and (span.top != top or (task and task != span.task_id)):
                self._close(project, seen)
                span = None
            if top <= 0:
                continue
            if span is None:
                self._open(project, top, task, seen)
            else:
                span.last = _iso(max(seen, _parse(span.last) or seen))

    # ------------------------------------------------------------ reading

    def status(self) -> dict[str, Any]:
        cfg = self._cfg()
        idle_sec, how = self.read_idle()
        grace = int(cfg.get("time.grace_seconds") or 60)
        with self._lock:
            return {
                "idle_sec": None if idle_sec is None else int(idle_sec),
                "idle_source": how,
                "idle_pause": bool(cfg.get("time.idle_pause", True)),
                "idle_minutes": int(cfg.get("time.idle_minutes") or 10),
                "grace_seconds": grace,
                "default_mode": str(cfg.get("time.default_mode") or "remind"),
                "modes": self.modes(),
                "working": [{"project": s.project, "entry_id": s.entry_id, "task_id": s.task_id, "top": s.top}
                            for s in self.spans.values()],
                "away": list(self.away.values()),
            }

    def dismiss(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            got = self.away.pop(entry_id, None)
            self._save()
            return got

    # ------------------------------------------------------------ the thread

    def start(self) -> None:
        self.recover()

        def run() -> None:
            while not self._stop.wait(TICK_SEC):
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 — the clock keeps going
                    log.exception("time tick failed")

        self._thread = threading.Thread(target=run, name="timeauto", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for project, span in list(self.spans.items()):
                self._close(project, _parse(span.last) or datetime.now())
            self._save()


def of(app: Any) -> AutoTimer:
    """The app's timer, made on first use (a test app gets one with no thread)."""
    timer = getattr(app.state, "timer", None)
    if timer is None:
        timer = AutoTimer(app.state.store)
        app.state.timer = timer
    return timer
