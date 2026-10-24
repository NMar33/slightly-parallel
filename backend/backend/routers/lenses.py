"""Generic list / detail / create endpoints for every registered entity.

One declarative table per concern replaces the former per-entity copy-paste:

- ``FILTERS``   — which query params each entity's list endpoint accepts and
                  the SQL clause each one binds.
- ``ORDER_BY``  — the list ordering per entity.
- ``ENRICHERS`` — extra payload merged into a detail response (goal children,
                  sprint goals, library body).
- ``PRE_CREATE``— server-side defaults applied before a create is persisted.

Adding an entity to ``entities.ENTITIES`` automatically provides
``GET /api/<base>``, ``GET /api/<base>/{id}`` and ``POST /api/<base>``.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from .. import archpage, artifactlib, donelib, entry_fields, frontmatter, keeplib, nowlib, skilllib, repomap, undolib
from ..csvio import rewrite_rows
from ..db import ViewStore
from ..docs_md import build_detail, read_detail, resolve_under
from ..turns import description_of, parse_task_doc
from ..entities import ENTITIES, Entity
from ..file_safety import atomic_write
from .deps import (
    adopt_when_changed, detail_cached, etag_for, frontmatter_cached,
    get_store, json_response, maybe_304, parsed_file, refuse_agent, written_by_agent,
)
from .integrate import sync_all_rules

# Creating an entry — the gate, the per-lens preparation, the advisory
# checks, the id and the detail document — lives in entitylib.py; the
# libraries that write (timeauto, the task gate) call it without a router.
from ..entitylib import (  # noqa: E402,F401
    CONTRACT_CHECKS, OPERATOR_ONLY, PRE_CREATE, create_entity, detail_ref, doc_path, mint_id, named_text,
    refuse_agent_write, task_membership,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Declarative configuration
# ---------------------------------------------------------------------------

# (query param, accepted aliases, SQL clause). "?" count must match `repeat`.
FilterSpec = tuple[str, tuple[str, ...], str, dict[str, Any]]


def _f(
    param: str,
    clause: str,
    *aliases: str,
    like: bool = False,
    lower: bool = False,
    repeat: int = 1,
    flag: bool = False,
) -> FilterSpec:
    return (
        param,
        aliases,
        clause,
        {"like": like, "lower": lower, "repeat": repeat, "flag": flag},
    )


_PROJECT = _f("project", "project = ?")
_AGENT = _f("agent_id", "agent_id = ?", "agent")
_FROM = _f("from_date", "created_date >= ?", "from")
_TO = _f("to_date", "created_date <= ?", "to")
_COMMON = (_PROJECT, _AGENT, _FROM, _TO)
# `tags` is a comma-separated membership list (ui,backend): a tag matches
# a whole member, never a substring of another tag.
_TAG = _f("tag", "list_contains(string_split(COALESCE(tags, ''), ','), ?)")
# The library's tags are written with commas or with spaces (the prompt
# library joins them with spaces): a whole member either way.
_LIB_TAG = _f("tag", "list_contains(regexp_split_to_array(COALESCE(tags, ''), '[,\\s]+'), ?)")

FILTERS: dict[str, tuple[FilterSpec, ...]] = {
    "standup": _COMMON,
    "goal": _COMMON + (
        _f("status", "status = ?"),
        _f("parent_goal_id", "parent_goal_id = ?"),
        _f("sprint_id", "sprint_id = ?"),
        _f("root_only", "(parent_goal_id IS NULL OR parent_goal_id = '')", flag=True),
    ),
    "activity": _COMMON + (
        _f("goal_id", "goal_id = ?"),
        _f("activity_type", "activity_type = ?"),
        _f("min_duration", "duration_min >= ?"),
        _f("max_duration", "duration_min <= ?"),
    ),
    "decision": _COMMON + (
        _f("source", "source LIKE ?", like=True),
        _f("related_goal_id", "related_goal_id = ?"),
    ),
    "vision": _COMMON + (
        _TAG,
        _f("category", "category = ?"),
        _f("impact", "impact = ?"),
        _f("search", "(LOWER(l1) LIKE ? OR LOWER(category) LIKE ?)",
           like=True, lower=True, repeat=2),
    ),
    "entrypoint": _COMMON + (
        _TAG,
        _f("status", "status = ?"),
        _f("search", "(LOWER(l1) LIKE ? OR LOWER(topic) LIKE ?)",
           like=True, lower=True, repeat=2),
    ),
    "problem": _COMMON + (
        _TAG,
        _f("severity", "severity = ?"),
        _f("status", "status = ?"),
        _f("search", "(LOWER(l1) LIKE ? OR LOWER(severity) LIKE ?)",
           like=True, lower=True, repeat=2),
    ),
    "rule": _COMMON + (
        _TAG,
        _f("auto", "auto = ?"),
        _f("kind", "kind = ?"),
        # "importance" is the historical name some clients still send.
        _f("severity", "severity = ?", "importance"),
        _f("status", "status = ?"),
    ),
    "sprint": (
        _f("status", "status = ?"),
        # `projects` is a comma-separated membership column: a whole code,
        # so `p1` never reads the sprints of `p10`.
        _f("project",
           "(list_contains(string_split(REPLACE(COALESCE(projects, ''), ' ', ''), ','), ?) "
           "OR COALESCE(projects, '') = '')"),
        _f("from_date", "started_date >= ?", "from"),
        _f("to_date", "(ended_date <= ? OR ended_date IS NULL OR ended_date = '')", "to"),
    ),
    "file": _COMMON + (_f("trigger_lens", "trigger_lens = ?"),),
    "idea": _COMMON + (_LIB_TAG,),
    "note": _COMMON + (_LIB_TAG,),
    "prompt": _COMMON + (_LIB_TAG,),
    "task": (
        # A task lives in its home `project` and may be a member of more
        # (`projects`, comma-separated) — a project's board shows both.
        _f("project",
           "(project = ? OR list_contains(string_split(COALESCE(projects, ''), ','), ?))",
           repeat=2),
        _AGENT,
        _f("status", "status = ?"),
        _f("assignee", "assignee = ?"),
        _f("priority", "priority = ?"),
        _f("lane", "lane = ?"),
    ),
    "time_entry": _COMMON + (
        _f("goal_id", "goal_id = ?"),
        _f("sprint_id", "sprint_id = ?"),
        _f("running", "(ended_at IS NULL OR ended_at = '')", flag=True),
    ),
    "snippet": (_PROJECT,),
}

_DEFAULT_ORDER = "created_date DESC, created_time DESC"
ORDER_BY: dict[str, str] = {
    "goal": "created_date DESC",
    "activity": "created_date DESC, start_time DESC",
    "sprint": "started_date DESC",
    "task": (
        "status ASC, position ASC NULLS LAST, "
        "created_date ASC, created_time ASC"
    ),
    "snippet": "position ASC NULLS LAST, created_date ASC",
    "time_entry": "created_date DESC, started_at DESC",
    # A rating has no creation date of its own: newest rating first.
    "prompt_run": "rated_at DESC, id DESC",
}

ROUTE_BASES: dict[str, str] = {
    ent.name: ent.list_key.replace("_", "-") for ent in ENTITIES.values()
}
# `activity` is both singular and plural; keep the historical route.
ROUTE_BASES["activity"] = "activity"

DEFAULT_LIST_LIMIT: dict[str, int] = {"task": 1000, "snippet": 200}


# ---------------------------------------------------------------------------
# Detail enrichment + create defaults
# ---------------------------------------------------------------------------


def _goal_children(store: ViewStore, row: dict) -> dict:
    children = store.query(
        "SELECT id, goal_text, status, confidence_pct FROM goals_mutual "
        "WHERE parent_goal_id = ?",
        (row.get("id"),),
    )
    return {"children": children}


def _sprint_goals(store: ViewStore, row: dict) -> dict:
    goals = store.query(
        "SELECT id, goal_text, status, confidence_pct FROM goals_mutual "
        "WHERE sprint_id = ? ORDER BY created_date DESC",
        (row.get("id"),),
    )
    return {"goals": goals}


def _file_paths(store: ViewStore, row: dict) -> dict:
    # The annotated path list and git range live in the detail frontmatter.
    fm = frontmatter_cached(store.data_root, row.get("md_ref") or "") or {}
    return {
        "paths": fm.get("paths") if isinstance(fm.get("paths"), list) else [],
        "commit_from": str(fm.get("commit_from") or ""),
        "commit_to": str(fm.get("commit_to") or ""),
        "dirty": bool(fm.get("dirty", False)),
        # filled | not-a-repo | no-path | "" (entries written before this field)
        "git_status": str(fm.get("git_status") or ""),
        "range_basis": str(fm.get("range_basis") or ""),
    }


def _library_body(_store: ViewStore, _row: dict, l2: str = "", l4: str = "") -> dict:
    # Library entities keep their full body in the MD; expose it directly.
    return {"body": l2 or l4 or ""}


# Where an entity's answers read from (db.ViewStore._area): its tag follows
# those areas' stamps, so a change elsewhere still answers 304. The chats
# are in every set because the agent behind a row comes from them. An
# entity not named here follows the whole store.
ETAG_AREAS: dict[str, tuple[str, ...]] = {
    "task": ("tasks", "chats"),
    "sprint": ("tasks", "chats"),
    "time_entry": ("tasks", "chats"),
    "file": ("scans", "chats"),
    "architecture": ("scans", "chats"),
}

ENRICHERS: dict[str, Callable[..., dict]] = {
    "file": _file_paths,
    "goal": _goal_children,
    "sprint": _sprint_goals,
}
# A kept vision, rule or problem opens with its message, the turns around it
# and the versions of its interpretation (keeplib.py).
for _kept_kind in keeplib.KINDS:
    ENRICHERS[_kept_kind] = (
        lambda store, row, kind=_kept_kind: keeplib.enrich(store, kind, row)
    )
# A skill's detail adds its current SKILL.md, checks, installed copies and usage.
ENRICHERS["skill"] = skilllib.enrich
# An artifact's detail adds its folder: files, preview by kind, the manifest.
ENRICHERS["artifact"] = artifactlib.enrich
# State that lives outside the store's views: a skill's installed copies sit
# in project folders, an artifact's files sit in a folder the agent writes
# by hand. Their fingerprints join the ETag, so an install, a removal or a
# hand edit is never answered from the cache.
# The architecture page is the third: its versions are markdown files under
# projects/<p>/architecture/, written by an MCP tool and by no CSV, so a new
# version moves nothing the views watch. ``archpage.fingerprint`` was written
# for exactly this and had no caller — the page could be answered from cache
# after a write.
ETAG_STATE = {
    "skill": skilllib.install_fingerprint,
    "artifact": artifactlib.fingerprint,
    "architecture": lambda store: archpage.fingerprint(store) + "|" + repomap.fingerprint(store),
}
_LIBRARY_ENTITIES = {"idea", "note", "prompt"}


# The read models, the vocabularies filtered views select on and the check
# that keeps a write inside them live in vocab.py (the doctor and the
# libraries read them too); this module uses and re-exports them.
from ..vocab import ENUM_FIELDS, HEADLINE_REQUIRED, READ_MODELS, check_enum_fields  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Shared create implementation
# ---------------------------------------------------------------------------


def update_entity(
    store: ViewStore, ent: Entity, item_id: str, body: dict
) -> dict:
    """Change lifecycle fields and/or the detail doc of one existing row.

    Only the registry's ``mutable_fields`` are applied; unknown keys are
    ignored. ``l2``/``l3``/``l4`` (or ``body`` as an alias for l2) rewrite
    the MD detail document, minting an ``md_ref`` when the row has none.
    The CSV rewrite runs under the table's sidecar lock.

    Rows living in per-project overlay CSVs are read-only here — updates
    apply to the mutual table, the API's write surface.
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="send the body as a JSON object")
    refuse_agent_write(ent, body)
    check_enum_fields(ent.name, body)
    if ent.name in keeplib.KINDS and written_by_agent(body):
        probe = entry_fields.to_slots(ent.name, dict(body), ent.columns)
        if any(k in probe for k in ("l2", "l3", "l4", "body")):
            # The text of a kept entry is the operator's own message, kept as
            # written; an agent's reading of it is a version of the
            # interpretation, not an edit of the message.
            refuse_agent(f"a {ent.name}'s text is the operator's own message, kept as it was written",
                         f"write your reading of it with the MCP tool interpret {{lens: \"{ent.name}\", id, text}}")
    csv_path = store.data_root / ent.csv
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"{ent.csv} not found")

    changed = False

    def mutate(rows: list[dict[str, str]]) -> bool:
        nonlocal changed
        target = next((r for r in rows if r.get("id") == item_id), None)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"{ent.name} not found in {ent.csv}: {item_id} "
                    "(rows from per-project overlay files are read-only)"
                ),
            )
        if ent.name in entry_fields.PARTS:
            entry_fields.merge_parts(ent.name, body, read_detail(store.data_root, target.get("md_ref") or "")[2]
                                     if target.get("md_ref") else "")
        entry_fields.to_slots(ent.name, body, ent.columns)
        if ent.name in entry_fields.HEADLINE_MUTABLE and str(body.get("l1") or "").strip():
            new_head = str(body["l1"]).strip()
            if target.get("l1", "") != new_head:
                target["l1"] = new_head
                changed = True
        for k, v in body.items():
            if k not in ent.mutable_fields:
                continue
            new_v = str(v) if v is not None else ""
            if target.get(k, "") != new_v:
                target[k] = new_v
                changed = True

        if any(k in body for k in ("l2", "l3", "l4", "body")):
            md_ref, md_path = doc_path(store, ent, target, item_id)
            target["md_ref"] = md_ref
            # The row holds no text: what the body does not send is read
            # back from the document, or a one-level update erases the rest.
            old_l2, old_l3, old_l4 = read_detail(store.data_root, md_ref)
            # The same for what only the document's head holds: a file
            # entry's list of paths and its git range are not columns.
            try:
                old_head = frontmatter.meta(md_path.read_text(encoding="utf-8"))[0] or {}
            except (OSError, ValueError):
                old_head = {}
            md_input = {
                **{k: v for k, v in old_head.items() if k != "id" and k not in ent.columns},
                **target,
                "l2": old_l2, "l3": old_l3, "l4": old_l4,
                **{k: body[k] for k in ("l2", "l3", "l4") if k in body},
            }
            if "body" in body and "l2" not in body:
                md_input["l2"] = body["body"]
            md_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(md_path, build_detail(md_input, item_id))
            changed = True
        return changed

    rewrite_rows(csv_path, ent.columns, mutate)
    store.rebuild()
    if ent.name == "rule":
        # Turned on or off for all agents, archived, restored, reworded:
        # every project's copy of "Rules for all agents" follows.
        sync_all_rules(store)
    row = store.query_one(f"SELECT * FROM {ent.view} WHERE id = ?", (item_id,))
    if row is None:
        raise HTTPException(
            status_code=500,
            detail=f"The {ent.name} entry was updated, but the list does not show it yet.",
        )
    l2, l3, l4 = read_detail(store.data_root, row.get("md_ref") or "")
    return {"metadata": row, "l2": l2, "l3": l3, "l4": l4, "text": named_text(ent, row, l2, l3, l4)}


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _filter_docs(ent: Entity) -> str:
    specs = _specs_for(ent)
    names = ", ".join(
        f"`{p}`" + (f" (alias {', '.join(a)})" if a else "")
        for p, a, _, _ in specs
    )
    return (
        f"List {ent.list_key} newest-first. Filters: {names}, `limit`. "
        "Sends an ETag; If-None-Match short-circuits to 304."
    )


def _specs_for(ent: Entity) -> list:
    """The filters of a kind's list. ?project= on a kind with no project
    column (prompt runs) is no filter: it was a DuckDB binder error, a 500."""
    return [s for s in FILTERS.get(ent.name, _COMMON) if s is not _PROJECT or "project" in ent.columns]


def _list_filters(specs: Sequence, qp: Any) -> tuple[list[str], list[Any], list[str]]:
    """The WHERE clauses, their parameters and the ETag's fingerprint for a
    list read's query string."""
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    fingerprint: list[str] = []
    for param, aliases, clause, opts in specs:
        value: str | None = None
        for name in (param, *aliases):
            if name in qp and qp[name] != "":
                value = qp[name]
                break
        if value is None:
            continue
        if opts["flag"]:
            if value.lower() in ("1", "true", "yes"):
                clauses.append(clause)
                fingerprint.append(f"{param}=1")
            continue
        v: Any = value.lower() if opts["lower"] else value
        if opts["like"]:
            v = f"%{v}%"
        clauses.append(clause)
        params.extend([v] * opts["repeat"])
        fingerprint.append(f"{param}={value}")
    return clauses, params, fingerprint


def _list_limit(qp: Any, default_limit: int) -> int:
    try:
        return min(max(int(qp.get("limit", default_limit)), 1), 5000)
    except ValueError:
        return default_limit


def _attach_text(store: ViewStore, ent: Entity, rows: list[dict[str, Any]]) -> None:
    """?with_l2=1 (or with_desc=1) — attach each row's text from its
    detail document. One request instead of N, for surfaces that show
    summaries inline (the kanban board's description mode). Tasks
    have no l2: they get `description` (turn 1), `turn_last` and
    `turns_n` — see backend/turns.py."""
    for row in rows:
        if ent.name == "task":
            path = resolve_under(store.data_root, row.get("md_ref") or "")
            turns = parsed_file(path, "task", parse_task_doc, [])
            row["description"] = description_of(turns)
            row["turns_n"] = len(turns)
            row["turn_last"] = turns[-1].as_dict() if turns else None
        else:
            l2, _l3, _l4 = detail_cached(store.data_root, row.get("md_ref") or "")
            row["l2"] = l2


def _register(ent: Entity) -> None:
    base = ROUTE_BASES[ent.name]
    specs = _specs_for(ent)
    order = ORDER_BY.get(ent.name, _DEFAULT_ORDER)
    default_limit = DEFAULT_LIST_LIMIT.get(ent.name, 500)

    # A plain function: it reads files and waits on the store, and FastAPI
    # runs it on a worker thread. As a coroutine it held the event loop —
    # every other request and every terminal socket — while it read.
    def list_endpoint(
        request: Request,
        store: ViewStore = Depends(get_store),
    ) -> Response:
        if ent.name in keeplib.KINDS:
            # Tagged messages join the ledger on the way past, as #prompt does.
            adopt_when_changed(store, "keep", keeplib.adopt)
        if ent.name == "task":
            # A #now card the agent did not write is written first, so a
            # #done after it finds it; the operator's #done then moves its
            # task on the board's next read.
            adopt_when_changed(store, "now", nowlib.adopt)
            adopt_when_changed(store, "done", donelib.adopt)
        qp = request.query_params
        clauses, params, fingerprint = _list_filters(specs, qp)
        if ent.name in undolib.HIDDEN_BY_DATE:
            # An entry the operator archived with #undo leaves the lists;
            # ?include_archived=1 reads it, and the detail read always does.
            if qp.get("include_archived", "").lower() in ("1", "true", "yes"):
                fingerprint.append("include_archived=1")
            else:
                clauses.append("COALESCE(archived_at, '') = ''")
        limit = _list_limit(qp, default_limit)

        state = ETAG_STATE.get(ent.name)
        etag = etag_for(
            f"{base}:{'&'.join(fingerprint)}:{limit}:{qp.get('with_l2', '')}:{qp.get('with_desc', '')}"
            f":{state(store) if state else ''}", store, *ETAG_AREAS.get(ent.name, ())
        )
        if (r := maybe_304(request, etag)) is not None:
            return r

        sql = (
            f"SELECT * FROM {ent.view} WHERE " + " AND ".join(clauses)
            + f" ORDER BY {order} LIMIT ?"
        )
        params.append(limit)
        rows = store.query(sql, tuple(params))

        flags = ("1", "true", "yes")
        if qp.get("with_l2", "").lower() in flags or qp.get("with_desc", "").lower() in flags:
            _attach_text(store, ent, rows)
        return json_response({"total": len(rows), ent.list_key: rows}, etag)

    list_endpoint.__doc__ = _filter_docs(ent)

    def detail_endpoint(
        item_id: str,
        request: Request,
        store: ViewStore = Depends(get_store),
    ) -> Response:
        state = ETAG_STATE.get(ent.name)
        etag = etag_for(f"{base}:{item_id}:{state(store) if state else ''}", store,
                        *ETAG_AREAS.get(ent.name, ()))
        if (r := maybe_304(request, etag)) is not None:
            return r
        row = store.query_one(
            f"SELECT * FROM {ent.view} WHERE id = ?", (item_id,)
        )
        if row is None and ent.name in keeplib.KINDS:
            # The hook names a kept id before any list read has adopted it.
            if keeplib.adopt(store):
                row = store.query_one(
                    f"SELECT * FROM {ent.view} WHERE id = ?", (item_id,)
                )
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"{ent.name} not found: {item_id}"
            )
        l2, l3, l4 = read_detail(store.data_root, row.get("md_ref") or "")
        payload: dict[str, Any] = {"metadata": row, "l2": l2, "l3": l3, "l4": l4,
                                   "text": named_text(ent, row, l2, l3, l4)}
        if ent.name in _LIBRARY_ENTITIES:
            payload.update(_library_body(store, row, l2, l4))
        enricher = ENRICHERS.get(ent.name)
        if enricher:
            payload.update(enricher(store, row))
        return json_response(payload, etag)

    detail_endpoint.__doc__ = (
        f"One {ent.name} row plus its parsed L2/L3/L4 detail document."
    )

    def create_endpoint(
        response: Response,
        body: dict = Body(...),
        store: ViewStore = Depends(get_store),
    ) -> dict:
        out = create_entity(store, ent, body)
        if out.get("existing"):
            response.status_code = 200      # a repeat: nothing new was written
        return out

    create_endpoint.__doc__ = (
        f"Append one {ent.name} (CSV row + MD detail). Identical payloads "
        "mint the identical id and are idempotent."
    )

    def update_endpoint(
        item_id: str,
        body: dict = Body(...),
        store: ViewStore = Depends(get_store),
    ) -> dict:
        return update_entity(store, ent, item_id, body)

    update_endpoint.__doc__ = (
        f"Update one {ent.name}'s lifecycle fields "
        f"({', '.join(sorted(ent.mutable_fields))}) and/or its L2/L3/L4 "
        "detail document. Unknown fields are ignored."
    )

    router.add_api_route(
        f"/api/{base}", list_endpoint,
        methods=["GET"], name=f"{base}_list",
    )
    router.add_api_route(
        f"/api/{base}/{{item_id}}", detail_endpoint,
        methods=["GET"], name=f"{base}_detail",
    )
    router.add_api_route(
        f"/api/{base}", create_endpoint,
        methods=["POST"], status_code=201, name=f"{base}_create",
    )
    if ent.mutable_fields:
        router.add_api_route(
            f"/api/{base}/{{item_id}}/update", update_endpoint,
            methods=["POST"], name=f"{base}_update",
        )


for _ent in ENTITIES.values():
    _register(_ent)
