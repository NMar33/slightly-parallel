"""What a row must hold to be readable, and the words a field may take.

The strict read models by entity, the entities whose headline is required,
and the vocabularies that filtered views select on — with the check that
refuses a write outside them. Read by the lens routes, the task routes, the
schema and the doctor."""

from __future__ import annotations

from typing import Any

from . import artifactlib
from .entities import ENTITIES
from .models import Activity as _Activity
from .models import Decision as _Decision
from .models import Goal as _Goal

# The strict read models, by entity name. These models are the single
# authority on what a row must carry to be readable: the create gate below
# derives its requirements from them instead of keeping a parallel list
# that can drift (that drift is exactly how a valid-looking POST once broke
# the project page).

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
    """Refuse a write that would put a filtered-on field outside its
    vocabulary: a ValueError, which the server answers as 422 with its sentence."""
    for field, allowed in ENUM_FIELDS.get(ent_name, {}).items():
        v = body.get(field)
        if v in (None, ""):
            continue
        if str(v) not in allowed:
            raise ValueError(f"{ent_name}.{field} {v} is not a known value — "
                             f"use one of: {', '.join(sorted(allowed))}")
