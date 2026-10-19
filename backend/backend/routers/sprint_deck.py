"""The sprint deck: every block in flight, its tasks, clocks and cumulative flow, on one page."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response

from ..db import ViewStore
from ..entities import is_done
from .deps import DONE_SQL, etag_for, get_store, json_response, maybe_304
from .sprints import (
    _by_sprint, _events_of, _member_spans_many, _ph, _sessions_of, _sprint_clocks_many, _sprint_day,
)

router = APIRouter()


@router.get("/api/sprints/deck")
def sprints_deck(
    request: Request,
    days: int = Query(0, ge=0, le=120),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every running block of every project, with everything the cross-project
    board needs in one call: derived clocks, the day's plan, the tasks
    themselves, any timer currently running on the block, and how long since
    anything happened to it. One request so a page can be dense without being
    slow."""
    etag = etag_for(f"sprints:deck:{days}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    import datetime as _dt
    today = _dt.date.today()
    sprints = store.query(
        "SELECT id, name, projects, started_date, time_budget_h, bet_days, status, md_ref "
        "FROM sprints_mutual WHERE status = 'active' ORDER BY started_date ASC, id ASC"
    )
    open_timers = store.query(
        "SELECT id, project, sprint_id, started_at, paused_at, paused_total_sec, share_pct, note "
        "FROM time_entries_mutual WHERE COALESCE(ended_at, '') = ''"
    )
    # Every ledger is read once for all the blocks, then split by block.
    sids = [str(sp["id"]) for sp in sprints]
    rows_of = _by_sprint(store.query(
        "SELECT id, title, status, position, today_on, stack_id, priority, assignee, sprint_id "
        f"FROM tasks_mutual WHERE sprint_id IN ({_ph(sids)}) AND COALESCE(archived_at, '') = '' "
        "ORDER BY COALESCE(TRY_CAST(position AS DOUBLE), 0) ASC", tuple(sids),
    ), sids) if sids else {}
    # One read of the blocks' task history serves everything below.
    events = _events_of(store, [str(t["id"]) for rows in rows_of.values() for t in rows])
    # When each task joined the block and when it landed — the two dates
    # a cumulative flow is read with: the gap between them is lead time,
    # and a task still open since its join date is work in flight.
    spans_of = _member_spans_many(store, {
        str(sp["id"]): _sprint_day(str(sp.get("started_date") or "")) or today for sp in sprints
    }, events)
    ids_of = {sid: [str(t["id"]) for t in rows] for sid, rows in rows_of.items()}
    sessions_of = _sessions_of(store, ids_of)
    clocks = _sprint_clocks_many(store, ids_of, sessions_of)
    entries_of = _by_sprint(store.query(
        "SELECT sprint_id, created_date, started_at, duration_min, share_pct "
        f"FROM time_entries_mutual WHERE sprint_id IN ({_ph(sids)})", tuple(sids),
    ), sids) if sids and days > 0 else {}

    blocks: list[dict] = []
    for sp in sprints:
        sid = str(sp["id"])
        rows = rows_of[sid]
        mine = {str(t["id"]) for t in rows}
        task_events = [e for e in events if str(e["task_id"]) in mine]
        tasks = _deck_tasks(rows, task_events, {x["id"]: x for x in spans_of[sid]})
        human_min, agent_min = clocks[sid]
        stamps = [e["timestamp"] for e in task_events if e["timestamp"] is not None]
        block = _deck_block(sp, tasks, today, human_min, agent_min if tasks else 0.0,
                            str(max(stamps) or "") if stamps else "")
        if days > 0:
            block["series"] = _deck_series(
                today, days, rows, task_events, entries_of[sid], sessions_of[sid] if tasks else [],
                {t["id"]: t["joined"] for t in tasks},
            )
        timer = next((t for t in open_timers if str(t.get("sprint_id") or "") == sid), None)
        block["timer"] = ({
            "id": str(timer["id"]), "started_at": timer.get("started_at"),
            "paused_at": timer.get("paused_at"),
            "paused_total_sec": timer.get("paused_total_sec"),
            "share_pct": timer.get("share_pct"), "note": timer.get("note"),
        } if timer else None)
        blocks.append(block)
    # Projects that have blocks, plus their unassigned backlog depth.
    codes = sorted({b["project"] for b in blocks if b["project"]})
    settled = store.query(
        "SELECT id, name, projects, started_date, ended_date, bet_days, time_budget_h "
        "FROM sprints_mutual WHERE status = 'ended' ORDER BY ended_date DESC LIMIT 12"
    )
    return json_response({
        "today": today.isoformat(),
        "projects": codes,
        "backlog": _deck_backlog(store, codes),
        "blocks": blocks,
        "running_elsewhere": [
            {"id": str(t["id"]), "project": t.get("project"), "sprint_id": t.get("sprint_id"),
             "started_at": t.get("started_at"), "paused_at": t.get("paused_at"),
             "paused_total_sec": t.get("paused_total_sec"), "share_pct": t.get("share_pct")}
            for t in open_timers
        ],
        "settled": [{
            "id": str(s["id"]), "name": s.get("name"),
            "project": str(s.get("projects") or "").split(",")[0].strip(),
            "started_date": s.get("started_date"), "ended_date": s.get("ended_date"),
            "bet_days": s.get("bet_days"), "budget_h": s.get("time_budget_h"),
        } for s in settled],
    }, etag)


def _deck_tasks(rows: list[dict], task_events: list[dict], spans: dict[str, dict]) -> list[dict]:
    """The block's cards with their join, landing and how long each has sat
    where it is: the last status change, or its join if it has never moved
    (a number for "stuck")."""
    since: dict[str, str] = {}
    for e in task_events:
        if e["field"] == "status":
            since[str(e["task_id"])] = str(e["timestamp"])
    return [{
        "id": str(t["id"]), "title": t.get("title"), "status": t.get("status"),
        "today_on": t.get("today_on"), "stack_id": t.get("stack_id"),
        "priority": t.get("priority"), "assignee": t.get("assignee"),
        "joined": (spans.get(str(t["id"])) or {}).get("joined"),
        "done_on": (spans.get(str(t["id"])) or {}).get("done"),
        "status_since": since.get(str(t["id"]))
            or (spans.get(str(t["id"])) or {}).get("joined"),
    } for t in rows]


def _deck_block(sp: dict, tasks: list[dict], today, human_min, agent_min, last_at: str) -> dict:
    """One block's counts, clocks and days, without its series and timer."""
    started = str(sp.get("started_date") or "")
    days_left = None
    ran_days = None
    try:
        d0 = _sprint_day(started)
        if d0 is not None:
            ran_days = (today - d0).days
            if sp.get("bet_days") not in (None, ""):
                days_left = int(sp["bet_days"]) - ran_days
    except (ValueError, TypeError):
        pass
    return {
        "id": str(sp["id"]), "name": sp.get("name"),
        "project": str(sp.get("projects") or "").split(",")[0].strip(),
        "started_date": started, "bet_days": sp.get("bet_days"),
        "days_left": days_left, "ran_days": ran_days,
        "budget_h": sp.get("time_budget_h"),
        "tasks_total": len(tasks),
        "tasks_done": sum(1 for t in tasks if is_done(t["status"] or "")),
        "tasks_doing": sum(1 for t in tasks if str(t["status"] or "").lower() in ("doing", "review")),
        "today_n": sum(1 for t in tasks if str(t.get("today_on") or "") == today.isoformat()),
        "human_min": human_min, "agent_min": agent_min,
        "last_event_at": last_at, "tasks": tasks, "series": [],
    }


def _deck_series(today, days: int, rows: list[dict], task_events: list[dict],
                 entries: list[dict], sessions: list[dict], joined: dict[str, str]) -> list[dict]:
    """The daily rhythm of a block over the last ``days``: what landed, what
    was worked, how much noise it made, and where every task stood."""
    import datetime as _dt
    first = today - _dt.timedelta(days=days - 1)
    buckets = {
        (first + _dt.timedelta(days=i)).isoformat(): {
            "date": (first + _dt.timedelta(days=i)).isoformat(),
            "done": 0, "human_min": 0, "agent_min": 0, "events": 0,
            "bands": {},
        }
        for i in range(days)
    }
    if rows:
        for e in task_events:
            d = _sprint_day(str(e["timestamp"]))
            key = d.isoformat() if d else ""
            if key not in buckets:
                continue
            buckets[key]["events"] += 1
            if e["field"] == "status" and is_done(e.get("new_value") or ""):
                buckets[key]["done"] += 1
        _deck_bands(buckets, first, rows, [e for e in task_events if e["field"] == "status"], joined)
    for e in entries:
        d = _sprint_day(str(e.get("started_at") or "")) or _sprint_day(str(e.get("created_date") or ""))
        key = d.isoformat() if d else ""
        if key in buckets:
            buckets[key]["human_min"] += round(
                float(e.get("duration_min") or 0) * float(e.get("share_pct") or 100) / 100.0
            )
    for sess in sessions:
        d = _sprint_day(str(sess.get("created_date") or ""))
        key = d.isoformat() if d else ""
        if key in buckets:
            buckets[key]["agent_min"] += round(float(sess.get("duration_min") or 0))
    return list(buckets.values())


def _deck_bands(buckets: dict[str, dict], first: date, rows: list[dict], status_events: list[dict],
                joined: dict[str, str]) -> None:
    """Cumulative flow: where every member task stood on each day, replayed
    from its status events. A day's bands are the shape of the work in
    flight — a fat middle is a queue before Done. A task counts from the
    day it joined the block (``joined``, from the member spans)."""
    import datetime as _dt
    joined_on: dict[str, _dt.date] = {}
    moves: dict[str, list[tuple[_dt.date, str]]] = {}
    for t in rows:
        tid = str(t["id"])
        # The rows carry no created_date: reading it here put every task
        # on the block from the window's first day.
        joined_on[tid] = _sprint_day(str(joined.get(tid) or "")) or first
        moves[tid] = []
    # Replay every status change in order, then read each day off it.
    for e in status_events:
        d = _sprint_day(str(e["timestamp"]))
        if d is None:
            continue
        moves.setdefault(str(e["task_id"]), []).append(
            (d, str(e.get("new_value") or "").lower())
        )
        # The first move also reveals where the task started.
        tid = str(e["task_id"])
        if len(moves[tid]) == 1 and e.get("old_value"):
            moves[tid].insert(0, (joined_on.get(tid, first), str(e["old_value"]).lower()))
    current = {str(t["id"]): str(t.get("status") or "").lower() for t in rows}
    for key, bucket in buckets.items():
        day = _dt.date.fromisoformat(key)
        bands: dict[str, int] = {}
        for t in rows:
            tid = str(t["id"])
            if joined_on.get(tid, first) > day:
                continue
            past = [st for (d, st) in moves.get(tid, []) if d <= day]
            # No move by this day: the task still sat where it was
            # made, which is its first known status.
            status = past[-1] if past else (
                moves[tid][0][1] if moves.get(tid) else current.get(tid, "")
            )
            status = "done" if is_done(status) else (status or "unclassified")
            bands[status] = bands.get(status, 0) + 1
        bucket["bands"] = bands


def _deck_backlog(store: ViewStore, codes: list[str]) -> dict[str, int]:
    """Per project, the open tasks in no sprint, from one read."""
    if not codes:
        return {}
    rows = store.query(
        "SELECT project, projects FROM tasks_mutual WHERE "
        "COALESCE(sprint_id, '') = '' AND COALESCE(archived_at, '') = '' AND "
        "LOWER(COALESCE(status, '')) NOT IN " + DONE_SQL
    )
    return {
        code: sum(
            1 for r in rows
            if r.get("project") == code or code in str(r.get("projects") or "").split(",")
        )
        for code in codes
    }
