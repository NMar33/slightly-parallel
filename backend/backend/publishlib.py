"""Publish — what shipped, worth telling (docs/publish.md).

A card is a message the operator tagged ``#publish``: the kept kind
``publish`` (keeplib: the message as typed, the operator's edits as
versions). This module adds the operator's documents (a release note, a
post, a video script …), each in numbered versions, and the cards placed
into a version with the text as placed. Everything here is the operator's;
the router refuses an agent.

Ledgers (entities.PUBLISH_*_COLUMNS): publish_docs.csv, publish_versions.csv,
publish_items.csv. A card's attachments are read, never stored: the tasks
its message names (or the chat's task at that turn), their cores, commits
and evidence images.
"""

from __future__ import annotations

import time
from typing import Any

from . import corelib, keeplib, limits, taskwork
from .answers import mint_id
from .csvio import append_row, as_int, read_rows, rewrite_rows
from .date_utils import iso_moment, now_iso
from .db import ViewStore
from .docs_md import read_detail
from .entities import (
    ENTITIES, PUBLISH_ATTACHMENT_COLUMNS, PUBLISH_DOC_COLUMNS, PUBLISH_ITEM_COLUMNS, PUBLISH_VERSION_COLUMNS,
)
from .sessions import _TASK_ID_RE
from .story_images import checked_image

DOCS_FILE = "publish_docs.csv"
VERSIONS_FILE = "publish_versions.csv"
ITEMS_FILE = "publish_items.csv"
ATTACH_FILE = "publish_attachments.csv"
IMAGES_DIR = "publish_images"
ATTACH_MAX = 12
NAME_MAX = 80
TEXT_MAX = limits.MAX_TEXT
STEP = 10


class PublishRefused(Exception):
    """A write the page does not take; the router answers 422 with the text."""


def _rows(store: ViewStore, name: str) -> list[dict[str, str]]:
    return read_rows(store.data_root / name)


def _tag_free(text: str) -> str:
    """The message without its #publish tag (the card's text starts clean)."""
    import re
    return re.sub(r"(?<![\w#])#{1,3}publish(?![\w-])\s*", "", text or "", flags=re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _card_rows(store: ViewStore, project: str) -> list[dict[str, Any]]:
    ent = ENTITIES["publish"]
    return store.query(
        f"SELECT * FROM {ent.view} WHERE project = ? AND COALESCE(archived_at, '') = '' "
        "ORDER BY created_date DESC, created_time DESC", (project,))


def _card_text(store: ViewStore, row: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """(message as typed, current text, versions) of a card."""
    _l2, _l3, message = read_detail(store.data_root, str(row.get("md_ref") or ""))
    message = _tag_free(message)
    versions = [v.as_dict() for v in keeplib.read_versions(store, str(row["id"]))]
    for v in versions:
        # A kept version's moment is "YYMM-DD HH:MM"; the page reads ISO everywhere.
        day, _, hm = str(v.get("at") or "").partition(" ")
        v["at"] = iso_moment(day, hm) or str(v.get("at") or "")
    text = str(versions[-1]["text"]) if versions else message
    return message, text, versions


def _tasks_of(store: ViewStore, row: dict[str, Any], message: str) -> list[dict[str, Any]]:
    ids: list[str] = []
    for m in _TASK_ID_RE.finditer(message):
        if m.group(1).startswith("tk_") and m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:
        # The chat's task at that turn: the last task the operator named up to it.
        agent, turn = str(row.get("agent_id") or ""), as_int(row.get("source_turn"))
        named = store.query(
            "SELECT task_id FROM task_mentions WHERE agent_id = ? AND role = 'user' AND turn <= ? "
            "ORDER BY turn DESC LIMIT 1", (agent, turn))
        ids = [str(r["task_id"]) for r in named if str(r.get("task_id") or "").startswith("tk_")]
    out = []
    for tid in ids:
        t = store.query_one("SELECT id, title, status FROM tasks_mutual WHERE id = ?", (tid,))
        if t:
            out.append({"id": tid, "title": str(t.get("title") or ""), "status": str(t.get("status") or "")})
    return out


def _attachments(store: ViewStore, card_id: str, tasks: list[dict[str, Any]],
                 work_of: dict[str, dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """What the server finds for a card (the tasks' cores, commits, files,
    evidence and story images) and what was attached to it (images, links)."""
    cores: dict[str, dict[str, Any]] = {}
    commits: dict[str, dict[str, Any]] = {}
    files: dict[str, dict[str, Any]] = {}
    images: list[dict[str, Any]] = []
    memo = work_of if work_of is not None else {}
    for t in tasks:
        for c in corelib.cores_of_task(store, t["id"]):
            cores.setdefault(c["id"], {"id": c["id"], "name": c["name"], "type": c["type"]})
        if t["id"] not in memo:
            try:
                memo[t["id"]] = taskwork.task_work(store, t["id"])
            except Exception:  # noqa: BLE001 — git is best effort; the card still shows
                memo[t["id"]] = {"commit_list": [], "files": []}
        work = memo[t["id"]]
        for c in work.get("commit_list") or []:
            commits.setdefault(str(c.get("sha") or ""), {
                "sha": str(c.get("sha") or ""), "subject": str(c.get("subject") or ""), "at": str(c.get("at") or "")})
        for f in (work.get("files") or [])[:12]:
            files.setdefault(str(f.get("path") or ""), {"path": str(f.get("path") or ""),
                                                        "add": as_int(f.get("lines_add")), "del": as_int(f.get("lines_del"))})
        for r in store.query(
                "SELECT id, kind, title FROM task_evidence_mutual WHERE task_id = ? AND kind = 'image' "
                "ORDER BY created_at", (t["id"],)):
            images.append({"url": f"/api/tasks/evidence/{r['id']}/file", "label": str(r.get("title") or t["title"]), "from": "evidence"})
        for r in store.query(
                "SELECT id, title FROM story_images_mutual WHERE task_id = ? ORDER BY created_at", (t["id"],)):
            images.append({"url": f"/api/story/images/{r['id']}/file", "label": str(r.get("title") or t["title"]), "from": "story"})
    links: list[dict[str, Any]] = []
    for a in _rows(store, ATTACH_FILE):
        if a.get("card_id") != card_id or (a.get("removed_at") or "").strip():
            continue
        if a.get("kind") == "image":
            images.append({"url": f"/api/publishing/attachments/{a['id']}/file", "label": a.get("title") or "",
                           "from": "attached", "id": a["id"], "by": a.get("actor") or ""})
        elif a.get("kind") == "link":
            links.append({"url": a.get("target") or "", "label": a.get("title") or a.get("target") or "",
                          "id": a["id"], "by": a.get("actor") or ""})
    return {"cores": list(cores.values()), "commits": sorted(commits.values(), key=lambda c: c["at"]),
            "files": list(files.values())[:12], "images": images, "links": links}


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
    cards = []
    card_text: dict[str, str] = {}
    work_of: dict[str, dict[str, Any]] = {}      # one git read per task, however many cards name it
    for row in rows:
        message, text, versions = _card_text(store, row)
        card_text[str(row["id"])] = text
        tasks = _tasks_of(store, row, message)
        placements = [{
            "doc_id": i.get("doc_id") or "", "doc_name": names.get(i.get("doc_id") or "", ""),
            "version_n": as_int(i.get("version_n")), "item_id": i["id"], "text": i.get("text") or "",
            "changed": (i.get("text") or "").strip() != text.strip(),
        } for i in items if i.get("card_id") == row["id"] and (i.get("doc_id") or "") in names]
        placements.sort(key=lambda p: (p["doc_name"], p["version_n"]))
        cards.append({
            "id": str(row["id"]), "project": project, "agent_id": str(row.get("agent_id") or ""),
            "session_id": str(row.get("session_id") or ""), "source_turn": as_int(row.get("source_turn")),
            "at": iso_moment(row.get("created_date"), row.get("created_time")),
            "message": message, "text": text, "versions": versions, "tasks": tasks,
            **_attachments(store, str(row["id"]), tasks, work_of), "placements": placements,
            "archived_at": str(row.get("archived_at") or ""),
        })
    return {
        "project": project, "cards": cards,
        "docs": [_doc_view(store, d, items, card_text) for d in docs],
    }


def card(store: ViewStore, card_id: str) -> dict[str, Any] | None:
    """One card with its history (oldest first), or None."""
    row = store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,))
    if row is None:
        return None
    project = str(row.get("project") or "")
    page = board(store, project)
    found = next((c for c in page["cards"] if c["id"] == card_id), None)
    if found is None:
        return None
    names = {d["id"]: d["name"] for d in page["docs"]}
    history: list[dict[str, Any]] = [{"at": found["at"], "what": "kept", "text": found["message"]}]
    for v in found["versions"]:
        history.append({"at": str(v.get("at") or ""), "what": "edited", "text": str(v.get("text") or ""), "note": v.get("note") or ""})
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
    from datetime import datetime

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


def edit_card(store: ViewStore, card_id: str, body: dict) -> dict[str, Any]:
    row = store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,))
    if row is None:
        raise LookupError(card_id)
    text = str(body.get("text") or "").strip()
    if not text:
        raise PublishRefused("the text cannot be empty")
    if len(text) > TEXT_MAX:
        raise PublishRefused(f"the text is at most {TEXT_MAX} characters")
    try:
        keeplib.interpret(store, "publish", dict(row), text, str(body.get("note") or ""), by_agent=False)
    except ValueError as exc:
        raise PublishRefused(str(exc)) from None
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


def attach(store: ViewStore, card_id: str, body: dict, actor: str) -> dict[str, Any]:
    """Images (``images``: title, ext, data_base64) and links (``links``:
    title, url) onto a card, by the operator or an agent. The same image
    or link again is the existing attachment."""
    row = store.query_one(f"SELECT * FROM {ENTITIES['publish'].view} WHERE id = ?", (card_id,))
    if row is None:
        raise LookupError(card_id)
    images = body.get("images") or []
    links = body.get("links") or []
    if not isinstance(images, list) or not isinstance(links, list):
        raise PublishRefused("images and links are lists")
    if not images and not links:
        raise PublishRefused("nothing to attach: send images or links")
    if len(images) + len(links) > ATTACH_MAX:
        raise PublishRefused(f"at most {ATTACH_MAX} attachments in one call")
    checked: list[tuple[str, str, str, bytes | None, str]] = []   # (kind, title, ext, raw, url)
    for i, item in enumerate(images, 1):
        if not isinstance(item, dict):
            raise PublishRefused(f"image {i}: an object with title, ext and data_base64")
        try:
            ext, raw = checked_image(item, f"image {i}")
        except ValueError as exc:
            raise PublishRefused(str(exc)) from None
        checked.append(("image", str(item.get("title") or "").strip()[:120], ext, raw, ""))
    for i, item in enumerate(links, 1):
        if not isinstance(item, dict):
            raise PublishRefused(f"link {i}: an object with title and url")
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise PublishRefused(f"link {i}: url must start with http:// or https://")
        checked.append(("link", str(item.get("title") or "").strip()[:120], "", None, url[:2000]))
    import hashlib
    known = {a["id"] for a in _rows(store, ATTACH_FILE)}
    out = []
    now = now_iso()
    for kind, title, ext, raw, url in checked:
        digest = hashlib.sha256(raw).hexdigest() if raw is not None else url
        aid = "pa_" + hashlib.sha256(f"{card_id}|{kind}|{digest}".encode()).hexdigest()[:10]
        if aid in known:
            out.append({"id": aid, "kind": kind, "title": title, "existing": True})
            continue
        target = url
        if raw is not None:
            rel = f"{IMAGES_DIR}/{card_id}/{aid}.{ext}"
            path = store.data_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            target = rel
        append_row(store.data_root / ATTACH_FILE, PUBLISH_ATTACHMENT_COLUMNS, {
            "id": aid, "card_id": card_id, "kind": kind, "title": title, "target": target,
            "at": now, "actor": actor or "operator", "removed_at": ""})
        known.add(aid)
        out.append({"id": aid, "kind": kind, "title": title, "existing": False})
    store.rebuild()
    return {"attached": out, "card": card(store, card_id)}


def attachment_file(store: ViewStore, attachment_id: str):
    """The image file of an attachment (a Path), or None."""
    from .docs_md import resolve_under
    a = next((a for a in _rows(store, ATTACH_FILE) if a.get("id") == attachment_id and a.get("kind") == "image"), None)
    if a is None:
        return None
    root = (store.data_root / IMAGES_DIR).resolve()
    path = resolve_under(root, str(a.get("target") or "").removeprefix(f"{IMAGES_DIR}/"))
    return path if path is not None and path.exists() else None


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


def markdown(store: ViewStore, doc_id: str, n: int | None = None) -> str:
    d = _doc(store, doc_id)
    use = n or _current_n(store, doc_id)
    items = _positions(store, doc_id, use)
    head = f"# {d.get('name') or 'Document'}\n\n"
    stamp = time.strftime("%Y-%m-%d")
    body = "\n\n".join((i.get("text") or "").strip() for i in items if (i.get("text") or "").strip())
    return head + (body + "\n" if body else "") + f"\n<!-- v{use} · {stamp} -->\n"
