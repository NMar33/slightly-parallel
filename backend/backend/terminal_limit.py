"""Read-only measurements and excerpts for Aqua's terminal limit panel."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import psutil

from . import hookshared, sessions, termlib
from .date_utils import format_yymm_dd, parse_yymm_dd
from .db import ViewStore

KINDS = ("claude", "codex", "opencode", "shell")
WEEK_SECONDS = 7 * 24 * 60 * 60
RUNNING_SECONDS = 10 * 60
EXCERPT_COUNT = 3
EXCERPT_CHARS = 800


def kind_of(row: dict[str, Any]) -> str:
    agent = str(row.get("agent_id") or "")
    for prefix, kind in (("cc-", "claude"), ("codex-", "codex"), ("oc-", "opencode")):
        if agent.startswith(prefix):
            return kind
    for field in ("program", "command"):
        tool = re.search(r"\b(claude|codex|opencode)(?:-code)?\b", str(row.get(field) or ""))
        if tool:
            return tool.group(1)
    return "shell"


def _process_parents() -> dict[int, int]:
    # This is the snapshot used by psutil's own Process.children. On
    # Windows a call to Process.ppid would rescan the process table.
    snapshot = getattr(psutil, "_ppid_map", None)
    if snapshot is not None:
        try:
            return snapshot()
        except (psutil.Error, OSError):
            pass  # Use the public per-process reads if a snapshot fails.
    parents = {}
    try:
        for process in psutil.process_iter():
            try:
                parents[process.pid] = process.ppid()
            except (psutil.Error, OSError):
                continue
    except (psutil.Error, OSError):
        return {}
    return parents


def process_tree_memory(roots: set[int]) -> dict[int, int | None]:
    """Use one process index for every terminal's RSS sample."""
    if not roots:
        return {}
    children: dict[int, list[int]] = defaultdict(list)
    for pid, parent in _process_parents().items():
        children[parent].append(pid)
    usage: dict[int, int | None] = {}
    for root in roots:
        pending = [root]
        seen: set[int] = set()
        total = 0
        measured = False
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            pending.extend(children[pid])
            try:
                total += psutil.Process(pid).memory_info().rss
                measured = True
            except (psutil.Error, OSError):
                continue
        usage[root] = total if measured else None
    return usage


def terminal_memory(
    root: Path, rows: list[dict[str, Any]], plain_pids: dict[str, int],
) -> tuple[dict[str, Any], dict[str, int | None]]:
    panes = termlib.tmux_panes(root) if any(row.get("backend") == "tmux" for row in rows) else {}
    kinds = {kind: {"count": 0, "bytes": 0, "measured": 0} for kind in KINDS}
    pids = {}
    for row in rows:
        sid = row["id"]
        pane_pid = str(panes.get(sid, {}).get("pid") or "")
        pids[sid] = int(pane_pid) if pane_pid.isdecimal() else plain_pids.get(sid, 0)
    rss_by_pid = process_tree_memory(set(pids.values()) - {0})
    usage = {sid: rss_by_pid.get(pid) for sid, pid in pids.items()}
    for row in rows:
        rss = usage[row["id"]]
        kind = kinds[kind_of(row)]
        kind["count"] += 1
        if rss is not None:
            kind["bytes"] += rss
            kind["measured"] += 1
    try:
        host = psutil.virtual_memory()
    except (psutil.Error, OSError):
        host = None
    return {"total": host.total if host else None, "available": host.available if host else None,
            "used": sum(kind["bytes"] for kind in kinds.values()), "kinds": kinds}, usage


def reported_inputs(root: Path, ids: set[str]) -> dict[str, float]:
    """Recent operator typing reports also survive a server restart."""
    latest: dict[str, float] = {}
    if ids:
        for line in reversed(hookshared.tail_lines(root / termlib.FOLDER / termlib.TYPING)):
            columns = line.split(",", 2)
            if len(columns) < 3 or columns[1] not in ids or columns[1] in latest:
                continue
            try:
                latest[columns[1]] = datetime.fromisoformat(columns[0]).timestamp()
            except ValueError:
                continue
            if len(latest) == len(ids):
                break
    return latest


def recent_turns(store: ViewStore, agent_ids: set[str], now: float) -> dict[str, tuple[int, float]]:
    """Recent recorded operator turns per agent, with the timestamp of the last."""
    if not agent_ids:
        return {}
    start = datetime.fromtimestamp(now) - timedelta(days=8)
    placeholders = ",".join("?" for _ in agent_ids)
    rows = store.query(
        f"SELECT agent_id, created_date, turns_json FROM sessions WHERE created_date >= ? AND agent_id IN ({placeholders})",  # noqa: S608
        (format_yymm_dd(start), *sorted(agent_ids)),
    )
    recent: dict[str, tuple[int, float]] = {}
    for row in rows:
        agent = str(row["agent_id"])
        count, latest = recent.get(agent, (0, 0.0))
        try:
            day = parse_yymm_dd(row["created_date"])
            turns = json.loads(row["turns_json"] or "[]")
            # The session builder splits at midnight and stores only HH:MM for each turn.
            stamps = [datetime.combine(day, time.fromisoformat(turn["at"])).timestamp()
                      for turn in turns if turn.get("user")]
        except (ValueError, KeyError, TypeError):
            continue
        count += sum(at >= now - WEEK_SECONDS for at in stamps)
        recent[agent] = count, max(latest, max(stamps, default=0.0))
    return recent


def excerpts(root: Path, store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
    sid = row["id"]
    agent = str(termlib.agent_links(root).get(sid, {}).get("agent_id") or row.get("agent_id") or "")
    if agent or kind_of(row) != "shell":
        path = sessions.chat_path(store, agent) if agent else None
        lines = [{"at": turn.at.isoformat(), "text": turn.user_summary[:EXCERPT_CHARS]}
                 for turn in sessions.parse_turns(path) if turn.user_summary] if path else []
        return {"kind": "messages", "first": lines[:EXCERPT_COUNT],
                "last": lines[max(EXCERPT_COUNT, len(lines) - EXCERPT_COUNT):]}
    if row.get("backend") != "tmux":
        return {"kind": "lines", "first": [], "last": []}
    pos = termlib.pane_pos(root, sid)
    end = pos["history"] + pos["cursor"]

    def read(start: int, stop: int) -> list[dict[str, str]]:
        if start > stop:
            return []
        result = termlib.capture(root, sid, start, stop)
        return [{"text": line[:EXCERPT_CHARS]} for line in result["text"].split("\n") if line]

    return {"kind": "lines", "first": read(0, min(end, EXCERPT_COUNT - 1)),
            "last": read(max(EXCERPT_COUNT, end - EXCERPT_COUNT + 1), end)}
