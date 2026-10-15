"""SCAN snapshots — the pyramid entries at the heart of the product.

Scans predate the generic entity machinery and keep two specifics: a typed
request model (:class:`ScanCreate`) and detail documents that live under
``snapshots/`` rather than a ``*_details`` folder.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from .. import entry_fields, scanlib

from ..csvio import append_if_absent, rewrite_rows
from ..db import ViewStore
from ..docs_md import parse_sections, resolve_under, safe_ref_part
from ..file_safety import atomic_write
from ..models import ScanCreate, ScanDetail, ScanRow, ScansListResponse
from .deps import (
    clean, etag_for, get_store, json_response, known_project, maybe_304, rows_as,
)

router = APIRouter()

# Columns MUST match the header row in scans.csv.
_SCAN_COLUMNS = (
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "files_n", "lines_add", "lines_del", "decisions_n",
    "scope", "md_ref",
)


def _scan_errors(exc: "ValidationError") -> str:
    """Name the fields the way an agent wrote them, not the storage slots."""
    names = {f.slot: f.name for f in entry_fields.fields_for("scan")}
    parts = []
    for err in exc.errors():
        loc = str(err["loc"][0]) if err.get("loc") else ""
        parts.append(f"{names.get(loc, loc)}: {err.get('msg', 'invalid')}")
    return "scan: " + "; ".join(parts)


def _mint_scan_id(body: ScanCreate) -> str:
    """Deterministic 8-char id — stable across re-POSTs of the same payload."""
    key = "|".join(
        [body.project, body.agent_id, body.created_date, body.created_time, body.l1]
    )
    return "sn_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _build_scan_md(body: ScanCreate, sid: str) -> str:
    lines = [
        "---",
        f"id: {sid}",
        f"created_date: {body.created_date}",
        f"created_time: {body.created_time}",
        f"project: {body.project}",
        f"agent_id: {body.agent_id}",
        'l1: "' + body.l1.replace('"', '\\"') + '"',
        f"files_n: {body.files_n}",
        f"lines_add: {body.lines_add}",
        f"lines_del: {body.lines_del}",
        f"decisions_n: {body.decisions_n}",
        f"scope: {body.scope}",
        "---",
        "",
        "## L2",
        "",
        body.l2,
        "",
        "## L3",
        "",
    ]
    lines.extend(f"- {item}" for item in body.l3)
    lines += ["", "## L4", "", body.l4, ""]
    return "\n".join(lines)


@router.get("/api/scans", response_model=ScansListResponse)
def scans_list(
    request: Request,
    project: str | None = Query(None),
    agent_id: str | None = Query(None),
    from_: str | None = Query(None, alias="from_date"),
    to: str | None = Query(None, alias="to_date"),
    limit: int = Query(500, ge=1, le=5000),
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"scans:{project}:{agent_id}:{from_}:{to}:{limit}", store, "scans")
    if (r := maybe_304(request, etag)) is not None:
        return r

    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if project:
        clauses.append("project = ?")
        params.append(project)
    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if from_:
        clauses.append("created_date >= ?")
        params.append(from_)
    if to:
        clauses.append("created_date <= ?")
        params.append(to)
    sql = (
        "SELECT * FROM scans WHERE " + " AND ".join(clauses)
        + " ORDER BY created_date DESC, created_time DESC LIMIT ?"
    )
    params.append(limit)
    rows = store.query(sql, tuple(params))
    scans = rows_as(ScanRow, rows, source="scans.list")
    payload = ScansListResponse(total=len(scans), scans=scans)
    return json_response(payload, etag)


@router.get("/api/scans/page")
def scans_page(
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The scans page in one answer: every scan with its text, its file
    entry and the id of its architecture form, plus the architecture rows
    and the agents the page names.

    The page used to read the list and then ask for each scan and each file
    entry on its own — 124 requests to open it, and 124 again whenever
    anything changed. One answer, one ETag.
    """
    from .deps import agents_by_id, detail_cached
    from .lenses import _file_paths

    etag = etag_for(f"scans:page:{limit}", store, "scans", "chats")
    if (r := maybe_304(request, etag)) is not None:
        return r
    rows = store.query(
        "SELECT * FROM scans ORDER BY created_date DESC, created_time DESC LIMIT ?",
        (limit,),
    )
    # Newest first and the first one seen stays: the same row the one-scan
    # answer picks with its ORDER BY … DESC LIMIT 1.
    files_by_scan: dict[str, dict[str, Any]] = {}
    for f in store.query("SELECT * FROM files_mutual ORDER BY created_date DESC, created_time DESC, id DESC"):
        files_by_scan.setdefault(str(f.get("trigger_id") or ""), f)
    arch_by_scan: dict[str, str] = {}
    for a in store.query(
        "SELECT id, trigger_id FROM architecture_mutual ORDER BY created_date DESC, created_time DESC, id DESC"
    ):
        arch_by_scan.setdefault(str(a.get("trigger_id") or ""), str(a.get("id") or ""))
    scans: list[dict[str, Any]] = []
    for row in rows:
        meta_rows = rows_as(ScanRow, [row], source="scans.page")
        if not meta_rows:
            continue
        meta = meta_rows[0]
        l2, l3, l4 = detail_cached(store.data_root, row.get("md_ref") or "")
        file_row = files_by_scan.get(meta.id)
        scans.append({
            "metadata": meta.model_dump(mode="json"), "l2": l2, "l3": l3, "l4": l4,
            "text": entry_fields.from_slots("scan", meta.l1, l2, l3, l4),
            "files_entry": str(file_row.get("id")) if file_row else None,
            "architecture_entry": arch_by_scan.get(meta.id) or None,
            "file": ({"metadata": file_row, **_file_paths(store, file_row)} if file_row else None),
        })
    architecture = store.query(
        "SELECT * FROM architecture_mutual ORDER BY created_date DESC, created_time DESC LIMIT 5000"
    )
    return json_response({
        "total": len(scans), "scans": scans, "architecture": architecture,
        "agents": list(agents_by_id(store).values()),
    }, etag)


@router.get("/api/scans/material")
def scans_material(
    request: Request,
    project: str = Query(...),
    agent_id: str = Query(""),
    store: ViewStore = Depends(get_store),
) -> dict:
    """What a scan is written from: the commits and files since the project's
    last scan, the counters counted, and how to write the three entries a
    scan is made of (scanlib.py). MCP: scan_material."""
    from pathlib import Path

    code = known_project(store, project)
    root = getattr(request.app.state, "prompt_root", None) or Path(__file__).resolve().parents[3]
    return {
        **scanlib.material(store, code, agent_id.strip()),
        "instructions": scanlib.instructions(Path(root)),
        "next": (
            'MCP tool write_entry {lens: "scan", fields: {summary, why, deltas, proof, '
            "...counters}}, then lens file, then lens architecture, each with the scan's id as trigger_id"
        ),
    }


SCAN_MUTABLE = ("files_n", "lines_add", "lines_del", "decisions_n", "scope")

# One sentence for a scan id that matches nothing — the update and detail
# routes used to carry their own copies of it.
_SCAN_NOT_FOUND = (
    "scan not found: {scan_id} — the id is in the scan's own answer; "
    "the latest one comes back from the MCP tool scan_material."
)


@router.post("/api/scans/{scan_id}/update")
def scans_update(
    scan_id: str,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """Correct a scan: its text by name (summary, why, deltas, proof) and its
    counters. Its id is minted from the summary and the minute, so "fix and
    write again" could not correct one: an unchanged summary returned the
    old row and a changed one minted a second scan. The same route shape as
    every other lens's update."""

    row = store.query_one("SELECT * FROM scans WHERE id = ?", (scan_id,))
    if row is None:
        raise HTTPException(
            status_code=404, detail=_SCAN_NOT_FOUND.format(scan_id=scan_id)
        )
    entry_fields.to_slots("scan", body, _SCAN_COLUMNS)
    text_keys = [k for k in ("l1", "l2", "l3", "l4") if k in body]
    counters = {k: body[k] for k in SCAN_MUTABLE if k in body}
    if not text_keys and not counters:
        raise HTTPException(status_code=422, detail=(
            "nothing to change: send the text by name (summary, why, deltas, proof) "
            "or a counter (files_n, lines_add, lines_del, decisions_n, scope)"))
    for k in ("files_n", "lines_add", "lines_del", "decisions_n"):
        if k in counters:
            try:
                counters[k] = int(counters[k])
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"{k} must be a whole number")

    def mutate(rows: list[dict[str, str]]) -> bool:
        target = next((r for r in rows if r.get("id") == scan_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail=f"scan not found in scans.csv: {scan_id}")
        if "l1" in body:
            target["l1"] = str(body["l1"])
        for k, v in counters.items():
            target[k] = str(v)
        return True

    rewrite_rows(store.scans_csv_path, _SCAN_COLUMNS, mutate)
    md_path = resolve_under(store.data_root, str(row.get("md_ref") or ""))
    if md_path is not None:
        l2, l3, l4 = "", [], ""
        try:
            l2, l3, l4 = parse_sections(md_path.read_text(encoding="utf-8"))
        except OSError:
            pass
        merged = ScanCreate(**{
            **{k: row.get(k) for k in ("created_date", "created_time", "project", "agent_id", "scope")},
            **{k: int(row.get(k) or 0) for k in ("files_n", "lines_add", "lines_del", "decisions_n")},
            "l1": str(body.get("l1", row.get("l1") or "")),
            **counters,
            "l2": str(body.get("l2", l2)), "l3": list(body.get("l3", l3) or []), "l4": str(body.get("l4", l4)),
        })
        atomic_write(md_path, _build_scan_md(merged, scan_id))
    store.rebuild()
    fresh = store.query_one("SELECT * FROM scans WHERE id = ?", (scan_id,)) or row
    l2, l3, l4 = "", [], ""
    if md_path is not None:
        l2, l3, l4 = parse_sections(md_path.read_text(encoding="utf-8"))
    return {"metadata": clean(fresh), "text": entry_fields.from_slots("scan", str(fresh.get("l1") or ""), l2, l3, l4, _SCAN_COLUMNS),
            "changed": sorted(text_keys + list(counters))}


@router.get("/api/scans/{scan_id}", response_model=ScanDetail)
def scans_detail(
    scan_id: str,
    request: Request,
    store: ViewStore = Depends(get_store),
) -> Response:
    etag = etag_for(f"scans:{scan_id}", store, "scans")
    if (r := maybe_304(request, etag)) is not None:
        return r

    row = store.query_one("SELECT * FROM scans WHERE id = ?", (scan_id,))
    if row is None:
        raise HTTPException(
            status_code=404, detail=_SCAN_NOT_FOUND.format(scan_id=scan_id)
        )

    md_path = resolve_under(store.data_root, row.get("md_ref") or "")
    l2, l3, l4 = "", [], ""
    if md_path is not None and md_path.exists():
        try:
            l2, l3, l4 = parse_sections(md_path.read_text(encoding="utf-8"))
        except OSError:
            pass

    meta_rows = rows_as(ScanRow, [row], source="scans.detail")
    if not meta_rows:
        raise HTTPException(
            status_code=409,
            detail=f"Scan {scan_id} exists but cannot be read. Run the data check (/api/doctor).",
        )
    payload = ScanDetail(
        metadata=meta_rows[0], l2=l2, l3=l3, l4=l4,
        files_entry=_files_entry_for(store, scan_id),
        architecture_entry=_architecture_entry_for(store, scan_id),
    )
    payload.text = entry_fields.from_slots("scan", payload.metadata.l1, l2, l3, l4)
    return json_response(payload, etag)


@router.post("/api/scans", response_model=ScanDetail, status_code=201)
def scans_create(
    response: Response,
    raw: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> ScanDetail:
    # A scan is written by name like every entry (entry_fields.py): summary,
    # why, deltas, proof. The names land in the storage slots first.
    try:
        body = ScanCreate(**entry_fields.to_slots("scan", dict(raw)))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_scan_errors(exc))
    sid = _mint_scan_id(body)
    existing = store.query_one("SELECT * FROM scans WHERE id = ?", (sid,))
    if existing is not None:
        return _repeat(store, existing, response)

    date_part = safe_ref_part(body.created_date, "nodate")
    hhmm = safe_ref_part(body.created_time.replace(":", ""), "0000")
    proj_slug = safe_ref_part(body.project.lower())
    agent_part = safe_ref_part(body.agent_id)
    # The id keeps the path unique: two scans by one agent in one minute
    # shared a file, and the second replaced the first one's text.
    md_ref = f"snapshots/{date_part}-{hhmm}__{proj_slug}__{agent_part}__{sid}.md"

    md_path = store.data_root / md_ref
    md_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(md_path, _build_scan_md(body, sid))

    row = {
        "id": sid,
        "created_date": body.created_date,
        "created_time": body.created_time,
        "project": body.project,
        "agent_id": body.agent_id,
        "l1": body.l1,
        "files_n": body.files_n,
        "lines_add": body.lines_add,
        "lines_del": body.lines_del,
        "decisions_n": body.decisions_n,
        "scope": (body.scope or "")[:60],
        "md_ref": md_ref,
    }
    # Looked for again and written in one locked step: identical posts at
    # once all passed the look above and wrote one row each, same id.
    raced = append_if_absent(store.scans_csv_path, _SCAN_COLUMNS, row)
    if raced is not None:
        store.rebuild()  # the view, not the file's strings, answers
        return _repeat(store, store.query_one("SELECT * FROM scans WHERE id = ?", (sid,)) or raced, response)

    store.rebuild()
    stored = store.query_one("SELECT * FROM scans WHERE id = ?", (sid,))
    if stored is None:
        raise HTTPException(
            status_code=500,
            detail="The scan was saved, but the list does not show it yet.",
        )
    scanlib.mark(store, sid, body.project, body.agent_id)
    return _with_files_link(
        store,
        ScanDetail(
            metadata=ScanRow(**clean(stored)), l2=body.l2, l3=list(body.l3), l4=body.l4
        ),
    )


def _repeat(store: ViewStore, existing: dict[str, Any], response: Response) -> ScanDetail:
    """The answer to a scan that is already there: 200, nothing written."""
    md_path = resolve_under(store.data_root, existing.get("md_ref") or "")
    l2, l3, l4 = "", [], ""
    if md_path is not None and md_path.exists():
        try:
            l2, l3, l4 = parse_sections(md_path.read_text(encoding="utf-8"))
        except OSError:
            pass
    response.status_code = 200      # a repeat: nothing new was written
    return _with_files_link(
        store, ScanDetail(metadata=ScanRow(**clean(existing)), l2=l2, l3=l3, l4=l4, existing=True)
    )


def _files_entry_for(store: ViewStore, scan_id: str) -> str | None:
    row = store.query_one(
        "SELECT id FROM files_mutual WHERE trigger_id = ? "
        "ORDER BY created_date DESC, created_time DESC, id DESC LIMIT 1",
        (scan_id,),
    )
    return str(row["id"]) if row and row.get("id") else None


def _architecture_entry_for(store: ViewStore, scan_id: str) -> str | None:
    row = store.query_one(
        "SELECT id FROM architecture_mutual WHERE trigger_id = ? "
        "ORDER BY created_date DESC, created_time DESC, id DESC LIMIT 1",
        (scan_id,),
    )
    return str(row["id"]) if row and row.get("id") else None


def _with_files_link(store: ViewStore, payload: ScanDetail) -> ScanDetail:
    """Attach the triggered file entry — or the reminder that it is owed.

    A scan is complete only with its file entry (the agent's per-path
    judgment); the reminder rides on the response because that is the
    moment the agent is looking.
    """
    payload.text = entry_fields.from_slots(
        "scan", payload.metadata.l1, payload.l2, payload.l3, payload.l4)
    sid = payload.metadata.id
    payload.files_entry = _files_entry_for(store, sid)
    payload.architecture_entry = _architecture_entry_for(store, sid)
    warnings: list[str] = []
    if payload.files_entry is None:
        warnings.append(
            f"No file entry yet for this scan — MCP tool write_entry, lens file, with "
            f"trigger_lens \"scan\", trigger_id \"{sid}\" and a paths list "
            "(one record per file you modified: importance, blast_radius, "
            "test_coverage, why). See SLIGHTLY-PARALLEL.md §4."
        )
    if payload.architecture_entry is None:
        warnings.append(
            f"No architecture answer for this scan — MCP tool write_entry, "
            f"lens architecture, with trigger_id \"{sid}\": the form of eight groups (does · "
            "owes · runs · stores · talks · built with · faces · holds), "
            "each group in `checked` or with its changes listed. All eight "
            "checked with no changes is a valid answer. See SLIGHTLY-PARALLEL.md §4."
        )
    payload.warnings = warnings
    return payload
