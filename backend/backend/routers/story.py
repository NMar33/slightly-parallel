"""Story notes and Storyboard documents.

A *story note* is the value of a task written down while it is clear — a
typed, templated, atomic paragraph on the task (article paragraph, post,
release note, report line, FAQ entry, or a *prompt* note: how to write
about it). A *document* arranges notes (one note may sit in many docs)
with free-text blocks, per kind. Its *pack* is one markdown with three
parts — the arranged doc with the prompt notes on top, the tasks'
context, and their connections (chat mentions, checkpoints, decisions) —
made to be handed to an agent, which posts its result back as a *version*
with the MCP tool ``doc_version`` (or the operator pastes it by hand).
Doc ids (``dc_…``) are found in captured chats like task ids, so a doc's
history shows who worked on it and when.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from ..csvio import append_if_absent, append_row, rewrite_rows
from ..db import ViewStore
from ..docs_md import resolve_under
from ..turns import parse_task_doc
from ..entities import (
    DOC_COLUMNS, DOC_ITEM_COLUMNS, DOC_KINDS, DOC_VERSION_COLUMNS,
    TASK_NOTE_COLUMNS, TASK_NOTE_TYPES,
)
from .deps import (
    not_found, identity_of,
    create_answer, etag_for, get_store, json_response, maybe_304, mint_id,
    rewrite_one, task_brief,
)
from ..taskevents import append_events as _append_events
from ..date_utils import now_iso
from .. import limits

router = APIRouter()
_ACTOR = "operator"

# Scaffolds — plain text the note starts from; editable, agent-friendly.
TEMPLATES: dict[str, dict[str, str]] = {
    "article": {
        "note": "",
        "problem-insight": "**Problem** — \n\n**Insight** — \n\n**What we did** — \n\n**Why it matters** — ",
        "before-after": "**Before** — \n\n**After** — \n\n**The one-line takeaway** — ",
    },
    "post": {
        "note": "",
        "hook": "Hook: \n\nValue in one line: \n\nLink / CTA: ",
    },
    "release": {
        "note": "",
        "what-why-how": "**What** — \n\n**Why** — \n\n**How to use** — ",
    },
    "report": {
        "note": "",
        "outcome-evidence-next": "**Outcome** — \n\n**Evidence** — \n\n**Next** — ",
    },
    "faq": {
        "note": "",
        "q-a": "**Q:** \n\n**A:** ",
    },
    "prompt": {
        "note": "",
        "style": "Audience: \n\nTone: \n\nMust include: \n\nAvoid: \n\nLength: ",
    },
}






_task = task_brief  # the task behind a note (deps)


# ---------------------------------------------------------------------------
# Story notes on a task
# ---------------------------------------------------------------------------


@router.get("/api/story/templates")
def story_templates() -> dict:
    return {"types": list(TASK_NOTE_TYPES), "kinds": list(DOC_KINDS), "templates": TEMPLATES}


@router.get("/api/tasks/notes")
def notes_wall(
    request: Request,
    project: str = Query(...),
    type: str | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Every story note of the project's tasks (home or member), with the
    task title — the Storyboard wall."""
    etag = etag_for(f"notes:wall:{project}:{type}", store, "tasks")
    if (r := maybe_304(request, etag)) is not None:
        return r
    clauses = ["(t.project = ? OR list_contains(string_split(COALESCE(t.projects, ''), ','), ?))"]
    params: list[Any] = [project, project]
    if type:
        clauses.append("n.type = ?")
        params.append(type)
    rows = store.query(
        "SELECT n.id, n.task_id, n.project, n.type, n.template, n.body, n.created_at, "
        "n.updated_at, n.actor, t.title AS task_title, t.status AS task_status "
        "FROM task_notes_mutual n JOIN tasks_mutual t ON t.id = n.task_id "
        "WHERE " + " AND ".join(clauses) + " ORDER BY n.created_at DESC",
        tuple(params),
    )
    return json_response({"total": len(rows), "notes": rows}, etag)


@router.get("/api/tasks/notes/summary")
def notes_summary(
    request: Request, project: str = Query(...), store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"notes:summary:{project}", store, "tasks")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT n.task_id, COUNT(*) AS n FROM task_notes_mutual n JOIN tasks_mutual t "
        "ON t.id = n.task_id WHERE t.project = ? OR "
        "list_contains(string_split(COALESCE(t.projects, ''), ','), ?) GROUP BY n.task_id",
        (project, project),
    )
    return json_response({"notes": {r["task_id"]: int(r["n"]) for r in rows}}, etag)


@router.get("/api/tasks/{task_id}/notes")
def notes_of_task(task_id: str, request: Request, store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for(f"notes:task:{task_id}", store, "tasks")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT * FROM task_notes_mutual WHERE task_id = ? ORDER BY created_at ASC", (task_id,)
    )
    return json_response({"total": len(rows), "notes": rows}, etag)


@router.post("/api/tasks/{task_id}/notes", status_code=201)
def notes_create(
    task_id: str, response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{type, body, template?, actor?}`` — type ∈ article | post | release
    | report | faq | prompt. The same note in the same minute is one note:
    the answer is then 200 with ``existing: true``."""
    ntype = str(body.get("type") or "").strip()
    text = str(body.get("body") or "").strip()
    if ntype not in TASK_NOTE_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(TASK_NOTE_TYPES)}")
    if not text:
        raise HTTPException(status_code=422, detail="body is required")
    task = _task(store, task_id)
    if task is None:
        raise not_found("task", task_id)
    now = now_iso()
    actor = str(body.get("actor") or _ACTOR)
    # "The same note in the same minute is one note" — so the id is seeded
    # with the minute, not the second. Seeded with the second, a double
    # click that straddled a tick minted two ids and wrote the note twice.
    note_id = mint_id("nt_", task_id, ntype, text, now[:16])
    csv_path = store.data_root / "task_notes.csv"
    row = {
        "id": note_id, "task_id": task_id,
        "project": str(task.get("project") or ""), "type": ntype,
        "template": str(body.get("template") or "note"), "body": text,
        "created_at": now, "updated_at": now, "actor": actor,
    }
    # Looked for and written in one locked step: both halves of a double
    # click used to pass a look made before either had written.
    existing = append_if_absent(csv_path, TASK_NOTE_COLUMNS, row)
    if existing is not None:
        # A double click or a retried request: the row is there, answer with it.
        return create_answer({"note": existing}, response, existing=True)
    _append_events(store, task_id, actor, [("note", "", ntype)])
    store.rebuild()
    return create_answer({"note": row})


def _rewrite_note(store: ViewStore, note_id: str, fn) -> dict:
    return rewrite_one(store, "task_notes.csv", TASK_NOTE_COLUMNS, note_id, fn, "note")


@router.post("/api/tasks/notes/{note_id}/update")
def notes_update(note_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    def fn(_rows, r):
        if "body" in body and str(body["body"]).strip():
            r["body"] = str(body["body"]).strip()
        if "type" in body and str(body["type"]) in TASK_NOTE_TYPES:
            r["type"] = str(body["type"])
        r["updated_at"] = now_iso()
        return True
    return {"note": _rewrite_note(store, note_id, fn)}


@router.post("/api/tasks/notes/{note_id}/delete")
def notes_delete(note_id: str, store: ViewStore = Depends(get_store)) -> dict:
    def fn(rows, r):
        rows.remove(r)
        return True
    _rewrite_note(store, note_id, fn)
    from .story_release import drop_note_images
    drop_note_images(store, note_id)
    # Items pointing at the note lose their reference but keep their place.
    items_csv = store.data_root / "doc_items.csv"
    if items_csv.exists():
        def strip(rows: list[dict[str, str]]) -> bool:
            changed = False
            for it in rows:
                if it.get("note_id") == note_id:
                    it["note_id"] = ""
                    it["text"] = it.get("text") or "(note removed)"
                    changed = True
            return changed
        rewrite_rows(items_csv, DOC_ITEM_COLUMNS, strip)
        store.rebuild()
    return {"deleted": note_id}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.get("/api/docs")
def docs_list(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for(f"docs:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT d.*, (SELECT COUNT(*) FROM doc_items_mutual i WHERE i.doc_id = d.id) AS items_n, "
        "(SELECT COUNT(*) FROM doc_versions_mutual v WHERE v.doc_id = d.id) AS versions_n "
        "FROM docs_mutual d WHERE d.project = ? ORDER BY d.updated_at DESC",
        (project,),
    )
    return json_response({"total": len(rows), "docs": rows}, etag)


@router.post("/api/docs", status_code=201)
def docs_create(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    project = str(body.get("project") or "").strip()
    kind = str(body.get("kind") or "article").strip()
    title = str(body.get("title") or "").strip()
    if not project or not title:
        raise HTTPException(status_code=422, detail="project and title are required")
    if kind not in DOC_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(DOC_KINDS)}")
    now = now_iso()
    row = {
        "id": mint_id("dc_", project, kind, title, now), "project": project, "kind": kind,
        "title": title, "status": "draft", "created_at": now, "updated_at": now,
        "actor": str(body.get("actor") or _ACTOR),
    }
    append_row(store.data_root / "docs.csv", DOC_COLUMNS, row)
    store.rebuild()
    return create_answer({"doc": row})


def _doc(store: ViewStore, doc_id: str) -> dict:
    row = store.query_one("SELECT * FROM docs_mutual WHERE id = ?", (doc_id,))
    if row is None:
        raise not_found("doc", doc_id)
    return row


def _touch_doc(store: ViewStore, doc_id: str, **changes: str) -> dict:
    csv_path = store.data_root / "docs.csv"
    hit: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == doc_id:
                for k, v in changes.items():
                    if k in DOC_COLUMNS and k not in ("id", "project", "created_at"):
                        r[k] = v
                r["updated_at"] = now_iso()
                hit.append(r)
                return True
        return False

    if csv_path.exists():
        rewrite_rows(csv_path, DOC_COLUMNS, mutate)
    if not hit:
        raise not_found("doc", doc_id)
    return hit[0]


def _items(store: ViewStore, doc_id: str) -> list[dict]:
    rows = store.query(
        "SELECT i.id, i.doc_id, i.position, i.note_id, i.text, n.type AS note_type, "
        "n.body AS note_body, n.task_id, t.title AS task_title "
        "FROM doc_items_mutual i LEFT JOIN task_notes_mutual n ON n.id = i.note_id "
        "LEFT JOIN tasks_mutual t ON t.id = n.task_id WHERE i.doc_id = ? "
        "ORDER BY TRY_CAST(i.position AS INTEGER) ASC, i.id ASC",
        (doc_id,),
    )
    return rows


@router.get("/api/docs/{doc_id}")
def docs_detail(doc_id: str, request: Request, store: ViewStore = Depends(get_store)) -> Response:
    etag = etag_for(f"docs:one:{doc_id}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    doc = _doc(store, doc_id)
    # Newest first. Two posts in one second tie on the stamp: the file's
    # order (the view keeps it) breaks the tie, the later append first.
    versions = store.query(
        "SELECT id, doc_id, created_at, agent_id, body, COALESCE(note, '') AS note FROM doc_versions_mutual "
        "WHERE doc_id = ?", (doc_id,)
    )
    versions.reverse()
    versions.sort(key=lambda v: str(v.get("created_at") or ""), reverse=True)
    mentions = store.query(
        "SELECT agent_id, session_id, turn, at_ts AS at, role, excerpt FROM task_mentions "
        "WHERE task_id = ? ORDER BY at_ts DESC, turn DESC, CASE role WHEN 'agent' THEN 0 ELSE 1 END",
        (doc_id,)
    )
    return json_response(
        {"doc": doc, "items": _items(store, doc_id), "versions": versions, "mentions": mentions}, etag
    )


@router.post("/api/docs/{doc_id}/update")
def docs_update(doc_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    changes = {k: str(v) for k, v in body.items() if k in ("title", "kind", "status") and str(v).strip()}
    if "kind" in changes and changes["kind"] not in DOC_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {', '.join(DOC_KINDS)}")
    row = _touch_doc(store, doc_id, **changes)
    store.rebuild()
    return {"doc": row}


@router.post("/api/docs/{doc_id}/delete")
def docs_delete(doc_id: str, store: ViewStore = Depends(get_store)) -> dict:
    _doc(store, doc_id)
    for csv_name, cols, key in (("doc_items.csv", DOC_ITEM_COLUMNS, "doc_id"),
                                ("doc_versions.csv", DOC_VERSION_COLUMNS, "doc_id"),
                                ("docs.csv", DOC_COLUMNS, "id")):
        p = store.data_root / csv_name
        if p.exists():
            rewrite_rows(p, cols, lambda rows, k=key: (rows.__setitem__(slice(None), [r for r in rows if r.get(k) != doc_id]) or True))
    store.rebuild()
    return {"deleted": doc_id}


@router.post("/api/docs/{doc_id}/items", status_code=201)
def items_add(doc_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{note_id}`` places a note; ``{text}`` adds a free block. Appended
    at the end unless ``position`` is given (0-based; the rest shift)."""
    _doc(store, doc_id)
    note_id = str(body.get("note_id") or "").strip()
    text = str(body.get("text") or "")
    if not note_id and not text.strip():
        raise HTTPException(status_code=422, detail="note_id or text is required")
    if note_id and store.query_one("SELECT id FROM task_notes_mutual WHERE id = ?", (note_id,)) is None:
        raise not_found("note", note_id)
    existing = _items(store, doc_id)
    pos = body.get("position")
    order = [it["id"] for it in existing]
    new_id = mint_id("di_", doc_id, note_id or text, now_iso(), str(len(existing)))
    try:
        idx = len(order) if pos is None else max(0, min(len(order), int(pos)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="position must be a number")
    order.insert(idx, new_id)
    append_row(store.data_root / "doc_items.csv", DOC_ITEM_COLUMNS,
               {"id": new_id, "doc_id": doc_id, "position": str(idx), "note_id": note_id, "text": text})
    _apply_order(store, doc_id, order)
    _touch_doc(store, doc_id)
    store.rebuild()
    return create_answer({"item_id": new_id, "items": _items(store, doc_id)})


def _apply_order(store: ViewStore, doc_id: str, order: list[str]) -> None:
    p = store.data_root / "doc_items.csv"
    if not p.exists():
        return
    rank = {iid: i for i, iid in enumerate(order)}

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            if r.get("doc_id") == doc_id and r.get("id") in rank:
                new = str(rank[r["id"]])
                if r.get("position") != new:
                    r["position"] = new
                    changed = True
        return changed
    rewrite_rows(p, DOC_ITEM_COLUMNS, mutate)


@router.post("/api/docs/{doc_id}/reorder")
def items_reorder(doc_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    _doc(store, doc_id)
    if not isinstance(body.get("item_ids"), list):
        raise HTTPException(status_code=422, detail="item_ids is a list of item ids")
    order = [str(x) for x in body["item_ids"] if str(x)]
    if not order:
        raise HTTPException(status_code=422, detail="item_ids is required")
    _apply_order(store, doc_id, order)
    _touch_doc(store, doc_id)
    store.rebuild()
    return {"items": _items(store, doc_id)}


@router.post("/api/docs/{doc_id}/items/{item_id}/update")
def items_update(doc_id: str, item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    p = store.data_root / "doc_items.csv"
    hit: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == item_id and r.get("doc_id") == doc_id:
                if "text" in body:
                    r["text"] = str(body["text"])
                hit.append(r)
                return True
        return False
    if p.exists():
        rewrite_rows(p, DOC_ITEM_COLUMNS, mutate)
    if not hit:
        raise not_found("item", item_id)
    _touch_doc(store, doc_id)
    store.rebuild()
    return {"items": _items(store, doc_id)}


@router.post("/api/docs/{doc_id}/items/{item_id}/delete")
def items_delete(doc_id: str, item_id: str, store: ViewStore = Depends(get_store)) -> dict:
    p = store.data_root / "doc_items.csv"
    removed: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        keep = [r for r in rows if not (r.get("id") == item_id and r.get("doc_id") == doc_id)]
        removed.extend(r for r in rows if r.get("id") == item_id and r.get("doc_id") == doc_id)
        if not removed:
            return False
        rows[:] = keep
        return True
    if p.exists():
        rewrite_rows(p, DOC_ITEM_COLUMNS, mutate)
    if not removed:
        raise not_found("item", item_id)
    _touch_doc(store, doc_id)
    store.rebuild()
    return {"items": _items(store, doc_id)}


def _doc_for_version(store: ViewStore, doc_id: str) -> dict:
    """The document a version is posted to. Decisions mint ``dc_`` ids
    too, so an id that names a decision is told apart from one that names
    nothing: an agent that copied the wrong id learns which it was."""
    row = store.query_one("SELECT * FROM docs_mutual WHERE id = ?", (doc_id,))
    if row is not None:
        return row
    if store.query_one("SELECT id FROM decisions_mutual WHERE id = ?", (doc_id,)) is not None:
        raise HTTPException(
            status_code=404,
            detail=f"{doc_id} is a decision, not a Storyboard document — "
                   "post the version under the doc id the pack names on its second line",
        )
    raise HTTPException(
        status_code=404,
        detail=f"doc not found: {doc_id} — the doc id (dc_…) is on the pack's second line; "
               "ask the operator for the pack again if the document was deleted",
    )


@router.post("/api/docs/{doc_id}/versions", status_code=201)
def versions_add(doc_id: str, response: Response, body: dict = Body(...),
                 store: ViewStore = Depends(get_store)) -> dict:
    """``{body, note?, agent_id?}`` — the finished text of the document,
    kept, dated and signed. An agent posts it with the MCP tool
    ``doc_version`` after it was handed the pack (its identity is stamped
    there; a raw HTTP write from an agent is refused by the MCP gate); the
    operator pastes one by hand from the Storyboard. The same text posted
    twice in the same minute is one version (200, ``existing: true``)."""
    doc = _doc_for_version(store, doc_id)
    text = str(body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="body is required — the document's finished text, in markdown")
    if len(text) > limits.MAX_DOC_VERSION:
        raise HTTPException(status_code=422, detail=f"body is at most {limits.MAX_DOC_VERSION} characters")
    note = " ".join(str(body.get("note") or "").split())
    if len(note) > limits.MAX_NOTE:
        raise HTTPException(status_code=422, detail=f"note is one line, at most {limits.MAX_NOTE} characters")
    who = identity_of(body) or _ACTOR
    now = now_iso()
    row = {"id": mint_id("dv_", doc_id, who, text, now[:16]), "doc_id": doc_id, "created_at": now,
           "agent_id": who, "body": text, "note": note}
    existing = append_if_absent(store.data_root / "doc_versions.csv", DOC_VERSION_COLUMNS, row)
    if existing is not None:
        return create_answer({"version": existing}, response, existing=True)
    _touch_doc(store, doc_id, status="drafted")
    store.rebuild()
    n = len(store.query("SELECT id FROM doc_versions_mutual WHERE doc_id = ?", (doc_id,)))
    return create_answer({"version": row, "n": n, "doc": {"id": doc_id, "title": doc.get("title")}})


# ---------------------------------------------------------------------------
# The pack — three layers of markdown for an agent (or any LLM chat)
# ---------------------------------------------------------------------------


def build_pack(store: ViewStore, doc_id: str) -> str:
    doc = _doc(store, doc_id)
    items = _items(store, doc_id)
    task_ids: list[str] = []
    for it in items:
        tid = str(it.get("task_id") or "")
        if tid and tid not in task_ids:
            task_ids.append(tid)

    # Prompt notes: placed in the doc, plus every referenced task's own.
    prompt_lines: list[str] = []
    for it in items:
        if it.get("note_type") == "prompt" and it.get("note_body"):
            prompt_lines.append(str(it["note_body"]))
    task_prompts: dict[str, list[str]] = {}
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        for n in store.query(
            f"SELECT task_id, type, body FROM task_notes_mutual WHERE task_id IN ({ph}) AND type = 'prompt'",
            tuple(task_ids),
        ):
            task_prompts.setdefault(str(n["task_id"]), []).append(str(n["body"]))

    out: list[str] = []
    out.append(f"# {doc['title']}")
    out.append(f"*{doc['kind']} · {doc_id} · project {doc['project']} · status {doc.get('status') or 'draft'}*")
    out.append("")
    out.append("This pack has three parts. **The document** is as the operator arranged it: "
               "make it final in that shape, then post the finished text with the Slightly Parallel "
               f"MCP tool `doc_version {{id: \"{doc_id}\", body, note}}` — it is kept as a version "
               "on the Storyboard; `note` is one line on what this version changed. Without that "
               "tool, give the finished text in your reply and the operator pastes it in. "
               "**Context** is what the tasks say; **Connections** is where to verify "
               "(code, chats, checkpoints). Check claims against the code before you write them down.")
    out.append("")
    if prompt_lines or any(task_prompts.values()):
        out.append("## Instructions (prompt notes)")
        for p in prompt_lines:
            out.append(f"- {p}")
        for tid, ps in task_prompts.items():
            for p in ps:
                out.append(f"- ({tid}) {p}")
        out.append("")

    out.append("## The document")
    for it in items:
        if it.get("note_type") == "prompt":
            continue
        if it.get("note_id"):
            out.append(f"<!-- note {it['note_id']} · {it.get('note_type')} · task {it.get('task_id')} -->")
            out.append(str(it.get("note_body") or ""))
        else:
            out.append(str(it.get("text") or ""))
        out.append("")

    out.append("## Context")
    if not task_ids:
        out.append("(no task-bound notes in this document)")
    for tid in task_ids:
        t = _task(store, tid) or {"id": tid, "title": "", "status": ""}
        path = resolve_under(store.data_root, str(t.get("md_ref") or ""))
        turns = parse_task_doc(path.read_text(encoding="utf-8")) if path is not None and path.exists() else []
        out.append(f"### {t.get('title') or tid} · `{tid}` · {t.get('status') or ''}")
        for turn in turns:
            if turn.n > 1:
                out.append(f"Turn {turn.n} · {turn.date} {turn.time}".rstrip())
            if turn.text:
                out.append(turn.text)
        others = store.query(
            "SELECT type, body FROM task_notes_mutual WHERE task_id = ? AND type <> 'prompt' ORDER BY created_at",
            (tid,),
        )
        if others:
            out.append("Other story notes:")
            out.extend(f"- *{n['type']}*: {n['body']}" for n in others)
        links = store.query(
            "SELECT l.kind, l.from_id, l.to_id, a.title AS ft, b.title AS tt FROM task_links_mutual l "
            "LEFT JOIN tasks_mutual a ON a.id = l.from_id LEFT JOIN tasks_mutual b ON b.id = l.to_id "
            "WHERE l.from_id = ? OR l.to_id = ?", (tid, tid),
        )
        if links:
            out.append("Links:")
            out.extend(f"- {l['ft'] or l['from_id']} {l['kind']} {l['tt'] or l['to_id']}" for l in links)
        out.append("")

    out.append("## Connections (verify here)")
    if task_ids:
        ph = ",".join("?" * len(task_ids))
        mentions = store.query(
            f"SELECT task_id, agent_id, session_id, turn, at_ts AS at, role FROM task_mentions "
            f"WHERE task_id IN ({ph}) ORDER BY at_ts ASC", tuple(task_ids),
        )
        if mentions:
            out.append("Captured chats that named these tasks (agent · session · turn · time · role):")
            out.extend(f"- {m['task_id']} · {m['agent_id']} · {m['session_id']} · turn {m['turn']} · {m['at']} · {m['role']}"
                       for m in mentions)
            first, last = mentions[0]["at"][:10], mentions[-1]["at"][:10]
            d0 = f"{first[2:4]}{first[5:7]}-{first[8:10]}"
            d1 = f"{last[2:4]}{last[5:7]}-{last[8:10]}"
            files = store.query(
                "SELECT id, created_date, created_time, l1 FROM files_mutual WHERE project = ? "
                "AND created_date >= ? AND created_date <= ? ORDER BY created_date, created_time",
                (doc["project"], d0, d1),
            )
            if files:
                out.append("File checkpoints in that span (GET /api/files/{id} for the annotated paths):")
                out.extend(f"- {f['id']} · {f['created_date']} {f['created_time']} · {f['l1']}" for f in files)
            decisions = store.query(
                "SELECT id, created_date, decision_text FROM decisions_mutual WHERE project = ? "
                "AND created_date >= ? AND created_date <= ? ORDER BY created_date",
                (doc["project"], d0, d1),
            )
            if decisions:
                out.append("Decisions in that span:")
                out.extend(f"- {d['id']} · {d['created_date']} · {d['decision_text']}" for d in decisions)
        else:
            out.append("(no captured chat named these tasks yet — copy a task to an agent and its id travels)")
    else:
        out.append("(nothing to trace — no task-bound notes)")
    out.append("")
    out.append(f"Sessions: GET /api/sessions?project={doc['project']} · tasks: GET /api/tasks/{{id}} · "
               f"this doc: GET /api/docs/{doc_id}")
    return "\n".join(out)


@router.get("/api/docs/{doc_id}/pack")
def docs_pack(doc_id: str, store: ViewStore = Depends(get_store)) -> PlainTextResponse:
    return PlainTextResponse(build_pack(store, doc_id), media_type="text/markdown; charset=utf-8")
