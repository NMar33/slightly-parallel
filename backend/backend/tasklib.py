"""What a task's status, archive and comeback date set off, whoever moves
it — the board, the editor, an agent's write, a #done or an #undo in a chat:
a stack advancing, a repeating task re-armed, a card resurfacing on its day,
the archive mark with its history line.

The task routes (routers/tasks_extra.py) re-export these; donelib and
undolib call them here, so neither imports a router."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from fastapi import HTTPException

from . import app_settings, hookshared, limits, thinklib, titlelib
from .actors import HOUSE_ACTORS as _HOUSE_ACTORS
from .actors import AGENT_REFUSED, identity_of, refuse_agent
from .answers import create_answer, not_found
from .csvio import as_int, rewrite_rows
from .db import ViewStore
from .docs_md import build_detail, resolve_under
from .entities import ENTITIES, is_done
from .entitylib import create_entity
from .file_safety import atomic_write
from .refusals import Reasons
from .frontmatter import block as fm_block
from .taskevents import DEFAULT_ACTOR as _DEFAULT_ACTOR
from .taskevents import append_events as _append_events
from .turns import Turn, build_task_doc, description_of, parse_task_doc
from .vocab import ENUM_FIELDS

TASK_STATUSES = ENUM_FIELDS["task"]["status"]
TITLE_MAX = limits.MAX_TASK_TITLE
DESCRIPTION_MAX = limits.MAX_TASK_DESCRIPTION
log = logging.getLogger("sp.tasks")


def _set_archived(store: ViewStore, task_id: str, value: str, actor: str) -> dict:
    ent = ENTITIES["task"]
    csv_path = store.data_root / ent.csv
    hit: list[dict] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == task_id:
                old = r.get("archived_at", "") or ""
                if old == value:
                    hit.append(r)
                    return False
                r["archived_at"] = value
                hit.append(r)
                return True
        return False

    changed = csv_path.exists() and rewrite_rows(csv_path, ent.columns, mutate)
    if not hit:
        raise not_found("task", task_id)
    if changed:
        _append_events(store, task_id, actor, [("archived", "" if value else "yes", "yes" if value else "")])
        store.rebuild()
    return {"task_id": task_id, "archived_at": value}


def resurface_sweep(store: ViewStore) -> int:
    """Move every task whose ``resurface_on`` date has arrived back onto
    the board — to ``resurface_to`` (todo by default) — clearing the date,
    stamping ``resurfaced_at`` (the card glows for a while), and logging
    the move in the task's history as actor ``resurface``. Returns how
    many came back. Cheap when nothing is due."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    moved: list[tuple[str, str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        changed = False
        for r in rows:
            due = str(r.get("resurface_on") or "").strip()
            if not due or due > today or (r.get("archived_at") or ""):
                continue
            target = str(r.get("resurface_to") or "").strip() or "todo"
            if target not in TASK_STATUSES:
                # The column is enum-checked on write; an old row may still
                # hold a stray value, and a card must land where a filter finds it.
                target = "todo"
            old = str(r.get("status") or "")
            r["status"] = target
            r["resurface_on"] = ""
            r["resurfaced_at"] = now
            moved.append((str(r.get("id") or ""), old, target))
            changed = True
        return changed

    csv_path = store.data_root / "tasks.csv"
    if csv_path.exists():
        rewrite_rows(csv_path, ENTITIES["task"].columns, mutate)
    for tid, old, new in moved:
        _append_events(store, tid, "resurface", [("status", old, new), ("resurface_on", "due", "")])
    if moved:
        store.rebuild()
    return len(moved)


_SWEEP_INTERVAL_SEC = 600
_last_sweep = 0.0


def maybe_resurface(store: ViewStore) -> None:
    """Throttled sweep — runs at most every ten minutes, invoked from the
    request path so resurfacing needs no cron and no browser."""
    global _last_sweep
    nowts = time.time()
    if nowts - _last_sweep < _SWEEP_INTERVAL_SEC:
        return
    _last_sweep = nowts
    try:
        resurface_sweep(store)
    except Exception:  # noqa: BLE001 — the sweep must never break a request
        # …but hiding the reason forever is how real faults stay unfixed.
        logging.getLogger("sp.resurface").exception("resurface sweep failed")


def after_status_change(store: ViewStore, rows: list[dict[str, str]], target: dict[str, str],
                        old_status: str | None, changes: list[tuple[str, str, str]],
                        deferred: list | None = None) -> None:
    """What a status change sets off, whoever made it — the board, the
    editor, an agent's POST, a #done in a chat (donelib):

    - a stack advances: when a member leaves its column, the next one there
      becomes the head and is stamped;
    - a repeating task re-arms: done + every-days sets the comeback date.

    Called inside a rewrite that can still be refused, pass ``deferred``:
    the events for other cards are put there instead of written.
    """
    stack_id = str(target.get("stack_id") or "").strip()
    if stack_id and old_status is not None:
        def _pos(r: dict[str, str]) -> float:
            try:
                return float(r.get("position") or 0)
            except ValueError:
                return 0.0
        waiting = [
            r for r in rows
            if r is not target
            and str(r.get("stack_id") or "") == stack_id
            and str(r.get("status") or "") == old_status
            and not (r.get("archived_at") or "")
        ]
        if waiting:
            head = min(waiting, key=_pos)
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            head["stack_head_at"] = stamp
            event = (str(head.get("id") or ""), "stack", [("stack_head_at", "", stamp)])
            if deferred is not None:
                # The caller writes it once its own rewrite has landed.
                deferred.append(event)
            else:
                _append_events(store, *event)
    every = str(target.get("resurface_every_days") or "").strip()
    if every.isdigit() and is_done(target.get("status") or "") \
            and not str(target.get("resurface_on") or "").strip():
        import datetime as _dt
        try:
            due = (_dt.date.today() + _dt.timedelta(days=int(every))).isoformat()
        except (OverflowError, ValueError):
            # A stored count past the calendar (an old or damaged row) is no
            # reason to refuse the move: the task is done, and comes back never.
            log.warning("task %s: resurface_every_days=%s is past the calendar; not re-armed", target.get("id"), every)
        else:
            target["resurface_on"] = due
            changes.append(("resurface_on", "", due))


def _task_doc(store: ViewStore, md_ref: str, row: dict, task_id: str, *, for_write: bool = False) -> tuple[str, list[Turn]]:
    """(frontmatter, turns) of a task's document — a fresh frontmatter from
    the row when the file does not exist yet.

    A file that is there but cannot be read, or does not start with its
    frontmatter, is not an empty one: read for a write (``for_write``), it
    is refused with 422 naming the file, so the rounds in it are never
    written over with the new text alone. Read for showing, it shows empty
    and the log says why."""
    path = resolve_under(store.data_root, md_ref) if md_ref else None
    if path is not None and path.exists():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            if for_write:
                raise HTTPException(status_code=422, detail=f"the task's text file cannot be read ({path.name}: {exc})")
            log.warning("task %s: %s cannot be read (%s); shown without its text", task_id, path.name, exc)
            text = ""
        # The parameter name ``frontmatter`` is taken in this module, so
        # the one parser comes in under its function name.
        fm, _ = fm_block(text)
        if text.startswith("---"):
            return fm, parse_task_doc(text)
        if text.strip():
            if for_write:
                raise HTTPException(status_code=422, detail=(
                    f"the task's text file does not start with its frontmatter ({path.name}); "
                    "fix the file before editing the task"))
            log.warning("task %s: %s does not start with its frontmatter; shown without its text", task_id, path.name)
    front = {k: v for k, v in row.items() if k not in ("l2", "l3", "l4") and v not in (None, "")}
    return build_detail(front, task_id).rstrip("\n"), []


def _write_task_doc(store: ViewStore, md_ref: str, frontmatter: str, turns: list[Turn]) -> None:
    md_path = resolve_under(store.data_root, md_ref)
    if md_path is None:
        # Callers take the ref from doc_path; this is the last check.
        raise HTTPException(status_code=422, detail="the task's document path is outside the data folder")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(md_path, build_task_doc(frontmatter, turns))


# /task — an agent's own card. It lands in the `agent` column (the folded
# strip before To do), carries 1–3 tags from this closed set, and nothing
# the operator owns: the column is the review, the tag the one judgment.
AGENT_TAGS = ("ag_debt", "ag_bug", "ag_followup", "ag_idea", "ag_decision")
AGENT_TAGS_MAX = 3
AGENT_TITLE_MAX = limits.MAX_AGENT_TASK_TITLE

#: What an agent changes only on a card it created: the words on the card and
#: the day it is planned for. On anyone else's card they are that writer's.
OWN_CARD_FIELDS = ("title", "description", "today_on")


def own_card_refusal(row: dict, actor: str, task_id: str, fields: list[str]) -> tuple[str, str] | None:
    """Why this agent may not change ``fields`` (of OWN_CARD_FIELDS) on the
    task ``row`` — (reason, what to do instead) for ``refuse_agent`` — or None
    when it may: the card's creator (its ``agent_id``) is this agent. The
    operator's card (no agent creator) and another agent's are refused. The
    one exception, a task made from a message whose title waits for this
    chat (titlelib), is the caller's: it leaves ``title`` out of ``fields``.
    Every task write path an agent has comes through /api/tasks/{id}/update
    (MCP task_update and update_entry), which asks here."""
    held = [f for f in OWN_CARD_FIELDS if f in fields]
    creator = str(row.get("agent_id") or "").strip()
    if not held or not actor or creator == actor:
        return None
    whose = (f"{task_id} was created by {creator}: its title and text are that agent's"
             if creator and creator not in _HOUSE_ACTORS else
             f"{task_id} was created by the operator: its title and text are the operator's")
    return (f"{', '.join(held)}: an agent changes these only on a task it created; {whose}",
            f"add your words after the text with task_update {{id: \"{task_id}\", comment}}.")


def agent_tags(raw: object) -> list[str]:
    """An agent's tags, as names: comma-separated text (the published shape,
    ``"ag_bug,ag_debt"``) or a list of names (``["ag_bug"]``, what agents send
    when a field holds several values). Any other shape is refused by its
    shape. A list read as text was ``"['ag_followup']"``, refused with a
    message that listed ag_followup as allowed (round 5)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.split(",")
    elif isinstance(raw, list) and all(isinstance(t, str) for t in raw):
        parts = [p for t in raw for p in t.split(",")]
    else:
        raise HTTPException(
            status_code=422,
            detail=f"tags is text such as \"ag_bug,ag_debt\" or a list of tag names, not {type(raw).__name__}"
            + (" with items that are not text" if isinstance(raw, list) else ""),
        )
    return [t.strip() for t in parts if t.strip()]


_AGENT_CREATE_FIELDS = frozenset({
    "created_date", "created_time", "project", "projects", "agent_id",
    "title", "description", "tags", "lane", "assignee", "status", "today_on",
})


def _operator_command(store: ViewStore, agent: str, *, in_helper: bool = False) -> tuple[str, str, str, str]:
    """(command, lane, column, message) of the operator's latest message in
    the agent's chat: ``#now-todo {ui} …`` → ("now", "ui", "todo", the whole
    message); no chat, or no command → ("", "", "", ""). A helper chat has
    none, unless ``in_helper``: the command its latest message holds, which
    does not act (_refuse_in_helper)."""
    return _operator_said(store, agent, in_helper=in_helper)[:4]


def _operator_said(store: ViewStore, agent: str, *, in_helper: bool = False) -> tuple[str, str, str, str, int]:
    """_operator_command and the turn of that message (0 with none). Read
    from chat.md itself, never the derived tables: the hook writes the turn
    there before it announces the card, and the store has it only once the
    watcher rebuilt (tk_1cb0324a)."""
    from .sessions import _operator_text, chat_path, helper_ids, parse_turns, task_command
    from .hookshared import command_text
    path = chat_path(store, agent)
    if path is None or (not in_helper and agent in helper_ids(store)):
        # A helper's prompt was written by another agent: no operator's command.
        return "", "", "", "", 0
    try:
        turns = parse_turns(path)
    except OSError:
        return "", "", "", "", 0
    for t in reversed(turns):
        text = _operator_text(t)
        if text:
            command, lane, column = task_command(command_text(text))
            return command, lane, column, text if command else "", t.number
    return "", "", "", "", 0


def _catch_up(store: ViewStore) -> None:
    """Take in the chat the operator just typed in before an agent's create
    is judged: the hook wrote the turn to chat.md and announced the card at
    once, and the agent's write came before the watcher rebuilt (tk_1cb0324a,
    seen twice on 26 Nov). Rebuilt, as thinklib.refusal does for #think. The
    #now cards owed are not written here (nowlib.adopt): an agent's write
    must not be the read that writes the server's card for it, or the since
    stamp. A failure is logged, never the agent's error: the gate reads the
    message from chat.md all the same."""
    try:
        store.rebuild()
    except Exception:  # noqa: BLE001 — as deps.adopt_when_changed
        log.warning("catching up the chats before an agent's create failed; the gate reads chat.md", exc_info=True)


def _not_captured(agent: str, status: str) -> tuple[str, str]:
    """The agent's chat is not in the store yet, even after a rebuild: the
    operator's message (a #now in it, likely) cannot be read. An agent card
    is offered only for a write no #now asked for: a #now card filed there
    would lose the message, and a tool without the hook, which never gets a
    chat, must not be left retrying."""
    return (
        f"the operator's latest message in this chat ({agent}) is not captured yet, "
        f"so the status {status!r} cannot be checked against its #now",
        "retry the same write in a few seconds; if it is refused again, tell the operator in one line. "
        'Or, if the operator gave no #now, write it with status "agent"',
    )


def _board_lanes(store: ViewStore, project: str) -> list[str]:
    """The lanes the project's board shows: every assignee (lane) a live card has."""
    rows = store.query(
        "SELECT lane, assignee, archived_at FROM tasks_mutual WHERE project = ?", (project,))
    seen: dict[str, str] = {}
    for r in rows:
        if str(r.get("archived_at") or "").strip():
            continue
        name = str(r.get("lane") or r.get("assignee") or "").strip()
        if name:
            seen.setdefault(name.lower(), name)
    return sorted(seen.values(), key=str.lower)


def _lane_for(store: ViewStore, project: str, command: str, named: str) -> str:
    """The lane an agent's card lands in. Named in the message's braces: the
    board's, matched without case, else a new lane as typed (note
    nt_258a7ed7 §3: anything that is not a project is a lane); not named:
    #now's own lane from Settings, and #task's none ("unassigned")."""
    if named:
        for lane in _board_lanes(store, project):
            if lane.lower() == named.lower():
                return lane
        return named
    if command == "now":
        return str(app_settings.load(store.data_root).get("tasks.now_lane") or "Now").strip() or "Now"
    return ""


def _latest_now_turn(store: ViewStore, agent: str) -> int | None:
    """The turn of the chat's latest #now the store knows."""
    latest = store.query_one("SELECT max(turn) AS turn FROM now_tags WHERE agent_id = ?", (agent,)) or {}
    return None if latest.get("turn") is None else as_int(latest.get("turn"))


def _now_card_written(store: ViewStore, agent: str, turn: int | None = None) -> bool:
    """Whether the latest #now of this chat has its card: one the agent wrote
    in that turn (its history says so), or the server's (now.csv). ``turn``:
    the #now's turn as chat.md has it (_operator_said) — the store's latest
    may still be the previous #now, whose card is not this message's."""
    from . import nowlib
    if turn is None:
        turn = _latest_now_turn(store, agent)
    if turn is None:
        return False
    if any(r.get("agent_id") == agent and as_int(r.get("turn")) == turn for r in nowlib.rows(store)):
        return True
    return any(n == turn for _a, n, _t in nowlib.card_turns(store, {agent}, skip_server=True))


def _refuse_in_helper(store: ViewStore, agent: str) -> None:
    """A task command in the latest message of a chat marked a helper: it
    does not act there, and the card is refused instead of filed quietly in
    `agent` without the message (tk_2484f160: an operator's chat marked a
    helper by mistake lost its #now and #now-todo, and nobody was told)."""
    from .sessions import helper_ids
    if agent not in helper_ids(store):
        return
    command, _lane, column, _message = _operator_command(store, agent, in_helper=True)
    if not command:
        return
    row = next((a for a in store.agents() if str(a.get("agent_id") or "") == agent), {})
    kind = str(row.get("helper_kind") or "").strip()
    tag = "#task" if command == "task" else ("#now" if column == "doing" else f"#now-{column}")
    refuse_agent(
        f"this chat ({agent}) is marked a helper chat{f' ({kind})' if kind else ''}; operator "
        f"commands do not apply here, so the {tag} in its latest message made no task",
        "tell the operator, in one line, that this chat is marked a helper and the command did "
        "nothing; do not write the task another way",
    )


LEVEL_ONE = ("agent {agent} may create tasks only in its home {home} (level 1). "
             "Name the project in braces, or the operator raises the level on the agent card")


NO_BRACES: dict[str, Any] = {"project": "", "lane": "", "refusal": "", "ask": "", "reasons": []}


def unclear_lane_note(ask: str) -> str:
    """The history line of a card whose braces left the lane unclear."""
    return f"the braces left the lane unclear, so the card went to the default lane: {ask}"


def task_braces(store: ViewStore, agent: str, message: str, kind: str = "") -> dict[str, Any]:
    """The project and the lane the braces of the operator's #task / #now
    name (hookshared.resolve_braces, the hook's own rule), for ``agent``:
    ``{"project", "lane", "refusal", "ask"}``; NO_BRACES without a command. Each
    tag has its own braces: ``kind`` "now" or "task" reads that tag's
    (``#now {ui} x and #task {writing-tracker} y``)."""
    from . import memberships
    from .sessions import TASK_CMD_RE
    text = hookshared.command_text(message or "")
    m = hookshared.pick_task_hit(list(TASK_CMD_RE.finditer(text)), kind)
    if m is None:
        return dict(NO_BRACES)
    groups = hookshared.task_braces(text[m.end(1):])
    if not groups:
        return dict(NO_BRACES)
    view = memberships.agent_view(store, agent)
    return hookshared.resolve_braces(
        groups, agent=agent, home=view.home if view else "", members=list(view.members) if view else [],
        codes=[pf.code for pf in store.projects], aliases=memberships.alias_map(store),
        lanes_of=lambda code: _board_lanes(store, code))


def _check_level(store: ViewStore, agent: str, body: dict, named: str = "") -> None:
    """The agent's task level (note nt_258a7ed7 §3): at level 1 its tasks go
    to its home only — or to the project the operator named in braces
    (``named``); levels 2 and 3 take any member project (the gate checked
    membership before the request got here). Refused with one line, 403."""
    from . import memberships
    from .entitylib import project_codes
    view = memberships.agent_view(store, agent)
    if view is None or view.level != 1:
        return
    allowed = {view.home} | ({named} if named else set())
    codes = [str(body.get("project") or "").strip(), *project_codes(body.get("projects"))]
    if any(c and c not in allowed for c in codes):
        raise HTTPException(status_code=403, detail=LEVEL_ONE.format(agent=agent, home=view.home))


def _gate_agent_create(body: dict, store: ViewStore) -> tuple[list[str], str]:
    """Apply the /task contract to an agent's create; return the fields
    dropped, and the line to ask the operator when the braces left the lane
    unclear (hookshared.resolve_braces ``ask``: the card is made all the same).

    A house actor (the board) passes untouched. The operator's message
    decides the column and the lane: ``#task`` → the `agent` column,
    ``#now`` → `doing`, ``#now-todo`` and the rest → that column, with the
    lane named in braces or #now's own. A #now task's text is the
    operator's message itself: the agent sends the title and tags only.
    """
    agent = identity_of(body)
    if agent in _HOUSE_ACTORS:
        return [], ""
    _refuse_in_helper(store, agent)
    command, named, column, message, said_turn = _operator_said(store, agent)
    now_written = command == "now" and _now_card_written(store, agent, said_turn)
    if now_written:
        # The #now card is on the board (the agent's or the server's): what
        # the agent writes after it, while that message is still the latest,
        # are ordinary #task cards (the findings of the work), in `agent`.
        # The #task beside it keeps its own braces (#now {ui} x and #task {wt} y).
        braces = task_braces(store, agent, message, "task")
        command, named, column, message = "", "", "agent", ""
    else:
        braces = task_braces(store, agent, message) if command else dict(NO_BRACES)
    if braces["refusal"]:
        # Each refusal of the braces, one line each (hookshared.resolve_braces).
        why = Reasons()
        for line in braces.get("reasons") or [braces["refusal"]]:
            why.add(line, status=403, code="braces")
        why.raise_if_any()
    if braces["project"] and str(body.get("project") or "").strip() != braces["project"]:
        raise HTTPException(status_code=403, detail=(
            f"the operator named {braces['project']} in braces: this task goes to {braces['project']}, "
            f"not {str(body.get('project') or '').strip() or '(none)'} — send project {braces['project']}"))
    named = braces["lane"]
    _check_level(store, agent, body, braces["project"])
    # The rest are named together (tk_90c1ba5f): the status, the text, the
    # lane, the title, the tags.
    why = Reasons()
    status = str(body.get("status") or "").strip() or (column if command == "now" else "agent")
    if command == "now" and status != column:
        why.add(
            f"the operator's #now puts this task in `{column}`",
            f"send status \"{column}\" (or none), not {status!r}", code="status", field="status",
        )
    if command == "now":
        if str(body.get("description") or "").strip():
            why.add(
                "a #now task's text is the operator's message, kept as it was written",
                "send the title and tags only; the server writes the message in as the text",
                code="own_card", field="description",
            )
        body["description"] = message
    if status != "agent":
        # A #now written late: the server wrote the card when the turn ended
        # (whether or not that message is still the operator's latest).
        from . import nowlib
        # The #now of the message on disk, when it holds one: the store's
        # latest may be the previous #now, and its server card is not this
        # message's (tk_1cb0324a: the agent was told to retitle that one).
        now_turn = said_turn if command == "now" or now_written else _latest_now_turn(store, agent)
        last = next((r for r in nowlib.rows(store) if r.get("agent_id") == agent
                     and as_int(r.get("turn")) == (-1 if now_turn is None else now_turn)), None)
        if last:
            why.add(
                f"the server already wrote the #now task as {last['task_id']}: "
                "the turn ended without one",
                f"give it a title with task_update {{id: \"{last['task_id']}\", title}}; do not write it again",
                code="written", field="status",
            )
        elif command != "now":
            from .sessions import chat_path
            if not now_written and chat_path(store, agent) is None:
                why.add_pair(_not_captured(agent, status), code="not_captured", field="status")
            else:
                why.add_pair((
                "an agent creates tasks only in the `agent` column",
                f"send status \"agent\" (or none), not {status!r}; the operator "
                "classifies the card from there"
                # The reason the message gave none: its #now has its card
                # already, or it has no #now at all.
                + (" (the #now in the operator's latest message already has its card; "
                   "a task written after it is an agent card)" if now_written
                   else "" if command else " (#now in the operator's message starts a task in `doing`)"),
                ), code="status", field="status")
    body["status"] = status
    # The lane comes from the operator's message, never from the agent.
    lane = _lane_for(store, str(body.get("project") or ""), command, named)
    # A lane the agent names itself: a new one is the operator's to make
    # (vision vs_5dd903f1, tk_79e9f2cd). One the board has, or the one the
    # operator's braces named (made at once), and any when the braces named
    # one, is dropped as before: the lane comes from the operator's message,
    # never from the agent.
    on_board = _board_lanes(store, str(body.get("project") or ""))
    board = {x.lower() for x in on_board}
    for key in ("lane", "assignee"):
        own = str(body.get(key) or "").strip()
        if own and not named and own.lower() not in board and own.lower() != lane.lower():
            reason = f"the lane {own!r} is not on the board"
            if not any(r.reason == reason for r in why.items):     # lane and assignee alike: once
                why.add(
                    reason,
                    ("the board's lanes: " + ", ".join(on_board) if on_board else "the board has no lanes yet")
                    + " — ask the operator which, in one line; a new lane is the operator's to make",
                    code="lane", field=key,
                )
    dropped = {k for k in ("lane", "assignee") if str(body.pop(k, None) or "").strip()}
    if lane:
        body["lane"] = body["assignee"] = lane
    if command == "now" and column == "doing":
        body["today_on"] = date.today().isoformat()
    title = str(body.get("title") or "").strip()
    if not title:
        why.add("an agent task needs a title", code="empty", field="title")
    elif len(title) > AGENT_TITLE_MAX:
        why.add(f"an agent task title is at most {AGENT_TITLE_MAX} characters ({len(title)} sent)",
                code="length", field="title")
    tags = agent_tags(body.get("tags"))
    bad = [t for t in tags if t not in AGENT_TAGS]
    if not tags or bad:
        why.add(("unknown tag(s) " + ", ".join(bad) + " — " if bad else "an agent task needs tags — ")
                + f"1–{AGENT_TAGS_MAX} of: " + ", ".join(AGENT_TAGS), code="vocabulary", field="tags")
    elif len(tags) > AGENT_TAGS_MAX:
        why.add(f"an agent task carries at most {AGENT_TAGS_MAX} tags ({len(tags)} sent)",
                code="length", field="tags")
    why.raise_if_any()
    body["tags"] = ",".join(tags)
    ignored = sorted(k for k in list(body) if k not in _AGENT_CREATE_FIELDS)
    for k in ignored:
        body.pop(k, None)
    return sorted(set(ignored) | dropped), braces.get("ask", "")


def _title_from_message(store: ViewStore, body: dict) -> str:
    """With ``title_from: "message"`` and the message in ``title_source``
    (``<agent>#<turn>`` or ``…/reply``): the server's provisional title put
    in ``body``, and the source returned (the flag's chat). '' when not asked."""
    if str(body.get(titlelib.TITLE_FROM_FIELD) or "") != titlelib.TITLE_FROM_MESSAGE:
        return ""
    source = str(body.get(titlelib.TITLE_SOURCE_FIELD) or "").strip()
    parsed = hookshared.parse_target(source)
    if parsed is None:
        raise HTTPException(status_code=422, detail=(
            "title_source names the message: <agent_id>#<turn>, or <agent_id>#<turn>/reply for the agent's reply"))
    from .pinlib import _Chats, message_text  # reads the chats; imported here, it imports much
    agent, turn, side = parsed
    text = message_text(_Chats(store), agent, turn, side)[0]
    title = (titlelib.provisional_title(text)
             or titlelib.provisional_title(str(body.get("description") or ""))
             or str(body.get("title") or "").strip())
    if title:
        body["title"] = title
    return hookshared.mark_target(agent, turn, side)


def create_task(store: ViewStore, body: dict, *, text_max: int | None = DESCRIPTION_MAX,
                chosen: bool = False) -> dict:
    """One task, as POST /api/tasks makes it — the operator's board, an
    agent through the /task gate, the server's own #now card (nowlib). The
    answer is create_answer's: ``existing`` true when the same task was
    already there (the route then answers 200, not 201).

    ``chosen``: a next task the operator chose by number after #done
    (nextlib). The server built the body (status agent, its tag, no lane),
    so the gate is not asked: it reads the operator's latest message as a
    command, and a later #now or #task {lane} there would move the card."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    if any(k in body for k in ("l2", "l3", "l4")):
        raise HTTPException(
            status_code=422,
            detail="a task holds title and description — send its text as description",
        )
    # A task the operator made from one message of a chat (the terminal's
    # message menu): the server titles it, and the title waits for that
    # chat's agent (titlelib). Only the operator's create asks for it; an
    # agent's gate names the fields back as ignored.
    title_wait = ""
    if identity_of(body) in _HOUSE_ACTORS:
        title_wait = _title_from_message(store, body)
        body.pop(titlelib.TITLE_FROM_FIELD, None)
        body.pop(titlelib.TITLE_SOURCE_FIELD, None)
    agent_create = identity_of(body) not in _HOUSE_ACTORS and not chosen
    if agent_create:
        _catch_up(store)
    said = _operator_said(store, identity_of(body)) if agent_create else ("", "", "", "", 0)
    started_now, column = said[0] == "now", said[2]
    # #think beside #now / #task: the card this message makes is the
    # operator's to think through (thinklib). Not a card written after the
    # #now one already has its card: that one is the agent's finding.
    think = bool(said[0]) and thinklib.wants_mark(hookshared.command_text(said[3])) and not (
        started_now and _now_card_written(store, identity_of(body), said[4]))
    ignored, ask = ([], "") if chosen else _gate_agent_create(body, store)
    if think:
        body.update(thinklib.mark_fields())
    if len(str(body.get("title") or "")) > TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title is at most {TITLE_MAX} characters")
    description = str(body.pop("description", "") or "").strip()
    # A #now card's text is the operator's message, put in by the gate: it is
    # kept whole, as the server's own card keeps it (nowlib._write_card).
    if text_max is not None and not started_now and len(description) > text_max:
        raise HTTPException(status_code=422, detail=f"description is at most {text_max} characters")
    out = create_entity(store, ENTITIES["task"], body, seed_extra=description)
    meta = dict(out.get("metadata") or {})
    task_id = str(meta.get("id") or "")
    md_ref = str(meta.get("md_ref") or "")
    fm, turns = _task_doc(store, md_ref, meta, task_id, for_write=bool(out.get("existing")))
    if description and not turns and md_ref:
        turns = [Turn(1, "", "", description)]
        _write_task_doc(store, md_ref, fm, turns)
        store.rebuild()
    if title_wait and task_id and not out.get("existing"):
        titlelib.open_wait(store.data_root, task_id, str(meta.get("project") or ""), title_wait,
                           str(meta.get("title") or ""))
    if (think or thinklib.marked(body)) and task_id and not out.get("existing"):
        _append_events(store, task_id, _DEFAULT_ACTOR, [("think", "", "set with #think in the chat")])
    if identity_of(body) not in _HOUSE_ACTORS and task_id and not out.get("existing"):
        # An agent's task outside its home: the history says where it went
        # (note nt_258a7ed7 §6), as the answer's `where` and the hook's notice do.
        from . import memberships
        view = memberships.agent_view(store, identity_of(body))
        made_in = str(meta.get("project") or "")
        if view is not None and view.home and made_in and made_in != view.home:
            _append_events(store, task_id, identity_of(body), [("created_in", "", f"{made_in} (home {view.home})")])
            store.rebuild()
    if started_now and not out.get("existing"):
        # The card's history says where it came from: the operator's #now
        # in the chat, and the agent that wrote it down.
        verb, tag = ("started", "#now") if column == "doing" else ("filed", f"#now-{column}")
        _append_events(store, task_id, _DEFAULT_ACTOR, [(verb, "", f"in the chat, with {tag} (written by {identity_of(body)})")])
        store.rebuild()
    if ask and task_id and not out.get("existing"):
        _append_events(store, task_id, _DEFAULT_ACTOR, [("note", "", unclear_lane_note(ask))])
        store.rebuild()
    result = {
        "metadata": meta,
        "description": description_of(turns),
        "turns": [t.as_dict() for t in turns],
        "turns_n": len(turns),
    }
    if ignored:
        result["ignored"] = ignored
    if ask:
        # The card is made; the agent asks the operator now, in one line.
        result["ask"] = f"ask the operator in one line: {ask}"
    return create_answer(result, existing=bool(out.get("existing")),
                         warnings=out.get("warnings"))


# ---------------------------------------------------------------------------
# The move (tk_d1d25a4d step 3, note nt_258a7ed7 §3 «The move», level 3)
# ---------------------------------------------------------------------------

MOVE_LEVEL = 3


def move_task(store: ViewStore, task_id: str, to: str, actor: str) -> dict:
    """Move a task to project ``to``, keeping its id. The operator, or an
    agent at level 3 that is a member of both projects. ``project`` becomes
    ``to`` and ``projects`` loses the old one, so the card leaves its board;
    the column and ``md_ref`` stay; the lane stays when a live card in ``to``
    carries it, else it is cleared; a topic of the old project and a stack
    in it are let go. The history says «moved from A to B, by …». Refused with
    every reason at once, writing nothing, the most general first: no such
    task or project (alone); an agent below level 3 or not in ``to`` (no
    access: alone); a done or archived task, the same project and, for an
    agent, the operator's think mark."""
    from . import memberships
    from .entitylib import project_codes
    from .entities import ENTITIES
    from .entrypointlib import TOPICS_FILE, entry_of, topics_by_task
    from .entities import TASK_TOPIC_COLUMNS

    to = str(to or "").strip()
    if not to:
        raise HTTPException(status_code=422, detail="to names the project the task moves to")
    # Every reason at once, all before any write (tk_90c1ba5f). A missing
    # task or project is the only reason; no access (the source by the gate,
    # then the level and ``to``) ends the answer, naming nothing about the
    # task; then a closed task, the same project and, for an agent, the
    # operator's think mark, together.
    row = store.query_one("SELECT * FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None:
        raise not_found("task", task_id)
    old = str(row.get("project") or "")
    if to not in memberships.existing_codes(store.data_root):
        raise HTTPException(status_code=404, detail=f"no project «{to}»")
    why = Reasons()
    if actor not in _HOUSE_ACTORS:
        view = memberships.agent_view(store, actor)
        if view is None:
            raise HTTPException(status_code=403, detail=memberships.UNINDEXED.format(agent=actor))
        if view.level < MOVE_LEVEL:
            why.add(f"agent {actor} may not move tasks (level {view.level}); the operator raises it to "
                    f"level {MOVE_LEVEL} on the agent card", status=403, code="level")
        ok, line = memberships.may_write(store, actor, to)
        if not ok:
            why.add(line, status=403, code="not_member", field="to")
        why.raise_if_any()
    if str(row.get("archived_at") or "").strip() or is_done(str(row.get("status") or "")):
        why.add(f"{task_id} is done or archived: a closed task is not moved", status=409, code="closed")
    if to == old:
        why.add(f"{task_id} is in {to} already", status=409, code="same_project", field="to")
    # A task the operator thinks through is not moved by an agent. The
    # operator's move keeps the mark (it is in the task's columns).
    why.add_pair(thinklib.reason(store, task_id, actor, "moving it to another project"),
                 status=AGENT_REFUSED, code="think")
    why.raise_if_any()
    lane = str(row.get("lane") or row.get("assignee") or "").strip()
    kept_lane = next((x for x in _board_lanes(store, to) if lane and x.lower() == lane.lower()), "")
    ep_id = topics_by_task(store).get(task_id) or ""
    topic = entry_of(store, ep_id) if ep_id else None
    drop_topic = topic is not None and str(topic.get("project") or "") != to
    stack = str(row.get("stack_id") or "").strip()
    sprint = str(row.get("sprint_id") or "").strip()
    if sprint:
        # A sprint that plans the target project too keeps the task.
        planned = store.query_one("SELECT projects FROM sprints_mutual WHERE id = ?", (sprint,))
        if planned is not None and to in project_codes(planned.get("projects")):
            sprint = ""
    from .entities import (MILESTONE_TASK_COLUMNS, STORY_IMAGE_COLUMNS, STORY_REQUEST_COLUMNS,
                           TASK_EVIDENCE_COLUMNS, TASK_NOTE_COLUMNS)
    milestones = [str(r.get("milestone_id") or "") for r in store.query(
        "SELECT milestone_id FROM milestone_tasks_mutual WHERE task_id = ?", (task_id,))]
    deferred: list = []
    projects = ",".join([to, *[c for c in project_codes(row.get("projects")) if c not in (old, to)]])
    ent = ENTITIES["task"]

    def mutate(rows: list[dict[str, str]]) -> bool:
        target = next((r for r in rows if r.get("id") == task_id), None)
        if target is None or str(target.get("project") or "") != old:
            raise HTTPException(status_code=409, detail=f"{task_id} changed while moving; nothing was written")
        target["project"] = to
        target["projects"] = projects
        if lane and not kept_lane:
            target["lane"] = target["assignee"] = ""
        if stack:
            # The stack stays in A: the card leaves it as a card leaving its
            # column does, so the next one there becomes its head.
            after_status_change(store, rows, target, str(target.get("status") or ""), [], deferred)
            target["stack_id"] = ""
        if sprint:
            target["sprint_id"] = ""
        return True

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    for ev_task, ev_actor, ev_changes in deferred:
        _append_events(store, ev_task, ev_actor, ev_changes)
    # Its notes, evidence, story requests and story images go with it (a
    # later delete of A sweeps every row filed under A); a milestone is A's
    # plan and lets it go.
    for name, columns in (("task_notes.csv", TASK_NOTE_COLUMNS), ("task_evidence.csv", TASK_EVIDENCE_COLUMNS),
                          ("story_requests.csv", STORY_REQUEST_COLUMNS), ("story_images.csv", STORY_IMAGE_COLUMNS)):
        def follow(rs: list[dict[str, str]]) -> bool:
            hit = [r for r in rs if r.get("task_id") == task_id and r.get("project") != to]
            for r in hit:
                r["project"] = to
            return bool(hit)
        if (store.data_root / name).exists():
            rewrite_rows(store.data_root / name, columns, follow)
    if milestones:
        rewrite_rows(store.data_root / "milestone_tasks.csv", MILESTONE_TASK_COLUMNS,
                     lambda rs: bool([rs.remove(r) for r in list(rs) if r.get("task_id") == task_id]))
    if drop_topic:
        rewrite_rows(store.data_root / TOPICS_FILE, TASK_TOPIC_COLUMNS,
                     lambda rs: bool([rs.remove(r) for r in list(rs) if r.get("task_id") == task_id]))
    by = actor if actor not in _HOUSE_ACTORS else "the operator"
    _append_events(store, task_id, actor or _DEFAULT_ACTOR, [
        ("project", old, to),
        ("moved", "", f"from {old} to {to}, by {by}"),
    ] + ([("lane", lane, "")] if lane and not kept_lane else [])
      + ([("stack_id", stack, "")] if stack else [])
      + ([("sprint_id", sprint, "")] if sprint else [])
      + [("milestone", m, "") for m in milestones])
    store.rebuild()
    said = [f"{task_id} → {to}" + (f" · lane {kept_lane}" if kept_lane else "")]
    if lane and not kept_lane:
        said.append(f"its lane {lane} is not on {to}'s board: cleared")
    if drop_topic:
        said.append(f"its topic {ep_id} is {old}'s: let go")
    if stack:
        said.append(f"its stack {stack} stays in {old}: let go")
    if sprint:
        said.append(f"its sprint {sprint} is {old}'s: let go")
    if milestones:
        said.append(f"its milestone{'s' if len(milestones) > 1 else ''} {', '.join(milestones)} "
                    f"{'are' if len(milestones) > 1 else 'is'} {old}'s: let go")
    said.append("its notes, evidence and story go with it")
    return {"task_id": task_id, "from": old, "to": to, "lane": kept_lane, "projects": projects,
            "lane_cleared": bool(lane and not kept_lane), "topic_dropped": drop_topic,
            "stack_dropped": bool(stack), "sprint_dropped": bool(sprint), "milestones_dropped": milestones,
            "where": said[0], "said": "; ".join(said)}
