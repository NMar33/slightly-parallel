"""Cross-entity read endpoints: health, snapshot, project, agent, chat,
search, timeline, heatmap."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import app_settings
from ..date_utils import format_yymm_dd
from ..db import ViewStore
from ..entities import DONE_STATUSES
from ..file_safety import acquire_flock, atomic_write_json
from ..models import (
    Activity,
    LoadError,
    Capabilities,
    Agent,
    AgentDetail,
    ChatSlice,
    Decision,
    HealthResponse,
    HeatmapCell,
    HeatmapResponse,
    KPIStrip,
    ProjectBundle,
    ProjectSummary,
    SearchResults,
    SnapshotResponse,
    TaskBrief,
    TimelineEvent,
    TimelineResponse,
)
from .deps import (
    not_found,
    DONE_SQL,
    clean_agent,
    etag_for,
    get_store,
    json_response,
    maybe_304,
    rows_as,
    scalar,
    to_int,
)

log = logging.getLogger("sp.core")
router = APIRouter()

# A task is open while it is neither done nor archived; "in play" orders
# the open ones the way an operator scans a board — what is moving first.
_DONE_STATUSES = DONE_STATUSES
_DONE_SQL = DONE_SQL  # the one list of done statuses, spelled for SQL (deps)
_OPEN_TASK_SQL = (
    f"LOWER(COALESCE(status, '')) NOT IN {_DONE_SQL} "
    "AND COALESCE(archived_at, '') = ''"
)
_STATUS_RANK = {
    "doing": 0, "review": 1, "next": 2, "todo": 3, "agent": 4,
    "review-later": 5, "unclassified": 6, "backlog": 7, "parked": 8,
}


def _terminal_on(app) -> bool:
    from .terminal import SUPPORTED, enabled
    return SUPPORTED and enabled(app)


def _task_brief(r: dict) -> TaskBrief:
    return TaskBrief(
        id=str(r.get("id") or ""),
        project=str(r.get("project") or ""),
        title=str(r.get("title") or ""),
        status=str(r.get("status") or ""),
        priority=str(r.get("priority") or ""),
        sprint_id=str(r.get("sprint_id") or ""),
        created_date=str(r.get("created_date") or ""),
        agent_id=str(r.get("agent_id") or ""),
    )


def _in_play_key(r: dict) -> tuple:
    rank = _STATUS_RANK.get(str(r.get("status") or "").lower(), 9)
    return (rank, str(r.get("created_date") or ""), str(r.get("created_time") or ""))


def _open_tasks(store: ViewStore, project: str | None = None) -> list[dict]:
    """Open tasks, the ones in play first, newest first within a status."""
    where = _OPEN_TASK_SQL
    params: tuple = ()
    if project is not None:
        where += " AND project = ?"
        params = (project,)
    rows = store.query(f"SELECT * FROM tasks_mutual WHERE {where}", params)
    # Newest first, then a stable sort by status rank keeps that order
    # inside each status.
    rows.sort(key=lambda r: _in_play_key(r)[1:], reverse=True)
    rows.sort(key=lambda r: _in_play_key(r)[0])
    return rows


def _tasks_done_since(store: ViewStore, since_iso: str) -> dict[str, set[str]]:
    """project -> ids of tasks that entered done on/after `since_iso`
    (from the event log) and are still done."""
    events = store.query(
        "SELECT task_id FROM task_events_mutual WHERE field = 'status' "
        f"AND LOWER(COALESCE(new_value, '')) IN {_DONE_SQL} "
        "AND timestamp >= ?",
        (since_iso,),
    )
    ids = {str(e.get("task_id") or "") for e in events}
    out: dict[str, set[str]] = {}
    if not ids:
        return out
    ph = ",".join("?" * len(ids))
    for r in store.query(
        f"SELECT id, project, status FROM tasks_mutual WHERE id IN ({ph})",
        tuple(ids),
    ):
        if str(r.get("status") or "").lower() in _DONE_STATUSES:
            out.setdefault(str(r.get("project") or ""), set()).add(str(r["id"]))
    return out


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")


def _yymmdd_offset(days: int) -> str:
    """Today+days in the canonical YYMM-DD format."""
    return format_yymm_dd(date.today() + timedelta(days=days))


def _pick_headline(agents: list[dict[str, Any]]) -> str:
    """Newest agent's l1_headline (or empty)."""
    latest, latest_ts = "", ""
    for a in agents:
        h = a.get("l1_headline") or ""
        ts = a.get("last_active") or a.get("created_date") or ""
        if h and ts > latest_ts:
            latest, latest_ts = h, ts
    return latest


@router.get("/api/health", response_model=HealthResponse)
def health(store: ViewStore = Depends(get_store)) -> HealthResponse:
    fs_mtime = store.view_mtime
    view_age_ms = int((time.time() - fs_mtime) * 1000) if fs_mtime else 0
    errors = list(getattr(store, "load_errors", []))
    return HealthResponse(
        ok=True,
        degraded=bool(errors),
        load_errors=[LoadError(**e) for e in errors],
        fs_mtime=fs_mtime,
        stamps=store.stamps,
        view_age_ms=max(view_age_ms, 0),
        projects=len(store.projects),
        agents=len(store.agents()),
        data_root=str(store.data_root),
    )


@router.get("/api/snapshot", response_model=SnapshotResponse)
def snapshot(
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for("snapshot", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    prefs = app_settings.load(store.data_root)
    agents = store.agents()
    done_7d = _tasks_done_since(store, _iso_days_ago(7))

    # One grouped query per number, not six queries per project: the
    # sidebar asks for this every 20 s and on every change.
    def by_project(sql: str, params: tuple = ()) -> dict[str, Any]:
        return {str(r.get("project") or ""): r.get("n") for r in store.query(sql, params)}

    open_by = by_project(
        f"SELECT project, COUNT(*) AS n FROM tasks_mutual WHERE {_OPEN_TASK_SQL} GROUP BY project"
    )
    total_by = by_project(
        "SELECT project, COUNT(*) AS n FROM tasks_mutual "
        "WHERE COALESCE(archived_at, '') = '' GROUP BY project"
    )
    dec_by = by_project(
        "SELECT project, COUNT(*) AS n FROM decisions_mutual WHERE created_date >= ? GROUP BY project",
        (_yymmdd_offset(-7),),
    )
    # Hours are the agents' working time, not the sessions' wall clock.
    mins_by = by_project(
        "SELECT project, COALESCE(SUM(agent_min), 0) AS n FROM time_blocks "
        "WHERE created_date >= ? GROUP BY project",
        (_yymmdd_offset(-30),),
    )
    last_by = by_project("SELECT project, MAX(created_date) AS n FROM time_blocks GROUP BY project")

    summaries: list[ProjectSummary] = []
    total_open_tasks = 0
    total_done_7d = 0
    total_dec_7d = 0
    total_hours_30d = 0.0
    for pf in store.projects:
        open_tasks = _int(open_by.get(pf.code) or 0)
        tasks_total = _int(total_by.get(pf.code) or 0)
        tasks_done_7d = len(done_7d.get(pf.code, ()))
        dec_7d = _int(dec_by.get(pf.code) or 0)
        mins_30d = _int(mins_by.get(pf.code) or 0)
        last_act = str(last_by.get(pf.code) or "")
        proj_agents = [a for a in agents if a.get("project") == pf.code]
        summaries.append(
            ProjectSummary(
                code=pf.code,
                name=pf.code,
                l1_headline=_pick_headline(proj_agents),
                open_tasks=open_tasks,
                tasks_total=tasks_total,
                tasks_done_7d=tasks_done_7d,
                decisions_7d=dec_7d,
                est_hours_30d=round(mins_30d / 60.0, 1),
                active_agents=len(proj_agents),
                last_activity=last_act,
            )
        )
        total_open_tasks += open_tasks
        total_done_7d += tasks_done_7d
        total_dec_7d += dec_7d
        total_hours_30d += mins_30d / 60.0

    recent = rows_as(Activity, store.query(
        "SELECT * FROM time_blocks ORDER BY created_date DESC, start_time DESC LIMIT ?",
        (prefs["overview.recent_activity_limit"],),
    ), source="snapshot.recent_activity")
    open_task_rows = _open_tasks(store)[: int(prefs["overview.open_tasks_limit"])]
    recent_decisions_rows = store.query(
        "SELECT * FROM decisions_mutual WHERE created_date >= ? "
        "ORDER BY created_date DESC LIMIT ?",
        (_yymmdd_offset(-30), prefs["overview.recent_decisions_limit"]),
    )

    payload = SnapshotResponse(
        view_mtime=store.view_mtime,
        capabilities=Capabilities(
            # The same answer /api/terminal/state gives: the env flag OR the
            # Settings switch (the project's Terminals tab reads this).
            terminal_enabled=_terminal_on(request.app),
        ),
        kpi=KPIStrip(
            projects=len(store.projects),
            agents=len(agents),
            open_tasks=total_open_tasks,
            tasks_done_7d=total_done_7d,
            decisions_7d=total_dec_7d,
            est_hours_30d=round(total_hours_30d, 1),
        ),
        projects=summaries,
        recent_activity=recent,
        open_tasks=[_task_brief(r) for r in open_task_rows],
        recent_decisions=rows_as(
            Decision, recent_decisions_rows, source="snapshot.recent_decisions"
        ),
        agents=rows_as(Agent, agents, source="snapshot.agents", prepare=clean_agent),
    )
    return json_response(payload, etag)


@router.get("/api/projects/folders")
def project_folders(store: ViewStore = Depends(get_store)) -> dict:
    """Each project's working folder on this machine, and the data root.

    The pages show a path the way the agent wrote it, relative to the
    project folder, because that is how the agent reads it. A path copied
    out of a page is pasted into a terminal or an editor, where only an
    absolute path works — so every Copy path joins the folder to the
    relative path (frontend ``lib/paths.ts``). One reading of the folders
    for every page that copies a path.
    """
    from ..csvio import read_rows

    folders: dict[str, str] = {}
    for row in read_rows(store.data_root / "integrations.csv"):
        code = str(row.get("project") or "").strip()
        path = str(row.get("path") or "").strip()
        if code and path and code not in folders:
            folders[code] = str(Path(path).expanduser())
    return {"folders": folders, "data_root": str(store.data_root)}


@router.get("/api/project/{code}", response_model=ProjectBundle)
def project(
    code: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"project:{code}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    if not any(pf.code == code for pf in store.projects):
        # Graceful: an empty bundle lets the UI render an empty state.
        empty = ProjectBundle(
            code=code, summary=ProjectSummary(code=code, name=code)
        )
        return json_response(empty, etag)

    decisions = rows_as(Decision, store.query(
        "SELECT * FROM decisions_mutual WHERE project=? ORDER BY created_date DESC",
        (code,),
    ), source=f"project:{code}.decisions")
    activity = rows_as(Activity, store.query(
        "SELECT * FROM time_blocks WHERE project=? "
        "ORDER BY created_date DESC LIMIT 500",
        (code,),
    ), source=f"project:{code}.activity")
    agents = rows_as(
        Agent, [a for a in store.agents() if a.get("project") == code],
        source=f"project:{code}.agents", prepare=clean_agent,
    )

    open_tasks = _int(scalar(
        store,
        f"SELECT COUNT(*) AS n FROM tasks_mutual WHERE project=? AND {_OPEN_TASK_SQL}",
        (code,),
    ))
    tasks_total = _int(scalar(
        store,
        "SELECT COUNT(*) AS n FROM tasks_mutual WHERE project=? "
        "AND COALESCE(archived_at, '') = ''",
        (code,),
    ))
    tasks_done_7d = len(_tasks_done_since(store, _iso_days_ago(7)).get(code, ()))
    dec_7d = sum(1 for d in decisions if d.created_date >= _yymmdd_offset(-7))
    mins_30d = sum(
        (a.agent_min if a.agent_min is not None else a.duration_min or 0)
        for a in activity
        if a.created_date >= _yymmdd_offset(-30)
    )
    summary = ProjectSummary(
        code=code,
        name=code,
        l1_headline=_pick_headline(
            [a for a in store.agents() if a.get("project") == code]
        ),
        open_tasks=open_tasks,
        tasks_total=tasks_total,
        tasks_done_7d=tasks_done_7d,
        decisions_7d=dec_7d,
        est_hours_30d=round(mins_30d / 60.0, 1),
        active_agents=len(agents),
        last_activity=activity[0].created_date if activity else "",
    )
    payload = ProjectBundle(
        code=code,
        summary=summary,
        decisions=decisions,
        activity=activity,
        agents=agents,
    )
    return json_response(payload, etag)


@router.get("/api/agent/{agent_id}", response_model=AgentDetail)
def agent(
    agent_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"agent:{agent_id}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    raw = next(
        (a for a in store.agents() if a.get("agent_id") == agent_id), None
    )
    if raw is None:
        raise not_found("agent", agent_id)

    chat_path = Path(raw.get("_chat_path", ""))
    chat_lines = 0
    if chat_path.exists():
        try:
            with open(chat_path, encoding="utf-8", errors="replace") as fh:
                chat_lines = sum(1 for _ in fh)
        except OSError:
            chat_lines = 0

    decisions = rows_as(Decision, store.query(
        "SELECT * FROM decisions_mutual WHERE agent_id=? ORDER BY created_date DESC",
        (agent_id,),
    ), source=f"agent:{agent_id}.decisions")
    payload = AgentDetail(
        agent=Agent(**clean_agent(raw)),
        chat_lines=chat_lines,
        chat_available=chat_path.exists(),
        decisions=decisions,
    )
    return json_response(payload, etag)


_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _parse_range(spec: str | None, default: tuple[int, int]) -> tuple[int, int]:
    if not spec:
        return default
    m = _RANGE_RE.match(spec)
    if not m:
        return default
    a, b = int(m.group(1)), int(m.group(2))
    return (b, a) if a > b else (a, b)


@router.get("/api/chat/{agent_id}", response_model=ChatSlice)
def chat(
    agent_id: str,
    range: str | None = Query(
        None, description="line range a-b (1-indexed, inclusive)"
    ),
    store: ViewStore = Depends(get_store),
) -> ChatSlice:
    raw = next(
        (a for a in store.agents() if a.get("agent_id") == agent_id), None
    )
    if raw is None:
        raise not_found("agent", agent_id)
    chat_path = Path(raw.get("_chat_path", ""))
    if not chat_path.exists():
        return ChatSlice(agent_id=agent_id, start=0, end=0, total_lines=0)

    start, end = _parse_range(range, default=(1, 200))
    s = max(1, start)
    # One pass: the lines asked for are kept, the rest only counted. The
    # whole transcript used to be held in memory for a 200-line slice.
    lines: list[str] = []
    total = 0
    try:
        with open(chat_path, encoding="utf-8", errors="replace") as fh:
            for total, ln in enumerate(fh, start=1):
                if s <= total <= end:
                    lines.append(ln.rstrip("\n"))
    except OSError:
        return ChatSlice(agent_id=agent_id, start=0, end=0, total_lines=0)
    e = min(total, end)
    return ChatSlice(
        agent_id=agent_id,
        start=s if total else 0,
        end=e if total else 0,
        total_lines=total,
        lines=lines,
    )


@router.get("/api/search", response_model=SearchResults)
def search(
    q: str = Query("", min_length=0),
    types: str = Query(""),
    limit: int = Query(40, ge=1, le=1000),
    store: ViewStore = Depends(get_store),
) -> SearchResults:
    """Everything, by one word (searchlib.py).

    `types` names the kinds to look in — the entity names, plus `scan`,
    `agent` and `turn` (one captured chat turn, with who said it and when) —
    and empty means all of them. `counts` and `total` are over every match;
    `hits` is the first `limit` of them, the line the match sits on
    included. `tasks`, `decisions` and `agents` stay as they were, for the
    box in the top bar.
    """
    from .. import searchlib

    q_norm = q.strip()
    result = SearchResults(query=q_norm)
    if not q_norm:
        return result

    # `types=tasks` and `types=task` mean the same kind: the pages ask in the
    # plural, the index is keyed by the entity's own singular name.
    kinds = {t.strip().rstrip("s") for t in types.split(",") if t.strip()} or None
    hits = searchlib.search(store, q_norm, kinds)
    result.total = len(hits)
    result.counts = searchlib.counts(hits)          # over every match, not the page
    result.hits = [h.as_dict() for h in hits[:limit]]

    # The three the top bar has always shown, from the same one search.
    by_kind: dict[str, list[str]] = {}
    for h in hits:
        by_kind.setdefault(h.kind, []).append(h.id)

    def rows_of(view: str, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        order = {rid: n for n, rid in enumerate(ids)}
        got = store.query(
            f"SELECT * FROM {view} WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)
        )
        return sorted(got, key=lambda r: order.get(str(r.get("id") or ""), 99))

    result.tasks = [
        _task_brief(r) for r in rows_of("tasks_mutual", by_kind.get("task", [])[:limit])
        if not str(r.get("archived_at") or "")
    ]
    result.decisions = rows_as(
        Decision, rows_of("decisions_mutual", by_kind.get("decision", [])[:limit]),
        source="search.decisions",
    )
    agent_ids = set(by_kind.get("agent", [])[:limit])
    result.agents = rows_as(
        Agent, [a for a in store.agents() if str(a.get("agent_id") or "") in agent_ids],
        source="search.agents", prepare=clean_agent,
    )
    return result


@router.get("/api/search/overview")
def search_overview(
    q: str = Query(""),
    types: str = Query(""),
    store: ViewStore = Depends(get_store),
) -> dict:
    """What is in the index — as a whole, or around one word.

    A search page with no query is a blank page, and everything worth
    showing there is already in the index: the words that come up most, how
    much was said on each day, how long a turn runs, which chats carry the
    weight. Counted once when the index is built (`searchlib.overview`), so
    the page costs a lookup. With `q`, the same shape over the rows that
    match, plus `near` — the words that keep this one company, ranked by how
    much more often they sit beside it than anywhere else.
    """
    from .. import searchlib

    kinds = {t.strip().rstrip("s") for t in types.split(",") if t.strip()} or None
    return searchlib.overview(store, q, kinds)


@router.get("/api/timeline", response_model=TimelineResponse)
def timeline(
    request: Request,
    project: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"timeline:{project}:{from_}:{to}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    agents = store.agents()
    if project:
        agents = [a for a in agents if a.get("project") == project]

    sql_parts = ["SELECT * FROM time_blocks WHERE 1=1"]
    params: list[Any] = []
    if project:
        sql_parts.append("AND project = ?")
        params.append(project)
    if from_:
        sql_parts.append("AND created_date >= ?")
        params.append(from_)
    if to:
        sql_parts.append("AND created_date <= ?")
        params.append(to)
    sql_parts.append("ORDER BY created_date")
    rows = store.query(" ".join(sql_parts), tuple(params))

    by_agent: dict[str, list[Activity]] = {}
    for act in rows_as(Activity, rows, source="timeline.activity"):
        by_agent.setdefault(act.agent_id, []).append(act)

    lanes = [
        TimelineEvent(
            agent_id=a.get("agent_id", ""),
            agent_name=a.get("agent_name", "") or a.get("agent_id", ""),
            chat_title=str(a.get("chat_title") or ""),
            project=a.get("project", "") or "",
            parent_agent_id=a.get("parent_agent_id"),
            created_date=a.get("created_date", "") or "",
            last_active=a.get("last_active", "") or "",
            activities=by_agent.get(a.get("agent_id", ""), []),
        )
        for a in agents
    ]
    lanes.sort(key=lambda e: (e.created_date or "", e.agent_id))
    return json_response(
        TimelineResponse(project=project, from_date=from_, to_date=to, lanes=lanes),
        etag,
    )


@router.get("/api/heatmap", response_model=HeatmapResponse)
def heatmap(
    request: Request,
    project: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Files × dates × touch-count, attributed via meta.json.files_touched."""
    etag = etag_for(f"heatmap:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    cells: dict[tuple[str, str], int] = {}
    for a in store.agents():
        if project and a.get("project") != project:
            continue
        last_active = a.get("last_active") or ""
        day = last_active[:7] or (a.get("created_date") or "")
        files = a.get("files_touched")
        if not isinstance(files, list):
            continue
        for f in files:
            key = (str(f), day)
            cells[key] = cells.get(key, 0) + 1

    payload = HeatmapResponse(
        project=project,
        cells=[
            HeatmapCell(file=f, date=d, touches=n)
            for (f, d), n in sorted(cells.items())
        ],
    )
    return json_response(payload, etag)


_int = to_int  # a whole number out of a query value (deps)


@router.post("/api/agents/{agent_id}/rename")
def rename_agent(
    agent_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Set an agent's display name (``agent_name`` in its meta.json).

    The id stays the immutable key — every entry, session, and filter
    references it — so a rename is pure presentation and can never orphan
    history. Duplicate names are allowed; the id disambiguates.
    """
    name = str(body.get("name") or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(
            status_code=422, detail="name must be 1-80 characters"
        )
    raw = next(
        (a for a in store.agents() if a.get("agent_id") == agent_id), None
    )
    if raw is None:
        raise not_found("agent", agent_id)

    meta_path = Path(raw.get("_chat_path", "")).parent / "meta.json"
    # Under the sidecar lock the capture hook takes for its own writes, so a
    # rename landing mid-turn cannot revert pending_turn and drop a reply.
    with acquire_flock(meta_path.with_name("meta.json.lock")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"cannot read meta.json: {exc}")
        meta["agent_name"] = name
        atomic_write_json(meta_path, meta)
    store.rebuild()
    return {"agent_id": agent_id, "agent_name": name}
