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

import hashlib
from pathlib import Path
from typing import Any, Callable, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from .. import archpage, artifactlib, donelib, entry_fields, frontmatter, keeplib, skilllib, repomap, undolib
from ..csvio import append_if_absent, rewrite_rows
from ..db import ViewStore
from ..docs_md import build_detail, read_detail, resolve_under, safe_ref_part
from ..turns import description_of, parse_task_doc
from ..entities import ENTITIES, Entity
from ..file_entries import assessment_summary, prepare_file_entry
from ..file_safety import atomic_write
from .deps import (
    adopt_when_changed, create_answer, detail_cached, etag_for, frontmatter_cached,
    get_store, json_response, maybe_304, parsed_file, refuse_agent, written_by_agent,
)
from .integrate import sync_all_rules

# Writes that are the operator's alone. Sprints are planned by a person.
OPERATOR_ONLY: dict[str, str] = {
    # A rule is the operator's own #rule message, kept by the server. An
    # agent's rule was accepted with a warning, made active, and served to
    # every agent of the project as the operator's (sp://rules).
    "rule": (
        "a rule is the operator's own #rule message, kept by the server — write "
        "its interpretation with the MCP tool interpret {lens: \"rule\", id, text}"
    ),
    "sprint": "sprints are the operator's — an agent does not start, end or change one",
    # The operator's prompt is already captured verbatim in the chat log.
    # An agent writing a second copy of it can only disagree with the first,
    # so the library harvests #prompt instead — see promptlib.py.
    "prompt": (
        "prompts are harvested, not reported — tag the message #prompt and "
        "the library takes it from the chat log verbatim"
    ),
    "skill": (
        "skills come from #skill in a message or the Skills page — an agent "
        "writes a draft with the MCP tool skill_draft"
    ),
    "artifact": (
        "artifacts come from #artifact in a message or the Artifacts page — an "
        "agent writes the folder and makes the record with the MCP tool "
        "artifact_write"
    ),
}


def refuse_agent_write(ent: Entity, body: dict) -> None:
    reason = OPERATOR_ONLY.get(ent.name)
    if reason and written_by_agent(body):
        refuse_agent(reason)

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


def _pre_create_file(store: ViewStore, body: dict) -> None:
    # Per-project chain + paths normalisation + git fill (file_entries.py).
    prepare_file_entry(store, body)


# Architecture creation is bespoke: routers/architecture.py registers its
# own POST /api/architecture (the per-scan form) ahead of this router, so
# the generic create below never sees it. List/detail stay generic.


def _pre_create_task(_store: ViewStore, body: dict) -> None:
    body["projects"] = task_membership(str(body.get("project") or ""), body.get("projects"))
    body.setdefault("status", "unclassified")
    if not body.get("status"):
        body["status"] = "unclassified"
    if not body.get("position"):
        body["position"] = "0"


def task_membership(home: str, raw: Any) -> str:
    """Comma-separated membership list, home first, no duplicates or blanks."""
    if isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        items = str(raw or "").split(",")
    seen: list[str] = []
    for code in [home, *items]:
        c = code.strip()
        if c and c not in seen:
            seen.append(c)
    return ",".join(seen)


def _pre_create_snippet(_store: ViewStore, body: dict) -> None:
    if not body.get("position"):
        body["position"] = "100"


PRE_CREATE: dict[str, Callable[[ViewStore, dict], None]] = {
    "file": _pre_create_file,
    "task": _pre_create_task,
    "snippet": _pre_create_snippet,
}


# ---------------------------------------------------------------------------
# Level-contract checks — advisory, never blocking
# ---------------------------------------------------------------------------
#
# Each lens defines what its L2/L3 layers owe the reader (the "level
# contract", mirrored in the frontend lens registry and the Guide page).
# Creates that fall short still persist, but the response carries a
# `warnings` list so a well-behaved agent can fix and re-post.


def _l2_of(body: dict) -> str:
    return str(body.get("l2") or "").lower()


def _warn_decision(body: dict) -> list[str]:
    warnings = []
    weight = str(body.get("weight") or "normal")
    if weight == "minor":
        return warnings  # a minor decision is one line and one reason
    if not body.get("l3"):
        warnings.append(
            "`alternatives` should list each option turned down "
            "('<option> — rejected: <specific reason>')."
        )
    if weight == "major" and not any(
        k in _l2_of(body)
        for k in ("revisit", "reversal", "revert", "undo", "reconsider", "re-evaluate")
    ):
        warnings.append(
            "`why` should say what would make us undo it — what "
            "observation would make us undo this decision."
        )
    return warnings


def _warn_problem(body: dict) -> list[str]:
    warnings = []
    if not any(
        k in _l2_of(body)
        for k in ("block", "impact", "affect", "prevent", "stall", "delay")
    ):
        warnings.append(
            "`impact` should say what this affects — what this "
            "problem blocks downstream — and who or what owns the fix."
        )
    if not body.get("l3"):
        warnings.append(
            "`attempts` should list what was already tried "
            "('<tried> — <result>') so the next agent does not repeat them."
        )
    return warnings


def _warn_file(body: dict) -> list[str]:
    warnings = []
    paths = body.get("paths") if isinstance(body.get("paths"), list) else []
    if not paths:
        warnings.append(
            "a file entry needs a paths list — one record per "
            "file you modified, with importance/blast_radius/why. Without it "
            "the heatmap has nothing to plot."
        )
    else:
        summary = assessment_summary(paths)
        if summary["judged"] == 0:
            warnings.append(
                "no path carries a judgment (importance, "
                "blast_radius, test_coverage, why). Git already knows what "
                "moved; the entry exists to say which moves matter."
            )
    if not body.get("trigger_id"):
        warnings.append(
            "set trigger_lens/trigger_id to the scan that "
            "prompted this entry so the chain is replayable."
        )
    return warnings


CONTRACT_CHECKS: dict[str, Callable[[dict], list[str]]] = {
    "decision": _warn_decision,
    "problem": _warn_problem,
    "file": _warn_file,
}


# The strict read models, by entity name. These models are the single
# authority on what a row must carry to be readable: the create gate below
# derives its requirements from them instead of keeping a parallel list
# that can drift (that drift is exactly how a valid-looking POST once broke
# the project page).
from ..models import Activity as _Activity  # noqa: E402
from ..models import Decision as _Decision  # noqa: E402
from ..models import Goal as _Goal  # noqa: E402

READ_MODELS: dict[str, Any] = {
    "decision": _Decision,
    "goal": _Goal,
    "activity": _Activity,
}

# Entities whose read model requires their headline field — derived, not
# hand-maintained. A headless create for these is a 422 at the door rather
# than a 500 three endpoints away.
HEADLINE_REQUIRED = {
    name
    for name, model in READ_MODELS.items()
    if (ent := ENTITIES.get(name)) is not None
    and ent.headline_field in model.model_fields
    and model.model_fields[ent.headline_field].is_required()
}

# Values that filtered views select on. A row whose status is a typo does
# not error — it silently disappears from every board and deck that filters
# WHERE status = …, which reads as lost data. Refusing the write with the
# allowed list is the honest answer.
ENUM_FIELDS: dict[str, dict[str, frozenset[str]]] = {
    "sprint": {"status": frozenset({"active", "ended"})},
    "task": {"status": frozenset({
        "unclassified", "backlog", "next", "todo", "parked", "doing",
        "review", "review-later", "done", "done-archived",
        # "agent": the folded column before To do where an agent's own
        # tasks land (/task); the operator drags them out to classify.
        "agent",
    })},
}
# Where a resurfacing card lands is a status too: the sweep copies it into
# `status`, so a stray value there would hide the card from every filter.
ENUM_FIELDS["task"]["resurface_to"] = ENUM_FIELDS["task"]["status"]
ENUM_FIELDS["decision"] = {"weight": frozenset({"minor", "normal", "major"})}
ENUM_FIELDS.update({
    "problem": {"status": frozenset({"open", "resolved"})},
    # A closed entry point is a topic that is done; it stays readable.
    "entrypoint": {"status": frozenset({"open", "closed"})},
    # An archived rule is kept but written nowhere; restore makes it active again.
    "rule": {"status": frozenset({"active", "archived"})},
    "skill": {"status": frozenset({"draft", "active", "archived"})},
    "artifact": {"status": frozenset({"draft", "active", "archived"}),
                 "kind": frozenset(artifactlib.KINDS)},
})


def check_enum_fields(ent_name: str, body: dict) -> None:
    """422 when a write would put a filtered-on field outside its vocabulary."""
    for field, allowed in ENUM_FIELDS.get(ent_name, {}).items():
        v = body.get(field)
        if v in (None, ""):
            continue
        if str(v) not in allowed:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{ent_name}.{field} {v} is not a known value — "
                    f"use one of: {', '.join(sorted(allowed))}"
                ),
            )


# ---------------------------------------------------------------------------
# Shared create implementation
# ---------------------------------------------------------------------------


def mint_id(ent: Entity, body: dict, seed_extra: str = "") -> str:
    """Deterministic 8-hex id — identical payloads mint the identical id.

    ``seed_extra`` is text that is part of the payload but not a column
    (a task's description lives in its document): two posts that differ
    only there are two entries, not one silent fold.
    """
    fields = ent.id_fields or (
        "created_date", "created_time", "project", "agent_id", ent.headline_field,
    )
    key = "|".join(str(body.get(k, "")) for k in fields)
    if seed_extra:
        key += "|" + hashlib.sha256(seed_extra.encode("utf-8")).hexdigest()[:16]
    return ent.id_prefix + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def named_text(ent: Entity, row: dict, l2: Any, l3: Any, l4: Any) -> dict[str, Any]:
    """An entry's text by name, for every detail answer (entry_fields.py)."""
    head = row.get(ent.headline_field) or row.get("l1") or ""
    return entry_fields.from_slots(ent.name, head, l2, l3, l4, ent.columns)


def detail_ref(ent: Entity, row: dict, eid: str) -> str:
    """Where an entry's detail document lives, minted from its row.

    The path segments are folded to a safe charset — a request body must
    not be able to steer the write location. The id keeps the path unique:
    two same-minute creates (or entities without created_time, like
    sprints) must never share a detail doc. The two update paths minted
    theirs without the id; one rule now.
    """
    date_part = safe_ref_part(str(row.get("created_date", "")).replace("-", ""), "nodate")
    time_part = safe_ref_part(str(row.get("created_time", "")).replace(":", ""), "0000")
    slug = safe_ref_part(str(row.get("project") or "unknown").lower())
    agent_part = safe_ref_part(str(row.get("agent_id") or eid).lower())
    return f"{ent.detail_dir}/{date_part}-{time_part}__{slug}__{agent_part}__{eid}.md"


def doc_path(store: ViewStore, ent: Entity, row: dict, eid: str) -> tuple[str, Path]:
    """(md_ref, path) an entry's detail document is written to.

    The row's own ``md_ref`` when it stays inside the data root; otherwise
    (none yet, or a ``../`` or an absolute path someone put in the CSV) a
    fresh one minted from the row. Reads already went through
    ``resolve_under``; writes took the CSV's word.
    """
    ref = str(row.get("md_ref") or "")
    path = resolve_under(store.data_root, ref) if ref else None
    if path is None:
        ref = detail_ref(ent, row, eid)
        path = store.data_root / ref
    return ref, path


def create_entity(store: ViewStore, ent: Entity, body: dict, seed_extra: str = "") -> dict:
    """Persist one entity row + its MD detail document.

    Idempotent on the minted id: re-POSTing an identical payload returns the
    existing row instead of appending a duplicate; the answer then carries
    ``existing: true`` so a caller can say so.
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="send the body as a JSON object")
    refuse_agent_write(ent, body)
    # Agents write what the entry holds by name (entry_fields.py); the names
    # land in the storage slots here, before anything reads them.
    entry_fields.to_slots(ent.name, body, ent.columns)
    if ent.name == "rule" and written_by_agent(body):
        body.pop("auto", None)  # for all agents is the operator's choice
    # L1 is the headline in the contract every agent writes to, but a few
    # entities name that column something of their own (decisions call it
    # decision_text, goals goal_text). Without this the row is created
    # headless and only fails much later, in a reader that requires it.
    head = ent.headline_field
    if head != "l1" and not str(body.get(head) or "").strip():
        if str(body.get("l1") or "").strip():
            body[head] = body["l1"]
        elif ent.name in HEADLINE_REQUIRED:
            named = entry_fields.fields_for(ent.name, ent.columns)
            first = named[0].name if named else head
            raise HTTPException(
                status_code=422,
                detail=f"{ent.name} needs its first line: send {first}",
            )
    pre = PRE_CREATE.get(ent.name)
    if pre:
        pre(store, body)
    check_enum_fields(ent.name, body)

    check = CONTRACT_CHECKS.get(ent.name)
    warnings = check(body) if check else []

    eid = mint_id(ent, body, seed_extra)
    existing = store.query_one(
        f"SELECT * FROM {ent.view} WHERE id = ?", (eid,)
    )
    if existing is not None:
        l2, l3, l4 = read_detail(store.data_root, existing.get("md_ref") or "")
        return create_answer(
            {"metadata": existing, "l2": l2, "l3": l3, "l4": l4,
             "text": named_text(ent, existing, l2, l3, l4)},
            existing=True, warnings=warnings,
        )

    md_ref, md_path = doc_path(store, ent, {**body, "md_ref": ""}, eid)
    body["md_ref"] = md_ref

    md_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(md_path, build_detail(body, eid))

    row = dict(body)
    row["id"] = eid
    # The look above read the view; this one reads the file under its lock,
    # so two identical posts at once write one row.
    raced = append_if_absent(store.data_root / ent.csv, ent.columns, row)

    store.rebuild()
    stored = store.query_one(f"SELECT * FROM {ent.view} WHERE id = ?", (eid,))
    if raced is not None and stored is not None:
        l2, l3, l4 = read_detail(store.data_root, stored.get("md_ref") or "")
        return create_answer(
            {"metadata": stored, "l2": l2, "l3": l3, "l4": l4,
             "text": named_text(ent, stored, l2, l3, l4)},
            existing=True, warnings=warnings,
        )
    if stored is None:
        raise HTTPException(
            status_code=500,
            detail=f"The {ent.name} entry was saved, but the list does not show it yet.",
        )
    out = {
        "metadata": stored,
        "l2": body.get("l2", ""),
        "l3": list(body.get("l3", [])) if isinstance(body.get("l3"), list) else [],
        "l4": body.get("l4", ""),
    }
    out["text"] = named_text(ent, stored, out["l2"], out["l3"], out["l4"])
    return create_answer(out, warnings=warnings)


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
    if ent.name == "rule" and "auto" in body and written_by_agent(body):
        refuse_agent("whether a rule is for all agents is yours to set",
                     "an agent does not change it")
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
            # The operator's #done moves its task on the board's next read.
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
