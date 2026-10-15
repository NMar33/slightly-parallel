"""Press releases — the operator asks, the agent writes, the note lands.

The Storyboard is the operator's field. This is the one door through
which an agent writes on it, and the operator opens it: the release
button on a task builds a prompt from three parts — the *focus* (what
matters this time), the *brief* (what to write) and the *style* (examples
of the voice) — records a *request* (``sr_…``) and hands the prompt to the
operator, who pastes it to the agent. The agent posts the piece back with
the request id; without an open request there is no post. Screenshots
come with it — the prompt asks for the size the ``story.image_quality``
setting names, the server keeps the bytes as sent — and the note lands on
the task with the images beside it.

Presets: each part keeps its own named texts in ``story_prompts.json`` at
the data root — the built-in brief and style stay, the operator's own are
added, renamed and removed. Everything long lives on disk, not in CSV:
the assembled prompt at ``task_story/<task>/<sr>.prompt.md`` and the
images at ``task_story/<task>/<si>.<ext>``.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from .. import app_settings, limits, story_images
from ..csvio import append_row, rewrite_rows
from ..db import ViewStore
from ..docs_md import resolve_under
from ..entities import (
    STORY_IMAGE_COLUMNS, STORY_REQUEST_COLUMNS, TASK_NOTE_COLUMNS, TASK_NOTE_TYPES,
)
from ..file_safety import atomic_write, edit_json, safe_read_json
from .deps import create_answer, get_store, mint_id, not_found, rewrite_one, task_brief
from .tasks_extra import _append_events
from ..date_utils import now_iso

router = APIRouter()

PROMPTS_FILE = "story_prompts.json"
STORY_DIR = "task_story"
PARTS = ("focus", "brief", "style")
RELEASE_TYPES = ("article", "post", "release")
MAX_NAME = limits.MAX_PRESET_NAME
MAX_PART = limits.MAX_STORY_PART
MAX_FOCUS_CSV = 4_000
MAX_PRESETS = 40
MAX_BODY = limits.MAX_STORY_BODY
MAX_IMAGES = 8
MAX_IMAGE_BYTES = limits.MAX_IMAGE_BYTES
IMAGE_EXTS = story_images.IMAGE_EXTS
_ACTOR = "operator"

BUILTIN = {
    "brief": {
        "id": "brief-default",
        "name": "The press kit",
        "text": (
            "Write about this task. It is my work and my ideas; say what was "
            "done, in plain words, in this order:\n\n"
            "1.1 What was built — dense: one line per feature, feature then "
            "description.\n"
            "1.2 How to use it — the steps, very short.\n"
            "2.1 The short press release — short and catchy; take the voice "
            "from the style examples.\n"
            "2.2 The problem and the solution — a few, each in a different "
            "style.\n"
            "2.3 Why you would pay for it — first think who the real users "
            "are and why they would care, then write from their side.\n"
            "3 A few ideas — thoughts, philosophy, what I may not have "
            "thought of.\n"
            "4.1 Real quotes from statisticians, programmers, founders — or "
            "4.2 one real, classic anecdote.\n\n"
            "Attach 1–4 screenshots of what was built, each with a one-line "
            "title, and put each where it belongs in the text."
        ),
    },
    "style": {
        "id": "style-default",
        "name": "My words, three voices",
        "text": (
            "Very important. It's my work, my ideas, my choice. There is a lot "
            "of original content. You don't have the right to steal it with "
            "watermarked LLM language.\n\n"
            "As a source of text style use the examples below. Use different "
            "examples for different parts of the answer. Use different words, "
            "and when you sample, don't take the word with the highest "
            "probability. Use vocabulary from the examples where it fits.\n\n"
            "Avoid at any cost: after distillation and corporate politics you "
            "have a watermarked language — words whose repetition, or even "
            "presence, shows that an LLM wrote it. That is bad and unfair to "
            "me. I do this project, I keep correcting you, I spend hours on it "
            "and it could be useful to people. A short press release is not a "
            "big deal: describe what was done, maybe in a fancier way. If you "
            "use watermarked language you steal my intellectual property.\n\n"
            "--- Example 1 · Andrew Wilkinson, MetaLab, on Slack ---\n\n"
            "It looked like a hacked together version of IRC in the browser. "
            "Barebones and stark. Just six weeks later, we had done some of "
            "the best work of our careers.\n\n"
            "We aren't big on process. We prefer to just put our heads down "
            "and design stuff, iterating over and over again until something "
            "feels right.\n\n"
            "--- Example 2 · Piero Paialunga, Towards Data Science, on anomaly "
            "detection ---\n\n"
            "In order to build the anomaly collector, we need to have a "
            "dataset where we know exactly what anomaly we are searching for, "
            "so that we know if our anomaly detector is working or not.\n\n"
            "Keep in mind that the baseline is simple on purpose, and it uses "
            "very simple statistics.\n\n"
            "--- Example 3 · Julia Evans, on compiling C programs ---\n\n"
            "Unlike some newer programming languages, C doesn't have a "
            "dependency manager. So if a program has any dependencies, you "
            "need to hunt them down yourself.\n\n"
            "Also I don't want to pretend that I \"magically\" knew that those "
            "were the right arguments to pass, figuring them out involved a "
            "bunch of confused Googling that I skipped over in this post.\n\n"
            "--- Rewrites I chose for this product's own text ---\n\n"
            "Not: A sprint is a bet: name the block, bet the days, budget your "
            "hours.\n"
            "Write: This creates a sprint, a named block of work with a length "
            "in days and an optional budget of your hours.\n\n"
            "Not: The living playbook — lessons promoted into rules.\n"
            "Write: Rules agents follow, written after something went wrong.\n\n"
            "Not: Finished work waits on your verdict.\n"
            "Write: In review.\n\n"
            "Not: Today cleared — 3 tasks stay where they are.\n"
            "Write: Removed 3 tasks from today's plan.\n"
        ),
    },
}






_task = task_brief  # the task behind a request (deps)





# ---------------------------------------------------------------------------
# Presets — a named text per part
# ---------------------------------------------------------------------------


def _load_presets(store: ViewStore) -> dict:
    path = store.data_root / PROMPTS_FILE
    data = None
    if path.exists():
        try:
            data = safe_read_json(path)
        except (OSError, ValueError):
            data = None
    return _clean_presets(data)


def _clean_presets(data: Any) -> dict:
    parts = data.get("parts") if isinstance(data, dict) else None
    if not isinstance(parts, dict):
        parts = {}
    out: dict[str, list[dict]] = {}
    for part in PARTS:
        rows = parts.get(part) if isinstance(parts.get(part), list) else []
        clean = [
            {"id": str(r["id"]), "name": str(r["name"]), "text": str(r["text"])}
            for r in rows
            if isinstance(r, dict) and r.get("id") and r.get("name") and r.get("text") is not None
        ]
        built = BUILTIN.get(part)
        if built and not any(r["id"] == built["id"] for r in clean):
            clean.insert(0, dict(built))
        out[part] = clean
    return {"parts": out}


def _edit_presets(store: ViewStore, change) -> dict:
    """Read-modify-write story_prompts.json under one lock
    (file_safety.edit_json)."""
    def apply(raw: dict) -> dict:
        data = _clean_presets(raw)
        change(data)
        return data

    return edit_json(store.data_root / PROMPTS_FILE, apply)


def _preset(data: dict, part: str, pid: str) -> dict | None:
    return next((p for p in data["parts"][part] if p["id"] == pid), None)


@router.get("/api/story/prompts")
def story_prompts(store: ViewStore = Depends(get_store)) -> dict:
    data = _load_presets(store)
    data["builtin"] = [b["id"] for b in BUILTIN.values()]
    data["types"] = list(RELEASE_TYPES)
    return data


@router.post("/api/story/prompts")
def story_prompts_save(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{part, name, text, id?}`` — no id creates; an id renames or rewrites
    (built-ins too — the text is the operator's to change, the id stays)."""
    part = str(body.get("part") or "").strip()
    if part not in PARTS:
        raise HTTPException(status_code=422, detail=f"part must be one of {', '.join(PARTS)}")
    name = str(body.get("name") or "").strip()
    text = str(body.get("text") or "").rstrip()
    if not name:
        raise HTTPException(status_code=422, detail="a preset needs a name")
    if len(name) > MAX_NAME or len(text) > MAX_PART:
        raise HTTPException(status_code=422, detail=f"name is at most {MAX_NAME} characters and text at most {MAX_PART}")
    pid = str(body.get("id") or "").strip()

    def change(data: dict) -> None:
        nonlocal pid
        if pid:
            target = _preset(data, part, pid)
            if target is None:
                raise not_found("preset", pid)
            target["name"], target["text"] = name, text
        else:
            if len(data["parts"][part]) >= MAX_PRESETS:
                raise HTTPException(status_code=422, detail=f"at most {MAX_PRESETS} presets per part")
            pid = mint_id("pre_", part, name, str(time.time()))
            data["parts"][part].append({"id": pid, "name": name, "text": text})

    data = _edit_presets(store, change)
    return {"preset": _preset(data, part, pid), "part": part, "warnings": []}


@router.post("/api/story/prompts/{preset_id}/delete")
def story_prompts_delete(preset_id: str, store: ViewStore = Depends(get_store)) -> dict:
    if any(b["id"] == preset_id for b in BUILTIN.values()):
        raise HTTPException(status_code=409, detail="Built-in presets cannot be deleted. Edit them instead.")
    gone: list[str] = []

    def change(data: dict) -> None:
        for part in PARTS:
            before = len(data["parts"][part])
            data["parts"][part] = [p for p in data["parts"][part] if p["id"] != preset_id]
            if len(data["parts"][part]) != before:
                gone.append(part)
                return

    _edit_presets(store, change)
    if not gone:
        raise not_found("preset", preset_id)
    return {"deleted": preset_id, "part": gone[0]}


# ---------------------------------------------------------------------------
# The request — permission for one note, and the prompt that carries it
# ---------------------------------------------------------------------------


def _resolve_part(data: dict, part: str, body: dict) -> tuple[str, str]:
    """A part comes as a preset id, an inline text, or both (inline wins —
    the operator edited the preset for this one request)."""
    text = body.get(part)
    pid = str(body.get(f"{part}_id") or "").strip()
    if isinstance(text, str) and text.strip():
        return (pid or "inline"), text.rstrip()
    if isinstance(text, str) and part in body and not pid:
        # The operator emptied the box on purpose: no preset stands in.
        return "", ""
    if pid:
        found = _preset(data, part, pid)
        if found is None:
            raise not_found(f"{part} preset", pid)
        return pid, found["text"]
    built = BUILTIN.get(part)
    if built:
        found = _preset(data, part, built["id"]) or built
        return found["id"], found["text"]
    return "", ""


def build_prompt(task: dict, req: dict, brief: str, style: str, level: str = "high") -> str:
    tid = str(task.get("id"))
    focus = str(req.get("focus") or "").strip()
    call = json.dumps({
        "id": tid, "request_id": req["id"],
        "body": "<the piece, markdown>",
        "images": [{"title": "…", "data_base64": "…", "ext": "png"}],
    }, ensure_ascii=False)
    return "\n".join([
        f"{tid} · {task.get('title') or ''} — press release request {req['id']}",
        "",
        "FOCUS",
        focus or "(none this time — the task and its chat are the material)",
        "(the operator's own words; they are placed at the top of the piece as "
        "written — build on them, do not rewrite them)" if focus else "",
        "",
        "WHAT TO DO",
        brief.strip(),
        "",
        "STYLE EXAMPLES",
        style.strip() or "(none given)",
        "",
        "WHEN DONE",
        "Post the piece back. The request id is the permission to write on the "
        "Storyboard; without it the post is refused.",
        "MCP tool task_story:",
        call,
        "Put a screenshot into the text as ![title](image:1) — 1-based, in the "
        f"order sent; up to {MAX_IMAGES} images, {MAX_IMAGE_BYTES // (1024 * 1024)} MB "
        f"each, png/jpg/webp/gif, {story_images.size_ask(level)}. "
        f"The note lands as \"{req['type']}\" on {tid}. One post per request; it "
        "closes on success.",
    ])


def _prompt_path(store: ViewStore, task_id: str, rid: str):
    return store.data_root / STORY_DIR / task_id / f"{rid}.prompt.md"


def _focus_path(store: ViewStore, task_id: str, rid: str):
    return store.data_root / STORY_DIR / task_id / f"{rid}.focus.md"


def _focus_of(store: ViewStore, req: dict) -> str:
    """The operator's focus, whole. The CSV keeps a preview; the file keeps the text."""
    path = _focus_path(store, str(req.get("task_id") or ""), str(req.get("id") or ""))
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return str(req.get("focus") or "").strip()


@router.post("/api/tasks/{task_id}/story-requests", status_code=201)
def story_request_create(
    task_id: str, request: Request, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{type?, focus?, brief_id?, brief?, style_id?, style?, actor?}`` →
    the request row and the prompt to hand to the agent."""
    task = _task(store, task_id)
    if task is None:
        raise not_found("task", task_id)
    ntype = str(body.get("type") or "release").strip()
    if ntype not in RELEASE_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(RELEASE_TYPES)}")
    data = _load_presets(store)
    focus = str(body.get("focus") or "").strip()
    if len(focus) > MAX_PART:
        raise HTTPException(status_code=422, detail=f"focus is at most {MAX_PART} characters")
    brief_id, brief = _resolve_part(data, "brief", body)
    style_id, style = _resolve_part(data, "style", body)
    if not brief.strip():
        raise HTTPException(status_code=422, detail="The brief is empty. Type what the agent should write.")
    now = now_iso()
    actor = str(body.get("actor") or _ACTOR)
    rid = mint_id("sr_", task_id, ntype, focus, now, f"{time.time():.6f}")
    req = {
        "id": rid, "task_id": task_id, "project": str(task.get("project") or ""),
        "type": ntype, "created_at": now, "actor": actor, "status": "open",
        "focus": focus[:MAX_FOCUS_CSV], "brief_id": brief_id, "style_id": style_id,
        "note_id": "", "agent_id": "", "fulfilled_at": "",
    }
    level = str(app_settings.load(store.data_root).get("story.image_quality") or "high")
    prompt = build_prompt(task, {**req, "focus": focus}, brief, style, level)
    path = _prompt_path(store, task_id, rid)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, prompt)
    if focus:
        # Whole, beside the prompt: the note reads it back from here.
        atomic_write(_focus_path(store, task_id, rid), focus + "\n")
    append_row(store.data_root / "story_requests.csv", STORY_REQUEST_COLUMNS, req)
    _append_events(store, task_id, actor, [("story_request", "", ntype)])
    store.rebuild()
    return create_answer({"request": req, "prompt": prompt})


@router.get("/api/tasks/{task_id}/story-requests")
def story_requests_list(task_id: str, store: ViewStore = Depends(get_store)) -> dict:
    rows = store.query(
        "SELECT * FROM story_requests_mutual WHERE task_id = ? ORDER BY created_at DESC", (task_id,)
    )
    return {"total": len(rows), "requests": rows}


@router.get("/api/story/requests/{request_id}/prompt", response_class=PlainTextResponse)
def story_request_prompt(request_id: str, store: ViewStore = Depends(get_store)) -> str:
    row = store.query_one("SELECT * FROM story_requests_mutual WHERE id = ?", (request_id,))
    if row is None:
        raise not_found("request", request_id)
    path = _prompt_path(store, str(row["task_id"]), request_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The prompt file was not found.")
    return path.read_text(encoding="utf-8")


@router.post("/api/story/requests/{request_id}/cancel")
def story_request_cancel(request_id: str, store: ViewStore = Depends(get_store)) -> dict:
    row = _set_request(store, request_id, lambda r: r.update(status="cancelled") if r.get("status") == "open" else None)
    if str(row.get("status") or "") == "fulfilled":
        raise HTTPException(status_code=409, detail="This request is already done. The note is on the task.")
    return {"request": row}


def _set_request(store: ViewStore, request_id: str, fn) -> dict:
    def change(_rows: list[dict[str, str]], r: dict[str, str]) -> bool:
        fn(r)
        return True

    return rewrite_one(store, "story_requests.csv", STORY_REQUEST_COLUMNS, request_id, change, "request")


# ---------------------------------------------------------------------------
# The story — the agent's post, under the request
# ---------------------------------------------------------------------------

_IMAGE_REF = re.compile(r"\(image:(\d+)\)")


@router.post("/api/tasks/{task_id}/story", status_code=201)
def story_post(task_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{request_id, agent_id, body, images?: [{title, data_base64, ext}]}``
    — the piece, under an open request. Images are stored at the operator's
    quality and ``(image:N)`` in the text becomes their URL."""
    rid = str(body.get("request_id") or "").strip()
    if not rid:
        raise HTTPException(
            status_code=422,
            detail="a story needs a request_id — the operator asks for a press "
                   "release from the task; the request id comes in that prompt",
        )
    req = store.query_one("SELECT * FROM story_requests_mutual WHERE id = ?", (rid,))
    if req is None:
        raise not_found("request", rid)
    if str(req.get("task_id")) != task_id:
        raise HTTPException(status_code=422, detail=f"request {rid} belongs to task {req.get('task_id')}")
    if str(req.get("status")) != "open":
        raise HTTPException(status_code=409, detail=f"request {rid} is {req.get('status')} — ask the operator for a new one")
    agent_id = str(body.get("agent_id") or "").strip()
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    text = str(body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="body is required")
    if len(text) > MAX_BODY:
        raise HTTPException(status_code=422, detail=f"body is at most {MAX_BODY} characters")
    # The kind of note was the operator's choice when the request was made;
    # the prompt promised it, so the agent does not pick another.
    ntype = str(req.get("type") or "release")
    if ntype not in TASK_NOTE_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(TASK_NOTE_TYPES)}")
    task = _task(store, task_id)
    if task is None:
        raise not_found("task", task_id)
    images = body.get("images") or []
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise HTTPException(status_code=422, detail=f"images: a list of at most {MAX_IMAGES}")

    # Decode and measure every image before anything is written.
    prepared: list[tuple[str, bytes, str, int, int]] = []
    for i, item in enumerate(images, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"image {i}: not an object")
        ext, raw = story_images.checked_image(item, f"image {i}")
        w, h = story_images.dimensions(raw)
        prepared.append((str(item.get("title") or f"image {i}")[:limits.MAX_TITLE], raw, ext, w, h))

    now = now_iso()
    note_id = mint_id("nt_", task_id, ntype, text, now, f"{time.time():.6f}")

    # One post per request: the request is taken under the ledger's lock
    # before anything is written. The look above read the view, and two
    # posts at once (a retry after a slow upload) both passed it; a cancel
    # landing in between was turned back into fulfilled.
    def claim(r: dict) -> None:
        if str(r.get("status") or "") != "open":
            raise HTTPException(status_code=409, detail=f"request {rid} is {r.get('status')} — ask the operator for a new one")
        r.update(status="fulfilled", note_id=note_id, agent_id=agent_id, fulfilled_at=now)

    _set_request(store, rid, claim)
    try:
        return _write_story(store, task, req, rid, note_id, ntype, text, agent_id, now, prepared)
    except Exception:
        # Nothing landed: the request is open again for the retry.
        _set_request(store, rid, lambda r: r.update(status="open", note_id="", agent_id="", fulfilled_at=""))
        raise


def _write_story(store: ViewStore, task: dict, req: dict, rid: str, note_id: str, ntype: str,
                 text: str, agent_id: str, now: str, prepared: list) -> dict:
    """The images and the note of a claimed request."""
    task_id = str(task.get("id"))
    saved: list[dict] = []
    for i, (title, out, ext, w, h) in enumerate(prepared, start=1):
        iid = mint_id("si_", note_id, str(i), title, now)
        rel = f"{STORY_DIR}/{task_id}/{iid}.{ext}"
        path = store.data_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(out)
        row = {
            "id": iid, "note_id": note_id, "task_id": task_id,
            "project": str(task.get("project") or ""), "title": title, "path": rel,
            "width": str(w), "height": str(h), "bytes": str(len(out)), "created_at": now,
        }
        append_row(store.data_root / "story_images.csv", STORY_IMAGE_COLUMNS, row)
        saved.append({**row, "url": f"/api/story/images/{iid}/file"})

    def swap(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(saved):
            return f"({saved[n - 1]['url']})"
        return m.group(0)

    text = _IMAGE_REF.sub(swap, text)
    # The operator's note is theirs: it heads the piece as written, whole.
    focus = _focus_of(store, req)
    if focus:
        text = f"**From the operator**\n\n{focus}\n\n---\n\n{text}"
    note = {
        "id": note_id, "task_id": task_id, "project": str(task.get("project") or ""),
        "type": ntype, "template": rid, "body": text,
        "created_at": now, "updated_at": now, "actor": agent_id,
    }
    append_row(store.data_root / "task_notes.csv", TASK_NOTE_COLUMNS, note)
    _append_events(store, task_id, agent_id, [("story", "", f"{ntype} · {len(saved)} image(s)")])
    store.rebuild()
    return create_answer({"note": note, "images": saved, "request_id": rid})


@router.get("/api/story/images")
def story_images_list(
    note_id: str = "", task_id: str = "", project: str = "", store: ViewStore = Depends(get_store),
) -> dict:
    where, args = [], []
    if note_id:
        where.append("note_id = ?"); args.append(note_id)
    if task_id:
        where.append("task_id = ?"); args.append(task_id)
    if project:
        where.append("project = ?"); args.append(project)
    if not where:
        raise HTTPException(status_code=422, detail="filter by note_id, task_id or project")
    rows = store.query(
        f"SELECT * FROM story_images_mutual WHERE {' AND '.join(where)} ORDER BY created_at ASC, id ASC",
        tuple(args),
    )
    for r in rows:
        r["url"] = f"/api/story/images/{r['id']}/file"
    return {"total": len(rows), "images": rows}


@router.get("/api/story/images/{image_id}/file")
def story_image_file(image_id: str, store: ViewStore = Depends(get_store)):
    row = store.query_one("SELECT * FROM story_images_mutual WHERE id = ?", (image_id,))
    if row is None:
        raise not_found("image", image_id)
    root = (store.data_root / STORY_DIR).resolve()
    path = resolve_under(root, str(row.get("path") or "").removeprefix(f"{STORY_DIR}/"))
    if path is None or not path.exists():
        raise not_found("image file", image_id)
    return FileResponse(path)


def drop_note_images(store: ViewStore, note_id: str) -> int:
    """Called when a note is deleted: its images go with it."""
    csv_path = store.data_root / "story_images.csv"
    if not csv_path.exists():
        return 0
    gone: list[str] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        keep = [r for r in rows if r.get("note_id") != note_id]
        gone.extend(r.get("path") or "" for r in rows if r.get("note_id") == note_id)
        rows[:] = keep
        return bool(gone)

    rewrite_rows(csv_path, STORY_IMAGE_COLUMNS, mutate)
    root = (store.data_root / STORY_DIR).resolve()
    for rel in gone:
        p = resolve_under(root, rel.removeprefix(f"{STORY_DIR}/"))
        if p is not None and p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return len(gone)
