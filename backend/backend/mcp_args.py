"""The top-level arguments of every MCP tool, and which of them take ``project``.

One table (task tk_0b8a32d2, audit pattern P23): the translator builds its
tool schemas from it and refuses any other top-level argument; the CI
stand's guard (scripts/fresh_user/core_mcp.py) reads it instead of keeping
its own list. Standard library only and no relative imports, so a script can
load this file by path without the backend's dependencies.

``project`` is always top-level, next to the tool's other arguments — for
write_entry next to ``lens``, never inside ``fields``.
"""

from __future__ import annotations

#: The tools that write to or read one project, and so take a top-level ``project``.
PROJECT_TOOLS: frozenset[str] = frozenset({
    "write_entry", "scan_material",
    "architecture_material", "architecture_page", "map_material", "map_write",
    "core_new", "note_write",
    "tasks", "cores", "pins", "entrypoints", "notes", "usage", "project",
})

_ARGS: dict[str, tuple[str, ...]] = {
    "write_entry": ("lens", "fields"),
    "update_entry": ("lens", "id", "changes"),
    "tasks": ("status",),
    "task_story": ("id", "request_id", "body", "images"),
    "task_report": ("id", "summary"),
    "task_commits": ("id", "shas"),
    "task_move": ("id", "to"),
    "task_done": ("proposals",),
    "next_tasks": ("numbers",),
    "undo_find": (),
    "undo_propose": ("ids",),
    "undo_apply": (),
    "undo_restore": ("id",),
    "cores": (),
    "pins": ("kind", "scope", "q"),
    "carry_brief": ("message", "text", "turn"),
    "core_new": ("name", "type", "text", "reason", "comment", "anchors", "task_id"),
    "core_note": ("id", "text", "comment", "kind", "task_id"),
    "core_attach": ("id", "turn", "task_id", "note"),
    "core_off": ("id",),
    "architecture_status": (),
    "architecture_material": (),
    "map_material": (),
    "map_write": ("map", "note"),
    "architecture_page": ("text", "note"),
    "scan_material": (),
    "standup_material": ("date", "claim", "clip"),
    "standup_postpone": ("date", "hours"),
    "task_work": ("id",),
    "task_evidence_ask": ("id",),
    "publish_write": ("id", "text", "context", "note", "merge", "base", "tasks", "notes",
                      "commits", "links", "images", "files"),
    "publish_attach": ("id", "images", "links"),
    "entrypoints": ("id",),
    "entrypoint_stop": ("id", "text", "task_id"),
    "entrypoint_way": ("id", "way", "way_id"),
    "entrypoint_shot": ("id", "way_id", "path", "caption", "replaces"),
    "entrypoint_offer": ("name", "why"),
    "entrypoint_ask": ("id", "name"),
    "entrypoint_answer": ("number", "name", "id"),
    "task_topic": ("id", "topic"),
    "task_evidence": ("id", "items"),
    "task_update": ("id", "title", "description", "status", "comment", "today_on"),
    "interpret": ("lens", "id", "text", "note"),
    "skill_draft": ("id", "skill_md", "files", "note"),
    "artifact_write": ("id", "name", "kind", "description"),
    "doc_version": ("id", "body", "note"),
    "deck": ("days",),
    "search": ("q",),
    "project": (),
    "doctor": (),
    "checkup": (),
    "usage": ("range",),
    "usage_prices_material": (),
    "usage_prices_write": ("models", "sources", "note"),
    "note_write": ("text", "kind", "title", "id", "base", "images", "task_id",
                   "entrypoint_id", "replaces"),
    "note_image": ("id", "path", "caption"),
    "notes": ("id", "task_id"),
    "message": ("to", "text", "reply_to"),
    "messages": ("recent",),
}

#: Every tool's top-level arguments, ``project`` included where PROJECT_TOOLS says.
TOOL_ARGS: dict[str, frozenset[str]] = {
    name: frozenset(args) | ({"project"} if name in PROJECT_TOOLS else frozenset())
    for name, args in _ARGS.items()
}


#: The one decision table for identity a model sends (tk_0b8a32d2): each field
#: is "refuse" (refused with the right shape, nothing written) or "stamp"
#: (written over by the stamp). Every tool applies it the same way, and
#: tests/test_identity_matrix.py walks every write tool against it. All are
#: refused: a silent override hid the bug in P23. ``project`` is refused
#: inside ``fields``/``changes`` and on a tool outside PROJECT_TOOLS; top-level
#: on a project tool it is the argument itself.
IDENTITY: dict[str, str] = {
    "agent_id": "refuse", "actor": "refuse", "from": "refuse", "from_agent": "refuse", "agent": "refuse",
    "created_by": "refuse", "session": "refuse", "session_id": "refuse",
    "created_date": "refuse", "created_time": "refuse", "project": "refuse",
}
#: Identity Slightly Parallel stamps: no tool takes one as an argument.
STAMPED: frozenset[str] = frozenset(k for k in IDENTITY if k != "project")


def stamped_refusal(keys: list[str]) -> str:
    """«agent_id is stamped by Slightly Parallel; leave it out»."""
    if len(keys) == 1:
        return f"{keys[0]} is stamped by Slightly Parallel; leave it out"
    return f"{', '.join(keys)} are stamped by Slightly Parallel; leave them out"


def nested_identity(args: dict, skip: tuple[str, ...] = ()) -> tuple[str, str] | None:
    """The first identity name inside an object the arguments carry (an
    evidence item, a map row, a way in …), as (name, where): a stamped name
    or ``project``. The top level is the caller's to judge; ``skip`` names
    top-level objects with refusals of their own (write_entry's fields). A
    map relation's ``from`` names a part, not a writer. The translator and
    the server's gate both ask this (tk_0b8a32d2)."""
    def walk(value: object, where: str) -> tuple[str, str] | None:
        if isinstance(value, list):
            for i, item in enumerate(value):
                if (got := walk(item, f"{where}[{i}]")):
                    return got
            return None
        if not isinstance(value, dict):
            return None
        for key, inner in value.items():
            here = f"{where}.{key}"
            if inner is not None and inner != "" and (key in STAMPED or key == "project") and not (
                    key == "from" and "relations[" in here):
                return str(key), where
            if (got := walk(inner, here)):
                return got
        return None

    for key, value in args.items():
        if key in skip and isinstance(value, dict):
            # Its own level has its own refusals; what it carries is walked.
            inner_hits = (walk(v, f"{key}.{k}") for k, v in value.items())
            got = next((h for h in inner_hits if h), None)
        else:
            got = walk(value, key)
        if got:
            return got
    return None


def accepts(tool: str) -> frozenset[str]:
    """The top-level arguments ``tool`` takes; empty for a tool there is not."""
    return TOOL_ARGS.get(tool, frozenset())


def project_shape(lens: str, project: str) -> str:
    """The one shape of a write_entry with a project, as the refusals and the
    notices show it."""
    return f'{{"lens":"{lens}","project":"{project}","fields":{{…}}}}'


def send_project(project: str, lens: str = "task") -> str:
    """What the hook's notice and the server's refusal tell an agent to send:
    the same words in both (tests/test_project_one_place.py)."""
    return f'call write_entry with "project": "{project}" next to lens: {project_shape(lens, project)}'


#: What every project tool's ``project`` argument says of its place.
PROJECT_TOP = "a top-level argument, never inside another one"
#: What write_entry's description and the contract say of the project.
PROJECT_PLACE = ("The project is this chat's home unless you name another of its projects: put `project` "
                 "next to lens, never inside `fields`: " + project_shape("task", "<code>") + ".")
