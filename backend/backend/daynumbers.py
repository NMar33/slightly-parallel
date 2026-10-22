"""What a project's day held, counted from the ledgers and git, with no model.

A standup says what happened in words. These are the numbers beside it:
how many chats and agents, how many tasks were made and finished, which
tasks moved, what was committed, how long people and agents were at it.
The standup helper gets them with the day's messages, so it reports
counts it did not make up; the Standups page shows them for every day of
a month, which is also the heatmap.

One day at a time (``day``), or a whole month at once (``month``), which
reads each ledger once. Everything here is a fact of the day: nothing is
written, and the numbers are the same whoever asks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from . import gitwork
from .db import ViewStore
from .date_utils import day_before, day_of, iso_of
from .entities import is_done
from .file_entries import project_repo

# A drag on the board or a stamp the server sets is not a change a person made.
NOISE_FIELDS = frozenset({"position", "stack_id", "stack_head_at", "today_on", "resurfaced_at",
                          "reported_at", "reported_by", "moved_at", "archived_at"})
TASKS_LIST_MAX = 40


def _month_days(month: str) -> list[str]:
    """Every YYMM-DD of a month given as 'YYYY-MM'."""
    first = datetime.fromisoformat(month + "-01")
    out = []
    for n in range(1, 32):
        try:
            d = first.replace(day=n)
        except ValueError:
            break
        out.append(d.strftime("%y%m-%d"))
    return out


def _blank() -> dict[str, Any]:
    return {
        "messages_n": 0, "chats_n": 0, "agents": [], "session_minutes": 0, "agent_minutes": 0,
        "tasks_created_n": 0, "tasks_done_n": 0, "tasks_moved_n": 0, "tasks": [],
        "commits_n": 0, "files_n": 0, "lines_add": 0, "lines_del": 0,
        "tracked_minutes": 0, "decisions_n": 0, "standup_id": "", "map_versions": [],
    }


def month(store: ViewStore, project: str, month_text: str) -> dict[str, dict[str, Any]]:
    """{YYMM-DD: numbers} for every day of the month, empty days included."""
    days = {d: _blank() for d in _month_days(month_text)}
    if not days:
        return {}
    first, last = min(days), max(days)

    # Chats and agents: the session table, one row per work session.
    agents_by_day: dict[str, set[str]] = defaultdict(set)
    for r in store.query(
        "SELECT created_date, agent_id, turns_n, duration_min, agent_min FROM sessions "
        "WHERE project = ? AND created_date BETWEEN ? AND ?", (project, first, last)
    ):
        d = days.get(str(r.get("created_date") or ""))
        if d is None:
            continue
        d["messages_n"] += int(r.get("turns_n") or 0)
        d["session_minutes"] += int(r.get("duration_min") or 0)
        d["agent_minutes"] += int(r.get("agent_min") or 0)
        agents_by_day[str(r["created_date"])].add(str(r.get("agent_id") or ""))
    for day, ids in agents_by_day.items():
        days[day]["agents"] = sorted(ids)
        days[day]["chats_n"] = len(ids)

    # Tasks: made that day, and every field change that day from the event log.
    titles: dict[str, str] = {}
    for r in store.query(
        "SELECT id, title, created_date FROM tasks_mutual WHERE project = ?", (project,)
    ):
        titles[str(r["id"])] = str(r.get("title") or "")
        d = days.get(str(r.get("created_date") or ""))
        if d is not None:
            d["tasks_created_n"] += 1
    moved: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)   # day → task → record
    iso_first, iso_last = iso_of(first), iso_of(last)
    for e in store.query(
        "SELECT task_id, timestamp, actor, field, old_value, new_value FROM task_events_mutual "
        "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
        (iso_first, iso_last + "T99"),
    ):
        tid = str(e.get("task_id") or "")
        if tid not in titles:
            continue
        day = day_of(str(e.get("timestamp") or ""))
        if day not in days:
            continue
        field = str(e.get("field") or "")
        if field in NOISE_FIELDS:
            continue
        rec = moved[day].setdefault(tid, {"id": tid, "title": titles[tid], "changes": []})
        rec["changes"].append({
            "at": str(e.get("timestamp") or "")[11:16], "actor": str(e.get("actor") or ""),
            "field": field, "from": str(e.get("old_value") or ""), "to": str(e.get("new_value") or ""),
        })
        if field == "status" and is_done(e.get("new_value")):
            days[day]["tasks_done_n"] += 1
    for day, by_task in moved.items():
        days[day]["tasks_moved_n"] = len(by_task)
        days[day]["tasks"] = list(by_task.values())[:TASKS_LIST_MAX]

    # Decisions logged that day.
    for r in store.query(
        "SELECT created_date, COUNT(*) AS n FROM decisions_mutual WHERE project = ? "
        "AND created_date BETWEEN ? AND ? GROUP BY created_date", (project, first, last)
    ):
        d = days.get(str(r.get("created_date") or ""))
        if d is not None:
            d["decisions_n"] = int(r.get("n") or 0)

    # Commits: the project's registered repository, by the commit's day.
    repo = project_repo(store, project)
    if repo is not None:
        files_by_day: dict[str, set[str]] = defaultdict(set)
        for c in gitwork.commits(repo):
            day = c.at.strftime("%y%m-%d")
            d = days.get(day)
            if d is None:
                continue
            d["commits_n"] += 1
            d["lines_add"] += c.add
            d["lines_del"] += c.dele
            files_by_day[day].update(p for p, _, _ in c.files)
        for day, paths in files_by_day.items():
            days[day]["files_n"] = len(paths)

    # Time the operator tracked by hand.
    for r in store.query(
        "SELECT created_date, SUM(duration_min) AS m FROM time_entries_mutual WHERE project = ? "
        "AND created_date BETWEEN ? AND ? GROUP BY created_date", (project, first, last)
    ):
        d = days.get(str(r.get("created_date") or ""))
        if d is not None:
            d["tracked_minutes"] = int(r.get("m") or 0)

    # Map versions written that day (repomap): the diary shows "map v2".
    from . import repomap
    for v in repomap.versions(store, project):
        d = days.get(day_of(str(v.get("at") or "")))
        if d is not None:
            d["map_versions"].append(int(v["n"]))

    # The standup that covers each day.
    for r in store.query(
        "SELECT id, created_date, for_date FROM standups_mutual WHERE project = ?", (project,)
    ):
        covers = str(r.get("for_date") or "")
        if not covers:
            covers = day_before(str(r.get("created_date") or ""))
        d = days.get(covers)
        if d is not None and not d["standup_id"]:
            d["standup_id"] = str(r["id"])
    return days


def day(store: ViewStore, project: str, yymm_dd: str) -> dict[str, Any]:
    """One day's numbers, with the changed tasks listed in full."""
    iso = iso_of(yymm_dd)
    if not iso:
        return _blank()
    return month(store, project, iso[:7]).get(yymm_dd) or _blank()
