"""One file to send when something is wrong: what the machine is, how the
server has been (memory, slow requests, errors, restarts), what the monitor
and the capture hooks saw, and how big the data is.

Built two ways, with the same sections: ``GET /api/diagnostics/report`` (the
Download report button on Monitor › Server) adds the running server's own
summary; ``python sp.py report`` builds it from the files alone, so it works
when the server does not start. Standard library only: sp.py loads this file
by path, before the backend's packages exist.

What it leaves out: the text of chats, tasks and entries, the settings
whose names say secret, and the values of ``.env``. Log lines are copied
with their query strings cut and each line short; a log or an exception can
still quote something, so read the file before sending it. Paths under the
home folder are written from ``~``. Each section and the whole file have a
ceiling, so the file stays a few hundred KB at most.
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DAY = 86400
SECRETISH = ("token", "secret", "password", "key")


LINE_MAX = 300
SECTION_MAX = 40_000
REPORT_MAX = 400_000
_QUERY = __import__("re").compile(r"\?[^\s\"']*")


def _home(text: str) -> str:
    home = str(Path.home())
    return text.replace(home, "~") if home and home != "/" else text


def _clean(text: str, limit: int = LINE_MAX) -> str:
    """A line for the report: home as ~, query strings cut (a search's words,
    a token), at most ``limit`` characters."""
    text = _QUERY.sub("?…", _home(text))
    return text if len(text) <= limit else text[:limit] + " …"


def _cap(lines: list[str], limit: int = SECTION_MAX) -> list[str]:
    out, size = [], 0
    for ln in lines:
        size += len(ln) + 1
        if size > limit:
            out.append(f"… cut: the section is longer than {limit // 1000} KB")
            break
        out.append(ln)
    return out


def _mb(n: float) -> str:
    return f"{n / 1e6:,.0f} MB" if n >= 1e6 else f"{n / 1e3:,.0f} KB"


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _tail(path: Path, lines: int, max_bytes: int = 2_000_000) -> list[str]:
    """The last lines of a file, reading at most its last ``max_bytes``."""
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, 2)
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = data.splitlines()
    if size > max_bytes and out:
        out = out[1:]       # the first one is cut
    return out[-lines:]


def _exc_line(exc: str) -> str:
    """A traceback's own message: its last line that says something (not a
    caret line under the code)."""
    lines = [x.strip() for x in exc.splitlines() if x.strip() and set(x.strip()) - set("^~ ")]
    return _clean(lines[-1]) if lines else ""


def _json_lines(path: Path, max_bytes: int = 5_000_000) -> Iterable[dict[str, Any]]:
    for line in _tail(path, 10**7, max_bytes):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            yield rec


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def machine(app_root: Path) -> list[str]:
    version = ""
    try:
        version = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=app_root,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    mem = ""
    try:
        import psutil  # in the backend's environment; sp.py's own Python may lack it
        vm = psutil.virtual_memory()
        mem = f", memory {_mb(vm.total)} ({vm.percent:.0f}% used now)"
    except Exception:  # noqa: BLE001
        pass
    return [
        f"version: {version or 'unknown'}",
        f"system: {platform.system()} {platform.release()} ({platform.machine()}), {os.cpu_count()} cpus{mem}",
        f"python: {platform.python_version()} ({_home(sys.executable)})",
        f"app folder: {_home(str(app_root))}",
    ]


def memory_history(data_root: Path, now: float) -> list[str]:
    """The server's own memory, hour by hour for a day, from the monitor."""
    db = Path(data_root) / "monitor" / "monitor.sqlite"
    if not db.is_file():
        return ["(no monitor data: the monitor is off or has not run)"]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            # The bucket's peak where the record keeps one (sysmon.PEAKS), else the average.
            have = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
            top = "MAX(COALESCE(self_rss_max, self_rss))" if "self_rss_max" in have else "MAX(self_rss)"
            rows = con.execute(
                f"SELECT CAST(ts / 3600 AS INTEGER) AS h, MIN(self_rss), {top}, MAX(cpu), MAX(mem_pct) "
                "FROM samples WHERE ts >= ? AND self_rss IS NOT NULL GROUP BY h ORDER BY h", (now - DAY,)).fetchall()
            events = con.execute(
                "SELECT started, ended, severity, kind, title FROM events WHERE started >= ? AND kind != 'gap' "
                "ORDER BY started DESC LIMIT 25", (now - 7 * DAY,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return [f"(monitor data not readable: {exc})"]
    out = ["hour              server memory (min–max)   machine cpu max   machine memory max"]
    for h, lo, hi, cpu, mem in rows:
        out.append(f"{_when(h * 3600)}  {_mb(lo or 0):>9} – {_mb(hi or 0):<9}   {cpu or 0:>6.0f}%          {mem or 0:>5.0f}%")
    if not rows:
        out.append("(no samples in the last day)")
    out.append("")
    out.append(f"monitor events, last 7 days ({len(events)} shown):")
    for started, ended, severity, kind, title in events:
        out.append(f"  {_when(started)}  {severity:<8} {kind:<10} {_clean(str(title))}" + ("" if ended else "  (open)"))
    return out


def server_log(log_file: Path, now: float) -> list[str]:
    """From the rotating log: the memory lines, restarts, slow requests and
    every warning and error of the last two days."""
    files = sorted(Path(log_file).parent.glob(Path(log_file).name + "*"), key=lambda p: p.stat().st_mtime) \
        if Path(log_file).parent.is_dir() else []
    memory: deque[str] = deque(maxlen=48)
    trouble: deque[str] = deque(maxlen=80)
    slow: Counter[str] = Counter()
    starts: list[str] = []
    for f in files:
        for rec in _json_lines(f):
            ts = float(rec.get("ts") or 0)
            if ts < now - 2 * DAY:
                continue
            line = f"{_when(ts)} {rec.get('level', '')} {rec.get('logger', '')} {_clean(str(rec.get('msg', '')))}"
            if rec.get("msg") == "req":
                if rec.get("why") == "slow":
                    slow[f"{rec.get('method')} {rec.get('path')}"] += 1
                if rec.get("level") in ("ERROR", "CRITICAL") or int(rec.get("status") or 0) >= 500:
                    trouble.append(_clean(f"{_when(ts)} {rec.get('method')} {rec.get('path')} → {rec.get('status')} in {rec.get('ms')} ms"))
                continue
            if rec.get("logger") == "sp.memory":
                memory.append(line)
            if str(rec.get("msg")).startswith("watching "):        # once per start (watcher.py)
                starts.append(_when(ts))
            if rec.get("level") in ("WARNING", "ERROR", "CRITICAL") and rec.get("logger") != "sp.memory":
                trouble.append(line + (f"\n      {_exc_line(str(rec['exc']))}" if rec.get("exc") else ""))
    out = [f"log files: {', '.join(f'{p.name} ({_mb(p.stat().st_size)})' for p in files) or 'none'}",
           f"starts in the last 2 days: {len(starts)}" + (f" ({', '.join(starts[-8:])})" if starts else "")]
    out += ["", "memory, every 5 minutes (last 48):"] + ([f"  {m}" for m in memory] or ["  (none yet)"])
    out += ["", "slow requests by path (last 2 days):"]
    out += [f"  {n:>4}  {p}" for p, n in slow.most_common(15)] or ["  (none)"]
    out += ["", "warnings and errors (last 80):"] + ([f"  {t}" for t in trouble] or ["  (none)"])
    return out


def supervisor_log(path: Path) -> list[str]:
    """The supervisor's output: a crash at start shows here and nowhere else."""
    return [_clean(x) for x in _tail(path, 60, 200_000)] or ["(empty)"]


def capture_errors(data_root: Path, now: float) -> list[str]:
    path = Path(data_root) / ".capture" / "errors.jsonl"
    recent = [r for r in _json_lines(path, 300_000) if str(r.get("at") or "") >= _when(now - 7 * DAY)]
    if not recent:
        return ["none in the last 7 days"]
    by = Counter(f"{r.get('tool', '?')} · {r.get('project', '?')}" for r in recent)
    out = [f"{len(recent)} in the last 7 days: " + ", ".join(f"{k} ({n})" for k, n in by.most_common())]
    out += [f"  {r.get('at')}  {r.get('tool')}  {_clean(str(r.get('error', '')), 200)}" for r in recent[-10:]]
    return out


def data_sizes(data_root: Path) -> list[str]:
    root = Path(data_root)
    total, files, biggest = 0, 0, []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("backups", "tour_shots")]
        for n in names:
            try:
                size = os.stat(os.path.join(dirpath, n)).st_size
            except OSError:
                continue
            total += size
            files += 1
            biggest.append((size, os.path.relpath(os.path.join(dirpath, n), root)))
    biggest.sort(reverse=True)
    projects = len([p for p in (root / "projects").iterdir() if p.is_dir()]) if (root / "projects").is_dir() else 0
    chats = len(list(root.glob("projects/*/chats/*/chat.md")))
    out = [f"data folder: {_home(str(root))}",
           f"{files} files, {_mb(total)} (without backups), {projects} projects, {chats} chats",
           "largest files:"] + [f"  {_mb(s):>9}  {p}" for s, p in biggest[:8]]
    return out


def transcripts() -> list[str]:
    """The tools' own logs the server reads: their size is what memory at
    start depended on (docs/performance.md)."""
    out = []
    claude = Path.home() / ".claude" / "projects"
    codex = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    for name, folder, pattern in (("Claude Code", claude, "*/*.jsonl"), ("Claude Code helpers", claude, "*/*/subagents/*.jsonl"),
                                  ("Codex", codex, "**/*.jsonl")):
        if not folder.is_dir():
            continue
        sizes = []
        for p in folder.glob(pattern):
            try:
                sizes.append(p.stat().st_size)
            except OSError:
                pass
        if sizes:
            out.append(f"{name}: {len(sizes)} files, {_mb(sum(sizes))}, largest {_mb(max(sizes))}")
    return out or ["none found"]


def settings_section(data_root: Path) -> list[str]:
    try:
        values = json.loads((Path(data_root) / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["(defaults: no settings.json)"]
    flat: list[str] = []

    def walk(prefix: str, v: Any) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(f"{prefix}.{k}" if prefix else str(k), x)
        elif not any(s in prefix.lower() for s in SECRETISH):
            flat.append(f"{prefix} = {json.dumps(v, ensure_ascii=False)[:120]}")
    walk("", values)
    return flat or ["(empty)"]


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def report(*, app_root: Path, data_root: Path, log_file: Path, supervisor_file: Path,
           live: str | None = None, server: dict[str, Any] | None = None, now: float | None = None) -> str:
    """The whole report as Markdown. ``live``: the running server's summary
    (its health text); ``server``: its process numbers. Without them the
    report says the server was not reached."""
    now = now or time.time()
    sections: list[tuple[str, list[str]]] = [
        ("Machine", machine(app_root)),
        ("Server now", (
            [f"memory {server.get('rss_mb')} MB, peak {server.get('peak_mb')} MB since its start, "
             f"threads {server.get('threads')}, open files {server.get('open_files')}"] if server else
            ["not reached: the report was built from the files alone (python sp.py report)"])),
        ("Memory and machine, last 24 hours", memory_history(data_root, now)),
        ("Server log", server_log(log_file, now)),
        ("Capture hook errors", capture_errors(data_root, now)),
        ("Data", data_sizes(data_root)),
        ("Tool transcripts", transcripts()),
        ("Settings", settings_section(data_root)),
        ("Supervisor output (last 60 lines)", supervisor_log(supervisor_file)),
    ]
    parts = [f"# Slightly Parallel report\n\ngenerated {_when(now)}. "
             "No chat text, no .env values, no settings named secret; query strings cut, paths "
             "under the home folder start with ~. Log lines can still quote something: read it before sending.\n"]
    for title, lines in sections:
        parts.append(f"## {title}\n\n```\n" + "\n".join(_cap(lines)) + "\n```\n")
    if live:
        parts.append("## The running server's summary\n\n```\n" + "\n".join(_cap([_clean(x, 400) for x in live.splitlines()])) + "\n```\n")
    text = "\n".join(parts)
    return text if len(text) <= REPORT_MAX else text[:REPORT_MAX] + "\n\n… cut: the report is longer than its ceiling\n"
