"""Publish — what shipped, worth telling (docs/publish.md).

A card starts from a message the operator tagged ``#publish``: the kept kind
``publish`` (keeplib: the message as typed, the text's versions). The tag is
an instruction to the agent of that chat: it writes the card in the same
turn with MCP ``publish_write`` — the text when asked (else the message is
the text), a context block under it, and what belongs to it (tasks, notes,
commits, files, images, links). Every write of the text or the context is a
version; whoever wrote it is kept (publish_writes.csv).

What a card carries is stored, never computed: the server does not read the
chat for a task, nor a task's commits and files. A card lives with the work:
``#publish pu_… <more>`` from any chat of the project adds the message to
that card (publish_sources.csv) instead of making a new one, and a card can
be merged into another (the merged card hides while the merge stands).

The operator's documents (a release note, a post, a video script …) hold
cards in numbered versions, each with the text as placed.

Ledgers (entities.PUBLISH_*_COLUMNS): publish_docs.csv, publish_versions.csv,
publish_items.csv, publish_attachments.csv, publish_sources.csv,
publish_writes.csv; files under publish_images/, publish_files/ and
publish_context/.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import corelib, keeplib, limits
from .actors import is_agent
from .answers import mint_id
from .csvio import append_if_absent, append_row, as_int, read_rows, rewrite_rows
from .date_utils import iso_moment, now_iso
from .db import ViewStore
from .docs_md import read_detail, resolve_under
from .entities import (
    ENTITIES, PUBLISH_ATTACHMENT_COLUMNS, PUBLISH_DOC_COLUMNS, PUBLISH_ITEM_COLUMNS, PUBLISH_SOURCE_COLUMNS,
    PUBLISH_VERSION_COLUMNS, PUBLISH_WRITE_COLUMNS,
)
from .file_safety import acquire_flock, atomic_write, lock_path
from .promptlib import Version, parse_doc, render_doc
from .story_images import checked_image

DOCS_FILE = "publish_docs.csv"
VERSIONS_FILE = "publish_versions.csv"
ITEMS_FILE = "publish_items.csv"
ATTACH_FILE = "publish_attachments.csv"
SOURCES_FILE = "publish_sources.csv"
WRITES_FILE = "publish_writes.csv"
IMAGES_DIR = "publish_images"
FILES_DIR = "publish_files"
CONTEXT_DIR = "publish_context"
MIGRATION_FILE = "publish_migration.json"
MIGRATION_VERSION = 1
ATTACH_MAX = 24
NAME_MAX = 80
TITLE_MAX = 120
TEXT_MAX = limits.MAX_TEXT
FILE_MAX = 25 * 1024 * 1024
STEP = 10
CARD_RE = re.compile(r"^pu_[0-9a-f]{8}$")
TASK_RE = re.compile(r"^tk_[0-9a-z][0-9a-z_-]{2,40}$")
NOTE_RE = re.compile(r"^nt_[0-9a-z_]{3,40}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
# `#publish pu_… more`: the card the message goes to, right after the tag.
APPEND_RE = re.compile(r"^\s*(pu_[0-9a-f]{8})\b[\s:,.—-]*", re.IGNORECASE)


class PublishRefused(Exception):
    """A write the page does not take; the router answers 422 with the text."""


def _rows(store: ViewStore, name: str) -> list[dict[str, str]]:
    return read_rows(store.data_root / name)


def _tag_free(text: str) -> str:
    """The message without its #publish tag (the card's text starts clean)."""
    return re.sub(r"(?<![\w#])#{1,3}publish(?![\w-])\s*", "", text or "", flags=re.IGNORECASE).strip()


def _live(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in rows if not (r.get("removed_at") or "").strip()]


def _iso(at: str) -> str:
    """A kept version's moment ("YYMM-DD HH:MM") as ISO, which the page reads everywhere."""
    day, _, hm = str(at or "").partition(" ")
    return iso_moment(day, hm) or str(at or "")


def _stamp(at: datetime) -> str:
    return f"{at.year % 100:02d}{at.month:02d}-{at.day:02d} {at:%H:%M}"


# ---------------------------------------------------------------------------
# Which card: an appended message's id and a merged card lead to the card
# ---------------------------------------------------------------------------


def _card_row(store: ViewStore, card_id: str) -> dict[str, Any] | None:
    return store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,))


def _merges(store: ViewStore) -> dict[str, str]:
    """merged card → the card it was merged into (live merges only)."""
    return {r["from_card"]: r["card_id"] for r in _live(_rows(store, SOURCES_FILE)) if r.get("from_card")}


def root_of(card_id: str, merges: dict[str, str]) -> str:
    """The card a card shows on: itself, or the end of its merges."""
    seen = {card_id}
    while card_id in merges and merges[card_id] not in seen:
        card_id = merges[card_id]
        seen.add(card_id)
    return card_id


def resolve(store: ViewStore, any_id: str) -> str:
    """The card an id names: a card, the id of a message appended to a card
    (the hook may name it before the server saw the card it goes to), or a
    merged card. '' when it names none. Adopts the chat logs first: the
    hook names a card the moment the message arrives."""
    any_id = str(any_id or "").strip()
    if not any_id.startswith("pu_"):
        return ""
    if _card_row(store, any_id) is None:
        keeplib.adopt(store)
    merges = _merges(store)
    if _card_row(store, any_id) is not None:
        return root_of(any_id, merges)
    src = next((s for s in _live(_rows(store, SOURCES_FILE)) if s.get("id") == any_id), None)
    if src is not None and _card_row(store, str(src.get("card_id") or "")) is not None:
        return root_of(str(src["card_id"]), merges)
    return ""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _card_rows(store: ViewStore, project: str) -> list[dict[str, Any]]:
    ent = ENTITIES["publish"]
    return store.query(
        f"SELECT * FROM {ent.view} WHERE project = ? AND COALESCE(archived_at, '') = '' "
        "ORDER BY created_date DESC, created_time DESC", (project,))


def _writers(store: ViewStore) -> dict[tuple[str, str, int], str]:
    return {(w.get("card_id") or "", w.get("part") or "", as_int(w.get("n"))): w.get("actor") or ""
            for w in _rows(store, WRITES_FILE)}


def _versions_out(versions: list[Version], card_id: str, part: str,
                  writers: dict[tuple[str, str, int], str]) -> list[dict[str, Any]]:
    out = []
    for v in versions:
        by = writers.get((card_id, part, v.n)) or ("operator" if v.how == "edited" else "agent")
        out.append({"n": v.n, "at": _iso(v.at), "text": v.text, "note": v.note, "by": by})
    return out


def _context_path(store: ViewStore, card_id: str) -> Path:
    return store.data_root / CONTEXT_DIR / card_id / "context.md"


def _context_versions(store: ViewStore, card_id: str) -> list[Version]:
    try:
        return parse_doc(_context_path(store, card_id).read_text(encoding="utf-8"))[1]
    except OSError:
        return []


def _card_text(store: ViewStore, row: dict[str, Any],
               writers: dict[tuple[str, str, int], str] | None = None) -> tuple[str, str, list[dict[str, Any]]]:
    """(message as typed, current text, versions) of a card."""
    _l2, _l3, message = read_detail(store.data_root, str(row.get("md_ref") or ""))
    message = _tag_free(message)
    cid = str(row["id"])
    versions = _versions_out(keeplib.read_versions(store, cid), cid, "text",
                             writers if writers is not None else _writers(store))
    text = str(versions[-1]["text"]) if versions else message
    return message, text, versions


def _source_text(text: str) -> str:
    """An appended message as the card shows it: no tag, no card id in front."""
    return APPEND_RE.sub("", _tag_free(text), count=1).strip()


def _attachment_view(store: ViewStore, a: dict[str, str], tasks: dict[str, dict[str, str]],
                     notes: dict[str, dict[str, str]]) -> tuple[str, dict[str, Any]]:
    kind, aid, by = a.get("kind") or "", a["id"], a.get("actor") or ""
    target, title = a.get("target") or "", a.get("title") or ""
    if kind == "image":
        return "images", {"url": f"/api/publishing/attachments/{aid}/file", "label": title,
                          "from": "attached", "id": aid, "by": by}
    if kind == "link":
        return "links", {"url": target, "label": title or target, "id": aid, "by": by}
    if kind == "file":
        return "files", {"id": aid, "name": title or Path(target).name, "path": a.get("source") or "",
                         "size": as_int(a.get("size")), "url": f"/api/publishing/attachments/{aid}/file", "by": by}
    if kind == "task":
        t = tasks.get(target) or {}
        return "tasks", {"id": target, "title": str(t.get("title") or ""), "status": str(t.get("status") or ""),
                         "project": str(t.get("project") or ""), "attachment_id": aid, "by": by}
    if kind == "note":
        n = notes.get(target) or {}
        return "notes", {"id": target, "title": str(n.get("title") or title), "project": str(n.get("project") or ""),
                         "attachment_id": aid, "by": by}
    if kind == "commit":
        subject, _, at = title.partition("\x1f")
        return "commits", {"sha": target, "subject": subject, "at": at, "repo": a.get("source") or "",
                           "attachment_id": aid, "by": by}
    return "", {}


def _card_view(store: ViewStore, row: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    cid = str(row["id"])
    project = str(row.get("project") or "")
    message, text, versions = _card_text(store, row, ctx["writers"])
    context_versions = _versions_out(_context_versions(store, cid), cid, "context", ctx["writers"])
    merged_from = [s for s in ctx["sources"] if s.get("card_id") == cid and s.get("from_card")]
    shown_ids = {cid} | {c for c, root in ctx["roots"].items() if root == cid}
    sources: list[dict[str, Any]] = [{
        "id": cid, "kind": "kept", "at": iso_moment(row.get("created_date"), row.get("created_time")),
        "agent_id": str(row.get("agent_id") or ""), "session_id": str(row.get("session_id") or ""),
        "turn": as_int(row.get("source_turn")), "text": message, "from_card": "",
    }]
    for s in ctx["sources"]:
        if s.get("card_id") in shown_ids and s.get("card_id") != "":
            sources.append({
                "id": s["id"], "kind": "merged" if s.get("from_card") else "appended", "at": s.get("at") or "",
                "agent_id": s.get("agent_id") or "", "session_id": s.get("session_id") or "",
                "turn": as_int(s.get("turn")), "text": s.get("text") or "", "from_card": s.get("from_card") or "",
            })
    sources[1:] = sorted(sources[1:], key=lambda s: s["at"])
    got: dict[str, list[dict[str, Any]]] = {k: [] for k in ("images", "links", "files", "tasks", "notes", "commits")}
    seen: set[tuple[str, str]] = set()
    for a in ctx["attachments"]:
        if a.get("card_id") not in shown_ids:
            continue
        key, view = _attachment_view(store, a, ctx["tasks"], ctx["notes"])
        if not key or (a.get("kind") or "", a.get("target") or a["id"]) in seen:
            continue
        seen.add((a.get("kind") or "", a.get("target") or a["id"]))
        got[key].append(view)
    got["commits"].sort(key=lambda c: c["at"])
    cores: dict[str, dict[str, Any]] = {}
    for t in got["tasks"]:
        for c in corelib.cores_of_task(store, t["id"]):
            cores.setdefault(c["id"], {"id": c["id"], "name": c["name"], "type": c["type"]})
    names = ctx["doc_names"]
    placements = [{
        "doc_id": i.get("doc_id") or "", "doc_name": names.get(i.get("doc_id") or "", ""),
        "version_n": as_int(i.get("version_n")), "item_id": i["id"], "text": i.get("text") or "",
        "changed": (i.get("text") or "").strip() != text.strip(),
    } for i in ctx["items"] if i.get("card_id") == cid and (i.get("doc_id") or "") in names]
    placements.sort(key=lambda p: (p["doc_name"], p["version_n"]))
    return {
        "id": cid, "project": project, "agent_id": str(row.get("agent_id") or ""),
        "session_id": str(row.get("session_id") or ""), "source_turn": as_int(row.get("source_turn")),
        "at": iso_moment(row.get("created_date"), row.get("created_time")),
        "message": message, "text": text, "versions": versions,
        "context": str(context_versions[-1]["text"]) if context_versions else "",
        "context_versions": context_versions,
        "rev": len(versions) + len(context_versions),
        "sources": sources, "merged_from": [s["from_card"] for s in merged_from],
        **got, "cores": list(cores.values()), "placements": placements,
        "archived_at": str(row.get("archived_at") or ""),
    }


def _context(store: ViewStore, project: str, items: list[dict[str, str]],
             doc_names: dict[str, str]) -> dict[str, Any]:
    """What every card of a read needs, read once."""
    attachments = _live(_rows(store, ATTACH_FILE))
    task_ids = sorted({a.get("target") or "" for a in attachments if a.get("kind") == "task"})
    tasks: dict[str, dict[str, str]] = {}
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        tasks = {str(r["id"]): r for r in store.query(
            f"SELECT id, title, status, project FROM tasks_mutual WHERE id IN ({ph})", tuple(task_ids))}
    notes: dict[str, dict[str, str]] = {}
    if any(a.get("kind") == "note" for a in attachments):
        from . import notelib
        notes = {str(r.get("id") or ""): r for r in notelib.all_rows(store)}
    sources = _live(_rows(store, SOURCES_FILE))
    merges = {s["from_card"]: s["card_id"] for s in sources if s.get("from_card")}
    return {
        "writers": _writers(store), "attachments": attachments, "tasks": tasks, "notes": notes,
        "sources": sources, "roots": {c: root_of(c, merges) for c in merges},
        "items": items, "doc_names": doc_names,
    }


def _doc_rows(store: ViewStore, project: str) -> list[dict[str, str]]:
    return [d for d in _rows(store, DOCS_FILE) if d.get("project") == project]


def _live_items(store: ViewStore) -> list[dict[str, str]]:
    return [i for i in _rows(store, ITEMS_FILE) if not (i.get("removed_at") or "").strip()]


def _doc_view(store: ViewStore, doc: dict[str, str], items: list[dict[str, str]],
              card_text: dict[str, str]) -> dict[str, Any]:
    versions = sorted((v for v in _rows(store, VERSIONS_FILE) if v.get("doc_id") == doc["id"]),
                      key=lambda v: as_int(v.get("n")))
    out_versions = []
    for v in versions:
        n = as_int(v.get("n"))
        mine = sorted((i for i in items if i.get("doc_id") == doc["id"] and as_int(i.get("version_n")) == n),
                      key=lambda i: (as_int(i.get("position")), i.get("at") or ""))
        out_versions.append({
            "n": n, "at": v.get("at") or "", "actor": v.get("actor") or "", "note": v.get("note") or "",
            "items": [{
                "id": i["id"], "card_id": i.get("card_id") or "", "text": i.get("text") or "",
                "position": as_int(i.get("position")), "at": i.get("at") or "",
                "changed": (i.get("text") or "").strip() != card_text.get(i.get("card_id") or "", "").strip(),
            } for i in mine],
        })
    return {
        "id": doc["id"], "project": doc.get("project") or "", "name": doc.get("name") or "",
        "created_at": doc.get("created_at") or "", "archived_at": doc.get("archived_at") or "",
        "current": out_versions[-1]["n"] if out_versions else 0, "versions": out_versions,
    }



def board(store: ViewStore, project: str) -> dict[str, Any]:
    """The page: every card of the project with its life, every document with its versions."""
    rows = _card_rows(store, project)
    items = _live_items(store)
    docs = _doc_rows(store, project)
    names = {d["id"]: d.get("name") or "" for d in docs}
    ctx = _context(store, project, items, names)
    cards = []
    card_text: dict[str, str] = {}
    for row in rows:
        view = _card_view(store, row, ctx=ctx)
        card_text[view["id"]] = view["text"]
        if view["id"] in ctx["roots"]:
            continue        # merged into another card: shown there
        cards.append(view)
    return {
        "project": project, "cards": cards,
        "docs": [_doc_view(store, d, items, card_text) for d in docs],
    }


def card(store: ViewStore, card_id: str) -> dict[str, Any] | None:
    """One card with its history (oldest first), or None. A merged card
    answers the card it was merged into."""
    row = _card_row(store, card_id)
    if row is None:
        return None
    card_id = root_of(card_id, _merges(store))
    row = _card_row(store, card_id)
    if row is None:
        return None
    project = str(row.get("project") or "")
    items = _live_items(store)
    docs = _doc_rows(store, project)
    names = {d["id"]: d.get("name") or "" for d in docs}
    found = _card_view(store, row, ctx=_context(store, project, items, names))
    history: list[dict[str, Any]] = [{"at": found["at"], "what": "kept", "text": found["message"]}]
    for s in found["sources"][1:]:
        history.append({"at": s["at"], "what": s["kind"], "text": s["text"], "by": s["agent_id"]})
    for v in found["versions"]:
        history.append({"at": str(v.get("at") or ""), "what": "edited" if v["by"] == "operator" else "written",
                        "text": str(v.get("text") or ""), "note": v.get("note") or "", "by": v["by"]})
    for v in found["context_versions"]:
        history.append({"at": str(v.get("at") or ""), "what": "context", "text": str(v.get("text") or ""),
                        "note": v.get("note") or "", "by": v["by"]})
    for i in _rows(store, ITEMS_FILE):
        if i.get("card_id") != card_id:
            continue
        base = {"doc_id": i.get("doc_id") or "", "doc_name": names.get(i.get("doc_id") or "", ""),
                "version_n": as_int(i.get("version_n")), "item_id": i["id"]}
        history.append({"at": i.get("at") or "", "what": "placed", "text": i.get("text") or "", **base})
        if (i.get("removed_at") or "").strip():
            history.append({"at": i["removed_at"], "what": "removed from", **base})
    history.sort(key=lambda h: h["at"])
    return {**found, "history": history}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def create_card(store: ViewStore, body: dict) -> dict[str, Any]:
    """A card written on the page by hand (source ``page``), beside the ones
    kept from a chat's #publish. The same text in the same minute is the
    same card."""
    from .entitylib import create_entity

    project = str(body.get("project") or "").strip()
    text = str(body.get("text") or "").strip()
    if not project:
        raise PublishRefused("project is required")
    if not text:
        raise PublishRefused("the text cannot be empty")
    if len(text) > TEXT_MAX:
        raise PublishRefused(f"the text is at most {TEXT_MAX} characters")
    now = datetime.now()
    head = next((ln.strip() for ln in text.splitlines() if ln.strip()), text)[:limits.MAX_TITLE]
    row: dict[str, Any] = {
        "project": project, "created_date": now.strftime("%y%m-%d"), "created_time": now.strftime("%H:%M"),
        "agent_id": "operator", "l1": head, "l4": text, "source": "page",
        "session_id": "", "source_turn": 0, "versions_n": 0,
    }
    out = create_entity(store, ENTITIES["publish"], row)
    cid = str((out.get("metadata") or {}).get("id") or "")
    return {"card": card(store, cid), "existing": bool(out.get("existing"))}


def _log_write(store: ViewStore, card_id: str, part: str, v: Version, actor: str) -> None:
    append_row(store.data_root / WRITES_FILE, PUBLISH_WRITE_COLUMNS, {
        "id": f"{card_id}#{part}#{v.n}", "card_id": card_id, "part": part, "n": str(v.n),
        "at": _iso(v.at), "actor": actor, "note": v.note})


def _write_text(store: ViewStore, row: dict[str, Any], text: str, note: str, actor: str) -> bool:
    """A new version of the card's text; False when it is the text already."""
    if text == _card_text(store, row)[1]:
        return False
    before = len(keeplib.read_versions(store, str(row["id"])))
    try:
        after = keeplib.interpret(store, "publish", dict(row), text, note, by_agent=is_agent(actor),
                                  on_version=lambda v: _log_write(store, str(row["id"]), "text", v, actor))
    except ValueError as exc:
        raise PublishRefused(str(exc)) from None
    return len(after) > before


def _write_context(store: ViewStore, card_id: str, text: str, note: str, actor: str) -> bool:
    """A new version of the context block; False when it is the context already."""
    path = _context_path(store, card_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with acquire_flock(lock_path(path)):
        versions = _context_versions(store, card_id)
        if versions and versions[-1].text == text:
            return False
        versions.append(Version(
            n=versions[-1].n + 1 if versions else 1, at=_stamp(datetime.now()),
            how="written" if is_agent(actor) else "edited", note=(note or "").strip()[:limits.MAX_NOTE], text=text))
        atomic_write(path, render_doc(f"---\nid: {card_id}\nkind: publish-context\n---\n", versions))
        _log_write(store, card_id, "context", versions[-1], actor)
    return True


def edit_card(store: ViewStore, card_id: str, body: dict) -> dict[str, Any]:
    row = _card_row(store, card_id)
    if row is None:
        raise LookupError(card_id)
    text = str(body.get("text") or "").strip()
    if not text:
        raise PublishRefused("the text cannot be empty")
    if len(text) > TEXT_MAX:
        raise PublishRefused(f"the text is at most {TEXT_MAX} characters")
    _write_text(store, row, text, str(body.get("note") or ""), "operator")
    store.rebuild()
    got = card(store, card_id)
    assert got is not None
    return got


def _doc(store: ViewStore, doc_id: str) -> dict[str, str]:
    d = next((d for d in _rows(store, DOCS_FILE) if d.get("id") == doc_id), None)
    if d is None:
        raise LookupError(doc_id)
    return d


def _current_n(store: ViewStore, doc_id: str) -> int:
    return max((as_int(v.get("n")) for v in _rows(store, VERSIONS_FILE) if v.get("doc_id") == doc_id), default=0)


def _doc_out(store: ViewStore, doc_id: str) -> dict[str, Any]:
    d = _doc(store, doc_id)
    page = board(store, str(d.get("project") or ""))
    return next(x for x in page["docs"] if x["id"] == doc_id)


def create_doc(store: ViewStore, body: dict) -> dict[str, Any]:
    project = str(body.get("project") or "").strip()
    name = " ".join(str(body.get("name") or "").split())
    if not project:
        raise PublishRefused("project is required")
    if not name:
        raise PublishRefused("a document needs a name")
    if len(name) > NAME_MAX:
        raise PublishRefused(f"a document's name is at most {NAME_MAX} characters")
    actor = str(body.get("actor") or body.get("agent_id") or "operator")
    doc_id = mint_id("pd_", project, name.lower())
    existing = any(d.get("id") == doc_id for d in _rows(store, DOCS_FILE))
    if not existing:
        now = now_iso()
        append_row(store.data_root / DOCS_FILE, PUBLISH_DOC_COLUMNS,
                   {"id": doc_id, "project": project, "name": name, "created_at": now, "actor": actor, "archived_at": ""})
        append_row(store.data_root / VERSIONS_FILE, PUBLISH_VERSION_COLUMNS,
                   {"id": mint_id("pv_", doc_id, "1"), "doc_id": doc_id, "n": "1", "at": now, "actor": actor, "note": ""})
        store.rebuild()
    return {"doc": _doc_out(store, doc_id), "existing": existing}


def update_doc(store: ViewStore, doc_id: str, body: dict) -> dict[str, Any]:
    _doc(store, doc_id)
    name = " ".join(str(body.get("name") or "").split()) if "name" in body else None
    if name is not None and (not name or len(name) > NAME_MAX):
        raise PublishRefused(f"a document's name is one to {NAME_MAX} characters")

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            if r.get("id") != doc_id:
                continue
            if name is not None and r.get("name") != name:
                r["name"] = name
                changed = True
            if "archived" in body:
                want = now_iso() if body.get("archived") else ""
                if bool(r.get("archived_at")) != bool(want):
                    r["archived_at"] = want
                    changed = True
        return changed

    rewrite_rows(store.data_root / DOCS_FILE, PUBLISH_DOC_COLUMNS, mutate)
    store.rebuild()
    return _doc_out(store, doc_id)


def new_version(store: ViewStore, doc_id: str, body: dict) -> dict[str, Any]:
    """The next version: the current one's items copied, in order."""
    _doc(store, doc_id)
    actor = str(body.get("actor") or body.get("agent_id") or "operator")
    cur = _current_n(store, doc_id)
    nxt = cur + 1
    now = now_iso()
    append_row(store.data_root / VERSIONS_FILE, PUBLISH_VERSION_COLUMNS,
               {"id": mint_id("pv_", doc_id, str(nxt)), "doc_id": doc_id, "n": str(nxt), "at": now, "actor": actor,
                "note": str(body.get("note") or "").strip()[:limits.MAX_NOTE]})
    items = sorted((i for i in _live_items(store) if i.get("doc_id") == doc_id and as_int(i.get("version_n")) == cur),
                   key=lambda i: as_int(i.get("position")))
    for i in items:
        append_row(store.data_root / ITEMS_FILE, PUBLISH_ITEM_COLUMNS, {
            "id": mint_id("pi_", doc_id, str(nxt), i.get("card_id") or ""), "doc_id": doc_id, "version_n": str(nxt),
            "card_id": i.get("card_id") or "", "text": i.get("text") or "", "position": i.get("position") or "0",
            "at": now, "actor": actor, "removed_at": ""})
    store.rebuild()
    return _doc_out(store, doc_id)


def _positions(store: ViewStore, doc_id: str, n: int) -> list[dict[str, str]]:
    return sorted((i for i in _live_items(store) if i.get("doc_id") == doc_id and as_int(i.get("version_n")) == n),
                  key=lambda i: as_int(i.get("position")))


def _slot(items: list[dict[str, str]], before: str, skip: str = "") -> int:
    """A whole position in front of ``before`` (an item id), else after the last."""
    rows = [i for i in items if i["id"] != skip]
    if before:
        idx = next((k for k, i in enumerate(rows) if i["id"] == before), None)
        if idx is not None:
            hi = as_int(rows[idx].get("position"))
            lo = as_int(rows[idx - 1].get("position")) if idx > 0 else 0
            if hi - lo >= 2:
                return (lo + hi) // 2
            return hi  # no room: lands at the same number, ordered by time after it; renumber below
    return (as_int(rows[-1].get("position")) if rows else 0) + STEP


def place(store: ViewStore, doc_id: str, body: dict) -> dict[str, Any]:
    """A card into the document's current version; the same card there answers the existing item."""
    d = _doc(store, doc_id)
    card_id = str(body.get("card_id") or "").strip()
    row = store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,)) if card_id else None
    if row is None:
        raise PublishRefused(f"{card_id or 'card_id'} is not a card")
    if str(row.get("project") or "") != str(d.get("project") or ""):
        raise PublishRefused("the card is of another project")
    n = _current_n(store, doc_id)
    if n == 0:
        raise PublishRefused("the document has no version yet")
    items = _positions(store, doc_id, n)
    existing = next((i for i in items if i.get("card_id") == card_id), None)
    if existing is not None:
        return {"item": _item_out(store, existing, card_id), "existing": True}
    text = str(body.get("text") or "").strip() or _card_text(store, row)[1]
    if len(text) > TEXT_MAX:
        raise PublishRefused(f"the text is at most {TEXT_MAX} characters")
    pos = _slot(items, str(body.get("before") or ""))
    item = {"id": mint_id("pi_", doc_id, str(n), card_id), "doc_id": doc_id, "version_n": str(n), "card_id": card_id,
            "text": text, "position": str(pos), "at": now_iso(),
            "actor": str(body.get("actor") or body.get("agent_id") or "operator"), "removed_at": ""}
    append_row(store.data_root / ITEMS_FILE, PUBLISH_ITEM_COLUMNS, item)
    _renumber(store, doc_id, n)
    store.rebuild()
    return {"item": _item_out(store, item, card_id), "existing": False}


def _renumber(store: ViewStore, doc_id: str, n: int) -> None:
    """Positions in tens, in the order shown, when two items share a number."""
    items = sorted(_positions(store, doc_id, n), key=lambda i: (as_int(i.get("position")), i.get("at") or ""))
    if len({as_int(i.get("position")) for i in items}) == len(items):
        return
    want = {i["id"]: str((k + 1) * STEP) for k, i in enumerate(items)}

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            if r.get("id") in want and r.get("position") != want[r["id"]]:
                r["position"] = want[r["id"]]
                changed = True
        return changed

    rewrite_rows(store.data_root / ITEMS_FILE, PUBLISH_ITEM_COLUMNS, mutate)


def _item_out(store: ViewStore, item: dict[str, str], card_id: str) -> dict[str, Any]:
    row = store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,))
    current = _card_text(store, row)[1] if row else ""
    return {"id": item["id"], "doc_id": item.get("doc_id") or "", "version_n": as_int(item.get("version_n")),
            "card_id": card_id, "text": item.get("text") or "", "position": as_int(item.get("position")),
            "at": item.get("at") or "", "changed": (item.get("text") or "").strip() != current.strip()}


def _item(store: ViewStore, item_id: str) -> dict[str, str]:
    i = next((i for i in _live_items(store) if i.get("id") == item_id), None)
    if i is None:
        raise LookupError(item_id)
    return i


def update_item(store: ViewStore, item_id: str, body: dict) -> dict[str, Any]:
    i = _item(store, item_id)
    text = str(body.get("text") or "").strip() if "text" in body else None
    if text is not None and (not text or len(text) > TEXT_MAX):
        raise PublishRefused(f"the text is one to {TEXT_MAX} characters")
    pos = None
    if "before" in body:
        pos = _slot(_positions(store, i["doc_id"], as_int(i.get("version_n"))), str(body.get("before") or ""), skip=item_id)

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            if r.get("id") != item_id:
                continue
            if text is not None and r.get("text") != text:
                r["text"] = text
                changed = True
            if pos is not None and r.get("position") != str(pos):
                r["position"] = str(pos)
                changed = True
        return changed

    rewrite_rows(store.data_root / ITEMS_FILE, PUBLISH_ITEM_COLUMNS, mutate)
    if pos is not None:
        _renumber(store, i["doc_id"], as_int(i.get("version_n")))
    store.rebuild()
    return _item_out(store, _item(store, item_id), i.get("card_id") or "")


def remove_item(store: ViewStore, item_id: str) -> bool:
    _item(store, item_id)
    stamp = now_iso()

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == item_id and not (r.get("removed_at") or "").strip():
                r["removed_at"] = stamp
                return True
        return False

    rewrite_rows(store.data_root / ITEMS_FILE, PUBLISH_ITEM_COLUMNS, mutate)
    store.rebuild()
    return True



# ---------------------------------------------------------------------------
# The card's writes: text, context, attachments (MCP publish_write, the page)
# ---------------------------------------------------------------------------


def _agent_project(store: ViewStore, agent: str) -> str:
    for a in store.agents():
        if str(a.get("agent_id") or "") == agent:
            return str(a.get("project") or "")
    return ""


def _list(body: dict, key: str) -> list[Any]:
    v = body.get(key)
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise PublishRefused(f"{key} is a list")
    return v


def _title(item: dict, fallback: str = "") -> str:
    return " ".join(str(item.get("title") or fallback).split())[:TITLE_MAX]


def _decode(item: dict, label: str) -> bytes:
    try:
        raw = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
    except (binascii.Error, ValueError):
        raise PublishRefused(f"{label}: data_base64 is not valid base64") from None
    if not raw:
        raise PublishRefused(f"{label}: the file is empty")
    if len(raw) > FILE_MAX:
        raise PublishRefused(f"{label}: the file is over {FILE_MAX // (1024 * 1024)}MB")
    return raw


def _safe_name(name: str) -> str:
    base = Path(str(name or "")).name.strip() or "file"
    return re.sub(r"[^\w.\- ]+", "_", base)[:120] or "file"


def _commit(store: ViewStore, project: str, item: Any, i: int) -> tuple[str, str, str]:
    """(sha, repo, subject\\x1fISO date) of a commit the repository holds."""
    from . import gitwork
    from .file_entries import project_repo
    if isinstance(item, str):
        item = {"sha": item}
    if not isinstance(item, dict):
        raise PublishRefused(f"commit {i}: an object with sha and repo")
    sha = str(item.get("sha") or "").strip().lower()
    if not SHA_RE.match(sha):
        raise PublishRefused(f"commit {i}: sha is 7 to 40 hex characters")
    given = str(item.get("repo") or "").strip()
    repo = Path(given).expanduser() if given else project_repo(store, project)
    if repo is None or not repo.is_dir():
        raise PublishRefused(f"commit {i}: repo is the repository's folder on this machine"
                             + ("" if given else f" ({project} has no registered repository)"))
    out = gitwork.git(repo, "show", "-s", "--format=%H%x1f%s%x1f%cI", sha, "--")
    if not out or "\x1f" not in out:
        raise PublishRefused(f"commit {i}: {sha} is not a commit of {repo}")
    full, subject, at = (out.strip().split("\x1f") + ["", ""])[:3]
    return full[:12], str(repo), f"{subject[:200]}\x1f{at[:19]}"


def _checked(store: ViewStore, project: str, body: dict) -> list[dict[str, Any]]:
    """Every attachment of a write, checked before anything is written."""
    out: list[dict[str, Any]] = []
    for i, tid in enumerate(_list(body, "tasks"), 1):
        tid = str(tid.get("id") if isinstance(tid, dict) else tid or "").strip()
        if not TASK_RE.match(tid):
            raise PublishRefused(f"task {i}: {tid or '(empty)'} is not a task id (tk_…)")
        if store.query_one("SELECT id FROM tasks_mutual WHERE id = ?", (tid,)) is None:
            raise PublishRefused(f"task {i}: {tid} is not a task. Nothing was written")
        out.append({"kind": "task", "target": tid, "title": "", "digest": tid})
    from . import notelib
    for i, nid in enumerate(_list(body, "notes"), 1):
        nid = str(nid.get("id") if isinstance(nid, dict) else nid or "").strip()
        if not NOTE_RE.match(nid) or notelib.row_of(store, nid) is None:
            raise PublishRefused(f"note {i}: {nid or '(empty)'} is not a note. Nothing was written")
        out.append({"kind": "note", "target": nid, "title": "", "digest": nid})
    for i, item in enumerate(_list(body, "commits"), 1):
        sha, repo, title = _commit(store, project, item, i)
        out.append({"kind": "commit", "target": sha, "source": repo, "title": title, "digest": f"{repo}|{sha}"})
    for i, item in enumerate(_list(body, "links"), 1):
        if not isinstance(item, dict):
            raise PublishRefused(f"link {i}: an object with title and url")
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise PublishRefused(f"link {i}: url must start with http:// or https:// (a file on this machine goes in files)")
        out.append({"kind": "link", "target": url[:2000], "title": _title(item), "digest": url[:2000]})
    for i, item in enumerate(_list(body, "images"), 1):
        if not isinstance(item, dict):
            raise PublishRefused(f"image {i}: an object with title and path (or data_base64)")
        try:
            ext, raw = checked_image(item, f"image {i}")
        except ValueError as exc:
            raise PublishRefused(str(exc)) from None
        out.append({"kind": "image", "ext": ext, "raw": raw, "title": _title(item),
                    "source": str(item.get("source") or "")[:500], "digest": hashlib.sha256(raw).hexdigest()})
    for i, item in enumerate(_list(body, "files"), 1):
        if not isinstance(item, dict):
            raise PublishRefused(f"file {i}: an object with path and title")
        raw = _decode(item, f"file {i}")
        name = _safe_name(str(item.get("name") or item.get("source") or "file"))
        out.append({"kind": "file", "raw": raw, "name": name, "title": _title(item, name),
                    "source": str(item.get("source") or "")[:500], "size": str(len(raw)),
                    "digest": hashlib.sha256(raw).hexdigest()})
    if len(out) > ATTACH_MAX:
        raise PublishRefused(f"at most {ATTACH_MAX} attachments in one write")
    order = ("image", "link", "file", "task", "note", "commit")
    return sorted(out, key=lambda c: order.index(c["kind"]))


def _store_attachments(store: ViewStore, card_id: str, checked: list[dict[str, Any]], actor: str) -> list[dict[str, Any]]:
    known = {a["id"]: a for a in _rows(store, ATTACH_FILE)}
    out = []
    now = now_iso()
    for c in checked:
        aid = "pa_" + hashlib.sha256(f"{card_id}|{c['kind']}|{c['digest']}".encode()).hexdigest()[:10]
        old = known.get(aid)
        if old is not None and not (old.get("removed_at") or "").strip():
            out.append({"id": aid, "kind": c["kind"], "title": old.get("title") or "", "existing": True})
            continue
        if old is not None:
            # Removed by the operator and attached again: it comes back.
            def back(rows: list[dict[str, str]], aid: str = aid) -> bool:
                for r in rows:
                    if r.get("id") == aid:
                        r["removed_at"] = ""
                        return True
                return False
            rewrite_rows(store.data_root / ATTACH_FILE, PUBLISH_ATTACHMENT_COLUMNS, back)
            out.append({"id": aid, "kind": c["kind"], "title": old.get("title") or "", "existing": False})
            continue
        target = c.get("target") or ""
        if c["kind"] == "image":
            target = f"{IMAGES_DIR}/{card_id}/{aid}.{c['ext']}"
        elif c["kind"] == "file":
            target = f"{FILES_DIR}/{card_id}/{aid}/{c['name']}"
        if "raw" in c:
            path = store.data_root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, c["raw"])
        append_row(store.data_root / ATTACH_FILE, PUBLISH_ATTACHMENT_COLUMNS, {
            "id": aid, "card_id": card_id, "kind": c["kind"], "title": c.get("title") or "", "target": target,
            "at": now, "actor": actor or "operator", "removed_at": "", "source": c.get("source") or "",
            "size": c.get("size") or ""})
        known[aid] = {"id": aid, "title": c.get("title") or ""}
        out.append({"id": aid, "kind": c["kind"], "title": (c.get("title") or "").split("\x1f")[0], "existing": False})
    return out


def write(store: ViewStore, any_id: str, body: dict, actor: str) -> dict[str, Any]:
    """One write of a card: its text (a version), its context (a version),
    what belongs to it, and a card of this chat folded into it (``merge``).
    Everything is checked first; a refusal writes nothing."""
    if not isinstance(body, dict):
        raise PublishRefused("send the body as a JSON object")
    card_id = resolve(store, any_id)
    if not card_id:
        raise LookupError(any_id)
    row = _card_row(store, card_id)
    assert row is not None
    project = str(row.get("project") or "")
    agent = is_agent(actor)
    if agent:
        mine = _agent_project(store, actor)
        if mine and project and mine != project:
            raise PublishRefused(f"{card_id} is a card of {project}; this chat works in {mine}. Nothing was written")
    text = body.get("text")
    context = body.get("context")
    for key, v in (("text", text), ("context", context)):
        if v is not None and not isinstance(v, str):
            raise PublishRefused(f"{key} is text")
        if isinstance(v, str) and len(v.strip()) > TEXT_MAX:
            raise PublishRefused(f"the {key} is at most {TEXT_MAX} characters")
    if isinstance(text, str) and not text.strip():
        raise PublishRefused("the text cannot be empty; leave text out to keep it")
    note = str(body.get("note") or "")
    base = body.get("base")
    current = card(store, card_id)
    assert current is not None
    if base not in (None, ""):
        if isinstance(base, bool) or not str(base).isdigit():
            raise PublishRefused("base is the card's rev you read, a number")
        if int(str(base)) != current["rev"]:
            raise PublishRefused(f"{card_id} is at rev {current['rev']} now, not {base}: someone wrote since. "
                                 "Read the card again and write on top of it. Nothing was written")
    merge_from = str(body.get("merge") or "").strip()
    if merge_from:
        _check_merge(store, merge_from, card_id, actor)
    checked = _checked(store, project, body)
    if text is None and context is None and not checked and not merge_from:
        raise PublishRefused("nothing to write: send text, context, or something to attach")
    wrote: list[str] = []
    if isinstance(text, str) and _write_text(store, row, text.strip(), note, actor or "operator"):
        wrote.append("text")
    if isinstance(context, str):
        if context.strip():
            if _write_context(store, card_id, context.strip(), note, actor or "operator"):
                wrote.append("context")
        elif current["context"]:
            raise PublishRefused("the context cannot be emptied; write the context you want instead")
    attached = _store_attachments(store, card_id, checked, actor or "operator")
    if merge_from:
        _merge(store, merge_from, card_id, actor or "operator")
        wrote.append("merge")
    store.rebuild()
    got = card(store, card_id)
    assert got is not None
    return {"id": card_id, "rev": got["rev"], "wrote": wrote, "attached": attached, "card": got,
            "page": f"/publish?card={card_id}",
            "reply": f"In the chat, say in one line what the card {card_id} now carries."}


def attach(store: ViewStore, card_id: str, body: dict, actor: str) -> dict[str, Any]:
    """The older door (MCP publish_attach, the page's drop and paste):
    images and links, and now anything ``write`` takes besides text."""
    if not isinstance(body, dict):
        raise PublishRefused("send the body as a JSON object")
    keys = ("images", "links", "files", "tasks", "notes", "commits")
    if not any(body.get(k) for k in keys):
        raise PublishRefused("nothing to attach: send images, links, files, tasks, notes or commits")
    got = write(store, card_id, {k: body.get(k) for k in keys if body.get(k)}, actor)
    return {"attached": got["attached"], "card": got["card"]}


# ---------------------------------------------------------------------------
# Merging and the messages a card carries
# ---------------------------------------------------------------------------


def _check_merge(store: ViewStore, from_id: str, into: str, actor: str) -> str:
    src = _card_row(store, from_id) if CARD_RE.match(from_id) else None
    if src is None:
        keeplib.adopt(store)
        src = _card_row(store, from_id) if CARD_RE.match(from_id) else None
    if src is None:
        raise PublishRefused(f"merge: {from_id} is not a card")
    merges = _merges(store)
    if root_of(from_id, merges) != from_id:
        raise PublishRefused(f"merge: {from_id} is merged into {root_of(from_id, merges)} already")
    if root_of(into, merges) == from_id or from_id == into:
        raise PublishRefused("merge: a card cannot be merged into itself")
    target = _card_row(store, into)
    if target is None or str(src.get("project") or "") != str(target.get("project") or ""):
        raise PublishRefused(f"merge: {from_id} is a card of another project")
    if is_agent(actor) and str(src.get("agent_id") or "") != actor:
        raise PublishRefused(f"merge: {from_id} was kept in another chat; only the operator merges it (the Publish page)")
    return from_id


def _merge(store: ViewStore, from_id: str, into: str, actor: str) -> dict[str, str]:
    src = _card_row(store, from_id)
    assert src is not None
    message = _card_text(store, src)[0]
    row = {"id": "ps_" + hashlib.sha256(f"{from_id}|{into}".encode()).hexdigest()[:10],
           "card_id": into, "from_card": from_id, "project": str(src.get("project") or ""),
           "agent_id": str(src.get("agent_id") or ""), "session_id": str(src.get("session_id") or ""),
           "turn": str(as_int(src.get("source_turn"))),
           "at": iso_moment(src.get("created_date"), src.get("created_time")) or now_iso(),
           "text": message, "actor": actor, "removed_at": ""}
    had = append_if_absent(store.data_root / SOURCES_FILE, PUBLISH_SOURCE_COLUMNS, row)
    if had is not None and (had.get("removed_at") or "").strip():
        def back(rows: list[dict[str, str]]) -> bool:
            for r in rows:
                if r.get("id") == row["id"]:
                    r["removed_at"] = ""
                    return True
            return False
        rewrite_rows(store.data_root / SOURCES_FILE, PUBLISH_SOURCE_COLUMNS, back)
    return row


def merge(store: ViewStore, from_id: str, into: str, actor: str) -> dict[str, Any]:
    """The operator folds one card into another: its message becomes a source
    of the other, its attachments show there, and it leaves the feed. Taken
    back with remove_source."""
    keeplib.adopt(store)
    if _card_row(store, into) is None:
        raise LookupError(into)
    into = root_of(into, _merges(store))
    _check_merge(store, from_id, into, actor)
    _merge(store, from_id, into, actor)
    store.rebuild()
    got = card(store, into)
    assert got is not None
    return got


def remove_source(store: ViewStore, source_id: str) -> dict[str, Any]:
    """Take back a merge (the merged card returns to the feed) or drop an
    appended message from the card."""
    stamp = now_iso()
    found: dict[str, str] = {}

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == source_id:
                found.update(r)
                if not (r.get("removed_at") or "").strip():
                    r["removed_at"] = stamp
                    return True
        return False

    rewrite_rows(store.data_root / SOURCES_FILE, PUBLISH_SOURCE_COLUMNS, mutate)
    if not found:
        raise LookupError(source_id)
    store.rebuild()
    return {"removed": True, "card_id": found.get("card_id") or "", "from_card": found.get("from_card") or ""}


def source_ids(store: ViewStore) -> set[str]:
    """Every appended message's id (keeplib reads them as kept already)."""
    return {str(r.get("id") or "") for r in _rows(store, SOURCES_FILE)}


def take_append(store: ViewStore, kid: str, mark: dict[str, Any]) -> bool:
    """A ``#publish pu_… more`` turn: the message goes onto that card of the
    project (or the card it was merged into) instead of making a new one.
    False when the id names no card of the project: the turn is a card."""
    body = str(mark.get("body") or "")
    m = APPEND_RE.match(body)
    if m is None:
        return False
    target = m.group(1).lower()
    project = str(mark.get("project") or "")
    rows = {str(r.get("id") or ""): r for r in read_rows(store.data_root / ENTITIES["publish"].csv)}
    if target not in rows or str(rows[target].get("project") or "") != project:
        return False
    target = root_of(target, _merges(store))
    append_if_absent(store.data_root / SOURCES_FILE, PUBLISH_SOURCE_COLUMNS, {
        "id": kid, "card_id": target, "from_card": "", "project": project,
        "agent_id": str(mark.get("agent_id") or ""), "session_id": str(mark.get("session_id") or ""),
        "turn": str(as_int(mark.get("turn"))), "at": str(mark.get("at_ts") or "")[:19],
        "text": _source_text(body), "actor": "operator", "removed_at": ""})
    return True


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def attachment_file(store: ViewStore, attachment_id: str) -> tuple[Path, str] | None:
    """(the file, its name) of an image or file attachment, or None."""
    a = next((a for a in _rows(store, ATTACH_FILE)
              if a.get("id") == attachment_id and a.get("kind") in ("image", "file")), None)
    if a is None:
        return None
    path = resolve_under(store.data_root, str(a.get("target") or ""))
    if path is None or not path.exists():
        return None
    allowed = (store.data_root / IMAGES_DIR).resolve(), (store.data_root / FILES_DIR).resolve()
    if not any(path.resolve().is_relative_to(d) for d in allowed):
        return None
    return path, (str(a.get("title") or "") if a.get("kind") == "file" else "") or path.name


def remove_attachment(store: ViewStore, attachment_id: str) -> bool:
    stamp = now_iso()
    found = False

    def mutate(rows: list[dict[str, str]]) -> bool:
        nonlocal found
        for r in rows:
            if r.get("id") == attachment_id:
                found = True
                if not (r.get("removed_at") or "").strip():
                    r["removed_at"] = stamp
                    return True
        return False

    rewrite_rows(store.data_root / ATTACH_FILE, PUBLISH_ATTACHMENT_COLUMNS, mutate)
    if not found:
        raise LookupError(attachment_id)
    store.rebuild()
    return True


# ---------------------------------------------------------------------------
# The migration: what the server used to guess, frozen once where it was sound
# ---------------------------------------------------------------------------


def _legacy_tasks(store: ViewStore, row: dict[str, Any], message: str) -> list[str]:
    """The tasks the server used to compute for a card: the tk_ ids in the
    message, else the last task the operator named in the chat up to it."""
    from .sessions import _TASK_ID_RE
    ids: list[str] = []
    for m in _TASK_ID_RE.finditer(message):
        if m.group(1).startswith("tk_") and m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:
        named = store.query(
            "SELECT task_id FROM task_mentions WHERE agent_id = ? AND role = 'user' AND turn <= ? "
            "ORDER BY turn DESC LIMIT 1", (str(row.get("agent_id") or ""), as_int(row.get("source_turn"))))
        ids = [str(r["task_id"]) for r in named if str(r.get("task_id") or "").startswith("tk_")]
    return ids


def migrate(store: ViewStore, *, backup: bool = True) -> dict[str, Any]:
    """Once per data root: the task a card used to show (computed at every
    read) becomes a stored link, actor ``migration`` — only when the task is
    of the card's own project; one of another project is dropped. Commits,
    files and evidence images that came from a task are not kept: a card
    carries what was attached to it. Before the first write publish.csv and
    publish_attachments.csv are copied to publish-migration-<stamp>/ in the
    backup folder (beside the data root). The marker is written on a data
    root with no cards too: a card kept later never gets a guessed task."""
    root = store.data_root
    marker = root / MIGRATION_FILE
    if not root.is_dir():
        return {"frozen": 0, "dropped": 0}
    with acquire_flock(lock_path(marker)):
        try:
            state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        except (OSError, ValueError):
            state = {}
        if isinstance(state, dict) and as_int(state.get("version")) >= MIGRATION_VERSION:
            return {"frozen": 0, "dropped": 0}
        ent = ENTITIES["publish"]
        rows = [r for r in read_rows(root / ent.csv) if r.get("id") and not (r.get("archived_at") or "").strip()]
        plan: list[tuple[str, str]] = []
        dropped = 0
        if rows:
            projects = {str(r["id"]): str(r.get("project") or "") for r in store.query(
                "SELECT id, project FROM tasks_mutual")}
            for r in rows:
                _l2, _l3, message = read_detail(root, str(r.get("md_ref") or ""))
                for tid in _legacy_tasks(store, r, _tag_free(message)):
                    if projects.get(tid) == str(r.get("project") or ""):
                        plan.append((str(r["id"]), tid))
                    else:
                        dropped += 1
        if backup and plan:
            from .backup import backup_root_for
            dest = backup_root_for(root) / f"publish-migration-{time.strftime('%Y%m%d-%H%M%S')}"
            dest.mkdir(parents=True, exist_ok=True)
            for name in (ent.csv, ATTACH_FILE):
                if (root / name).exists():
                    atomic_write(dest / name, (root / name).read_bytes())
        known = {a.get("id") for a in read_rows(root / ATTACH_FILE)}
        at = now_iso()
        for cid, tid in plan:
            aid = "pa_" + hashlib.sha256(f"{cid}|task|{tid}".encode()).hexdigest()[:10]
            if aid in known:
                continue
            append_row(root / ATTACH_FILE, PUBLISH_ATTACHMENT_COLUMNS, {
                "id": aid, "card_id": cid, "kind": "task", "title": "", "target": tid, "at": at,
                "actor": "migration", "removed_at": "", "source": "", "size": ""})
            known.add(aid)
        atomic_write(marker, json.dumps({"version": MIGRATION_VERSION, "frozen": len(plan), "dropped": dropped},
                                        indent=1).encode("utf-8"))
    if plan:
        store.rebuild()
    return {"frozen": len(plan), "dropped": dropped}


def markdown(store: ViewStore, doc_id: str, n: int | None = None) -> str:
    d = _doc(store, doc_id)
    use = n or _current_n(store, doc_id)
    items = _positions(store, doc_id, use)
    head = f"# {d.get('name') or 'Document'}\n\n"
    stamp = time.strftime("%Y-%m-%d")
    body = "\n\n".join((i.get("text") or "").strip() for i in items if (i.get("text") or "").strip())
    return head + (body + "\n" if body else "") + f"\n<!-- v{use} · {stamp} -->\n"
