"""Important marks — the agents, tasks and messages the operator stars.

``#important`` in a message marks three things: the message, the agent of
the chat, and every task the message names. ``#important-agent``,
``#important-task`` and ``#important-message`` mark one of them; the task
form, when the message names none, takes the last task named earlier in
the same chat. The ★ on a page marks and unmarks by hand. A task's star is
the board's own (its ``remember`` field); the router sets it for a task
row adopted here (routers/marks.py).

Like ``#vision``, the tag is the whole act: the capture already holds the
message, and the server adopts every tagged turn on read (``adopt``). One
ledger, ``marks.csv``, holds every mark. An unmark stamps ``removed_at``
rather than deleting, so a tag already adopted is never adopted again —
the operator's ☆ wins over the old message that set it.

A message is known by its agent and turn (``<agent_id>#<turn>``): turn
numbers are fixed in a chat, while session ids regroup with the gap setting.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .db import ViewStore
from .date_utils import now_iso

MARKS_CSV = "marks.csv"
MARK_COLUMNS: tuple[str, ...] = (
    "id", "kind", "target", "project", "agent_id", "session_id", "turn",
    "excerpt", "marked_at", "source", "removed_at",
)
KINDS: tuple[str, ...] = ("agent", "task", "message")

_lock = threading.Lock()


def message_target(agent_id: str, turn: int | str) -> str:
    return f"{agent_id}#{int(turn or 0)}"


def _id(*parts: Any) -> str:
    return "mk_" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8]




def adopt(store: ViewStore) -> list[str]:
    """Bring every #important turn into marks.csv. Idempotent; safe on every read."""
    with _lock:
        return _adopt_locked(store)


def _adopt_locked(store: ViewStore) -> list[str]:
    tags = store.query(
        "SELECT kind, project, agent_id, session_id, turn, at_ts, excerpt, tasks "
        "FROM important_tags ORDER BY at_ts"
    )
    if not tags:
        return []
    path = store.data_root / MARKS_CSV
    known = {r.get("id") for r in read_rows(path)}
    tasks = {str(r["id"]) for r in store.query("SELECT id FROM tasks_mutual")}
    added: list[str] = []

    def put(kind: str, target: str, tag: dict) -> None:
        mid = _id(kind, target, tag["agent_id"], tag["turn"])
        if mid in known:
            return
        append_row(path, MARK_COLUMNS, {
            "id": mid, "kind": kind, "target": target, "project": tag["project"] or "",
            "agent_id": tag["agent_id"] or "", "session_id": tag["session_id"] or "",
            "turn": int(tag["turn"] or 0), "excerpt": tag["excerpt"] or "",
            "marked_at": str(tag["at_ts"] or ""), "source": "tag", "removed_at": "",
        })
        known.add(mid)
        added.append(mid)

    for t in tags:
        kind, agent, turn = str(t["kind"]), str(t["agent_id"] or ""), int(t["turn"] or 0)
        named = [x for x in str(t["tasks"] or "").split(",") if x in tasks]
        if kind in ("all", "message"):
            put("message", message_target(agent, turn), t)
        if kind in ("all", "agent") and agent:
            put("agent", agent, t)
        if kind == "all":
            for tid in named:
                put("task", tid, t)
        if kind == "task":
            if not named:
                # The last task named earlier in this chat, by either side.
                row = store.query_one(
                    "SELECT task_id FROM task_mentions WHERE agent_id = ? AND turn < ? "
                    "AND task_id LIKE 'tk_%' ORDER BY turn DESC LIMIT 1",
                    (agent, turn),
                )
                named = [str(row["task_id"])] if row and str(row["task_id"]) in tasks else []
            for tid in named:
                put("task", tid, t)
    return added


def rows(store: ViewStore) -> list[dict[str, str]]:
    """Every row of the ledger, unmarked ones included."""
    return read_rows(store.data_root / MARKS_CSV)


def active(store: ViewStore, project: str = "") -> list[dict[str, str]]:
    """The marks in force: one per (kind, target), the newest, none unmarked."""
    rows = [r for r in read_rows(store.data_root / MARKS_CSV) if not (r.get("removed_at") or "")]
    if project:
        rows = [r for r in rows if (r.get("project") or "") == project]
    newest: dict[tuple[str, str], dict[str, str]] = {}
    for r in sorted(rows, key=lambda r: r.get("marked_at") or ""):
        newest[(r.get("kind") or "", r.get("target") or "")] = r
    return sorted(newest.values(), key=lambda r: r.get("marked_at") or "", reverse=True)


def mark(store: ViewStore, kind: str, target: str, fields: dict[str, Any]) -> dict[str, str]:
    """Star one thing by hand. Marking what is already marked changes nothing."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not target:
        raise ValueError("a mark needs a target")
    with _lock:
        path = store.data_root / MARKS_CSV
        for r in read_rows(path):
            if r.get("kind") == kind and r.get("target") == target and not r.get("removed_at"):
                return r
        now = now_iso()
        row = {
            "id": _id(kind, target, "operator", now), "kind": kind, "target": target,
            "project": str(fields.get("project") or ""), "agent_id": str(fields.get("agent_id") or ""),
            "session_id": str(fields.get("session_id") or ""), "turn": int(fields.get("turn") or 0),
            "excerpt": str(fields.get("excerpt") or "")[:160], "marked_at": now,
            "source": "operator", "removed_at": "",
        }
        append_row(path, MARK_COLUMNS, row)
        return {k: str(v) for k, v in row.items()}


def unmark(store: ViewStore, kind: str, target: str) -> int:
    """Take the star off: every mark in force on this target is stamped removed."""
    path = store.data_root / MARKS_CSV
    if not path.exists():
        return 0
    n = 0

    def mutate(rows: list[dict[str, str]]) -> bool:
        nonlocal n
        now = now_iso()
        for r in rows:
            if r.get("kind") == kind and r.get("target") == target and not r.get("removed_at"):
                r["removed_at"] = now
                n += 1
        return n > 0

    with _lock:
        rewrite_rows(path, MARK_COLUMNS, mutate)
    return n
