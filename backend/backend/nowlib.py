"""#now — the card the agent did not write, written by the server.

``#now`` in a message starts the task the chat works on: the agent titles it
with ``write_entry {lens: "task"}`` and the server keeps the operator's
message as its text (routers/tasks_extra.py). A model that goes straight to
the work skips that call, and the task was lost: no card, and the ``#done``
after it had nothing to move.

So the server writes it once the agent had its chance: the #now turn has an
answer, or a later message came (a turn cut off). The card is the one the
agent would have written — the message as its text, its column and lane —
titled with the message's start (the tag taken out, up to 80 characters, at
a word). Its history says the server wrote it, and for which chat; the
agent can retitle it with ``task_update``. A lane the message names that the
board does not have is left to the agent, who asks the operator which.

The ledger ``now.csv`` keeps one row per #now turn the server wrote a card
for, so a card moved or archived on the board is not written again; tags
written before the feature existed are never applied (``now.json`` holds
the moment it first ran).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime

from .csvio import append_row, read_rows
from .date_utils import now_iso
from .db import ViewStore

NOW_CSV = "now.csv"
STATE = "now.json"
NOW_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "project", "agent_id", "session_id", "turn", "at", "applied_at", "column",
)
#: The title the server gives, at most: an agent task's own limit.
TITLE_CHARS = 80
#: The verbs an agent-written #now card carries in its history (tasks_extra.tasks_create).
WRITTEN_FIELDS = ("started", "filed")

_lock = threading.Lock()
_NOW_TAG_RE = re.compile(
    r"(?<![\w#])#now(?:-(?:to-?do|next|backlog|doing|review|parked|done))?(?![\w-])(?:[ \t]*\{[^}\n]{1,80}\})?",
    re.IGNORECASE)


def since(store: ViewStore) -> str:
    """The moment the server began writing #now cards; older tags are history."""
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
    return read_rows(store.data_root / NOW_CSV)


def _id(agent_id: str, turn: int) -> str:
    return "nw_" + hashlib.sha256(f"{agent_id}|{turn}".encode()).hexdigest()[:8]


def title_of(message: str) -> str:
    """The message without its #now tag, on one line, cut at a word to 80 characters."""
    text = " ".join(_NOW_TAG_RE.sub(" ", message or "").split())
    if len(text) <= TITLE_CHARS:
        return text or "#now"
    cut = text[: TITLE_CHARS - 1]
    # A word cut in half goes; one that ends right at the limit stays.
    whole = text[TITLE_CHARS - 1] == " "
    head = cut if whole or " " not in cut[TITLE_CHARS // 2:] else cut.rsplit(" ", 1)[0]
    return head.rstrip(" ,.;:—-") + "…"


def adopt(store: ViewStore) -> list[dict[str, str]]:
    """Write every #now card an agent left unwritten. Idempotent; safe on every read."""
    with _lock:
        return _adopt_locked(store)


def _adopt_locked(store: ViewStore) -> list[dict[str, str]]:
    start = since(store)
    tags = store.query(
        "SELECT project, agent_id, session_id, turn, at_ts, column_, lane, answered, body "
        "FROM now_tags WHERE at_ts >= ? ORDER BY agent_id, turn", (start,))
    if not tags:
        return []
    path = store.data_root / NOW_CSV
    known = {r.get("id") for r in read_rows(path)}
    # The agent's chance is over once it answered this turn or a later one.
    open_ = [t for t in tags if str(t["answered"] or "")
             and _id(str(t["agent_id"] or ""), int(t["turn"] or 0)) not in known]
    if not open_:
        return []
    written = {(a, n) for a, n, _ in written_by_agents(store, {str(t["agent_id"] or "") for t in open_})}
    added: list[dict[str, str]] = []
    for tag in open_:
        agent, turn = str(tag["agent_id"] or ""), int(tag["turn"] or 0)
        rid = _id(agent, turn)
        if (agent, turn) in written:
            continue
        task_id = _write_card(store, tag)
        if not task_id:
            continue
        row = {"id": rid, "task_id": task_id, "project": str(tag["project"] or ""), "agent_id": agent,
               "session_id": str(tag["session_id"] or ""), "turn": str(turn), "at": str(tag["at_ts"] or ""),
               "applied_at": now_iso(), "column": str(tag["column_"] or "")}
        append_row(path, NOW_COLUMNS, row)
        known.add(rid)
        added.append(row)
    if added:
        store.rebuild()
    return added


def _write_card(store: ViewStore, tag: dict) -> str:
    """The card the agent would have written; "" when the lane is not on the board."""
    from fastapi import HTTPException, Response

    from .csvio import rewrite_rows
    from .entities import ENTITIES
    from .routers.tasks_extra import _lane_for, tasks_create
    from .taskevents import append_events

    project, agent = str(tag["project"] or ""), str(tag["agent_id"] or "")
    column = str(tag["column_"] or "doing")
    try:
        lane = _lane_for(store, project, "now", str(tag["lane"] or ""))
    except HTTPException:
        return ""                        # the agent asks the operator which lane
    try:
        at = datetime.fromisoformat(str(tag["at_ts"]))
    except ValueError:
        at = datetime.now()
    body = {
        "project": project, "title": title_of(str(tag["body"] or "")), "status": column,
        "created_date": at.strftime("%y%m-%d"), "created_time": at.strftime("%H:%M"),
        "description": str(tag["body"] or ""),
    }
    if lane:
        body["lane"] = body["assignee"] = lane
    if column == "doing":
        body["today_on"] = at.date().isoformat()
    out = tasks_create(Response(), body, store)
    task_id = str((out.get("metadata") or {}).get("id") or "")
    if not task_id:
        return ""
    # The card is the chat's: its agent can retitle it, and the chat's page lists it.
    rewrite_rows(store.data_root / ENTITIES["task"].csv, ENTITIES["task"].columns,
                 lambda rs: _own(rs, task_id, agent))
    if out.get("existing"):
        # The id comes from the message: a retry after a write that stopped
        # half way finds the same card, which already has its history.
        return task_id
    verb, tagname = ("started", "#now") if column == "doing" else ("filed", f"#now-{column}")
    append_events(store, task_id, "operator", [
        (verb, "", f"in the chat, with {tagname} ({agent}#{tag['turn']}); "
                   "the agent wrote no card, so the server did, titled with the message's start"),
    ])
    return task_id


def _own(rs: list[dict[str, str]], task_id: str, agent: str) -> bool:
    for r in rs:
        if r.get("id") == task_id and not r.get("agent_id"):
            r["agent_id"] = agent
            return True
    return False


def written_by_agents(store: ViewStore, agents: set[str]) -> list[tuple[str, int, str]]:
    """(agent, turn, task) for each card an agent wrote on the operator's #now:
    the turn is the one the card was written in, read from its history."""
    from .sessions import chat_path, parse_turns

    marks = ",".join("?" for _ in WRITTEN_FIELDS)
    found = store.query(
        "SELECT e.task_id, e.timestamp, t.agent_id FROM task_events_mutual e "
        f"JOIN tasks_mutual t ON t.id = e.task_id WHERE e.field IN ({marks})", WRITTEN_FIELDS)
    server = {r.get("task_id") for r in rows(store)}
    out: list[tuple[str, int, str]] = []
    turns_of: dict[str, list] = {}
    for r in found:
        agent = str(r["agent_id"] or "")
        if agent not in agents or str(r["task_id"]) in server:
            continue
        if agent not in turns_of:
            path = chat_path(store, agent)
            try:
                turns_of[agent] = parse_turns(path) if path else []
            except OSError:
                turns_of[agent] = []
        try:
            at = datetime.fromisoformat(str(r["timestamp"])).replace(tzinfo=None)
        except ValueError:
            continue
        before = [t.number for t in turns_of[agent] if t.at.replace(tzinfo=None) <= at]
        if before:
            out.append((agent, before[-1], str(r["task_id"])))
    return out


def server_cards(store: ViewStore) -> list[tuple[str, int, str]]:
    """(agent, turn, task) for each card the server wrote, exact from the ledger."""
    return [(r.get("agent_id") or "", int(r.get("turn") or 0), r.get("task_id") or "")
            for r in rows(store) if r.get("task_id")]

