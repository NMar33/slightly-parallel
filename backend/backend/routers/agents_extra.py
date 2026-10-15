"""Agents beyond the lane: the profile, the group, and the links between them.

Everything an agent leaves behind is already on disk under its id — the
captured chat (sessions), the scans it posted, its file and architecture
entries, its decisions, the tasks named in its turns. The
profile endpoint is the join: one read, every count, so a page can be
presentation only.

Two things here are written, both by the operator, never by agents:

* ``agent_group`` — several lanes that are one piece of work; lives in the
  agent's meta.json next to ``agent_name`` (the id stays the key).
* ``agent_links.csv`` — a drawn connection between two lanes with a kind
  (why), a style (how the line looks) and a note (what the dot says).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from ..csvio import append_if_absent, read_rows
from ..db import ViewStore
from ..entities import (
    DONE_STATUSES,
    AGENT_LINK_COLUMNS,
    AGENT_LINK_DEFAULT_STYLE,
    AGENT_LINK_KINDS,
    AGENT_LINK_STYLES,
)
from ..file_safety import acquire_flock, atomic_write_json
from .deps import (
    not_found,
    clean_agent, create_answer, etag_for, get_store, json_response, maybe_304,
    rewrite_one, rows_or_empty, to_int,
)

router = APIRouter()

_DEFAULT_ACTOR = "operator"
_DONE = DONE_STATUSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_agent(store: ViewStore, agent_id: str) -> dict[str, Any]:
    raw = next((a for a in store.agents() if a.get("agent_id") == agent_id), None)
    if raw is None:
        raise not_found("agent", agent_id)
    return raw


def _brief(a: dict[str, Any]) -> dict[str, Any]:
    """The few fields another agent's row needs when it is only referenced."""
    return {
        "agent_id": a.get("agent_id", ""),
        "agent_name": a.get("agent_name", ""),
        "chat_title": a.get("chat_title", ""),
        "agent_group": a.get("agent_group", ""),
        "created_date": a.get("created_date", ""),
        "last_active": a.get("last_active", ""),
    }


def _link_id(frm: str, to: str, kind: str) -> str:
    return "al_" + hashlib.sha256(f"{frm}|{to}|{kind}".encode()).hexdigest()[:8]


def _links_csv(store: ViewStore) -> Path:
    return store.data_root / "agent_links.csv"


def _resolve_links(store: ViewStore, rows: list[dict]) -> list[dict]:
    by_id = {a.get("agent_id"): a for a in store.agents()}
    out = []
    for r in rows:
        # An empty CSV cell reads back as NULL from the view; the contract
        # for text columns is "", so a page never meets null in a note.
        r = {k: ("" if v is None else v) for k, v in r.items()}
        out.append({
            **r,
            "from": _brief(by_id.get(r.get("from_id"), {"agent_id": r.get("from_id", "")})),
            "to": _brief(by_id.get(r.get("to_id"), {"agent_id": r.get("to_id", "")})),
        })
    return out


_int = to_int  # a whole number out of a query value (deps)


# ---------------------------------------------------------------------------
# Profile — the join
# ---------------------------------------------------------------------------


# What a profile reads, one query per table for however many agents: the
# roster asked each of these once per agent — twelve queries an agent, and
# a hundred agents is a project. ``{ph}`` takes the ids; ``_aid`` says whose
# row it is and is taken off before the row is answered.
_PROFILE_SQL: dict[str, str] = {
    "sessions": (
        "SELECT agent_id AS _aid, id, created_date, start_time, end_time, duration_min, agent_min, "
        "waiting_min, helper_min, timed, turns_n, l1, turns_json "
        "FROM sessions WHERE agent_id IN ({ph}) ORDER BY created_date ASC, start_time ASC"
    ),
    "scans": (
        "SELECT agent_id AS _aid, id, created_date, created_time, l1, files_n, lines_add, lines_del, "
        "decisions_n, scope FROM scans_mutual WHERE agent_id IN ({ph}) "
        "ORDER BY created_date DESC, created_time DESC"
    ),
    "files": (
        "SELECT agent_id AS _aid, id, created_date, created_time, l1, files_important_n, files_ignored_n, "
        "trigger_id FROM files_mutual WHERE agent_id IN ({ph}) ORDER BY created_date DESC, created_time DESC"
    ),
    "decisions": (
        "SELECT agent_id AS _aid, id, created_date, created_time, decision_text, rationale, source, "
        "related_goal_id FROM decisions_mutual WHERE agent_id IN ({ph}) ORDER BY created_date DESC"
    ),
    "architecture": (
        "SELECT agent_id AS _aid, id, created_date, created_time, name AS l1, op, "
        "\"type\" AS kind, task, trigger_id FROM architecture_mutual "
        "WHERE agent_id IN ({ph}) AND op != 'check' "
        "ORDER BY created_date DESC, created_time DESC"
    ),
    "problems": (
        "SELECT agent_id AS _aid, id, created_date, created_time, l1, severity, status, resolved_date "
        "FROM problems_mutual WHERE agent_id IN ({ph}) ORDER BY created_date DESC, created_time DESC"
    ),
    "rules": (
        "SELECT agent_id AS _aid, id, created_date, l1, kind, severity, status FROM rules_mutual "
        "WHERE agent_id IN ({ph}) ORDER BY created_date DESC"
    ),
    "standups": "SELECT agent_id AS _aid, id FROM standups_mutual WHERE agent_id IN ({ph})",
    # Tasks — from the captured turns: handed (the user named it) and
    # replied (the agent named it). "Done" is the task's status now; the
    # board does not record who closed it, so this is attribution by
    # involvement, said so in the UI.
    "mentions": (
        "SELECT m.agent_id AS _aid, m.task_id, COALESCE(t.title, '') AS title, COALESCE(t.status, '') AS status, "
        "MIN(m.at_ts) AS first_at, MAX(m.at_ts) AS last_at, "
        "SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) AS handed_n, "
        "SUM(CASE WHEN m.role = 'agent' THEN 1 ELSE 0 END) AS replied_n, "
        "MAX(COALESCE(m.task_turn, 0)) AS turn_max "
        "FROM task_mentions m JOIN tasks_mutual t ON t.id = m.task_id "
        "WHERE m.agent_id IN ({ph}) GROUP BY m.agent_id, m.task_id, t.title, t.status ORDER BY first_at ASC"
    ),
}
_LINKS_SQL = (
    "SELECT id, project, from_id, to_id, kind, style, note, from_at, to_at, "
    "created_at, actor FROM agent_links_mutual WHERE from_id IN ({ph}) OR to_id IN ({ph}) "
    "ORDER BY created_at ASC"
)


def profile_rows(store: ViewStore, agent_ids: list[str]) -> dict[str, dict[str, list[dict]]]:
    """Every table a profile reads, for these agents: ``{table: {agent_id: rows}}``,
    each agent's rows in the order its own query gave them."""
    ids = [a for a in dict.fromkeys(agent_ids) if a]
    out: dict[str, dict[str, list[dict]]] = {name: {} for name in (*_PROFILE_SQL, "links")}
    if not ids:
        return out
    ph = ",".join("?" * len(ids))
    for name, sql in _PROFILE_SQL.items():
        for r in rows_or_empty(store, sql.format(ph=ph), tuple(ids)):
            out[name].setdefault(str(r.pop("_aid") or ""), []).append(r)
    wanted = set(ids)
    for r in rows_or_empty(store, _LINKS_SQL.format(ph=ph), tuple(ids) * 2):
        for end in {str(r.get("from_id") or ""), str(r.get("to_id") or "")} & wanted:
            out["links"].setdefault(end, []).append(r)
    return out


def build_profile(
    store: ViewStore, raw: dict[str, Any],
    pre: dict[str, dict[str, list[dict]]] | None = None,
) -> dict[str, Any]:
    """One agent's profile. ``pre`` is ``profile_rows`` for a whole roster,
    read once by the caller; without it this agent's rows are read here."""
    aid = str(raw.get("agent_id") or "")
    agents = store.agents()
    got = pre if pre is not None else profile_rows(store, [aid])

    def mine(table: str) -> list[dict]:
        return got.get(table, {}).get(aid, [])

    sessions = mine("sessions")
    by_day, by_hour = _rhythm(sessions)
    session_rows = [{k: v for k, v in s.items() if k != "turns_json"} for s in sessions]
    architecture = mine("architecture")
    tasks = _profile_tasks(mine("mentions"))
    links = _resolve_links(store, mine("links"))
    parent = next((a for a in agents if a.get("agent_id") == raw.get("parent_agent_id")), None)
    children = [a for a in agents if a.get("parent_agent_id") == aid]
    group = str(raw.get("agent_group") or "")
    members = [
        _brief(a) for a in agents
        if group and a.get("agent_group") == group and a.get("project") == raw.get("project")
        and a.get("agent_id") != aid
    ]
    return {
        "agent": clean_agent(raw),
        "origin": {
            "tool": raw.get("tool") or "",
            "cwd": raw.get("cwd") or "",
            "session_ref": raw.get("session_ref") or "",
            "capture": raw.get("capture") or "",
            "chat_path": raw.get("_chat_path") or "",
        },
        "totals": _profile_totals(mine, sessions, by_day, tasks, links),
        "by_day": [
            {"date": d, **v} for d, v in sorted(by_day.items())
        ],
        "by_hour": by_hour,
        "architecture_kinds": dict(Counter(str(a.get("kind") or "") for a in architecture)),
        "sessions": session_rows,
        "scans": mine("scans"),
        "files": mine("files"),
        "decisions": mine("decisions"),
        "architecture": architecture,
        "problems": mine("problems"),
        "rules": mine("rules"),
        "tasks": tasks,
        "links": links,
        "parent": _brief(parent) if parent else None,
        "children": [_brief(c) for c in children],
        "group": {"name": group, "members": members},
    }


def _rhythm(sessions: list[dict]) -> tuple[dict[str, dict[str, int]], list[int]]:
    """Per day: turns, minutes and sessions; per hour of the day: turns."""
    by_day: dict[str, dict[str, int]] = {}
    by_hour = [0] * 24
    for s in sessions:
        d = str(s.get("created_date") or "")
        slot = by_day.setdefault(d, {"turns": 0, "minutes": 0, "session_minutes": 0, "sessions": 0})
        slot["turns"] += _int(s.get("turns_n"))
        # The agent's working minutes; the session's wall clock beside them.
        slot["minutes"] += _int(s.get("agent_min"))
        slot["session_minutes"] += _int(s.get("duration_min"))
        slot["sessions"] += 1
        try:
            turns = json.loads(s.get("turns_json") or "[]")
        except json.JSONDecodeError:
            turns = []
        for t in turns:
            at = str(t.get("at") or "")
            if len(at) >= 2 and at[:2].isdigit():
                by_hour[int(at[:2]) % 24] += 1
    return by_day, by_hour


def _profile_tasks(mentions: list[dict]) -> list[dict]:
    return [
        {
            "id": r["task_id"], "title": r["title"], "status": r["status"],
            "first_at": r["first_at"], "last_at": r["last_at"],
            "handed_n": _int(r["handed_n"]), "replied_n": _int(r["replied_n"]),
            "turn_max": _int(r["turn_max"]),
        }
        for r in mentions
    ]


def _profile_totals(mine, sessions: list[dict], by_day: dict, tasks: list[dict], links: list[dict]) -> dict[str, Any]:
    scans = mine("scans")
    architecture = mine("architecture")
    problems = mine("problems")
    return {
        "sessions_n": len(sessions),
        # minutes: the agent working. session_minutes: first prompt → last
        # answer; waiting_minutes: the rest, the agent waiting on the person.
        "minutes": sum(_int(s.get("agent_min")) for s in sessions),
        "session_minutes": sum(_int(s.get("duration_min")) for s in sessions),
        "waiting_minutes": sum(_int(s.get("waiting_min")) for s in sessions),
        # The helpers it started, their own minutes added up: the work done.
        "helper_minutes": sum(_int(s.get("helper_min")) for s in sessions),
        "minutes_approx": any(s.get("timed") == "approx" for s in sessions),
        "turns": sum(_int(s.get("turns_n")) for s in sessions),
        "days_active": len(by_day),
        "scans_n": len(scans),
        "files_n": sum(_int(s.get("files_n")) for s in scans),
        "lines_add": sum(_int(s.get("lines_add")) for s in scans),
        "lines_del": sum(_int(s.get("lines_del")) for s in scans),
        "file_entries_n": len(mine("files")),
        "decisions_n": len(mine("decisions")),
        "architecture_n": len(architecture),
        "features_n": len([a for a in architecture if a.get("kind") == "feature"]),
        "problems_n": len(problems),
        "bugs_resolved_n": len([p for p in problems if p.get("status") == "resolved"]),
        "rules_n": len(mine("rules")),
        "standups_n": len(mine("standups")),
        "tasks_n": len(tasks),
        "tasks_handed_n": len([t for t in tasks if t["handed_n"]]),
        "tasks_done_n": len([t for t in tasks if t["status"] in _DONE]),
        "links_n": len(links),
    }


@router.get("/api/agents/profiles")
def agents_profiles(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every agent of a project with its profile — the roster in one read."""
    etag = etag_for(f"agents:profiles:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    roster = [a for a in store.agents() if a.get("project") == project]
    # One read of each table for the whole roster, not one per agent.
    pre = profile_rows(store, [str(a.get("agent_id") or "") for a in roster])
    rows = [build_profile(store, a, pre) for a in roster]
    rows.sort(key=lambda p: (p["agent"].get("created_date") or "", p["agent"].get("agent_id") or ""))
    return json_response({"total": len(rows), "profiles": rows}, etag)


@router.get("/api/agents/links")
def agent_links_list(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"agents:links:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = rows_or_empty(
        store,
        "SELECT id, project, from_id, to_id, kind, style, note, from_at, to_at, "
        "created_at, actor FROM agent_links_mutual WHERE project = ? ORDER BY created_at ASC",
        (project,),
    )
    return json_response({"total": len(rows), "links": _resolve_links(store, rows),
                          "kinds": list(AGENT_LINK_KINDS), "styles": list(AGENT_LINK_STYLES)}, etag)


@router.post("/api/agents/links", status_code=201)
def agent_link_create(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{from, to, kind, style?, note?, from_at?, to_at?, actor?}``.

    Directed: *from* is the earlier lane, *to* the one it explains (a branch
    goes from the parent to the branch; a handoff from the one that stopped
    to the one that continued). Idempotent on (from, to, kind) — posting
    again returns the stored row; use update to change its note or style.
    """
    frm = str(body.get("from") or "").strip()
    to = str(body.get("to") or "").strip()
    kind = str(body.get("kind") or "").strip()
    if not frm or not to:
        raise HTTPException(status_code=422, detail="from and to are both required")
    if frm == to:
        raise HTTPException(status_code=422, detail="an agent cannot be linked to itself")
    if kind not in AGENT_LINK_KINDS:
        raise HTTPException(
            status_code=422, detail=f"kind must be one of {', '.join(AGENT_LINK_KINDS)}"
        )
    style = str(body.get("style") or AGENT_LINK_DEFAULT_STYLE[kind]).strip()
    if style not in AGENT_LINK_STYLES:
        raise HTTPException(
            status_code=422, detail=f"style must be one of {', '.join(AGENT_LINK_STYLES)}"
        )
    a, b = _raw_agent(store, frm), _raw_agent(store, to)
    if a.get("project") != b.get("project"):
        raise HTTPException(status_code=422, detail="both agents must belong to one project")
    note = str(body.get("note") or "").strip()
    if len(note) > 500:
        raise HTTPException(status_code=422, detail="note must be at most 500 characters")

    csv_path = _links_csv(store)
    for r in read_rows(csv_path):
        if r.get("from_id") == frm and r.get("to_id") == to and r.get("kind") == kind:
            # `created` is what the pages read; `existing` and the 200 are
            # the one rule every create follows (deps.create_answer).
            return create_answer({"link": r, "created": False}, response, existing=True)
    lid = _link_id(frm, to, kind)
    row = {
        "id": lid,
        "project": str(a.get("project") or ""),
        "from_id": frm,
        "to_id": to,
        "kind": kind,
        "style": style,
        "note": note,
        "from_at": str(body.get("from_at") or ""),
        "to_at": str(body.get("to_at") or ""),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "actor": str(body.get("actor") or _DEFAULT_ACTOR),
    }
    raced = append_if_absent(
        csv_path, AGENT_LINK_COLUMNS, row,
        lambda r: r.get("from_id") == frm and r.get("to_id") == to and r.get("kind") == kind,
    )
    if raced is not None:
        return create_answer({"link": raced, "created": False}, response, existing=True)
    store.rebuild()
    return create_answer({"link": _resolve_links(store, [row])[0], "created": True})


@router.post("/api/agents/links/{link_id}/update")
def agent_link_update(
    link_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Change a link's kind, style, note or anchors; the ends stay."""
    patch: dict[str, str] = {}
    if "kind" in body:
        kind = str(body.get("kind") or "").strip()
        if kind not in AGENT_LINK_KINDS:
            raise HTTPException(
                status_code=422, detail=f"kind must be one of {', '.join(AGENT_LINK_KINDS)}"
            )
        patch["kind"] = kind
    if "style" in body:
        style = str(body.get("style") or "").strip()
        if style not in AGENT_LINK_STYLES:
            raise HTTPException(
                status_code=422, detail=f"style must be one of {', '.join(AGENT_LINK_STYLES)}"
            )
        patch["style"] = style
    if "note" in body:
        note = str(body.get("note") or "").strip()
        if len(note) > 500:
            raise HTTPException(status_code=422, detail="note must be at most 500 characters")
        patch["note"] = note
    for k in ("from_at", "to_at"):
        if k in body:
            patch[k] = str(body.get(k) or "")
    if not patch:
        raise HTTPException(status_code=422, detail="nothing to update: send kind, style, note, from_at or to_at")

    def change(rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        kind = patch.get("kind", r.get("kind"))
        if kind != r.get("kind"):
            # The id follows (from, to, kind), as a new link's would:
            # kept, a later create of the old shape minted this id again.
            if any(o is not r and o.get("from_id") == r.get("from_id")
                   and o.get("to_id") == r.get("to_id") and o.get("kind") == kind
                   for o in rows):
                raise HTTPException(status_code=409, detail="that link already exists")
            r["id"] = _link_id(str(r.get("from_id")), str(r.get("to_id")), str(kind))
        r.update(patch)
        return True

    row = rewrite_one(store, _links_csv(store).name, AGENT_LINK_COLUMNS, link_id, change, "link")
    return {"link": _resolve_links(store, [dict(row)])[0]}


@router.post("/api/agents/links/{link_id}/delete")
def agent_link_delete(
    link_id: str,
    store: ViewStore = Depends(get_store),
) -> dict:
    def drop(rows: list[dict[str, str]], _row: dict[str, str]) -> bool:
        rows[:] = [r for r in rows if r.get("id") != link_id]
        return True

    rewrite_one(store, _links_csv(store).name, AGENT_LINK_COLUMNS, link_id, drop, "link")
    return {"deleted": link_id}


# ---------------------------------------------------------------------------
# One agent
# ---------------------------------------------------------------------------


@router.get("/api/agents/{agent_id}/profile")
def agent_profile(
    agent_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"agents:profile:{agent_id}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response(build_profile(store, _raw_agent(store, agent_id)), etag)


@router.post("/api/agents/{agent_id}/group")
def agent_set_group(
    agent_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{group}`` — put the agent in a named group; empty removes it.

    Like rename, this is presentation: the group is a label over several
    lanes, stored in each member's meta.json, and the ids never change.
    """
    group = str(body.get("group") or "").strip()
    if len(group) > 80:
        raise HTTPException(status_code=422, detail="group must be at most 80 characters")
    raw = _raw_agent(store, agent_id)
    meta_path = Path(raw.get("_chat_path", "")).parent / "meta.json"
    # Same sidecar lock as the capture hook (see routers/core.py rename).
    with acquire_flock(meta_path.with_name("meta.json.lock")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"cannot read meta.json: {exc}")
        if group:
            meta["agent_group"] = group
        else:
            meta.pop("agent_group", None)
        atomic_write_json(meta_path, meta)
    store.rebuild()
    return {"agent_id": agent_id, "agent_group": group}


@router.get("/api/agents/groups")
def agent_groups(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The groups in use for a project, with their members — for pickers."""
    etag = etag_for(f"agents:groups:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    groups: dict[str, list[dict]] = {}
    for a in store.agents():
        g = str(a.get("agent_group") or "")
        if a.get("project") == project and g:
            groups.setdefault(g, []).append(_brief(a))
    return json_response(
        {"groups": [{"name": g, "members": m} for g, m in sorted(groups.items())]}, etag
    )
