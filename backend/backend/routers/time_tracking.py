"""Manual time tracking — start / pause / resume / stop.

The generic entity routes already provide listing, hand-written entries,
and after-the-fact edits (``/api/time-entries``). What needs its own
endpoints is the *clock*: elapsed time must be computed from server
timestamps, never from a browser's clock, and a running timer must be a
durable row rather than UI state — so closing the tab, reloading, or
restarting the server never loses time.

Shape of an entry:

- running  → ``started_at`` set, ``ended_at`` empty, ``paused_at`` empty
- paused   → ``paused_at`` set (accumulating into ``paused_total_sec``)
- done     → ``ended_at`` set, ``duration_min`` frozen

``share_pct`` is the multiplier for working several projects at once:
attributed minutes = elapsed × share ÷ 100. Changing the share closes the
current entry and opens a fresh one, so every entry keeps one honest rate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ..date_utils import today_yymm_dd
from ..db import ViewStore
from ..entities import ENTITIES
from .. import timeauto
from .deps import create_answer, etag_for, get_store, json_response, maybe_304, not_found, rewrite_one
from .lenses import create_entity

router = APIRouter()

ENT = ENTITIES["time_entry"]

# A timer left running this long is almost certainly forgotten, not worked.
RUNAWAY_HOURS = 8


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def elapsed_seconds(row: dict, now: datetime | None = None) -> int:
    """Worked seconds so far: wall time minus everything spent paused."""
    started = _parse(str(row.get("started_at") or ""))
    if started is None:
        return 0
    ended = _parse(str(row.get("ended_at") or ""))
    paused_at = _parse(str(row.get("paused_at") or ""))
    edge = ended or paused_at or (now or _now())
    gross = int((edge - started).total_seconds())
    return max(0, gross - _int(row.get("paused_total_sec")))


def decorate(row: dict, now: datetime | None = None) -> dict:
    """Add derived state the UI needs but the CSV must not duplicate."""
    ended = str(row.get("ended_at") or "")
    paused = str(row.get("paused_at") or "")
    status = "done" if ended else ("paused" if paused else "running")
    secs = (
        _int(row.get("duration_min")) * 60
        if status == "done"
        else elapsed_seconds(row, now)
    )
    share = _int(row.get("share_pct")) or 100
    return {
        **row,
        "status": status,
        "elapsed_sec": secs,
        "attributed_sec": round(secs * share / 100),
        "runaway": status != "done" and secs > RUNAWAY_HOURS * 3600,
    }


def _load(store: ViewStore, entry_id: str) -> dict:
    row = store.query_one(
        f"SELECT * FROM {ENT.view} WHERE id = ?", (entry_id,)
    )
    if row is None:
        raise not_found("time entry", entry_id)
    return row


def _patch(store: ViewStore, entry_id: str, updates: Any) -> dict:
    """Write columns straight to the CSV row, then rebuild the views.

    ``updates`` is the columns, or a function of the row as it stands under
    the lock that returns them. A clock change is worked out that way: the
    smart timer pauses entries from its own thread, and a stop computed
    from a row read before that pause counted the away stretch as work.
    """
    def change(rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        patch = updates(r) if callable(updates) else updates
        if not patch:
            return False
        r.update(patch)
        return True

    rewrite_one(store, ENT.csv, ENT.columns, entry_id, change, "time entry")
    return decorate(_load(store, entry_id))


@router.post("/api/time/start", status_code=201)
def time_start(
    request: Request,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Open a running entry. Several can run at once — one per block
    (sprint, or the no-sprint bucket) — because working two blocks in
    parallel is exactly what the share multiplier is for. The same block
    cannot be punched twice."""
    project = str(body.get("project") or "").strip()
    if not project:
        raise HTTPException(status_code=422, detail="project is required")

    sprint_key = str(body.get("sprint_id") or "").strip()
    open_rows = store.query(
        f"SELECT * FROM {ENT.view} WHERE project = ? "
        "AND (ended_at IS NULL OR ended_at = '') "
        # The auto-timer's own rows never block a timer you start.
        "AND COALESCE(CAST(source AS VARCHAR), '') <> 'auto' "
        "AND COALESCE(CAST(sprint_id AS VARCHAR), '') = ?",
        (project, sprint_key),
    )
    if open_rows:
        raise HTTPException(
            status_code=409,
            detail=(
                "a timer is already running for this block — stop it first "
                f"({open_rows[0].get('id')})"
            ),
        )

    now = _now()
    share = _int(body.get("share_pct")) or 100
    if not 1 <= share <= 100:
        raise HTTPException(status_code=422, detail="share_pct must be 1-100")

    payload = {
        "created_date": today_yymm_dd(),
        "created_time": now.strftime("%H:%M"),
        "project": project,
        "agent_id": str(body.get("actor") or "operator"),
        "started_at": now.isoformat(),
        "ended_at": "",
        "paused_at": "",
        "paused_total_sec": 0,
        "duration_min": 0,
        "share_pct": share,
        "goal_id": str(body.get("goal_id") or ""),
        "sprint_id": str(body.get("sprint_id") or ""),
        "note": str(body.get("note") or ""),
        "task_id": str(body.get("task_id") or ""),
    }
    created = create_entity(store, ENT, payload)
    return create_answer(decorate(created["metadata"]),
                         existing=bool(created.get("existing")),
                         warnings=created.get("warnings"))


@router.post("/api/time/{entry_id}/pause")
def time_pause(
    entry_id: str, store: ViewStore = Depends(get_store)
) -> dict:
    """Hold the clock without closing the entry."""
    _load(store, entry_id)

    def pause(r: dict) -> dict:
        if str(r.get("ended_at") or ""):
            raise HTTPException(status_code=409, detail="entry is already stopped")
        if str(r.get("paused_at") or ""):
            return {}  # already paused — idempotent
        return {"paused_at": _now().isoformat()}

    return _patch(store, entry_id, pause)


@router.post("/api/time/{entry_id}/resume")
def time_resume(
    entry_id: str, store: ViewStore = Depends(get_store)
) -> dict:
    """Bank the paused stretch and start counting again."""
    row = _load(store, entry_id)
    return time_resume_row(store, row, _now(), refuse_stopped=True)


def time_resume_row(store: ViewStore, row: dict, now: datetime, *, refuse_stopped: bool = False) -> dict:
    """Bank the paused stretch of the entry up to `now` and run again."""

    def resume(r: dict) -> dict:
        if refuse_stopped and str(r.get("ended_at") or ""):
            raise HTTPException(status_code=409, detail="entry is already stopped")
        paused_at = _parse(str(r.get("paused_at") or ""))
        if paused_at is None:
            return {}  # not paused — idempotent
        banked = _int(r.get("paused_total_sec")) + max(
            0, int((now - paused_at).total_seconds())
        )
        return {"paused_at": "", "paused_total_sec": str(banked)}

    return _patch(store, str(row["id"]), resume)


@router.post("/api/time/{entry_id}/stop")
def time_stop(
    entry_id: str,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Close the entry and freeze its duration."""
    _load(store, entry_id)
    now = _now()

    def stop(r: dict) -> dict:
        if str(r.get("ended_at") or ""):
            raise HTTPException(status_code=409, detail="entry is already stopped")
        # A pause that was never resumed still counts as paused time.
        paused_at = _parse(str(r.get("paused_at") or ""))
        banked = _int(r.get("paused_total_sec"))
        if paused_at is not None:
            banked += max(0, int((now - paused_at).total_seconds()))
        updates = {
            "ended_at": now.isoformat(),
            "paused_at": "",
            "paused_total_sec": str(banked),
        }
        secs = elapsed_seconds({**r, **updates}, now)
        updates["duration_min"] = str(max(0, round(secs / 60)))
        note = body.get("note")
        if note is not None:
            updates["note"] = str(note)
        return updates

    return _patch(store, entry_id, stop)


@router.get("/api/time/running")
def time_running(
    request: Request, store: ViewStore = Depends(get_store)
) -> Response:
    """Every open timer, across all projects — the global "still ticking" view."""
    etag = etag_for("time:running", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        f"SELECT * FROM {ENT.view} WHERE ended_at IS NULL OR ended_at = '' "
        "ORDER BY started_at ASC"
    )
    now = _now()
    return json_response(
        {"total": len(rows), "running": [decorate(r, now) for r in rows]}, etag
    )


@router.get("/api/time/summary")
def time_summary(
    request: Request,
    project: str = "",
    task_id: str = "",
    store: ViewStore = Depends(get_store),
) -> Response:
    """Attributed minutes for today, the last 7 days, and per goal — of a
    project, of one task (``task_id``), or of everything."""
    etag = etag_for(f"time:summary:{project}:{task_id}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    where, params = [], []
    if project:
        where.append("project = ?")
        params.append(project)
    if task_id:
        where.append("CAST(task_id AS VARCHAR) = ?")
        params.append(task_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = store.query(f"SELECT * FROM {ENT.view} {clause}", params)

    now = _now()
    today = today_yymm_dd()
    per_goal: dict[str, int] = {}
    today_sec = week_sec = total_sec = 0
    for row in rows:
        d = decorate(row, now)
        attributed = int(d["attributed_sec"])
        total_sec += attributed
        started = _parse(str(row.get("started_at") or ""))
        if started and (now - started).days < 7:
            week_sec += attributed
        if str(row.get("created_date") or "") == today:
            today_sec += attributed
        gid = str(row.get("goal_id") or "")
        if gid:
            per_goal[gid] = per_goal.get(gid, 0) + attributed

    return json_response(
        {
            "project": project,
            "task_id": task_id,
            "today_min": round(today_sec / 60),
            "week_min": round(week_sec / 60),
            "total_min": round(total_sec / 60),
            "per_goal_min": {k: round(v / 60) for k, v in per_goal.items()},
        },
        etag,
    )


@router.post("/api/time/{entry_id}/delete", status_code=200)
def time_delete(
    entry_id: str, store: ViewStore = Depends(get_store)
) -> dict:
    """Remove an entry outright — mistyped, duplicated, or never worked."""
    _delete(store, entry_id)
    return {"deleted": entry_id}


def _delete(store: ViewStore, entry_id: str) -> None:
    def drop(rows: list[dict[str, str]], _row: dict[str, str]) -> bool:
        rows[:] = [r for r in rows if r.get("id") != entry_id]
        return True

    rewrite_one(store, ENT.csv, ENT.columns, entry_id, drop, "time entry")


# ---------------------------------------------------------------------------
# The smart timer (timeauto.py): away, working, and each project's mode
# ---------------------------------------------------------------------------


@router.get("/api/time/auto")
def time_auto(request: Request) -> dict:
    """What the smart timer sees: idle time and where it is read from, each
    project's mode, the auto spans running now, and the away notices."""
    return timeauto.of(request.app).status()


@router.post("/api/time/auto/beat")
def time_auto_beat(request: Request, body: dict = Body(...)) -> dict:
    """A page says: someone is working on this project (and this task) now."""
    project = str(body.get("project") or "").strip()
    if not project:
        raise HTTPException(status_code=422, detail="project is required")
    timeauto.of(request.app).beat(project, str(body.get("task_id") or ""), "page")
    return {"ok": True}


@router.post("/api/time/auto/mode")
def time_auto_mode(request: Request, body: dict = Body(...)) -> dict:
    """A project's timer: remind, auto or manual."""
    project = str(body.get("project") or "").strip()
    if not project:
        raise HTTPException(status_code=422, detail="project is required")
    timer = timeauto.of(request.app)
    timer.set_mode(project, str(body.get("mode") or ""))
    return {"project": project, "mode": timer.mode_of(project)}


@router.post("/api/time/auto/away/{entry_id}")
def time_auto_away(
    entry_id: str,
    request: Request,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Answer an away notice. ``count``: the away stretch counts after all
    (taken back out of the entry's paused time); ``resume``: a long absence
    goes on from now; ``stop``: it ends where you left; ``dismiss``: as is."""
    action = str(body.get("action") or "dismiss")
    note = timeauto.of(request.app).dismiss(entry_id)
    if note is None:
        raise HTTPException(status_code=404, detail="no away notice for this entry")
    row = _load(store, entry_id)
    if action == "count":
        if note.get("long"):
            row = time_resume_row(store, row, _now())
        away_sec = _int(note.get("sec"))
        return _patch(store, entry_id, lambda r: {
            "paused_total_sec": str(max(0, _int(r.get("paused_total_sec")) - away_sec)),
        })
    if action == "resume":
        return time_resume_row(store, row, _now())
    if action == "stop" and not str(row.get("ended_at") or ""):
        # Ends where you left: the pause up to now is not work.
        return time_stop(entry_id, {}, store)
    return decorate(row)
