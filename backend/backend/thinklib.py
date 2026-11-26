"""#think — a task the operator thinks through himself.

A task with the think mark is the operator's to think about. An agent never
picks it up, starts it or finishes it: the server refuses an agent's status
change, lane or assignee change, its report of done, its archive and moving
it to another project while the mark is on (``refusal``). An agent may still read it, comment, write
notes, attach evidence and links, propose options and ask.

The mark is two task columns: ``think_at`` (when it was set) and
``think_by`` (who set it: the operator). Only the operator sets or removes
it:

- ``#think`` in the operator's message, beside ``#now`` / ``#now-todo`` /
  ``#task``: the task that message makes gets the mark when it is written
  (tasklib.create_task for the agent's card, nowlib for the server's);
- ``#think tk_…`` (several ids allowed): those tasks get it;
- ``#think-off tk_…``: those tasks lose it;
- the board and the task window: the badge's ×, or ``think`` in an update.

The chat tags are applied by the server like ``#done`` (``adopt``): the
capture already holds the message. The ledger ``think.csv`` keeps one row
per (tag, task), so a tag is applied once and the mark the operator removed
on the board does not come back from the old message; tags written before
the feature existed are never applied (``think.json`` holds the moment it
first ran).
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import TYPE_CHECKING, Any

from .csvio import as_int, read_rows, rewrite_rows
from .date_utils import now_iso
from .hookshared import THINK_OFF_TAG_RE, THINK_TAG_RE  # noqa: F401 — one copy, the hook reads it too

if TYPE_CHECKING:  # pragma: no cover
    from .db import ViewStore

THINK_CSV = "think.csv"
STATE = "think.json"
THINK_COLUMNS: tuple[str, ...] = (
    "id", "task_id", "kind", "project", "agent_id", "session_id", "turn", "at", "applied_at", "result",
)
# result: set · cleared · already (the mark was as asked) · unknown (no such
# task) · unnamed (no task named and no task made by the message)

#: What the operator sees in a refusal and in the task's history.
MARK = "think"
WHO = "operator"

_lock = threading.Lock()
log = logging.getLogger("sp.think")


def marked(row: dict[str, Any] | None) -> bool:
    return bool(row) and bool(str((row or {}).get("think_at") or "").strip())


def wants_mark(message: str) -> bool:
    """Whether an operator's message (as the commands read it) asks for the
    mark: ``#think`` in it, ``#think-off`` not counted."""
    return bool(THINK_TAG_RE.search(message or ""))


def mark_fields(at: str | None = None) -> dict[str, str]:
    return {"think_at": at or now_iso(), "think_by": WHO}


# ---------------------------------------------------------------------------
# The gate: one helper every task write path asks
# ---------------------------------------------------------------------------


def refusal(store: "ViewStore", task_id: str, actor: str, what: str,
            asked: dict[str, Any] | None = None) -> None:
    """Refuse an agent's ``what`` on a task with the think mark; the operator
    and the server's own hands pass. With ``asked`` (field → value), only a
    write that changes one of those fields is refused. A #think the operator
    just typed is applied first, so the mark is on before the agent's next
    call."""
    from .actors import is_agent, refuse_agent

    if not is_agent(actor):
        return
    # The chat the operator just typed in may not be in the store yet. A
    # failure here (an unreadable think.csv) is logged, never the agent's
    # error: the mark on the row is checked all the same.
    # Without the since-stamp no list was ever read here: every tag would be
    # history (the stamp would be made now), so there is nothing to apply,
    # and an agent's write must not be the read that writes it.
    try:
        if (store.data_root / STATE).exists():
            store.rebuild()
            adopt(store)
    except Exception:  # noqa: BLE001 — as deps.adopt_when_changed
        log.warning("the #think adoption failed; the mark on the row decides", exc_info=True)
    row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    if asked is not None and row is not None and all(
            str(v if v is not None else "") == str(row.get(k) or "") for k, v in asked.items()):
        return
    if marked(row):
        refuse_agent(
            f"{task_id} carries the operator's «{MARK}» mark: {what} is refused while it is on",
            "the operator thinks this task through himself. You may comment (task_update {id, comment}), "
            "add notes, evidence and links, propose options and ask the operator; only the operator "
            "removes the mark",
        )


# ---------------------------------------------------------------------------
# The chat tags, applied
# ---------------------------------------------------------------------------


def since(store: "ViewStore") -> str | None:
    from .nowlib import since_stamp
    return since_stamp(store.data_root / STATE, "#think")


def rows(store: "ViewStore") -> list[dict[str, str]]:
    return read_rows(store.data_root / THINK_CSV)


def _id(agent_id: str, turn: int, kind: str, task_id: str) -> str:
    return "th_" + hashlib.sha256(f"{agent_id}|{turn}|{kind}|{task_id}".encode()).hexdigest()[:8]


def adopt(store: "ViewStore") -> list[dict[str, str]]:
    """Apply every #think / #think-off not applied yet. Idempotent."""
    with _lock:
        return _adopt_locked(store)


def _adopt_locked(store: "ViewStore") -> list[dict[str, str]]:
    from .sessions import helper_ids

    start = since(store)
    if start is None:
        return []
    tags = store.query(
        "SELECT kind, project, agent_id, session_id, turn, at_ts, tasks, creates FROM think_tags "
        "WHERE at_ts >= ? ORDER BY at_ts, agent_id, turn", (start,))
    if not tags:
        return []
    path = store.data_root / THINK_CSV
    ledger = read_rows(path)
    settled = {(r.get("agent_id") or "", as_int(r.get("turn")), r.get("kind") or "") for r in ledger}
    # A helper's prompt was written by another agent: no operator's command.
    helpers = helper_ids(store)
    tags = [t for t in tags
            if (str(t["agent_id"] or ""), as_int(t["turn"]), str(t["kind"] or "")) not in settled
            and str(t["agent_id"] or "") not in helpers]
    if not tags:
        return []
    known = {str(t["id"]) for t in store.query("SELECT id FROM tasks_mutual")}
    added: list[dict[str, str]] = []
    # task → each mark asked for it, in the order the tags were typed.
    final: dict[str, list[tuple[bool, dict]]] = {}
    for tag in tags:
        kind = str(tag["kind"] or "")
        agent, turn = str(tag["agent_id"] or ""), as_int(tag["turn"])
        ids = [x for x in str(tag["tasks"] or "").split(",") if x]
        if not ids:
            # #think beside #now / #task: the card carries it from its
            # creation (tasklib.create_task); nothing named, nothing to do.
            added.append(_row(_id(agent, turn, kind, ""), "", tag,
                              "made" if kind == "think" and str(tag["creates"] or "") else "unnamed"))
            continue
        for tid in ids:
            if tid not in known:
                added.append(_row(_id(agent, turn, kind, tid), tid, tag, "unknown"))
                continue
            row = _row(_id(agent, turn, kind, tid), tid, tag, "")
            added.append(row)
            final.setdefault(tid, []).append((kind == "think", row))
    changed: dict[str, list[tuple[str, str, str]]] = {}
    if final:
        def mutate(rs: list[dict[str, str]]) -> bool:
            hit = False
            for r in rs:
                tid = r.get("id") or ""
                if tid not in final:
                    continue
                for on, led in final[tid]:
                    was = str(r.get("think_at") or "")
                    where = f"{led['agent_id']}#{led['turn']}"
                    if on and not was:
                        r.update(mark_fields())
                        changed.setdefault(tid, []).append(("think", "", f"set with #think in the chat ({where})"))
                        led["result"] = "set"
                        hit = True
                    elif not on and was:
                        r["think_at"] = r["think_by"] = ""
                        changed.setdefault(tid, []).append(("think", was, f"removed with #think-off in the chat ({where})"))
                        led["result"] = "cleared"
                        hit = True
                    else:
                        led["result"] = "already"
            return hit

        from .entities import ENTITIES
        ent = ENTITIES["task"]
        rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    for r in added:
        r["result"] = r["result"] or "already"
    # The tasks first, the ledger after: a refused rewrite leaves no row
    # saying it happened, and the tag is tried again at the next read.
    from .taskevents import append_events
    for tid, ch in changed.items():
        append_events(store, tid, WHO, ch)

    def record(rs: list[dict[str, str]]) -> bool:
        have = {r.get("id") for r in rs}
        new = [r for r in added if r["id"] not in have]
        rs.extend(new)
        return bool(new)

    rewrite_rows(path, THINK_COLUMNS, record)
    store.rebuild()
    return added


def _row(rid: str, tid: str, tag: Any, result: str) -> dict[str, str]:
    return {
        "id": rid, "task_id": tid, "kind": str(tag["kind"] or ""), "project": str(tag["project"] or ""),
        "agent_id": str(tag["agent_id"] or ""), "session_id": str(tag["session_id"] or ""),
        "turn": str(as_int(tag["turn"])), "at": str(tag["at_ts"] or ""), "applied_at": now_iso(),
        "result": result,
    }
