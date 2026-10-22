"""Examples — what a new Slightly Parallel shows before anything has been kept.

Two visions, two rules and two problems, written once when a data root is
first opened, so the three pages explain themselves: the words someone
wrote, what they mean, versions, tags, open and resolved, a rule for all
agents. They are mocks. They carry ``source: "demo"`` and the tag
``example``, and Integrate never writes them into an AGENTS.md — not in
"Rules for all agents", not in a set someone adds them to (integrate.py).

``examples.json`` at the data root records that they were written, so
they come once: removed examples do not return on the next start.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .db import ViewStore
from .docs_md import build_detail
from .entities import ENTITIES
from .file_safety import atomic_write, edit_json, safe_read_json
from .keeplib import versions_ref
from .promptlib import Version, render_doc

MARKER = "examples.json"
SOURCE = "demo"
KINDS = ("vision", "rule", "problem", "skill")

# (how, note, text) per version, oldest first. Each example shows the whole
# loop on its page: a message as people really type it, what the agent
# understood, a correction where the agent got it wrong, the reason behind a
# rule, what fixed a problem.
EXAMPLES: list[dict[str, Any]] = [
    {
        "kind": "vision", "id": "vs_e0000001", "date": "2609-01", "time": "10:04",
        "l1": "Start a new project with what we already learned",
        "message": "when I start a new project I don't want to explain everything to the agent again. let me pick the rules and visions from old projects and give them to it",
        "versions": [
            ("interpreted", "", "A new project starts with what earlier projects learned. Slightly Parallel copies the visions, rules and problems from older projects into the new project's AGENTS.md."),
            ("edited", "The agent read it as automatic", "A new project starts with what earlier projects learned. You choose which visions, rules and problems to bring, and Slightly Parallel writes them into the new project's AGENTS.md. Nothing is copied on its own."),
        ],
        "fields": {"tags": "example,product,agents"},
    },
    {
        "kind": "vision", "id": "vs_e0000002", "date": "2609-02", "time": "14:30",
        "l1": "Guests can buy without an account",
        "message": "people leave on the signup step. let them pay first, the account can be created after from the order email",
        "versions": [
            ("interpreted", "", "Guests can pay without an account. After payment, the order email has a link to create the account, with the details already filled in.\n\nThis replaces the signup step before checkout."),
        ],
        "fields": {"tags": "example,product,ui"},
    },
    {
        "kind": "rule", "id": "rl_e0000001", "date": "2609-01", "time": "11:20",
        "l1": "Ask before installing packages or tools",
        "message": "why did you install it globally?? never install anything without asking me first",
        "versions": [
            ("interpreted", "", "Ask before installing any package, library or tool.\n\nWhy: a tool was installed globally and changed the system Python. Two other projects stopped working."),
        ],
        "fields": {"tags": "example,agents", "status": "active", "auto": "yes"},
    },
    {
        "kind": "rule", "id": "rl_e0000002", "date": "2609-02", "time": "09:15",
        "l1": "Never delete data to make a test pass",
        "message": "you dropped the table to make the test green. never delete data to make something pass, stop and ask",
        "versions": [
            ("interpreted", "", "Never delete or rewrite data to make a test or a fix pass. Stop and ask.\n\nWhy: a migration table was dropped so that a failing test would pass."),
        ],
        "fields": {"tags": "example,backend", "status": "active"},
    },
    {
        "kind": "problem", "id": "pb_e0000001", "date": "2609-01", "time": "16:20",
        "l1": "Tasks saved in the same minute disappear",
        "message": "I saved two tasks quickly and the second one is just gone",
        "versions": [
            ("interpreted", "", "Two tasks saved in the same minute got the same id. The server treated the second save as a repeat of the first and dropped it.\n\nFixed: the id includes the task title, and a test saves two tasks in the same minute."),
        ],
        "fields": {"tags": "example,backend", "status": "resolved", "resolved_date": "2609-01", "severity": "high"},
    },
    {
        "kind": "rule", "id": "rl_e0000003", "date": "2609-01", "time": "17:05",
        "l1": "Test two saves made in the same minute",
        "message": "I saved two tasks quickly and the second one is just gone",
        "versions": [
            ("edited", "from pb_e0000001", "When an id is built from a date and time, include every field that tells two entries apart. Test two saves made in the same minute."),
        ],
        "fields": {"tags": "example,backend", "status": "active", "related_incident": "pb_e0000001"},
    },
    {
        "kind": "problem", "id": "pb_e0000002", "date": "2609-02", "time": "12:00",
        "l1": "Login fails after the laptop wakes up",
        "message": "after the laptop wakes up the app says I'm logged out and the refresh just spins",
        "versions": [
            ("interpreted", "", "After sleep, the session token has expired and the refresh request is sent before the network is back. It fails once and is not retried. Retrying when the tab gets focus works only when the tab is visible."),
        ],
        "fields": {"tags": "example,backend", "status": "open", "severity": "medium"},
    },
    {
        "kind": "skill", "id": "sk_e0000001", "date": "2609-03", "time": "14:05",
        "l1": "before-you-say-done",
        "message": "you said it was done and the tests were red. we go through the same checks every time, make it a skill #skill",
        "versions": [
            ("interpreted", "", (
                "---\n"
                "name: before-you-say-done\n"
                "description: Run the project's checks and report what they printed, before saying a task is done. "
                "Use when finishing any task.\n"
                "---\n\n"
                "1. Run the tests.\n"
                "2. Run the type check.\n"
                "3. If anything failed, fix it, or say what failed and stop.\n"
                "4. Report the task with the output, not from memory.\n\n"
                "Check: the last command printed no errors."
            )),
        ],
        "fields": {
            "tags": "example,process", "status": "active",
            "name": "before-you-say-done",
            "description": (
                "Run the project's checks and report what they printed, before saying a task is done. "
                "Use when finishing any task."
            ),
        },
    },
]

# The chat around an example's message, so Context shows what it does for a
# real one. Examples have no chat log; these turns stand in for it.
_CONTEXT: dict[str, dict[str, Any]] = {
    "vs_e0000001": {
        "before": [
            ("2026-09-01T09:52:00", "the agent in the new repo asked me again how we name API routes",
             "New work gets a new path, and existing paths keep their names. I can add this to the project notes."),
            ("2026-09-01T09:58:00", "we decided that three projects ago",
             "Yes. It was decided in an earlier project. This project has no copy of it."),
        ],
        "turn": ("2026-09-01T10:04:00", "when I start a new project I don't want to explain everything to the agent again. let me pick the rules and visions from old projects and give them to it #vision",
                 "Kept as a vision. A new project would start with the visions, rules and problems from earlier projects."),
        "after": [
            ("2026-09-01T10:07:00", "not everything. only what I choose",
             "Understood. Nothing is copied unless you choose it."),
        ],
    },
    "pb_e0000001": {
        "before": [
            ("2026-09-01T16:12:00", "something is wrong with saving on the board",
             "Checking the task API."),
        ],
        "turn": ("2026-09-01T16:20:00", "I saved two tasks quickly and the second one is just gone #problem",
                 "Kept as a problem. Both tasks got the same id, so the second save was dropped."),
        "after": [
            ("2026-09-01T16:31:00", "fix it and add a test",
             "Fixed. The id includes the title, and a new test saves two tasks in the same minute."),
        ],
    },
    "sk_e0000001": {
        "before": [
            ("2026-09-03T13:48:00", "is the task done?",
             "Yes, the page loads and the change is in."),
            ("2026-09-03T13:55:00", "the tests are red",
             "You are right. Two tests fail on the new column."),
        ],
        "turn": ("2026-09-03T14:05:00", "you said it was done and the tests were red. we go through the same checks every time, make it a skill #skill",
                 "Kept as a skill. The draft holds the checks to run before a task is reported done."),
        "after": [
            ("2026-09-03T14:09:00", "and print what the command said, not your summary",
             "Added. The report carries the output of the last command."),
        ],
    },
}


def context_for(example_id: str) -> dict[str, Any] | None:
    """The stand-in chat around an example's message, in the record's shape."""
    ctx = _CONTEXT.get(example_id)
    if ctx is None:
        return None

    def turn(n: int, t: tuple[str, str, str]) -> dict[str, Any]:
        return {"n": n, "at": t[0], "user": t[1], "agent": t[2]}

    before = [turn(i + 1, t) for i, t in enumerate(ctx["before"])]
    at = len(before) + 1
    return {
        "before": before,
        "turn": turn(at, ctx["turn"]),
        "after": [turn(at + i + 1, t) for i, t in enumerate(ctx["after"])],
    }


def _known(store: ViewStore) -> dict[str, Any]:
    """The marker as a dict — missing, empty or malformed reads as ``{}``."""
    try:
        data = safe_read_json(store.data_root / MARKER)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def seed(store: ViewStore) -> list[str]:
    """Write the examples this data root does not have yet. Returns the ids written.

    The marker holds what was written and what the operator took out. A
    later version can add an example — a page that arrives empty teaches
    nothing — without bringing back the ones someone removed on purpose.
    """
    marker = store.data_root / MARKER
    known = _known(store)
    written: set[str] = set(known.get("ids") or []) if isinstance(known, dict) else set()
    dropped: set[str] = set(known.get("removed") or []) if isinstance(known, dict) else set()
    added: list[str] = []
    for ex in EXAMPLES:
        ent = ENTITIES[ex["kind"]]
        if ex["id"] in written or ex["id"] in dropped:
            continue
        if any(r.get("id") == ex["id"] for r in read_rows(store.data_root / ent.csv)):
            continue
        at = f"{ex['date']} {ex['time']}"
        versions = [Version(n, at, how, note, text) for n, (how, note, text) in enumerate(ex["versions"], start=1)]
        md_ref = f"{ent.detail_dir}/{ex['id']}.md"
        row: dict[str, Any] = {
            "created_date": ex["date"], "created_time": ex["time"], "project": "",
            "agent_id": "example", "l1": ex["l1"], "md_ref": md_ref, "source": SOURCE,
            "session_id": "", "source_turn": 0, "versions_n": len(versions), **ex["fields"],
        }
        doc = store.data_root / md_ref
        doc.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(doc, build_detail({**row, "l2": versions[-1].text, "l4": ex["message"]}, ex["id"]))
        history = store.data_root / versions_ref(ex["id"])
        history.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(history, render_doc(f"---\nid: {ex['id']}\nkind: {ex['kind']}\n---\n", versions))
        append_row(store.data_root / ent.csv, ent.columns, {"id": ex["id"], **row})
        added.append(ex["id"])
    # Written only when something changed: a data root under version control
    # (the demo fixture) must not gain a new timestamp on every start.
    if added or not marker.exists() or not isinstance(known, dict):
        def stamp(data: dict) -> dict:
            return {
                "written_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "ids": sorted(set(data.get("ids") or []) | written | set(added)),
                "removed": sorted(set(data.get("removed") or []) | dropped),
            }

        edit_json(marker, stamp)
    if added:
        store.rebuild()
    return added


def state(store: ViewStore) -> dict[str, list[str]]:
    """Which examples are in the ledgers, which were taken out, and every one there is."""
    present: list[str] = []
    for kind in KINDS:
        ent = ENTITIES[kind]
        present.extend(
            str(r.get("id") or "") for r in read_rows(store.data_root / ent.csv)
            if r.get("source") == SOURCE
        )
    known = _known(store)
    removed = sorted(set(known.get("removed") or []))
    return {"present": sorted(present), "removed": removed, "all": [ex["id"] for ex in EXAMPLES]}


def restore(store: ViewStore) -> list[str]:
    """Put the removed examples back. Returns the ids written."""
    removed = set(_known(store).get("removed") or [])
    if removed:
        # Forgotten on both lists, so seed() writes them again.
        def forget(data: dict) -> dict:
            return {**data, "ids": sorted(set(data.get("ids") or []) - removed), "removed": []}

        edit_json(store.data_root / MARKER, forget)
    return seed(store)


def remove(store: ViewStore) -> list[str]:
    """Take every example out of visions, rules, problems and skills. They do not come back."""
    removed: list[str] = []
    for kind in KINDS:
        ent = ENTITIES[kind]
        path = store.data_root / ent.csv
        if not path.exists():
            continue

        def mutate(rows: list[dict[str, str]]) -> bool:
            gone = [r for r in rows if r.get("source") == SOURCE]
            if not gone:
                return False
            removed.extend(str(r.get("id") or "") for r in gone)
            rows[:] = [r for r in rows if r.get("source") != SOURCE]
            return True

        rewrite_rows(path, ent.columns, mutate)
    if removed:
        # Written into the marker, so a later start does not put them back.
        def forget(data: dict) -> dict:
            return {
                **data,
                "ids": sorted(set(data.get("ids") or []) | set(removed)),
                "removed": sorted(set(data.get("removed") or []) | set(removed)),
            }

        edit_json(store.data_root / MARKER, forget)
        store.rebuild()
    return removed
