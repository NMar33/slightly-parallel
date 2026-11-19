"""Incremental, optional Usage telemetry from local CLI transcripts."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import math
import statistics
import multiprocessing
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .file_safety import atomic_write_json
from .hookshared import codex_home
from .usagebackfill import find_transcript

log = logging.getLogger(__name__)
LIMIT = 4 << 20
SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors(path TEXT PRIMARY KEY, identity TEXT, offset INTEGER, skipping INTEGER);
CREATE TABLE IF NOT EXISTS pending(path TEXT, id TEXT, start REAL, family TEXT, job TEXT,
 PRIMARY KEY(path,id));
CREATE TABLE IF NOT EXISTS calls(project TEXT, agent TEXT, id TEXT, start REAL, end REAL,
 family TEXT, quality TEXT, job TEXT, PRIMARY KEY(project,id));
CREATE TABLE IF NOT EXISTS jobs(project TEXT, agent TEXT, job TEXT, launched REAL, fetched REAL,
 waited REAL, first_poll REAL, other_call INTEGER DEFAULT 0, PRIMARY KEY(project,agent,job,launched));
CREATE INDEX IF NOT EXISTS open_jobs ON jobs(project,agent,fetched,job);
"""


def enabled():
    return os.environ.get("SP_TOOL_WAITS", "").lower() in ("1", "true", "yes")


def family(name, args):
    if name in ("wait_agent", "Agent", "Task"):
        return "helper"
    if name in ("sleep", "wait", "write_stdin", "TaskOutput"):
        return "wait"
    cmd = str(args.get("command") or args.get("cmd") or "")
    if name == "exec":
        match = re.search(
            r"""\bcmd\s*:\s*(["'`])([^"'\n`]*)\1""", str(args.get("js", ""))
        )
        cmd = match[2] if match else ""
    families = set()
    for part in re.split(r"&&|\|\||[;|\n]", cmd.partition("<<")[0]):
        part = re.sub(
            r"^\s*(?:(?:env|[\w]+=[^\s]+|timeout\s+[\d.]+[smh]?)\s+)*", "", part
        )
        for label, pattern in (
            (
                "tests",
                r"(?:[\w./-]+/)?(?:pytest|vitest|jest|playwright)\b|(?:npm|cargo|go|pnpm|yarn) (?:run )?test\b|npx (?:vitest|jest|playwright)\b|(?:[\w./-]+/)?python[\d.]* (?:-m pytest|scripts/verify\.py)\b",
            ),
            ("build", r"(?:npm run|pnpm|cargo|go) build\b|(?:npx )?tsc\b"),
            ("install", r"(?:npm|pnpm|pip|uv pip) (?:install|ci)\b"),
            ("git", r"git\b"),
        ):
            if re.match(pattern, part):
                families.add(label)
    return (
        next(iter(families)) if len(families) == 1 else "mixed" if families else "other"
    )


def events(record):
    message = record.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), list):
        for item in message["content"]:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                yield True, item.get("id"), item.get("name"), item.get("input")
            elif item.get("type") == "tool_result":
                yield False, item.get("tool_use_id"), "", item.get("content")
    p = record.get("payload")
    if record.get("type") != "response_item" or not isinstance(p, dict):
        return
    kind = p.get("type")
    if kind == "function_call":
        yield (
            True,
            p.get("call_id"),
            p.get("name"),
            json.loads(p.get("arguments", "{}")),
        )
    elif kind == "custom_tool_call":
        yield True, p.get("call_id"), p.get("name"), {"js": p.get("input", "")}
    elif kind in ("function_call_output", "custom_tool_call_output"):
        yield False, p.get("call_id"), "", p.get("output")


def consume(db, path, project, agent, record):
    when = datetime.fromisoformat(record["timestamp"]).timestamp()
    for begin, ident, name, value in events(record):
        if not isinstance(ident, str) or not ident:
            continue
        if begin:
            if not isinstance(name, str):
                continue
            if not isinstance(value, dict) or name in (
                "AskUserQuestion",
                "request_user_input",
                "request_user_input_async",
                "ExitPlanMode",
            ):
                continue
            job = ""
            if name in ("wait", "write_stdin", "TaskOutput"):
                job = str(
                    value.get("cell_id")
                    or value.get("session_id")
                    or value.get("task_id")
                    or ""
                )
            elif name == "exec":
                m = re.search(
                    r"write_stdin\s*\(\s*\{\s*session_id\s*:\s*(\d+)",
                    str(value.get("js", "")),
                )
                job = m[1] if m else ""
            if job:
                db.execute(
                    "UPDATE jobs SET first_poll=COALESCE(first_poll,?) WHERE project=? AND agent=? AND job=? AND fetched IS NULL AND launched<=?",
                    (when, project, agent, job, when),
                )
            elif name != "sleep":
                db.execute(
                    "UPDATE jobs SET other_call=1 WHERE project=? AND agent=? AND first_poll IS NULL AND fetched IS NULL AND launched<?",
                    (project, agent, when),
                )
            db.execute(
                "INSERT OR IGNORE INTO pending VALUES(?,?,?,?,?)",
                (path, ident, when, family(name, value), job),
            )
            continue
        row = db.execute(
            "SELECT start,family,job FROM pending WHERE path=? AND id=?", (path, ident)
        ).fetchone()
        if not row:
            continue
        db.execute("DELETE FROM pending WHERE path=? AND id=?", (path, ident))
        start, label, job = row
        if isinstance(value, list):
            value = next(
                (v.get("text") for v in value if isinstance(v, dict) and v.get("text")),
                "",
            )
        out = value[:2048] if isinstance(value, str) else ""
        if when < start or re.search(
            r"auto mode classifier gave no verdict|user (?:rejected|denied)|permission was denied",
            out,
            re.I,
        ):
            continue
        handle = re.search(
            r"(?:Script running with cell ID|Process running with session ID|running in the background with ID)\s*[:=]?\s*([\w-]+)",
            out,
            re.I,
        )
        if handle and not job:
            db.execute(
                "INSERT OR IGNORE INTO jobs(project,agent,job,launched) VALUES(?,?,?,?)",
                (project, agent, handle[1], when),
            )
        duration = when - start
        clock = re.search(r"(?m)^Wall time[: ]+([\d.]+) seconds", out)
        disputed = bool(
            clock and float(clock[1]) > duration + 2 and float(clock[1]) > 30
        )
        unfinished = re.search(
            r"<(?:retrieval_status|status)>(?:timeout|not_ready|running|pending)<",
            out,
            re.I,
        )
        if job and not handle and not unfinished:
            db.execute(
                "UPDATE jobs SET fetched=?,waited=? WHERE project=? AND agent=? AND job=? AND fetched IS NULL AND launched<=?",
                (when, None if disputed else duration, project, agent, job, start),
            )
        if duration > 30 or disputed:
            db.execute(
                "INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?,?)",
                (
                    project,
                    agent,
                    ident,
                    when - float(clock[1]) if disputed else start,
                    when,
                    label,
                    "clock" if disputed else "paired",
                    job,
                ),
            )


def advance(db, source, project, agent):
    """Commit parsed rows and cursor together. Leave a partial last line for next time."""
    path = str(source)
    with source.open("rb") as stream, db:
        st = os.fstat(stream.fileno())
        identity = f"{st.st_dev}:{st.st_ino}"
        old = db.execute(
            "SELECT identity,offset,skipping FROM cursors WHERE path=?", (path,)
        ).fetchone()
        offset = old[1] if old and old[0] == identity and old[1] <= st.st_size else 0
        if old and not offset and old[1]:
            db.execute("DELETE FROM pending WHERE path=?", (path,))
        skipping = bool(old and offset and old[2])
        stream.seek(offset)
        position = offset
        while stream.tell() - offset < LIMIT:
            line = stream.readline(LIMIT)
            if not line:
                break
            if skipping or len(line) == LIMIT and not line.endswith(b"\n"):
                skipping = not line.endswith(b"\n")
                position = stream.tell()
                continue
            if not line.endswith(b"\n"):
                break
            try:
                record = json.loads(line)
                if isinstance(record, dict) and "timestamp" in record:
                    consume(db, path, project, agent, record)
            except (ValueError, TypeError, OverflowError, OSError):
                pass
            position = stream.tell()
        if position != offset or old is None or old[0] != identity or old[1] != offset:
            db.execute(
                "INSERT OR REPLACE INTO cursors VALUES(?,?,?,?)",
                (path, identity, position, skipping),
            )
        return max(0, st.st_size - position)


def snapshot(db, now):
    """Sweep all call boundaries per agent; assign overlap to one family."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    first = midnight - timedelta(days=29)
    groups = defaultdict(list)
    disputed = Counter()
    for project, agent, start, end, label, quality in db.execute(
        "SELECT project,agent,start,end,family,quality FROM calls WHERE end>=?",
        (first.timestamp(),),
    ):
        if quality == "clock":
            disputed[project, datetime.fromtimestamp(end).date().isoformat()] += 1
            continue
        groups[project, agent].extend(
            [(max(start, first.timestamp()), label, 1), (end, label, -1)]
        )
    daily = Counter()
    for (project, agent), points in groups.items():
        points.extend(
            ((first + timedelta(days=i)).timestamp(), "", 0) for i in range(31)
        )
        active = Counter()
        prev = first.timestamp()
        for at, label, change in sorted(points):
            labels = [key for key, n in active.items() if n]
            if at > prev and labels:
                day = datetime.fromtimestamp(prev).date().isoformat()
                daily[
                    project, day, agent, labels[0] if len(labels) == 1 else "mixed"
                ] += at - prev
            active[label] += change
            prev = at
    jobs = list(
        db.execute(
            "SELECT project,launched,fetched,waited,first_poll,other_call FROM jobs WHERE launched>=?",
            (first.timestamp(),),
        )
    )
    return {
        "updated": now.isoformat(timespec="seconds"),
        "daily": [[*k, round(v, 3)] for k, v in daily.items()],
        "clock": [[*k, v] for k, v in disputed.items()],
        "jobs": [
            [
                p,
                datetime.fromtimestamp(s).date().isoformat(),
                w,
                f is not None,
                poll is not None and not other,
            ]
            for p, s, f, w, poll, other in jobs
        ],
    }


def summary(root, project, days, now):
    if not enabled():
        return None
    try:
        data = json.loads((root / ".usage/tool-waits.json").read_bytes())
    except (OSError, ValueError):
        return {"ready": False}
    begin = (now.date() - timedelta(days=days - 1)).isoformat()

    def included(p, d):
        return (not project or p == project) and begin <= d <= now.date().isoformat()

    families = Counter()
    for p, d, _agent, label, seconds in data["daily"]:
        if included(p, d):
            families[label] += seconds
    jobs = [
        (w, collected, immediate)
        for p, d, w, collected, immediate in data["jobs"]
        if included(p, d)
    ]
    waits = sorted(w for w, _, _ in jobs if w is not None)
    daily = Counter()
    agents = Counter()
    for p, d, agent, _, seconds in data["daily"]:
        if included(p, d):
            daily[d] += seconds
            agents[agent] += seconds
    return {
        "ready": True,
        "catching_up": bool(data.get("unread_bytes")),
        "missing": data.get("missing", 0),
        "updated": data["updated"],
        "seconds": sum(families.values()),
        "families": families,
        "clock": sum(n for p, d, n in data["clock"] if included(p, d)),
        "jobs": len(jobs),
        "collected": sum(collected for _, collected, _ in jobs),
        "blocked": sum(w > 30 for w in waits),
        "immediate": sum(immediate for _, _, immediate in jobs),
        "daily": daily,
        "agents": dict(agents.most_common(10)),
        "median": statistics.median(waits) if waits else None,
        "p90": waits[math.ceil(0.9 * len(waits)) - 1] if waits else None,
    }


class Collector:
    """Own the indexer's process so parsing never holds the API interpreter's GIL."""

    def __init__(self, root):
        context = multiprocessing.get_context("spawn")
        self.halt = context.Event()
        self.process = context.Process(
            target=_collect, args=(root, self.halt), name="sp-tool-waits", daemon=True
        )

    def start(self):
        self.process.start()

    def stop(self):
        self.halt.set()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)


def _collect(root, halt):
    if hasattr(os, "nice"):
        try:
            os.nice(10)
        except OSError:
            pass
    paths = {}
    while not halt.is_set():
        try:
            folder = root / ".usage"
            folder.mkdir(exist_ok=True)
            db = sqlite3.connect(folder / "tool-waits.sqlite")
            try:
                db.executescript(SCHEMA)
                unread_bytes = 0
                missing = 0
                cutoff = (datetime.now() - timedelta(days=31)).timestamp()
                for meta in root.glob("projects/*/chats/*/meta.json"):
                    if halt.is_set():
                        return
                    try:
                        data = json.loads(meta.read_bytes())
                        if not isinstance(data, dict):
                            continue
                        tool = data.get("tool")
                        ref = data.get("session_ref", "")
                        if tool not in ("claude-code", "codex") or not re.fullmatch(
                            r"[\w-]+", ref
                        ):
                            continue
                        path = paths.get((tool, ref))
                        if path is None or not path.exists():
                            path = find_transcript(
                                data,
                                tool,
                                Path.home() / ".claude/projects",
                                codex_home(),
                            )
                            if path:
                                paths[tool, ref] = path
                        if not path:
                            missing += 1
                            continue
                        if path:
                            sources = [path]
                            if tool == "claude-code":
                                sources.extend(
                                    (path.with_suffix("") / "subagents").glob(
                                        "**/*.jsonl"
                                    )
                                )
                            for source in sources:
                                if halt.is_set():
                                    return
                                if source.stat().st_mtime < cutoff:
                                    continue
                                unread_bytes += advance(
                                    db,
                                    source,
                                    meta.parents[2].name,
                                    meta.parent.name if source == path else source.stem,
                                )
                    except (ValueError, OSError, TypeError):
                        continue
                with db:
                    for table, column in (
                        ("pending", "start"),
                        ("calls", "end"),
                        ("jobs", "launched"),
                    ):
                        db.execute(f"DELETE FROM {table} WHERE {column}<?", (cutoff,))
                report = snapshot(db, datetime.now())
                report.update(unread_bytes=unread_bytes, missing=missing)
                atomic_write_json(folder / "tool-waits.json", report)
            finally:
                db.close()
        except Exception:
            log.exception("Tool wait collection paused until next pass")
        halt.wait(60)
