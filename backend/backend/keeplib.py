"""Kept messages — the visions, rules and problems the operator tags in chat.

``#vision``, ``#rule`` and ``#problem`` work the way ``#prompt`` does: the
message is already in the chat log verbatim, so the tag is the whole act of
keeping it, and nobody is asked to copy it out. The server adopts every
tagged turn into the ledger that kind already has — visions.csv, rules.csv,
problems.csv — so every reader of those (the pages, the API, the sets that
are written into agents' files) sees a kept row without a second shape to
learn.

A kept row carries three things:

- the message, verbatim: the entry's L4, never edited;
- the turns around it: read from the chat log when the entry is opened and
  never stored, so they cannot disagree with the log;
- the interpretation: the message read with its context, written by the
  agent when the capture hook asks and edited by the operator afterwards.
  Every write is a version, in the same document format as a prompt's; the
  current one is the entry's L2.

``#skill`` is kept the same way; its version history holds SKILL.md drafts
rather than interpretations (skilllib.py).
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .csvio import append_if_absent, append_row, read_rows, rewrite_rows
from . import limits
from .db import ViewStore
from .docs_md import build_detail, read_detail, resolve_under, safe_ref_part
from .entities import ENTITIES
from .file_safety import acquire_flock, atomic_write, lock_path
from .promptlib import Version, _stamp, parse_doc, render_doc
from .sessions import Turn, parse_turns

# The tags that are adopted, each into the entity of the same name.
KINDS: tuple[str, ...] = ("vision", "rule", "problem", "entrypoint", "skill", "artifact")

# What a kept row starts as beyond the shared columns. A rule is in force
# from the moment the operator writes it; a problem is open until solved.
_DEFAULTS: dict[str, dict[str, str]] = {
    "vision": {},
    "rule": {"status": "active"},
    "problem": {"status": "open"},
    # An entry point is open while the topic is worked on; closed when it is done.
    "entrypoint": {"status": "open"},
    # A skill is a draft until the operator has read it (skilllib.py).
    "skill": {"status": "draft"},
    # An artifact is a draft until the agent has written the folder and
    # made the record (artifactlib.py).
    "artifact": {"status": "draft"},
}

MAX_TEXT = limits.MAX_TEXT
MAX_NOTE = limits.MAX_NOTE
CONTEXT_TURNS = 3
VERSIONS_DIR = "kept_versions"

# Rows that carry a record and a versioned interpretation: kept from a tagged
# message, a rule the operator wrote from a problem (which borrows the
# problem's message and context), or an example a new data root starts with
# (examples.py — a message and versions, no chat).
SOURCES: tuple[str, ...] = ("captured", "problem", "demo")


def keep_id(kind: str, project: str, agent_id: str, turn: int) -> str:
    """Identity is the tagged turn: one chat, one turn number, one kind.

    Not the session: sessions regroup when the gap setting changes, and the
    capture hook names this id the moment the message arrives, before any
    session exists. ``scripts/hooks/capture.py:keep_id`` computes the same
    hash; a test holds the two equal.
    """
    seed = f"{kind}|{project}|{agent_id}|{turn}"
    return ENTITIES[kind].id_prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Harvesting
# ---------------------------------------------------------------------------

# Adoption rides list reads, and two can land at once (the page's poll and an
# agent reading its rules). Same guard as the prompt library.
_adopt_lock = threading.Lock()


def row_of(store: ViewStore, kind: str, item_id: str) -> dict | None:
    """One kept entry by id — adopting first when it is not there yet: the
    hook names a kept id to the agent before any list read has adopted it."""
    sql = f"SELECT * FROM {ENTITIES[kind].view} WHERE id = ?"
    row = store.query_one(sql, (item_id,))
    if row is None:
        adopt(store)
        row = store.query_one(sql, (item_id,))
    return row


def adopt(store: ViewStore) -> list[str]:
    """Bring every tagged turn into its ledger. Idempotent; safe on every read."""
    with _adopt_lock:
        return _adopt_locked(store)


def _adopt_locked(store: ViewStore) -> list[str]:
    ph = ",".join("?" * len(KINDS))
    marks = store.query(
        "SELECT kind, project, agent_id, session_id, turn, at_ts, title, body "
        f"FROM keep_marks WHERE kind IN ({ph}) ORDER BY at_ts",
        KINDS,
    )
    if not marks:
        return []
    # The check reads the file as well as the view: a row appended a moment
    # ago by the other reader is not in a view that has not rebuilt yet.
    known: dict[str, set[str]] = {}
    for kind in KINDS:
        ent = ENTITIES[kind]
        ids = {str(r["id"]) for r in store.query(f"SELECT id FROM {ent.view}")}
        ids |= {str(r.get("id") or "") for r in read_rows(store.data_root / ent.csv)}
        known[kind] = ids

    added: list[str] = []
    for m in marks:
        kind = str(m["kind"])
        ent = ENTITIES[kind]
        project, agent = str(m["project"] or ""), str(m["agent_id"] or "")
        turn = int(m["turn"] or 0)
        kid = keep_id(kind, project, agent, turn)
        body = str(m["body"] or "").strip()
        if kid in known[kind] or not body:
            continue
        date, time = _stamp(str(m["at_ts"]))
        md_ref = (
            f"{ent.detail_dir}/{safe_ref_part(date.replace('-', ''), 'nodate')}-"
            f"{safe_ref_part(time.replace(':', ''), '0000')}__"
            f"{safe_ref_part(project.lower())}__{safe_ref_part(agent.lower())}__{kid}.md"
        )
        row: dict[str, Any] = {
            "created_date": date, "created_time": time, "project": project,
            "agent_id": agent, "l1": str(m["title"] or "")[:limits.MAX_TITLE],
            **_DEFAULTS[kind],
            "md_ref": md_ref, "source": "captured",
            "session_id": str(m["session_id"] or ""), "source_turn": turn,
            "versions_n": 0,
        }
        path = store.data_root / md_ref
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, build_detail({**row, "l4": body}, kid))
        append_row(store.data_root / ent.csv, ent.columns, {"id": kid, **row})
        known[kind].add(kid)
        added.append(kid)
    if added:
        store.rebuild()
    return added


# ---------------------------------------------------------------------------
# The interpretation
# ---------------------------------------------------------------------------


def versions_ref(kid: str) -> str:
    return f"{VERSIONS_DIR}/{kid}.md"


def read_versions(store: ViewStore, kid: str) -> list[Version]:
    try:
        text = (store.data_root / versions_ref(kid)).read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_doc(text)[1]


def interpret(
    store: ViewStore, kind: str, row: dict[str, Any], text: str, note: str = "",
    *, by_agent: bool, now: datetime | None = None,
) -> list[Version]:
    """Write the interpretation: a new version, and the entry's L2.

    A write identical to the current one is not a version — the history
    answers "what changed", and a no-op entry in it is a lie. The message
    (L4) is never touched.
    """
    body = (text or "").strip()
    if not body:
        raise ValueError("an interpretation cannot be empty")
    if len(body) > MAX_TEXT:
        raise ValueError(f"an interpretation is at most {MAX_TEXT} characters")
    kid = str(row["id"])
    doc = resolve_under(store.data_root, str(row.get("md_ref") or ""))
    if doc is None:
        raise ValueError(f"{kid} has no detail document")

    path = store.data_root / versions_ref(kid)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Read, number and write under one lock: an agent's interpretation and
    # an edit on the page at the same moment were both version n+1, and one
    # of them was lost.
    with acquire_flock(lock_path(path)):
        versions = read_versions(store, kid)
        if versions and versions[-1].text == body:
            return versions
        at = now or datetime.now()
        versions.append(Version(
            n=versions[-1].n + 1 if versions else 1,
            at=f"{at.year % 100:02d}{at.month:02d}-{at.day:02d} {at:%H:%M}",
            how="interpreted" if by_agent else "edited",
            note=(note or "").strip()[:MAX_NOTE],
            text=body,
        ))
        atomic_write(path, render_doc(f"---\nid: {kid}\nkind: {kind}\n---\n", versions))
        # The document and the count follow under the same lock: written
        # after it, two writers at once left the older text in the document
        # and the count one short of the versions.
        _l2, l3, l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
        fields = {k: v for k, v in row.items() if k != "id" and v not in (None, "")}
        fields["versions_n"] = len(versions)
        atomic_write(doc, build_detail({**fields, "l2": body, "l3": l3, "l4": l4}, kid))
        _set_fields(store, kind, kid, {"versions_n": len(versions)})
    return versions


def _set_fields(store: ViewStore, kind: str, kid: str, fields: dict[str, Any], rebuild: bool = True) -> None:
    """Set columns of one kept row (a rule, problem, vision, artifact or
    skill) by id. ``rebuild=False`` for a caller that writes more first."""
    ent = ENTITIES[kind]
    values = {k: str(v) for k, v in fields.items()}

    def mutate(rows: list[dict[str, str]]) -> bool:
        touched = False
        for r in rows:
            if r.get("id") == kid and any(r.get(k) != v for k, v in values.items()):
                r.update(values)
                touched = True
        return touched

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    if rebuild:
        store.rebuild()


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _chat_path(store: ViewStore, agent_id: str) -> Path | None:
    for a in store.agents():
        if str(a.get("agent_id") or "") == agent_id:
            path = Path(a.get("_chat_path") or "")
            return path if path.exists() else None
    return None


def _turn(t: Turn) -> dict[str, Any]:
    return {"n": t.number, "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
            "user": t.user_summary, "agent": t.agent_summary}


def record(store: ViewStore, kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """The kept message, the turns either side of it, every interpretation.

    A rule written from a problem has no message of its own: it reads the
    problem's message and turns, and keeps its own versions.
    """
    kid = str(row["id"])
    origin = row
    if str(row.get("source") or "") in ("problem", "demo") and row.get("related_incident"):
        origin = store.query_one(
            f"SELECT * FROM {ENTITIES['problem'].view} WHERE id = ?", (str(row["related_incident"]),),
        ) or row
    _l2, _l3, message = read_detail(store.data_root, str(origin.get("md_ref") or ""))
    versions = read_versions(store, kid)
    out: dict[str, Any] = {
        "kind": kind,
        "from": str(origin["id"]) if origin is not row else None,
        "message": message,
        "turn": None, "before": [], "after": [],
        "versions": [v.as_dict() for v in versions],
        "current": versions[-1].as_dict() if versions else None,
    }
    if str(origin.get("source") or "") == "demo":
        # An example has no chat log; examples.py holds the turns around it.
        from .examples import context_for
        out.update(context_for(str(origin["id"])) or {})
        return out
    turn = int(origin.get("source_turn") or 0)
    path = _chat_path(store, str(origin.get("agent_id") or ""))
    turns = parse_turns(path) if path is not None else []
    at = next((i for i, t in enumerate(turns) if t.number == turn), None)
    if at is not None:
        out["turn"] = _turn(turns[at])
        out["before"] = [_turn(t) for t in turns[max(0, at - CONTEXT_TURNS):at]]
        out["after"] = [_turn(t) for t in turns[at + 1:at + 1 + CONTEXT_TURNS]]
    return out


def enrich(store: ViewStore, kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """Lens detail: a kept row carries its record; a posted one carries nothing."""
    if str(row.get("source") or "") not in SOURCES:
        return {}
    return {"kept": record(store, kind, row)}


# ---------------------------------------------------------------------------
# A rule from a problem
# ---------------------------------------------------------------------------


def rule_from_problem(
    store: ViewStore, problem: dict[str, Any], text: str, title: str = "",
    *, now: datetime | None = None,
) -> str:
    """The operator writes a rule on the basis of a problem. Returns the rule id.

    Never automatic: a problem stays a problem, open or resolved as it was.
    The rule points back at it (``related_incident``), borrows its message
    and context for the record, and starts its own versions with the
    operator's text as version 1. The same text from the same problem is
    the same rule — a second click does not make a second row.
    """
    body = (text or "").strip()
    if not body:
        raise ValueError("the rule cannot be empty")
    if len(body) > MAX_TEXT:
        raise ValueError(f"a rule is at most {MAX_TEXT} characters")
    at = now or datetime.now()
    date = f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}"
    time = at.strftime("%H:%M")
    pid = str(problem["id"])
    ent = ENTITIES["rule"]
    kid = ent.id_prefix + hashlib.sha256(f"problem|{pid}|{body}".encode()).hexdigest()[:8]
    if any(r.get("id") == kid for r in read_rows(store.data_root / ent.csv)):
        return kid
    head = " ".join((title or body.split("\n", 1)[0]).split())[:limits.MAX_TITLE]
    project = str(problem.get("project") or "")
    md_ref = (
        f"{ent.detail_dir}/{safe_ref_part(date.replace('-', ''), 'nodate')}-"
        f"{safe_ref_part(time.replace(':', ''), '0000')}__{safe_ref_part(project.lower())}__operator__{kid}.md"
    )
    _l2, _l3, message = read_detail(store.data_root, str(problem.get("md_ref") or ""))
    row: dict[str, Any] = {
        "created_date": date, "created_time": time, "project": project,
        "agent_id": "operator", "l1": head, "status": "active",
        "related_incident": pid, "md_ref": md_ref, "source": "problem",
        "session_id": str(problem.get("session_id") or ""),
        "source_turn": int(problem.get("source_turn") or 0),
        "versions_n": 1, "tags": str(problem.get("tags") or ""),
    }
    path = store.data_root / md_ref
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, build_detail({**row, "l2": body, "l4": message}, kid))
    versions_path = store.data_root / versions_ref(kid)
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(versions_path, render_doc(f"---\nid: {kid}\nkind: rule\n---\n", [
        Version(1, f"{date} {time}", "edited", f"from {pid}", body),
    ]))
    # Looked for again and written in one locked step: two clicks at once
    # both passed the look above and wrote the rule twice.
    if append_if_absent(store.data_root / ent.csv, ent.columns, {"id": kid, **row}) is None:
        store.rebuild()
    return kid
