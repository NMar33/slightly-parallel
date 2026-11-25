"""Notes: the long texts agents write for the operator — context to come
back to, a text to paste somewhere, a review with pictures, a plan for
helpers, a report, the manual steps only the operator can do (tk_3e544086).

A note is a row of the ``note`` lens (``notes.csv``, its header extended)
plus ledgers at the data root:

- ``note_versions.csv`` — every write is a version; its text at
  ``note_details/<nt>/v001.md``; the row's ``md_ref`` document carries the
  current text (``## L4``) so the lens detail and search read it;
- ``note_images.csv`` — pictures under ``note_images/<nt>/<ni>.<ext>``,
  referenced from the markdown by id: ``![caption](ni_…)``;
- ``note_marks.csv`` — the operator's ticks, answers and copies, one row
  per act, the latest per (note, item, kind) wins. A mark names its item by
  the item's text hash (``nt_…:k:<fnv1a>``), so a new version that leaves
  an item as it was keeps its tick.
- ``note_comments.csv`` — operator comments on a note, check or choice,
  with the original label, section and version so later edits preserve context.

The markup inside the markdown (the frontend draws it, notes/render):

  ```copy Title … ```     a block with a copy button
  - [ ] / - [x]           a checklist the operator ticks
  ```gallery ![c](ni_…)   pictures with captions
  :::fold Title … :::     a folded section
  ```choice Question      numbered options the operator picks one of
  ```mermaid              a diagram
  tk_ ep_ dc_ pu_ nt_ ids live chips

Who writes what: an agent writes notes, versions and pictures through the
MCP tools only; the operator ticks, answers, copies, comments and archives on the
Notes page. Any chat of the note's project may write its next version;
each version keeps the chat that wrote it.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from pathlib import Path
from typing import Any

from . import chatstore, limits
from .actors import identity_of, is_agent
from .csvio import append_row, as_int, read_rows, rewrite_rows
from .date_utils import now_iso, today_yymm_dd
from .db import ViewStore
from .docs_md import build_detail, read_detail, resolve_under
from .entities import ENTITIES, NOTE_COMMENT_COLUMNS, NOTE_IMAGE_COLUMNS, NOTE_KINDS, NOTE_MARK_COLUMNS, NOTE_VERSION_COLUMNS
from .file_safety import acquire_flock, atomic_write

VERSIONS_FILE = "note_versions.csv"
IMAGES_FILE = "note_images.csv"
MARKS_FILE = "note_marks.csv"
COMMENTS_FILE = "note_comments.csv"
IMAGES_DIR = "note_images"
# Note revisions and comments share a lock to keep each comment with the
# version it addresses. append_row separately takes the ledger's own lock.
WRITE_LOCK = "note_write.lock"

TITLE_MAX = 160
TEXT_MAX = 400_000
CAPTION_MAX = 200
IMAGES_MAX = 60
IMAGES_PER_WRITE = 20
MARK_KINDS = ("tick", "answer", "copy")
COMMENT_MAX = 2000
ID_RE = re.compile(r"\b(?:tk|ep|dc|pu|nt)_[0-9a-f]{8}\b")
NOTE_ID_RE = re.compile(r"^nt_[0-9a-z_]{3,40}$")
IMAGE_ID_RE = re.compile(r"^ni_[0-9a-f]{10}$")


class NoteRefused(ValueError):
    """A write the server will not make; answered as 422 with the sentence."""


def _rows(store: Any, name: str) -> list[dict[str, str]]:
    return read_rows(Path(getattr(store, "data_root", store)) / name)


def _text(body: dict, key: str, most: int, *, required: bool = False, what: str = "") -> str:
    v = body.get(key)
    if v is None or v == "":
        if required:
            raise NoteRefused(f"{key} is required{': ' + what if what else ''}")
        return ""
    if not isinstance(v, str):
        raise NoteRefused(f"{key} is text, not {'a list' if isinstance(v, list) else type(v).__name__}")
    v = v.strip()
    if len(v) > most:
        raise NoteRefused(f"{key} is at most {most:,} characters; this one is {len(v):,}")
    return v


# ---------------------------------------------------------------------------
# The markup: the same parse as the page's (frontend notes/render/model.ts)
# ---------------------------------------------------------------------------


def hash_of(s: str) -> str:
    """FNV-1a over UTF-16 code units, as the page computes it (JS charCodeAt)."""
    h = 2166136261
    raw = s.encode("utf-16-le", "surrogatepass")
    for i in range(0, len(raw), 2):
        h ^= raw[i] | (raw[i + 1] << 8)
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


_FENCE = re.compile(r"^```(copy|gallery|choice|mermaid)\b ?(.*)$")
_FOLD = re.compile(r"^:::fold\s+(.*)$")
_CHECK = re.compile(r"^\s*- \[( |x|X)\] (.*)$")
_OPTION = re.compile(r"^\s*\d+\.\s+(.*)$")
_SHOT = re.compile(r"^!\[(.*)\]\((.*)\)\s*$")


def _blocks(lines: list[str], note_id: str, out: list[dict[str, Any]], section: str) -> None:
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            inner: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                inner.append(lines[i])
                i += 1
            kind, head = fence.group(1), (fence.group(2) or "").strip()
            if kind == "copy":
                out.append({"type": "copy", "id": f"{note_id}:c:{hash_of(head + chr(10).join(inner))}",
                            "title": head, "section": section})
            elif kind == "choice":
                options = [m.group(1) for m in (_OPTION.match(x) for x in inner) if m]
                out.append({"type": "choice", "id": f"{note_id}:q:{hash_of(head + '|'.join(options))}",
                            "question": head, "options": options, "section": section})
            elif kind == "gallery":
                shots = [{"caption": m.group(1), "src": m.group(2)} for m in (_SHOT.match(x) for x in inner) if m]
                out.append({"type": "gallery", "shots": shots, "section": section})
            i += 1
            continue
        fold = _FOLD.match(line)
        if fold:
            inner = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                inner.append(lines[i])
                i += 1
            _blocks(inner, note_id, out, section)
            i += 1
            continue
        m = _CHECK.match(line)
        if m:
            out.append({"type": "check", "id": f"{note_id}:k:{hash_of(m.group(2))}", "text": m.group(2),
                        "done": m.group(1) != " ", "section": section})
        i += 1


def parse(note_id: str, text: str) -> dict[str, Any]:
    """Title, sections, the items the operator acts on, the ids named."""
    lines = text.replace("\r\n", "\n").split("\n")
    title = ""
    if lines and lines[0].startswith("# "):
        title = lines.pop(0)[2:].strip()
    items: list[dict[str, Any]] = []
    sections: list[str] = []
    cur_title, cur = "", []
    for line in lines + ["## "]:
        if line.startswith("## "):
            _blocks(cur, note_id, items, cur_title)
            if cur_title:
                sections.append(cur_title)
            cur_title, cur = line[3:].strip(), []
            continue
        cur.append(line)
    words = len(text.split())
    lead = ""
    for para in re.split(r"\n\s*\n", "\n".join(lines)):
        p = para.strip()
        if p and not p.startswith(("#", "```", ":::", "- [", "![")):
            lead = re.sub(r"[`*]", "", " ".join(p.split()))[:400]
            break
    refs = list(dict.fromkeys(ID_RE.findall(text)))
    return {"title": title, "sections": sections, "items": items, "words": words, "lead": lead, "refs": refs}


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _mint(prefix: str, n: int, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:n]


def all_rows(store: ViewStore) -> list[dict[str, str]]:
    return read_rows(store.data_root / ENTITIES["note"].csv)


def row_of(store: ViewStore, note_id: str) -> dict[str, str] | None:
    if not str(note_id or "").startswith("nt_"):
        return None
    return next((r for r in all_rows(store) if r.get("id") == note_id), None)


def kind_of(row: dict[str, Any]) -> str:
    k = str(row.get("kind") or "").strip()
    return k if k in NOTE_KINDS else "context"


def versions_of(store: Any, note_id: str) -> list[dict[str, str]]:
    out = [v for v in _rows(store, VERSIONS_FILE) if v.get("note_id") == note_id]
    out.sort(key=lambda v: int(v.get("n") or 0))
    return out


def text_of(store: ViewStore, row: dict[str, Any], n: int | None = None) -> str:
    """A version's text (the current one by default). A note written before
    versions (the old lens) reads from its detail document."""
    vs = versions_of(store, str(row.get("id") or ""))
    if n is not None:
        vs = [v for v in vs if int(v.get("n") or 0) == n]
        if not vs:
            raise LookupError(f"{row.get('id')} v{n}")
    if vs:
        path = resolve_under(store.data_root, str(vs[-1].get("file") or ""))
        if path is not None and path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return ""
    l2, l3, l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
    body = l4 or "\n".join(x for x in (l2, "\n".join(f"- {b}" for b in l3)) if x)
    title = str(row.get("title") or "").strip()
    return (f"# {title}\n\n" if title and not body.startswith("# ") else "") + body


def images_of(store: Any, note_id: str) -> list[dict[str, str]]:
    return [r for r in _rows(store, IMAGES_FILE)
            if r.get("note_id") == note_id and not str(r.get("removed_at") or "").strip()]


def image_file(store: ViewStore, image_id: str) -> Path | None:
    if not IMAGE_ID_RE.match(str(image_id or "")):
        return None
    r = next((x for x in _rows(store, IMAGES_FILE) if x.get("id") == image_id), None)
    if r is None:
        return None
    path = resolve_under(store.data_root / IMAGES_DIR, str(r.get("file") or "").removeprefix(f"{IMAGES_DIR}/"))
    return path if path is not None and path.is_file() else None


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------


def marks_of(store: Any, note_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """{ticks: {item: bool}, answers: {item: int}, copied: {item: at}} —
    the latest act per item wins; an untick or a taken-back answer clears."""
    ticks: dict[str, bool] = {}
    answers: dict[str, int] = {}
    copied: dict[str, str] = {}
    for r in _rows(store, MARKS_FILE):
        if note_ids is not None and r.get("note_id") not in note_ids:
            continue
        item, kind, value = str(r.get("item") or ""), r.get("kind"), str(r.get("value") or "")
        if kind == "tick":
            ticks[item] = value == "1"
        elif kind == "answer":
            if value.strip().lstrip("-").isdigit():
                answers[item] = int(value)
            else:
                answers.pop(item, None)
        elif kind == "copy":
            copied[item] = str(r.get("at") or "")
    return {"ticks": ticks, "answers": answers, "copied": copied}


def open_of(kind: str, items: list[dict[str, Any]], marks: dict[str, dict[str, Any]]) -> dict[str, int]:
    """What still waits on the operator (the page's openOf)."""
    o = {"to_tick": 0, "ticked": 0, "to_answer": 0, "answered": 0, "to_copy": 0, "copies": 0}
    for it in items:
        if it["type"] == "check":
            on = marks["ticks"].get(it["id"], it["done"])
            o["ticked" if on else "to_tick"] += 1
        elif it["type"] == "choice":
            o["answered" if it["id"] in marks["answers"] else "to_answer"] += 1
        elif it["type"] == "copy":
            o["copies"] += 1
            if kind == "paste" and it["id"] not in marks["copied"]:
                o["to_copy"] += 1
    return o


def mark(store: ViewStore, note_id: str, body: Any) -> dict[str, Any]:
    """The operator ticks an item, answers a choice (value = option index,
    "" takes it back) or copies a block. The item must be one of the note's
    current text."""
    if not isinstance(body, dict):
        raise NoteRefused("send the body as a JSON object")
    row = _need(store, note_id)
    kind = _text(body, "kind", 10, required=True)
    if kind not in MARK_KINDS:
        raise NoteRefused(f"kind is one of {', '.join(MARK_KINDS)}")
    item = _text(body, "item", 80, required=True)
    want = {"tick": "check", "answer": "choice", "copy": "copy"}[kind]
    # A gallery has no id: it is shown, not marked.
    found = next((it for it in parse(note_id, text_of(store, row))["items"] if it.get("id") == item), None)
    if found is None or found["type"] != want:
        raise NoteRefused(f"{item} is not a {want} of {note_id} as it reads now")
    raw = body.get("value")
    if kind == "tick":
        value = "1" if raw in (True, 1, "1", "true") else "0"
    elif kind == "answer":
        # Option 0 is an answer (0 == False in Python: compared by identity).
        if raw is None or raw is False or raw == "":
            value = ""
        elif isinstance(raw, bool) or not str(raw).isdigit() or int(str(raw)) >= len(found["options"]):
            raise NoteRefused(f"value is the option's index, 0 to {len(found['options']) - 1}, or empty to take it back")
        else:
            value = str(int(str(raw)))
    else:
        value = "1"
    at = now_iso()
    rec = {"id": _mint("nm_", 12, note_id, item, kind, value, at, str(len(_rows(store, MARKS_FILE)))),
           "note_id": note_id, "item": item, "kind": kind, "value": value, "at": at, "actor": "operator"}
    append_row(store.data_root / MARKS_FILE, NOTE_MARK_COLUMNS, rec)
    return {"mark": rec, "marks": marks_of(store, {note_id})}


# ---------------------------------------------------------------------------
# Operator comments
# ---------------------------------------------------------------------------


def _comment_view(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "item": row.get("item") or None, "version": as_int(row.get("version"), 1)}


def comments_of(store: ViewStore, note_ids: set[str]) -> list[dict[str, Any]]:
    if not note_ids:
        return []
    return [_comment_view(row) for row in _rows(store, COMMENTS_FILE) if row.get("note_id") in note_ids]


def feed_stamp(store: ViewStore) -> str:
    """Invalidate the feed after comments or revisions without waiting for the watcher."""
    stamps = []
    for name in (COMMENTS_FILE, VERSIONS_FILE):
        try:
            stamp = (store.data_root / name).stat()
        except FileNotFoundError:
            stamps.append("0")
        else:
            stamps.append(f"{stamp.st_mtime_ns}:{stamp.st_size}")
    return ":".join(stamps)


def comment(store: ViewStore, note_id: str, body: Any) -> dict[str, Any]:
    """Add operator feedback to a note or a check/choice in its current version."""
    if not isinstance(body, dict):
        raise NoteRefused("send the body as a JSON object")
    text = _text(body, "text", COMMENT_MAX, required=True)
    if not text:
        raise NoteRefused("a comment needs text")
    try:
        units = len(text.encode("utf-16-le")) // 2
    except UnicodeEncodeError:
        raise NoteRefused("a comment must contain valid Unicode text") from None
    if units > COMMENT_MAX:
        raise NoteRefused(f"text is at most {COMMENT_MAX:,} characters")
    item = _text(body, "item", 80)
    requested_section = _text(body, "section", TEXT_MAX) if body.get("section") is not None else None
    if not item and requested_section is not None:
        raise NoteRefused("section requires a checklist item or choice")
    request = _text(body, "request_id", 80)
    if request and re.fullmatch(r"[A-Za-z0-9_-]+", request) is None:
        raise NoteRefused("request_id uses letters, digits, underscores or hyphens")
    cid = _mint("nc_", 24, note_id, request) if request else "nc_" + secrets.token_hex(12)

    # Note revisions and comment retries share one lock so a target and its
    # recorded version agree, and a retried request appends at most one row.
    with acquire_flock(store.data_root / WRITE_LOCK, mode="a"):
        row = _need(store, note_id)
        if request:
            existing = next((r for r in _rows(store, COMMENTS_FILE) if r.get("id") == cid), None)
            if existing is not None:
                if (existing.get("item") != item or existing.get("text") != text
                        or (requested_section is not None and existing.get("section") != requested_section)):
                    raise NoteRefused("request_id already belongs to a different comment")
                return {"comment": _comment_view(existing)}
        if str(row.get("archived_at") or "").strip():
            raise NoteRefused(f"{note_id} is archived")
        section = label = ""
        if item:
            matches = [it for it in parse(note_id, text_of(store, row))["items"]
                       if it.get("id") == item and it["type"] in ("check", "choice")
                       and (requested_section is None or it["section"] == requested_section)]
            if not matches:
                raise NoteRefused(f"{item} is not a checklist item or choice of {note_id} as it reads now")
            if len(matches) > 1:
                raise NoteRefused("this point appears more than once; comment on the whole note instead")
            found = matches[0]
            section = found["section"]
            label = found["text"] if found["type"] == "check" else found["question"]
        rec = {"id": cid, "note_id": note_id, "item": item, "text": text, "at": now_iso(),
               "version": len(versions_of(store, note_id)) or 1, "section": section, "label": label}
        append_row(store.data_root / COMMENTS_FILE, NOTE_COMMENT_COLUMNS, rec)
    return {"comment": _comment_view(rec)}


# ---------------------------------------------------------------------------
# Links: tasks, entry points, decisions, publish cards
# ---------------------------------------------------------------------------


def entities_of(store: ViewStore, ids: set[str]) -> dict[str, dict[str, str]]:
    """The live title and status of every id a note names: the chips."""
    out: dict[str, dict[str, str]] = {}
    want = {p: {i for i in ids if i.startswith(p)} for p in ("tk_", "ep_", "dc_", "pu_", "nt_")}
    if want["tk_"]:
        for r in read_rows(store.data_root / ENTITIES["task"].csv):
            if r.get("id") in want["tk_"]:
                out[r["id"]] = {"title": str(r.get("title") or ""), "project": str(r.get("project") or ""),
                                "status": "archived" if str(r.get("archived_at") or "").strip() else str(r.get("status") or "")}
    if want["ep_"]:
        from . import entrypointlib as E
        for r in read_rows(store.data_root / ENTITIES["entrypoint"].csv):
            if r.get("id") in want["ep_"]:
                out[r["id"]] = {"title": E.name_of(r) or str(r.get("l1") or ""), "project": str(r.get("project") or ""),
                                "status": E.state_of(r)}
    if want["dc_"]:
        for r in read_rows(store.data_root / ENTITIES["decision"].csv):
            if r.get("id") in want["dc_"]:
                out[r["id"]] = {"title": str(r.get("decision_text") or "")[:200], "project": str(r.get("project") or ""),
                                "status": str(r.get("weight") or "")}
    if want["pu_"]:
        for r in read_rows(store.data_root / ENTITIES["publish"].csv):
            if r.get("id") in want["pu_"]:
                out[r["id"]] = {"title": str(r.get("l1") or "")[:200], "project": str(r.get("project") or ""),
                                "status": "archived" if str(r.get("archived_at") or "").strip() else "card"}
    if want["nt_"]:
        for r in all_rows(store):
            if r.get("id") in want["nt_"]:
                out[r["id"]] = {"title": str(r.get("title") or ""), "project": str(r.get("project") or ""),
                                "status": kind_of(r)}
    return out


def _task_row(store: ViewStore, task_id: str) -> dict[str, str] | None:
    return next((r for r in read_rows(store.data_root / ENTITIES["task"].csv) if r.get("id") == task_id), None)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _need(store: ViewStore, note_id: str) -> dict[str, str]:
    row = row_of(store, note_id)
    if row is None:
        raise LookupError(note_id)
    return row


def view(store: ViewStore, row: dict[str, str], *, marks: dict[str, Any], replaced_by: dict[str, str],
         text: str | None = None) -> dict[str, Any]:
    nid = str(row["id"])
    body = text_of(store, row) if text is None else text
    p = parse(nid, body)
    imgs = images_of(store, nid)
    vs = versions_of(store, nid)
    replaces = [x for x in str(row.get("replaces") or "").split(",") if x.strip()]
    created = vs[0]["at"] if vs else _stamp(row)
    return {
        "id": nid, "project": str(row.get("project") or ""), "kind": kind_of(row),
        "title": p["title"] or str(row.get("title") or "") or nid,
        "task": str(row.get("task_id") or ""), "entrypoint": str(row.get("entrypoint_id") or ""),
        "chat": str(row.get("updated_by") or row.get("agent_id") or ""), "agent_id": str(row.get("agent_id") or ""),
        "created": created, "updated": str(row.get("updated_at") or "") or created,
        "versions": max(1, len(vs)), "archived_at": str(row.get("archived_at") or ""),
        "replaces": replaces, "replaced_by": replaced_by.get(nid, ""),
        "words": p["words"], "lead": p["lead"], "refs": p["refs"],
        "open": open_of(kind_of(row), p["items"], marks),
        "images": [{"id": i["id"], "caption": i.get("caption") or "", "width": int(i.get("width") or 0),
                    "height": int(i.get("height") or 0), "src": f"/api/notes/images/{i['id']}/file"} for i in imgs],
        "body": body,
    }


def _stamp(row: dict[str, Any]) -> str:
    d, t = str(row.get("created_date") or ""), str(row.get("created_time") or "")
    if re.match(r"^\d{4}-\d{2}$", d):
        return f"20{d[:2]}-{d[2:4]}-{d[5:7]}T{t or '00:00'}:00"
    return ""


def _replaced_by(rows: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: str(r.get("updated_at") or "")):
        if str(r.get("archived_at") or "").strip():
            continue
        for old in str(r.get("replaces") or "").split(","):
            if old.strip():
                out[old.strip()] = str(r["id"])
    return out


def feed(store: ViewStore, *, project: str = "", task: str = "", archived: bool = False) -> dict[str, Any]:
    """Every live note (of a project, or naming a task) with its text, its
    pictures and what waits on the operator; the marks; the chips' titles."""
    rows = all_rows(store)
    by = _replaced_by(rows)
    picked = []
    for r in rows:
        if project and r.get("project") != project:
            continue
        if bool(str(r.get("archived_at") or "").strip()) != archived:
            continue
        picked.append(r)
    ids = {str(r["id"]) for r in picked}
    marks = marks_of(store, ids)
    notes = [view(store, r, marks=marks, replaced_by=by) for r in picked]
    if task:
        notes = [n for n in notes if n["task"] == task or task in n["refs"]]
    notes.sort(key=lambda n: n["updated"], reverse=True)
    named: set[str] = set()
    for n in notes:
        named.update(n["refs"])
        named.update(x for x in (n["task"], n["entrypoint"]) if x)
    keep = {n["id"] for n in notes}
    return {"notes": notes,
            "marks": {k: {i: v for i, v in m.items() if i.split(":", 1)[0] in keep} for k, m in marks.items()},
            "comments": comments_of(store, keep),
            "entities": entities_of(store, named),
            "projects": sorted({n["project"] for n in notes})}


def one(store: ViewStore, note_id: str, n: int | None = None) -> dict[str, Any]:
    row = _need(store, note_id)
    marks = marks_of(store, {note_id})
    text = text_of(store, row, n) if n is not None else None
    out = view(store, row, marks=marks, replaced_by=_replaced_by(all_rows(store)), text=text)
    out["version"] = n or out["versions"]
    out["history"] = [{"n": int(v.get("n") or 0), "at": v.get("at") or "", "agent_id": v.get("agent_id") or "",
                       "title": v.get("title") or "", "words": int(v.get("words") or 0)} for v in versions_of(store, note_id)]
    out["marks"] = marks
    out["comments"] = comments_of(store, {note_id})
    return out


def for_agent(store: ViewStore, note_id: str) -> dict[str, Any]:
    """One note as an agent reads it back: the text and what the operator did —
    each checklist item ticked or not, each choice's answer and comments."""
    full = one(store, note_id)
    items = parse(note_id, full["body"])["items"]
    m = full["marks"]
    did = []
    for it in items:
        if it["type"] == "check":
            did.append({"item": it["text"], "section": it["section"], "ticked": bool(m["ticks"].get(it["id"], it["done"]))})
        elif it["type"] == "choice":
            a = m["answers"].get(it["id"])
            did.append({"question": it["question"], "section": it["section"], "options": it["options"],
                        "answer": None if a is None else {"number": a + 1, "option": it["options"][a] if a < len(it["options"]) else ""}})
        elif it["type"] == "copy":
            did.append({"copy": it["title"], "copied_at": m["copied"].get(it["id"], "")})
    keep = ("id", "project", "kind", "title", "task", "entrypoint", "versions", "updated", "chat", "open",
            "replaced_by", "replaces", "archived_at", "body", "comments")
    return {**{k: full[k] for k in keep}, "images": [{"id": i["id"], "caption": i["caption"]} for i in full["images"]],
            "operator": did}


def listing(store: ViewStore, project: str = "", task: str = "") -> dict[str, Any]:
    got = feed(store, project=project, task=task)
    return {"notes": [{k: n[k] for k in ("id", "project", "kind", "title", "task", "entrypoint", "versions", "updated",
                                         "chat", "open", "replaced_by", "words")} for n in got["notes"]]}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _image_kind(raw: bytes) -> str:
    from .entrypointlib import _image_kind as kind
    return kind(raw)


def _decode_image(item: Any, i: int) -> tuple[bytes, str, str, str]:
    """(bytes, ext, caption, name) of one picture of a write; refused when it is not an image."""
    if not isinstance(item, dict):
        raise NoteRefused(f"image {i}: an object with data_base64, caption and the name the text uses")
    data = item.get("data_base64")
    if not isinstance(data, str) or not data.strip():
        raise NoteRefused(f"image {i}: data_base64 is the image, base64 text")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        raise NoteRefused(f"image {i}: data_base64 is not valid base64") from None
    if not raw:
        raise NoteRefused(f"image {i}: the image is empty")
    if len(raw) > limits.MAX_IMAGE_BYTES:
        raise NoteRefused(f"image {i}: over {limits.MAX_IMAGE_BYTES // (1024 * 1024)}MB")
    ext = _image_kind(raw)
    if not ext:
        raise NoteRefused(f"image {i}: not a PNG, JPEG, GIF or WebP image")
    caption = item.get("caption")
    if caption is not None and not isinstance(caption, str):
        raise NoteRefused(f"image {i}: caption is text")
    name = item.get("name")
    if name is not None and not isinstance(name, str):
        raise NoteRefused(f"image {i}: name is text")
    return raw, ext, " ".join(str(caption or "").split())[:CAPTION_MAX], str(name or "").strip()


def _store_image(store: ViewStore, note_id: str, raw: bytes, ext: str, caption: str, agent: str) -> dict[str, str]:
    from .story_images import dimensions
    digest = hashlib.sha256(raw).hexdigest()
    iid = _mint("ni_", 10, note_id, digest)
    known = next((r for r in _rows(store, IMAGES_FILE) if r.get("id") == iid), None)
    if known is not None:
        return known
    rel = f"{IMAGES_DIR}/{note_id}/{iid}.{ext}"
    path = store.data_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, raw)
    w, h = dimensions(raw)
    rec = {"id": iid, "note_id": note_id, "file": rel, "caption": caption, "at": now_iso(), "agent_id": agent,
           "width": str(w or ""), "height": str(h or ""), "removed_at": ""}
    append_row(store.data_root / IMAGES_FILE, NOTE_IMAGE_COLUMNS, rec)
    return rec


def _with_ids(text: str, name: str, iid: str) -> str:
    """The text's reference to a picture by its file name or path becomes its id."""
    if not name:
        return text
    forms = {name, Path(name).name}
    for f in sorted(forms, key=len, reverse=True):
        text = text.replace(f"]({f})", f"]({iid})")
    return text


def add_image(store: ViewStore, note_id: str, body: Any) -> dict[str, Any]:
    """One picture for a note an agent wrote or will write the next version of."""
    if not isinstance(body, dict):
        raise NoteRefused("send the body as a JSON object")
    who = identity_of(body)
    if not is_agent(who):
        raise NoteRefused("agent_id is required: the chat that adds the picture")
    row = _need(store, note_id)
    _same_project(store, row, who, body)
    if len(images_of(store, note_id)) >= IMAGES_MAX:
        raise NoteRefused(f"{note_id} holds {IMAGES_MAX} pictures already")
    raw, ext, caption, _name = _decode_image(body, 1)
    rec = _store_image(store, note_id, raw, ext, caption, who)
    return {"image": {"id": rec["id"], "caption": rec.get("caption") or ""},
            "markdown": f"![{rec.get('caption') or ''}]({rec['id']})",
            "next": f"put the markdown line in the next version of {note_id} (note_write with id), "
                    "or the id on a line of a ```gallery block"}


def _agent_project(store: ViewStore, agent: str) -> str:
    for a in store.agents():
        if str(a.get("agent_id") or "") == agent:
            return str(a.get("project") or "")
    return ""


def _same_project(store: ViewStore, row: dict[str, Any], who: str, body: dict) -> None:
    mine = _agent_project(store, who) or str(body.get("project") or "")
    if mine and row.get("project") and mine != row.get("project"):
        raise NoteRefused(f"{row['id']} is a note of {row['project']}; this chat works in {mine}. Nothing was written")


def write(store: ViewStore, body: Any) -> dict[str, Any]:
    """A new note, or (with ``id``) the next version of one. The agent's
    chat and project are stamped by the MCP tool."""
    if not isinstance(body, dict):
        raise NoteRefused("send the body as a JSON object")
    who = identity_of(body)
    if not is_agent(who):
        raise NoteRefused("agent_id is required: notes are written by an agent's chat through note_write")
    project = str(body.get("project") or "").strip() or _agent_project(store, who)
    if not project or not chatstore.is_code(project) or not (store.data_root / "projects" / project).is_dir():
        raise NoteRefused(f"project {project or '(none)'} is not one Slightly Parallel knows")
    note_id = _text(body, "id", 44)
    text = _text(body, "text", TEXT_MAX, required=True, what="the note's markdown")
    title = _text(body, "title", TITLE_MAX)
    kind = _text(body, "kind", 20)
    task_id = _text(body, "task_id", 20)
    ep_id = _text(body, "entrypoint_id", 20)
    replaces = _text(body, "replaces", 200)
    row = None
    if note_id:
        row = row_of(store, note_id)
        if row is None:
            raise NoteRefused(f"{note_id} is not a note; leave id out to write a new one")
        if str(row.get("archived_at") or "").strip():
            raise NoteRefused(f"{note_id} is archived by the operator; write a new note instead")
        _same_project(store, row, who, {"project": project})
        kind = kind or kind_of(row)
        task_id = task_id if "task_id" in body else str(row.get("task_id") or "")
        ep_id = ep_id if "entrypoint_id" in body else str(row.get("entrypoint_id") or "")
        replaces = replaces if "replaces" in body else str(row.get("replaces") or "")
    if kind not in NOTE_KINDS:
        raise NoteRefused(f"kind is one of {', '.join(NOTE_KINDS)}")
    if task_id:
        if not re.match(r"^tk_[0-9a-f]{8}$", task_id) or _task_row(store, task_id) is None:
            raise NoteRefused(f"{task_id} is not a task; give the tk_… id of the task the note is for, or leave it out")
    if ep_id:
        from . import entrypointlib as E
        ep = E.entry_of(store, ep_id)
        if ep is None:
            raise NoteRefused(f"{ep_id} is not an entry point; leave entrypoint_id out or give an ep_… of the project")
        if ep.get("project") and ep.get("project") != project:
            raise NoteRefused(f"{ep_id} is an entry point of {ep.get('project')}, not of {project}")
    olds = [x.strip() for x in replaces.split(",") if x.strip()]
    for old in olds:
        r = row_of(store, old)
        if r is None or r.get("project") != project or old == note_id:
            raise NoteRefused(f"replaces: {old} is not an older note of {project}")
    raw_images = body.get("images") or []
    if not isinstance(raw_images, list):
        raise NoteRefused("images is a list of {data_base64, caption, name}")
    if len(raw_images) > IMAGES_PER_WRITE:
        raise NoteRefused(f"at most {IMAGES_PER_WRITE} pictures in one write; add more with note_image")
    decoded = [_decode_image(item, i + 1) for i, item in enumerate(raw_images)]
    bases = [Path(d[3]).name for d in decoded if d[3]]
    if len(bases) != len(set(bases)):
        raise NoteRefused("two pictures of one write have the same file name; rename one, the text refers to them by name")
    base = body.get("base")
    if base not in (None, "") and row is not None:
        if isinstance(base, bool) or not str(base).isdigit():
            raise NoteRefused("base is the version number you read and changed")
        now_n = len(versions_of(store, note_id)) or 1
        if int(str(base)) != now_n:
            raise NoteRefused(f"{note_id} is at v{now_n} now, not v{base}: another chat wrote a version since. "
                              "Read it with notes {id} and write yours on top of it. Nothing was written")
    # The title: the text's own first line `# …`, else the one given, written in.
    first = text.replace("\r\n", "\n").split("\n", 1)
    if first[0].startswith("# "):
        title = first[0][2:].strip()[:TITLE_MAX] or title
    elif title:
        text = f"# {title}\n\n{text}"
    else:
        raise NoteRefused("a note has a title: the text's first line `# Title`, or title")
    at = now_iso()
    if not note_id:
        # Random, not from the text: one chat writing two notes of one title in a minute gets two ids.
        while True:
            note_id = "nt_" + secrets.token_hex(4)
            if row_of(store, note_id) is None:
                break
    if row is not None and len(images_of(store, note_id)) + len(decoded) > IMAGES_MAX:
        raise NoteRefused(f"{note_id} would hold more than {IMAGES_MAX} pictures")
    for raw, ext, caption, name in decoded:
        rec = _store_image(store, note_id, raw, ext, caption, who)
        text = _with_ids(text, name, rec["id"])
    p = parse(note_id, text)
    ent = ENTITIES["note"]
    md_ref = f"{ent.detail_dir}/{note_id}.md"
    with acquire_flock(store.data_root / WRITE_LOCK, mode="a"):
        n = len(versions_of(store, note_id)) + 1
        rel = f"{ent.detail_dir}/{note_id}/v{n:03d}.md"
        atomic_write(store.data_root / rel, text)
        append_row(store.data_root / VERSIONS_FILE, NOTE_VERSION_COLUMNS, {
            "id": f"{note_id}#{n}", "note_id": note_id, "n": str(n), "at": at, "agent_id": who,
            "title": title, "kind": kind, "words": str(p["words"]), "file": rel})
        atomic_write(store.data_root / md_ref, build_detail(
            {"title": title, "kind": kind, "project": project, "version": n, "l2": p["lead"], "l4": _escaped(text)}, note_id))
        fields = {"title": title, "kind": kind, "task_id": task_id, "entrypoint_id": ep_id, "replaces": ",".join(olds),
                  "versions_n": str(n), "updated_at": at, "updated_by": who, "md_ref": md_ref}
        if row is None:
            date = f"{at[2:4]}{at[5:7]}-{at[8:10]}"
            append_row(store.data_root / ent.csv, ent.columns, {
                "id": note_id, "created_date": date, "created_time": at[11:16], "project": project,
                "agent_id": who, "tags": "", "archived_at": "", **fields})
        else:
            def change(rows: list[dict[str, str]]) -> bool:
                for r in rows:
                    if r.get("id") == note_id:
                        r.update(fields)
                        return True
                return False
            rewrite_rows(store.data_root / ent.csv, ent.columns, change)
    waits = open_of(kind, p["items"], marks_of(store, {note_id}))
    return {"id": note_id, "version": n, "title": title, "kind": kind, "project": project,
            "task": task_id, "entrypoint": ep_id, "words": p["words"], "open": waits,
            "unknown_images": [s for it in p["items"] if it["type"] == "gallery" for s in
                               (x["src"] for x in it["shots"]) if not IMAGE_ID_RE.match(s)],
            "page": f"/notes?note={note_id}",
            "reply": f"In the chat, say in one line what the note is for and give its id: {note_id}."}


_SECTION_LINE = re.compile(r"^(\s*##\s+)(L[234]\b)", re.M | re.I)


def _escaped(text: str) -> str:
    """The text as the detail document keeps it for search and the lens: a
    line of its own that reads like the document's `## L2` / `## L4` heading
    is kept from splitting it (a zero-width space before the L). The
    versions keep the text as written; the page reads those."""
    return _SECTION_LINE.sub("\\1\u200b\\2", text)


def archive(store: ViewStore, note_id: str, on: bool) -> dict[str, str]:
    _need(store, note_id)
    ent = ENTITIES["note"]
    # The date as #undo stamps it (undolib._archive), so restore and the lists agree.
    stamp = today_yymm_dd() if on else ""
    out: dict[str, str] = {}

    def change(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == note_id:
                r["archived_at"] = stamp
                out.update(r)
                return True
        return False

    rewrite_rows(store.data_root / ent.csv, ent.columns, change)
    return out
