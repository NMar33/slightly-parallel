"""Kanban boards — named sets of projects seen as one board.

Every project is a board by itself (nothing to store). A *combined* board
is ``{id, name, projects: [codes]}``; a *standalone* board is a board with
its own code and no other project — a tasks-only project that exists in
Slightly Parallel by its rows, like any data-only project. Boards live in
``boards.json`` at the data root so they are the same in every browser.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ..db import ViewStore
from ..file_safety import edit_json, safe_read_json
from .deps import etag_for, get_store, json_response, maybe_304, not_found

router = APIRouter()
BOARDS_FILE = "boards.json"
_CODE_RE = re.compile(r"[^a-z0-9_-]+")


def _rows(data: Any) -> list[dict[str, Any]]:
    boards = data.get("boards") if isinstance(data, dict) else None
    return [b for b in boards if isinstance(b, dict) and b.get("id")] if isinstance(boards, list) else []


def _read(store: ViewStore) -> list[dict[str, Any]]:
    try:
        return _rows(safe_read_json(store.data_root / BOARDS_FILE))
    except (OSError, ValueError):
        return []


def _edit(store: ViewStore, change) -> Any:
    """Read-modify-write boards.json under one lock (file_safety.edit_json).

    Without it two posts each read the file, each appended a board and the
    second write forgot the first. ``change(boards)`` mutates the list and
    returns what the route answers.
    """
    answer: list[Any] = []

    def apply(data: dict) -> dict:
        boards = _rows(data)
        answer.append(change(boards))
        return {"boards": boards}

    edit_json(store.data_root / BOARDS_FILE, apply)
    return answer[0]


def slugify(name: str) -> str:
    return _CODE_RE.sub("-", name.strip().lower()).strip("-")[:40]


def _clean_projects(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else str(raw or "").split(",")
    out: list[str] = []
    for x in items:
        c = str(x).strip()
        if c and c not in out:
            out.append(c)
    return out


@router.get("/api/boards")
def boards_list(request: Request, store: ViewStore = Depends(get_store)) -> Response:
    boards = _read(store)
    etag = etag_for("boards:" + hashlib.sha256(json.dumps(boards, sort_keys=True).encode()).hexdigest()[:12], store)
    if (r := maybe_304(request, etag)) is not None:
        return r
    return json_response({"total": len(boards), "boards": boards}, etag)


@router.post("/api/boards", status_code=201)
def boards_create(
    response: Response, body: dict = Body(...), store: ViewStore = Depends(get_store),
) -> dict:
    """``{name, projects?}`` — no projects → standalone board whose code is
    the slug of its name (its tasks' home project)."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    projects = _clean_projects(body.get("projects"))
    standalone = not projects
    if standalone:
        code = slugify(name)
        if not code:
            raise HTTPException(status_code=422, detail="name must contain letters or digits")
        projects = [code]
    bid = "bd_" + hashlib.sha256(f"{name}|{','.join(projects)}".encode()).hexdigest()[:8]

    def add(boards: list[dict[str, Any]]) -> dict:
        found = next((b for b in boards if b.get("id") == bid), None)
        if found is not None:
            return {**found, "existing": True}
        board = {"id": bid, "name": name, "projects": projects, "standalone": standalone}
        boards.append(board)
        return {**board, "existing": False}

    board = _edit(store, add)
    if board["existing"]:
        # The one rule for a repeated create: nothing new was written.
        response.status_code = 200
    return {**board, "warnings": []}


@router.post("/api/boards/{board_id}/update")
def boards_update(board_id: str, body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict:
    def change(boards: list[dict[str, Any]]) -> dict:
        board = next((b for b in boards if b.get("id") == board_id), None)
        if board is None:
            raise not_found("board", board_id)
        if "name" in body and str(body["name"]).strip():
            board["name"] = str(body["name"]).strip()
        if "projects" in body and not board.get("standalone"):
            projects = _clean_projects(body["projects"])
            if not projects:
                raise HTTPException(status_code=422, detail="a combined board needs at least one project")
            board["projects"] = projects
        return dict(board)

    return _edit(store, change)


@router.post("/api/boards/{board_id}/delete")
def boards_delete(board_id: str, store: ViewStore = Depends(get_store)) -> dict:
    """Forget the board. Tasks are never touched — a standalone board's tasks
    stay as a data-only project until deleted from Setup."""
    def drop(boards: list[dict[str, Any]]) -> dict:
        kept = [b for b in boards if b.get("id") != board_id]
        if len(kept) == len(boards):
            raise not_found("board", board_id)
        boards[:] = kept
        return {"deleted": board_id}

    return _edit(store, drop)
