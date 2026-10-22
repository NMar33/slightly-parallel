"""File-lens extras: the path×date heatmap.

Registered before the generic lens router so ``/api/files/heatmap`` wins
over ``/api/files/{file_id}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from ..db import ViewStore
from .deps import etag_for, frontmatter_cached, get_store, json_response, maybe_304, to_int

router = APIRouter()


def _semantic_score(pth: dict) -> int:
    """Composite 0-100 importance score from agent-provided assessment fields.

    Weights (defaults chosen to score neutral when fields are absent):
      importance (1-5)          × 5  →  0-25
      blast_radius (1-10)       × 2  →  0-20
      security_surface (bool)   → 15 when True
      test_coverage             →  0/8/15 (untested scores highest — risk)
      agent_confidence (inverse)→ (100-c)×0.15 (low confidence scores higher)
      novelty                   → 3/6/10 (pattern-break scores highest)
    """
    def _as_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    importance = _as_int(pth.get("importance"), 3)
    blast = _as_int(pth.get("blast_radius"), 3)
    security = bool(pth.get("security_surface", False))
    test_cov = str(pth.get("test_coverage", "partial")).lower()
    conf = _as_int(pth.get("agent_confidence"), 70)
    novelty = str(pth.get("novelty", "pattern-follow")).lower()

    s = max(0, min(5, importance)) * 5
    s += max(0, min(10, blast)) * 2
    s += 15 if security else 0
    s += {"covered": 0, "partial": 8, "untested": 15}.get(test_cov, 8)
    s += (100 - max(0, min(100, conf))) * 0.15
    s += {"pattern-follow": 3, "new": 6, "pattern-break": 10}.get(novelty, 6)
    return int(round(s))


@router.get("/api/files/heatmap")
def files_heatmap(
    request: Request,
    project: str | None = Query(None),
    from_: str | None = Query(None, alias="from_date"),
    to: str | None = Query(None, alias="to_date"),
    path_prefix: str | None = Query(None),
    limit_files: int = Query(50, ge=1, le=500),
    store: ViewStore = Depends(get_store),
) -> Response:
    """Aggregate touches across all file entries, per date and per entry.

    Returns ``{files, dates, matrix, entries, cells, max}``: ``matrix`` keys
    are ``"<path>||<date>"`` (day aggregate), ``cells`` keys are
    ``"<path>||<entry_id>"`` (one checkpoint), and ``entries`` lists every
    file entry in chronological order with its scan and derived session so
    a column can open the checkpoint and the chat behind it. Files are
    sorted by total touches descending, capped at ``limit_files``.
    """
    etag = etag_for(
        f"files:heatmap:{project}:{from_}:{to}:{path_prefix}:{limit_files}",
        store,
    )
    if (r := maybe_304(request, etag)) is not None:
        return r

    sessions_by_lane = _sessions_by_lane(store)
    matrix: dict[str, dict[str, Any]] = {}
    cells: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    file_totals: dict[str, dict[str, Any]] = {}
    dates_seen: set[str] = set()

    # One project asked for: a file is its path. Every project: the same
    # path in two repositories (README.md, AGENTS.md) is two files, so the
    # key the cells and the matrix hang on carries the project, and each
    # file row says which project it is from.
    scoped = bool(project)
    for row in _heatmap_rows(store, project, from_, to):
        fm = frontmatter_cached(store.data_root, row.get("md_ref") or "")
        if fm is None:
            continue
        paths_list = fm.get("paths") or []
        if not isinstance(paths_list, list):
            continue
        entry = _heatmap_entry(row, sessions_by_lane)
        entries.append(entry)
        for pth in paths_list:
            if not isinstance(pth, dict):
                continue
            path = str(pth.get("path") or "")
            if not path:
                continue
            if path_prefix and not path.startswith(path_prefix):
                continue
            dates_seen.add(entry["date"])
            key = path if scoped else f"{entry['project']}::{path}"
            _add_touch(matrix, cells, file_totals, entry, path, pth, key)
            entry["paths_n"] += 1

    files_sorted = _top_files(file_totals, limit_files)
    top_paths = {f["key"] for f in files_sorted}
    matrix_filtered = {
        k: v for k, v in matrix.items() if k.split("||", 1)[0] in top_paths
    }
    cells_filtered = {
        k: v for k, v in cells.items() if k.split("||", 1)[0] in top_paths
    }
    return json_response(
        {
            "files": files_sorted,
            "dates": sorted(dates_seen),
            "matrix": matrix_filtered,
            "entries": entries,
            "cells": cells_filtered,
            "max": max((c["count"] for c in matrix.values()), default=0),
        },
        etag,
    )


def _heatmap_rows(store: ViewStore, project: str | None, from_: str | None, to: str | None) -> list[dict[str, Any]]:
    """The file entries in range, oldest first."""
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if project:
        clauses.append("project = ?")
        params.append(project)
    if from_:
        clauses.append("created_date >= ?")
        params.append(from_)
    if to:
        clauses.append("created_date <= ?")
        params.append(to)
    return store.query(
        "SELECT id, created_date, created_time, project, agent_id, l1, "
        "trigger_lens, trigger_id, md_ref FROM files_mutual WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_date ASC, created_time ASC, id ASC",
        tuple(params),
    )


def _heatmap_entry(row: dict[str, Any], sessions_by_lane: dict) -> dict[str, Any]:
    """One checkpoint column: the entry, its scan and the session behind it."""
    date = row.get("created_date") or ""
    entry_project = str(row.get("project") or "")
    entry_time = str(row.get("created_time") or "")
    entry_agent = str(row.get("agent_id") or "")
    return {
        "id": row.get("id") or "",
        "date": date,
        "time": entry_time,
        "agent_id": entry_agent,
        # Fleet-wide reads ask "which project was this?" — the per-project
        # call already knows, but the unfiltered one cannot guess.
        "project": entry_project,
        "l1": str(row.get("l1") or ""),
        "trigger_lens": str(row.get("trigger_lens") or ""),
        "scan_id": (
            str(row.get("trigger_id") or "")
            if str(row.get("trigger_lens") or "") == "scan" else ""
        ),
        "session_id": _session_for(sessions_by_lane, entry_project, entry_agent, date, entry_time),
        "paths_n": 0,
    }


def _add_tags(target: dict[str, Any], tags: list | None) -> None:
    for t in tags or []:
        ts = str(t)
        if ts and ts not in target["tags"]:
            target["tags"].append(ts)


def _add_touch(
    matrix: dict[str, dict[str, Any]], cells: dict[str, dict[str, Any]],
    file_totals: dict[str, dict[str, Any]], entry: dict[str, Any], path: str, pth: dict,
    key: str | None = None,
) -> None:
    """Count one path of one entry into its day cell, its checkpoint cell
    and the file's totals. ``key`` names the file in the cells, the matrix
    and the totals: the path itself, or ``project::path`` when the answer
    spans every project."""
    key = key or path
    date, entry_id, entry_project = entry["date"], entry["id"], entry["project"]
    action = str(pth.get("action") or "modified")
    la = _as_int0(pth.get("lines_add"))
    ld = _as_int0(pth.get("lines_del"))
    sem_score = _semantic_score(pth)
    tags = pth.get("tags") if isinstance(pth.get("tags"), list) else []

    cell = matrix.setdefault(f"{key}||{date}", {
        "count": 0, "lines_add": 0, "lines_del": 0, "entry_ids": [],
        "semantic_score": 0, "tags": [],
    })
    cell["count"] += 1
    cell["lines_add"] += la
    cell["lines_del"] += ld
    cell["semantic_score"] = max(cell["semantic_score"], sem_score)
    _add_tags(cell, tags)
    if entry_id and entry_id not in cell["entry_ids"]:
        cell["entry_ids"].append(entry_id)

    one = cells.setdefault(f"{key}||{entry_id}", {
        "count": 0, "lines_add": 0, "lines_del": 0, "action": action,
        "semantic_score": 0, "tags": [], "why": "",
    })
    one["count"] += 1
    one["lines_add"] += la
    one["lines_del"] += ld
    one["semantic_score"] = max(one["semantic_score"], sem_score)
    if not one["why"]:
        one["why"] = str(pth.get("why") or "")
    _add_tags(one, tags)

    totals = file_totals.setdefault(key, {
        "path": path, "key": key, "total": 0, "created": 0, "modified": 0,
        "deleted": 0, "lines_add": 0, "lines_del": 0, "projects": {},
        "semantic_score": 0, "tags": [],
    })
    totals["total"] += 1
    totals["lines_add"] += la
    totals["lines_del"] += ld
    totals["semantic_score"] = max(totals["semantic_score"], sem_score)
    _add_tags(totals, tags)
    if action in ("created", "modified", "deleted"):
        totals[action] += 1
    if entry_project:
        totals["projects"][entry_project] = (
            totals["projects"].get(entry_project, 0) + 1
        )


def _top_files(file_totals: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Files by touches, most first, each with the project that touched it
    most as its own."""
    for totals in file_totals.values():
        proj_map = totals.pop("projects", {}) or {}
        totals["project"] = (
            max(proj_map.items(), key=lambda kv: (kv[1], kv[0]))[0]
            if proj_map
            else ""
        )
    return sorted(
        file_totals.values(), key=lambda x: (-x["total"], x["path"])
    )[:limit]


def _sessions_by_lane(store: ViewStore) -> dict[tuple[str, str, str], list[dict]]:
    """Every session under (project, agent, day), earliest first: one read
    for the heatmap, which asked once per file entry."""
    out: dict[tuple[str, str, str], list[dict]] = {}
    for r in store.query(
        "SELECT id, project, agent_id, created_date, start_time FROM sessions ORDER BY start_time ASC"
    ):
        key = (str(r.get("project") or ""), str(r.get("agent_id") or ""), str(r.get("created_date") or ""))
        out.setdefault(key, []).append(r)
    return out


def _session_for(
    lanes: dict[tuple[str, str, str], list[dict]], project: str, agent_id: str, date: str, time: str
) -> str:
    """The derived session this checkpoint belongs to: same agent and day,
    the latest one that started at or before the entry time (a scan is
    posted at the end of a turn, so it usually sits just past ``end_time``);
    else the day's first session."""
    if not (project and agent_id and date):
        return ""
    rows = lanes.get((project, agent_id, str(date)), [])
    if not rows:
        return ""
    chosen = rows[0]
    for r in rows:
        if str(r.get("start_time") or "") <= (time or "99:99"):
            chosen = r
    return str(chosen.get("id") or "")


_as_int0 = to_int  # a whole number out of a frontmatter value (deps)
