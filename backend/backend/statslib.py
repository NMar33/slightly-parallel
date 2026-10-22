"""Task statistics — what each task took, from the chats and the repository.

One row per task on the board: its messages, the
chats and the active minutes they span, who worked it, the commits, files
and lines the repository saw, when it was created, first worked and done,
and how it was closed.

The messages of a task are its stretch of the chat. A task closed with
``#done`` has an exact one (donelib.py); for any other the stretch is
estimated the way taskwork.py always has — from where the task is named to
where the next task is — and the row says which (``stretch``: done ·
estimated · none).

Active minutes are the spread of each chat's turns inside the stretch, each
chat at least a minute: time in the conversation, not time on the clock.

Computed once per rebuild of the store (``view_mtime``): a board of 180
tasks costs about three seconds of git the first time, then nothing.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any

from . import donelib, taskwork
from .db import ViewStore
from .entities import is_done

ACTIVITY_DAYS = 91
_cache: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
# A chat's turns and a task's git work outlive a rebuild: a new message
# changes one chat, and only the tasks worked in it are counted again.
_turns: dict[tuple[str, int], list[dict[str, Any]]] = {}
_work: dict[tuple, dict[str, Any]] = {}
_lock = threading.Lock()


def _iso(day: str, hm: str) -> str:
    """A task's YYMM-DD and HH:MM as an ISO minute."""
    if len(day) == 7 and day[4] == "-":
        return f"20{day[:2]}-{day[2:4]}-{day[5:7]}T{(hm or '00:00')[:5]}"
    return ""


def _minutes(a: str, b: str) -> float | None:
    try:
        return (datetime.fromisoformat(b[:16]) - datetime.fromisoformat(a[:16])).total_seconds() / 60
    except ValueError:
        return None


def task_rows(store: ViewStore) -> list[dict[str, Any]]:
    key = str(store.data_root)
    # The day is part of the key: ages, days in a status and "stuck" move
    # with the calendar even when no file does.
    view = getattr(store, "view_mtime", None)
    stamp = (view, datetime.now().date().isoformat()) if view is not None else None
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp and stamp is not None:
            return hit[1]
        rows = _compute(store)
        _cache[key] = (stamp, rows)
        return rows


def _compute(store: ViewStore) -> list[dict[str, Any]]:
    tasks = store.query(
        "SELECT id, title, project, status, created_date, created_time, archived_at, tags, sprint_id, "
        "priority, assignee, impact, effort, agent_id, lane, due_date, remember FROM tasks_mutual")
    named = {str(r["task_id"]) for r in store.query("SELECT DISTINCT task_id FROM task_mentions WHERE task_id LIKE 'tk_%'")}
    sessions: dict[str, dict[str, Any]] = {}
    for s in store.query("SELECT id, agent_id, created_date, chat_end_line, turns_json FROM sessions"):
        key = (str(s["id"]), int(s.get("chat_end_line") or 0))
        turns = _turns.get(key)
        if turns is None:
            try:
                turns = json.loads(s.get("turns_json") or "[]")
            except ValueError:
                turns = []
            _turns[key] = turns
        sessions[str(s["id"])] = {"agent": str(s["agent_id"] or ""), "day": str(s["created_date"] or ""),
                                  "turns": turns, "end": key[1]}
    # Every mention once, by session: a task's span needs the other tasks
    # named in its chats (what closes it).
    by_session: dict[str, list[dict[str, Any]]] = {}
    task_sessions: dict[str, set[str]] = {}
    for m in store.query("SELECT session_id, turn, task_id FROM task_mentions"):
        by_session.setdefault(str(m["session_id"]), []).append(m)
        task_sessions.setdefault(str(m["task_id"]), set()).add(str(m["session_id"]))
    minute = int(time.time() // 60)
    today_day = datetime.now().strftime("%y%m-%d")
    fresh_work: dict[tuple, dict[str, Any]] = {}
    events: dict[str, list[dict[str, Any]]] = {}
    for e in store.query(
            "SELECT task_id, timestamp, actor, field, old_value, new_value FROM task_events_mutual "
            "ORDER BY timestamp"):
        events.setdefault(str(e["task_id"]), []).append(e)
    # Chats a task was named in, and the days it was, for the activity strip.
    named_in: dict[str, set[str]] = {}
    days: dict[str, list[str]] = {}
    for m in store.query("SELECT task_id, session_id, at_ts FROM task_mentions WHERE task_id LIKE 'tk_%'"):
        named_in.setdefault(str(m["task_id"]), set()).add(str(m["session_id"]))
        days.setdefault(str(m["task_id"]), []).append(str(m["at_ts"] or "")[:10])
    today = datetime.now().date()
    closed_in_chat = {r["task_id"] for r in donelib.rows(store) if r.get("result") == "moved"}
    exact = {r["task_id"] for r in donelib.rows(store) if r.get("result") in donelib.RESOLVED}

    out: list[dict[str, Any]] = []
    for t in tasks:
        tid = str(t["id"])
        done = is_done(t.get("status"))
        evs = events.get(tid, [])
        done_at = next((str(e["timestamp"]) for e in reversed(evs)
                        if e["field"] == "status" and is_done(e["new_value"])), "") if done else ""
        created = _iso(str(t.get("created_date") or ""), str(t.get("created_time") or ""))
        if done and not done_at:
            # Done with no move in its history (imported, or older than the history).
            done_at = str(t.get("archived_at") or "") or created
        reopened = sum(1 for e in evs if e["field"] == "status" and is_done(e["old_value"]) and not is_done(e["new_value"]))
        reports = sum(1 for e in evs if e["field"] == "agent_report")
        moves = [e for e in evs if e["field"] == "status"]
        edits = sum(1 for e in evs if e["field"] not in ("status", "agent_report", "done_in_chat")
                    and not str(e["field"]).startswith("agent_"))
        # The last 91 days (13 weeks), oldest first: board events and chat
        # mentions per day — the task table draws them as a week grid.
        strip = [0] * ACTIVITY_DAYS
        for d in [str(e["timestamp"])[:10] for e in evs] + days.get(tid, []):
            try:
                back = (today - datetime.fromisoformat(d).date()).days
            except ValueError:
                continue
            if 0 <= back < ACTIVITY_DAYS:
                strip[ACTIVITY_DAYS - 1 - back] += 1

        mentions = [m for sid in sorted(task_sessions.get(tid, ())) for m in by_session.get(sid, [])] \
            if tid in named or tid in exact else []
        spans = taskwork._with_done(store, tid, taskwork._spans(mentions, tid))
        messages = minutes = 0
        chats = 0
        agents: set[str] = set()
        first = ""
        for sid, ranges in spans.items():
            s = sessions.get(sid)
            if not s:
                continue
            inside = [x for x in s["turns"] if any(lo <= int(x.get("n") or 0) <= hi for lo, hi in ranges)]
            if not inside:
                continue
            chats += 1
            messages += len(inside)
            agents.add(s["agent"])
            ats = [str(x.get("at") or "") for x in inside if len(str(x.get("at") or "")) >= 5]
            mins = [int(a[:2]) * 60 + int(a[3:5]) for a in ats if a[:2].isdigit()]
            if mins:
                minutes += max(1, max(mins) - min(mins) + 1)
            start = _iso(s["day"], min(ats)) if ats else ""
            if start and (not first or start < first):
                first = start
        if spans:
            # Git's account is the slow part: kept while the task's chats are
            # unchanged; a chat of today is asked again once a minute.
            wkey = (tid, tuple(sorted((sid, tuple(r), sessions.get(sid, {}).get("end", 0)) for sid, r in spans.items())),
                    minute if any(sessions.get(sid, {}).get("day") == today_day for sid in spans) else 0)
            work = _work.get(wkey) or taskwork.task_work(store, tid)
            fresh_work[wkey] = work
        else:
            work = {"files": [], "commits": 0, "add": 0, "del": 0}

        lead = _minutes(created, done_at) if created and done_at else None
        since = str(moves[-1]["timestamp"]) if moves else created
        now_iso = datetime.now().isoformat(timespec="minutes")
        age = _minutes(created, now_iso) if created else None
        in_status = _minutes(since, now_iso) if since else None
        worked = _minutes(first, done_at) if first and done_at else None
        out.append({
            "id": tid, "title": t.get("title") or "", "project": t.get("project") or "",
            "status": t.get("status") or "", "done": done, "sprint_id": t.get("sprint_id") or "",
            "created": created, "first": first, "done_at": done_at,
            "lead_hours": round(lead / 60, 2) if lead is not None and lead >= 0 else None,
            "work_hours": round(worked / 60, 2) if worked is not None and worked >= 0 else None,
            "messages": messages, "chats": chats, "minutes": minutes, "agents": sorted(agents),
            "commits": work["commits"], "files": len(work["files"]), "add": work["add"], "del": work["del"],
            # "#done" only when the last move to done was that #done: a task
            # reopened and closed again on the board was closed on the board.
            "closed": ("#done" if tid in closed_in_chat and any(
                e["field"] == "done_in_chat" and str(e["timestamp"])[:19] == done_at[:19] for e in evs)
                else "board") if done else "",
            "stretch": "done" if tid in exact else "estimated" if spans else "none",
            "reopened": reopened, "reports": reports,
            "priority": t.get("priority") or "", "assignee": t.get("assignee") or "",
            "impact": t.get("impact") or "", "effort": t.get("effort") or "",
            "tags": [x.strip() for x in str(t.get("tags") or "").split(",") if x.strip()],
            "lane": t.get("lane") or "", "due": t.get("due_date") or "",
            "starred": str(t.get("remember") or "") == "yes", "archived": bool(t.get("archived_at")),
            "age_days": round(age / 1440, 1) if age is not None and age >= 0 else None,
            "in_status_days": round(in_status / 1440, 1) if in_status is not None and in_status >= 0 else None,
            "status_since": since, "moves": len(moves), "edits": edits,
            "named_in": len(named_in.get(tid, ())), "activity": strip,
        })
    _work.clear()
    _work.update(fresh_work)
    live = {(sid, s["end"]) for sid, s in sessions.items()}
    for k in [k for k in _turns if k not in live]:
        del _turns[k]
    out.sort(key=lambda r: (r["done_at"] or r["first"] or r["created"]), reverse=True)
    return out
