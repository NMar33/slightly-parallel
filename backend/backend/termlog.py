"""The terminal's own log: how the terminal window works, to find its bugs
and slowdowns (tk_f89e84c4).

Three modes, Settings › Terminal › Terminal log (``terminal.log``):

- ``off``   — nothing is kept.
- ``light`` — the default. The page counts (frame times as a histogram,
  bytes, pastes, wheel paths, reconnects, errors, memory) and sends one row
  a minute when something happened; the server adds a row of its own (tmux
  call times and timeouts, slow writes to a terminal, slow sends to a
  view). One small JSONL file a day, ``light-YYYY-MM-DD.jsonl``, 14 days.
- ``full``  — everything of light, plus a stream of events with their times
  (each key, paste, wheel, frame, socket message: its kind and size), kept
  in rotating ``full-*.jsonl`` files with a size cap. Full turns itself back
  to light after its hours (two by default; the Monitor's button gives one).

What is never kept: what was typed, pasted or printed. Rows hold kinds,
sizes, counts and times only; strings are short names (a route, a kind, a
project code, an error's first words) cut at 120 characters.

Everything lives under ``<data root>/terminal/log/``: this machine's record,
left out of backups with the rest of ``terminal/`` (backup.EXCLUDE_DIRS).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from . import app_settings
from .file_safety import atomic_write_json, safe_read_json

MODES = ("off", "light", "full")
LIGHT_KEEP_DAYS = 14
FULL_KEEP_DAYS = 3
FULL_FILE_BYTES = 5_000_000
FULL_TOTAL_BYTES = 40_000_000
FULL_HOURS = 2.0
#: A batch the page sends: its body, its rows, its events.
MAX_BATCH_BYTES = 2_000_000
MAX_ROWS = 20
MAX_EVENTS = 20_000
#: A row is small: a minute of counters.
MAX_ROW_BYTES = 64_000
MAX_TEXT = 120
#: Frame-time buckets, in ms: a frame falls in the first bucket whose edge is
#: above it; the last bucket is "over 1000". The page uses the same edges.
EDGES = (8, 12, 17, 20, 25, 34, 50, 75, 100, 150, 200, 300, 500, 1000)
#: A frame over budget, and a stall.
SLOW_FRAME_MS = 50
STALL_MS = 200
#: A tmux call or a write slower than this is a stall on the server.
SLOW_CALL_MS = 500
SLOW_SEND_MS = 100

_lock = threading.Lock()


# ------------------------------------------------------------------ places

def log_dir(data_root: Path) -> Path:
    return Path(data_root) / "terminal" / "log"


def _state_path(data_root: Path) -> Path:
    return log_dir(data_root) / "state.json"


def _light_path(data_root: Path, day: str) -> Path:
    return log_dir(data_root) / f"light-{day}.jsonl"


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


# -------------------------------------------------------------------- mode

def _state(data_root: Path) -> dict[str, Any]:
    p = _state_path(data_root)
    if not p.exists():
        return {}
    try:
        got = safe_read_json(p)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _setting(data_root: Path) -> str:
    try:
        v = app_settings.load(data_root).get("terminal.log", "light")
    except Exception:  # noqa: BLE001 — a bad settings file: the default
        v = "light"
    return v if v in MODES else "light"


def mode(data_root: Path, now: float | None = None) -> dict[str, Any]:
    """The mode in force, read only: Full whose hours are over reads as Light
    (the next batch writes it back, housekeep)."""
    now = time.time() if now is None else now
    setting = _setting(data_root)
    until = _state(data_root).get("full_until")
    until = float(until) if isinstance(until, (int, float)) else None
    effective = setting
    if setting == "full" and until is not None and until <= now:
        effective = "light"
    if setting != "full":
        until = None
    REC.mode = effective
    return {"mode": effective, "setting": setting, "full_until": until, "full_hours": FULL_HOURS}


def set_mode(data_root: Path, new: str, hours: float | None = None, now: float | None = None) -> dict[str, Any]:
    """Switch the log; Full gets its hours (FULL_HOURS unless given)."""
    if new not in MODES:
        raise ValueError(f"mode is one of {', '.join(MODES)}")
    now = time.time() if now is None else now
    app_settings.save(data_root, {"terminal.log": new})
    st = _state(data_root)
    if new == "full":
        st["full_until"] = now + 3600 * float(hours if hours else FULL_HOURS)
    else:
        st.pop("full_until", None)
    log_dir(data_root).mkdir(parents=True, exist_ok=True)
    atomic_write_json(_state_path(data_root), st)
    return mode(data_root, now)


def housekeep(data_root: Path, now: float | None = None) -> None:
    """On a batch: give a Full switched on in Settings its hours, turn a Full
    whose hours are over back to Light, and drop old files."""
    now = time.time() if now is None else now
    setting = _setting(data_root)
    st = _state(data_root)
    until = st.get("full_until")
    if setting == "full" and not isinstance(until, (int, float)):
        st["full_until"] = now + 3600 * FULL_HOURS
        log_dir(data_root).mkdir(parents=True, exist_ok=True)
        atomic_write_json(_state_path(data_root), st)
    elif setting == "full" and isinstance(until, (int, float)) and until <= now:
        app_settings.save(data_root, {"terminal.log": "light"})
        st.pop("full_until", None)
        st["full_ended"] = now
        atomic_write_json(_state_path(data_root), st)
    _prune(data_root, now)


def _prune(data_root: Path, now: float) -> None:
    d = log_dir(data_root)
    if not d.exists():
        return
    oldest_light = _day(now - LIGHT_KEEP_DAYS * 86400)
    fulls: list[tuple[float, Path, int]] = []
    for p in d.iterdir():
        name = p.name
        if name.startswith("light-") and name.endswith(".jsonl"):
            if name[6:16] < oldest_light:
                p.unlink(missing_ok=True)
        elif name.startswith("full-") and name.endswith(".jsonl"):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < now - FULL_KEEP_DAYS * 86400:
                p.unlink(missing_ok=True)
            else:
                fulls.append((st.st_mtime, p, st.st_size))
    # The newest files up to the cap; older ones go.
    total = 0
    for _, p, size in sorted(fulls, key=lambda x: -x[0]):
        total += size
        if total > FULL_TOTAL_BYTES:
            p.unlink(missing_ok=True)


# --------------------------------------------------------- what is accepted

def _clean(v: Any, depth: int = 0) -> Any:
    """A value of a row as it may be stored: numbers, short strings, small
    lists and dicts. Anything longer is cut, anything else dropped."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v if v == v and abs(v) < 1e15 else 0
    if isinstance(v, str):
        return v[:MAX_TEXT]
    if depth >= 5:
        return None
    if isinstance(v, list):
        return [_clean(x, depth + 1) for x in v[:200]]
    if isinstance(v, dict):
        return {str(k)[:64]: _clean(x, depth + 1) for k, x in list(v.items())[:200]}
    return None


ROW_KEYS = ("t", "src", "page", "where", "frames", "longtasks", "terms", "scroll", "paste", "sock",
            "errors", "fetch", "mem", "findings", "self", "keys", "inputs")


def _row(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("a row is an object")
    t = raw.get("t")
    if not isinstance(t, (int, float)) or isinstance(t, bool):
        raise ValueError("a row needs its minute, t")
    row = {k: _clean(raw[k]) for k in ROW_KEYS if k in raw}
    row["src"] = "page"
    if len(json.dumps(row)) > MAX_ROW_BYTES:
        raise ValueError(f"a row is at most {MAX_ROW_BYTES // 1000} KB")
    return row


def _event(raw: Any) -> list[Any]:
    """[t_ms, kind, sid, a, b]: a time, a kind, a terminal, two numbers (or a short word)."""
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError("an event is [t, kind, sid, a, b]")
    t, kind = raw[0], raw[1]
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not isinstance(kind, str):
        raise ValueError("an event is [t, kind, sid, a, b]")
    out: list[Any] = [round(float(t), 1), kind[:24]]
    for x in raw[2:5]:
        out.append(_clean(x) if isinstance(x, (int, float, str)) and not isinstance(x, bool) else None)
    return out


def validate(batch: Any) -> tuple[list[dict[str, Any]], list[list[Any]], str]:
    """The rows and events of a batch, or ValueError: nothing is written
    for a batch that is refused."""
    if not isinstance(batch, dict):
        raise ValueError("a batch is an object")
    rows = batch.get("rows") or []
    events = batch.get("events") or []
    if not isinstance(rows, list) or not isinstance(events, list):
        raise ValueError("rows and events are lists")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows a batch")
    if len(events) > MAX_EVENTS:
        raise ValueError(f"at most {MAX_EVENTS} events a batch")
    page = str(batch.get("page") or "")[:24]
    return [_row(r) for r in rows], [_event(e) for e in events], page


# ------------------------------------------------------------------ writing

def _append(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))


def _full_file(data_root: Path, now: float) -> Path:
    """The full file being written: the newest, until it passes its size."""
    d = log_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    newest = sorted(d.glob("full-*.jsonl"))
    if newest and newest[-1].stat().st_size < FULL_FILE_BYTES:
        return newest[-1]
    return d / f"full-{datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S')}.jsonl"


def accept(data_root: Path, batch: Any, now: float | None = None) -> dict[str, Any]:
    """Store a page's batch (validated first: a refused one writes nothing),
    the server's own minute with it, and answer the mode in force."""
    now = time.time() if now is None else now
    rows, events, page = validate(batch)
    housekeep(data_root, now)
    m = mode(data_root, now)
    if m["mode"] == "off":
        REC.take()
        return {**m, "kept": 0}
    lines = [json.dumps(r, separators=(",", ":")) for r in rows]
    server = REC.take(now)
    if server:
        lines.append(json.dumps(server, separators=(",", ":")))
    _append(_light_path(data_root, _day(now)), lines)
    kept = len(rows)
    if m["mode"] == "full":
        evs = [[e[0], e[1], e[2] if len(e) > 2 else None, *(e[3:5])] for e in events]
        evs += REC.drain_events()
        if evs:
            _append(_full_file(data_root, now),
                    [json.dumps({"page": page, "e": e} if page else {"e": e}, separators=(",", ":")) for e in evs])
            kept += len(evs)
    else:
        REC.drain_events()
    return {**m, "kept": kept}


# --------------------------------------------------------- the server's own

class Recorder:
    """The server's half of the light log: tmux calls, writes to a terminal,
    sends to a view. Counted per minute in memory; taken with a page's batch.
    In Full also a bounded stream of events."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.mode = "light"
        self.events: deque[list[Any]] = deque(maxlen=20_000)
        self._reset(time.time())

    def _reset(self, now: float) -> None:
        self.since = now
        self.tmux: dict[str, list[float]] = {}  # cmd → [n, total ms, max ms, timeouts, slow]
        self.writes = [0, 0.0, 0.0, 0]          # n, total ms, max ms, slow
        self.sends = [0, 0, 0.0, 0]             # n, bytes, max ms, slow
        self.terms: dict[str, list[int]] = {}   # sid → [bytes out to the views, bytes written]

    def _event(self, kind: str, sid: str, a: float, b: Any = None) -> None:
        if self.mode == "full":
            self.events.append([round(time.time() * 1000, 1), kind, sid, round(a, 2), b])

    def tmux_call(self, cmd: str, ms: float, timed_out: bool = False) -> None:
        if self.mode == "off":
            return
        with self.lock:
            s = self.tmux.setdefault(cmd[:24], [0, 0.0, 0.0, 0, 0])
            s[0] += 1
            s[1] += ms
            s[2] = max(s[2], ms)
            s[3] += 1 if timed_out else 0
            s[4] += 1 if ms >= SLOW_CALL_MS else 0
            self._event("tmux", "", ms, cmd[:24] + (" timeout" if timed_out else ""))

    def write(self, sid: str, ms: float, n: int) -> None:
        if self.mode == "off":
            return
        with self.lock:
            w = self.writes
            w[0] += 1
            w[1] += ms
            w[2] = max(w[2], ms)
            w[3] += 1 if ms >= SLOW_CALL_MS else 0
            self.terms.setdefault(sid, [0, 0])[1] += n
            self._event("write", sid, ms, n)

    def send(self, sid: str, ms: float, n: int) -> None:
        if self.mode == "off":
            return
        with self.lock:
            s = self.sends
            s[0] += 1
            s[1] += n
            s[2] = max(s[2], ms)
            s[3] += 1 if ms >= SLOW_SEND_MS else 0
            self.terms.setdefault(sid, [0, 0])[0] += n
            if ms >= SLOW_SEND_MS or self.mode == "full":
                self._event("send", sid, ms, n)

    def take(self, now: float | None = None) -> dict[str, Any] | None:
        """The minute so far as a row, or None when nothing happened; reset."""
        now = time.time() if now is None else now
        with self.lock:
            if not self.tmux and not self.writes[0] and not self.sends[0]:
                self.since = now
                return None
            findings = []
            for cmd, s in self.tmux.items():
                if s[3]:
                    findings.append({"t": round(now * 1000), "kind": "tmux-timeout", "sid": "", "p": "",
                                     "doing": "server", "n": s[3], "what": cmd})
            if self.writes[3]:
                findings.append({"t": round(now * 1000), "kind": "write-stall", "sid": "", "p": "",
                                 "doing": "typing", "n": round(self.writes[2]), "what": "ConPTY" if os.name == "nt" else "pty"})
            row = {
                "t": int(self.since // 60 * 60), "src": "server",
                "tmux": {k: {"n": int(v[0]), "ms": round(v[1], 1), "max": round(v[2], 1), "timeouts": int(v[3]), "slow": int(v[4])}
                         for k, v in self.tmux.items()},
                "writes": {"n": self.writes[0], "ms": round(self.writes[1], 1), "max": round(self.writes[2], 1), "slow": self.writes[3]},
                "sends": {"n": self.sends[0], "bytes": self.sends[1], "max": round(self.sends[2], 1), "slow": self.sends[3]},
                "terms": {k: {"out": v[0], "in": v[1]} for k, v in list(self.terms.items())[:50]},
                "findings": findings,
            }
            self._reset(now)
            return row

    def peek(self) -> dict[str, Any]:
        """The minute so far, without taking it."""
        with self.lock:
            return {"since": self.since, "tmux": {k: list(v) for k, v in self.tmux.items()},
                    "writes": list(self.writes), "sends": list(self.sends), "events": len(self.events)}

    def drain_events(self) -> list[list[Any]]:
        with self.lock:
            out = list(self.events)
            self.events.clear()
            return out


REC = Recorder()


class timed:
    """``with termlog.timed("write", sid, n):`` — how long a write to a
    terminal took, into the recorder. Costs two clock reads."""

    def __init__(self, what: str, sid: str = "", n: int = 0) -> None:
        self.what, self.sid, self.n = what, sid, n

    def __enter__(self) -> "timed":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        ms = (time.perf_counter() - self.t0) * 1000
        if self.what == "write":
            REC.write(self.sid, ms, self.n)
        elif self.what == "send":
            REC.send(self.sid, ms, self.n)


# ----------------------------------------------------------------- reading

def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
    return out


def _hist_add(into: list[int], h: Any) -> None:
    if isinstance(h, list):
        for i, n in enumerate(h[: len(EDGES) + 1]):
            if isinstance(n, (int, float)):
                into[i] += int(n)


def percentile(hist: list[int], q: float, top: float = 0.0) -> float:
    """The bucket edge under which q of the frames fall (the max for the last bucket)."""
    total = sum(hist)
    if not total:
        return 0.0
    need = q * total
    run = 0
    for i, n in enumerate(hist):
        run += n
        if run >= need:
            return float(EDGES[i]) if i < len(EDGES) else max(top, float(EDGES[-1]))
    return top


def _over(hist: list[int], ms: float) -> int:
    """Frames in the buckets above `ms` (an edge)."""
    i = EDGES.index(ms) + 1 if ms in EDGES else len(EDGES)
    return sum(hist[i:])


def summary(data_root: Path, day: str = "", now: float | None = None) -> dict[str, Any]:
    """A day of the light log for the Monitor: the day in one line, per hour,
    the recent findings, the server's tmux calls. Read only."""
    now = time.time() if now is None else now
    day = day or _day(now)
    rows = _read_rows(_light_path(data_root, day))
    # The server's minute so far, not yet written (read only: not taken).
    hist = [0] * (len(EDGES) + 1)
    top = 0.0
    hours = [{"h": h, "frames": 0, "slow": 0, "stalls": 0, "errors": 0, "reconnects": 0, "findings": 0,
              "in": 0, "out": 0, "hist": [0] * (len(EDGES) + 1)} for h in range(24)]
    totals = {"frames": 0, "slow": 0, "stalls": 0, "errors": 0, "reconnects": 0, "findings": 0, "in": 0, "out": 0,
              "pastes": 0, "keys": 0, "wheels": 0, "longtasks": 0, "fetch_errors": 0}
    tmux: dict[str, dict[str, float]] = {}
    writes = {"n": 0, "max": 0.0, "slow": 0}
    sends = {"n": 0, "max": 0.0, "slow": 0}
    findings: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    scroll: dict[str, int] = {}
    paste: dict[str, int] = {}
    mem: dict[str, Any] = {}
    self_ms = 0.0
    page_minutes = 0
    for r in rows:
        t = r.get("t")
        if not isinstance(t, (int, float)):
            continue
        hr = hours[datetime.fromtimestamp(t).hour]
        for f in r.get("findings") or []:
            if isinstance(f, dict):
                findings.append(f)
                k = str(f.get("kind") or "")
                by_kind[k] = by_kind.get(k, 0) + 1
                hr["findings"] += 1
                totals["findings"] += 1
                if k == "scroll-stall":
                    hr["stalls"] += 1
                    totals["stalls"] += 1
                if k == "reconnect":
                    hr["reconnects"] += 1
                    totals["reconnects"] += 1
        if r.get("src") == "server":
            for cmd, s in (r.get("tmux") or {}).items():
                if not isinstance(s, dict):
                    continue
                a = tmux.setdefault(cmd, {"n": 0, "ms": 0.0, "max": 0.0, "timeouts": 0, "slow": 0})
                a["n"] += s.get("n", 0)
                a["ms"] += s.get("ms", 0)
                a["max"] = max(a["max"], s.get("max", 0))
                a["timeouts"] += s.get("timeouts", 0)
                a["slow"] += s.get("slow", 0)
            for into, got in ((writes, r.get("writes")), (sends, r.get("sends"))):
                if isinstance(got, dict):
                    into["n"] += got.get("n", 0)
                    into["max"] = max(into["max"], got.get("max", 0))
                    into["slow"] += got.get("slow", 0)
            continue
        page_minutes += 1
        for fr in (r.get("frames") or {}).values():
            if not isinstance(fr, dict):
                continue
            h = [0] * (len(EDGES) + 1)
            _hist_add(h, fr.get("h"))
            _hist_add(hist, h)
            _hist_add(hr["hist"], h)
            top = max(top, float(fr.get("max") or 0))
            n = sum(h)
            hr["frames"] += n
            totals["frames"] += n
            slow = _over(h, SLOW_FRAME_MS)
            hr["slow"] += slow
            totals["slow"] += slow
        errs = r.get("errors") or {}
        if isinstance(errs, dict):
            e = sum(v for v in errs.values() if isinstance(v, (int, float)))
            hr["errors"] += int(e)
            totals["errors"] += int(e)
            totals["fetch_errors"] += int(errs.get("fetch") or 0)
        for tm in (r.get("terms") or {}).values():
            if isinstance(tm, dict):
                for k in ("in", "out"):
                    v = int(tm.get(k) or 0)
                    hr[k] += v
                    totals[k] += v
                totals["pastes"] += int(tm.get("pastes") or 0)
                totals["keys"] += int(tm.get("keys") or 0)
                totals["wheels"] += int(tm.get("wheels") or 0)
        lt = r.get("longtasks") or {}
        if isinstance(lt, dict):
            totals["longtasks"] += int(lt.get("n") or 0)
        for src, into in ((r.get("scroll"), scroll), (r.get("paste"), paste)):
            if isinstance(src, dict):
                for k, v in src.items():
                    if isinstance(v, (int, float)):
                        into[k] = into.get(k, 0) + int(v)
        if isinstance(r.get("mem"), dict) and r["mem"]:
            mem = {**r["mem"], "t": t}
        if isinstance(r.get("self"), dict):
            self_ms += float(r["self"].get("ms") or 0)
    out_hours = []
    for hr in hours:
        h = hr.pop("hist")
        hr["p95"] = percentile(h, 0.95)
        out_hours.append(hr)
    findings.sort(key=lambda f: -(f.get("t") or 0))
    files = _files(data_root)
    return {
        "day": day,
        **mode(data_root, now),
        "totals": {**totals, "p50": percentile(hist, 0.5), "p95": percentile(hist, 0.95), "max": round(top, 1),
                   "page_minutes": page_minutes, "self_ms": round(self_ms, 1)},
        "edges": list(EDGES),
        "hist": hist,
        "hours": out_hours,
        "findings": findings[:60],
        "by_kind": by_kind,
        "scroll": scroll,
        "paste": paste,
        "mem": mem,
        "server": {"tmux": {k: {**v, "avg": round(v["ms"] / v["n"], 1) if v["n"] else 0} for k, v in tmux.items()},
                   "writes": writes, "sends": sends},
        "files": files,
    }


def _files(data_root: Path) -> dict[str, Any]:
    d = log_dir(data_root)
    light = full = 0
    n_full = 0
    if d.exists():
        for p in d.iterdir():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if p.name.startswith("light-"):
                light += size
            elif p.name.startswith("full-"):
                full += size
                n_full += 1
    return {"folder": str(d), "light_bytes": light, "full_bytes": full, "full_files": n_full}


def report(data_root: Path, now: float | None = None, tmux_version: str = "") -> dict[str, Any]:
    """The bundle for a bug report: the day's light rows, the last hour of
    the full log (when it was on), versions, the system, the terminal's
    settings. Bounded, and with no text anyone typed or the terminal printed."""
    from . import __version__
    now = time.time() if now is None else now
    try:
        cfg = app_settings.load(data_root)
    except Exception:  # noqa: BLE001
        cfg = {}
    full: list[Any] = []
    d = log_dir(data_root)
    if d.exists():
        since_ms = (now - 3600) * 1000
        for p in sorted(d.glob("full-*.jsonl"), reverse=True):
            try:
                if p.stat().st_mtime < now - 3600:
                    break
            except OSError:
                continue
            got = []
            for r in _read_rows(p):
                e = r.get("e")
                if isinstance(e, list) and e and isinstance(e[0], (int, float)) and e[0] >= since_ms:
                    got.append(r)
            full = got + full
            if len(full) > 200_000:
                full = full[-200_000:]
                break
    today = _day(now)
    yesterday = _day(now - 86400)
    return {
        "made": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "what": "Slightly Parallel terminal log: counts, sizes and times only — no typed, pasted or printed text.",
        "versions": {"slightly_parallel": __version__, "python": platform.python_version(), "tmux": tmux_version},
        "system": {"os": platform.system(), "release": platform.release(), "machine": platform.machine(),
                   "platform": sys.platform, "cpus": os.cpu_count()},
        "settings": {k: v for k, v in cfg.items() if k.startswith("terminal.")},
        "mode": mode(data_root, now),
        "summary": summary(data_root, today, now),
        "light": {yesterday: _read_rows(_light_path(data_root, yesterday)), today: _read_rows(_light_path(data_root, today))},
        "full_last_hour": full,
        "server_now": REC.peek(),
    }


def days_kept(data_root: Path) -> list[str]:
    d = log_dir(data_root)
    if not d.exists():
        return []
    return sorted(p.name[6:16] for p in d.glob("light-*.jsonl"))


__all__ = ["MODES", "EDGES", "REC", "Recorder", "accept", "housekeep", "log_dir", "mode", "percentile",
           "report", "set_mode", "summary", "timed", "validate", "days_kept"]
