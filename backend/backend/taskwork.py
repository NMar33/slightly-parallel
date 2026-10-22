"""What the repository saw a task's turns do.

A task is named in captured turns (``task_mentions``); those turns sit in
sessions; and ``gitwork`` already attributes commits and uncommitted work to
each turn. So "which files did this task touch" needs no new bookkeeping.

The span is the part worth getting right. A task is usually named once —
the operator hands it over — and every turn after that is its work, until
another task is named. So a span opens on a turn that names this task and
closes on the first later turn that names a different one, or at the end of
the session. Counting only the turns that said the id would find almost
nothing, which is what it did.

This never replaces what the agent says. Evidence is the agent's account;
this is the repository's. The two are shown side by side, and the difference
is the part worth looking at.

Each file says whether it was ``committed``. A commit belongs to the turn
that made it, but the uncommitted working tree belongs to whoever dirtied
it — and on a laptop running two sessions in one repository that is not
always this task. So an uncommitted file is reported and never held against
the agent: it is shown, and left out of what the agent is said to have
missed.
"""

from __future__ import annotations

import json
from typing import Any

from . import gitwork, sessions
from .db import ViewStore

MAX_FILES = 400


def _add(
    per_path: dict[str, dict[str, Any]], path: str, add: int, dele: int,
    *, committed: bool,
) -> None:
    if not path:
        return
    rec = per_path.setdefault(
        path, {"lines_add": 0, "lines_del": 0, "committed": False, "_dirty": (0, 0)}
    )
    if committed:
        rec["lines_add"] += max(0, add)
        rec["lines_del"] += max(0, dele)
        rec["committed"] = True
    else:
        # The working tree is a snapshot, the same edit seen again at every
        # turn: the latest one stands, it is never summed.
        rec["_dirty"] = (max(0, add), max(0, dele))


LAST_TURN = 1 << 30


def _spans(rows: list[dict[str, Any]], task_id: str) -> dict[str, list[tuple[int, int]]]:
    """Per session, the turn ranges this task owns.

    ``rows`` is every mention in the sessions this task appears in, of any
    task. A range opens where this task is named and closes just before the
    next turn naming another one.
    """
    by_session: dict[str, dict[int, set[str]]] = {}
    for r in rows:
        sid = str(r.get("session_id") or "")
        if not sid:
            continue
        by_session.setdefault(sid, {}).setdefault(int(r.get("turn") or 0), set()).add(
            str(r.get("task_id") or "")
        )

    spans: dict[str, list[tuple[int, int]]] = {}
    for sid, marks in by_session.items():
        out: list[tuple[int, int]] = []
        start: int | None = None
        for turn in sorted(marks):
            named = marks[turn]
            if task_id in named:
                if start is None:
                    start = turn
            elif start is not None:
                out.append((start, turn - 1))
                start = None
        if start is not None:
            out.append((start, LAST_TURN))
        if out:
            spans[sid] = out
    return spans


def _with_done(store: ViewStore, task_id: str, spans: dict[str, list[tuple[int, int]]]) -> dict[str, list[tuple[int, int]]]:
    """The operator's #done is the better boundary: the task owns its stretch
    (donelib.py), and a span guessed from the mentions stops at the #done."""
    from . import donelib

    for st in donelib.stretches_raw(store, task_id):
        agent, lo, hi = st
        for s in store.query("SELECT id, turns_json FROM sessions WHERE agent_id = ?", (agent,)):
            try:
                ns = [int(t.get("n") or 0) for t in json.loads(s.get("turns_json") or "[]")]
            except ValueError:
                continue
            if not ns:
                continue
            sid = str(s["id"])
            ranges = [(a, hi if a <= hi < b else b) for a, b in spans.get(sid, [])]
            if min(ns) <= hi and max(ns) >= lo:
                ranges.append((lo, hi))
            if ranges:
                spans[sid] = ranges
    return spans


def task_work(store: ViewStore, task_id: str) -> dict[str, Any]:
    """``{files, commits, add, del, sessions}`` — git's account of the task.

    ``files`` is one record per path, biggest change first. Empty when no
    captured turn ever named the task, or when the chats it was worked in
    are not in a repository.
    """

    empty: dict[str, Any] = {"files": [], "commits": 0, "add": 0, "del": 0, "sessions": 0}
    # Every mention in the sessions this task appears in, of any task: the
    # next task named is what closes this one's span.
    rows = store.query(
        "SELECT session_id, turn, task_id FROM task_mentions WHERE session_id IN "
        "(SELECT session_id FROM task_mentions WHERE task_id = ?)",
        (task_id,),
    )
    spans = _with_done(store, task_id, _spans(rows, task_id))
    if not spans:
        return empty

    per_path: dict[str, dict[str, Any]] = {}
    shas: set[str] = set()
    for sid, ranges in spans.items():
        row = store.query_one("SELECT * FROM sessions WHERE id = ?", (sid,))
        if row is None:
            continue
        try:
            turns = json.loads(row.get("turns_json") or "[]")
        except json.JSONDecodeError:
            continue
        chat = sessions.chat_path(store, str(row.get("agent_id") or ""))
        if chat is None or not turns:
            continue
        try:
            work, _ = gitwork.session_work(
                chat, str(row.get("created_date") or ""),
                str(row.get("end_time") or ""), turns,
            )
        except Exception:  # noqa: BLE001 — git is best effort; evidence stands without it
            continue
        for turn, done in zip(turns, work):
            n = int(turn.get("n") or 0)
            if done is None or not any(lo <= n <= hi for lo, hi in ranges):
                continue
            for commit in done.get("commits") or []:
                sha = str(commit.get("sha") or "")
                if sha in shas:
                    continue  # a commit inside two spans is still one commit
                shas.add(sha)
                for f in commit.get("files") or []:
                    _add(per_path, str(f.get("path") or ""), int(f.get("add") or 0),
                         int(f.get("del") or 0), committed=True)
            for f in (done.get("uncommitted") or {}).get("paths") or []:
                _add(per_path, str(f.get("path") or ""), int(f.get("add") or 0),
                     int(f.get("del") or 0), committed=False)

    for rec in per_path.values():
        dirty_add, dirty_del = rec.pop("_dirty")
        rec["lines_add"] += dirty_add
        rec["lines_del"] += dirty_del
    files = sorted(
        ({"path": p, **v} for p, v in per_path.items()),
        key=lambda f: (-(f["lines_add"] + f["lines_del"]), f["path"]),
    )[:MAX_FILES]
    return {
        "files": files,
        "commits": len(shas),
        "add": sum(f["lines_add"] for f in files),
        "del": sum(f["lines_del"] for f in files),
        "sessions": len(spans),
    }
