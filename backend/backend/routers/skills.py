"""Skills over HTTP — drafts, versions, installed copies and usage.

Reading a skill is the lens detail (``GET /api/skills/{id}``), which adds the
current SKILL.md, its checks, where it is installed and how often it ran.
This router holds what the generic lens cannot:

- ``POST /api/skills/{id}/draft`` — the next SKILL.md: an agent answering
  ``#skill``, or the operator editing.
- ``POST /api/skills/new`` — a skill written on the Skills page.
- ``POST /api/skills/{id}/install`` · ``/uninstall`` · ``/keep-disk`` — the
  copies in a project's ``.claude/skills`` and ``.agents/skills``. The
  operator's choice; an agent writes drafts only.
- ``GET /api/skills/usage`` · ``POST /api/skills/usage/backfill``.

Registered before the lens router, so ``/api/skills/usage`` is not read as
a skill id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import keeplib, skilllib
from ..db import ViewStore
from ..docs_md import read_detail
from .deps import create_answer, get_store, not_found, operator_only, written_by_agent

router = APIRouter()

# Plain functions: FastAPI runs each on a worker thread. As coroutines they
# read rows, documents and chat logs on the event loop around the one call
# they handed to a thread, and every other request waited meanwhile.


def _row(store: ViewStore, item_id: str) -> dict[str, Any]:
    row = keeplib.row_of(store, "skill", item_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {item_id}")
    return row


def _detail(store: ViewStore, item_id: str) -> dict[str, Any]:
    row = _row(store, item_id)
    l2, l3, l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
    return {"metadata": row, "l2": l2, "l3": l3, "l4": l4, **skilllib.enrich(store, row)}


def _operator_only(body: dict, what: str) -> None:
    operator_only(body, what, "an agent writes drafts")


@router.get("/api/skills/usage")
def skills_usage(days: int = Query(30, ge=1, le=3650), store: ViewStore = Depends(get_store)) -> dict:
    """Uses per skill, and skills that ran but are not in Slightly Parallel."""
    return skilllib.usage(store, days)


@router.post("/api/skills/usage/backfill")
def skills_backfill(store: ViewStore = Depends(get_store)) -> dict:
    """Read skill uses from past Claude Code logs into the captured chats."""
    return skilllib.backfill(store)


@router.get("/api/skills/found")
def skills_found(store: ViewStore = Depends(get_store)) -> dict:
    """Skill folders on this machine that Slightly Parallel does not keep, and where they sit."""
    return {"found": skilllib.found_skills(store)}


@router.post("/api/skills/import", status_code=201)
def skills_import(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{path, tags?}`` — take a folder from the list above into Slightly Parallel. The folder is not changed."""
    _operator_only(body, "taking a skill in")
    try:
        taken = skilllib.import_skill(
            store, str(body.get("path") or ""), tags=str(body.get("tags") or ""),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return create_answer({**_detail(store, taken["id"]), "skipped": taken["skipped"]})


@router.post("/api/skills/new", status_code=201)
def skills_new(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{skill_md, files?, project?, tags?}`` — a skill written on the Skills page."""
    _operator_only(body, "writing a skill on the Skills page")
    try:
        kid = skilllib.create_written(
            store, str(body.get("skill_md") or ""), body.get("files"),
            project=str(body.get("project") or ""), tags=str(body.get("tags") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return create_answer(_detail(store, kid))


@router.post("/api/skills/{item_id}/draft")
def skill_draft(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{agent_id | actor, skill_md, files?, note?}`` — the next version of SKILL.md and its files."""
    row = _row(store, item_id)
    by_agent = written_by_agent(body)
    try:
        skilllib.write_version(
            store, row, str(body.get("skill_md") or ""), body.get("files"),
            how="interpreted" if by_agent else "edited", note=str(body.get("note") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, item_id)


@router.get("/api/skills/{item_id}/versions/{n}")
def skill_version(item_id: str, n: int, store: ViewStore = Depends(get_store)) -> dict:
    _row(store, item_id)
    version = skilllib.read_version(store, item_id, n)
    if version is None:
        raise not_found("version", str(n))
    return version


@router.get("/api/skills/{item_id}/copy")
def skill_copy(item_id: str, project: str = Query(...), store: ViewStore = Depends(get_store)) -> dict:
    """The copy in that project as it is on disk, and which files differ from the current version."""
    row = _row(store, item_id)
    try:
        return skilllib.read_copy(store, row, project)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/skills/{item_id}/install")
def skill_install(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, dry_run?, force?}`` — write the current version into the project's skill folders.

    A dry run answers ``action``: created · updated · unchanged · changed. A
    copy edited on disk (``changed``) is written only with ``force``.
    """
    _operator_only(body, "installing a skill")
    row = _row(store, item_id)
    try:
        return skilllib.install(
            store, row, str(body.get("project") or "").strip(),
            dry_run=bool(body.get("dry_run", False)), force=bool(body.get("force", False)),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/skills/{item_id}/uninstall")
def skill_uninstall(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, force?}`` — take the skill's folders out of a project.

    ``{removed: []}`` when it was not installed there. A copy edited on disk
    is removed only with ``force``.
    """
    _operator_only(body, "removing a skill")
    row = _row(store, item_id)
    try:
        removed = skilllib.uninstall(
            store, row, str(body.get("project") or "").strip(),
            force=bool(body.get("force", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"removed": removed}


@router.post("/api/skills/{item_id}/keep-disk")
def skill_keep_disk(item_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    """``{project, path?}`` — a copy was edited on disk: keep it as the next version.

    ``path`` says which copy when the project's two copies differ from each other.
    """
    _operator_only(body, "taking a skill from disk")
    row = _row(store, item_id)
    try:
        skilllib.keep_disk(
            store, row, str(body.get("project") or "").strip(),
            str(body.get("path") or "").strip(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(store, item_id)
