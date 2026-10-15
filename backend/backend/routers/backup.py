"""Backups — list, take, verify, download, restore.

The engine is ``backend.backup``; this is the operator's hand on it. Two
rules shape everything below.

Never block the event loop. Tarring 30 MB takes seconds, hashing takes
more, and the browser fetches its data from this same server — a blocking
archive makes the dashboard hang while it is being protected. Every call
that touches the disk goes through ``asyncio.to_thread``.

Nothing here is cached. Every other endpoint ships an ETag off the store's
view clock; the backup root is outside the data root and outside the
watcher's view, so its clock says nothing about it. A stale backup list is
the one list an operator must never be shown.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .. import app_settings, backup, limits
from ..db import ViewStore
from .deps import get_store, not_found

router = APIRouter()


def _roots(store: ViewStore) -> tuple[Path, Path]:
    return store.data_root, backup.backup_root_for(store.data_root)


def keep_budget(data_root: Path) -> dict[str, int]:
    return backup.keep_budget(data_root)


def _archive_name(name: str) -> str:
    """A path segment is not a name. Anything that is not one is a 404."""
    if backup.parse_name(name) is None:
        raise not_found("backup", name)
    return name


def _fail(exc: backup.BackupError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _state(data_root: Path, backup_root: Path) -> dict[str, Any]:
    values = app_settings.load(data_root)
    every = int(values.get("backup.every_hours", 6))
    enabled = bool(values.get("backup.enabled", True))
    archives = backup.list_archives(backup_root)
    keep, drop = backup.plan_prune(archives, datetime.now(), keep_budget(data_root))
    src_files, src_bytes, src_mtime = backup.source_stats(data_root)
    ready, why = backup.due(archives, datetime.now(), every if enabled else 0, src_mtime)
    return {
        "data_root": str(data_root),
        "backup_root": str(backup_root),
        "enabled": enabled,
        "every_hours": every,
        "keep": keep_budget(data_root),
        "excluded": list(backup.EXCLUDE_GLOBS) + [d + "/" for d in backup.EXCLUDE_DIRS],
        "rungs": [{"name": r.name, "days": r.age.days} for r in backup.RUNGS],
        "source": {"files": src_files, "bytes": src_bytes, "mtime": src_mtime,
                   # Symbolic links in the data root: not followed, not archived.
                   "skipped_links": len(backup.skipped_links(data_root))},
        # Folders a failed restore left with the operator's data in them.
        "kept_aside": backup.kept_aside(backup_root),
        "due": ready,
        "due_reason": why,
        # Every archive on disk, kept or not — an archive the next rotation
        # will remove is exactly the one an operator might want to pin, and it
        # cannot be pinned from a list it is missing from.
        "archives": [
            a.as_dict() | {"expiring": a in drop}
            for a in sorted(keep + drop, key=lambda a: a.at, reverse=True)
        ],
        "expiring": [a.name for a in drop],
        "total_bytes": sum(a.bytes for a in archives),
        "count": len(archives),
    }


@router.get("/api/backup")
async def backup_state(store: ViewStore = Depends(get_store)) -> dict:
    """Everything the Backups page needs: the ladder, the archives, the clock."""
    data_root, backup_root = _roots(store)
    return await asyncio.to_thread(_state, data_root, backup_root)


@router.get("/api/backup/{name}/download")
def backup_download(name: str, store: ViewStore = Depends(get_store)) -> FileResponse:
    """The archive itself — the answer to "the backups are on the same disk"."""
    _archive_name(name)
    _, backup_root = _roots(store)
    archive = backup.find(backup_root, name)
    if archive is None or archive.path is None:
        raise not_found("backup", name)
    return FileResponse(
        archive.path, media_type="application/gzip",
        filename=name + backup.ARCHIVE_SUFFIX,
    )


@router.post("/api/backup/reveal")
async def backup_reveal(
    body: dict = Body(default={}), store: ViewStore = Depends(get_store),
) -> dict:
    """Open the backup folder in the file manager.

    ``{"name": "<archive>"}`` aims at one archive (selected in it, where the
    platform can); no name opens the folder itself. The path is resolved
    here from the server's own listing and never from the request, so this
    cannot be pointed at anything but the archives.
    """
    _, backup_root = _roots(store)
    name = str(body.get("name") or "")
    target = backup_root
    if name:
        _archive_name(name)
        archive = backup.find(backup_root, name)
        if archive is None or archive.path is None:
            raise not_found("backup", name)
        target = archive.path
    if not backup_root.exists():
        raise HTTPException(
            status_code=404,
            detail=f"The backup folder {backup_root} does not exist yet.",
        )
    opened, detail = await asyncio.to_thread(backup.reveal, target)
    return {"opened": opened, "path": str(target), "detail": detail}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _run(data_root: Path, backup_root: Path, kind: str, label: str) -> dict[str, Any]:
    # One hold for both: a second Back up now waits for this one to finish.
    with backup.BUSY:
        archive = backup.create(data_root, backup_root, kind=kind, label=label)
        pruned = backup.prune(backup_root, datetime.now(), keep_budget(data_root))
    return {"archive": archive.as_dict(), "pruned": pruned}


@router.post("/api/backup/run")
async def backup_run(
    body: dict = Body(default={}), store: ViewStore = Depends(get_store),
) -> dict:
    """Take one now. ``{"kind": "manual"|"auto", "label": "…"}``.

    Manual by default: a backup somebody asked for is a bookmark, and gets
    kept by count rather than aged off the ladder in a day.
    """
    kind = str(body.get("kind") or "manual")
    if kind not in backup.KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {backup.KINDS}")
    label = str(body.get("label") or "")[:limits.MAX_TITLE]
    data_root, backup_root = _roots(store)
    try:
        result = await asyncio.to_thread(_run, data_root, backup_root, kind, label)
    except backup.BackupError as exc:
        raise _fail(exc) from exc
    result["state"] = await asyncio.to_thread(_state, data_root, backup_root)
    return result


@router.post("/api/backup/{name}/trial")
async def backup_trial(name: str, store: ViewStore = Depends(get_store)) -> dict:
    """Restore the archive into a temporary folder and read it as the
    dashboard would (backup.trial); the result is kept as the last check."""
    backup_root = backup.backup_root_for(store.data_root)
    try:
        return await asyncio.to_thread(backup.trial, backup_root, name)
    except backup.BackupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/backup/checked")
def backup_checked(store: ViewStore = Depends(get_store)) -> dict:
    """The last trial restore: which archive, when, and what it found."""
    return {"checked": backup.last_trial(backup.backup_root_for(store.data_root))}


@router.post("/api/backup/{name}/verify")
async def backup_verify(name: str, store: ViewStore = Depends(get_store)) -> dict:
    """Re-hash it and read its table of contents — an unchecked backup is a belief."""
    _archive_name(name)
    _, backup_root = _roots(store)
    try:
        return await asyncio.to_thread(backup.verify, backup_root, name)
    except backup.BackupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/backup/{name}/pin")
async def backup_pin(
    name: str, body: dict = Body(default={}), store: ViewStore = Depends(get_store),
) -> dict:
    """``{"pinned": true}`` — exempt this archive from rotation, forever."""
    _archive_name(name)
    data_root, backup_root = _roots(store)
    pinned = bool(body.get("pinned", True))
    try:
        archive = await asyncio.to_thread(backup.set_pinned, backup_root, name, pinned)
    except backup.BackupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"archive": archive.as_dict(),
            "state": await asyncio.to_thread(_state, data_root, backup_root)}


@router.post("/api/backup/{name}/delete")
async def backup_delete(name: str, store: ViewStore = Depends(get_store)) -> dict:
    _archive_name(name)
    data_root, backup_root = _roots(store)
    try:
        await asyncio.to_thread(backup.delete, backup_root, name)
    except backup.BackupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": name,
            "state": await asyncio.to_thread(_state, data_root, backup_root)}


def _restore(data_root: Path, backup_root: Path, name: str) -> dict[str, Any]:
    # The state being replaced gets an archive of its own, once the archive
    # being restored has proved it will read (backup.restore_with_safety).
    report, safety = backup.restore_with_safety(backup_root, name, data_root)
    return {"restored": report, "safety": safety.as_dict()}


@router.post("/api/backup/{name}/restore")
async def backup_restore(
    name: str, request: Request, body: dict = Body(default={}),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Put an archive back over the live data root.

    Guarded by an explicit ``{"confirm": "<name>"}`` echo — this is the one
    endpoint in Slightly Parallel that destroys data, and a mis-click on a list of
    similar-looking dates should not be able to reach it.
    """
    _archive_name(name)
    if str(body.get("confirm") or "") != name:
        raise HTTPException(
            status_code=422,
            detail=f'restoring replaces the data root — send {{"confirm": "{name}"}}',
        )
    data_root, backup_root = _roots(store)
    try:
        result = await asyncio.to_thread(_restore, data_root, backup_root, name)
    except backup.BackupError as exc:
        raise _fail(exc) from exc
    # The views are a cache of a directory that just changed underneath them.
    await asyncio.to_thread(request.app.state.store.rebuild)
    result["state"] = await asyncio.to_thread(_state, data_root, backup_root)
    return result
