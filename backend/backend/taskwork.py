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

A commit is the task's in one of three ways, each kept on the commit as
``how``: ``signed`` — its message carries ``Task: tk_…`` (the contract asks
the agent to write it); ``linked`` — the agent linked it afterwards with the
MCP tool task_commits; ``chat`` — no word either way, so it is the one the
task's stretch of the chat made, as before. A commit signed or linked for
other tasks is never taken by a stretch, and a turn where the operator only
filed a task (``#task``, ``#now-todo`` …) opens no stretch: the work on it
has not started.

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
import re
from typing import Any

from . import gitwork, sessions
from .csvio import as_int, read_rows
from .db import ViewStore
from .hookshared import command_text

MAX_FILES = 400
LINKS_FILE = "commit_links.csv"
_UNDO_RE = re.compile(r"(?<![\w#])#undo(?:-yes)?(?![\w-])", re.IGNORECASE)


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
        by_session.setdefault(sid, {}).setdefault(as_int(r.get("turn")), set()).add(
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
    """``{files, commits, add, del, sessions, commit_list, signed, chat}`` —
    git's account of the task.

    ``files`` is one record per path, biggest change first. ``commit_list``
    is every commit once, oldest first, each with ``how``. Empty when no
    commit names the task and no captured turn worked on it, or when its
    chats are not in a repository.
    """

    empty: dict[str, Any] = {"files": [], "commits": 0, "add": 0, "del": 0, "sessions": 0,
                             "commit_list": [], "signed": 0, "chat": 0}
    per_path: dict[str, dict[str, Any]] = {}
    listed: dict[str, dict[str, Any]] = {}

    def take(commit: dict[str, Any], how: str) -> None:
        sha = str(commit.get("sha") or "")[:7]
        if not sha or sha in listed:
            return  # a commit inside two spans, or signed and in a span, is still one commit
        listed[sha] = {"sha": sha, "at": str(commit.get("at") or ""), "subject": str(commit.get("subject") or ""),
                       "how": how, "files": [str(f.get("path") or "") for f in (commit.get("files") or [])][:60],
                       "agent": str(commit.get("agent") or ""), "tasks": list(commit.get("tasks") or [])}
        for f in commit.get("files") or []:
            _add(per_path, str(f.get("path") or ""), int(f.get("add") or 0), int(f.get("del") or 0), committed=True)

    # The agent's word first: commits signed or linked for this task.
    links = _links(store)
    mine_linked = {sha for sha, tasks in links.items() if task_id in tasks}
    others = {sha for sha, tasks in links.items() if task_id not in tasks}
    for c in _repo_log(store, task_id):
        short = c.sha[:7]
        if task_id in c.tasks:
            take(c.as_dict(), "signed")
        elif short in mine_linked:
            take(c.as_dict(), "linked")
        elif c.tasks:
            others.add(short)

    # The operator opens and closes a task's stretch: a message of theirs
    # that names the task, or the #now that started it. The next such
    # message naming another task closes it. An agent naming a task in its
    # answer (a list, "filed tk_…") links the turn to the task (task_mentions
    # keeps it) but opens and closes nothing.
    # A stretch runs across the chat, not one session of it: a chat is cut
    # into sessions by pauses, and the work may go on after a pause without
    # the operator naming the task again. Turn numbers count the whole chat.
    from . import nowlib
    writer = store.query_one("SELECT agent_id FROM tasks_mutual WHERE id = ?", (task_id,))
    chats = {str(r["agent_id"] or "") for r in store.query(
        "SELECT DISTINCT agent_id FROM task_mentions WHERE task_id = ?", (task_id,))}
    chats |= {str(n.get("agent_id") or "") for n in nowlib.rows(store) if n.get("task_id") == task_id}
    if writer and writer.get("agent_id"):
        chats.add(str(writer["agent_id"]))
    chats -= {""}
    session_rows: dict[str, dict[str, Any]] = {}
    turns_of: dict[str, set[int]] = {}
    if chats:
        marks = ",".join("?" for _ in chats)
        for row in store.query(f"SELECT * FROM sessions WHERE agent_id IN ({marks})", tuple(chats)):
            sid = str(row["id"])
            session_rows[sid] = row
            try:
                turns_of[sid] = {int(t.get("n") or 0) for t in json.loads(row.get("turns_json") or "[]")}
            except (json.JSONDecodeError, ValueError):
                turns_of[sid] = set()
    filing = {sid: _filing_turns(row) for sid, row in session_rows.items()}

    def session_of(agent: str, turn: int) -> str:
        return next((sid for sid, row in session_rows.items()
                     if row.get("agent_id") == agent and turn in turns_of.get(sid, set())), "")
    rows: list[dict[str, Any]] = []
    if chats:
        rows = store.query(
            f"SELECT agent_id, session_id, turn, task_id, role FROM task_mentions WHERE agent_id IN ({marks})",
            tuple(chats))
    # Every #now in these chats opens the stretch of the card it started, and
    # so closes the one running: the card the server wrote (now.csv, exact)
    # and the card the agent wrote in that turn (its "started" event).
    for n in nowlib.rows(store):
        if n.get("agent_id") in chats and n.get("column") == "doing" and n.get("task_id"):
            turn = as_int(n.get("turn"))
            rows.append({"agent_id": n["agent_id"], "session_id": n.get("session_id") or session_of(n["agent_id"], turn),
                         "turn": turn, "task_id": n["task_id"], "role": "user"})
    for agent, turn, tid in nowlib.card_turns(store, chats, ("started",), skip_server=True):
        rows.append({"agent_id": agent, "session_id": session_of(agent, turn), "turn": turn, "task_id": tid, "role": "user"})
    # A turn that only filed a task (#task, #now-todo) or asked #undo names
    # tasks without working on them: it opens, closes and carries nothing.
    rows = [r for r in rows if as_int(r.get("turn")) not in filing.get(str(r.get("session_id") or ""), set())]
    # After a pause the stretch goes on only into a session that names the
    # task again, by anyone: an agent's mention keeps it, never opens it.
    named_in = {str(r.get("session_id") or "") for r in rows if r.get("task_id") == task_id}
    rows = [{**r, "session_id": r["agent_id"]} for r in rows if str(r.get("role") or "") == "user"]
    by_chat = _spans(rows, task_id)

    def held(row: dict[str, Any], ranges: list[tuple[int, int]]) -> bool:
        try:
            ns = [int(t.get("n") or 0) for t in json.loads(row.get("turns_json") or "[]")]
        except (json.JSONDecodeError, ValueError):
            return False
        return any(lo <= n <= hi for n in ns for lo, hi in ranges)
    spans = _with_done(store, task_id, {
        sid: by_chat[str(row.get("agent_id") or "")] for sid, row in session_rows.items()
        if str(row.get("agent_id") or "") in by_chat and sid in named_in and held(row, by_chat[str(row.get("agent_id") or "")])})

    for sid, ranges in spans.items():
        row = session_rows.get(sid) or store.query_one("SELECT * FROM sessions WHERE id = ?", (sid,))
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
            n = as_int(turn.get("n"))
            if done is None or not any(lo <= n <= hi for lo, hi in ranges):
                continue
            for commit in done.get("commits") or []:
                sha = str(commit.get("sha") or "")[:7]
                tasks = commit.get("tasks") or []
                if tasks or sha in others:
                    # Signed or linked: for this task it was taken above,
                    # for another it is that task's, never this stretch's.
                    continue
                # Found by the chat: the chat's agent made it, unless the line says otherwise.
                take({**commit, "agent": commit.get("agent") or str(row.get("agent_id") or "")}, "chat")
            for f in (done.get("uncommitted") or {}).get("paths") or []:
                _add(per_path, str(f.get("path") or ""), int(f.get("add") or 0),
                     int(f.get("del") or 0), committed=False)

    if not listed and not per_path:
        return {**empty, "sessions": len(spans)}
    for rec in per_path.values():
        dirty_add, dirty_del = rec.pop("_dirty")
        rec["lines_add"] += dirty_add
        rec["lines_del"] += dirty_del
    files = sorted(
        ({"path": p, **v} for p, v in per_path.items()),
        key=lambda f: (-(f["lines_add"] + f["lines_del"]), f["path"]),
    )[:MAX_FILES]
    commit_list = sorted(listed.values(), key=lambda c: c["at"])
    return {
        "files": files,
        "commits": len(commit_list),
        "add": sum(f["lines_add"] for f in files),
        "del": sum(f["lines_del"] for f in files),
        "sessions": len(spans),
        "commit_list": commit_list,
        "signed": sum(1 for c in commit_list if c["how"] in ("signed", "linked")),
        "chat": sum(1 for c in commit_list if c["how"] == "chat"),
    }


def _filing_turns(row: dict[str, Any]) -> set[int]:
    """The turns of a session where a task is named but not worked on: the
    operator filed one (``#task``, ``#now-todo`` and the like — the work has
    not started), or asked to undo a mistake (``#undo``: the agent lists
    candidates by id). A task named there opens no stretch and closes none."""
    try:
        turns = json.loads(row.get("turns_json") or "[]")
    except json.JSONDecodeError:
        return set()
    out: set[int] = set()
    for t in turns:
        said = command_text(str(t.get("user") or ""))
        command, _lane, column = sessions.task_command(said)
        if command == "task" or (command == "now" and column != "doing") or _UNDO_RE.search(said):
            out.add(int(t.get("n") or 0))
    return out


def _links(store: ViewStore) -> dict[str, set[str]]:
    """sha (its first 7 hex, as every list here shows it) → the tasks an agent linked it to."""
    out: dict[str, set[str]] = {}
    for r in read_rows(store.data_root / LINKS_FILE):
        sha = str(r.get("sha") or "").strip().lower()[:7]
        if sha and r.get("task_id"):
            out.setdefault(sha, set()).add(str(r["task_id"]))
    return out


def _repo_log(store: ViewStore, task_id: str) -> list[gitwork.Commit]:
    """The commits of the task's project's repository (read once per HEAD)."""
    from .file_entries import project_repo

    row = store.query_one("SELECT project FROM tasks_mutual WHERE id = ?", (task_id,))
    repo = project_repo(store, str((row or {}).get("project") or "")) if row else None
    if repo is None:
        return []
    try:
        return gitwork.commits(repo)
    except Exception:  # noqa: BLE001 — git is best effort
        return []
