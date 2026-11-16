"""The calendar: one time axis for a project.

Two kinds of things sit on it and the page draws them differently. In the
foreground, *intentions* — tasks with dates (due, planned, created, done),
the operator's own entries (meetings, deadlines, reminders, notes), sprint
spans and milestones. In the background, *facts* per day — sessions,
turns, minutes, commits and lines, hours logged, checkpoints — the density
of work, never events. One read returns both for a range, in ISO dates,
whatever form the ledgers keep them in.

Entries and milestones are the operator's field: two small append-only
ledgers, written through this router. A milestone is an outcome the code
is *for* — a sentence, the check that says when it is true, a target date
— and tasks join it through a link ledger, so the task schema stays as it
is and one task can serve one milestone.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from ..csvio import append_row, rewrite_rows
from ..date_utils import format_yymm_dd, parse_yymm_dd
from .. import limits
from ..db import ViewStore
from ..file_safety import edit_json, safe_read_json
from ..entities import (
    CALENDAR_ENTRY_COLUMNS, CALENDAR_ENTRY_KINDS, CALENDAR_ENTRY_STATUSES,
    DONE_STATUSES, ENTITIES, MILESTONE_COLUMNS, MILESTONE_STATUSES, MILESTONE_TASK_COLUMNS,
)
from .deps import (
    not_found,
    PROJECT_CODE_RE, create_answer, etag_for, get_store, json_response, maybe_304,
    rewrite_one, rows_or_empty,
)
from .sessions_api import _attach_git
from .time_tracking import decorate as _time_decorate
from ..date_utils import now_iso

router = APIRouter()

ENTRIES_FILE = "calendar_entries.csv"
MILESTONES_FILE = "milestones.csv"
MILESTONE_TASKS_FILE = "milestone_tasks.csv"
_ACTOR = "operator"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YYMM = re.compile(r"^\d{4}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}$")
_CODE = PROJECT_CODE_RE  # the one shape of a project code (deps)
MAX_TITLE = 200
MAX_BODY = limits.MAX_TEXT

ENTRY_MUTABLE = (
    "kind", "date", "time", "end_date", "end_time", "title", "body", "task_id",
    "milestone_id", "people", "link", "status",
)
MILESTONE_MUTABLE = ("title", "outcome", "check", "target_date", "reached_date", "status", "position", "proof")
REASONS_FILE = "project_reasons.json"
REASON_KINDS = ("attention", "money", "time", "learning", "other")




def _mint(prefix: str, *parts: str) -> str:
    seed = "|".join(parts) + f"|{time.time()!r}"
    return prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]


def iso(value: Any) -> str:
    """Whatever date form a ledger keeps, out as ISO; '' when it is not a date."""
    s = str(value or "").strip()
    if not s:
        return ""
    if _ISO.match(s):
        return s
    if _YYMM.match(s):
        try:
            return parse_yymm_dd(s).isoformat()
        except (ValueError, TypeError):
            return ""
    if len(s) >= 10 and _ISO.match(s[:10]):
        return s[:10]
    return ""


def _iso_or_422(value: Any, field: str, required: bool = False) -> str:
    s = str(value or "").strip()
    if not s:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} is required (YYYY-MM-DD)")
        return ""
    out = iso(s)
    if not out:
        raise HTTPException(status_code=422, detail=f"{field} must be YYYY-MM-DD")
    try:
        date.fromisoformat(out)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} is not a real date") from None
    return out


def _code_or_422(value: Any) -> str:
    """A project code a row can be written under: one code, no wildcards,
    never the scope words."""
    code = str(value or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="project is required")
    if code.lower() == "all" or not _CODE.match(code):
        raise HTTPException(status_code=422, detail="project must be one code (letters, digits, _ . -), not a scope")
    return code


def _time_or_422(value: Any, field: str) -> str:
    s = str(value or "").strip()
    if s and not _TIME.match(s):
        raise HTTPException(status_code=422, detail=f"{field} must be HH:MM")
    return s


_rows = rows_or_empty  # the one forgiving read (deps), under the name this file uses


# ---------------------------------------------------------------------------
# The read: one range, everything dated
# ---------------------------------------------------------------------------

def _range(from_: str | None, to: str | None) -> tuple[str, str]:
    today = date.today()
    start = _iso_or_422(from_, "from") or (today.replace(day=1) - timedelta(days=7)).isoformat()
    end = _iso_or_422(to, "to") or (today.replace(day=1) + timedelta(days=45)).isoformat()
    if end < start:
        start, end = end, start
    return start, end


def _day(days: dict[str, dict[str, int]], d: str) -> dict[str, int]:
    return days.setdefault(d, {
        "tasks_created": 0, "tasks_done": 0, "sessions": 0, "turns": 0, "minutes": 0,
        "commits": 0, "files": 0, "add": 0, "del": 0, "hours_min": 0,
        "standups": 0, "decisions": 0, "scans": 0, "problems": 0, "entries": 0,
    })


def _done_dates(store: ViewStore, task_ids: set[str] | None = None) -> dict[str, str]:
    """The day each task last became done, from its own history; the agent's
    report is the fallback when the operator moved it before events existed.
    ``task_ids`` None reads every task once — a request over several codes
    scans the event ledger a single time."""
    out: dict[str, str] = {}
    for ev in _rows(store, "SELECT task_id, timestamp, new_value FROM task_events_mutual WHERE field = 'status' ORDER BY timestamp ASC"):
        tid = str(ev.get("task_id") or "")
        if task_ids is not None and tid not in task_ids:
            continue
        nv = str(ev.get("new_value") or "").strip().lower()
        if nv in DONE_STATUSES:
            out[tid] = iso(ev.get("timestamp"))
        elif tid in out:
            out.pop(tid, None)
    return out


def _links(store: ViewStore) -> list[dict]:
    return _rows(store, "SELECT milestone_id, task_id, created_at FROM milestone_tasks_mutual ORDER BY created_at ASC")


def _in(codes: list[str]) -> str:
    return ",".join("?" * len(codes))


def _by_project(rows: list[dict], codes: list[str]) -> dict[str, list[dict]]:
    """Rows of one read over several codes, split by their project, each
    code's rows in the order the read gave them."""
    out: dict[str, list[dict]] = {c: [] for c in codes}
    for r in rows:
        bucket = out.get(str(r.get("project") or ""))
        if bucket is not None:
            bucket.append(r)
    return out


def _task_rows(store: ViewStore, project: str, done: dict[str, str] | None = None, links: list[dict] | None = None) -> list[dict[str, Any]]:
    """The project's tasks: its own and the ones that list it among their
    projects — matched as a whole code, so `seo` never reads `seo-fight`."""
    return _task_rows_by_code(store, [project], done, links)[project]


def _lists_code(projects: Any, code: str) -> bool:
    return f",{code}," in "," + str(projects or "").replace(" ", "") + ","


def _task_rows_by_code(
    store: ViewStore, codes: list[str], done: dict[str, str] | None = None, links: list[dict] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """``_task_rows`` for several codes from one read of the task view."""
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in codes}
    valid = [c for c in codes if _CODE.match(c)]
    if not valid:
        return out
    likes = " OR ".join(
        "(',' || REPLACE(COALESCE(projects, ''), ' ', '') || ',') LIKE ? ESCAPE '\\'" for _ in valid
    )
    rows = _rows(
        store,
        "SELECT id, title, status, priority, assignee, lane, created_date, due_date, today_on, "
        "resurface_on, archived_at, agent_done_at, sprint_id, tags, project, projects "
        f"FROM tasks_mutual WHERE project IN ({_in(valid)}) OR {likes}",
        tuple(valid) + tuple(f"%,{c.replace('_', chr(92) + '_')},%" for c in valid),
    )
    if done is None:
        done = _done_dates(store, {str(r.get("id")) for r in rows})
    if links is None:
        links = _links(store)
    by_task = {str(l.get("task_id")): str(l.get("milestone_id")) for l in links}
    for project in valid:
        for r in rows:
            if r.get("project") != project and not _lists_code(r.get("projects"), project):
                continue
            status = str(r.get("status") or "unclassified").strip().lower() or "unclassified"
            tid = str(r.get("id"))
            is_done = status in DONE_STATUSES
            out[project].append({
                "id": tid, "title": r.get("title") or "", "status": status, "project": str(r.get("project") or project),
                "priority": r.get("priority") or "", "assignee": r.get("assignee") or "",
                "created": iso(r.get("created_date")), "due": iso(r.get("due_date")),
                "planned": iso(r.get("today_on")), "resurface": iso(r.get("resurface_on")),
                # A task born done, or moved before events existed: the day it was
                # archived, else the day it was written — never a blank.
                "done": (done.get(tid) or iso(r.get("agent_done_at")) or iso(r.get("archived_at")) or iso(r.get("created_date"))) if is_done else "",
                "archived": bool(r.get("archived_at")), "sprint_id": r.get("sprint_id") or "",
                "milestone_id": by_task.get(tid, ""), "tags": r.get("tags") or "",
            })
    return out


def _sessions_by_code(store: ViewStore, codes: list[str], start: str, end: str, days: dict[str, dict[str, int]]) -> dict[str, list[dict[str, Any]]]:
    """Each code's sessions in the range, from one read; the day counts are
    added code by code, as the page has always summed them."""
    if not codes:
        return {}
    # Session dates are kept as YYMM-DD, which only spans 2000..2099; a
    # wider ask ("everything") is clamped to what the ledger can hold.
    lo, hi = date(2000, 1, 1), date(2099, 12, 31)
    s0 = format_yymm_dd(min(max(date.fromisoformat(start), lo), hi))
    s1 = format_yymm_dd(min(max(date.fromisoformat(end), lo), hi))
    rows = _rows(
        store,
        "SELECT id, project, agent_id, created_date, start_time, end_time, duration_min, turns_n, l1 "
        f"FROM sessions WHERE project IN ({_in(codes)}) AND created_date >= ? AND created_date <= ? "
        "ORDER BY created_date ASC, start_time ASC",
        (*codes, s0, s1),
    )
    if rows:
        try:
            # One pass for every code: a repository's HEAD is read once.
            _attach_git(store, rows)
        except Exception:  # noqa: BLE001 — no git is a fact, not a failure
            for r in rows:
                r.setdefault("git", {"commits": 0, "files": 0, "add": 0, "del": 0})
    out: dict[str, list[dict[str, Any]]] = {}
    for project, mine in _by_project(rows, codes).items():
        out[project] = []
        for r in mine:
            d = iso(r.get("created_date"))
            if not d:
                continue
            g = r.get("git") or {}
            day = _day(days, d)
            day["sessions"] += 1
            day["turns"] += int(r.get("turns_n") or 0)
            day["minutes"] += int(r.get("duration_min") or 0)
            for k in ("commits", "files", "add", "del"):
                day[k] += int(g.get(k) or 0)
            out[project].append({
                "id": r.get("id"), "agent_id": r.get("agent_id"), "date": d, "project": project,
                "start": r.get("start_time") or "", "end": r.get("end_time") or "",
                "minutes": int(r.get("duration_min") or 0), "turns": int(r.get("turns_n") or 0),
                "l1": r.get("l1") or "", "git": {k: int(g.get(k) or 0) for k in ("commits", "files", "add", "del")},
            })
    return out


_COUNTED = (("standups", "standups_mutual"), ("decisions", "decisions_mutual"), ("scans", "scans_mutual"), ("problems", "problems_mutual"))


def _facts_per_day(store: ViewStore, codes: list[str], days: dict[str, dict[str, int]], start: str, end: str) -> None:
    """Hours logged and the counted ledgers, per day: one read per ledger
    for every code, summed code by code."""
    if not codes:
        return
    ent = ENTITIES["time_entry"]
    hours = _by_project(_rows(store, f"SELECT * FROM {ent.view} WHERE project IN ({_in(codes)})", tuple(codes)), codes)
    counts = {
        key: _by_project(_rows(
            store,
            f"SELECT project, created_date, COUNT(*) AS n FROM {view} WHERE project IN ({_in(codes)}) "
            "GROUP BY project, created_date", tuple(codes),
        ), codes)
        for key, view in _COUNTED
    }
    now = datetime.now()
    for c in codes:
        for r in hours[c]:
            d = iso(r.get("created_date"))
            if not d or not (start <= d <= end):
                continue
            try:
                sec = int(_time_decorate(dict(r), now).get("attributed_sec") or 0)
            except Exception:  # noqa: BLE001
                sec = int(r.get("duration_min") or 0) * 60
            _day(days, d)["hours_min"] += round(sec / 60)
        for key, _view in _COUNTED:
            for r in counts[key][c]:
                d = iso(r.get("created_date"))
                if d and start <= d <= end:
                    _day(days, d)[key] += int(r.get("n") or 0)


def _entries_by_code(store: ViewStore, codes: list[str], start: str, end: str) -> dict[str, list[dict[str, Any]]]:
    if not codes:
        return {}
    rows = _rows(store, f"SELECT * FROM calendar_entries_mutual WHERE project IN ({_in(codes)}) ORDER BY date ASC, time ASC", tuple(codes))
    out: dict[str, list[dict[str, Any]]] = {}
    for project, mine in _by_project(rows, codes).items():
        kept: list[dict[str, Any]] = []
        for r in mine:
            d = iso(r.get("date"))
            e = iso(r.get("end_date")) or d
            if not d or e < start or d > end:
                continue
            kept.append({**{k: r.get(k) or "" for k in CALENDAR_ENTRY_COLUMNS}, "date": d, "end_date": iso(r.get("end_date")), "source": "calendar"})
        kept.sort(key=lambda r: (r["date"], r.get("time") or ""))
        out[project] = kept
    return out


def _milestones(store: ViewStore, project: str, tasks: list[dict[str, Any]], links: list[dict] | None = None) -> list[dict[str, Any]]:
    return _milestones_by_code(store, [project], tasks, links)[project]


def _milestones_by_code(store: ViewStore, codes: list[str], tasks: list[dict[str, Any]], links: list[dict] | None = None) -> dict[str, list[dict[str, Any]]]:
    if not codes:
        return {}
    by_id = {t["id"]: t for t in tasks}
    if links is None:
        links = _links(store)
    joined: dict[str, list[str]] = {}
    for l in links:
        joined.setdefault(str(l.get("milestone_id")), []).append(str(l.get("task_id")))
    rows = _rows(store, f"SELECT * FROM milestones_mutual WHERE project IN ({_in(codes)}) ORDER BY position ASC, created_at ASC", tuple(codes))
    out: dict[str, list[dict[str, Any]]] = {}
    for project, mine in _by_project(rows, codes).items():
        out[project] = []
        for r in mine:
            mid = str(r.get("id"))
            ids = joined.get(mid, [])
            members = [by_id[t] for t in ids if t in by_id]
            done = sum(1 for t in members if t["status"] in DONE_STATUSES)
            out[project].append({
                **{k: r.get(k) or "" for k in MILESTONE_COLUMNS},
                "target_date": iso(r.get("target_date")), "reached_date": iso(r.get("reached_date")),
                "position": int(r.get("position") or 0),
                "tasks": ids, "tasks_n": len(members), "done_n": done,
                "first_task": min((t["created"] for t in members if t["created"]), default=""),
                "last_done": max((t["done"] for t in members if t["done"]), default=""),
            })
    return out


def _sprint_rows(store: ViewStore) -> list[dict]:
    ent = ENTITIES["sprint"]
    return _rows(store, f"SELECT id, name, status, started_date, ended_date, bet_days, projects FROM {ent.view}")


def _sprints(store: ViewStore, project: str, rows: list[dict] | None = None) -> list[dict[str, Any]]:
    """The project's sprints. ``rows`` is every sprint, read once by a
    caller that asks for several codes."""
    out: list[dict[str, Any]] = []
    for r in (rows if rows is not None else _sprint_rows(store)):
        projects = [p.strip() for p in str(r.get("projects") or "").split(",") if p.strip()]
        if project not in projects:
            continue
        out.append({
            "id": r.get("id"), "name": r.get("name") or "", "status": r.get("status") or "",
            "started": iso(r.get("started_date")), "ended": iso(r.get("ended_date")),
            "bet_days": int(r.get("bet_days") or 0) or None,
        })
    return out


def codes_of(store: ViewStore, project: str) -> list[str]:
    """The scope: one project, a comma list (a board), or ``all`` — every
    project folder plus every code a task was ever written under."""
    raw = str(project or "").strip()
    if raw.lower() == "all":
        seen: list[str] = []
        for pf in store.projects:
            code = str(pf.code or "")
            if code and code not in seen:
                seen.append(code)
        for view in ("tasks_mutual", "calendar_entries_mutual", "milestones_mutual"):
            for r in _rows(store, f"SELECT DISTINCT project FROM {view}"):
                code = str(r.get("project") or "")
                if code and _CODE.match(code) and code not in seen:
                    seen.append(code)
        return sorted(seen)
    out: list[str] = []
    for c in raw.split(","):
        c = c.strip()
        if c and _CODE.match(c) and c not in out:
            out.append(c)
    return out


def _merge(lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Rows from several projects, each id once (a task in two projects,
    a sprint shared by both)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for rows in lists:
        for r in rows:
            key = str(r.get("id"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


@router.get("/api/calendar")
def calendar_read(
    request: Request,
    project: str = Query(...),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Everything dated on a project, for a range of days (ISO, inclusive).

    ``project`` is one code, a comma list (a board's members) or ``all``;
    ``projects`` in the answer names the codes that were read.

    ``days`` is the density: per ISO day, tasks created and done, sessions,
    turns, minutes, commits, files, lines added and deleted, hours logged,
    standups, decisions, scans, problems, entries. ``tasks`` carries every
    task of the project with its dates normalised (created, due, planned,
    resurface, done). ``entries``, ``milestones``, ``sprints``, ``sessions``
    are the range's rows.
    """
    start, end = _range(from_, to)
    # The minute is part of the key: a running timer's hours grow without
    # any file changing, and a yearly event's place depends on the date.
    etag = etag_for(f"calendar:{project}:{start}:{end}:{datetime.now():%Y-%m-%d %H:%M}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    codes = codes_of(store, project)
    days: dict[str, dict[str, int]] = {}
    done_all = _done_dates(store, None)
    links = _links(store)
    task_rows = _task_rows_by_code(store, codes, done_all, links)
    tasks = _merge([task_rows[c] for c in codes])
    for t in tasks:
        if t["created"] and start <= t["created"] <= end:
            _day(days, t["created"])["tasks_created"] += 1
        if t["done"] and start <= t["done"] <= end:
            _day(days, t["done"])["tasks_done"] += 1
    by_code = _sessions_by_code(store, codes, start, end, days)
    sessions = _merge([by_code[c] for c in codes])
    _facts_per_day(store, codes, days, start, end)
    entry_rows = _entries_by_code(store, codes, start, end)
    entries = _merge([entry_rows[c] for c in codes])
    entries.sort(key=lambda r: (r["date"], r.get("time") or ""))
    sessions.sort(key=lambda r: (r["date"], r.get("start") or ""))
    for e in entries:
        _day(days, e["date"])["entries"] += 1
    milestone_rows = _milestones_by_code(store, codes, tasks, links)
    milestones = _merge([milestone_rows[c] for c in codes])
    sprint_rows = _sprint_rows(store)
    return json_response({
        "project": project, "projects": codes, "from": start, "to": end, "today": date.today().isoformat(),
        "days": days, "tasks": tasks, "entries": entries,
        "milestones": milestones, "sprints": _merge([_sprints(store, c, sprint_rows) for c in codes]),
        "sessions": sessions,
    }, etag)


# ---------------------------------------------------------------------------
# Entries — the operator's own dates
# ---------------------------------------------------------------------------

def _entry_fields(body: dict, current: dict | None = None) -> dict[str, str]:
    cur = current or {}
    kind = str(body.get("kind", cur.get("kind") or "note")).strip().lower()
    if kind not in CALENDAR_ENTRY_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(CALENDAR_ENTRY_KINDS)}")
    status = str(body.get("status", cur.get("status") or "open")).strip().lower()
    if status not in CALENDAR_ENTRY_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(CALENDAR_ENTRY_STATUSES)}")
    title = str(body.get("title", cur.get("title") or "")).strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if len(title) > MAX_TITLE:
        raise HTTPException(status_code=422, detail=f"title is over {MAX_TITLE} characters")
    text = str(body.get("body", cur.get("body") or ""))
    if len(text) > MAX_BODY:
        raise HTTPException(status_code=422, detail=f"body is over {MAX_BODY} characters")
    d = _iso_or_422(body.get("date", cur.get("date")), "date", required=True)
    e = _iso_or_422(body.get("end_date", cur.get("end_date")), "end_date")
    if e and e < d:
        raise HTTPException(status_code=422, detail="end_date is before date")
    t0 = _time_or_422(body.get("time", cur.get("time")), "time")
    t1 = _time_or_422(body.get("end_time", cur.get("end_time")), "end_time")
    if t0 and t1 and (not e or e == d) and t1 < t0:
        raise HTTPException(status_code=422, detail="end_time is before time")
    return {
        "kind": kind, "status": status, "title": title, "body": text, "date": d, "end_date": e,
        "time": t0, "end_time": t1,
        "task_id": str(body.get("task_id", cur.get("task_id") or "")).strip(),
        "milestone_id": str(body.get("milestone_id", cur.get("milestone_id") or "")).strip(),
        "people": str(body.get("people", cur.get("people") or "")).strip(),
        "link": str(body.get("link", cur.get("link") or "")).strip(),
    }


@router.get("/api/calendar/entries")
def entries_list(
    request: Request, project: str = Query(...), from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None), store: ViewStore = Depends(get_store),
) -> Response:
    start, end = _range(from_, to)
    etag = etag_for(f"calendar:entries:{project}:{start}:{end}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    codes = codes_of(store, project)
    entry_rows = _entries_by_code(store, codes, start, end)
    entries = _merge([entry_rows[c] for c in codes])
    entries.sort(key=lambda r: (r["date"], r.get("time") or ""))
    return json_response({"entries": entries}, etag)


@router.post("/api/calendar/entries", status_code=201)
def entries_create(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, kind, date, title, time?, end_date?, end_time?, body?,
    task_id?, milestone_id?, people?, link?, actor?}``."""
    project = _code_or_422(body.get("project"))
    fields = _entry_fields(body)
    now = now_iso()
    row = {
        "id": _mint("ce_", project, fields["date"], fields["title"], now), "project": project,
        **fields, "created_at": now, "updated_at": now, "actor": str(body.get("actor") or _ACTOR),
    }
    append_row(store.data_root / ENTRIES_FILE, CALENDAR_ENTRY_COLUMNS, row)
    store.rebuild()
    return create_answer({"entry": {**row, "source": "calendar"}})


_rewrite = rewrite_one  # one row by id under the ledger's lock (deps)


@router.post("/api/calendar/entries/{entry_id}/update")
def entries_update(entry_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """Any of kind · date · time · end_date · end_time · title · body ·
    task_id · milestone_id · people · link · status."""
    hits = _rows(store, "SELECT * FROM calendar_entries_mutual WHERE id = ?", (entry_id,))
    cur = hits[0] if hits else None
    if cur is None:
        raise not_found("entry", entry_id)
    fields = _entry_fields({k: v for k, v in body.items() if k in ENTRY_MUTABLE}, cur)

    def apply(_rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        r.update(fields)
        r["updated_at"] = now_iso()
        return True

    row = _rewrite(store, ENTRIES_FILE, CALENDAR_ENTRY_COLUMNS, entry_id, apply, "entry")
    return {"entry": {**row, "source": "calendar"}}


@router.post("/api/calendar/entries/{entry_id}/delete")
def entries_delete(entry_id: str, store: ViewStore = Depends(get_store)) -> dict:
    def apply(rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        rows.remove(r)
        return True

    _rewrite(store, ENTRIES_FILE, CALENDAR_ENTRY_COLUMNS, entry_id, apply, "entry")
    return {"deleted": entry_id}


# ---------------------------------------------------------------------------
# Milestones — what the code is for
# ---------------------------------------------------------------------------

def _milestone_fields(body: dict, current: dict | None = None) -> dict[str, str]:
    cur = current or {}
    title = str(body.get("title", cur.get("title") or "")).strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if len(title) > MAX_TITLE:
        raise HTTPException(status_code=422, detail=f"title is over {MAX_TITLE} characters")
    status = str(body.get("status", cur.get("status") or "planned")).strip().lower()
    if status not in MILESTONE_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(MILESTONE_STATUSES)}")
    reached = _iso_or_422(body.get("reached_date", cur.get("reached_date")), "reached_date")
    if status == "reached" and not reached:
        reached = date.today().isoformat()
    if status != "reached":
        reached = ""
    try:
        position = int(body.get("position", cur.get("position") or 0) or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="position must be a number") from None
    if position < 0:
        raise HTTPException(status_code=422, detail="position cannot be negative")
    return {
        "title": title, "status": status, "reached_date": reached, "position": str(position),
        "outcome": str(body.get("outcome", cur.get("outcome") or "")).strip()[:MAX_BODY],
        "check": str(body.get("check", cur.get("check") or "")).strip()[:MAX_BODY],
        "proof": str(body.get("proof", cur.get("proof") or "")).strip()[:MAX_BODY],
        "target_date": _iso_or_422(body.get("target_date", cur.get("target_date")), "target_date"),
    }


# ---------------------------------------------------------------------------
# The reason — why the project exists, one line per project
# ---------------------------------------------------------------------------

def _reasons(store: ViewStore) -> dict[str, dict[str, str]]:
    try:
        data = safe_read_json(store.data_root / REASONS_FILE)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/api/projects/{code}/reason")
def reason_read(code: str, store: ViewStore = Depends(get_store)) -> dict:
    """``{project, kind, text, updated_at}`` — kind ∈ attention · money ·
    time · learning · other; empty when never set."""
    r = _reasons(store).get(code) or {}
    return {"project": code, "kind": r.get("kind") or "", "text": r.get("text") or "", "updated_at": r.get("updated_at") or ""}


@router.post("/api/projects/{code}/reason")
def reason_write(code: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    kind = str(body.get("kind") or "").strip().lower()
    if kind and kind not in REASON_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(REASON_KINDS)}")
    text = str(body.get("text") or "").strip()
    if len(text) > 500:
        raise HTTPException(status_code=422, detail="text is over 500 characters")
    code = _code_or_422(code)
    # One read-modify-write cycle under one lock (file_safety.edit_json).
    row = {"kind": kind, "text": text, "updated_at": now_iso()}
    edit_json(store.data_root / REASONS_FILE, lambda data: data.update({code: row}))
    return {"project": code, **row}


@router.get("/api/milestones")
def milestones_list(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for(f"milestones:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    codes = codes_of(store, project)
    done_all = _done_dates(store, None)
    links = _links(store)
    task_rows = _task_rows_by_code(store, codes, done_all, links)
    tasks = _merge([task_rows[c] for c in codes])
    milestone_rows = _milestones_by_code(store, codes, tasks, links)
    return json_response({"milestones": _merge([milestone_rows[c] for c in codes])}, etag)


@router.post("/api/milestones", status_code=201)
def milestones_create(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, title, outcome?, check?, target_date?, status?, tasks?, actor?}``."""
    project = _code_or_422(body.get("project"))
    fields = _milestone_fields(body)
    if not body.get("position"):
        n = len(_rows(store, "SELECT id FROM milestones_mutual WHERE project = ?", (project,)))
        fields["position"] = str(n + 1)
    now = now_iso()
    actor = str(body.get("actor") or _ACTOR)
    row = {
        "id": _mint("ms_", project, fields["title"], now), "project": project, **fields,
        "created_at": now, "updated_at": now, "actor": actor,
    }
    wanted = [str(t) for t in _ids(body, "tasks") if str(t).strip()]
    if wanted:
        known = {str(r.get("id")) for r in _rows(store, "SELECT id FROM tasks_mutual")}
        missing = [t for t in wanted if t not in known]
        if missing:
            raise HTTPException(status_code=422, detail=f"task not found: {', '.join(missing)}")
    append_row(store.data_root / MILESTONES_FILE, MILESTONE_COLUMNS, row)
    _link_tasks(store, row["id"], wanted, actor, now)
    store.rebuild()
    ms = [m for m in _milestones(store, project, _task_rows(store, project)) if m["id"] == row["id"]]
    return create_answer({"milestone": ms[0] if ms else row})


def _link_tasks(store: ViewStore, milestone_id: str, task_ids: list[str], actor: str, now: str) -> None:
    """One milestone per task, in one pass under one lock: the tasks' old
    links go and the new rows come in the same rewrite, so two writers
    cannot leave a task serving two milestones."""
    ids = [t for t in dict.fromkeys(task_ids) if t]
    if not ids:
        return
    csv_path = store.data_root / MILESTONE_TASKS_FILE
    fresh = [{
        "id": _mint("mt_", milestone_id, t, now, str(i)), "milestone_id": milestone_id,
        "task_id": t, "created_at": now, "actor": actor,
    } for i, t in enumerate(ids)]
    if not csv_path.exists():
        for row in fresh:
            append_row(csv_path, MILESTONE_TASK_COLUMNS, row)
        return
    wanted = set(ids)

    def relink(rows: list[dict[str, str]]) -> bool:
        rows[:] = [r for r in rows if r.get("task_id") not in wanted]
        rows.extend(fresh)
        return True

    rewrite_rows(csv_path, MILESTONE_TASK_COLUMNS, relink)


@router.post("/api/milestones/{milestone_id}/update")
def milestones_update(milestone_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """Any of title · outcome · check · target_date · reached_date · status · position."""
    hits = _rows(store, "SELECT * FROM milestones_mutual WHERE id = ?", (milestone_id,))
    cur = hits[0] if hits else None
    if cur is None:
        raise not_found("milestone", milestone_id)
    fields = _milestone_fields({k: v for k, v in body.items() if k in MILESTONE_MUTABLE}, cur)

    def apply(_rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        r.update(fields)
        r["updated_at"] = now_iso()
        return True

    row = _rewrite(store, MILESTONES_FILE, MILESTONE_COLUMNS, milestone_id, apply, "milestone")
    project = str(row.get("project") or "")
    ms = [m for m in _milestones(store, project, _task_rows(store, project)) if m["id"] == milestone_id]
    return {"milestone": ms[0] if ms else row}


def _ids(body: dict, key: str) -> list:
    """A list of ids from the body, or nothing; a number or a string there
    was a 500."""
    got = body.get(key)
    if got in (None, ""):
        return []
    if not isinstance(got, list):
        raise HTTPException(status_code=422, detail=f"{key} is a list of task ids")
    return got


@router.post("/api/milestones/{milestone_id}/tasks")
def milestones_tasks(milestone_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{add?: [task ids], remove?: [task ids], actor?}`` — a task serves one
    milestone; adding it here takes it from any other."""
    hits = _rows(store, "SELECT * FROM milestones_mutual WHERE id = ?", (milestone_id,))
    cur = hits[0] if hits else None
    if cur is None:
        raise not_found("milestone", milestone_id)
    actor = str(body.get("actor") or _ACTOR)
    now = now_iso()
    add = [str(t) for t in _ids(body, "add") if str(t).strip()]
    remove = {str(t) for t in _ids(body, "remove") if str(t).strip()}
    known = {str(r.get("id")) for r in _rows(store, "SELECT id FROM tasks_mutual")}
    missing = [t for t in add if t not in known]
    if missing:
        raise HTTPException(status_code=422, detail=f"task not found: {', '.join(missing)}")
    _link_tasks(store, milestone_id, add, actor, now)
    if remove:
        csv_path = store.data_root / MILESTONE_TASKS_FILE

        def drop(rows: list[dict[str, str]]) -> bool:
            before = len(rows)
            rows[:] = [r for r in rows if not (r.get("milestone_id") == milestone_id and r.get("task_id") in remove)]
            return len(rows) != before

        if csv_path.exists():
            rewrite_rows(csv_path, MILESTONE_TASK_COLUMNS, drop)
    store.rebuild()
    project = str(cur.get("project") or "")
    ms = [m for m in _milestones(store, project, _task_rows(store, project)) if m["id"] == milestone_id]
    return {"milestone": ms[0] if ms else cur}


@router.post("/api/milestones/{milestone_id}/delete")
def milestones_delete(milestone_id: str, store: ViewStore = Depends(get_store)) -> dict:
    def apply(rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        rows.remove(r)
        return True

    _rewrite(store, MILESTONES_FILE, MILESTONE_COLUMNS, milestone_id, apply, "milestone")
    csv_path = store.data_root / MILESTONE_TASKS_FILE
    if csv_path.exists():
        def drop(rows: list[dict[str, str]]) -> bool:
            before = len(rows)
            rows[:] = [r for r in rows if r.get("milestone_id") != milestone_id]
            return len(rows) != before
        rewrite_rows(csv_path, MILESTONE_TASK_COLUMNS, drop)
    entries_path = store.data_root / ENTRIES_FILE
    if entries_path.exists():
        # Entries that pointed at it stay, unpointed: a dangling id would
        # draw them on a row that no longer exists.
        def unpoint(rows: list[dict[str, str]]) -> bool:
            touched = False
            for r in rows:
                if r.get("milestone_id") == milestone_id:
                    r["milestone_id"] = ""
                    touched = True
            return touched
        rewrite_rows(entries_path, CALENDAR_ENTRY_COLUMNS, unpoint)
    store.rebuild()
    return {"deleted": milestone_id}
