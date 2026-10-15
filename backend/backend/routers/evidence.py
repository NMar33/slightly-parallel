"""The agent-done loop: reports, evidence, and the operator's prompts.

Task status belongs to the operator. What an agent may do when it thinks
a task is finished is *say so*:

    POST /api/tasks/{id}/report {agent_id, summary}

The server records the opinion (a stamp on the task + a row in the event
history), moves the card to **review** only when the task opts in
(``auto_manage`` — set from the task window), and answers with whether
evidence is wanted. When it is (``evidence_required``), the response
carries the operator's evidence prompt verbatim, and the agent follows
up with:

    POST /api/tasks/{id}/evidence {agent_id, items: [...]}

Items are text (markdown) or images (base64; written under
``task_evidence/<task_id>/`` at the data root, indexed in
``task_evidence.csv``). The prompts themselves are the operator's —
named, editable, stored in ``evidence_prompts.json`` so every browser
and agent reads the same ones.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from .. import evidence_items, limits, story_images, taskwork
from ..csvio import append_if_absent, read_rows, rewrite_rows
from ..db import ViewStore
from ..docs_md import resolve_under
from ..entities import TASK_EVIDENCE_COLUMNS, TASK_EVIDENCE_KINDS, is_done
from ..file_safety import edit_json, safe_read_json
from .deps import create_answer, get_store, not_found, operator_only

router = APIRouter()

PROMPTS_FILE = "evidence_prompts.json"
EVIDENCE_DIR = "task_evidence"
MAX_ITEMS = 8
MAX_TEXT = limits.MAX_TEXT
# One number for both doors: the story tool already took 12 MB, and a
# screenshot it accepts must not be refused here (limits.py).
MAX_IMAGE_BYTES = limits.MAX_IMAGE_BYTES
IMAGE_EXTS = story_images.IMAGE_EXTS
MAX_PROMPTS = 50
# A file the agent did not list is shown as missed only from this many changed lines.
MISSING_MIN_LINES = 20

DEFAULT_PROMPT = {
    "id": "default",
    "name": "Prove it, briefly",
    "text": (
        "Prove that what the task asked for now works, in 1–3 items, each "
        "with a one-line title saying what it shows. Pick what fits: a visual "
        "change → before/after screenshots if you can render the page; an API "
        "or backend change → the request and the response; a bugfix → the "
        "failing case, now passing; anything else → the one test that covers "
        "this change, not the whole suite. Text is markdown, each item under "
        "a screenful. End with one line: what you did not verify."
    ),
}


# ---------------------------------------------------------------------------
# The prompt store — named, editable, shared
# ---------------------------------------------------------------------------


# Earlier built-in texts. A saved "default" that still reads as one of these
# was never edited, so it follows the built-in text; one the operator changed
# is theirs and stays as written.
PREVIOUS_DEFAULT_TEXTS: tuple[str, ...] = (
    "Prove the work in 1–3 evidence items, each with a one-line title "
    "saying what it shows. Pick what fits: a visual change → before/after "
    "screenshots if you can render the page; an API or backend change → "
    "the request and response, or the test output; an architecture "
    "change → what the shape was and what it is now; a bugfix → the "
    "failing case, now passing. Text items are markdown; keep each "
    "under a screenful.",
)


def _load_prompts(store: ViewStore) -> dict:
    path = store.data_root / PROMPTS_FILE
    data = None
    if path.exists():
        try:
            data = safe_read_json(path)
        except (OSError, ValueError):
            data = None
    return _clean_prompts(data)


def _clean_prompts(data: Any) -> dict:
    """The stored document, made whole: the built-in prompt is always
    there, an unknown default falls back to it."""
    if not isinstance(data, dict) or not isinstance(data.get("prompts"), list):
        data = {"default_id": DEFAULT_PROMPT["id"], "prompts": [dict(DEFAULT_PROMPT)]}
    prompts = [
        p for p in data["prompts"]
        if isinstance(p, dict) and p.get("id") and p.get("name") and p.get("text")
    ]
    if not any(p["id"] == "default" for p in prompts):
        prompts.insert(0, dict(DEFAULT_PROMPT))
    for p in prompts:
        if p["id"] == "default" and p["text"] in PREVIOUS_DEFAULT_TEXTS:
            p["text"] = DEFAULT_PROMPT["text"]
    default_id = str(data.get("default_id") or "default")
    if not any(p["id"] == default_id for p in prompts):
        default_id = "default"
    return {"default_id": default_id, "prompts": prompts}


# What the server adds under the operator's prompt, whichever prompt it is:
# the account of the work itself. Kept apart from the prompt, which stays the
# operator's text verbatim. Setting `evidence.work_items` turns it off.
EVIDENCE_EXTRA = (
    "Also say what the task touched and what it did, as two more items: one "
    "`files` item (call task_work first and judge that list: path, action, "
    "importance 1-5, why in one sentence, and `start_here`, the file to open "
    "first) and one `change` item (what landed: op, type, name, path, one-line "
    "note). Keep both short: up to seven files that matter, not every file."
)


def _ask(store: ViewStore, task: dict) -> tuple[str, str, str]:
    """(prompt id, the operator's prompt verbatim, the server's addition).

    One place for both ways in: a done-report on a task with evidence on,
    and `#evidence` typed by the operator. The same instructions either way.
    """
    from .. import app_settings

    prompt_id, prompt = _prompt_text(store, str(task.get("evidence_prompt") or ""))
    wants_work = bool(app_settings.load(store.data_root).get("evidence.work_items", True))
    return prompt_id, prompt, EVIDENCE_EXTRA if wants_work else ""


def _edit_prompts(store: ViewStore, change) -> dict:
    """Read-modify-write evidence_prompts.json under one lock
    (file_safety.edit_json) — two saves at once kept both prompts."""
    def apply(raw: dict) -> dict:
        data = _clean_prompts(raw)
        change(data)
        return data

    return edit_json(store.data_root / PROMPTS_FILE, apply)


def _prompt_text(store: ViewStore, prompt_id: str) -> tuple[str, str]:
    """Resolve a prompt id (empty = default) to (id, text)."""
    data = _load_prompts(store)
    wanted = prompt_id or data["default_id"]
    for p in data["prompts"]:
        if p["id"] == wanted:
            return p["id"], p["text"]
    fallback = next(p for p in data["prompts"] if p["id"] == data["default_id"])
    return fallback["id"], fallback["text"]


@router.get("/api/evidence-prompts")
def evidence_prompts(store: ViewStore = Depends(get_store)) -> dict:
    return _load_prompts(store)


@router.post("/api/evidence-prompts", status_code=200)
def evidence_prompts_save(
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Create or update one named prompt. ``{name, text, id?}`` — no id
    creates a new one; ``make_default: true`` also selects it."""
    operator_only(body, "the evidence prompts")
    name = str(body.get("name") or "").strip()
    text = str(body.get("text") or "").strip()
    if not name or not text:
        raise HTTPException(status_code=422, detail="a prompt needs a name and a text")
    if len(name) > 60 or len(text) > 4000:
        raise HTTPException(status_code=422, detail="the name takes up to 60 characters and the text up to 4000")
    pid = str(body.get("id") or "").strip()

    def change(data: dict) -> None:
        nonlocal pid
        if pid:
            target = next((p for p in data["prompts"] if p["id"] == pid), None)
            if target is None:
                raise not_found("prompt", pid)
            target["name"], target["text"] = name, text
        else:
            if len(data["prompts"]) >= MAX_PROMPTS:
                raise HTTPException(status_code=422, detail=f"at most {MAX_PROMPTS} prompts")
            pid = "ep_" + hashlib.sha256(f"{name}{time.time()}".encode()).hexdigest()[:8]
            data["prompts"].append({"id": pid, "name": name, "text": text})
        if body.get("make_default"):
            data["default_id"] = pid

    data = _edit_prompts(store, change)
    return {**data, "saved": pid, "warnings": []}


@router.post("/api/evidence-prompts/{prompt_id}/delete")
def evidence_prompts_delete(
    prompt_id: str,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    operator_only(body, "the evidence prompts")
    if prompt_id == "default":
        raise HTTPException(status_code=409, detail="the built-in prompt stays")
    def change(data: dict) -> None:
        before = len(data["prompts"])
        data["prompts"] = [p for p in data["prompts"] if p["id"] != prompt_id]
        if len(data["prompts"]) == before:
            raise not_found("prompt", prompt_id)
        if data["default_id"] == prompt_id:
            data["default_id"] = "default"

    return _edit_prompts(store, change)


# ---------------------------------------------------------------------------
# The report — an agent's opinion, and maybe a move
# ---------------------------------------------------------------------------


def _task(store: ViewStore, task_id: str) -> dict:
    row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"task not found: {task_id} — check the id in the [slightly-parallel] notice, "
                "or list the board with the MCP tool tasks."
            ),
        )
    return row


@router.post("/api/tasks/{task_id}/report", status_code=200)
def task_report(
    task_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """An agent reports the task done, in its opinion. Never the verdict:
    with ``auto_manage`` the card moves to *review*; without it only the
    badge appears. The response says whether evidence is wanted and, when
    it is, carries the operator's instructions."""
    from .tasks_extra import _append_events, after_status_change  # shared history writer
    from ..entities import ENTITIES

    agent_id = str(body.get("agent_id") or "").strip()
    summary = str(body.get("summary") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    if len(summary) > 500:
        raise HTTPException(status_code=422, detail="summary is at most 500 characters")

    task = _task(store, task_id)

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    ent = ENTITIES["task"]
    changes: list[tuple[str, str, str]] = [("agent_report", "", summary or "done")]
    side_events: list = []
    # Decided on the row as it is under the lock, not on the view read a
    # moment ago: the operator may have moved or archived the card since.
    seen = {"auto": False, "old": "", "moves": False}

    def mutate(rows: list[dict[str, str]]) -> bool:
        target = next((r for r in rows if r.get("id") == task_id), None)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"task not found in tasks.csv: {task_id} — list the board with "
                    "the MCP tool tasks and report the one you meant."
                ),
            )
        if str(target.get("archived_at") or ""):
            raise HTTPException(status_code=409, detail="the task is archived")
        auto = str(target.get("auto_manage") or "") == "yes"
        old_status = str(target.get("status") or "")
        moves = auto and not is_done(old_status) and old_status.lower() != "review"
        seen.update(auto=auto, old=old_status, moves=moves)
        target["agent_done_at"] = now
        target["agent_done_by"] = agent_id
        target["agent_done_note"] = summary
        if moves:
            target["status"] = "review"
            target["agent_moved_at"] = now
            changes.append(("status", old_status, "review"))
            changes.append(("agent_moved_at", "", now))
            # A card leaving its column advances its stack, whoever moved it.
            after_status_change(store, rows, target, old_status, changes, deferred=side_events)
        return True

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    for other_id, other_actor, other_changes in side_events:
        _append_events(store, other_id, other_actor, other_changes)
    _append_events(store, task_id, agent_id, changes)
    store.rebuild()
    auto, old_status, moves = seen["auto"], seen["old"], seen["moves"]

    wants_evidence = str(task.get("evidence_required") or "") == "yes"
    prompt_id, prompt, extra = _ask(store, task) if wants_evidence else ("", "", "")
    return {
        "task_id": task_id,
        "recorded": True,
        "moved": moves,
        "status": "review" if moves else old_status,
        "auto_manage": auto,
        "evidence": wants_evidence,
        "evidence_prompt": prompt,
        "evidence_prompt_id": prompt_id,
        "evidence_extra": extra,
        "next": (
            f"MCP tool task_evidence {{id: \"{task_id}\", items}} — follow "
            "evidence_prompt, then evidence_extra."
        ) if wants_evidence else "",
    }


# ---------------------------------------------------------------------------
# Evidence — text and images, indexed per task
# ---------------------------------------------------------------------------


@router.post("/api/tasks/{task_id}/evidence", status_code=201)
def evidence_add(
    task_id: str,
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    agent_id = str(body.get("agent_id") or "").strip()
    items = body.get("items")
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=422, detail="items must be a non-empty list")
    if len(items) > MAX_ITEMS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_ITEMS} items per post")

    task = _task(store, task_id)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Every item is checked before anything is written: a bad second item
    # must not leave the first on disk, and a retry after a 422 must not
    # add it twice. The id is the content, so the same item posted again
    # is the same row.
    checked: list[tuple[str, str, str, str, bytes | None]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"item {i}: not an object")
        kind = str(item.get("kind") or "").strip()
        title = str(item.get("title") or "").strip()[:limits.MAX_TITLE]
        if kind not in TASK_EVIDENCE_KINDS:
            raise HTTPException(
                status_code=422,
                detail=f"item {i}: kind must be one of {', '.join(TASK_EVIDENCE_KINDS)}",
            )
        if kind in ("files", "change"):
            # What was touched and what was done: structured, in the words
            # the file entry and the architecture form already use. Stored
            # as JSON in the same column that holds a note or a file path.
            try:
                payload = (
                    evidence_items.clean_files(item) if kind == "files"
                    else evidence_items.clean_changes(item)
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"item {i}: {exc}")
            checked.append((kind, title, "", evidence_items.dump(payload), None))
        elif kind == "text":
            text = str(item.get("body") or "").strip()
            if not text:
                raise HTTPException(status_code=422, detail=f"item {i}: text body is empty")
            if len(text) > MAX_TEXT:
                raise HTTPException(status_code=422, detail=f"item {i}: text is at most {MAX_TEXT} characters")
            checked.append((kind, title, "", text, None))
        else:
            ext, raw = story_images.checked_image(item, f"item {i}")
            digest = hashlib.sha256(raw).hexdigest()
            checked.append((kind, title, ext, digest, raw))

    known = {
        str(r.get("id") or "")
        for r in read_rows(store.data_root / "task_evidence.csv")
        if str(r.get("task_id") or "") == task_id
    }
    saved = []
    try:
        for kind, title, ext, text_or_digest, raw in checked:
            digest = text_or_digest if raw is not None else hashlib.sha256(text_or_digest.encode("utf-8")).hexdigest()
            eid = "tev_" + hashlib.sha256(f"{task_id}|{agent_id}|{kind}|{title}|{digest}".encode()).hexdigest()[:10]
            if eid in known:
                saved.append({"id": eid, "kind": kind, "title": title, "existing": True})
                continue
            if raw is not None:
                rel = f"{EVIDENCE_DIR}/{task_id}/{eid}.{ext}"
                path = store.data_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                stored = rel
            else:
                stored = text_or_digest
            raced = append_if_absent(
                store.data_root / "task_evidence.csv",
                TASK_EVIDENCE_COLUMNS,
                {
                    "id": eid, "task_id": task_id,
                    "project": str(task.get("project") or ""),
                    "agent_id": agent_id, "created_at": now,
                    "kind": kind, "title": title, "body": stored,
                },
            )
            known.add(eid)
            # A retry that ran beside this post wrote the row first.
            saved.append({"id": eid, "kind": kind, "title": title,
                          **({"existing": True} if raced is not None else {})})
        new = [s for s in saved if not s.get("existing")]
        if new:
            from .tasks_extra import _append_events
            _append_events(store, task_id, agent_id, [("evidence", "", f"{len(new)} item(s)")])
    finally:
        # Whatever landed is in the view, never half on disk and half unseen.
        store.rebuild()
    # The one rule for a repeated create: nothing new written → 200 and
    # `existing: true`; something written → 201.
    repeat = bool(saved) and all(s.get("existing") for s in saved)
    return create_answer({"task_id": task_id, "saved": saved}, response, existing=repeat)


@router.get("/api/tasks/evidence/summary")
def evidence_summary(
    project: str,
    store: ViewStore = Depends(get_store),
) -> dict:
    """How many evidence items each task of a project holds — the count
    the board draws on a card, in one query instead of one per task."""
    rows = store.query(
        "SELECT e.task_id, COUNT(*) AS n, "
        "SUM(CASE WHEN e.kind = 'image' THEN 1 ELSE 0 END) AS images "
        "FROM task_evidence_mutual e JOIN tasks_mutual t ON t.id = e.task_id "
        "WHERE t.project = ? OR list_contains(string_split(COALESCE(t.projects, ''), ','), ?) "
        "GROUP BY e.task_id",
        (project, project),
    )
    return {
        "evidence": {r["task_id"]: int(r["n"] or 0) for r in rows},
        "images": {r["task_id"]: int(r["images"] or 0) for r in rows},
    }


@router.get("/api/tasks/{task_id}/evidence/ask")
def evidence_ask(task_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """`#evidence`: the same instructions a done-report would have carried.

    The operator typed the command, so the checkbox does not matter here.
    The task's chosen prompt (or the default), the server's addition, and
    git's account of the work so the agent judges the file list.
    """
    task = _task(store, task_id)
    prompt_id, prompt, extra = _ask(store, task)
    return {
        "task_id": task_id,
        "evidence_prompt": prompt,
        "evidence_prompt_id": prompt_id,
        "evidence_extra": extra,
        "work": taskwork.task_work(store, task_id),
        "next": f"MCP tool task_evidence {{id: \"{task_id}\", items}}",
    }


@router.get("/api/tasks/{task_id}/work")
def task_work(task_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """What the repository saw in the turns that named this task.

    The agent reads this before writing a ``files`` evidence item, so it
    judges the list instead of hunting for it (``taskwork.py``).
    """
    return {"task_id": task_id, "work": taskwork.task_work(store, task_id)}


@router.get("/api/tasks/{task_id}/evidence")
def evidence_list(
    task_id: str,
    store: ViewStore = Depends(get_store),
) -> dict:
    """The task's evidence, with git's account of the same work beside it.

    A ``files`` item's paths each carry ``in_git``: whether the repository
    saw that file change in the turns that named the task. ``missing`` is
    the other direction — what git saw that no item claims. Neither is a
    verdict; the agent may have worked outside the repository, and a file
    may be uninteresting. They are shown so the two accounts can disagree
    in the open.
    """
    rows = store.query(
        "SELECT * FROM task_evidence_mutual WHERE task_id = ? ORDER BY created_at DESC",
        (task_id,),
    )
    work = taskwork.task_work(store, task_id)
    seen = {str(f["path"]) for f in work["files"]}
    claimed: set[str] = set()
    for r in rows:
        kind = str(r.get("kind") or "")
        if kind == "image":
            r["url"] = f"/api/tasks/evidence/{r['id']}/file"
        elif kind in ("files", "change"):
            payload = evidence_items.load(str(r.get("body") or ""))
            if kind == "files":
                paths = payload.get("paths") or []
                for p in paths:
                    p["in_git"] = str(p.get("path") or "") in seen
                    claimed.add(str(p.get("path") or ""))
                r["paths"] = paths
                r["start_here"] = str(payload.get("start_here") or "")
            else:
                r["changes"] = payload.get("changes") or []
    # Only committed files count as missed. The working tree is shared by
    # whatever else is running on this laptop, so a dirty file is reported
    # (in `work`) but never held against the agent (see taskwork.py).
    # And only files with large changes: the agent is asked to keep its list
    # short, so every small file it left out is not news.
    missing = [
        f for f in work["files"]
        if f["path"] not in claimed and f.get("committed")
        and f["lines_add"] + f["lines_del"] >= MISSING_MIN_LINES
    ] if claimed else []
    return {"task_id": task_id, "evidence": rows, "work": work, "missing": missing}


@router.post("/api/tasks/evidence/{evidence_id}/delete")
def evidence_delete(
    evidence_id: str,
    body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Drop one evidence item — the ledger row and, for a screenshot, the
    file it points at. Proof the operator does not want is proof that
    should stop taking up the card."""
    operator_only(body, "removing evidence")
    row = store.query_one(
        "SELECT * FROM task_evidence_mutual WHERE id = ?", (evidence_id,)
    )
    if row is None:
        raise not_found("evidence", evidence_id)

    if str(row.get("kind") or "") == "image":
        # The stored path is ours, but it arrives through the view — resolve
        # it under the evidence folder before unlinking anything, as the
        # file route does: the CSV is agent-written data, and anywhere under
        # the data root was a task's CSV or chat as much as a screenshot.
        target = resolve_under(store.data_root, str(row.get("body") or ""))
        evidence_root = (store.data_root / EVIDENCE_DIR).resolve()
        if target is not None and evidence_root in target.parents and target.is_file():
            try:
                target.unlink()
            except OSError:
                pass  # the row still goes; a stray file is not worth a 500

    def mutate(rows: list[dict[str, str]]) -> bool:
        before = len(rows)
        rows[:] = [r for r in rows if r.get("id") != evidence_id]
        return len(rows) != before

    rewrite_rows(store.data_root / "task_evidence.csv", TASK_EVIDENCE_COLUMNS, mutate)
    store.rebuild()
    return {"deleted": evidence_id, "task_id": str(row.get("task_id") or "")}


@router.get("/api/tasks/evidence/{evidence_id}/file")
def evidence_file(
    evidence_id: str,
    store: ViewStore = Depends(get_store),
):
    row = store.query_one(
        "SELECT * FROM task_evidence_mutual WHERE id = ?", (evidence_id,)
    )
    if row is None or row.get("kind") != "image":
        raise not_found("image", evidence_id)
    rel = str(row.get("body") or "")
    # Confined to the evidence directory — the CSV is agent-written data.
    # By path parts, not by text: "task_evidence-old" starts with the same letters.
    path = (store.data_root / rel).resolve()
    evidence_root = (store.data_root / EVIDENCE_DIR).resolve()
    if evidence_root not in path.parents or not path.is_file():
        raise not_found("image file", evidence_id)
    return FileResponse(path)
