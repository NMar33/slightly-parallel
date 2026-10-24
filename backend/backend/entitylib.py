"""Creating one entry of any lens: the gate an agent meets, what each lens
prepares before the write, the advisory checks of its level contract, the
id minted from its content and the detail document beside the row.

The lens routes (routers/lenses.py) and the libraries that create on a
router's behalf (timeauto, the task gate) all call create_entity; it lives
outside the routers so a library imports none."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from . import entry_fields
from .actors import refuse_agent, written_by_agent
from .answers import create_answer
from .csvio import append_if_absent
from .db import ViewStore
from .docs_md import build_detail, read_detail, resolve_under, safe_ref_part
from .entities import Entity
from .file_entries import assessment_summary, prepare_file_entry
from .file_safety import atomic_write
from .vocab import HEADLINE_REQUIRED, check_enum_fields

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
