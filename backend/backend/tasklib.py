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

from fastapi import HTTPException

from . import app_settings, limits
from .actors import HOUSE_ACTORS as _HOUSE_ACTORS
from .actors import identity_of, refuse_agent
from .answers import create_answer, not_found
from .csvio import rewrite_rows
from .db import ViewStore
from .docs_md import build_detail, resolve_under
from .entities import ENTITIES, is_done
from .entitylib import create_entity
from .file_safety import atomic_write
from .frontmatter import block as fm_block
from .taskevents import DEFAULT_ACTOR as _DEFAULT_ACTOR
from .taskevents import append_events as _append_events
from .turns import Turn, build_task_doc, description_of, parse_task_doc
from .vocab import ENUM_FIELDS

TASK_STATUSES = ENUM_FIELDS["task"]["status"]
TITLE_MAX = limits.MAX_TASK_TITLE
DESCRIPTION_MAX = limits.MAX_TASK_DESCRIPTION


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
        due = (_dt.date.today() + _dt.timedelta(days=int(every))).isoformat()
        target["resurface_on"] = due
        changes.append(("resurface_on", "", due))


def _task_doc(store: ViewStore, md_ref: str, row: dict, task_id: str) -> tuple[str, list[Turn]]:
    """(frontmatter, turns) of a task's document — a fresh frontmatter from
    the row when the file does not exist yet."""
    path = resolve_under(store.data_root, md_ref) if md_ref else None
    if path is not None and path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        # The parameter name ``frontmatter`` is taken in this module, so
        # the one parser comes in under its function name.
        fm, _ = fm_block(text)
        if text.startswith("---"):
            return fm, parse_task_doc(text)
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
_AGENT_CREATE_FIELDS = frozenset({
    "created_date", "created_time", "project", "projects", "agent_id",
    "title", "description", "tags", "lane", "assignee", "status", "today_on",
})


def _operator_command(store: ViewStore, agent: str) -> tuple[str, str, str, str]:
    """(command, lane, column, message) of the operator's latest message in
    the agent's chat: ``#now-todo {ui} …`` → ("now", "ui", "todo", the whole
    message); no chat, or no command → ("", "", "", "")."""
    from .sessions import _operator_text, chat_path, parse_turns, task_command
    from .hookshared import command_text
    path = chat_path(store, agent)
    if path is None:
        return "", "", "", ""
    try:
        turns = parse_turns(path)
    except OSError:
        return "", "", "", ""
    for t in reversed(turns):
        text = _operator_text(t)
        if text:
            command, lane, column = task_command(command_text(text))
            return command, lane, column, text if command else ""
    return "", "", "", ""


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
    """The lane an agent's card lands in. Named in the message: one the board
    has, matched without case; else #now's own lane from Settings, and
    #task's none (the card shows under "unassigned")."""
    lanes = _board_lanes(store, project)
    if named:
        for lane in lanes:
            if lane.lower() == named.lower():
                return lane
        refuse_agent(
            f"the lane {named!r} is not on the board",
            ("the board's lanes: " + ", ".join(lanes) if lanes else "the board has no lanes yet")
            + " — ask the operator which, in one line; a new lane is made on the board",
        )
    if command == "now":
        return str(app_settings.load(store.data_root).get("tasks.now_lane") or "Now").strip() or "Now"
    return ""


def _gate_agent_create(body: dict, store: ViewStore) -> list[str]:
    """Apply the /task contract to an agent's create; return the fields dropped.

    A house actor (the board) passes untouched. The operator's message
    decides the column and the lane: ``#task`` → the `agent` column,
    ``#now`` → `doing`, ``#now-todo`` and the rest → that column, with the
    lane named in braces or #now's own. A #now task's text is the
    operator's message itself: the agent sends the title and tags only.
    """
    agent = identity_of(body)
    if agent in _HOUSE_ACTORS:
        return []
    command, named, column, message = _operator_command(store, agent)
    status = str(body.get("status") or "").strip() or (column if command == "now" else "agent")
    if command == "now" and status != column:
        refuse_agent(
            f"the operator's #now puts this task in `{column}`",
            f"send status \"{column}\" (or none), not {status!r}",
        )
    if command == "now":
        if str(body.get("description") or "").strip():
            refuse_agent(
                "a #now task's text is the operator's message, kept as it was written",
                "send the title and tags only; the server writes the message in as the text",
            )
        body["description"] = message
    if command != "now" and status != "agent":
        # A #now written late: the server wrote the card when the turn ended.
        from . import nowlib
        latest = store.query_one("SELECT max(turn) AS turn FROM now_tags WHERE agent_id = ?", (agent,)) or {}
        last = next((r for r in nowlib.rows(store) if r.get("agent_id") == agent
                     and int(r.get("turn") or 0) == int(latest.get("turn") or -1)), None)
        if last:
            refuse_agent(
                f"the server already wrote the #now task as {last['task_id']}: "
                "the turn ended without one",
                f"give it a title with task_update {{id: \"{last['task_id']}\", title}}; do not write it again",
            )
        refuse_agent(
            "an agent creates tasks only in the `agent` column",
            f"send status \"agent\" (or none), not {status!r}; the operator "
            "classifies the card from there"
            + ("" if command else " (#now in the operator's message starts a task in `doing`)"),
        )
    body["status"] = status
    # The lane comes from the operator's message, never from the agent.
    lane = _lane_for(store, str(body.get("project") or ""), command, named)
    dropped = {k for k in ("lane", "assignee") if str(body.pop(k, None) or "").strip()}
    if lane:
        body["lane"] = body["assignee"] = lane
    if command == "now" and column == "doing":
        body["today_on"] = date.today().isoformat()
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="an agent task needs a title")
    if len(title) > AGENT_TITLE_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"an agent task title is at most {AGENT_TITLE_MAX} characters ({len(title)} sent)",
        )
    tags = [t.strip() for t in str(body.get("tags") or "").split(",") if t.strip()]
    bad = [t for t in tags if t not in AGENT_TAGS]
    if not tags or bad:
        raise HTTPException(
            status_code=422,
            detail=(
                ("unknown tag(s) " + ", ".join(bad) + " — " if bad else "an agent task needs tags — ")
                + f"1–{AGENT_TAGS_MAX} of: " + ", ".join(AGENT_TAGS)
            ),
        )
    if len(tags) > AGENT_TAGS_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"an agent task carries at most {AGENT_TAGS_MAX} tags ({len(tags)} sent)",
        )
    body["tags"] = ",".join(tags)
    ignored = sorted(k for k in list(body) if k not in _AGENT_CREATE_FIELDS)
    for k in ignored:
        body.pop(k, None)
    return sorted(set(ignored) | dropped)


def create_task(store: ViewStore, body: dict) -> dict:
    """One task, as POST /api/tasks makes it — the operator's board, an
    agent through the /task gate, the server's own #now card (nowlib). The
    answer is create_answer's: ``existing`` true when the same task was
    already there (the route then answers 200, not 201)."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    if any(k in body for k in ("l2", "l3", "l4")):
        raise HTTPException(
            status_code=422,
            detail="a task holds title and description — send its text as description",
        )
    said = _operator_command(store, identity_of(body)) if identity_of(body) not in _HOUSE_ACTORS else ("", "", "", "")
    started_now, column = said[0] == "now", said[2]
    ignored = _gate_agent_create(body, store)
    if len(str(body.get("title") or "")) > TITLE_MAX:
        raise HTTPException(status_code=422, detail=f"title is at most {TITLE_MAX} characters")
    description = str(body.pop("description", "") or "").strip()
    if len(description) > DESCRIPTION_MAX:
        raise HTTPException(status_code=422, detail=f"description is at most {DESCRIPTION_MAX} characters")
    out = create_entity(store, ENTITIES["task"], body, seed_extra=description)
    meta = dict(out.get("metadata") or {})
    task_id = str(meta.get("id") or "")
    md_ref = str(meta.get("md_ref") or "")
    fm, turns = _task_doc(store, md_ref, meta, task_id)
    if description and not turns and md_ref:
        turns = [Turn(1, "", "", description)]
        _write_task_doc(store, md_ref, fm, turns)
        store.rebuild()
    if started_now and not out.get("existing"):
        # The card's history says where it came from: the operator's #now
        # in the chat, and the agent that wrote it down.
        verb, tag = ("started", "#now") if column == "doing" else ("filed", f"#now-{column}")
        _append_events(store, task_id, _DEFAULT_ACTOR, [(verb, "", f"in the chat, with {tag} (written by {identity_of(body)})")])
        store.rebuild()
    result = {
        "metadata": meta,
        "description": description_of(turns),
        "turns": [t.as_dict() for t in turns],
        "turns_n": len(turns),
    }
    if ignored:
        result["ignored"] = ignored
    return create_answer(result, existing=bool(out.get("existing")),
                         warnings=out.get("warnings"))
