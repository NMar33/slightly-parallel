"""The architecture ledger — what each scan did to the shape of the system.

One question, answered with a fixed form at every scan: which entities were
added, changed or removed. The vocabulary is small and closed — eight groups,
twenty-four types, a few fields each — so the answer is stable across
projects and models. There is no init and no maintained map: the ledger is
the stream of answers, and the operator screens a scan by its rows.

``POST /api/architecture`` takes the whole form (``checked`` + ``changes``)
and writes one CSV row per change plus one check-receipt row (op ``check``)
that records which groups were looked at — the receipt is what closes the
scan and hook reminders when nothing changed. ``GET /api/architecture/state``
returns the scans with their answers, the counts, and the standing ``owes``
(debt and action-needed rows nothing later removed).

Registered before the generic lens router, so this POST shadows the generic
create and the literal ``state`` segment wins over ``/api/architecture/{id}``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from ..csvio import append_if_absent
from ..db import ViewStore
from ..entities import ENTITIES
from ..file_entries import project_path
from .deps import (
    create_answer, etag_for, get_store, identity_of, iso_moment, json_response,
    known_project, maybe_304, not_found,
)

router = APIRouter()

from ..archvocab import GROUPS, OPS, TYPE_GROUP  # the one vocabulary table


# Fields a type must carry (422 without) …
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "debt": ("risk",),
    "action-needed": ("action",),
    "runtime": ("version",),
    "database": ("engine",),
    "endpoint": ("method",),
    "integration": ("direction",),
    "hook": ("host",),
    "surface": ("route",),
    "rule": ("check",),
    "tests": ("command",),
}

# … and the fields it may carry (anything else is ignored, with a warning).
EXTRA_FIELDS: dict[str, tuple[str, ...]] = {
    "feature": ("surface", "endpoint"),
    "fix": ("surface", "endpoint"),
    "debt": ("risk",),
    "action-needed": ("action", "by_when"),
    "service": ("start", "port"),
    "runtime": ("version",),
    "config": ("read_in", "default"),
    "deploy": ("command",),
    "database": ("engine", "tables"),
    "files": ("format", "writer"),
    "cache": ("from", "rebuilt"),
    "queue": ("producer", "consumer"),
    "endpoint": ("method", "route", "service"),
    "integration": ("direction", "auth"),
    "hook": ("host", "event"),
    "command": ("usage",),
    "framework": ("version",),
    "library": ("version", "why"),
    "module": ("owns", "depends_on"),
    "surface": ("route", "service"),
    "auth": ("mechanism", "checked_in"),
    "job": ("schedule", "trigger"),
    "rule": ("enforced_in", "check"),
    "tests": ("command", "covers"),
}

# Types whose subject may have no file behind it (an operator step, a risk).
PATH_OPTIONAL = frozenset({"debt", "action-needed"})

PATH_MAX = 5

_ENT = ENTITIES["architecture"]


def _mint(project: str, trigger_id: str, op: str, type_: str, name: str) -> str:
    key = "|".join((project, trigger_id, op, type_, name))
    return "ar_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _mint_check(body: dict, checked: list[str]) -> str:
    key = "|".join((
        str(body.get("project") or ""), str(body.get("agent_id") or ""),
        str(body.get("trigger_id") or ""), "check", ",".join(checked),
        str(body.get("created_date") or ""), str(body.get("created_time") or ""),
    ))
    return "ar_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _fail(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


# ---------------------------------------------------------------------------
# Path anchors — every claim points at code that must exist.
# ---------------------------------------------------------------------------


def _split_symbol(entry: str) -> tuple[str, str]:
    """``file.py:Symbol`` → (file.py, Symbol); no colon → (entry, '')."""
    if ":" in entry:
        head, _, sym = entry.rpartition(":")
        if head and sym and "/" not in sym:
            return head, sym
    return entry, ""


def _check_path_entry(folder: Path, entry: str) -> str | None:
    """One anchor against the registered folder. Returns an error, or None."""
    rel, sym = _split_symbol(entry)
    rel = rel.strip().rstrip("/")
    if not rel:
        return f"empty path entry {entry!r}"
    if rel.startswith("/") or rel.startswith("~") or ".." in rel.split("/"):
        return f"path {entry!r} must be relative to the project folder, without '..'"
    target = folder / rel
    if not target.exists():
        return f"path {entry!r} not found in the project folder"
    if sym and target.is_file():
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if re.search(rf"\b{re.escape(sym)}\b", text) is None:
            return f"symbol {sym!r} not found in {rel}"
    return None


def _validate_paths(
    folder: Path | None, type_: str, name: str, raw: Any
) -> list[str]:
    if raw in (None, "", []):
        if type_ in PATH_OPTIONAL:
            return []
        raise _fail(
            f"changes[{type_} {name!r}] needs `path` — 1–{PATH_MAX} repo-relative "
            "entries (a file, a folder, or file:Symbol)"
        )
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        raise _fail(f"changes[{type_} {name!r}].path must be a list of strings")
    entries = [p.strip() for p in raw if p.strip()]
    if not entries or len(entries) > PATH_MAX:
        raise _fail(
            f"changes[{type_} {name!r}].path takes 1–{PATH_MAX} entries, got {len(entries)}"
        )
    if folder is None:
        return entries
    problems = [e for p in entries if (e := _check_path_entry(folder, p))]
    if problems:
        raise _fail(f"changes[{type_} {name!r}]: " + "; ".join(problems))
    return entries


# ---------------------------------------------------------------------------
# POST /api/architecture — the form, once per scan.
# ---------------------------------------------------------------------------


@router.post("/api/architecture", status_code=201)
def architecture_form(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """One answer to "what did you do to the shape?" — see SLIGHTLY-PARALLEL.md §4."""
    if not isinstance(body, dict):
        raise _fail("body must be a JSON object")
    for req in ("project", "agent_id", "created_date", "created_time"):
        if not str(body.get(req) or "").strip():
            raise _fail(f"architecture form needs `{req}`")
    project = str(body["project"]).strip()

    checked_raw = body.get("checked") or []
    if not isinstance(checked_raw, list):
        raise _fail("`checked` must be a list of group names")
    checked = [str(g).strip() for g in checked_raw if str(g).strip()]
    unknown_groups = [g for g in checked if g not in GROUPS]
    if unknown_groups:
        raise _fail(
            f"unknown group(s) in `checked`: {', '.join(unknown_groups)} — "
            f"groups are: {', '.join(GROUPS)}"
        )

    changes_raw = body.get("changes")
    if changes_raw is None:
        changes_raw = []
    if not isinstance(changes_raw, list):
        raise _fail("`changes` must be a list")

    trigger_id = str(body.get("trigger_id") or "").strip()
    trigger_lens = str(body.get("trigger_lens") or ("scan" if trigger_id else "")).strip()

    folder = project_path(store, project)
    warnings: list[str] = []
    rows: list[dict] = []
    seen_ids: set[str] = set()
    changed_groups: set[str] = set()

    for i, ch in enumerate(changes_raw):
        if not isinstance(ch, dict):
            raise _fail(f"changes[{i}] must be an object")
        op = str(ch.get("op") or "").strip()
        if op not in OPS:
            raise _fail(
                f"changes[{i}].op {op!r} is not one of: {', '.join(OPS)}"
            )
        type_ = str(ch.get("type") or "").strip()
        if type_ not in TYPE_GROUP:
            raise _fail(
                f"changes[{i}].type {type_!r} is not a known entity type — "
                + "; ".join(f"{g}: {', '.join(ts)}" for g, ts in GROUPS.items())
            )
        name = str(ch.get("name") or "").strip()
        if not name:
            raise _fail(f"changes[{i}] ({type_}) needs a `name`")
        missing = [
            f for f in REQUIRED_FIELDS.get(type_, ())
            if op != "remove" and not str(ch.get(f) or "").strip()
        ]
        if missing:
            raise _fail(
                f"changes[{i}] ({type_} {name!r}) is missing required "
                f"field(s): {', '.join(missing)}"
            )
        # A removed thing may be gone from the repo — its path is neither
        # required nor checked; whatever was sent is kept as the record.
        if op == "remove":
            raw_path = ch.get("path")
            if isinstance(raw_path, str):
                raw_path = [raw_path]
            entries = [str(p).strip() for p in raw_path or [] if str(p).strip()][:PATH_MAX]
        else:
            entries = _validate_paths(folder, type_, name, ch.get("path"))

        allowed = EXTRA_FIELDS.get(type_, ())
        fields = {
            f: str(ch[f]).strip()
            for f in allowed
            if str(ch.get(f) or "").strip()
        }
        core = {"op", "type", "name", "path", "note", "task", "decision"}
        ignored = [
            k for k in ch
            if k not in core and k not in allowed and str(ch.get(k) or "").strip()
        ]
        if ignored:
            warnings.append(
                f"changes[{i}] ({type_} {name!r}): ignored field(s) "
                f"{', '.join(sorted(ignored))} — {type_} takes: "
                + ", ".join(("name", "path", "note") + tuple(allowed))
            )

        rid = _mint(project, trigger_id, op, type_, name)
        if rid in seen_ids:
            warnings.append(f"changes[{i}] ({op} {type_} {name!r}) repeats an earlier change — kept once")
            continue
        seen_ids.add(rid)
        changed_groups.add(TYPE_GROUP[type_])
        rows.append({
            "id": rid,
            "created_date": body["created_date"],
            "created_time": body["created_time"],
            "project": project,
            "agent_id": body["agent_id"],
            "name": name,
            "op": op,
            "type": type_,
            "path": json.dumps(entries) if entries else "",
            "note": str(ch.get("note") or "").strip(),
            "fields": json.dumps(fields) if fields else "",
            "task": str(ch.get("task") or "").strip(),
            "decision": str(ch.get("decision") or "").strip(),
            "trigger_lens": trigger_lens,
            "trigger_id": trigger_id,
            "md_ref": "",
        })

    missing_groups = [g for g in GROUPS if g not in changed_groups and g not in checked]
    if missing_groups:
        raise _fail(
            "every group must be in `checked` or have changes — not answered: "
            + ", ".join(missing_groups)
        )

    # The check receipt: which groups were looked at. It is what closes the
    # scan/hook reminder when nothing changed, and the screening's "no".
    check_id = _mint_check(body, checked)
    receipt = {
        "id": check_id,
        "created_date": body["created_date"],
        "created_time": body["created_time"],
        "project": project,
        "agent_id": body["agent_id"],
        "name": "checked: " + (", ".join(checked) if checked else "(every group changed)"),
        "op": "check",
        "type": "",
        "path": "",
        "note": "",
        "fields": json.dumps({"checked": checked}),
        "task": "",
        "decision": "",
        "trigger_lens": trigger_lens,
        "trigger_id": trigger_id,
        "md_ref": "",
    }

    csv_path = store.data_root / _ENT.csv
    posted, skipped = 0, 0
    for row in rows + [receipt]:
        # Looked for and written in one locked step (csvio.append_if_absent).
        if append_if_absent(csv_path, _ENT.columns, row) is not None:
            skipped += 1
            continue
        posted += 1

    if posted:
        store.rebuild()
        probe = store.query_one(
            f"SELECT id FROM {_ENT.view} WHERE id = ?", (receipt["id"],)
        )
        if probe is None:
            raise HTTPException(
                status_code=500,
                detail="architecture rows were written but are not visible in the view",
            )

    # The one rule for a repeated create: nothing new written → 200 and
    # `existing: true`; something written → 201.
    if not posted:
        response.status_code = 200
    return {
        # `existing` here is the whole post's verdict: nothing new written.
        "existing": not posted,
        "warnings": warnings,
        "posted": posted,
        "skipped": skipped,
        "ids": [r["id"] for r in rows],
        "check_id": check_id,
        "checked": checked,
        "trigger_id": trigger_id,
    }


# ---------------------------------------------------------------------------
# GET /api/architecture/state — the scans, screened.
# ---------------------------------------------------------------------------


def _loads(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        v = json.loads(str(raw))
    except (ValueError, TypeError):
        return default
    return v if isinstance(v, type(default)) else default


def _serialize(r: dict[str, Any]) -> dict[str, Any]:
    type_ = str(r.get("type") or "")
    return {
        "id": str(r.get("id") or ""),
        "created_date": str(r.get("created_date") or ""),
        "created_time": str(r.get("created_time") or ""),
        "agent_id": str(r.get("agent_id") or ""),
        "op": str(r.get("op") or ""),
        "type": type_,
        "group": TYPE_GROUP.get(type_, ""),
        "name": str(r.get("name") or ""),
        "path": _loads(r.get("path"), []),
        "note": str(r.get("note") or ""),
        "task": str(r.get("task") or ""),
        "decision": str(r.get("decision") or ""),
        "fields": _loads(r.get("fields"), {}),
        "trigger_id": str(r.get("trigger_id") or ""),
    }


def _sort_key(r: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(r.get("created_date") or ""),
        str(r.get("created_time") or ""),
        str(r.get("id") or ""),
    )


def _standing_owes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Debt and action-needed rows whose last word was not ``remove``."""
    last: dict[tuple[str, str], dict[str, Any]] = {}
    for r in sorted(changes, key=_sort_key):
        if r["type"] in GROUPS["owes"]:
            last[(r["type"], r["name"])] = r
    return [r for r in last.values() if r["op"] != "remove"]


@router.get("/api/architecture/state")
def architecture_state(
    request: Request,
    project: str = Query(...),
    limit: int = Query(60, ge=1, le=500),
    store: ViewStore = Depends(get_store),
) -> Response:
    """The screening: scans newest first, each with its answer.

    Returns ``{project, scans, loose, counts, owes, total_changes}``.
    Each scan carries ``changes`` (its rows), ``checked`` (the groups its
    receipt named) and ``answered``; a scan with neither owes the form.
    ``loose`` holds changes posted without a scan; ``owes`` the standing
    debt and action-needed rows; ``counts`` the type and op totals.
    """
    etag = etag_for(f"architecture:state:{project}:{limit}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    raw = store.query(
        f"SELECT * FROM {_ENT.view} WHERE project = ?", (project,)
    )
    checks = [r for r in raw if str(r.get("op") or "") == "check"]
    changes = [_serialize(r) for r in sorted(
        (r for r in raw if str(r.get("op") or "") != "check"),
        key=_sort_key,
    )]

    checked_by_scan: dict[str, list[str]] = {}
    for c in sorted(checks, key=_sort_key):
        sid = str(c.get("trigger_id") or "")
        checked_by_scan[sid] = _loads(c.get("fields"), {}).get("checked", [])

    scan_rows = store.query(
        "SELECT id, created_date, created_time, agent_id, l1 FROM scans "
        "WHERE project = ? ORDER BY created_date DESC, created_time DESC LIMIT ?",
        (project, limit),
    )
    scan_ids = {str(s.get("id") or "") for s in scan_rows}
    scans = []
    for s in scan_rows:
        sid = str(s.get("id") or "")
        mine = [c for c in changes if c["trigger_id"] == sid]
        checked = checked_by_scan.get(sid)
        scans.append({
            "id": sid,
            "date": str(s.get("created_date") or ""),
            "time": str(s.get("created_time") or ""),
            "agent_id": str(s.get("agent_id") or ""),
            "l1": str(s.get("l1") or ""),
            "changes": mine,
            "checked": checked or [],
            "answered": bool(mine) or checked is not None,
        })

    loose = [c for c in changes if c["trigger_id"] not in scan_ids]

    types = Counter(c["type"] for c in changes)
    ops = Counter(c["op"] for c in changes)

    payload = {
        "project": project,
        "groups": {g: list(ts) for g, ts in GROUPS.items()},
        "scans": scans,
        "loose": list(reversed(loose)),
        "counts": {
            "types": [{"type": t, "n": n} for t, n in types.most_common()],
            "ops": [{"op": o, "n": n} for o, n in ops.most_common()],
        },
        "owes": _standing_owes(changes),
        "total_changes": len(changes),
    }
    return json_response(payload, etag)


# ---------------------------------------------------------------------------
# The architecture page — what the project is, as claims with their evidence.
# The ledger above is the log of changes; the page is the picture (archpage.py).
# ---------------------------------------------------------------------------




@router.get("/api/architecture/page")
def architecture_page_get(
    project: str = Query(...),
    version: int | None = Query(None, ge=1),
    store: ViewStore = Depends(get_store),
) -> dict:
    """The current page (or one version): its text, its sections with each
    claim parsed and checked against the folder, and the computed facts."""
    from .. import archpage, projectfacts

    code = known_project(store, project)
    listed = archpage.versions(store, code)
    page = archpage.current(store, code)
    if version is not None and listed:
        hit = next((v for v in listed if v["n"] == version), None)
        if hit is None:
            raise not_found("version", str(version))
        sections = archpage.parse(hit["_body"])
        page = {**{k: v for k, v in hit.items() if k != "_body"}, "text": hit["_body"], "sections": sections,
                "counts": archpage.check(store, code, sections, hit["at"])}
    return {
        "project": code,
        "page": page,
        "versions": [{k: v for k, v in v_.items() if k != "_body"} for v_ in listed],
        "facts": projectfacts.facts(store, code),
        "word_budget": archpage.WORD_BUDGET,
    }


@router.get("/api/architecture/page/material")
def architecture_page_material(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """What the next version is written from. MCP: architecture_material."""
    from .. import archpage, projectfacts

    code = known_project(store, project)
    page = archpage.current(store, code)
    flagged = [
        {"claim": c["text"][:120], "where": c.get("path", ""),
         "problem": "not found in the folder" if c.get("path_found") is False else f"changed {c['changed_since']}"}
        for sec in (page or {}).get("sections", []) for c in sec["claims"]
        if c.get("path_found") is False or c.get("changed_since")
    ]
    root = getattr(request.app.state, "prompt_root", None) or Path(__file__).resolve().parents[3]
    return {
        "project": code,
        "facts": projectfacts.facts(store, code),
        "current_page": ({"n": page["n"], "at": page["at"], "text": page["text"]} if page else None),
        "check_again": flagged[:40],
        "instructions": archpage.instructions(Path(root)),
        "next": "MCP tool architecture_page {text: <the whole next version, markdown>, note: <one line on what changed>}",
    }


@router.post("/api/architecture/page", status_code=201)
def architecture_page_write(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{project, agent_id, text, note?}`` — the whole next version."""
    from .. import archpage

    code = known_project(store, body.get("project"))
    who = identity_of(body)
    if not who:
        raise HTTPException(status_code=422, detail="agent_id is required")
    try:
        out = archpage.write(store, code, who, str(body.get("text") or ""), str(body.get("note") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return create_answer({"project": code, **out}, response,
                         existing=bool(out.get("existing")),
                         warnings=out.get("warnings"))


# ---------------------------------------------------------------------------
# The map of the program — every part as a row, and what connects to what
# (repomap.py). For projects that are programs.
# ---------------------------------------------------------------------------


@router.get("/api/map")
def map_get(
    project: str = Query(...),
    version: int | None = Query(None, ge=1),
    store: ViewStore = Depends(get_store),
) -> dict:
    """The current map (or one version): rows, relations, notes, what came
    and went since the version before, and what is wrong with it now."""
    from .. import repomap

    code = known_project(store, project)
    listed = repomap.versions(store, code)
    cur = repomap.current(store, code)
    if version is not None and listed:
        hit = next((v for v in listed if v["n"] == version), None)
        if hit is None:
            raise not_found("version", str(version))
        cur = {**{k: v for k, v in hit.items() if k != "_map"}, "map": hit["_map"], "changes": {"added": [], "removed": []},
               "problems": repomap.check(store, code, hit["_map"]), "by_kind": repomap._by_kind(hit["_map"])}
    return {"project": code, "map": cur, "versions": [{k: v for k, v in v_.items() if k != "_map"} for v_ in listed],
            "kinds": list(repomap.KINDS), "verbs": list(repomap.VERBS), "templates": {k: list(v) for k, v in repomap.TEMPLATES.items()},
            "facts": repomap.facts(store, code)}


@router.get("/api/architecture/status")
def architecture_status(
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """What `#architecture` has to do. MCP: architecture_status.

    Three parts, each ``needed`` or not, with the reason in words:
    the form for the last scan (missing?), the page (a scan newer than its
    last version?), the map (the program's shape changed since it was
    written — or, for a map from before shapes were kept, a scan newer
    than it). The skill update-the-architecture does only what is needed.
    """
    from .. import archpage, repomap

    code = known_project(store, project)
    scan = store.query_one(
        "SELECT id, created_date, created_time FROM scans WHERE project = ? "
        "ORDER BY created_date DESC, created_time DESC, id DESC LIMIT 1",
        (code,),
    )
    scan_at = iso_moment(scan["created_date"], scan["created_time"]) if scan else ""

    if not scan:
        form = {"needed": False, "why": "no scan yet: #scan makes the first, with its form"}
    else:
        has = store.query_one("SELECT id FROM architecture_mutual WHERE trigger_id = ? LIMIT 1", (scan["id"],))
        form = ({"needed": False, "why": f"the last scan {scan['id']} has its form", "scan_id": scan["id"]} if has
                else {"needed": True, "why": f"the last scan {scan['id']} has no form", "scan_id": scan["id"]})

    page_cur = archpage.current(store, code)
    if page_cur is None:
        page = {"needed": True, "why": "there is no page yet", "version": 0}
    elif scan_at and scan_at > str(page_cur["at"]):
        page = {"needed": True, "why": f"a scan ({scan_at[:16]}) is newer than page v{page_cur['n']} ({str(page_cur['at'])[:16]})", "version": page_cur["n"]}
    else:
        page = {"needed": False, "why": f"page v{page_cur['n']} is newer than the last scan", "version": page_cur["n"]}

    facts = repomap.facts(store, code)
    now_shape = repomap.shape_print(facts)
    listed = repomap.versions(store, code)
    last = listed[-1] if listed else None
    if not now_shape:
        mp = {"needed": False, "why": "no folder is registered for this project, so there is nothing to map", "version": last["n"] if last else 0}
    elif last is None:
        mp = {"needed": True, "why": "there is no map yet", "version": 0}
    elif last.get("shape"):
        mp = ({"needed": False, "why": f"the program's shape is the one map v{last['n']} was written against", "version": last["n"]}
              if last["shape"] == now_shape else
              {"needed": True, "why": f"the program's shape changed since map v{last['n']} (folders, manifests, dependencies, services, tests, variables or ports)", "version": last["n"]})
    elif scan_at and scan_at > str(last["at"]):
        mp = {"needed": True, "why": f"a scan is newer than map v{last['n']}, which does not record the shape it was written against", "version": last["n"]}
    else:
        mp = {"needed": False, "why": f"map v{last['n']} is newer than the last scan", "version": last["n"]}
    return {"project": code, "form": form, "page": page, "map": mp,
            "next": "the skill update-the-architecture: do the needed parts in order — form, page, map"}


@router.get("/api/map/material")
def map_material(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """What the next map is written from. MCP: map_material."""
    from .. import app_settings, repomap

    code = known_project(store, project)
    cur = repomap.current(store, code)
    root = getattr(request.app.state, "prompt_root", None) or Path(__file__).resolve().parents[3]
    values = app_settings.load(store.data_root)
    return {
        "project": code,
        "model": str(values.get("map.model") or "opus"),
        "facts": repomap.facts(store, code),
        "current_map": ({"n": cur["n"], "at": cur["at"], "map": cur["map"], "problems": cur["problems"]} if cur else None),
        "kinds": list(repomap.KINDS), "verbs": list(repomap.VERBS),
        "templates": {k: list(v) for k, v in repomap.TEMPLATES.items()},
        "instructions": repomap.instructions(Path(root)),
        "next": "MCP tool map_write {map: {template, rows, relations, notes}, note: <one line on what changed>}",
    }


@router.post("/api/map", status_code=201)
def map_write(
    response: Response,
    body: dict = Body(...),
    store: ViewStore = Depends(get_store),
) -> dict:
    """``{project, agent_id, map, note?}`` — the whole next version."""
    from .. import repomap

    code = known_project(store, body.get("project"))
    who = identity_of(body)
    if not who:
        raise HTTPException(status_code=422, detail="agent_id is required")
    out = repomap.write(store, code, who, body.get("map"), str(body.get("note") or ""))
    return create_answer({"project": code, **out}, response, existing=bool(out.get("existing")), warnings=out.get("warnings"))

