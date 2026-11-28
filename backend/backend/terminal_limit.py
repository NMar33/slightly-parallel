"""Read-only measurements and excerpts for Aqua's terminal limit panel."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psutil

from . import hookshared, sessions, termlib
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


def memory_of(pid: int) -> int | None:
    if not pid:
        return None
    try:
        process = psutil.Process(pid)
        tree = [process, *process.children(recursive=True)]
    except (psutil.Error, OSError):
        return None
    total = 0
    measured = False
    for child in tree:
        try:
            total += child.memory_info().rss
            measured = True
        except (psutil.Error, OSError):
            continue
    return total if measured else None


def terminal_memory(
    root: Path, rows: list[dict[str, Any]], plain_pids: dict[str, int],
) -> tuple[dict[str, Any], dict[str, int | None]]:
    panes = termlib.tmux_panes(root) if any(row.get("backend") == "tmux" for row in rows) else {}
    kinds = {kind: {"count": 0, "bytes": 0, "measured": 0} for kind in KINDS}
    usage = {}
    for row in rows:
        sid = row["id"]
        pane_pid = str(panes.get(sid, {}).get("pid") or "")
        pid = int(pane_pid) if pane_pid.isdecimal() else plain_pids.get(sid, 0)
        rss = memory_of(pid)
        usage[sid] = rss
        kind = kinds[kind_of(row)]
        kind["count"] += 1
        if rss is not None:
            kind["bytes"] += rss
            kind["measured"] += 1
    host = psutil.virtual_memory()
    return {"total": host.total, "available": host.available,
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
        f"SELECT agent_id, turns_json FROM sessions WHERE created_date >= ? AND agent_id IN ({placeholders})",  # noqa: S608
        (start.strftime("%y%m-%d"), *sorted(agent_ids)),
    )
    recent: dict[str, tuple[int, float]] = {}
    for row in rows:
        agent = str(row["agent_id"])
        count, latest = recent.get(agent, (0, 0.0))
        try:
            turns = json.loads(row["turns_json"] or "[]")
            stamps = [datetime.fromisoformat(turn["at"]).timestamp() for turn in turns if turn.get("user")]
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
