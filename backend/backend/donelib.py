"""#done — the operator closes a task from the chat.

``#done`` in a message is the operator's verdict on a task, typed where the
work happened. The task is the one the message names (``#done tk_…``, several
ids close several), else the last task named in this chat since the previous
``#done``. None named: nothing moves, and the agent asks which one.

What it does, applied by the server like ``#important`` (the capture already
holds the message):

- **the move** — the task goes to *done*, written in its history as the
  operator's (``done_in_chat`` says where). The operator's verdict clears a
  pending agent report, as a move on the board does. A task already done or
  archived is not moved.
- **the stretch** — the messages that were the task's work: from the turn
  after the previous ``#done`` of this chat (or the turn after another task
  was last named before this one, or the chat's first turn) up to and
  including the ``#done`` message. ``#done`` belongs to the task it closes.
  taskwork.py counts the task's files and commits over it.

The ledger ``done.csv`` keeps one row per (tag, task): a tag is applied once,
so moving the card back on the board is not undone by the old message. Tags
written before the feature existed are never applied: ``done.json`` holds the
moment it first ran, and older tags are history, not commands.

Turns are numbered per agent chat (chat.md), across sessions, so a stretch is
``(agent_id, start, end)`` in those numbers.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .db import ViewStore
from .entities import ENTITIES, is_done
from .date_utils import now_iso

DONE_CSV = "done.csv"
STATE = "done.json"
DONE_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "project", "agent_id", "session_id", "turn", "start_turn",
    "at", "applied_at", "result", "from_status", "excerpt",
)
# result: moved · already (done before) · archived · unnamed (no task named)
RESOLVED = ("moved", "already", "archived")

_lock = threading.Lock()




def since(store: ViewStore) -> str:
    """The moment #done became a command here; older tags are left alone."""
    path = store.data_root / STATE
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("since") or "")
    except (OSError, ValueError):
        pass
    now = now_iso()
    try:
        path.write_text(json.dumps({"since": now}) + "\n", encoding="utf-8")
    except OSError:
        pass
    return now


def rows(store: ViewStore) -> list[dict[str, str]]:
    return read_rows(store.data_root / DONE_CSV)


def _id(agent_id: str, turn: int, task_id: str) -> str:
    return "dn_" + hashlib.sha256(f"{agent_id}|{turn}|{task_id}".encode()).hexdigest()[:8]


def adopt(store: ViewStore) -> list[dict[str, str]]:
    """Apply every #done not applied yet. Idempotent; safe on every read."""
    with _lock:
        return _adopt_locked(store)


def _adopt_locked(store: ViewStore) -> list[dict[str, str]]:
    start = since(store)
    tags = store.query(
        "SELECT project, agent_id, session_id, turn, at_ts, excerpt, tasks FROM done_tags "
        "WHERE at_ts >= ? ORDER BY agent_id, turn", (start,))
    if not tags:
        return []
    path = store.data_root / DONE_CSV
    ledger = read_rows(path)
    known = {r.get("id") for r in ledger}
    # Every resolved #done is a boundary, whichever task it closed.
    bounds: dict[str, list[int]] = {}
    for r in ledger:
        if r.get("result") in RESOLVED:
            bounds.setdefault(r.get("agent_id") or "", []).append(int(r.get("turn") or 0))
    tasks = {str(t["id"]): t for t in store.query(
        "SELECT id, title, status, archived_at FROM tasks_mutual")}
    mentions: dict[str, list[tuple[int, str, str]]] = {}
    for m in store.query(
            "SELECT agent_id, turn, task_id, role FROM task_mentions "
            "WHERE task_id LIKE 'tk_%' ORDER BY turn"):
        if str(m["task_id"]) in tasks:
            mentions.setdefault(str(m["agent_id"]), []).append(
                (int(m["turn"]), str(m["task_id"]), str(m["role"] or "")))
    # A task the operator started with #now is named by that message, though
    # the message carries no id: the agent wrote the card in that turn.
    for agent, turn, tid in _started_with_now(store, {str(t["agent_id"] or "") for t in tags}):
        if tid in tasks:
            mentions.setdefault(agent, []).append((turn, tid, "user"))
    for ms in mentions.values():
        ms.sort(key=lambda m: m[0])

    added: list[dict[str, str]] = []
    moves: list[tuple[str, str, int]] = []
    for tag in tags:
        agent, turn = str(tag["agent_id"] or ""), int(tag["turn"] or 0)
        prev = max((b for b in bounds.get(agent, []) if b < turn), default=0)
        given = [x for x in str(tag["tasks"] or "").split(",") if x]
        named = [x for x in given if x in tasks]
        window = [m for m in mentions.get(agent, []) if prev < m[0] <= turn]
        # An id the operator typed that is no task (a typo) is no task named:
        # it closed the last task named before it instead.
        if not named and not given:
            # The last task the operator named — not one an agent's answer
            # mentioned in passing ("done; tk_B depends on this").
            before = [m for m in window if m[0] < turn and m[2] == "user"]
            named = [before[-1][1]] if before else []
        if not named:
            rid = _id(agent, turn, "")
            if rid not in known:
                row = _row(rid, "", tag, turn, "unnamed", "")
                known.add(rid)
                added.append(row)
            continue
        for tid in named:
            rid = _id(agent, turn, tid)
            if rid in known:
                continue
            first = min((m[0] for m in window if m[1] == tid), default=turn)
            # The turn after another task was last named by the operator,
            # before this one was: the stretch does not reach into that task.
            other = max((m[0] for m in window if m[1] != tid and m[2] == "user" and m[0] < first), default=prev)
            t = tasks[tid]
            status = str(t.get("status") or "")
            result = ("archived" if str(t.get("archived_at") or "") or status.lower() == "done-archived"
                      else "already" if is_done(status) else "moved")
            row = _row(rid, tid, tag, turn, result, status, start_turn=max(prev, other) + 1)
            known.add(rid)
            added.append(row)
            if result == "moved":
                moves.append((tid, status, turn))
                tasks[tid] = {**t, "status": "done"}
        bounds.setdefault(agent, []).append(turn)
    # The tasks move first and the ledger is written after: a move that
    # fails (a locked file) leaves no row saying it happened, and the tag is
    # tried again at the next read.
    if moves:
        _move(store, moves, {r["task_id"]: r for r in added if r["result"] == "moved"})
    for row in added:
        append_row(path, DONE_COLUMNS, row)
    if added:
        store.rebuild()
    return added


def _started_with_now(store: ViewStore, agents: set[str]) -> list[tuple[str, int, str]]:
    """(agent, turn, task) for each card an agent wrote on the operator's #now:
    the turn is the one the card was written in, read from its `started` event."""
    from datetime import datetime

    from .sessions import chat_path, parse_turns

    rows = store.query(
        "SELECT e.task_id, e.timestamp, t.agent_id FROM task_events_mutual e "
        "JOIN tasks_mutual t ON t.id = e.task_id WHERE e.field = 'started'")
    out: list[tuple[str, int, str]] = []
    turns_of: dict[str, list] = {}
    for r in rows:
        agent = str(r["agent_id"] or "")
        if agent not in agents:
            continue
        if agent not in turns_of:
            path = chat_path(store, agent)
            try:
                turns_of[agent] = parse_turns(path) if path else []
            except OSError:
                turns_of[agent] = []
        try:
            at = datetime.fromisoformat(str(r["timestamp"]))
        except ValueError:
            continue
        before = [t.number for t in turns_of[agent] if t.at.replace(tzinfo=None) <= at]
        if before:
            out.append((agent, before[-1], str(r["task_id"])))
    return out


def _iso_minute(day: str, hm: str) -> str:
    """YYMM-DD and HH:MM as 2026-09-27T14:02 (other shapes as they came)."""
    if len(day) == 7 and day[4] == "-":
        return f"20{day[:2]}-{day[2:4]}-{day[5:7]}T{(hm or '00:00')[:5]}"
    return f"{day} {hm}".strip()


def _row(rid: str, tid: str, tag: dict, turn: int, result: str, status: str, start_turn: int = 0) -> dict[str, str]:
    return {
        "id": rid, "task_id": tid, "project": str(tag["project"] or ""),
        "agent_id": str(tag["agent_id"] or ""), "session_id": str(tag["session_id"] or ""),
        "turn": str(turn), "start_turn": str(start_turn), "at": str(tag["at_ts"] or ""),
        "applied_at": now_iso(), "result": result, "from_status": status,
        "excerpt": str(tag["excerpt"] or "")[:160],
    }


def _move(store: ViewStore, moves: list[tuple[str, str, int]], by_task: dict[str, dict[str, str]]) -> None:
    """Every task to done, each change in its history as the operator's."""
    from .routers.tasks_extra import after_status_change
    from .taskevents import append_events as _append_events

    ent = ENTITIES["task"]
    ids = {tid for tid, _, _ in moves}
    history: dict[str, list[tuple[str, str, str]]] = {}

    def mutate(rs: list[dict[str, str]]) -> bool:
        changed = False
        for r in rs:
            tid = r.get("id") or ""
            if tid not in ids:
                continue
            old = r.get("status") or ""
            if is_done(old):
                continue
            where = f"{by_task[tid]['agent_id']}#{by_task[tid]['turn']}"
            ch = [("status", old, "done"), ("done_in_chat", "", where)]
            r["status"] = "done"
            # The operator's verdict clears a pending agent report, as a move on the board does.
            for stamp in ("agent_done_at", "agent_done_by", "agent_done_note"):
                if r.get(stamp):
                    ch.append((stamp, r[stamp], ""))
                    r[stamp] = ""
            # The stack advances and a repeating task re-arms, as on the board.
            after_status_change(store, rs, r, old, ch)
            history[tid] = ch
            changed = True
        return changed

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    for tid, ch in history.items():
        _append_events(store, tid, "operator", ch)


# ---------------------------------------------------------------------------
# Reading: a task's stretches, and what they add up to
# ---------------------------------------------------------------------------


def stretches_raw(store: ViewStore, task_id: str) -> list[tuple[str, int, int]]:
    """(agent_id, first turn, #done turn) for each #done that closed this task."""
    return [(r["agent_id"], int(r.get("start_turn") or 1), int(r.get("turn") or 0))
            for r in rows(store) if r.get("task_id") == task_id and r.get("result") in RESOLVED]


def stretches(store: ViewStore, task_id: str) -> list[dict[str, Any]]:
    """Each #done of this task: its stretch of the chat, counted."""
    out: list[dict[str, Any]] = []
    for r in rows(store):
        if r.get("task_id") != task_id or r.get("result") not in RESOLVED:
            continue
        agent, lo, hi = r["agent_id"], int(r.get("start_turn") or 1), int(r.get("turn") or 0)
        turns: list[tuple[str, str, str]] = []   # (session, day, hh:mm)
        for s in store.query(
                "SELECT id, created_date, turns_json FROM sessions WHERE agent_id = ? ORDER BY chat_start_line",
                (agent,)):
            try:
                ts = json.loads(s.get("turns_json") or "[]")
            except ValueError:
                continue
            for t in ts:
                if lo <= int(t.get("n") or 0) <= hi:
                    turns.append((str(s["id"]), str(s["created_date"]), str(t.get("at") or "")))
        minutes = 0
        by_session: dict[str, list[str]] = {}
        for sid, _, at in turns:
            by_session.setdefault(sid, []).append(at)
        for ats in by_session.values():
            mins = [int(a[:2]) * 60 + int(a[3:5]) for a in ats if len(a) >= 5 and a[:2].isdigit()]
            if mins:
                minutes += max(1, max(mins) - min(mins) + 1)
        out.append({
            "agent_id": agent, "project": r.get("project") or "", "start": lo, "end": hi,
            "turns": len(turns), "chats": len(by_session), "minutes": minutes,
            # ISO, as done_at is: one line must not carry two date formats.
            "first": _iso_minute(turns[0][1], turns[0][2]) if turns else "", "done_at": r.get("at") or "",
            "result": r.get("result") or "", "from_status": r.get("from_status") or "",
        })
    return out


def reopened(store: ViewStore, task_id: str) -> bool:
    """Moved out of done after a #done closed it."""
    closed = [r.get("applied_at") or "" for r in rows(store) if r.get("task_id") == task_id and r.get("result") == "moved"]
    if not closed:
        return False
    last = max(closed)
    return any(
        not is_done(e.get("new_value")) for e in store.query(
            "SELECT timestamp, new_value FROM task_events_mutual WHERE task_id = ? AND field = 'status' "
            "AND timestamp >= ?", (task_id, last)))
