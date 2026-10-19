"""Sprints: the board of blocks, a block's series, the timeline of every block and one block's dossier."""

from __future__ import annotations

import bisect
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..csvio import rewrite_rows
from ..db import ViewStore
from ..docs_md import read_detail
from ..entities import ENTITIES, is_done
from ..project_admin import TRASH_DIR, _archive_file, _split_rows, _stamp
from .deps import day_date, etag_for, get_store, json_response, maybe_304, not_found, ymd
from ..taskevents import DEFAULT_ACTOR as _DEFAULT_ACTOR, append_events as _append_events

router = APIRouter()


@router.get("/api/sprints/board")
def sprints_board(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The board strip: every active sprint of the project with everything
    derived — tasks done/total, days left of the bet, human hours (timer
    entries on the sprint, share applied) and agent hours (captured sessions
    that mentioned any of the sprint's tasks)."""
    etag = etag_for(f"sprints:board:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sprints = store.query(
        "SELECT id, name, started_date, ended_date, time_budget_h, bet_days, status "
        "FROM sprints_mutual WHERE status = 'active' AND "
        "(projects = ? OR list_contains(string_split(COALESCE(projects, ''), ','), ?)) "
        "ORDER BY started_date ASC, id ASC",
        (project, project),
    )
    out = []
    today = time.strftime("%Y-%m-%d")
    sids = [str(sp["id"]) for sp in sprints]
    tasks_of = _by_sprint(store.query(
        f"SELECT id, status, archived_at, sprint_id FROM tasks_mutual WHERE sprint_id IN ({_ph(sids)})",
        tuple(sids),
    ), sids) if sids else {}
    # Human hours: stopped timer entries + the elapsed part of running ones
    # is the tracker's job; here the stored duration_min × share is enough.
    # Agent hours: sessions that mentioned any of the sprint's tasks. A
    # session counts once, whole — an approximation, labeled as such.
    clocks = _sprint_clocks_many(store, {sid: [str(t["id"]) for t in rows] for sid, rows in tasks_of.items()})
    for sp in sprints:
        sid = str(sp["id"])
        rows = tasks_of[sid]
        live = [t for t in rows if not (t.get("archived_at") or "")]
        done = sum(1 for t in live if is_done(t.get("status") or ""))
        human_min, agent_min = clocks[sid]
        # Days left of the bet, from the start date.
        days_left: int | None = None
        started = str(sp.get("started_date") or "")
        bet = sp.get("bet_days")
        try:
            if started and bet not in (None, ""):
                import datetime as _dt
                d0 = _dt.date.fromisoformat(f"20{started[:2]}-{started[2:4]}-{started[5:7]}") if len(started) == 7 else _dt.date.fromisoformat(started)
                days_left = int(bet) - (_dt.date.fromisoformat(today) - d0).days
        except (ValueError, TypeError):
            days_left = None
        out.append({
            "id": sid, "name": sp.get("name"), "started_date": started,
            "bet_days": bet, "days_left": days_left,
            "budget_h": sp.get("time_budget_h"),
            "tasks_total": len(live), "tasks_done": done,
            "human_min": round(human_min), "agent_min": round(agent_min),
        })
    unassigned = store.query_one(
        "SELECT COUNT(*) AS n FROM tasks_mutual WHERE (project = ? OR "
        "list_contains(string_split(COALESCE(projects, ''), ','), ?)) AND "
        "COALESCE(sprint_id, '') = '' AND COALESCE(archived_at, '') = ''",
        (project, project),
    )
    return json_response({"sprints": out, "no_sprint": int(unassigned["n"]) if unassigned else 0}, etag)


@router.post("/api/sprints/{sprint_id}/delete")
def sprints_delete(sprint_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """Delete a sprint that should not exist (mistakes — real endings use
    finish + retro): the row and its detail doc move to
    ``<data_root>/.trash/sprints/<id>-<stamp>/``; tasks pointing at it
    return to the backlog, each logged in its history."""
    ent = ENTITIES["sprint"]
    row = store.query_one("SELECT id, md_ref FROM sprints_mutual WHERE id = ?", (sprint_id,))
    if row is None:
        raise not_found("sprint", sprint_id)
    root = store.data_root
    trash = root / TRASH_DIR / "sprints" / f"{sprint_id}-{_stamp()}"
    trash.mkdir(parents=True, exist_ok=True)
    moved = _split_rows(root, trash, ent.csv, ent.columns, lambda r: r.get("id") == sprint_id)
    if row.get("md_ref") and _archive_file(root, trash, str(row["md_ref"])):
        pass
    # Tasks return to the backlog.
    freed: list[str] = []
    tasks_csv = root / "tasks.csv"
    if tasks_csv.exists():
        def strip(rows: list[dict[str, str]]) -> bool:
            changed = False
            for t in rows:
                if t.get("sprint_id") == sprint_id:
                    t["sprint_id"] = ""
                    freed.append(str(t.get("id") or ""))
                    changed = True
            return changed
        rewrite_rows(tasks_csv, ENTITIES["task"].columns, strip)
    for tid in freed:
        _append_events(store, tid, _DEFAULT_ACTOR, [("sprint_id", sprint_id, "")])
    store.rebuild()
    return {"deleted": sprint_id, "trash": str(trash), "sprint_rows": moved, "tasks_freed": len(freed)}


_ymd = ymd  # '2608-20' → '2026-08-20' (deps)


@router.get("/api/sprints/{sprint_id}/series")
def sprint_series(
    sprint_id: str, request: Request, store: ViewStore = Depends(get_store),
) -> Response:
    """Per-day series of one sprint, derived from the ledgers — feeds
    burn-ups, day heat, trend ghosts and the radar axes.

    For each day from ``started_date`` to today (or ``ended_date``):
    ``scope`` (member tasks — joins reconstructed from sprint_id events,
    tasks created into the sprint count from creation), ``done`` (members
    whose status reached done by that day), ``human_min`` (timer entries ×
    share), ``agent_min`` (captured sessions that mentioned member tasks —
    whole sessions, an approximation), ``events`` (task-history rows that
    day — the discipline-free activity signal).
    """
    etag = etag_for(f"sprints:series:{sprint_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sp = store.query_one(
        "SELECT id, started_date, ended_date, status, bet_days FROM sprints_mutual WHERE id = ?",
        (sprint_id,),
    )
    if sp is None:
        raise not_found("sprint", sprint_id)
    import datetime as _dt
    try:
        d0 = _dt.date.fromisoformat(_ymd(str(sp.get("started_date") or "")))
    except ValueError:
        raise HTTPException(status_code=409, detail="sprint has no readable started_date")
    d_end = _dt.date.today()
    if str(sp.get("status")) == "ended" and sp.get("ended_date"):
        try:
            d_end = _dt.date.fromisoformat(_ymd(str(sp["ended_date"])))
        except ValueError:
            pass
    n_days = max((d_end - d0).days + 1, 1)
    dates = [d0 + _dt.timedelta(days=i) for i in range(n_days)]

    # Join and done day per member: the one reconstruction (_member_spans).
    spans = _member_spans(store, sprint_id, d0)
    ids = [t["id"] for t in spans]
    ph = ",".join("?" * len(ids)) if ids else "''"
    joined_days = sorted(_dt.date.fromisoformat(t["joined"]) for t in spans)
    done_days = sorted(_dt.date.fromisoformat(t["done"]) for t in spans if t["done"])
    ev = store.query(
        f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({ph})", tuple(ids),
    ) if ids else []
    entries = store.query(
        "SELECT created_date, started_at, duration_min, share_pct FROM time_entries_mutual "
        "WHERE sprint_id = ?", (sprint_id,),
    )
    sessions = store.query(
        f"SELECT created_date, duration_min FROM sessions WHERE id IN "
        f"(SELECT DISTINCT session_id FROM task_mentions WHERE task_id IN ({ph}))",
        tuple(ids),
    ) if ids else []

    # Each ledger is read into its days once. Every day used to walk every
    # row and parse its date again: days × rows for a long sprint.
    acts: dict[_dt.date, int] = {}
    for e in ev:
        if (d := day_date(str(e["timestamp"]))) is not None:
            acts[d] = acts.get(d, 0) + 1
    human: dict[_dt.date, float] = {}
    for e in entries:
        d = day_date(str(e.get("started_at") or "")) or day_date(str(e.get("created_date") or ""))
        if d is not None:
            human[d] = human.get(d, 0) + float(e.get("duration_min") or 0) * float(e.get("share_pct") or 100) / 100.0
    agent: dict[_dt.date, float] = {}
    for sess in sessions:
        if (d := day_date(str(sess.get("created_date") or ""))) is not None:
            agent[d] = agent.get(d, 0) + float(sess.get("duration_min") or 0)

    days = []
    for d in dates:
        days.append({
            "date": d.isoformat(),
            "scope": bisect.bisect_right(joined_days, d),
            "done": bisect.bisect_right(done_days, d),
            "human_min": round(human.get(d, 0)), "agent_min": round(agent.get(d, 0)),
            "events": acts.get(d, 0),
        })
    return json_response({"sprint_id": sprint_id, "days": days}, etag)


# ---------------------------------------------------------------------------
# Sprint timeline + dossier — the whole history, and one block's full story
# ---------------------------------------------------------------------------


_sprint_day = day_date  # the day of a stamp or a YYMM-DD, or None (deps)


def _ph(items) -> str:
    return ",".join("?" * len(items))


def _by_sprint(rows: list[dict], sids) -> dict[str, list[dict]]:
    """Rows of one read over several sprints, split by sprint, each in the
    order the read gave them."""
    out: dict[str, list[dict]] = {sid: [] for sid in sids}
    for r in rows:
        bucket = out.get(str(r.get("sprint_id") or ""))
        if bucket is not None:
            bucket.append(r)
    return out


def _events_of(store: ViewStore, task_ids: list[str]) -> list[dict]:
    """The history of these tasks, oldest first."""
    if not task_ids:
        return []
    return store.query(
        f"SELECT task_id, timestamp, field, old_value, new_value FROM task_events_mutual "
        f"WHERE task_id IN ({_ph(task_ids)}) ORDER BY timestamp ASC", tuple(task_ids),
    )


def _member_spans(store: ViewStore, sprint_id: str, d0) -> list[dict]:
    """Member tasks with their join and done dates, reconstructed from the
    event log (a task created aboard counts from creation; the last status
    word wins)."""
    return _member_spans_many(store, {sprint_id: d0})[sprint_id]


def _member_spans_many(store: ViewStore, starts: dict, events: list[dict] | None = None) -> dict[str, list[dict]]:
    """``_member_spans`` for several sprints (id → start day) from one read
    of their tasks and one of the tasks' history. ``events`` is that history
    when the caller has already read it."""
    if not starts:
        return {}
    sids = list(starts)
    members = _by_sprint(store.query(
        f"SELECT id, title, status, created_date, sprint_id FROM tasks_mutual "
        f"WHERE sprint_id IN ({_ph(sids)}) AND COALESCE(archived_at, '') = ''", tuple(sids),
    ), sids)
    if events is None:
        events = _events_of(store, [str(t["id"]) for rows in members.values() for t in rows])
    by_task: dict[str, list[dict]] = {}
    for e in events:
        by_task.setdefault(str(e["task_id"]), []).append(e)
    out: dict[str, list[dict]] = {}
    for sid in sids:
        d0 = starts[sid]
        joined: dict = {}
        done_on: dict = {}
        for t in members[sid]:
            tid = str(t["id"])
            joined[tid] = _sprint_day(str(t.get("created_date") or "")) or d0
            for e in by_task.get(tid, ()):
                d = _sprint_day(str(e["timestamp"]))
                if d is None:
                    continue
                if e["field"] == "sprint_id" and str(e.get("new_value") or "") == sid:
                    joined[tid] = d
                if e["field"] == "status":
                    if is_done(e.get("new_value") or ""):
                        done_on.setdefault(tid, d)
                    else:
                        done_on.pop(tid, None)
            if is_done(t.get("status") or ""):
                done_on.setdefault(tid, joined[tid])
        out[sid] = [
            {
                "id": str(t["id"]), "title": t.get("title"), "status": t.get("status"),
                "joined": joined[str(t["id"])].isoformat(),
                "done": done_on[str(t["id"])].isoformat() if str(t["id"]) in done_on else None,
            }
            for t in members[sid]
        ]
    return out


def _sessions_of(store: ViewStore, task_ids: dict[str, list[str]]) -> dict[str, list[dict]]:
    """Per sprint, the captured sessions that mentioned any of its tasks —
    each session once, whole."""
    every = sorted({t for ids in task_ids.values() for t in ids})
    out: dict[str, list[dict]] = {sid: [] for sid in task_ids}
    if not every:
        return out
    said: dict[str, set[str]] = {}
    for m in store.query(
        f"SELECT DISTINCT task_id, session_id FROM task_mentions WHERE task_id IN ({_ph(every)})",
        tuple(every),
    ):
        if m["session_id"] is not None:
            said.setdefault(str(m["task_id"]), set()).add(str(m["session_id"]))
    wanted = sorted({s for ss in said.values() for s in ss})
    if not wanted:
        return out
    rows = store.query(
        f"SELECT id, created_date, duration_min FROM sessions WHERE id IN ({_ph(wanted)})", tuple(wanted),
    )
    for sid, ids in task_ids.items():
        mine = {s for t in ids for s in said.get(t, ())}
        out[sid] = [r for r in rows if str(r["id"]) in mine]
    return out


def _sprint_clocks(store: ViewStore, sprint_id: str, task_ids: list[str]) -> tuple[float, float]:
    return _sprint_clocks_many(store, {sprint_id: task_ids})[sprint_id]


def _sprint_clocks_many(
    store: ViewStore, task_ids: dict[str, list[str]], sessions: dict[str, list[dict]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Human minutes (timer entries × share) and agent minutes (sessions that
    mentioned the tasks) per sprint, from one read of each ledger."""
    if not task_ids:
        return {}
    sids = list(task_ids)
    human = {
        str(r["sprint_id"]): float(r["m"] or 0)
        for r in store.query(
            "SELECT sprint_id, COALESCE(SUM(COALESCE(duration_min, 0) * COALESCE(share_pct, 100) / 100.0), 0) AS m "
            f"FROM time_entries_mutual WHERE sprint_id IN ({_ph(sids)}) GROUP BY sprint_id", tuple(sids),
        )
    }
    if sessions is None:
        sessions = _sessions_of(store, task_ids)
    out: dict[str, tuple[float, float]] = {}
    for sid in sids:
        agent = sum(float(s["duration_min"]) for s in sessions.get(sid, ()) if s.get("duration_min") is not None)
        out[sid] = (round(human.get(sid, 0.0)), round(agent))
    return out


@router.get("/api/sprints/timeline")
def sprints_timeline(
    request: Request, project: str = Query(...), store: ViewStore = Depends(get_store),
) -> Response:
    """Every sprint of the project — active and settled — with its window,
    bet, task spans and clocks. Feeds the Overview gantt in one call."""
    etag = etag_for(f"sprints:timeline:{project}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT id, name, status, started_date, ended_date, bet_days, time_budget_h "
        "FROM sprints_mutual WHERE projects = ? OR "
        "list_contains(string_split(COALESCE(projects, ''), ','), ?) "
        "ORDER BY started_date ASC, id ASC", (project, project),
    )
    starts = {}
    for sp in rows:
        d0 = _sprint_day(str(sp.get("started_date") or ""))
        if d0 is not None:
            starts[str(sp["id"])] = d0
    spans = _member_spans_many(store, starts)
    clocks = _sprint_clocks_many(store, {sid: [t["id"] for t in ts] for sid, ts in spans.items()})
    out = []
    for sp in rows:
        d0 = starts.get(str(sp["id"]))
        if d0 is None:
            continue
        d_end = _sprint_day(str(sp.get("ended_date") or "")) if str(sp.get("status")) == "ended" else None
        tasks = spans[str(sp["id"])]
        human, agent = clocks[str(sp["id"])]
        out.append({
            "id": sp["id"], "name": sp.get("name"), "status": sp.get("status"),
            "started": d0.isoformat(), "ended": d_end.isoformat() if d_end else None,
            "bet_days": sp.get("bet_days"), "budget_h": sp.get("time_budget_h"),
            "tasks": tasks, "human_min": human, "agent_min": agent,
        })
    return json_response({"sprints": out}, etag)


@router.get("/api/sprints/{sprint_id}/dossier")
def sprint_dossier(
    sprint_id: str, request: Request, store: ViewStore = Depends(get_store),
) -> Response:
    """One block's full story: the bet and how it ran, the tasks, both
    clocks, the agents that worked it, and — when the project folder is a
    git repo — the commits and lines written inside the window. Everything
    derived on read; whatever cannot be known says so."""
    etag = etag_for(f"sprints:dossier:{sprint_id}", store, "tasks", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    sp = store.query_one("SELECT * FROM sprints_mutual WHERE id = ?", (sprint_id,))
    if sp is None:
        raise not_found("sprint", sprint_id)
    import datetime as _dt
    d0 = _sprint_day(str(sp.get("started_date") or ""))
    if d0 is None:
        raise HTTPException(status_code=409, detail="sprint has no readable started_date")
    ended = _sprint_day(str(sp.get("ended_date") or "")) if str(sp.get("status")) == "ended" else None
    d_end = ended or _dt.date.today()
    ran_days = (d_end - d0).days
    bet = int(sp.get("bet_days") or 0)

    tasks = _member_spans(store, sprint_id, d0)
    task_ids = [t["id"] for t in tasks]
    human_min, agent_min = _sprint_clocks(store, sprint_id, task_ids)

    # The fleet: which agents worked the block's tasks, and how much.
    agents: list[dict] = []
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        agents = store.query(
            f"SELECT s.agent_id, COUNT(DISTINCT s.id) AS sessions_n, "
            f"COALESCE(SUM(s.duration_min), 0) AS minutes, COALESCE(SUM(s.turns_n), 0) AS turns "
            f"FROM sessions s WHERE s.id IN "
            f"(SELECT DISTINCT session_id FROM task_mentions WHERE task_id IN ({ph})) "
            f"GROUP BY s.agent_id ORDER BY minutes DESC", tuple(task_ids),
        )

    # Activity counted inside the window (events are discipline-free).
    events_n = 0
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        ev = store.query(
            f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({ph})", tuple(task_ids),
        )
        events_n = sum(1 for e in ev if (d := _sprint_day(str(e["timestamp"]))) and d0 <= d <= d_end)
    home = str(sp.get("projects") or "").split(",")[0].strip()
    win = (d0.isoformat(), d_end.isoformat())
    scans_n = store.query_one(
        "SELECT COUNT(*) AS n FROM scans_mutual WHERE project = ? AND created_date BETWEEN ? AND ?",
        (home, f"{win[0][2:4]}{win[0][5:7]}-{win[0][8:10]}", f"{win[1][2:4]}{win[1][5:7]}-{win[1][8:10]}"),
    )
    decisions_n = store.query_one(
        "SELECT COUNT(*) AS n FROM decisions_mutual WHERE project = ? AND created_date BETWEEN ? AND ?",
        (home, f"{win[0][2:4]}{win[0][5:7]}-{win[0][8:10]}", f"{win[1][2:4]}{win[1][5:7]}-{win[1][8:10]}"),
    )

    # Git, honestly: only when the registered folder is a repo.
    from ..file_entries import git as run_git, project_repo
    git: dict = {"available": False}
    repo = project_repo(store, home) if home else None
    if repo is not None:
        log = run_git(
            repo, "log", "--numstat", "--pretty=%H",
            f"--since={d0.isoformat()} 00:00", f"--until={d_end.isoformat()} 23:59",
        )
        if log is not None:
            commits = 0
            adds = dels = 0
            files: set = set()
            for line in log.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) == 3:
                    a, d, path = parts
                    if a.isdigit():
                        adds += int(a)
                    if d.isdigit():
                        dels += int(d)
                    files.add(path)
                elif len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                    commits += 1
            git = {
                "available": True, "commits": commits,
                "lines_add": adds, "lines_del": dels, "files_touched": len(files),
                "window": {"from": d0.isoformat(), "to": d_end.isoformat()},
            }

    l2, l3, l4 = read_detail(store.data_root, str(sp.get("md_ref") or ""))
    return json_response({
        "sprint": {
            "id": sp["id"], "name": sp.get("name"), "status": sp.get("status"),
            "started": d0.isoformat(), "ended": ended.isoformat() if ended else None,
            "bet_days": bet, "budget_h": sp.get("time_budget_h"),
            "ran_days": ran_days, "over_days": max(0, ran_days - bet) if bet else 0,
        },
        "tasks": tasks, "human_min": human_min, "agent_min": agent_min,
        "agents": agents, "events_n": events_n,
        "scans_n": int(scans_n["n"]) if scans_n else 0,
        "decisions_n": int(decisions_n["n"]) if decisions_n else 0,
        "git": git, "l2": l2, "l3": l3, "l4": l4,
    }, etag)
