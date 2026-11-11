"""Sessions endpoints — the derived time axis (see sessions.py).

Read-only by nature: sessions are computed from turn logs at rebuild.
The list is lens-shaped so the shared LensPage renders it; the detail
composes its pyramid live — L3 from the block's turn summaries, L4 from
the exact chat.md line range the session covers.
"""

from __future__ import annotations

import json
from itertools import islice
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from .. import gitwork, produced, sessions
from ..db import ViewStore
from .deps import attach_agent, etag_for, get_store, json_response, maybe_304, not_found

router = APIRouter()


@router.get("/api/sessions")
def sessions_list(
    request: Request,
    project: str | None = Query(None),
    agent_id: str | None = Query(None),
    from_: str | None = Query(None, alias="from_date"),
    to: str | None = Query(None, alias="to_date"),
    limit: int = Query(500, ge=1, le=5000),
    prompt: str | None = Query(None),
    q: str | None = Query(None),
    helpers: bool = Query(False),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Work sessions, newest first. Derived — agents never write these.

    Helper chats (a codex exec, a claude -p another chat started) are left
    out: they are listed under the chat that started them. ``agent_id``
    names one chat, a helper too; ``helpers=1`` keeps them in.

    ``prompt=<id>`` narrows to the sessions a prompt was sent in — every
    version and every reworded send — and puts ``prompt_turn`` on each row,
    so the page can open the session on the turn that carried it.

    ``q=<text>`` narrows to sessions whose turns contain the text and puts
    ``matches`` — the number of turns that do — on each row. Case-blind,
    substring: a find across the whole history, not inside one chat.

    Every row also carries ``marks`` (the saved prompt it was sent from,
    and the messages kept out of it) and ``produced`` (what the agent posted during the
    session, by kind) and ``tasks`` (distinct tasks mentioned) — the L3 the
    old drill-down had, at a fraction of its weight, from tables that
    already exist.
    """
    etag = etag_for(f"sessions:{project}:{agent_id}:{from_}:{to}:{limit}:{prompt}:{q}:{helpers}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    turns_by_session: dict[str, list[int]] = {}
    if prompt:
        from .. import promptlib
        _, versions = promptlib.read_doc(store.data_root, prompt)
        for send in promptlib.sends(store, versions):
            turns_by_session.setdefault(str(send["session_id"]), []).append(int(send["turn"]))
        if not turns_by_session:
            return json_response({"total": 0, "sessions": []}, etag)
        clauses.append(f"id IN ({','.join('?' * len(turns_by_session))})")
        params.extend(turns_by_session)
    if project:
        clauses.append("project = ?")
        params.append(project)
    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    elif not helpers:
        from ..sessions import helper_ids
        hidden = sorted(helper_ids(store))
        if hidden:
            clauses.append(f"agent_id NOT IN ({','.join('?' * len(hidden))})")
            params.extend(hidden)
    if from_:
        clauses.append("created_date >= ?")
        params.append(from_)
    if to:
        clauses.append("created_date <= ?")
        params.append(to)
    # The find reads the turns' own text, below. A LIKE over turns_json
    # matched the JSON around it: `user` found every session, `_` was a
    # wildcard, and a quote or a line break in the text was never found.
    needle = (q or "").strip().lower()
    # turns_json is the whole history's text; it is read only when a find
    # needs it. Reading it for every list load cost more than the list.
    # chat_end_line grows with every captured line: the page's version of a chat.
    cols = ("id, project, agent_id, created_date, start_time, end_time, duration_min, agent_min, "
            "waiting_min, helper_min, timed, turns_n, l1, chat_end_line")
    if needle:
        cols += ", turns_json"
    sql = (
        f"SELECT {cols} FROM sessions WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_date DESC, start_time DESC"
        + ("" if needle else " LIMIT ?")
    )
    if not needle:
        params.append(limit)
    rows = store.query(sql, tuple(params))
    if needle:
        found = []
        for row in rows:
            try:
                turns = json.loads(row.pop("turns_json", None) or "[]")
            except json.JSONDecodeError:
                turns = []
            row["matches"] = sum(
                1 for t in turns
                if needle in f"{t.get('user') or ''}\n{t.get('agent') or ''}".lower()
            )
            if row["matches"]:
                found.append(row)
                if len(found) >= limit:
                    break
        rows = found
    if turns_by_session:
        for row in rows:
            turns = sorted(turns_by_session.get(str(row.get("id")), []))
            row["prompt_turn"] = turns[0] if turns else None
            row["prompt_turns"] = turns
    _attach_produced(store, rows)
    attach_agent(store, rows)
    return json_response({"total": len(rows), "sessions": rows}, etag)


# The chat viewer's turns: what each changed, and the tokens it used.
_turns_with_work = sessions.turns_with_usage


@router.get("/api/sessions/turns")
def sessions_turns(
    request: Request, ids: str = Query(""), store: ViewStore = Depends(get_store),
) -> Response:
    """The turns of many sessions in one round trip — ``ids=a,b,c``, up to 500.

    The reader's "all" mode used to fetch 164 details one by one; the whole
    history is one request now, each turn still carrying its work. Each
    chat's usage is read once per request; the ETag follows the store and
    the files the usage reads beside it (the limits, the status line).
    """
    wanted = [x.strip() for x in ids.split(",") if x.strip()][:500]
    if not wanted:
        return json_response({"turns": {}}, etag_for("sessions-turns:", store))
    ph = ",".join("?" * len(wanted))
    rows = store.query(f"SELECT * FROM sessions WHERE id IN ({ph})", tuple(wanted))
    sig = sessions.usage_signature(store, {str(r.get("agent_id") or "") for r in rows})
    etag = etag_for(f"sessions-turns:{','.join(wanted)}:{sig}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    memo: dict[str, dict[int, dict[str, Any]]] = {}
    return json_response({"turns": {str(r["id"]): _turns_with_work(store, r, memo) for r in rows}}, etag)


@router.get("/api/sessions/{session_id}/diff")
def sessions_diff(
    session_id: str,
    sha: str | None = Query(None),
    path: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> dict:
    """The change behind a work line: one file of one commit, a whole commit,
    or — without ``sha`` — the working tree against HEAD right now.

    Scoped by session so the client never names a repository: the repo is
    the one the session's agent ran in, from its own capture.
    """
    row = store.query_one("SELECT agent_id FROM sessions WHERE id = ?", (session_id,))
    if row is None:
        raise not_found("session", session_id)
    chat = _chat_path(store, str(row.get("agent_id") or ""))
    repo = gitwork.repo_for_chat(chat) if chat else None
    if repo is None:
        raise HTTPException(status_code=409, detail="this session's agent has no repository")
    out = gitwork.diff(repo, sha, path)
    if out is None:
        raise not_found("change", sha or path or "working tree")
    return out


@router.post("/api/sessions/{session_id}/open")
def sessions_open(
    session_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{path}`` — open the file on this laptop, with whatever opens it."""
    row = store.query_one("SELECT agent_id FROM sessions WHERE id = ?", (session_id,))
    if row is None:
        raise not_found("session", session_id)
    chat = _chat_path(store, str(row.get("agent_id") or ""))
    repo = gitwork.repo_for_chat(chat) if chat else None
    if repo is None:
        raise HTTPException(status_code=409, detail="this session's agent has no repository")
    ok, why = gitwork.open_file(repo, str(body.get("path") or ""))
    return {"opened": ok, "path": why}


def _attach_produced(store: ViewStore, rows: list[dict[str, Any]]) -> None:
    """Commits, files, posts and tasks per session — from caches that live
    one store version, so a list load is arithmetic, not scans."""
    if not rows:
        return
    mentioned = produced.task_mentions(store)
    marked = produced.marks(store)
    for row in rows:
        row["produced"] = produced.count_in(
            store, str(row.get("agent_id") or ""), str(row.get("created_date") or ""),
            str(row.get("start_time") or ""), str(row.get("end_time") or ""),
        )
        row["tasks"] = mentioned.get(str(row["id"]), 0)
        row["marks"] = marked.get(str(row["id"]), {})
    _attach_git(store, rows)


_git_rows: dict[tuple[str, str], dict[str, int]] = {}


# The chat of an agent and its turns are read in sessions.py; the routes
# keep the short names they have always used.
_chat_paths = sessions.chat_paths
_chat_path = sessions.chat_path


def git_for_sessions(store: ViewStore, ids: list[str]) -> dict[str, dict[str, int]]:
    """Per-session git totals for the given ids — the same cache the list uses."""
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = store.query(
        f"SELECT id, agent_id, created_date, start_time, end_time FROM sessions WHERE id IN ({ph})",
        tuple(ids),
    )
    _attach_git(store, rows)
    return {str(r["id"]): r["git"] for r in rows}


def _attach_git(store: ViewStore, rows: list[dict[str, Any]]) -> None:
    """Commits and files changed per session, from each agent's own repo.

    One HEAD read per repository per request; the log behind it is cached
    by HEAD, and a session's totals are cached by (session, HEAD) — a list
    load repeats no git work unless something was committed.
    """
    paths = _chat_paths(store)
    heads: dict[str, str] = {}
    for row in rows:
        chat = paths.get(str(row.get("agent_id") or ""))
        row["git"] = {"commits": 0, "files": 0, "add": 0, "del": 0}
        if chat is None:
            continue
        repo = gitwork.repo_for_chat(chat)
        if repo is None:
            continue
        key = str(repo)
        if key not in heads:
            heads[key] = gitwork.head(repo)
        cache_key = (str(row["id"]), heads[key])
        hit = _git_rows.get(cache_key)
        if hit is not None:
            row["git"] = dict(hit)
            continue
        stamps = gitwork.turn_stamps(
            str(row.get("created_date") or ""),
            [{"at": str(row.get("start_time") or "")}, {"at": str(row.get("end_time") or "")}],
        )
        if not stamps or stamps[0] is None:
            continue
        per = gitwork.attribute(gitwork.commits(repo), stamps, stamps[-1])
        cs = [c for group in per for c in group]
        row["git"] = {
            "commits": len(cs),
            "files": len({p for c in cs for p, _, _ in c.files}),
            "add": sum(c.add for c in cs), "del": sum(c.dele for c in cs),
        }
        _git_rows[cache_key] = dict(row["git"])
        if len(_git_rows) > 5000:
            _git_rows.clear()


@router.get("/api/sessions/{session_id}")
def sessions_detail(
    session_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    """One session's pyramid: turn summaries (L3) + raw chat excerpt (L4)."""
    row = store.query_one(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    )
    # The turns carry usage, which also reads the limits and the status
    # line beside the store: the tag follows them too.
    sig = sessions.usage_signature(store, [str(row.get("agent_id") or "")]) if row is not None else ""
    etag = etag_for(f"sessions:{session_id}:{sig}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    if row is None:
        raise not_found("session", session_id)

    turns = _turns_with_work(store, row)
    summaries = [
        t.get("agent") or t.get("user")
        for t in turns
        if (t.get("agent") or t.get("user"))
    ]

    l4 = _chat_excerpt(
        store,
        str(row.get("agent_id") or ""),
        int(row.get("chat_start_line") or 0),
        int(row.get("chat_end_line") or 0),
    )
    metadata = {k: v for k, v in row.items() if k != "turns_json"}
    attach_agent(store, [metadata])
    approx = "about " if row.get("timed") == "approx" else ""
    l2 = (
        f"{row.get('turns_n')} turns over {row.get('duration_min')} minutes "
        f"({row.get('start_time')}–{row.get('end_time')}): the agent worked "
        f"{approx}{row.get('agent_min')}, waited on you {approx}{row.get('waiting_min')}"
        + (f"; its helpers worked {row.get('helper_min')} between them." if row.get("helper_min") else ".")
    )
    return json_response(
        {"metadata": metadata, "l2": l2, "l3": summaries, "l4": l4,
         "turns": turns},
        etag,
    )


def _chat_excerpt(
    store: ViewStore, agent_id: str, start: int, end: int
) -> str:
    """The chat.md lines this session covers (1-based, inclusive)."""
    agent = next(
        (a for a in store.agents() if a.get("agent_id") == agent_id), None
    )
    if agent is None or start < 1 or end < start:
        return ""
    chat_path = Path(agent.get("_chat_path") or "")
    if not chat_path.exists():
        return ""
    # Only the session's own lines are read. A line ends at "\n" and nowhere
    # else — the rule the line numbers were counted by (sessions.py);
    # ``splitlines`` also breaks on the Unicode separators.
    try:
        with open(chat_path, encoding="utf-8", errors="replace", newline="\n") as fh:
            lines = [ln.rstrip("\n") for ln in islice(fh, start - 1, end)]
    except OSError:
        return ""
    return "\n".join(lines).strip()
