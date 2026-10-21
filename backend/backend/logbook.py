"""The server's log, kept small and readable: what ran, how long, what broke.

Two homes for the same lines. A ring of the last few thousand records in
memory, which the health page reads and sums up; and a rotating file of a
few megabytes beside the server, for after a restart. Neither can fill a
disk: the ring is a fixed length and the file rotates. Stdout keeps only
warnings and errors, so the supervisor's own log stays short.

What a line holds: the time, the level, the logger, the message, and for
a request its method, path, status and milliseconds. Never the content of
a chat or an entry — only that something happened, and how long it took.

The point of it: when something is slow or wrong, the operator copies the
health page as text and pastes it to an AI, which reads it the way a
person who wrote the server would.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

RING_SIZE = 4000
FILE_BYTES = 5 * 1024 * 1024
FILE_KEEP = 3
# A request over this is named slow in the log; the rebuild has its own bar.
SLOW_REQUEST_MS = 300
SLOW_REBUILD_MS = 2000

STARTED_AT = time.time()
EXTRA_FIELDS = ("method", "path", "status", "ms", "etag", "client", "why",
                "rss_mb", "peak_mb", "threads", "open_files")

_ID = re.compile(r"/(?:[a-z]{2,3}_[0-9a-f]{6,}|cc-[0-9a-f]{6,}|ses_[0-9a-f]{6,})(?=/|$)")


# A secret in a URL stays out of the log: uvicorn names every socket it
# accepts with its query, and the terminal's carries its token.
_SECRET = re.compile(r"((?:token|sp_token)=)[^&\s\"']+", re.IGNORECASE)


def redact(text: str) -> str:
    return _SECRET.sub(r"\1…", text)


def shape(path: str) -> str:
    """One shape for every id: /api/tasks/tk_1234abcd → /api/tasks/{id}."""
    return _ID.sub("/{id}", path.split("?")[0])


class RingHandler(logging.Handler):
    """The last ``size`` records, as plain dicts, in memory."""

    def __init__(self, size: int = RING_SIZE) -> None:
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=size)
        self._lock_ = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            row: dict[str, Any] = {
                "ts": record.created, "level": record.levelname,
                "logger": record.name, "msg": redact(record.getMessage()),
            }
            for k in EXTRA_FIELDS:
                v = getattr(record, k, None)
                if v is not None:
                    row[k] = v
            if record.exc_info and record.exc_info[1] is not None:
                row["exc"] = f"{type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            with self._lock_:
                self.records.append(row)
        except Exception:  # noqa: BLE001 — a log line must never raise
            pass

    def tail(self, limit: int = 300, min_level: str = "INFO") -> list[dict[str, Any]]:
        floor = logging.getLevelName(min_level) if isinstance(min_level, str) else min_level
        floor = floor if isinstance(floor, int) else logging.INFO
        with self._lock_:
            rows = list(self.records)
        # An unknown level name counts as 0: getLevelName answers it with a string.
        levels = logging.getLevelNamesMapping()
        out = [r for r in rows if levels.get(str(r["level"]), 0) >= floor]
        return out[-limit:]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock_:
            return list(self.records)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "ts": time.time(), "level": record.levelname,
            "logger": record.name, "msg": redact(record.getMessage()),
        }
        for k in EXTRA_FIELDS:
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


RING = RingHandler()
LOG_FILE: Path | None = None

#: The memory line goes to the log this often, and warns past these.
MEMORY_EVERY_S = 300
MEMORY_HIGH_MB = 1024
MEMORY_JUMP_MB = 300
_last_rss = 0.0


def process_memory() -> dict[str, Any]:
    """This process: memory now and at its peak, threads, open files — on
    Linux, macOS and Windows (psutil; the peak from the OS's own count)."""
    out: dict[str, Any] = {"rss_mb": 0.0, "peak_mb": 0.0, "threads": 0, "open_files": 0}
    try:
        import psutil
        p = psutil.Process()
        mi = p.memory_info()
        out["rss_mb"] = round(mi.rss / 1048576, 1)
        out["peak_mb"] = round(getattr(mi, "peak_wset", 0) / 1048576, 1)     # Windows
        out["threads"] = p.num_threads()
        out["open_files"] = p.num_handles() if hasattr(p, "num_handles") else p.num_fds()  # pyright: ignore[reportAttributeAccessIssue] — Windows only
    except Exception:  # noqa: BLE001 — a count we cannot read stays 0
        pass
    if not out["peak_mb"]:
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss     # KB on Linux, bytes on macOS
            out["peak_mb"] = round(peak / 1048576 if sys.platform == "darwin" else peak / 1024, 1)
        except Exception:  # noqa: BLE001
            pass
    # Read a moment apart, the peak can come out a hair under the reading now.
    out["peak_mb"] = max(out["peak_mb"], out["rss_mb"])
    return out


def note_memory() -> dict[str, Any]:
    """One line in the log with the process's memory: kept in the rotating
    file, so a report after a restart still has the hours before it. A
    warning when it is high or jumped since the last line."""
    global _last_rss
    m = process_memory()
    jump = m["rss_mb"] - _last_rss if _last_rss else 0.0
    why = ("high" if m["rss_mb"] >= MEMORY_HIGH_MB else "jump" if jump >= MEMORY_JUMP_MB else None)
    logging.getLogger("sp.memory").log(
        logging.WARNING if why else logging.INFO,
        f"memory {m['rss_mb']:.0f} MB, peak {m['peak_mb']:.0f} MB" + (f" (+{jump:.0f} MB)" if why == "jump" else ""),
        extra={**m, **({"why": why} if why else {})},
    )
    _last_rss = m["rss_mb"]
    return m


def log_dir() -> Path:
    """Where the file goes: SP_LOG_DIR, else .sp beside the repo (the
    launcher's state folder; .merkhet when only the old one exists)."""
    env = os.environ.get("SP_LOG_DIR")
    if env:
        return Path(env).expanduser()
    root = Path(__file__).resolve().parents[2]
    if os.environ.get("SP_SANDBOX") == "1":
        # A test server (the browser tests, a measurement) keeps its own log:
        # it filled the operator's with its starts and its slow requests.
        return root / ".sp" / "sandbox"
    old = root / ".merkhet"
    return old if old.is_dir() and not (root / ".sp").exists() else root / ".sp"


def install(*, file: bool = True) -> None:
    """Wire the root logger once: the ring, the rotating file, warnings to
    stdout. Safe to call again; it does nothing the second time."""
    global LOG_FILE
    root = logging.getLogger()
    if any(getattr(h, "_sp_logbook", False) for h in root.handlers):
        return
    RING._sp_logbook = True  # type: ignore[attr-defined]
    RING.setLevel(logging.INFO)
    root.addHandler(RING)

    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(JsonFormatter())
    out.setLevel(logging.WARNING)
    out._sp_logbook = True  # type: ignore[attr-defined]
    root.addHandler(out)

    if file:
        try:
            d = log_dir()
            d.mkdir(parents=True, exist_ok=True)
            LOG_FILE = d / "sp.log"
            fh = RotatingFileHandler(
                LOG_FILE, maxBytes=FILE_BYTES, backupCount=FILE_KEEP, encoding="utf-8",
            )
            fh.setFormatter(JsonFormatter())
            fh.setLevel(logging.INFO)
            fh._sp_logbook = True  # type: ignore[attr-defined]
            root.addHandler(fh)
        except OSError as exc:
            LOG_FILE = None
            root.warning("log file not writable (%s) — logging to memory and stdout", exc)
    root.setLevel(logging.INFO)
    # uvicorn writes its own access line per request; the server's "req"
    # line says the same with the time it took, so the second one is noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


def _pct(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    return int(s[min(len(s) - 1, int(len(s) * q))])


def stats(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The ring summed up: requests by path shape, rebuilds, errors."""
    rows = RING.snapshot() if records is None else records
    by_path: dict[str, dict[str, Any]] = {}
    rebuild_ms: list[int] = []
    errors = 0
    warnings = 0
    slow = 0
    requests = 0
    first_ts = rows[0]["ts"] if rows else time.time()
    for r in rows:
        lvl = r.get("level")
        if lvl == "ERROR" or lvl == "CRITICAL":
            errors += 1
        elif lvl == "WARNING":
            warnings += 1
        msg = str(r.get("msg") or "")
        if msg == "req" and r.get("path"):
            requests += 1
            ms = int(r.get("ms") or 0)
            if ms >= SLOW_REQUEST_MS:
                slow += 1
            key = f"{r.get('method', 'GET')} {shape(str(r['path']))}"
            b = by_path.setdefault(key, {"path": key, "n": 0, "ms": [], "errors": 0})
            b["n"] += 1
            b["ms"].append(ms)
            if int(r.get("status") or 0) >= 500:
                b["errors"] += 1
        elif msg.startswith("views rebuilt") and r.get("ms") is not None:
            rebuild_ms.append(int(r["ms"]))
    paths = [
        {
            "path": b["path"], "n": b["n"], "p50_ms": _pct(b["ms"], 0.5),
            "max_ms": max(b["ms"]) if b["ms"] else 0, "total_ms": sum(b["ms"]),
            "errors": b["errors"],
        }
        for b in by_path.values()
    ]
    paths.sort(key=lambda p: (-p["total_ms"], p["path"]))
    return {
        "since": first_ts,
        "records_n": len(rows),
        "requests": {"n": requests, "slow_n": slow, "by_path": paths[:40]},
        "rebuilds": {
            "n": len(rebuild_ms), "p50_ms": _pct(rebuild_ms, 0.5),
            "max_ms": max(rebuild_ms) if rebuild_ms else 0,
            "last_ms": rebuild_ms[-1] if rebuild_ms else 0,
        },
        "errors_n": errors,
        "warnings_n": warnings,
    }


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def line(r: dict[str, Any]) -> str:
    """One record as one plain line."""
    parts = [_when(r["ts"]), f"{r['level']:<7}", r.get("logger", "")]
    if r.get("msg") == "req" and r.get("path"):
        parts.append(f"{r.get('method', '')} {r.get('path', '')} → {r.get('status', '')} in {r.get('ms', 0)} ms")
    else:
        parts.append(str(r.get("msg", "")))
        if r.get("ms") is not None:
            parts.append(f"({r['ms']} ms)")
        if r.get("why"):
            parts.append(f"— {r['why']}")
    if r.get("exc"):
        parts.append(f"| {r['exc']}")
    return " ".join(str(p) for p in parts)


def text(summary: dict[str, Any], tail: list[dict[str, Any]]) -> str:
    """The health page as plain text — what the operator copies for an AI."""
    s = summary
    out = [
        "# Slightly Parallel health",
        f"generated: {_when(time.time())}",
        f"server started: {_when(s['started_at'])}  (up {int(s['uptime_s'] // 60)} min)",
        f"data root: {s['data_root']}",
        f"log file: {s.get('log_file') or 'none'} ({s.get('log_file_bytes', 0)} bytes)",
        f"views: age {s['view_age_ms']} ms, load errors {len(s['load_errors'])}",
        f"memory: rss {s.get('rss_mb', 0)} MB, peak {s.get('peak_mb', 0)} MB, threads {s.get('threads', 0)}, open files {s.get('open_files', 0)}",
        "",
        "## Rebuilds",
        f"count {s['rebuilds']['n']}, p50 {s['rebuilds']['p50_ms']} ms, "
        f"max {s['rebuilds']['max_ms']} ms, last {s['rebuilds']['last_ms']} ms",
        "",
        f"## Requests (last {s['records_n']} log lines, since {_when(s['since'])})",
        f"count {s['requests']['n']}, slow (>= {SLOW_REQUEST_MS} ms) {s['requests']['slow_n']}, "
        f"warnings {s['warnings_n']}, errors {s['errors_n']}",
        "",
        f"{'n':>6} {'p50 ms':>7} {'max ms':>7} {'errors':>6}  path",
    ]
    for p in s["requests"]["by_path"]:
        out.append(f"{p['n']:>6} {p['p50_ms']:>7} {p['max_ms']:>7} {p['errors']:>6}  {p['path']}")
    if s["load_errors"]:
        out += ["", "## Load errors"]
        for e in s["load_errors"]:
            out.append(f"- {e.get('file')} [{e.get('stage')}]: {e.get('error')}")
    out += ["", f"## Log tail ({len(tail)} lines)"]
    out += [line(r) for r in tail]
    return "\n".join(out) + "\n"
