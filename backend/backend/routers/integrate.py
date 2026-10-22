"""Integrate — write a saved set into a project's AGENTS.md.

Copy puts a set on the clipboard; Integrate writes it where every agent in a
project reads it. Each set is its own fenced block, so one set can be
updated or removed without touching the rest of the file:

    <!-- sp:set ks_1a2b3c4d -->
    ## UI for the next release
    …
    <!-- sp:set-end ks_1a2b3c4d -->

A block fenced ``merkhet:set`` (written before the product was renamed) is
read as the same block; the next write fences it anew.

Only ``AGENTS.md`` inside a folder registered in Setup (integrations.csv) is
written — the folder comes from the registry, never from the request.
Claude Code reads it through the ``@AGENTS.md`` line Setup puts in
CLAUDE.md; Codex and OpenCode read AGENTS.md themselves.

A written block is *fresh* when the file holds exactly what the set would
write now, *stale* when an item or the set changed since, *missing* when the
block is gone from the file. ``set_integrations.json`` remembers where each
set was written.

One set is built in: "Rules for all agents" (``all-rules``) — every active
rule the operator turned on for all agents. Slightly Parallel writes it into every
project set up in Setup by itself and rewrites it whenever it changes.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..csvio import read_rows
from ..db import ViewStore
from ..docs_md import read_detail
from ..entities import ENTITIES
from ..file_safety import edit_json, safe_read_json, write_in_place
from .deps import get_store
from .sets import _find as find_set
from .sets import _read as read_sets

router = APIRouter()
LEDGER = "set_integrations.json"
# The built-in set: every rule turned on for all agents, kept written into
# every project set up in Setup. It is not in sets.json; it is derived.
ALL_RULES = "all-rules"
_LABEL = {"vision": "Visions", "rule": "Rules", "problem": "Problems", "entrypoint": "Entry points"}
# A message may open with a list number and a task id: "1. tk_1f96c6db · Name".
_TITLE_RE = re.compile(r"^\s*(?:\d+\.\s*)?(?:tk_[a-z0-9_-]+(?:\.\d+)?\s*·\s*)?", re.IGNORECASE)


MARK = "sp"
OLD_MARK = "merkhet"  # the fence's name before the product was renamed


def marks(set_id: str, name: str = MARK) -> tuple[str, str]:
    return f"<!-- {name}:set {set_id} -->", f"<!-- {name}:set-end {set_id} -->"


def _title(l1: str) -> str:
    return _TITLE_RE.sub("", l1 or "").strip() or (l1 or "").strip()


def compose(store: ViewStore, s: dict[str, Any]) -> str:
    """The block a set writes, exactly as it lands in the file."""
    ent = ENTITIES[s["kind"]]
    ids = [str(i) for i in s.get("items") or []]
    rows: dict[str, dict[str, Any]] = {}
    cols = "id, l1, md_ref, source, status, archived_at" if s["kind"] == "rule" else "id, l1, md_ref, source, archived_at"
    if ids:
        ph = ",".join("?" * len(ids))
        rows = {
            str(r["id"]): r
            for r in store.query(f"SELECT {cols} FROM {ent.view} WHERE id IN ({ph})", tuple(ids))
        }
    parts: list[str] = []
    for i in ids:
        row = rows.get(i)
        if row is None:
            continue
        # An archived rule stays in its sets but is no longer written anywhere,
        # and an example is a mock: it is never written, whatever set holds it.
        if s["kind"] == "rule" and str(row.get("status") or "active") != "active":
            continue
        if str(row.get("source") or "") == "demo":
            continue
        # An entry archived with #undo stays in its sets, written nowhere.
        if str(row.get("archived_at") or "").strip() and s["kind"] != "rule":
            continue
        l2, _l3, l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
        text = (l2 or l4 or "").strip()
        if s["kind"] == "rule":
            # Rules read as one numbered list; a rule's later paragraphs stay under its number.
            first, *rest = (text or _title(str(row["l1"]))).split("\n")
            parts.append("\n".join([f"{len(parts) + 1}. {first}", *[f"   {ln}" if ln.strip() else "" for ln in rest]]))
        else:
            parts.append(f"### {_title(str(row['l1']))}\n\n{text}")
    start, end = marks(s["id"])
    body = ("\n" if s["kind"] == "rule" else "\n\n").join(parts) if parts else "This set is empty."
    intro = (
        "Rules from Slightly Parallel for every project. Slightly Parallel rewrites this block when a rule changes."
        if s["id"] == ALL_RULES else
        f"{_LABEL.get(s['kind'], 'Entries')} from Slightly Parallel, set {s['id']}. "
        "Slightly Parallel replaces this block when the set is updated."
    )
    return f"{start}\n## {s['name']}\n\n{intro}\n\n{body}\n{end}"


def all_rules_set(store: ViewStore) -> dict[str, Any]:
    """The built-in set: active rules turned on for all agents, oldest first."""
    rows = store.query(
        f"SELECT id FROM {ENTITIES['rule'].view} "
        "WHERE lower(trim(COALESCE(auto, ''))) = 'yes' "
        "AND COALESCE(NULLIF(status, ''), 'active') = 'active' "
        "AND COALESCE(source, '') <> 'demo' "
        "ORDER BY created_date, created_time, id"
    )
    return {"id": ALL_RULES, "name": "Rules for all agents", "kind": "rule",
            "items": [str(r["id"]) for r in rows]}


def block_in(text: str, set_id: str) -> str | None:
    for name in (MARK, OLD_MARK):
        start, end = marks(set_id, name)
        a = text.find(start)
        if a < 0:
            continue
        b = text.find(end, a)
        return None if b < 0 else text[a:b + len(end)]
    return None


def _refenced(block: str, set_id: str) -> str:
    """The block with today's fence, whichever it was written with."""
    for old, new in zip(marks(set_id, OLD_MARK), marks(set_id)):
        block = block.replace(old, new, 1)
    return block


def upsert(text: str, block: str, set_id: str) -> tuple[str, str]:
    """(new text, created | appended | updated | unchanged)."""
    current = block_in(text, set_id)
    if current is not None:
        new = text.replace(current, block, 1)
        return new, "unchanged" if new == text else "updated"
    if not text.strip():
        return block + "\n", "created"
    return text.rstrip("\n") + "\n\n" + block + "\n", "appended"


def remove(text: str, set_id: str) -> tuple[str, bool]:
    current = block_in(text, set_id)
    if current is None:
        return text, False
    before, after = text.split(current, 1)
    joined = (before.rstrip("\n") + "\n\n" + after.lstrip("\n")).strip("\n")
    return (joined + "\n" if joined else ""), True


_ANY_SET_RE = re.compile(rf"<!-- (?:{MARK}|{OLD_MARK}):set (\S+) -->.*?<!-- (?:{MARK}|{OLD_MARK}):set-end \1 -->", re.DOTALL)


def remove_all_sets(text: str) -> tuple[str, str]:
    """Take every Slightly Parallel set block out of a file: (new text, removed | unchanged)."""
    ids = [m.group(1) for m in _ANY_SET_RE.finditer(text)]
    if not ids:
        return text, "unchanged"
    for set_id in ids:
        text, _ = remove(text, set_id)
    return text, "removed"


def forget_project(store: ViewStore, project: str) -> None:
    """Drop every record of sets written into a project that is disconnected."""
    _edit_ledger(store, lambda rows: rows.__setitem__(
        slice(None), [e for e in rows if e.get("project") != project]))


def _targets(store: ViewStore) -> dict[str, str]:
    return {
        str(r.get("project") or ""): str(r.get("path") or "")
        for r in read_rows(store.data_root / "integrations.csv")
        if r.get("project") and r.get("path")
    }


def _agents_md(store: ViewStore, project: str) -> Path:
    raw = _targets(store).get(project)
    if not raw:
        raise HTTPException(status_code=409, detail=f"{project or 'That project'} is not set up. Add it in Setup first.")
    folder = Path(raw)
    if not folder.is_dir():
        raise HTTPException(status_code=422, detail=f"the folder for {project} does not exist: {folder}")
    return folder / "AGENTS.md"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"cannot read {path}: {exc}") from exc


def _ledger_rows(data: Any) -> list[dict[str, Any]]:
    rows = data.get("integrations") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict) and r.get("set_id")] if isinstance(rows, list) else []


def _ledger(store: ViewStore) -> list[dict[str, Any]]:
    try:
        return _ledger_rows(safe_read_json(store.data_root / LEDGER))
    except (OSError, ValueError):
        return []


def _edit_ledger(store: ViewStore, change) -> list[dict[str, Any]]:
    """Read-modify-write set_integrations.json under one lock
    (file_safety.edit_json). ``change(rows)`` mutates the list in place."""
    def apply(data: dict) -> dict:
        rows = _ledger_rows(data)
        change(rows)
        return {"integrations": rows}

    return _ledger_rows(edit_json(store.data_root / LEDGER, apply))


def sync_all_rules(store: ViewStore) -> list[dict[str, str]]:
    """Keep "Rules for all agents" written into every project set up in Setup.

    Runs after anything that can change the block: a rule turned on or off
    for all agents, archived, restored or reworded, or a project set up.
    A file is written only when its text changes; with no rule for all
    agents the block is taken out. A folder that is gone is skipped.
    """
    s = all_rules_set(store)
    block = compose(store, s) if s["items"] else ""
    before = _ledger(store)
    prior = {str(e.get("project")): e for e in before if e.get("set_id") == ALL_RULES}
    mine: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    results: list[dict[str, str]] = []
    for project, raw in sorted(_targets(store).items()):
        folder = Path(raw)
        if not folder.is_dir():
            results.append({"project": project, "action": "skipped"})
            continue
        path = folder / "AGENTS.md"
        try:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            if block:
                new, action = upsert(existing, block, ALL_RULES)
            else:
                new, removed = remove(existing, ALL_RULES)
                action = "removed" if removed else "unchanged"
            if new != existing:
                write_in_place(path, new)
        except OSError as exc:
            results.append({"project": project, "action": "failed", "error": str(exc)})
            continue
        if block:
            keep = prior.get(project) if action == "unchanged" else None
            mine.append(keep or {"set_id": ALL_RULES, "project": project, "path": str(folder), "written_at": now})
        results.append({"project": project, "action": action})
    if [e for e in before if e.get("set_id") != ALL_RULES] + mine != before:
        # Only this block's entries are replaced, on the rows as they are
        # under the lock: writing back the copy read at the start wiped
        # whatever another set recorded while the files were written.
        _edit_ledger(store, lambda rows: rows.__setitem__(
            slice(None), [e for e in rows if e.get("set_id") != ALL_RULES] + mine))
    return results


def _set_for(store: ViewStore, set_id: str, sets: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return all_rules_set(store) if set_id == ALL_RULES else sets.get(set_id)


def status_of(store: ViewStore, s: dict[str, Any] | None, entry: dict[str, Any]) -> str:
    try:
        text = (Path(str(entry.get("path") or "")) / "AGENTS.md").read_text(encoding="utf-8")
    except OSError:
        return "missing"
    block = block_in(text, str(entry["set_id"]))
    if block is None:
        return "missing"
    return "fresh" if s is not None and _refenced(block, str(entry["set_id"])) == compose(store, s) else "stale"


@router.get("/api/integrations/targets")
def integration_targets(store: ViewStore = Depends(get_store)) -> dict:
    """The projects a set can be written into: every folder set up in Setup."""
    return {"targets": [
        {"project": p, "path": raw, "agents_md": (Path(raw) / "AGENTS.md").is_file()}
        for p, raw in sorted(_targets(store).items())
    ]}


@router.get("/api/integrations")
def integrations_all(store: ViewStore = Depends(get_store)) -> dict:
    """Where every set was written, and whether each block is still current."""
    sets = {str(s["id"]): s for s in read_sets(store)}
    return {"integrations": [
        {**e, "status": status_of(store, _set_for(store, str(e["set_id"]), sets), e)} for e in _ledger(store)
    ]}


@router.get("/api/integrations/all-rules")
def all_rules(store: ViewStore = Depends(get_store)) -> dict:
    """The built-in set: which rules, the exact block, and each project's copy."""
    s = all_rules_set(store)
    content = compose(store, s) if s["items"] else ""
    written = {str(e.get("project")): e for e in _ledger(store) if e.get("set_id") == ALL_RULES}
    return {
        "items": s["items"],
        "content": content,
        "words": len(content.split()),
        "projects": [
            {"project": p, "path": raw,
             "status": status_of(store, s, written[p]) if p in written else ("missing" if s["items"] else "none")}
            for p, raw in sorted(_targets(store).items())
        ],
    }


@router.post("/api/integrations/all-rules/sync")
async def all_rules_sync(store: ViewStore = Depends(get_store)) -> dict:
    """Write the built-in set into every project now — for a copy changed by hand."""
    return {"results": await asyncio.to_thread(sync_all_rules, store)}


@router.get("/api/sets/{set_id}/integrations")
def set_integrations(set_id: str, store: ViewStore = Depends(get_store)) -> dict:
    s = find_set(read_sets(store), set_id)
    return {"integrations": [
        {**e, "status": status_of(store, s, e)} for e in _ledger(store) if e.get("set_id") == set_id
    ]}


@router.post("/api/sets/{set_id}/integrate")
def integrate_set(set_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, dry_run?}`` — write (or preview) the set's block in that project's AGENTS.md."""
    s = find_set(read_sets(store), set_id)
    project = str(body.get("project") or "").strip()
    path = _agents_md(store, project)
    existing = _read_text(path)
    block = compose(store, s)
    new, action = upsert(existing, block, set_id)
    dry_run = bool(body.get("dry_run", False))
    if not dry_run:
        if action != "unchanged":
            write_in_place(path, new)
        def record(rows: list[dict[str, Any]]) -> None:
            rows[:] = [e for e in rows if not (e.get("set_id") == set_id and e.get("project") == project)]
            rows.append({
                "set_id": set_id, "project": project, "path": str(path.parent),
                "written_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            })

        _edit_ledger(store, record)
    return {
        "file": str(path), "action": action, "dry_run": dry_run, "content": block,
        "previous": block_in(existing, set_id), "words": len(block.split()),
    }


@router.post("/api/sets/{set_id}/integrate/remove")
def integrate_remove(set_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project}`` — take the set's block out of that project's AGENTS.md."""
    project = str(body.get("project") or "").strip()
    path = _agents_md(store, project)
    new, removed = remove(_read_text(path), set_id)
    if removed:
        write_in_place(path, new)
    _edit_ledger(store, lambda rows: rows.__setitem__(slice(None), [
        e for e in rows if not (e.get("set_id") == set_id and e.get("project") == project)
    ]))
    return {"file": str(path), "action": "removed" if removed else "unchanged"}
