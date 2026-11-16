"""Cores: the program's core elements, named by the operator, each with a story.

A core is a noun about the program — a capability (chat capture), a feature
(the ### suppressor), a store, a part of the interface — that the operator chose to keep
in view. The motive differs (watch how a capability is doing; remember a
feature for the release notes); the subject is always the program. Not a
feature tracker (no readiness, no dates), not a monitor (no alerts), not a
second board.

Three ledgers at the data root: ``cores.csv`` (the cores), ``core_notes.csv``
(the story: the operator's text as typed plus the agent's comment, dated,
with who wrote it and whether the operator approved it) and
``core_links.csv`` (what is attached: tasks, anchors, map rows, releases).

What the server computes from those, on read: the linked tasks with their
status, the files and commits of those tasks (taskwork), the commits that
touched the anchors ("touched nearby" — by file, not by sense, so shown
apart), and a 30-day activity grid.

Who may do what: anyone creates a core and adds a note (the operator's
commands run through the agent); an agent's ``auto`` note needs tracking on;
approving a note, switching tracking, changing a core and ordering them are
the operator's.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .actors import identity_of, is_agent, refuse_agent
from .csvio import append_row, read_rows, rewrite_rows
from .date_utils import now_iso
from .db import ViewStore
from .entities import CORE_COLUMNS, CORE_EVENT_COLUMNS, CORE_LINK_COLUMNS, CORE_NOTE_COLUMNS, CORE_STATUSES, CORE_TYPES
from .file_entries import project_path

CORES_FILE = "cores.csv"
NOTES_FILE = "core_notes.csv"
LINKS_FILE = "core_links.csv"
EVENTS_FILE = "core_events.csv"

NAME_MAX = 60
REASON_MAX = 200
NOTE_MAX = 4000
LINK_KINDS = ("task", "anchor", "map", "release", "vision", "decision", "message")
NOTE_KINDS = ("founding", "note", "auto")
TRACKING_SPANS = {"day": 1, "week": 7}
GRID_DAYS = 30
TASKS_TO_CLAIM = 2
# The map kinds a core can hold by its tasks alone: concrete parts. A
# framework, a runtime or a build file is touched by every task.
TASK_CLAIM_KINDS = frozenset({"module", "surface", "store", "service", "job", "entry", "step", "data-in", "data-out"})


class CoreRefused(ValueError):
    """A write the server will not make; answered as 422 with the sentence."""


def _mint(prefix: str, *parts: str) -> str:
    seed = "|".join(parts) + f"|{time.time()!r}"
    return prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]


def _rows(store: ViewStore, name: str) -> list[dict[str, str]]:
    return read_rows(store.data_root / name)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def core_of(store: ViewStore, core_id: str) -> dict[str, str] | None:
    return next((r for r in _rows(store, CORES_FILE) if r.get("id") == core_id), None)


def tracking_state(core: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """``{on, until, days_left}`` — tracking is on while the switch is on and
    the end date, if any, has not passed. An expired switch reads as off;
    nothing announces it."""
    today = today or date.today()
    until = str(core.get("tracking_until") or "")
    on = str(core.get("tracking_on") or "") == "1"
    if on and until:
        try:
            end = date.fromisoformat(until)
        except ValueError:
            end = None
        if end is not None and end < today:
            return {"on": False, "until": until, "days_left": 0, "expired": True}
        days_left = (end - today).days + 1 if end is not None else None
        return {"on": True, "until": until, "days_left": days_left, "expired": False}
    return {"on": on, "until": until, "days_left": None, "expired": False}


def _day(stamp: Any) -> str:
    return str(stamp or "")[:10]


def _grid(days: list[tuple[str, str]], today: date | None = None) -> list[dict[str, Any]]:
    """The last GRID_DAYS days, oldest first: ``{day, story, nearby}`` counts.
    ``days`` are (day, kind) pairs, kind ``story`` (a note, a linked task's
    event, a commit of a linked task) or ``nearby`` (a commit on an anchor)."""
    today = today or date.today()
    first = today - timedelta(days=GRID_DAYS - 1)
    counts: dict[tuple[str, str], int] = Counter(days)
    out = []
    for i in range(GRID_DAYS):
        d = (first + timedelta(days=i)).isoformat()
        out.append({"day": d, "story": counts.get((d, "story"), 0), "nearby": counts.get((d, "nearby"), 0)})
    return out


def _tasks_of(store: ViewStore, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = store.query(
        f"SELECT id, title, status, archived_at, created_date, created_time FROM tasks_mutual WHERE id IN ({marks})", tuple(ids))
    by_id = {str(r.get("id")): r for r in rows}
    return [{"id": i, **{k: v for k, v in by_id[i].items() if k != "id"}} for i in ids if i in by_id]


def _anchor_commits(store: ViewStore, project: str, anchors: list[str]) -> list[dict[str, Any]]:
    """Commits of the project's repository that touched an anchor's file —
    by path, not by sense: the caller shows them as "touched nearby"."""
    if not anchors:
        return []
    from . import gitwork
    repo = project_path(store, project)
    if repo is None:
        return []
    paths = [a.split(":", 1)[0].strip().replace("\\", "/") for a in anchors]
    out = []
    for c in gitwork.commits(repo):
        hit = [p for p, _, _ in c.files if any(p == a or p.startswith(a.rstrip("/") + "/") for a in paths)]
        if hit:
            out.append({"sha": c.sha[:7], "at": c.at.isoformat(timespec="seconds"), "subject": c.subject, "files": hit})
    return out


def summary_rows(store: ViewStore, project: str) -> list[dict[str, Any]]:
    """Every core of the project with what a tile shows: the latest note,
    the linked tasks' counts, tracking, and the 30-day grid."""
    cores = [r for r in _rows(store, CORES_FILE) if r.get("project") == project]
    notes = [n for n in _rows(store, NOTES_FILE)]
    links = [l for l in _rows(store, LINKS_FILE)]
    out = []
    for c in cores:
        mine = sorted((n for n in notes if n.get("core_id") == c["id"]), key=lambda n: n.get("at") or "")
        my_links = [l for l in links if l.get("core_id") == c["id"]]
        task_ids = [l["target"] for l in my_links if l.get("kind") == "task"]
        tasks = _tasks_of(store, task_ids)
        open_n = sum(1 for t in tasks if str(t.get("status") or "") not in ("done", "done-archived") and not t.get("archived_at"))
        last = mine[-1] if mine else None
        days = [(_day(n.get("at")), "story") for n in mine]
        if task_ids:
            marks = ",".join("?" for _ in task_ids)
            for e in store.query(f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({marks})", tuple(task_ids)):
                days.append((_day(e.get("timestamp")), "story"))
        out.append({
            **c,
            "tracking": tracking_state(c),
            "notes_n": len(mine),
            "pending_n": sum(1 for n in mine if not n.get("approved_at")),
            "last_note": ({"at": last.get("at"), "text": last.get("text"), "comment": last.get("comment"),
                           "author": last.get("author"), "kind": last.get("kind"),
                           "approved": bool(last.get("approved_at"))} if last else None),
            "tasks_n": len(tasks),
            "open_n": open_n,
            "anchors": [l["target"] for l in my_links if l.get("kind") == "anchor"],
            "grid": _grid(days),
        })
    out.sort(key=lambda c: (c["status"] != "view", not c["tracking"]["on"], -_pos(c), c.get("name") or ""))
    return out


def _pos(c: dict[str, Any]) -> float:
    try:
        return float(c.get("position") or 0)
    except ValueError:
        return 0.0


def _agents_of(store: ViewStore, task_ids: list[str], notes: list[dict[str, str]],
               commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Who worked on the core: every agent the operator gave one of its tasks
    in a chat (named it in a message that was not only filing it), that made
    one of its commits, or that wrote a note on it — with the tasks, the
    commits, the notes, the chats and the last time. An agent that only
    named a task in its own answer (a list, "I filed tk_…") did not work on it."""
    from .taskwork import _filing_turns
    out: dict[str, dict[str, Any]] = {}

    def get(agent: str) -> dict[str, Any]:
        return out.setdefault(agent, {"agent_id": agent, "tasks": [], "given": [], "commits": 0, "notes": 0, "turns": 0,
                                      "sessions": [], "last_at": ""})

    def seen(rec: dict[str, Any], at: str) -> None:
        if at and at > rec["last_at"]:
            rec["last_at"] = at
    if task_ids:
        marks = ",".join("?" for _ in task_ids)
        rows = store.query(
            f"SELECT m.task_id, m.session_id, m.turn, s.agent_id, s.created_date, s.end_time FROM task_mentions m "
            f"JOIN sessions s ON s.id = m.session_id WHERE m.role = 'user' AND m.task_id IN ({marks})", tuple(task_ids))
        filing: dict[str, set[int]] = {}
        for r in rows:
            agent = str(r.get("agent_id") or "")
            if not agent:
                continue
            sid = str(r["session_id"])
            if sid not in filing:
                row = store.query_one("SELECT turns_json FROM sessions WHERE id = ?", (sid,))
                filing[sid] = _filing_turns(row) if row else set()
            if int(r.get("turn") or 0) in filing[sid]:
                continue
            rec = get(agent)
            if r["task_id"] not in rec["tasks"]:
                rec["tasks"].append(r["task_id"])
            # Given in a chat by the operator, as opposed to found through commits.
            if r["task_id"] not in rec["given"]:
                rec["given"].append(r["task_id"])
            if r["session_id"] not in rec["sessions"]:
                rec["sessions"].append(r["session_id"])
            rec["turns"] += 1
            day = _iso_of_yymm(str(r.get("created_date") or ""))
            seen(rec, f"{day}T{r.get('end_time') or '00:00'}:00" if day else "")
    for c in commits:
        agent = str(c.get("agent") or "")
        if not agent:
            continue
        rec = get(agent)
        rec["commits"] += 1
        for tid in c.get("tasks") or []:
            if tid not in rec["tasks"]:
                rec["tasks"].append(tid)
        seen(rec, str(c.get("at") or ""))
    for n in notes:
        agent = str(n.get("author") or "")
        if not agent or not is_agent(agent):
            continue
        rec = get(agent)
        rec["notes"] += 1
        seen(rec, str(n.get("at") or ""))
    for rec in out.values():
        rec["sessions"] = len(rec["sessions"])
    return sorted(out.values(), key=lambda r: (-(r["commits"] + r["turns"] + r["notes"]), r["agent_id"]))


def detail(store: ViewStore, core_id: str) -> dict[str, Any]:
    """One core: its notes (oldest first), its links, the linked tasks with
    status, the files and commits of those tasks, the commits that touched
    its anchors, and the 30-day grid."""
    from . import taskwork
    core = core_of(store, core_id)
    if core is None:
        raise LookupError(core_id)
    notes = sorted((n for n in _rows(store, NOTES_FILE) if n.get("core_id") == core_id), key=lambda n: n.get("at") or "")
    links = [l for l in _rows(store, LINKS_FILE) if l.get("core_id") == core_id]
    task_ids = [l["target"] for l in links if l.get("kind") == "task"]
    tasks = _tasks_of(store, task_ids)
    files: dict[str, dict[str, Any]] = {}
    commits: dict[str, dict[str, Any]] = {}
    for tid in task_ids:
        try:
            work = taskwork.task_work(store, tid)
        except Exception:  # noqa: BLE001 — git is best effort
            continue
        for f in work.get("files") or []:
            rec = files.setdefault(f["path"], {"path": f["path"], "lines_add": 0, "lines_del": 0, "tasks": []})
            rec["lines_add"] += int(f.get("lines_add") or 0)
            rec["lines_del"] += int(f.get("lines_del") or 0)
            if tid not in rec["tasks"]:
                rec["tasks"].append(tid)
        for c in work.get("commit_list") or []:
            got = commits.setdefault(c["sha"], {**c, "tasks": []})
            if tid not in got["tasks"]:
                got["tasks"].append(tid)
    commit_list = sorted(commits.values(), key=lambda c: c.get("at") or "", reverse=True)
    anchors = [l["target"] for l in links if l.get("kind") == "anchor"]
    nearby = [c for c in _anchor_commits(store, str(core.get("project") or ""), anchors)
              if c["sha"] not in commits]
    days = [(_day(n.get("at")), "story") for n in notes]
    if task_ids:
        marks = ",".join("?" for _ in task_ids)
        for e in store.query(f"SELECT timestamp FROM task_events_mutual WHERE task_id IN ({marks})", tuple(task_ids)):
            days.append((_day(e.get("timestamp")), "story"))
    days.extend((_day(c["at"]), "nearby") for c in nearby)
    return {
        **core,
        "tracking": tracking_state(core),
        "notes": [{**n, "approved": bool(n.get("approved_at"))} for n in notes],
        "links": links,
        "tasks": tasks,
        "files": sorted(files.values(), key=lambda f: -(f["lines_add"] + f["lines_del"]))[:40],
        "commits_n": len(commit_list),
        # Every commit of the linked tasks once, newest first: how it is known
        # (signed · linked · chat), its agent, the core's tasks it is for, its files.
        "commits": commit_list[:400],
        "agents": _agents_of(store, task_ids, notes, commit_list),
        "nearby": nearby[:60],
        "grid": _grid(days),
        # What happened to the core itself: made, tracking on and off, out of view and back.
        "events": sorted((e for e in _rows(store, EVENTS_FILE) if e.get("core_id") == core_id), key=lambda e: e.get("at") or ""),
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _check_type(value: Any) -> str:
    kind = str(value or "").strip().lower()
    if kind not in CORE_TYPES:
        raise CoreRefused(f"type must be one of {', '.join(CORE_TYPES)}")
    return kind


def create(store: ViewStore, body: dict) -> dict[str, Any]:
    """A new core. ``{project, name, type, reason?, text?, position?, actor|agent_id,
    task_id?, session_id?, turn?, anchors?}``: ``text`` is the operator's message
    as typed and becomes the founding note; ``anchors`` are file or
    file:symbol paths the agent knows from the chat."""
    project = str(body.get("project") or "").strip()
    if not project or not (store.data_root / "projects" / project).is_dir():
        raise CoreRefused(f"project not found: {project!r}")
    name = " ".join(str(body.get("name") or "").split())
    if not name:
        raise CoreRefused("a core needs a name")
    if len(name) > NAME_MAX:
        raise CoreRefused(f"a core's name is at most {NAME_MAX} characters ({len(name)} sent)")
    kind = _check_type(body.get("type"))
    reason = str(body.get("reason") or "").strip()[:REASON_MAX]
    actor = identity_of(body) or "operator"
    same = next((c for c in _rows(store, CORES_FILE)
                 if c.get("project") == project and c.get("name", "").lower() == name.lower()
                 and c.get("status") == "view"), None)
    if same is not None:
        return {"core": same, "existing": True}
    now = now_iso()
    n = sum(1 for c in _rows(store, CORES_FILE) if c.get("project") == project)
    row = {
        "id": _mint("cr_", project, name), "project": project, "name": name, "type": kind, "reason": reason,
        "status": "view", "position": str(body.get("position") or n + 1),
        "tracking_on": "", "tracking_until": "", "created_at": now, "updated_at": now, "actor": actor, "off_at": "",
    }
    append_row(store.data_root / CORES_FILE, CORE_COLUMNS, row)
    _event(store, row["id"], "created", "", actor)
    text = str(body.get("text") or "").strip()
    if text:
        add_note(store, row["id"], {**body, "text": text, "kind": "founding", "comment": body.get("comment") or ""})
    for a in body.get("anchors") or []:
        link(store, row["id"], {"kind": "anchor", "target": str(a), "actor": actor})
    if body.get("task_id"):
        link(store, row["id"], {"kind": "task", "target": str(body["task_id"]), "actor": actor})
    return {"core": row, "existing": False}


def add_note(store: ViewStore, core_id: str, body: dict) -> dict[str, str]:
    """A note on the story. ``{text, comment?, kind?, task_id?, session_id?,
    turn?, actor|agent_id}``. The operator's own note is approved as written;
    an agent's waits for the operator. An agent's ``auto`` note needs
    tracking on."""
    core = core_of(store, core_id)
    if core is None:
        raise LookupError(core_id)
    if core.get("status") != "view":
        raise CoreRefused(f"{core_id} is out of view: bring it back on its page first")
    text = str(body.get("text") or "").strip()
    comment = str(body.get("comment") or "").strip()
    if not text and not comment:
        raise CoreRefused("a note needs its text")
    if len(text) > NOTE_MAX or len(comment) > NOTE_MAX:
        raise CoreRefused(f"a note is at most {NOTE_MAX} characters")
    kind = str(body.get("kind") or "note").strip().lower()
    if kind not in NOTE_KINDS:
        raise CoreRefused(f"kind must be one of {', '.join(NOTE_KINDS)}")
    actor = identity_of(body) or "operator"
    if kind == "auto":
        if not is_agent(actor):
            raise CoreRefused("an auto note is an agent's: the operator writes a note")
        if not tracking_state(core)["on"]:
            refuse_agent(f"tracking is off for {core['name']}", "notes on it come from the operator's #core-note; "
                         "the operator switches tracking on, on the core's page")
    now = now_iso()
    operator = not is_agent(actor)
    row = {
        "id": _mint("cn_", core_id, text, comment, now), "core_id": core_id, "at": now, "author": actor, "kind": kind,
        "text": text, "comment": comment, "task_id": str(body.get("task_id") or ""),
        "session_id": str(body.get("session_id") or ""), "turn": str(body.get("turn") or ""),
        "approved_at": now if operator else "", "approved_by": "operator" if operator else "",
    }
    append_row(store.data_root / NOTES_FILE, CORE_NOTE_COLUMNS, row)
    _touch(store, core_id)
    if row["task_id"]:
        link(store, core_id, {"kind": "task", "target": row["task_id"], "actor": actor})
    return row


def approve(store: ViewStore, core_id: str, note_id: str, body: dict) -> dict[str, str]:
    """The operator endorses an agent's note: the author and the words stay;
    the approval is added. Operator only."""
    if is_agent(identity_of(body)):
        refuse_agent("approving a note is the operator's")
    hit: list[dict[str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == note_id and r.get("core_id") == core_id:
                hit.append(r)
                if r.get("approved_at"):
                    return False
                r["approved_at"] = now_iso()
                r["approved_by"] = "operator"
                return True
        return False
    rewrite_rows(store.data_root / NOTES_FILE, CORE_NOTE_COLUMNS, mutate)
    if not hit:
        raise LookupError(note_id)
    return hit[0]


def link(store: ViewStore, core_id: str, body: dict) -> dict[str, str] | None:
    """Attach one thing: ``{kind, target, note?, actor|agent_id}``. The same
    target twice is one link."""
    kind = str(body.get("kind") or "").strip().lower()
    target = str(body.get("target") or "").strip()
    if kind not in LINK_KINDS:
        raise CoreRefused(f"kind must be one of {', '.join(LINK_KINDS)}")
    if not target:
        raise CoreRefused("a link needs its target")
    if kind == "anchor" and (".." in target or target.startswith(("/", "~"))):
        raise CoreRefused("an anchor is a path inside the project, as file or file:symbol")
    if kind == "task" and not store.query_one("SELECT id FROM tasks_mutual WHERE id = ?", (target,)):
        raise CoreRefused(f"task not found: {target}")
    if any(l.get("core_id") == core_id and l.get("kind") == kind and l.get("target") == target
           for l in _rows(store, LINKS_FILE)):
        return None
    row = {"id": _mint("cl_", core_id, kind, target), "core_id": core_id, "kind": kind, "target": target,
           "note": str(body.get("note") or "")[:200], "at": now_iso(), "actor": identity_of(body) or "operator"}
    append_row(store.data_root / LINKS_FILE, CORE_LINK_COLUMNS, row)
    _touch(store, core_id)
    return row


def unlink(store: ViewStore, core_id: str, link_id: str, body: dict) -> bool:
    if is_agent(identity_of(body)):
        refuse_agent("removing a link is the operator's")

    def mutate(rows: list[dict[str, str]]) -> bool:
        before = len(rows)
        rows[:] = [r for r in rows if not (r.get("id") == link_id and r.get("core_id") == core_id)]
        return len(rows) != before
    return rewrite_rows(store.data_root / LINKS_FILE, CORE_LINK_COLUMNS, mutate)


def update(store: ViewStore, core_id: str, body: dict) -> dict[str, str]:
    """The operator changes name, type, reason, position or status (view |
    off). An agent is refused."""
    if is_agent(identity_of(body)):
        refuse_agent("changing a core is the operator's", "an agent adds a note with core_note")
    changes: dict[str, str] = {}
    if "name" in body:
        name = " ".join(str(body.get("name") or "").split())
        if not name or len(name) > NAME_MAX:
            raise CoreRefused(f"a core's name is 1 to {NAME_MAX} characters")
        changes["name"] = name
    if "type" in body:
        changes["type"] = _check_type(body.get("type"))
    if "reason" in body:
        changes["reason"] = str(body.get("reason") or "").strip()[:REASON_MAX]
    if "position" in body:
        changes["position"] = str(body.get("position") or "")
    if "status" in body:
        status = str(body.get("status") or "").strip()
        if status not in CORE_STATUSES:
            raise CoreRefused(f"status must be one of {', '.join(CORE_STATUSES)}")
        changes["status"] = status
        changes["off_at"] = now_iso() if status == "off" else ""
    if not changes:
        raise CoreRefused("nothing to change: name, type, reason, position or status")
    before = core_of(store, core_id)
    out = _rewrite(store, core_id, changes)
    if "status" in changes and before is not None and before.get("status") != changes["status"]:
        _event(store, core_id, changes["status"], "", "operator")
    return out


def set_tracking(store: ViewStore, core_id: str, body: dict) -> dict[str, str]:
    """``{on, span?: day|week, until?: YYYY-MM-DD}`` — operator only. On with
    neither span nor until is tracking with no end."""
    if is_agent(identity_of(body)):
        refuse_agent("switching tracking is the operator's", "it is switched on the core's page")
    on = bool(body.get("on"))
    until = ""
    if on:
        span = str(body.get("span") or "").strip().lower()
        if span:
            if span not in TRACKING_SPANS:
                raise CoreRefused(f"span must be one of {', '.join(TRACKING_SPANS)}")
            until = (date.today() + timedelta(days=TRACKING_SPANS[span] - 1)).isoformat()
        elif body.get("until"):
            try:
                until = date.fromisoformat(str(body["until"])).isoformat()
            except ValueError:
                raise CoreRefused("until is a date, YYYY-MM-DD")
            if until < date.today().isoformat():
                raise CoreRefused("until is in the past")
    out = _rewrite(store, core_id, {"tracking_on": "1" if on else "", "tracking_until": until})
    _event(store, core_id, "tracking_on" if on else "tracking_off", until, "operator")
    return out


def off(store: ViewStore, core_id: str, body: dict) -> dict[str, str]:
    """Out of view (the operator's #core-off, run by the agent): the story
    and the links stay."""
    out = _rewrite(store, core_id, {"status": "off", "off_at": now_iso()})
    _event(store, core_id, "off", "", identity_of(body) or "operator")
    return out


def _rewrite(store: ViewStore, core_id: str, changes: dict[str, str]) -> dict[str, str]:
    hit: list[dict[str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == core_id:
                hit.append(r)
                before = dict(r)
                r.update(changes)
                r["updated_at"] = now_iso()
                return r != before
        return False
    rewrite_rows(store.data_root / CORES_FILE, CORE_COLUMNS, mutate)
    if not hit:
        raise LookupError(core_id)
    return hit[0]


def _touch(store: ViewStore, core_id: str) -> None:
    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == core_id:
                r["updated_at"] = now_iso()
                return True
        return False
    rewrite_rows(store.data_root / CORES_FILE, CORE_COLUMNS, mutate)


def _event(store: ViewStore, core_id: str, kind: str, value: str, actor: str) -> None:
    append_row(store.data_root / EVENTS_FILE, CORE_EVENT_COLUMNS, {
        "id": _mint("ce_", core_id, kind), "core_id": core_id, "at": now_iso(),
        "kind": kind, "value": value, "actor": actor})


# ---------------------------------------------------------------------------
# Tasks and cores
# ---------------------------------------------------------------------------


def task_index(store: ViewStore, project: str) -> dict[str, list[dict[str, str]]]:
    """Every task linked to a core of the project in view: task id → the
    cores (id, name, type). The board reads it once for all its cards."""
    cores = {c["id"]: c for c in _rows(store, CORES_FILE) if c.get("project") == project and c.get("status") == "view"}
    out: dict[str, list[dict[str, str]]] = {}
    for l in _rows(store, LINKS_FILE):
        c = cores.get(l.get("core_id") or "")
        if c is None or l.get("kind") != "task":
            continue
        out.setdefault(l["target"], []).append({"id": c["id"], "name": c.get("name") or "", "type": c.get("type") or ""})
    return out


def cores_of_task(store: ViewStore, task_id: str) -> list[dict[str, str]]:
    cores = {c["id"]: c for c in _rows(store, CORES_FILE)}
    out = []
    for l in _rows(store, LINKS_FILE):
        if l.get("kind") == "task" and l.get("target") == task_id and l.get("core_id") in cores:
            c = cores[l["core_id"]]
            out.append({"id": c["id"], "name": c.get("name") or "", "type": c.get("type") or "",
                        "status": c.get("status") or "", "link_id": l["id"]})
    return out


def set_task_cores(store: ViewStore, task_id: str, body: dict) -> list[dict[str, str]]:
    """The operator sets which cores a task belongs to: ``{cores: [id …]}``.
    Links missing are added, links not named are removed. An agent attaches
    with core_attach instead."""
    if is_agent(identity_of(body)):
        refuse_agent("setting a task's cores is the operator's", "an agent attaches a task with core_attach")
    if not store.query_one("SELECT id FROM tasks_mutual WHERE id = ?", (task_id,)):
        raise LookupError(task_id)
    raw = body.get("cores")
    if not isinstance(raw, list):
        raise CoreRefused("cores is a list of core ids")
    wanted = [str(c) for c in raw if str(c).strip()]
    known = {c["id"] for c in _rows(store, CORES_FILE)}
    missing = [c for c in wanted if c not in known]
    if missing:
        raise CoreRefused(f"core not found: {', '.join(missing)}")
    now = now_iso()

    # One read-modify-write under the ledger's lock: the old set is replaced
    # by the new one whole, never half (a failed add after a remove), and two
    # windows saving at once each see the other's result.
    def mutate(rows: list[dict[str, str]]) -> bool:
        mine = [r for r in rows if r.get("kind") == "task" and r.get("target") == task_id]
        keep_ids = {r["id"] for r in mine if r.get("core_id") in wanted}
        before = len(rows)
        rows[:] = [r for r in rows if not (r.get("kind") == "task" and r.get("target") == task_id) or r["id"] in keep_ids]
        have = {r["core_id"] for r in mine if r["id"] in keep_ids}
        added = [cid for cid in dict.fromkeys(wanted) if cid not in have]
        for cid in added:
            rows.append({"id": _mint("cl_", cid, "task", task_id), "core_id": cid, "kind": "task", "target": task_id,
                         "note": "", "at": now, "actor": "operator"})
        return len(rows) != before or bool(added)
    changed = rewrite_rows(store.data_root / LINKS_FILE, CORE_LINK_COLUMNS, mutate)
    if changed:
        for cid in set(wanted):
            _touch(store, cid)
    return cores_of_task(store, task_id)


# ---------------------------------------------------------------------------
# The timeline: one lane per core, day by day
# ---------------------------------------------------------------------------


def _iso_of_yymm(s: str) -> str:
    """``2610-24`` (the ledgers' day) → ``2026-10-24``; '' when it is not one."""
    s = str(s or "").strip()
    if len(s) >= 7 and s[4] == "-" and s[:4].isdigit() and s[5:7].isdigit():
        return f"20{s[:2]}-{s[2:4]}-{s[5:7]}"
    return ""


def _releases(store: ViewStore, project: str, first: str, last: str) -> list[dict[str, str]]:
    """The project's release tags (``v…``) in the range, from its repository."""
    from . import gitwork
    from .file_entries import project_repo
    repo = project_repo(store, project)
    if repo is None:
        return []
    raw = gitwork.git(repo, "tag", "-l", "v*", "--format=%(refname:short)\t%(creatordate:short)") or ""
    out = []
    for line in raw.splitlines():
        name, _, day = line.partition("\t")
        if first <= day <= last:
            out.append({"name": name.strip(), "day": day.strip()})
    return sorted(out, key=lambda r: r["day"])


def _spans(events: list[dict[str, str]], core: dict[str, str], first: str, last: str) -> list[dict[str, str]]:
    """When tracking was on, as day spans clipped to the range. A core with no
    recorded switch but tracking on now counts from its creation."""
    spans: list[dict[str, str]] = []
    start: str | None = None
    end_at = ""
    for e in sorted(events, key=lambda e: e.get("at") or ""):
        day = _day(e.get("at"))
        if e.get("kind") == "tracking_on":
            if start is not None:
                spans.append({"from": start, "to": min(day, end_at or day)})
            start, end_at = day, str(e.get("value") or "")
        elif e.get("kind") == "tracking_off" and start is not None:
            spans.append({"from": start, "to": min(day, end_at or day)})
            start = None
    if start is None and not events and tracking_state(core)["on"]:
        start, end_at = _day(core.get("created_at")), str(core.get("tracking_until") or "")
    if start is not None:
        spans.append({"from": start, "to": min(end_at or last, last)})
    out = [{"from": max(s["from"], first), "to": min(s["to"], last)} for s in spans if s["to"] >= first and s["from"] <= last]
    return [s for s in out if s["from"] <= s["to"]]


def timeline(store: ViewStore, project: str, days: int = 30) -> dict[str, Any]:
    """The project's cores over the last ``days`` days, one lane each: per day
    the notes (yours and agents'), the linked tasks made and done, the
    commits of those tasks, and the commits in the core's files that no
    linked task made. Above them, the day's standup and the release tags."""
    from . import taskwork
    days = max(7, min(int(days or 30), 120))
    today = date.today()
    first_d = today - timedelta(days=days - 1)
    first, last = first_d.isoformat(), today.isoformat()
    all_days = [(first_d + timedelta(days=i)).isoformat() for i in range(days)]

    standups: dict[str, dict[str, str]] = {}
    for r in store.query("SELECT id, l1, for_date, created_date FROM standups_mutual WHERE project = ?", (project,)):
        day = _iso_of_yymm(str(r.get("for_date") or r.get("created_date") or ""))
        if first <= day <= last:
            standups[day] = {"id": str(r.get("id") or ""), "summary": str(r.get("l1") or "")}

    cores = [c for c in _rows(store, CORES_FILE) if c.get("project") == project and c.get("status") == "view"]
    notes = _rows(store, NOTES_FILE)
    links = _rows(store, LINKS_FILE)
    events = _rows(store, EVENTS_FILE)
    lanes = []
    for c in cores:
        cid = c["id"]
        by_day: dict[str, dict[str, list[dict[str, Any]]]] = {}

        def put(day: str, key: str, item: dict[str, Any], by_day: dict = by_day) -> None:
            if first <= day <= last:
                by_day.setdefault(day, {}).setdefault(key, []).append(item)

        for n in notes:
            if n.get("core_id") != cid:
                continue
            operator = not is_agent(n.get("author") or "")
            put(_day(n.get("at")), "notes", {
                "id": n["id"], "at": n.get("at") or "", "kind": n.get("kind") or "", "operator": operator, "approved": bool(n.get("approved_at")),
                "text": (n.get("comment") if not operator and n.get("comment") else n.get("text") or n.get("comment") or "")[:200],
                "author": n.get("author") or ""})
        task_ids = [l["target"] for l in links if l.get("core_id") == cid and l.get("kind") == "task"]
        titles = {t["id"]: t for t in _tasks_of(store, task_ids)}
        seen: set[str] = set()
        for tid in task_ids:
            t = titles.get(tid)
            if t is None:
                continue
            made = _iso_of_yymm(str(t.get("created_date") or ""))
            put(made, "made", {"id": tid, "title": t.get("title") or "", "at": made + "T" + (str(t.get("created_time") or "00:00") + ":00")[:8]})
            try:
                work = taskwork.task_work(store, tid)
            except Exception:  # noqa: BLE001 — git is best effort
                work = {"commit_list": []}
            for cm in work.get("commit_list") or []:
                if cm["sha"] in seen:
                    continue
                seen.add(cm["sha"])
                put(_day(cm["at"]), "commits", {**cm, "task_id": tid})
        if task_ids:
            marks = ",".join("?" for _ in task_ids)
            for e in store.query(
                    f"SELECT task_id, timestamp, new_value FROM task_events_mutual WHERE field = 'status' AND task_id IN ({marks})",
                    tuple(task_ids)):
                if str(e.get("new_value") or "") == "done" and e.get("task_id") in titles:
                    put(_day(e.get("timestamp")), "done", {"id": e["task_id"], "title": titles[e["task_id"]].get("title") or "", "at": str(e.get("timestamp") or "")})
        anchors = [l["target"] for l in links if l.get("core_id") == cid and l.get("kind") == "anchor"]
        for cm in _anchor_commits(store, project, anchors):
            if cm["sha"] not in seen:
                put(_day(cm["at"]), "nearby", cm)
        mine = [e for e in events if e.get("core_id") == cid]
        lanes.append({
            "id": cid, "name": c.get("name") or "", "type": c.get("type") or "", "reason": c.get("reason") or "",
            "tracking": tracking_state(c), "tracking_spans": _spans(mine, c, first, last),
            "created": _day(c.get("created_at")),
            "days": by_day,
            "totals": {k: sum(len(v.get(k, [])) for v in by_day.values()) for k in ("notes", "made", "done", "commits", "nearby")},
        })
    lanes.sort(key=lambda l: (not l["tracking"]["on"], -sum(l["totals"].values()), l["name"].lower()))
    return {"project": project, "first": first, "last": last, "days": all_days,
            "standups": standups, "releases": _releases(store, project, first, last), "lanes": lanes}


# ---------------------------------------------------------------------------
# Cores over the map of the program
# ---------------------------------------------------------------------------


def _held_by_tasks(per_task: list[set[str]], where: str, under: Any) -> bool:
    """Two or more of the core's tasks, and at least half of them, changed
    files under ``where``."""
    n = sum(1 for fs in per_task if any(under(f, where) for f in fs))
    return n >= TASKS_TO_CLAIM and n * 2 >= len(per_task)


def map_overlay(store: ViewStore, project: str) -> dict[str, Any]:
    """The current map's rows, each with the cores that claim it and how: a
    map link the operator set (``linked``), an anchor of the core under the
    row's path (``files``), or a file a linked task changed under it
    (``tasks``). Rows no core claims are counted."""
    from . import repomap, taskwork
    cur = repomap.current(store, project)
    rows = list(((cur or {}).get("map") or {}).get("rows") or [])
    cores = [c for c in _rows(store, CORES_FILE) if c.get("project") == project and c.get("status") == "view"]
    links = _rows(store, LINKS_FILE)
    claims: dict[str, dict[str, str]] = {}   # row name → core id → how
    link_ids: dict[tuple[str, str], str] = {}  # (row name, core id) → the map link
    order = {"linked": 0, "files": 1, "tasks": 2}

    def claim(row: str, cid: str, how: str) -> None:
        held = claims.setdefault(row, {})
        if cid not in held or order[how] < order[held[cid]]:
            held[cid] = how

    def under(path: str, where: str) -> bool:
        w = where.strip().rstrip("/")
        return bool(w) and (path == w or path.startswith(w + "/") or w.startswith(path.rstrip("/") + "/"))

    for c in cores:
        mine = [l for l in links if l.get("core_id") == c["id"]]
        for l in mine:
            if l.get("kind") == "map":
                claim(l["target"], c["id"], "linked")
                link_ids[(l["target"], c["id"])] = l["id"]
        anchors = [l["target"].split(":", 1)[0] for l in mine if l.get("kind") == "anchor"]
        per_task: list[set[str]] = []
        for l in mine:
            if l.get("kind") == "task":
                try:
                    per_task.append({f["path"] for f in taskwork.task_work(store, l["target"]).get("files") or []})
                except Exception:  # noqa: BLE001
                    pass
        for r in rows:
            where = str(r.get("where") or "")
            if not where or where.startswith("http"):
                continue
            if any(under(a, where) for a in anchors):
                claim(str(r.get("name") or ""), c["id"], "files")
            # One task that touched half the program says little: a row is the
            # core's by its tasks when two or more of them changed it.
            elif str(r.get("kind") or "") in TASK_CLAIM_KINDS and _held_by_tasks(per_task, where, under):
                claim(str(r.get("name") or ""), c["id"], "tasks")
    out_rows = []
    for r in rows:
        name = str(r.get("name") or "")
        held = claims.get(name, {})
        out_rows.append({"kind": r.get("kind") or "", "name": name, "what": r.get("what") or "", "where": r.get("where") or "",
                         "cores": [{"id": cid, "how": how, **({"link_id": link_ids[(name, cid)]} if (name, cid) in link_ids else {})}
                                   for cid, how in sorted(held.items(), key=lambda kv: order[kv[1]])]})
    return {
        "project": project, "version": (cur or {}).get("n"), "template": ((cur or {}).get("map") or {}).get("template") or "",
        "rows": out_rows,
        "cores": [{"id": c["id"], "name": c.get("name") or "", "type": c.get("type") or "",
                   "rows": sum(1 for r in out_rows if any(x["id"] == c["id"] for x in r["cores"]))} for c in cores],
        "unclaimed": sum(1 for r in out_rows if not r["cores"]),
    }


# ---------------------------------------------------------------------------
# For the hook: the tracked cores, read from the file alone (no store)
# ---------------------------------------------------------------------------


def tracked(data_root: Path, project: str) -> list[dict[str, str]]:
    """The cores of ``project`` with tracking on and not expired, as the
    capture hook tells the agent on its first turn (one reader: hookshared)."""
    from .hookshared import tracked_cores
    return tracked_cores(data_root, project)
