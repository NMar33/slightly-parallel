"""#undo — the operator archives entries that were made by mistake.

A tag typed or pasted by accident makes an entry nobody wanted: a pasted
announcement that mentions #vision and #rule keeps a vision and a rule.
``#undo`` takes them back, and because archiving hides entries from every
page and from the agents' files, the server lets it happen only on the
operator's word, twice:

1. **the request** — ``#undo <what was the mistake>`` in an operator's
   message. Without one in the agent's chat, nothing is proposed.
2. **the proposal** — the agent lists the candidates (``candidates``), the
   operator answers with numbers, and the agent sends the chosen ids
   (``propose``). The server answers the confirmation text the agent shows:
   what goes to the archive, with a warning and the reply that confirms.
3. **the confirmation** — ``#undo-yes`` in the operator's very next message
   after the proposal. ``apply`` archives only then. Any other next message
   cancels the request; no next message yet is refused as not confirmed.

Both checks read the captured chat (chat.md), which only the capture hook
writes: an agent cannot make the operator's words appear.

Archiving keeps every row. A rule, skill or artifact moves to its own
``archived`` status, which its page already shows and restores; a vision,
problem or entry point gets ``archived_at`` and leaves the lists and the
sets written into AGENTS.md; a prompt gets both, as its library does; a
task gets ``archived_at``, as the board's archive does. ``restore`` undoes
one entry. The ledger ``undo.csv`` keeps one row per request.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .date_utils import now_iso, today_yymm_dd
from .db import ViewStore
from .entities import ENTITIES
from .hookshared import command_text, plain_text
from .sessions import Turn, _operator_text, parse_turns

UNDO_CSV = "undo.csv"
UNDO_COLUMNS: tuple[str, ...] = (
    "id", "project", "agent_id", "turn", "at", "hint", "state",
    "proposal", "proposed_turn", "confirmed_turn", "applied_at", "archived",
)
# state: open (asked) · proposed (waiting for #undo-yes) · done · cancelled

# ``#undo`` asks, ``#undo-yes`` confirms; neither fires inside ``##undo``,
# ``#undone`` or ``#undo-yes-please``. The hook's command table holds the
# same two words (scripts/hooks/capture.py).
UNDO_TAG_RE = re.compile(r"(?<![\w#])#undo(-yes)?(?![\w-])", re.IGNORECASE)

# What can be archived, by id prefix. ar_ is also an architecture form's
# prefix: an id is an artifact only when the artifacts ledger holds it.
KINDS: dict[str, str] = {
    "vs_": "vision", "rl_": "rule", "pb_": "problem", "ep_": "entrypoint",
    "sk_": "skill", "ar_": "artifact", "pm_": "prompt", "tk_": "task",
}
# Kinds whose own status has an archived value, shown and restored on their page.
STATUS_ARCHIVED = ("rule", "skill", "artifact", "prompt")
# Kinds hidden by archived_at alone: the list reads leave them out.
HIDDEN_BY_DATE = ("vision", "problem", "entrypoint")

CONFIRM = "#undo-yes"
MAX_CANDIDATES = 30
_lock = threading.Lock()


class UndoRefused(Exception):
    """A step the operator has not asked for, or has not confirmed."""


def _ledger(store: ViewStore) -> list[dict[str, str]]:
    return read_rows(store.data_root / UNDO_CSV)


def _rid(agent_id: str, turn: int) -> str:
    return "ud_" + hashlib.sha256(f"{agent_id}|{turn}".encode()).hexdigest()[:8]


def _turns(store: ViewStore, agent_id: str) -> list[Turn]:
    from .keeplib import _chat_path

    path = _chat_path(store, agent_id)
    return parse_turns(path) if path is not None else []


def _tags(t: Turn) -> set[str]:
    """{"ask"} / {"yes"} / both — the undo tags in the operator's words of a turn."""
    text = _operator_text(t)
    if "#undo" not in text.lower():
        return set()
    return {"yes" if m.group(1) else "ask" for m in UNDO_TAG_RE.finditer(command_text(text))}


def _hint(t: Turn) -> str:
    body = UNDO_TAG_RE.sub("", plain_text(_operator_text(t))).strip()
    return " ".join(body.split())[:300]


def _request(store: ViewStore, agent_id: str, turns: list[Turn]) -> dict[str, str]:
    """The live request of this chat: the last #undo, in the ledger.
    Refused when the chat has none, or the last one is finished."""
    asked = [t for t in turns if "ask" in _tags(t)]
    if not asked:
        raise UndoRefused(
            "no #undo request in this chat: archiving runs only after the operator types "
            "#undo and says what was the mistake")
    t = asked[-1]
    rid = _rid(agent_id, t.number)
    row = next((r for r in _ledger(store) if r.get("id") == rid), None)
    if row is None:
        row = {
            "id": rid, "project": "", "agent_id": agent_id, "turn": str(t.number),
            "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"), "hint": _hint(t), "state": "open",
            "proposal": "", "proposed_turn": "", "confirmed_turn": "", "applied_at": "",
            "archived": "",
        }
        for a in store.agents():
            if str(a.get("agent_id") or "") == agent_id:
                row["project"] = str(a.get("project") or "")
        append_row(store.data_root / UNDO_CSV, UNDO_COLUMNS, row)
    if row.get("state") in ("done", "cancelled"):
        raise UndoRefused(
            f"the last #undo request of this chat is {row['state']}: the operator types #undo again to start a new one")
    return row


def _save(store: ViewStore, rid: str, changes: dict[str, str]) -> None:
    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == rid:
                r.update(changes)
                return True
        return False
    rewrite_rows(store.data_root / UNDO_CSV, UNDO_COLUMNS, mutate)


# ---------------------------------------------------------------------------
# What could be archived
# ---------------------------------------------------------------------------


def _kind_of(store: ViewStore, eid: str) -> str:
    kind = KINDS.get(eid[:3], "")
    if kind == "artifact" and store.query_one(
            f"SELECT id FROM {ENTITIES['artifact'].view} WHERE id = ?", (eid,)) is None:
        return ""
    return kind


def _row(store: ViewStore, kind: str, eid: str) -> dict[str, Any] | None:
    return store.query_one(f"SELECT * FROM {ENTITIES[kind].view} WHERE id = ?", (eid,))


def _archived(kind: str, row: dict[str, Any]) -> bool:
    # A kind with an archived status answers by it: its page restores by
    # status alone and leaves the date behind.
    status = str(row.get("status") or "").lower()
    if kind in STATUS_ARCHIVED:
        return status == "archived"
    if kind == "task" and status == "done-archived":
        return True
    return bool(str(row.get("archived_at") or "").strip())


def _title(kind: str, row: dict[str, Any]) -> str:
    text = str(row.get("title") if kind in ("prompt", "task") else row.get("l1") or row.get("name") or "")
    return " ".join(text.split())[:120]


def _entry(kind: str, row: dict[str, Any], agent_id: str) -> dict[str, Any]:
    return {
        "kind": kind, "id": str(row["id"]), "title": _title(kind, row),
        "created": f"{row.get('created_date') or ''} {row.get('created_time') or ''}".strip(),
        "turn": int(row.get("source_turn") or 0) or None,
        "status": str(row.get("status") or ""),
        "interpreted": int(row.get("versions_n") or 0) > 0 if "versions_n" in row else None,
        "this_chat": str(row.get("agent_id") or "") == agent_id,
        "agent_id": str(row.get("agent_id") or ""),
    }


def candidates(store: ViewStore, agent_id: str) -> dict[str, Any]:
    """The live request and the entries it could mean: this chat's first,
    newest first, then the project's other entries of the last days."""
    from . import keeplib, promptlib

    with _lock:
        turns = _turns(store, agent_id)
        req = _request(store, agent_id, turns)
    keeplib.adopt(store)
    promptlib.adopt(store)
    project = req.get("project") or ""
    found: list[dict[str, Any]] = []
    for kind in ("vision", "rule", "problem", "entrypoint", "skill", "artifact", "prompt", "task"):
        ent = ENTITIES[kind]
        rows = store.query(
            f"SELECT * FROM {ent.view} WHERE project = ? AND (agent_id = ? OR created_date >= ?) "
            "ORDER BY created_date DESC, created_time DESC LIMIT 60",
            (project, agent_id, _days_ago(2)))
        for r in rows:
            if kind == "task" and str(r.get("status") or "") not in ("agent", "doing", "todo", "unclassified", "backlog", "next"):
                continue
            if not _archived(kind, r):
                found.append(_entry(kind, r, agent_id))
    found.sort(key=lambda e: e["created"], reverse=True)
    found.sort(key=lambda e: not e["this_chat"])
    found = found[:MAX_CANDIDATES]
    for n, e in enumerate(found, 1):
        e["n"] = n
    return {
        "request": {"id": req["id"], "turn": int(req["turn"]), "said": req["hint"], "state": req["state"]},
        "candidates": found,
        "next": (
            "Show the operator the candidates as a numbered list: number, kind and id, title, "
            "when, and whether it came from this chat. Mark the ones that fit what they said. "
            "Ask them to answer with the numbers. Then call undo_propose with the chosen ids."),
    }


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta

    d = datetime.now() - timedelta(days=days)
    return d.strftime("%y%m-%d")


# ---------------------------------------------------------------------------
# Proposal, confirmation, archive
# ---------------------------------------------------------------------------


def propose(store: ViewStore, agent_id: str, ids: list[str]) -> dict[str, Any]:
    """Record what the operator chose; answer the confirmation to show."""
    ids = [str(i).strip() for i in ids if str(i).strip()]
    if not ids:
        raise UndoRefused("ids is empty: send the ids of the entries the operator chose")
    with _lock:
        turns = _turns(store, agent_id)
        req = _request(store, agent_id, turns)
        entries: list[dict[str, Any]] = []
        for eid in dict.fromkeys(ids):
            kind = _kind_of(store, eid)
            if not kind:
                raise UndoRefused(f"{eid}: not an entry #undo can archive (visions, rules, problems, "
                                  "entry points, skills, artifacts, prompts, tasks)")
            row = _row(store, kind, eid)
            if row is None:
                raise UndoRefused(f"{eid}: no such {kind}")
            if _archived(kind, row):
                raise UndoRefused(f"{eid}: already archived")
            entries.append(_entry(kind, row, agent_id))
        last = turns[-1].number if turns else 0
        _save(store, req["id"], {"state": "proposed", "proposal": ",".join(e["id"] for e in entries),
                                 "proposed_turn": str(last)})
    lines = "\n".join(f"- {e['kind']} {e['id']} — {e['title']}" for e in entries)
    confirm = (
        f"⚠ These {len(entries)} entries go to the archive:\n{lines}\n\n"
        "They leave the pages and the agents' files; nothing is deleted, and each can be restored.\n"
        f"To archive them, reply with {CONFIRM}. Any other reply cancels."
    )
    return {"request": req["id"], "proposed": entries, "confirm": confirm,
            "next": f"Show the operator the confirm text as it is. On their {CONFIRM}, call undo_apply."}


def apply(store: ViewStore, agent_id: str) -> dict[str, Any]:
    """Archive the proposal — only when the operator's next message says #undo-yes."""
    with _lock:
        turns = _turns(store, agent_id)
        req = _request(store, agent_id, turns)
        if req.get("state") != "proposed":
            raise UndoRefused("nothing is proposed yet: call undo_propose with the operator's choice first")
        after = int(req.get("proposed_turn") or 0)
        nxt = next((t for t in turns if t.number > after), None)
        if nxt is None:
            raise UndoRefused(f"not confirmed: the operator has not answered yet. Archiving waits for {CONFIRM}")
        if "yes" not in _tags(nxt):
            _save(store, req["id"], {"state": "cancelled"})
            raise UndoRefused(
                f"not confirmed: the operator's answer has no {CONFIRM}, so the request is cancelled. "
                "Nothing was archived")
        done: list[dict[str, str]] = []
        for eid in [i for i in (req.get("proposal") or "").split(",") if i]:
            kind = _kind_of(store, eid)
            row = _row(store, kind, eid) if kind else None
            if row is None or _archived(kind, row):
                continue
            _archive(store, kind, eid, agent_id)
            done.append({"kind": kind, "id": eid, "from_status": str(row.get("status") or "")})
        _save(store, req["id"], {"state": "done", "confirmed_turn": str(nxt.number),
                                 "applied_at": now_iso(), "archived": json.dumps(done)})
    store.rebuild()
    return {"request": req["id"], "archived": done,
            "next": "Tell the operator in one line what went to the archive, and that each can be "
                    "restored (undo_restore with its id)."}


def _archive(store: ViewStore, kind: str, eid: str, actor: str) -> None:
    if kind == "task":
        from .routers.tasks_extra import _set_archived
        _set_archived(store, eid, today_yymm_dd(), actor)
        return
    ent = ENTITIES[kind]
    stamp = today_yymm_dd()

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == eid:
                r["archived_at"] = stamp
                if kind in STATUS_ARCHIVED:
                    r["status"] = "archived"
                return True
        return False
    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)


def restore(store: ViewStore, eid: str, actor: str) -> dict[str, Any]:
    """Bring one archived entry back, with the status it had."""
    kind = _kind_of(store, eid)
    if not kind:
        raise UndoRefused(f"{eid}: not an entry #undo archives")
    if kind == "task":
        from .routers.tasks_extra import _set_archived
        _set_archived(store, eid, "", actor)
        return {"restored": eid, "kind": kind}
    before = ""
    for r in _ledger(store):
        for a in json.loads(r.get("archived") or "[]"):
            if a.get("id") == eid:
                before = a.get("from_status") or ""
    ent = ENTITIES[kind]
    hit: list[bool] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == eid:
                r["archived_at"] = ""
                if kind in STATUS_ARCHIVED and str(r.get("status") or "") == "archived":
                    r["status"] = before if before and before != "archived" else _ACTIVE[kind]
                hit.append(True)
                return True
        return False
    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    if not hit:
        raise UndoRefused(f"{eid}: no such {kind}")
    store.rebuild()
    return {"restored": eid, "kind": kind}


_ACTIVE = {"rule": "active", "skill": "active", "artifact": "active", "prompt": "active"}


def requests(store: ViewStore) -> list[dict[str, str]]:
    return _ledger(store)
