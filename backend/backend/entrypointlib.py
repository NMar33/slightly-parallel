"""Entry points: the outside of a project — a topic the operator opens and
comes back to (the films and the launch, the site's texts), with what an
agent needs to pick it up. Cores are the inside.

An entry point is the kept ``entrypoint`` row (keeplib: the operator's
``#entrypoint`` message, the record an agent writes from it in versions)
plus four ledgers at the data root (entities.ENTRYPOINT_*):

- ``entrypoint_ways.csv`` — its ways in: what the operator opens (a page, a
  site, an app, a file, a folder, a script, an artifact), each with where it
  opens, the command that starts it, the folder, the port;
- ``entrypoint_stops.csv`` — "where it stopped": a feed of short messages,
  the operator's or an agent's (one at ``#done`` for a task of the topic);
- ``entrypoint_shots.csv`` — screenshots of the ways in, a series per way,
  each with the chat it was taken in; the files under ``entrypoint_shots/``;
- ``task_topics.csv`` — a task's topic, one row per task.

"What is next" is not stored: it is the topic's open tasks.

What the server computes on read: the desk (every topic of a project with
what its tile shows), and one topic's context — the chats before and after,
the tasks open and done with their reports, the decisions, commits and
files, artifacts and Publish cards, the spend, and the briefing text that
"Copy to agent" gives. A topic's project scopes every one of those: a task,
chat or decision of another project never enters.

Who writes what: the operator everything on the page (name, state, ways in,
stops, shots, a task's topic); an agent, through the MCP tools, only a stop,
a way in (added or changed, never removed), a shot and a task's topic.

The record is written by an agent only after the operator's ``#entrypoint``
in its chat. A topic lives long and many chats work on it, so the command
typed in another chat of the project with the topic's name makes no second
entry point: it opens a new version of that topic's record, and the agent
of that chat writes it (``entrypoint_commands.csv``: each command and the
topic it opened). The chat of the topic's last command is the one that
writes; every version is kept with the chat that wrote it
(``entrypoint_versions.csv``).
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import ipaddress
import json
import re
import socket
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from . import limits, memberships
from .actors import identity_of, is_agent
from .csvio import append_if_absent, append_row, as_int, read_rows, rewrite_rows
from .date_utils import as_local, iso_moment, now_iso
from .db import ViewStore
from .docs_md import read_detail, resolve_under
from .entities import (
    ENTITIES, ENTRYPOINT_COMMAND_COLUMNS, ENTRYPOINT_NAME_COLUMNS, ENTRYPOINT_SHOT_COLUMNS, ENTRYPOINT_STATES, ENTRYPOINT_STOP_COLUMNS,
    ENTRYPOINT_VERSION_COLUMNS, ENTRYPOINT_WAY_COLUMNS, ENTRYPOINT_WAY_KINDS, TASK_TOPIC_COLUMNS, is_done,
)
from .file_safety import acquire_flock, atomic_write, lock_path

WAYS_FILE = "entrypoint_ways.csv"
STOPS_FILE = "entrypoint_stops.csv"
SHOTS_FILE = "entrypoint_shots.csv"
TOPICS_FILE = "task_topics.csv"
COMMANDS_FILE = "entrypoint_commands.csv"
AUTHORS_FILE = "entrypoint_versions.csv"
NAMES_FILE = "entrypoint_names.csv"
SHOTS_DIR = "entrypoint_shots"

NAME_MAX = 80
STOP_MAX = 1000
CAPTION_MAX = 200
COMMAND_MAX = 500
URL_MAX = 2000
PATH_MAX = 1000
NOTE_MAX = 200
WAYS_MAX = 30
STOPS_SHOWN = 5
CONTEXT_TASKS = 40
PORT_TIMEOUT_S = 0.3
PORT_DEADLINE_S = 1.0
PORT_PROBES_MAX = 20
# Host spellings that mean this computer. Mapped to a loopback address
# without asking DNS: a name that resolves elsewhere is never connected to.
LOCAL_HOSTS: dict[str, str] = {
    "localhost": "localhost", "127.0.0.1": "127.0.0.1", "0.0.0.0": "127.0.0.1",
    "::1": "::1", "[::1]": "::1", "ip6-localhost": "::1",
}


class EntryRefused(ValueError):
    """A write the server will not make; answered as 422 with the sentence."""


def _mint(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


def _rows(store_or_root: Any, name: str) -> list[dict[str, str]]:
    root = Path(getattr(store_or_root, "data_root", store_or_root))
    return read_rows(root / name)


def _live(r: dict[str, str]) -> bool:
    return not str(r.get("removed_at") or "").strip()


# ---------------------------------------------------------------------------
# The entry point row
# ---------------------------------------------------------------------------


def entry_of(store: ViewStore, ep_id: str) -> dict[str, str] | None:
    """The row, read from the file (a row written a moment ago is there)."""
    if not str(ep_id or "").startswith("ep_"):
        return None
    return next((r for r in read_rows(store.data_root / ENTITIES["entrypoint"].csv) if r.get("id") == ep_id), None)


def state_of(row: dict[str, Any]) -> str:
    """active · paused · dead. A row written before states (or by the old
    page, which knows only open/closed) reads from its status."""
    st = str(row.get("state") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if st in ENTRYPOINT_STATES:
        # set_state writes status open exactly when active. A status changed
        # since through the generic update (update_entry) wins: closed is
        # paused, open again is active.
        if st == "active" and status == "closed":
            return "paused"
        if st != "active" and status == "open":
            return "active"
        return st
    return "paused" if status == "closed" else "active"


def name_of(row: dict[str, Any]) -> str:
    """The operator's name for the topic; "" when none is written yet."""
    return " ".join(str(row.get("topic") or "").split())


def record_of(store: ViewStore, row: dict[str, Any]) -> str:
    """The current record (What / Where / How / State / Next), or ""."""
    try:
        l2, _l3, _l4 = read_detail(store.data_root, str(row.get("md_ref") or ""))
    except (OSError, UnicodeDecodeError):
        return ""
    return (l2 or "").strip()


_SECTION = re.compile(r"^#{1,6}\s*(\w+)[^\n]*\n", re.M)


def sections(text: str) -> dict[str, str]:
    """The record cut at its headings: {"What": body, …} (first wins)."""
    out: dict[str, str] = {}
    text = (text or "").replace("\r", "")
    marks = list(_SECTION.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.setdefault(m.group(1), text[m.end():end].strip())
    return out


def what_of(record: str) -> str:
    """The first paragraph of the record's What, one line."""
    return what_paragraph(record)[:600]


def what_paragraph(record: str) -> str:
    """The first paragraph of the record's What, whole, on one line."""
    body = sections(record).get("What", "").strip()
    return " ".join(body.split("\n\n", 1)[0].split())


_SENTENCE = re.compile(r"^(.+?[.!?…])(?=\s|$)")


def what_sentence(record: str) -> str:
    """The first sentence of the record's What: what an unnamed topic is
    called by, instead of the first line of the message it was kept from."""
    para = what_paragraph(record)
    m = _SENTENCE.match(para)
    return _clip(m.group(1) if m else para, 160)


def label_of(store: ViewStore, row: dict[str, Any], record: str | None = None) -> str:
    """The topic as a person reads it: its name; unnamed, the first sentence
    of its record's What; with no record yet, the first line it was kept from."""
    return name_of(row) or what_sentence(record_of(store, row) if record is None else record) or _title(row)


def ways_of(store: Any, ep_id: str) -> list[dict[str, str]]:
    rows = [r for r in _rows(store, WAYS_FILE) if r.get("entrypoint_id") == ep_id and _live(r)]
    return sorted(rows, key=lambda r: (as_int(r.get("position"), 0), r.get("created_at") or ""))


def stops_of(store: Any, ep_id: str) -> list[dict[str, str]]:
    """The feed, newest first."""
    rows = [r for r in _rows(store, STOPS_FILE) if r.get("entrypoint_id") == ep_id and _live(r)]
    return sorted(rows, key=lambda r: r.get("at") or "", reverse=True)


def shots_of(store: Any, ep_id: str) -> list[dict[str, str]]:
    """The screenshots in use (a replaced one is out), oldest first."""
    rows = [r for r in _rows(store, SHOTS_FILE) if r.get("entrypoint_id") == ep_id and _live(r)]
    return sorted(rows, key=lambda r: r.get("at") or "")


def topics_by_task(store: Any) -> dict[str, str]:
    """task id → entry point id (the last row for a task wins)."""
    out: dict[str, str] = {}
    for r in _rows(store, TOPICS_FILE):
        tid = str(r.get("task_id") or "")
        if tid:
            out[tid] = str(r.get("entrypoint_id") or "")
    return {k: v for k, v in out.items() if v}


def in_project(task: dict[str, Any], project: str) -> bool:
    """A task's home project, or one of the projects it is a member of."""
    if str(task.get("project") or "") == project:
        return True
    return project in [p.strip() for p in str(task.get("projects") or "").split(",") if p.strip()]


def tasks_of_topic(store: ViewStore, row: dict[str, Any]) -> list[dict[str, Any]]:
    """The topic's tasks, of its project only, newest first."""
    ep_id = str(row["id"])
    ids = [t for t, e in topics_by_task(store).items() if e == ep_id]
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = store.query(
        "SELECT id, title, status, project, projects, archived_at, created_date, created_time, agent_done_note, "
        f"agent_done_at, agent_done_by FROM tasks_mutual WHERE id IN ({marks})", tuple(ids))
    project = str(row.get("project") or "")
    rows = [r for r in rows if in_project(r, project)]
    return sorted(rows, key=lambda r: (str(r.get("created_date") or ""), str(r.get("created_time") or "")), reverse=True)


def topic_of_task(store: ViewStore, task_id: str) -> dict[str, Any] | None:
    """{id, name, state} of the task's topic, when its project matches."""
    ep_id = topics_by_task(store).get(task_id)
    if not ep_id:
        return None
    row = entry_of(store, ep_id)
    task = store.query_one("SELECT project, projects FROM tasks_mutual WHERE id = ?", (task_id,))
    if row is None or task is None or not in_project(task, str(row.get("project") or "")):
        return None
    return {"id": ep_id, "name": label_of(store, row), "state": state_of(row)}


def _title(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("l1") or "").split())[:NAME_MAX]


# ---------------------------------------------------------------------------
# Shapes — checked before anything is written
# ---------------------------------------------------------------------------


def _text(body: dict, key: str, most: int, *, required: bool = False, what: str = "") -> str:
    raw = body.get(key)
    label = what or key
    if raw is None or raw == "":
        if required:
            raise EntryRefused(f"{label} is required")
        return ""
    if not isinstance(raw, str):
        kind = "a list" if isinstance(raw, list) else "an object" if isinstance(raw, dict) else type(raw).__name__
        raise EntryRefused(f"{label} is text, not {kind}")
    value = raw.strip()
    if required and not value:
        raise EntryRefused(f"{label} is required")
    if len(value) > most:
        raise EntryRefused(f"{label} is at most {most} characters")
    return value


def _port(raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise EntryRefused("port is a whole number from 1 to 65535")
    s = str(raw).strip()
    if not s.isdigit() or not 1 <= int(s) <= 65535:
        raise EntryRefused("port is a whole number from 1 to 65535")
    return str(int(s))


def _body(body: Any) -> dict:
    if not isinstance(body, dict):
        raise EntryRefused("send the body as a JSON object")
    return body


def checked_way(raw: Any) -> dict[str, str]:
    """A way in from a request, every field checked; nothing written yet."""
    if not isinstance(raw, dict):
        raise EntryRefused("way is an object: {name, kind, url?, path?, command?, folder?, port?, note?}")
    kind = _text(raw, "kind", 20, required=True).lower()
    if kind not in ENTRYPOINT_WAY_KINDS:
        raise EntryRefused(f"kind is one of {', '.join(ENTRYPOINT_WAY_KINDS)}")
    url = _text(raw, "url", URL_MAX)
    if url and not url.lower().startswith(("http://", "https://")):
        raise EntryRefused("url starts with http:// or https://")
    way = {
        "name": _text(raw, "name", NAME_MAX, required=True),
        "kind": kind,
        "url": url,
        "path": _text(raw, "path", PATH_MAX),
        "command": _text(raw, "command", COMMAND_MAX),
        "folder": _text(raw, "folder", PATH_MAX),
        "port": _port(raw.get("port")),
        "note": _text(raw, "note", NOTE_MAX),
    }
    if not (way["url"] or way["path"] or way["command"]):
        raise EntryRefused("a way in needs where it opens (url or path) or the command that starts it")
    for k in ("name", "command", "note"):
        if "\n" in way[k]:
            raise EntryRefused(f"{k} is one line")
    return way


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _need(store: ViewStore, ep_id: str) -> dict[str, str]:
    row = entry_of(store, ep_id)
    if row is None or str(row.get("archived_at") or "").strip():
        raise LookupError(ep_id)
    return row


def _last_turn(store: ViewStore, agent: str) -> int:
    """The chat's last captured turn: where an agent's write was made."""
    best = 0
    for s in store.query("SELECT turns_json FROM sessions WHERE agent_id = ?", (agent,)):
        try:
            for t in json.loads(s.get("turns_json") or "[]"):
                best = max(best, as_int((t or {}).get("n")))
        except (ValueError, TypeError, AttributeError):
            continue
    return best


def _member_of_row(store: ViewStore, row: dict[str, Any], who: str, what: str = "topic") -> None:
    """An agent writes on a topic (or a task) of its member projects only."""
    if not is_agent(who):
        return
    from .entitylib import project_codes
    ok, line = memberships.may_write_row(store, who, str(row.get("project") or ""), what,
                                         also=project_codes(row.get("projects")))
    if not ok:
        raise EntryRefused(line)


# ---------------------------------------------------------------------------
# The #entrypoint command: the topic the operator chooses
# ---------------------------------------------------------------------------

# Where an operator's line stops naming the topic and starts saying more:
# "#entrypoint the install film: put the video work in".
_NAME_END = re.compile(r"\s*(?::|\s[—–-]\s)")
# A command's ``how``: pending (the operator has not chosen yet), name (the
# exact name of a named topic: a new version at once), chosen (the operator
# chose an existing topic: a new version), new (the operator chose a new
# topic: made then), dropped (the answer chose nothing).
OPENS_VERSION = ("name", "chosen")


def name_key(text: str) -> str:
    """A name compared: lower case, ``ё`` as ``е``, only letters and digits."""
    low = str(text or "").lower().replace("ё", "е")
    return " ".join(re.findall(r"[^\W_]+", low))


def _name_forms(text: str) -> list[str]:
    """The line, and its head before a colon or a dash, when it has one."""
    line = " ".join(str(text or "").split()).rstrip("…")
    head = _NAME_END.split(line, maxsplit=1)[0]
    return [x for x in dict.fromkeys((line, head)) if x.strip()]


def same_name(line: str, name: str) -> bool:
    """The operator's line names this topic exactly: the line, or its head
    before a colon or a dash, equals the name once case and punctuation are
    out. No stems, no stop words, no likeness: a near name is a question."""
    key = name_key(name)
    return bool(key) and any(name_key(x) == key for x in _name_forms(line))


def topic_named(store: ViewStore, project: str, line: str) -> dict[str, str] | None:
    """The project's one named topic the line names exactly; None when none
    does or when two do (the operator then chooses)."""
    if not project or not str(line or "").strip():
        return None
    hits = [r for r in entries(store, project) if name_of(r) and same_name(line, name_of(r))]
    return hits[0] if len(hits) == 1 else None


def commands(store: Any) -> list[dict[str, str]]:
    return _rows(store, COMMANDS_FILE)


def command_of(store: Any, cmd_id: str) -> dict[str, str] | None:
    return next((c for c in commands(store) if c.get("id") == cmd_id), None)


def take_command(store: ViewStore, *, kid: str, project: str, agent: str, session_id: str, turn: int,
                 at: str, name: str) -> dict[str, str]:
    """An operator's #entrypoint, seen once (keeplib.adopt). It makes no
    topic: it is kept as pending until the operator chooses one
    (entrypointask.py). Only the exact name of one named topic of the
    project opens a new version of that topic at once."""
    same = topic_named(store, project, name)
    rec = {"id": kid, "entrypoint_id": same["id"] if same else "", "project": project, "agent_id": agent,
           "session_id": session_id, "turn": str(turn), "at": at, "name": name[:NAME_MAX],
           "how": "name" if same else "pending", "asked": "", "chosen_at": at if same else ""}
    known = append_if_absent(store.data_root / COMMANDS_FILE, ENTRYPOINT_COMMAND_COLUMNS, rec)
    return known if known is not None else rec


def resolve_command(store: ViewStore, cmd_id: str, *, ep_id: str, how: str, at: str) -> None:
    """The operator's choice, written on the command."""
    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == cmd_id:
                changed = (r.get("entrypoint_id"), r.get("how")) != (ep_id, how)
                r.update({"entrypoint_id": ep_id, "how": how, "chosen_at": r.get("chosen_at") or at})
                return changed
        return False
    rewrite_rows(store.data_root / COMMANDS_FILE, ENTRYPOINT_COMMAND_COLUMNS, mutate)


def resolve(store: ViewStore, item_id: str) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    """(the topic, the command) an id names: a topic's own id, or the id the
    hook named for a command that opened a version of another topic. A
    command still pending names no topic."""
    row = entry_of(store, item_id)
    cmd = command_of(store, item_id)
    if row is None and cmd is not None and cmd.get("entrypoint_id"):
        row = entry_of(store, str(cmd.get("entrypoint_id") or ""))
    return row, cmd


def _when(c: dict[str, str]) -> tuple[str, int]:
    # When the topic was chosen: a command answered later hands the record
    # on later, whenever it was typed.
    return (str(c.get("chosen_at") or c.get("at") or ""), as_int(c.get("turn")))


def last_command(store: ViewStore, row: dict[str, Any]) -> dict[str, str]:
    """The topic's newest #entrypoint: its chat writes the record. A topic
    kept before commands were written down reads its own message."""
    mine = [c for c in commands(store) if c.get("entrypoint_id") == row["id"] and c.get("how") != "dropped"]
    if mine:
        return max(mine, key=_when)
    return {"id": str(row["id"]), "entrypoint_id": str(row["id"]), "agent_id": str(row.get("agent_id") or ""),
            "turn": str(row.get("source_turn") or ""), "how": "new", "asked": ""}


def may_write_record(store: ViewStore, row: dict[str, Any], who: str) -> dict[str, str]:
    """The command an agent's version answers. Refused for a topic of
    another project, and for a chat other than the one the operator typed
    the topic's last #entrypoint in."""
    _member_of_row(store, row, who)
    last = last_command(store, row)
    if last.get("agent_id") != who:
        raise EntryRefused(
            f"the record of {row['id']} is written right after the operator's #entrypoint, by the chat it was "
            f"typed in; the last one was in {last.get('agent_id') or 'another chat'}. Here, add a message with "
            f"entrypoint_stop or a way in with entrypoint_way; for a new version of the record from this chat, "
            f"the operator types #entrypoint here and chooses this topic. Nothing was written")
    return last


def note_version(store: ViewStore, ep_id: str, n: int, at: str, who: str, command_id: str) -> None:
    rec = {"id": f"{ep_id}#{n}", "entrypoint_id": ep_id, "n": str(n), "at": at,
           "agent_id": who if is_agent(who) else "operator", "command_id": command_id}
    append_if_absent(store.data_root / AUTHORS_FILE, ENTRYPOINT_VERSION_COLUMNS, rec)


def authors(store: Any, row: dict[str, Any]) -> dict[int, dict[str, str]]:
    """n → {by, command} for each version; a version written before this
    was recorded reads as the keeping chat's (interpreted) or the operator's."""
    out: dict[int, dict[str, str]] = {}
    for r in _rows(store, AUTHORS_FILE):
        if r.get("entrypoint_id") == row["id"]:
            out[as_int(r.get("n"))] = {"by": str(r.get("agent_id") or ""), "command": str(r.get("command_id") or "")}
    return out


def by_of(row: dict[str, Any], version: dict[str, Any], known: dict[int, dict[str, str]]) -> dict[str, str]:
    got = known.get(as_int(version.get("n")))
    if got:
        return got
    if version.get("how") == "interpreted":
        return {"by": str(row.get("agent_id") or ""), "command": str(row["id"])}
    return {"by": "operator", "command": ""}


def command_view(store: ViewStore, item_id: str) -> dict[str, Any]:
    """What an #entrypoint opened, for the agent of the chat it was typed in:
    the topic, the record as it is, who writes, and what to write. A command
    the operator has not answered yet opened nothing (``opened`` pending)."""
    row, cmd = resolve(store, item_id)
    if row is None and cmd is not None and cmd.get("how") in ("pending", "dropped"):
        pending = cmd.get("how") == "pending"
        return {
            "id": "", "command": str(cmd.get("id") or ""), "name": "", "project": cmd.get("project") or "",
            "opened": "pending" if pending else "nothing", "writer": "", "versions": 0, "record": "",
            "next": (f"Nothing is made until the operator chooses the topic. Call entrypoint_ask "
                     f'{{id: "{cmd.get("id")}", name}} and give its `show` exactly as given, every line, as the '
                     "end of your reply."
                     if pending else "The operator's answer chose no topic: nothing was made. Write nothing."),
        }
    if row is None:
        raise LookupError(item_id)
    if cmd is None or cmd.get("id") == row["id"]:
        cmd = last_command(store, row)  # a topic's own id: its last command
    record = record_of(store, row)
    name = label_of(store, row, record)
    n = as_int(row.get("versions_n"))
    ep_id = row["id"]
    write = f'interpret {{lens: "entrypoint", id: "{ep_id}", text, note}}'
    version = cmd.get("how") in OPENS_VERSION
    if version:
        nxt = (f"This #entrypoint opened version {n + 1} of the record of «{name}» ({ep_id}), a topic of this "
               f"project. Write it with {write}: start from the record below; add to Where and How what this "
               f"chat used (keep every line there), replace State with where the work stops now, and keep What "
               f"and Next unless this chat changed them. Do not make a new entry point.")
        if cmd.get("how") == "name":
            nxt += (f" The operator typed the topic's exact name, so nothing was asked: say in one line that this "
                    f"is a new version of «{name}».")
    elif record:
        nxt = (f"Write the next version with {write}: start from the record below, add to Where and How, "
               f"replace State.")
    else:
        nxt = (f"A new entry point, «{name}». Write its record with {write}: What, Where, How, State, Next.")
    return {
        "id": ep_id, "command": str(cmd.get("id") or ""), "name": name, "project": row.get("project") or "",
        "opened": "version" if version else "new",
        "writer": last_command(store, row).get("agent_id") or "",
        "versions": n, "record": record,
        "next": nxt,
    }


def add_stop(store: ViewStore, ep_id: str, body: Any) -> dict[str, Any]:
    """One "where it stopped" message. The same text by the same author for
    the same task is the same message (a repeated call adds nothing)."""
    body = _body(body)
    row = _need(store, ep_id)
    text = _text(body, "text", STOP_MAX, required=True)
    task_id = _text(body, "task_id", 40)
    who = identity_of(body) or "operator"
    _member_of_row(store, row, who)
    if task_id and topics_by_task(store).get(task_id) != ep_id:
        raise EntryRefused(f"{task_id} is not a task of {ep_id}: set its topic first (task_topic)")
    turn = _last_turn(store, who) if is_agent(who) else 0
    sid = _mint("es_", ep_id, who, task_id, " ".join(text.split()))
    rec = {"id": sid, "entrypoint_id": ep_id, "at": now_iso(), "author": who if is_agent(who) else "operator",
           "text": text, "task_id": task_id, "removed_at": "", "turn": str(turn or "")}
    known = append_if_absent(store.data_root / STOPS_FILE, ENTRYPOINT_STOP_COLUMNS, rec)
    return {"stop": known, "existing": True} if known is not None else {"stop": rec, "existing": False}


def remove_stop(store: ViewStore, ep_id: str, stop_id: str) -> bool:
    _need(store, ep_id)
    return _mark_removed(store, STOPS_FILE, ENTRYPOINT_STOP_COLUMNS, ep_id, stop_id)


def _mark_removed(store: ViewStore, name: str, columns: tuple[str, ...], ep_id: str, item_id: str) -> bool:
    found = False
    stamp = now_iso()

    def mutate(rows: list[dict[str, str]]) -> bool:
        nonlocal found
        for r in rows:
            if r.get("id") == item_id and r.get("entrypoint_id") == ep_id:
                found = True
                if _live(r):
                    r["removed_at"] = stamp
                    return True
        return False

    path = store.data_root / name
    if path.exists():
        rewrite_rows(path, columns, mutate)
    if not found:
        raise LookupError(item_id)
    return True


def put_way(store: ViewStore, ep_id: str, body: Any) -> dict[str, Any]:
    """Add a way in, or change one (``id``). The operator or an agent."""
    body = _body(body)
    row = _need(store, ep_id)
    way = checked_way(body.get("way"))
    who = identity_of(body) or "operator"
    _member_of_row(store, row, who)
    way_id = _text(body, "id", 40)
    now = now_iso()
    current = ways_of(store, ep_id)
    if way_id:
        old = next((w for w in current if w.get("id") == way_id), None)
        if old is None:
            raise EntryRefused(f"{way_id} is not a way in of {ep_id}")
        if is_agent(who) and not is_agent(old.get("actor") or "") and old.get("actor") != "migration":
            raise EntryRefused(f"{way_id} was written by the operator; an agent adds a new way in instead of changing it")
        out: dict[str, str] = {}
        refused = ""

        def mutate(rows: list[dict[str, str]]) -> bool:
            nonlocal refused
            for r in rows:
                if r.get("id") == way_id and r.get("entrypoint_id") == ep_id:
                    # Read again under the lock: the operator may have
                    # removed or taken over the way since the look above.
                    if not _live(r):
                        refused = f"{way_id} was removed; add a new way in instead"
                        return False
                    if is_agent(who) and not is_agent(r.get("actor") or "") and r.get("actor") != "migration":
                        refused = f"{way_id} was written by the operator; an agent adds a new way in instead of changing it"
                        return False
                    if all(r.get(k, "") == v for k, v in way.items()):
                        out.update(r)
                        return False
                    r.update(way)
                    r["updated_at"] = now
                    r["actor"] = who
                    out.update(r)
                    return True
            return False

        rewrite_rows(store.data_root / WAYS_FILE, ENTRYPOINT_WAY_COLUMNS, mutate)
        if refused:
            raise EntryRefused(refused)
        return {"way": out, "existing": True}
    if len(current) >= WAYS_MAX:
        raise EntryRefused(f"a topic has at most {WAYS_MAX} ways in")
    same = next((w for w in current if all(w.get(k, "") == v for k, v in way.items())), None)
    if same is not None:
        return {"way": same, "existing": True}
    wid = _mint("ew_", ep_id, json.dumps(way, sort_keys=True))
    if any(r.get("id") == wid for r in _rows(store, WAYS_FILE)):
        # The same way in, removed before: written again under a new id.
        wid = _mint("ew_", ep_id, json.dumps(way, sort_keys=True), now)
    rec = {"id": wid, "entrypoint_id": ep_id, **way, "position": str(len(current) * 10 + 10),
           "created_at": now, "updated_at": now, "actor": who, "removed_at": ""}
    known = append_if_absent(
        store.data_root / WAYS_FILE, ENTRYPOINT_WAY_COLUMNS, rec,
        lambda r: r.get("id") == wid or (r.get("entrypoint_id") == ep_id and _live(r)
                                          and all(r.get(k, "") == v for k, v in way.items())))
    return {"way": known, "existing": True} if known is not None else {"way": rec, "existing": False}


def remove_way(store: ViewStore, ep_id: str, way_id: str) -> bool:
    _need(store, ep_id)
    return _mark_removed(store, WAYS_FILE, ENTRYPOINT_WAY_COLUMNS, ep_id, way_id)


_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"),
)


def _image_kind(raw: bytes) -> str:
    for magic, ext in _MAGIC:
        if raw.startswith(magic):
            return ext
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return ""


def add_shot(store: ViewStore, ep_id: str, body: Any) -> dict[str, Any]:
    """A screenshot of a way in: the bytes checked as an image (its kind
    read from the bytes, not from the name given), stored under
    entrypoint_shots/<ep>/<id>.<ext>. ``replaces``: a shot of this topic it
    takes the place of (kept in the history, out of the series)."""
    from .story_images import dimensions
    body = _body(body)
    row = _need(store, ep_id)
    who = identity_of(body) or "operator"
    _member_of_row(store, row, who)
    way_id = _text(body, "way_id", 40, required=True)
    if not any(w.get("id") == way_id for w in ways_of(store, ep_id)):
        raise EntryRefused(f"{way_id} is not a way in of {ep_id}")
    caption = _text(body, "caption", CAPTION_MAX)
    replaces = _text(body, "replaces", 40)
    if replaces and not any(s.get("id") == replaces for s in shots_of(store, ep_id)):
        raise EntryRefused(f"{replaces} is not a screenshot of {ep_id}")
    data = body.get("data_base64")
    if not isinstance(data, str) or not data.strip():
        raise EntryRefused("data_base64 is the image, base64 text")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError):
        raise EntryRefused("data_base64 is not valid base64") from None
    if not raw:
        raise EntryRefused("the image is empty")
    if len(raw) > limits.MAX_IMAGE_BYTES:
        raise EntryRefused(f"the image is over {limits.MAX_IMAGE_BYTES // (1024 * 1024)}MB")
    ext = _image_kind(raw)
    if not ext:
        raise EntryRefused("the file is not a PNG, JPEG, GIF or WebP image")
    w, h = dimensions(raw)
    digest = hashlib.sha256(raw).hexdigest()
    sid = _mint("eh_", ep_id, way_id, digest)
    known = next((s for s in _rows(store, SHOTS_FILE) if s.get("id") == sid), None)
    if known is not None and _live(known):
        return {"shot": known, "existing": True}
    rel = f"{SHOTS_DIR}/{ep_id}/{sid}.{ext}"
    path = store.data_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, raw)
    agent = who if is_agent(who) else ""
    rec = {"id": sid, "entrypoint_id": ep_id, "way_id": way_id, "file": rel, "caption": caption,
           "at": now_iso(), "author": who if is_agent(who) else "operator", "agent_id": agent,
           "replaces": replaces, "removed_at": "", "width": str(w or ""), "height": str(h or ""),
           "turn": str(_last_turn(store, agent) or "") if agent else ""}
    if known is not None:
        # The same picture again after it was replaced: back in the series.
        def back(rows: list[dict[str, str]]) -> bool:
            for r in rows:
                if r.get("id") == sid:
                    r.update(rec)
                    return True
            return False
        rewrite_rows(store.data_root / SHOTS_FILE, ENTRYPOINT_SHOT_COLUMNS, back)
    else:
        append_row(store.data_root / SHOTS_FILE, ENTRYPOINT_SHOT_COLUMNS, rec)
    if replaces:
        _mark_removed(store, SHOTS_FILE, ENTRYPOINT_SHOT_COLUMNS, ep_id, replaces)
    return {"shot": rec, "existing": False}


def shot_file(store: ViewStore, shot_id: str) -> Path | None:
    """The image file of a shot (a Path under entrypoint_shots/), or None."""
    s = next((r for r in _rows(store, SHOTS_FILE) if r.get("id") == shot_id), None)
    if s is None:
        return None
    path = resolve_under((store.data_root / SHOTS_DIR), str(s.get("file") or "").removeprefix(f"{SHOTS_DIR}/"))
    return path if path is not None and path.is_file() else None


def _rewrite_entry(store: ViewStore, ep_id: str, fields: dict[str, str]) -> dict[str, str]:
    ent = ENTITIES["entrypoint"]
    out: dict[str, str] = {}

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == ep_id:
                changed = any(r.get(k, "") != v for k, v in fields.items())
                r.update(fields)
                out.update(r)
                return changed
        return False

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    if not out:
        raise LookupError(ep_id)
    return out


def set_state(store: ViewStore, ep_id: str, body: Any) -> dict[str, str]:
    """active · paused · dead; the old status is written beside it so the
    readers of open/closed agree."""
    body = _body(body)
    _need(store, ep_id)
    state = _text(body, "state", 10, required=True).lower()
    if state not in ENTRYPOINT_STATES:
        raise EntryRefused(f"state is one of {', '.join(ENTRYPOINT_STATES)}")
    # status is open only while active: paused or dead read back as closed,
    # and a closed row with no state reads as paused (state_of).
    return _rewrite_entry(store, ep_id, {"state": state, "status": "open" if state == "active" else "closed"})


def rename(store: ViewStore, ep_id: str, name: str, *, who: str, at: str = "", command_id: str = "",
           more: dict[str, str] | None = None) -> dict[str, str]:
    """The topic's name, and a line in its history when the name changed:
    who, when, the old name and the new (``entrypoint_names.csv``)."""
    old = name_of(entry_of(store, ep_id) or {})
    row = _rewrite_entry(store, ep_id, {"topic": name, **(more or {})})
    if old != name:
        when = at or now_iso()
        append_row(store.data_root / NAMES_FILE, ENTRYPOINT_NAME_COLUMNS, {
            "id": _mint("epn_", ep_id, when, old, name), "entrypoint_id": ep_id, "at": when, "old": old,
            "new": name, "agent_id": who if is_agent(who) else "operator", "command_id": command_id})
    return row


def renames(store: Any, ep_id: str) -> list[dict[str, str]]:
    """The topic's names, oldest first: {at, old, new, agent_id, command_id}."""
    rows = [r for r in _rows(store, NAMES_FILE) if r.get("entrypoint_id") == ep_id]
    return sorted(({k: str(r.get(k) or "") for k in ("at", "old", "new", "agent_id", "command_id")} for r in rows),
                  key=lambda r: r["at"])


def set_name(store: ViewStore, ep_id: str, body: Any) -> dict[str, str]:
    body = _body(body)
    _need(store, ep_id)
    name = " ".join(_text(body, "name", NAME_MAX, required=True).split())
    fields: dict[str, str] = {}
    if "home" in body:
        fields["home"] = _text(body, "home", PATH_MAX)
    if "no_project" in body:
        raw = body.get("no_project")
        if not isinstance(raw, bool):
            raise EntryRefused("no_project is true or false")
        fields["no_project"] = "yes" if raw else ""
    return rename(store, ep_id, name, who=identity_of(body) or "operator", more=fields)


def set_task_topic(store: ViewStore, task_id: str, body: Any) -> dict[str, Any]:
    """The task's topic (``entrypoint_id``; "" clears it). The topic is of
    the task's own project."""
    body = _body(body)
    ep_id = _text(body, "entrypoint_id", 40)
    task = store.query_one("SELECT id, project, projects FROM tasks_mutual WHERE id = ?", (task_id,))
    if task is None:
        raise LookupError(task_id)
    who = identity_of(body) or "operator"
    if ep_id:
        row = _need(store, ep_id)
        if not in_project(task, str(row.get("project") or "")):
            raise EntryRefused(f"{ep_id} is a topic of {row.get('project')}; {task_id} is in {task.get('project')}")
        _member_of_row(store, row, who)
    elif is_agent(who):
        # Clearing: the task's own project stands in for the topic's.
        _member_of_row(store, {"id": task_id, "project": str(task.get("project") or ""),
                               "projects": str(task.get("projects") or "")}, who, "task")
    rec = {"id": _mint("tt_", task_id), "task_id": task_id, "entrypoint_id": ep_id, "at": now_iso(), "actor": who}
    def mutate(rows: list[dict[str, str]]) -> bool:
        # One step under the lock, the file's creation included: two calls
        # for a task never leave two rows.
        keep = [r for r in rows if r.get("task_id") == task_id]
        if len(keep) == 1 and keep[0].get("entrypoint_id") == ep_id:
            return False
        if not keep and not ep_id:
            return False
        rows[:] = [r for r in rows if r.get("task_id") != task_id] + [rec]
        return True

    rewrite_rows(store.data_root / TOPICS_FILE, TASK_TOPIC_COLUMNS, mutate)
    return {"task_id": task_id, "topic": topic_of_task(store, task_id) if ep_id else None}


# ---------------------------------------------------------------------------
# The port check
# ---------------------------------------------------------------------------


def probe_target(way: dict[str, Any]) -> tuple[str, int] | None:
    """(loopback address, port) for a way that runs on this computer, or
    None: a site elsewhere, a file, a way with no port. The host is mapped,
    never resolved: a name that is not this computer is not connected to."""
    url = str(way.get("url") or "").strip()
    port = as_int(way.get("port"), 0)
    host = "localhost"
    if url:
        try:
            parts = urllib.parse.urlsplit(url)
            host = (parts.hostname or "").lower()
            if parts.port and not port:
                port = parts.port
        except ValueError:
            return None
        try:
            # A loopback literal (127.x.y.z); never a name that starts like one.
            if ipaddress.ip_address(host).is_loopback and ":" not in host:
                host = "127.0.0.1"
        except ValueError:
            pass
    addr = LOCAL_HOSTS.get(host)
    if addr is None or not 1 <= port <= 65535:
        return None
    return addr, port


def _connect(addr: str, port: int, timeout: float) -> bool:
    """Up when the port answers; "localhost" is tried on both loopbacks (a
    dev server on Node 17+ often listens on ::1 only)."""
    if addr == "localhost":
        return _connect1("127.0.0.1", port, timeout) or _connect1("::1", port, timeout)
    return _connect1(addr, port, timeout)


def _connect1(addr: str, port: int, timeout: float) -> bool:
    family = socket.AF_INET6 if ":" in addr else socket.AF_INET
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((addr, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def check_ports(ways: list[dict[str, Any]], *, timeout: float = PORT_TIMEOUT_S,
                deadline: float = PORT_DEADLINE_S) -> list[dict[str, Any]]:
    """Whether each way in is up now: a TCP connect to its local port, each
    port once, all at once, the whole check bounded by ``deadline``. A way
    that is not on this computer answers ``up: None`` with the reason."""
    out: list[dict[str, Any]] = []
    targets: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for w in ways:
        t = probe_target(w)
        rec = {"id": w.get("id"), "port": t[1] if t else None, "up": None,
               "why": "" if t else ("not a local address" if w.get("url") or w.get("port") else "nothing to check")}
        out.append(rec)
        if t is not None:
            targets.setdefault(t, []).append(rec)
    probes = list(targets)[:PORT_PROBES_MAX]
    for t in list(targets)[PORT_PROBES_MAX:]:
        for rec in targets[t]:
            rec["why"] = "not checked: too many ports"
    if probes:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(probes)))
        try:
            futs = {pool.submit(_connect, a, p, timeout): (a, p) for a, p in probes}
            done, _pending = concurrent.futures.wait(futs, timeout=deadline)
            for f in futs:
                up = f.result() if f in done else False
                for rec in targets[futs[f]]:
                    rec["up"] = bool(up)
                    if f not in done:
                        rec["why"] = "no answer in time"
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    return out


# ---------------------------------------------------------------------------
# The desk: every topic of a project
# ---------------------------------------------------------------------------


def _shot_view(s: dict[str, str]) -> dict[str, Any]:
    return {"id": s.get("id"), "way_id": s.get("way_id"), "caption": s.get("caption") or "",
            "at": s.get("at") or "", "author": s.get("author") or "", "agent_id": s.get("agent_id") or "",
            "width": as_int(s.get("width")), "height": as_int(s.get("height")),
            "src": f"/api/entrypoints/shots/{s.get('id')}/file"}


def _stop_view(s: dict[str, str]) -> dict[str, Any]:
    return {"id": s.get("id"), "at": s.get("at") or "", "author": s.get("author") or "operator",
            "text": s.get("text") or "", "task_id": s.get("task_id") or "", "turn": as_int(s.get("turn"))}


def _way_view(w: dict[str, str]) -> dict[str, Any]:
    return {k: w.get(k) or "" for k in ("id", "name", "kind", "url", "path", "command", "folder", "note", "actor",
                                         "updated_at")} | {"port": as_int(w.get("port")) or None}


def entries(store: ViewStore, project: str = "", *, archived: bool = False) -> list[dict[str, str]]:
    """The project's topics (or all). Archived ones only when asked: the desk
    shows them folded; matching, offers and writes never see them."""
    rows = read_rows(store.data_root / ENTITIES["entrypoint"].csv)
    return [r for r in rows if (archived or not str(r.get("archived_at") or "").strip())
            and (not project or r.get("project") == project)]


def summary(store: ViewStore, row: dict[str, str], *, ways: list[dict[str, str]], stops: list[dict[str, str]],
            shots: list[dict[str, str]], tasks: list[dict[str, Any]], chats: int) -> dict[str, Any]:
    record = record_of(store, row)
    created = iso_moment(row.get("created_date"), row.get("created_time"))
    last = max([created] + [s.get("at") or "" for s in stops] + [s.get("at") or "" for s in shots]
               + [w.get("updated_at") or "" for w in ways if w.get("actor") != "migration"])
    return {
        "id": row["id"], "project": row.get("project") or "", "name": name_of(row), "title": what_sentence(record) or _title(row),
        "state": state_of(row), "no_project": str(row.get("no_project") or "") == "yes",
        "home": row.get("home") or "", "what": what_of(record), "has_record": bool(record),
        "versions": as_int(row.get("versions_n")), "created": created, "agent_id": row.get("agent_id") or "",
        "ways": [_way_view(w) for w in ways],
        "stops": [_stop_view(s) for s in stops[:STOPS_SHOWN]], "stops_n": len(stops),
        "shots": [_shot_view(s) for s in shots],
        "open_tasks": sum(1 for t in tasks if not is_done(t.get("status")) and not t.get("archived_at")),
        "chats": chats, "last_at": last,
        "archived_at": str(row.get("archived_at") or "").strip(),
    }


def desk(store: ViewStore, project: str = "") -> dict[str, Any]:
    """Every topic (of a project, or all), with what its tile and list line
    show, archived ones too (marked, the page folds them). Light: no chat is
    read, no git is run."""
    rows = entries(store, project, archived=True)
    all_ways = [w for w in _rows(store, WAYS_FILE) if _live(w)]
    all_stops = [s for s in _rows(store, STOPS_FILE) if _live(s)]
    all_shots = [s for s in _rows(store, SHOTS_FILE) if _live(s)]
    by_task = topics_by_task(store)
    tasks = store.query("SELECT id, project, projects, status, archived_at FROM tasks_mutual") if by_task else []
    out = []
    for r in rows:
        eid = r["id"]
        mine_tasks = [t for t in tasks if by_task.get(str(t["id"])) == eid and in_project(t, str(r.get("project") or ""))]
        ways = sorted((w for w in all_ways if w.get("entrypoint_id") == eid),
                      key=lambda w: (as_int(w.get("position")), w.get("created_at") or ""))
        stops = sorted((s for s in all_stops if s.get("entrypoint_id") == eid), key=lambda s: s.get("at") or "", reverse=True)
        shots = sorted((s for s in all_shots if s.get("entrypoint_id") == eid), key=lambda s: s.get("at") or "")
        agents = {r.get("agent_id") or ""} | {s.get("author") or "" for s in stops} | {s.get("agent_id") or "" for s in shots}
        if mine_tasks:
            marks = ",".join("?" for _ in mine_tasks)
            agents |= {str(m.get("agent_id") or "") for m in store.query(
                f"SELECT DISTINCT agent_id FROM task_mentions WHERE role = 'user' AND task_id IN ({marks})",
                tuple(t["id"] for t in mine_tasks))}
        chats = len({a for a in agents if a and is_agent(a)})
        out.append(summary(store, r, ways=ways, stops=stops, shots=shots, tasks=mine_tasks, chats=chats))
    return {"topics": out, "projects": sorted({t["project"] for t in out})}


# ---------------------------------------------------------------------------
# One topic's context
# ---------------------------------------------------------------------------


def _iso(d: datetime | None) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S") if d else ""


def _clip(s: str, n: int = 300) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _turn_at(turns: list[Any], at: str) -> int:
    """The turn a moment falls in: the last one that began at or before it."""
    moment = as_local(at)
    if moment is None:
        return 0
    best = 0
    for t in turns:
        if t.at <= moment:
            best = t.number
    return best


def chat_turns(store: ViewStore, row: dict[str, str], tasks: list[dict[str, Any]],
               stops: list[dict[str, str]], shots: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """The canonical account of which turns of which chat were the topic's:
    {agent_id: {"turns": set, "why": {n: [reasons]}, "agent": row, "all": [Turn]}}.

    A turn counts when: the topic was made in it (the #entrypoint message);
    the operator named one of the topic's tasks in it (not only filing it);
    it lies inside a #done stretch that closed one of them; an agent wrote a
    stop or a shot of the topic in it. A chat of another project never
    counts. Each turn once: counts, spend and the passage read this set."""
    from . import donelib
    from .sessions import chat_path, parse_turns
    from .taskwork import _filing_turns
    project = str(row.get("project") or "")
    agents = {str(a.get("agent_id") or ""): a for a in store.agents()}
    # The chats of the topic's project, its members included (memberships.Listing).
    listed = memberships.listing(store, project)
    want: dict[str, dict[int, list[str]]] = {}

    def add(agent: str, n: int, why: str) -> None:
        if not agent or not is_agent(agent) or n <= 0:
            return
        a = agents.get(agent)
        if a is None or not listed.has(a.get("project"), agent):
            return
        want.setdefault(agent, {}).setdefault(n, [])
        if why not in want[agent][n]:
            want[agent][n].append(why)

    if str(row.get("source") or "") == "captured":
        add(str(row.get("agent_id") or ""), as_int(row.get("source_turn")), "origin")
    # A later #entrypoint of the same topic in another chat is an origin too.
    for c in commands(store):
        if c.get("entrypoint_id") == row["id"] and c.get("how") == "name":
            add(str(c.get("agent_id") or ""), as_int(c.get("turn")), "origin")
    ids = [str(t["id"]) for t in tasks]
    if ids:
        marks = ",".join("?" for _ in ids)
        filing: dict[str, set[int]] = {}
        for m in store.query(
                f"SELECT task_id, agent_id, session_id, turn FROM task_mentions WHERE role = 'user' AND task_id IN ({marks})",
                tuple(ids)):
            sid = str(m.get("session_id") or "")
            if sid not in filing:
                srow = store.query_one("SELECT turns_json FROM sessions WHERE id = ?", (sid,))
                filing[sid] = _filing_turns(srow) if srow else set()
            n = as_int(m.get("turn"))
            if n in filing[sid]:
                continue
            add(str(m.get("agent_id") or ""), n, "task")
        for tid in ids:
            for agent, lo, hi in donelib.stretches_raw(store, tid):
                for n in range(max(1, lo), hi + 1):
                    add(agent, n, "done")
    out: dict[str, dict[str, Any]] = {}
    timed = [(str(s.get("author") or ""), as_int(s.get("turn")), str(s.get("at") or ""), "stop") for s in stops]
    timed += [(str(s.get("agent_id") or ""), as_int(s.get("turn")), str(s.get("at") or ""), "shot") for s in shots]
    needed = set(want) | {a for a, _, _, _ in timed if a and is_agent(a)}
    for agent in needed:
        a = agents.get(agent)
        if a is None or not listed.has(a.get("project"), agent):
            continue
        path = chat_path(store, agent)
        try:
            turns = parse_turns(path) if path else []
        except (OSError, UnicodeDecodeError):
            turns = []
        for who, n, at, why in timed:
            if who == agent:
                add(agent, n or _turn_at(turns, at), why)
        if agent in want and turns:
            have = {t.number for t in turns}
            keep = {n: w for n, w in want[agent].items() if n in have}
            if keep:
                out[agent] = {"turns": keep, "agent": a, "all": turns}
    return out


def _chat_name(a: dict[str, Any], agent: str) -> str:
    """The name the Agents page shows: the chat's given name, else its
    title (the first message) cut to a line, else the id."""
    given = " ".join(str(a.get("agent_name") or "").split())
    if given and given != agent:
        return given[:60]
    return _clip(str(a.get("chat_title") or ""), 60) or agent


def _agent_links(store: ViewStore) -> dict[str, dict[str, str]]:
    """chat → {id, how}: the chat it took the work over from or branched from."""
    out: dict[str, dict[str, str]] = {}
    for r in _rows(store, "agent_links.csv"):
        if r.get("kind") in ("handoff", "branch") and r.get("to_id"):
            out[str(r["to_id"])] = {"id": str(r.get("from_id") or ""), "how": str(r["kind"])}
    return out


def _within(at: str, spans: list[tuple[str, str]]) -> bool:
    return bool(at) and any(lo <= at <= hi for lo, hi in spans)


def _spans(turns: list[Any], numbers: set[int]) -> list[tuple[str, str]]:
    """The topic's turns of a chat as time spans (each turn from its start
    to its answer's end), merged where they touch."""
    out: list[tuple[str, str]] = []
    for t in sorted((t for t in turns if t.number in numbers), key=lambda t: t.number):
        lo = _iso(t.at)
        hi = _iso(t.end or t.at)
        if hi < lo:
            hi = lo
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi[:16] + ":59" if len(hi) >= 16 else hi))
    return out


def context(store: ViewStore, ep_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Everything the topic's card shows below its head, and the briefing."""
    from . import donelib
    row = entry_of(store, ep_id)
    if row is None:
        raise LookupError(ep_id)
    project = str(row.get("project") or "")
    stops, shots = stops_of(store, ep_id), shots_of(store, ep_id)
    all_tasks = tasks_of_topic(store, row)
    # Every open task is "what is next"; the cap (each task's commits are
    # read from git) applies to the done ones, newest first.
    open_all = [t for t in all_tasks if not is_done(t.get("status"))]
    done_all = [t for t in all_tasks if is_done(t.get("status"))]
    truncated = len(done_all) > CONTEXT_TASKS
    tasks = open_all + done_all[:CONTEXT_TASKS]
    per_chat = chat_turns(store, row, tasks, stops, shots)
    links = _agent_links(store)
    project_of = {str(a.get("agent_id") or ""): str(a.get("project") or "") for a in store.agents()}
    ref = now or datetime.now()

    # Tasks: open (what is next) and done, with the report and the closing chat.
    done_rows = {}
    for r in donelib.rows(store):
        if r.get("result") in donelib.RESOLVED and r.get("task_id"):
            done_rows[str(r["task_id"])] = r
    listed = memberships.listing(store, project)

    def _ours(agent: str) -> str:
        return agent if agent and agent in project_of and listed.has(project_of[agent], agent) else ""

    open_tasks, done_tasks = [], []
    for t in tasks:
        if t.get("archived_at") and not is_done(t.get("status")):
            continue
        if is_done(t.get("status")):
            d = done_rows.get(str(t["id"])) or {}
            done_tasks.append({"id": t["id"], "title": t.get("title") or "",
                               "done": str(d.get("at") or t.get("agent_done_at") or ""),
                               "chat": _ours(str(d.get("agent_id") or t.get("agent_done_by") or "")),
                               "report": str(t.get("agent_done_note") or "")})
        else:
            open_tasks.append({"id": t["id"], "title": t.get("title") or "", "status": t.get("status") or ""})
    done_tasks.sort(key=lambda k: k["done"], reverse=True)

    # Commits and files: each commit once, the files summed over those commits.
    from . import gitwork, taskwork
    from .file_entries import project_repo
    commits: dict[str, dict[str, Any]] = {}
    for t in tasks:
        try:
            work = taskwork.task_work(store, str(t["id"]))
        except Exception:  # noqa: BLE001 — git is best effort
            continue
        for c in work.get("commit_list") or []:
            got = commits.setdefault(str(c["sha"]), {**c, "tasks": []})
            if t["id"] not in got["tasks"]:
                got["tasks"].append(t["id"])
    files: dict[str, dict[str, Any]] = {}
    repo = project_repo(store, project) if commits else None
    by_sha: dict[str, Any] = {}
    if repo is not None:
        try:
            by_sha = {c.sha[:7]: c for c in gitwork.commits(repo)}
        except Exception:  # noqa: BLE001
            by_sha = {}
    commit_list = []
    for sha, c in sorted(commits.items(), key=lambda kv: str(kv[1].get("at") or ""), reverse=True):
        g = by_sha.get(sha[:7])
        add = sum(a for _, a, _ in g.files) if g else 0
        dele = sum(d for _, _, d in g.files) if g else 0
        for p, a, d in (g.files if g else []):
            f = files.setdefault(p, {"path": p, "add": 0, "del": 0})
            f["add"] += a
            f["del"] += d
        commit_list.append({"sha": sha, "at": str(c.get("at") or ""), "subject": str(c.get("subject") or ""),
                            "chat": str(c.get("agent") or ""), "files": len(c.get("files") or []),
                            "add": add, "del": dele, "tasks": c["tasks"]})

    # Chats, oldest first.
    chats = []
    spans_of: dict[str, list[tuple[str, str]]] = {}
    for agent, got in per_chat.items():
        a, turns_all, mine = got["agent"], got["all"], got["turns"]
        numbers = set(mine)
        ordered = [t for t in turns_all if t.number in numbers]
        if not ordered:
            continue
        spans_of[agent] = _spans(turns_all, numbers)
        last_all = turns_all[-1]
        waiting = bool((last_all.user_summary or "").strip()) and not (last_all.agent_summary or "").strip()
        tail = []
        for t in ordered[-3:]:
            if (t.user_summary or "").strip():
                tail.append({"who": "you", "at": _iso(t.at), "text": _clip(t.user_summary), "turn": t.number,
                             "unanswered": waiting and t.number == last_all.number})
            if (t.agent_summary or "").strip():
                tail.append({"who": "agent", "at": _iso(t.end or t.at), "text": _clip(t.agent_summary), "turn": t.number})
        mine_stops = [s for s in stops if s.get("author") == agent]
        did = (mine_stops[0].get("text") if mine_stops else "") or ""
        if not did:
            named = [t for t in tasks if any(
                m.get("agent_id") == agent for m in store.query(
                    "SELECT agent_id FROM task_mentions WHERE task_id = ? AND role = 'user' LIMIT 1", (t["id"],)))]
            did = f"{named[0]['id']} {named[0].get('title') or ''}".strip() if named else ""
        if not did and any("origin" in w for w in mine.values()):
            did = "made this entry point"
        last_at = _iso(ordered[-1].end or ordered[-1].at)
        live_at = as_local(str(a.get("last_active") or "")) or (ordered[-1].end or ordered[-1].at)
        chats.append({
            "id": agent, "name": _chat_name(a, agent),
            "tool": str(a.get("tool") or ""), "session_ref": str(a.get("session_ref") or ""),
            "cwd": str(a.get("cwd") or ""),
            "first": _iso(ordered[0].at), "last": last_at, "messages": len(ordered),
            "origin": any("origin" in w for w in mine.values()), "did": _clip(did, 240), "tail": tail,
            "commits": sum(1 for c in commit_list if c["chat"] == agent),
            "live": bool(live_at and (ref - live_at).total_seconds() < 36 * 3600),
            "from": links.get(agent), "waiting": waiting,
            "waiting_text": _clip(last_all.user_summary, 500) if waiting else "",
            "waiting_at": _iso(last_all.at) if waiting else "",
            "turns": sorted(numbers),
        })
    chats.sort(key=lambda c: c["first"])
    chat_ids = {c["id"] for c in chats}
    for c in chats:
        # A handoff from a chat of another project names no chat here.
        if c["from"] and c["from"].get("id") not in chat_ids:
            c["from"] = None

    # Decisions, artifacts and Publish cards made in the topic's turns of its chats.
    def made_in(agent: str, day: Any, hm: Any) -> bool:
        return agent in spans_of and _within(iso_moment(day, hm)[:16], [(lo[:16], hi[:16]) for lo, hi in spans_of[agent]])

    decisions = []
    if chat_ids:
        marks = ",".join("?" for _ in chat_ids)
        for d in store.query(
                "SELECT id, created_date, created_time, agent_id, decision_text, weight, project "
                f"FROM decisions_mutual WHERE agent_id IN ({marks})", tuple(chat_ids)):
            if str(d.get("project") or "") != project or not made_in(str(d["agent_id"]), d.get("created_date"), d.get("created_time")):
                continue
            decisions.append({"id": d["id"], "at": iso_moment(d.get("created_date"), d.get("created_time")),
                              "weight": str(d.get("weight") or "normal") or "normal",
                              "title": _clip(str(d.get("decision_text") or ""), 240), "chat": d["agent_id"]})
    decisions.sort(key=lambda d: d["at"], reverse=True)
    made = []
    for kind in ("artifact", "publish"):
        ent = ENTITIES[kind]
        if not chat_ids:
            break
        marks = ",".join("?" for _ in chat_ids)
        extra = "name, kind, status" if kind == "artifact" else "l1"
        for m in store.query(
                f"SELECT id, created_date, created_time, agent_id, project, archived_at, {extra} FROM {ent.view} "
                f"WHERE agent_id IN ({marks})", tuple(chat_ids)):
            if str(m.get("project") or "") != project or str(m.get("archived_at") or "").strip():
                continue
            if not made_in(str(m["agent_id"]), m.get("created_date"), m.get("created_time")):
                continue
            made.append({"id": m["id"], "kind": "artifact" if kind == "artifact" else "card",
                         "name": _clip(str(m.get("name") or m.get("l1") or m["id"]), 120),
                         "at": iso_moment(m.get("created_date"), m.get("created_time")), "chat": m["agent_id"],
                         "sub": str(m.get("kind") or "") if kind == "artifact" else "card"})
    made.sort(key=lambda m: m["at"], reverse=True)

    # Spend: the usage of the topic's turns, each turn once.
    from . import usagelib
    by_chat: dict[str, dict[str, Any]] = {}
    for c in chats:
        try:
            usage = usagelib.chat_turns(store, project, c["id"])
        except Exception:  # noqa: BLE001 — usage is best effort
            usage = {}
        tok = 0
        micro = 0
        counted = 0
        for n in c["turns"]:
            u = usage.get(n)
            if not u:
                continue
            counted += 1
            tok += as_int(u.get("new")) + as_int(u.get("cache")) + as_int(u.get("output"))
            micro += sum(as_int(u.get(k)) for k in ("cost_new", "cost_rebuilt", "cost_warm", "cost_output"))
        if counted:
            by_chat[c["id"]] = {"tokens": tok, "dollars": round(micro / 1_000_000, 2), "turns": counted}
    spend = None
    if by_chat:
        spend = {"tokens": sum(v["tokens"] for v in by_chat.values()),
                 "dollars": round(sum(v["dollars"] for v in by_chat.values()), 2), "by_chat": by_chat}

    out = {
        "id": ep_id, "stops": [_stop_view(s) for s in stops], "chats": chats, "open": open_tasks, "done": done_tasks,
        "decisions": decisions, "commits": commit_list[:200], "commits_n": len(commit_list),
        "files": sorted(files.values(), key=lambda f: -(f["add"] + f["del"]))[:60], "files_n": len(files),
        "made": made, "spend": spend, "tasks_truncated": truncated, "tasks_n": len(all_tasks),
    }
    out["briefing"] = briefing(store, row, out)
    return out


# ---------------------------------------------------------------------------
# The briefing — what "Copy to agent" gives
# ---------------------------------------------------------------------------


def _resume(chat: dict[str, Any], home: str) -> str:
    ref = chat.get("session_ref") or ""
    if not ref:
        return ""
    cwd = chat.get("cwd") or home
    cd = f'cd "{cwd}" && ' if cwd else ""
    tool = chat.get("tool") or ""
    if tool == "claude-code":
        return f"{cd}claude -r {ref}"
    if tool == "codex":
        return f"{cd}codex resume {ref}"
    if tool == "opencode":
        return f"{cd}opencode --session {ref}"
    return ""


def home_of(store: ViewStore, row: dict[str, Any]) -> str:
    if str(row.get("home") or "").strip():
        return str(row["home"]).strip()
    from .file_entries import project_path
    p = project_path(store, str(row.get("project") or ""))
    return str(p) if p else ""


def _record_parts(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The record as written: the text before its first heading, then every
    section in order with its body whole (a repeated heading kept too)."""
    text = (text or "").replace("\r", "").strip()
    marks = list(_SECTION.finditer(text))
    head = text[:marks[0].start()].strip() if marks else text
    parts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        parts.append((m.group(1), text[m.end():end].strip()))
    return head, parts


def briefing(store: ViewStore, row: dict[str, Any], cx: dict[str, Any]) -> str:
    """The text a new agent gets: the topic, its What, its ways in, the rest
    of its record (Where, How, State, Next — every section whole, nothing
    cut), where it stopped,
    what is next, where to resume, the operator's message that waits, the
    chats so far, what was done lately and the major decisions. English,
    Markdown, plain enough to paste."""
    ep_id = str(row["id"])
    name = label_of(store, row) or ep_id
    home = home_of(store, row)
    lines = [f"# {name}", "",
             f"Slightly Parallel entry point {ep_id} · project {row.get('project') or ''}"
             f"{' (belongs to no project)' if str(row.get('no_project') or '') == 'yes' else ''} · state {state_of(row)}"]
    if home:
        lines.append(f'Start in: `cd "{home}"`')
    head, record = _record_parts(record_of(store, row))
    what = "\n\n".join(b for k, b in record if k == "What" and b)
    if head or what:
        lines += ["", "\n\n".join(x for x in (head, what) if x)]
    ways = ways_of(store, ep_id)
    if ways:
        lines += ["", "## Ways in"]
        for w in ways:
            where = w.get("url") or w.get("path") or ""
            parts = [f"- {w.get('name')}{': ' + where if where else ''}"]
            if w.get("command"):
                parts.append(f"start: `{w['command']}`" + (f" in `{w['folder']}`" if w.get("folder") else ""))
            if w.get("port"):
                parts.append(f"port {w['port']}")
            if w.get("note"):
                parts.append(str(w["note"]))
            lines.append(" · ".join(parts))
    kept = [(k, body) for k, body in record if k != "What" and body]
    if kept:
        lines += ["", "## The record"]
        for k, body in kept:
            lines += ["", f"### {k}", body]
    stops = stops_of(store, ep_id)[:STOPS_SHOWN]
    if stops:
        lines += ["", "## Where it stopped (newest first)"]
        for s in stops:
            who = "the operator" if s.get("author") in ("", "operator") else str(s.get("author"))
            lines.append(f"- {str(s.get('at') or '')[:10]} {who}: {s.get('text')}")
    if cx.get("open"):
        lines += ["", "## Open tasks (what is next)"]
        for k in cx["open"]:
            lines.append(f"- {k['id']} ({k['status']}) {k['title']}")
    chats = cx.get("chats") or []
    last = max(chats, key=lambda c: c["last"]) if chats else None
    if last:
        lines += ["", "## Resume",
                  f"Last worked in {last['id']} \"{last['name']}\", {last['last'][:16].replace('T', ' ')} "
                  f"({last['messages']} messages on this topic since {last['first'][:10]})"
                  + (f": {last['did']}" if last.get("did") else "")]
        tail = (last.get("tail") or [])[-1:] if last.get("tail") else []
        if tail:
            lines.append(f"Its last message, {'the operator' if tail[0]['who'] == 'you' else 'the agent'}: {tail[0]['text']}")
        cmd = _resume(last, home)
        if cmd:
            lines.append(f"Resume it: `{cmd}`")
    waiting = [c for c in chats if c.get("waiting")]
    if waiting:
        lines += ["", "## Unanswered"]
        for c in waiting:
            lines.append(f"- {c['waiting_at'][:10]} the operator in {c['id']}: {c['waiting_text']}")
    earlier = [c for c in chats if c is not last][-5:]
    if earlier:
        lines += ["", "## Chats so far (oldest first)"]
        for c in earlier:
            lines.append(f"- {c['first'][:10]}–{c['last'][:10]} {c['id']} \"{c['name']}\""
                         + (" (the topic came from here)" if c.get("origin") else "") + (f": {c['did']}" if c.get("did") else ""))
    done = [k for k in cx.get("done") or [] if k.get("report")][:3]
    if done:
        lines += ["", "## Done lately"]
        for k in done:
            lines.append(f"- {k['id']} {k['title']}: {k['report']}")
    major = [d for d in cx.get("decisions") or [] if d.get("weight") == "major"][:3]
    if major:
        lines += ["", "## Major decisions"]
        for d in major:
            lines.append(f"- {d['id']} {d['at'][:10]}: {d['title']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The similar-topic check, for an agent's offer of a new entry point
# ---------------------------------------------------------------------------

SIMILAR_MIN = 0.35


DEFAULT_SIMILAR_ENTRYPOINTS = 3


def similar(store: ViewStore, project: str, text: str, *, limit: int = DEFAULT_SIMILAR_ENTRYPOINTS) -> list[dict[str, Any]]:
    """The project's topics most like ``text`` (a name and why), by word
    overlap weighted by rarity (similarlib): each {id, name, state, score}."""
    from . import similarlib
    docs = []
    rows = {}
    for r in entries(store, project):
        ways = " ".join(f"{w.get('name')} {w.get('url')} {w.get('path')} {w.get('command')}" for w in ways_of(store, r["id"]))
        doc = f"{name_of(r)} {name_of(r)} {_title(r)} {what_of(record_of(store, r))} {ways}"
        docs.append((r["id"], doc))
        rows[r["id"]] = r
    out = []
    for hid, score in similarlib.rank(text, docs, limit=limit, threshold=SIMILAR_MIN):
        if hid in rows:
            r = rows[hid]
            out.append({"id": hid, "name": label_of(store, r), "state": state_of(r), "score": round(score, 2)})
    return out


def offer_line(name: str, hits: list[dict[str, Any]]) -> str:
    if hits:
        h = hits[0]
        return (f"This matches the entry point «{h['name']}» ({h['id']}): add the way in there with "
                f"entrypoint_way, and say so to the operator in one line. Do not offer a new one.")
    return (f"No topic like it. Offer it to the operator in one line, as the last line of your reply: "
            f"«New entry point “{name}”? Type #entrypoint with its name to keep it.» Write nothing until they do.")


# ---------------------------------------------------------------------------
# Migration of the records written before ways in existed
# ---------------------------------------------------------------------------

MIGRATION_FILE = "entrypoints_migration.json"
MIGRATION_VERSION = 1
_URL = re.compile(r"https?://[^\s`<>)\]\"',;]+")
_TICK = re.compile(r"`([^`\n]+)`")
_RUNNERS = ("npm ", "npx ", "pnpm ", "yarn ", "python3 ", "python ", "node ", "uv ", "./", ".venv/", "flutter ",
            "make", "go run", "cargo ", "bun ", "deno ")
_FOLDER = re.compile(r"(?:\bfrom|\bin|\bиз|\bв)\s+`([^`\n]+)`", re.I)


def _local(url: str) -> tuple[str, int] | None:
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if host in ("localhost", "127.0.0.1", "0.0.0.0") and port:
        return host, port
    return None


def parse_ways(record: str) -> list[dict[str, str]]:
    """Ways in read from an old record, only where a line says one thing:

    - a How or Where line with exactly one local URL that has a port: a
      page, with that port; its command when the line holds exactly one
      backticked text that starts like a command (npm, python3, ./ …); its
      folder when the line says from/in/из `X`;
    - a Where line "Label: https://…" with exactly one URL: a site (an
      artifact when it is a claude.ai link), named by the label.

    A line with two URLs, or with a URL inside a command, says nothing."""
    out: list[dict[str, str]] = []
    secs = sections(record)
    seen: set[str] = set()
    for sec in ("Where", "How"):
        for raw in secs.get(sec, "").split("\n"):
            line = raw.strip().lstrip("-*0123456789. ").strip()
            urls = _URL.findall(line)
            if len(urls) != 1:
                continue
            url = urls[0].rstrip(".")
            ticks = _TICK.findall(line)
            if any(url in t for t in ticks):
                continue
            loc = _local(url)
            if loc is not None:
                commands = [t.strip() for t in ticks if t.strip().startswith(_RUNNERS)]
                folders = [m.strip() for m in _FOLDER.findall(line)]
                folder = folders[0] if len(folders) == 1 else ""
                way = {"name": f"{loc[0]}:{loc[1]}", "kind": "page", "url": url, "port": str(loc[1]),
                       "command": commands[0] if len(commands) == 1 else "",
                       "folder": folder if folder and not folder.startswith(_RUNNERS) else ""}
            elif sec == "Where":
                head, sep, _rest = line.partition(": ")
                if not sep or "http" in head or not head.strip() or len(head) > NAME_MAX or line.index(url) < len(head):
                    continue
                label = head.strip().strip("*`_ ")
                if not label:
                    continue
                host = (urllib.parse.urlsplit(url).hostname or "").lower()
                way = {"name": label, "kind": "artifact" if host == "claude.ai" else "site", "url": url,
                       "port": "", "command": "", "folder": ""}
            else:
                continue
            if way["url"] in seen:
                continue
            seen.add(way["url"])
            out.append(way)
    return out


def migrate(data_root: Path, *, backup: bool = True) -> dict[str, Any]:
    """Bring the records written before ways in existed into the new shape,
    once per record. Runs at start, under one lock for the whole run.

    Per record not done yet: ways in parsed from its record where a line is
    unambiguous (parse_ways), written with actor "migration" under ids made
    from the record and the way (a rerun after a crash writes the same ids,
    never a second copy). The record itself is not touched: it is the
    Record face. ``state`` is not written: it reads from the old status.
    Before the first write, entrypoints.csv and the ledgers are copied to
    entrypoints-migration-<stamp>/ in the backup folder (beside the data
    root, never inside it). A file that cannot be read stops the run
    before anything is written. One run per data root: the marker says
    it ran, and an entry point kept later is never parsed."""
    root = Path(data_root)
    ent = ENTITIES["entrypoint"]
    csv_path = root / ent.csv
    if not csv_path.exists():
        return {"migrated": [], "ways": 0}
    marker = root / MIGRATION_FILE
    lock = lock_path(marker)
    with acquire_flock(lock):
        try:
            state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"{MIGRATION_FILE} cannot be read ({exc}); the migration is not run") from exc
        if not isinstance(state, dict):
            raise RuntimeError(f"{MIGRATION_FILE} is not an object; the migration is not run")
        if as_int(state.get("version")) >= MIGRATION_VERSION:
            # Once: an entry point kept later starts in the new shape.
            return {"migrated": [], "ways": 0}
        done: dict[str, str] = dict(state.get("done") or {})
        rows = read_rows(csv_path)
        todo = [r for r in rows if r.get("id") and r["id"] not in done
                and not str(r.get("archived_at") or "").strip()]
        known_ways = {w.get("id") for w in read_rows(root / WAYS_FILE)}
        plan: list[tuple[str, list[dict[str, str]]]] = []
        for r in todo:
            doc = resolve_under(root, str(r.get("md_ref") or ""))
            if doc is None or not doc.exists():
                plan.append((r["id"], []))     # no text yet: nothing to read
                continue
            try:
                doc.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"{r['id']}: its record cannot be read ({exc}); the migration is not run") from exc
            l2, _l3, _l4 = read_detail(root, str(r.get("md_ref") or ""))
            plan.append((r["id"], parse_ways(l2 or "")))
        if backup and any(ways for _, ways in plan):
            from .backup import backup_root_for
            stamp = time.strftime("%Y%m%d-%H%M%S")
            dest = backup_root_for(root) / f"entrypoints-migration-{stamp}"
            dest.mkdir(parents=True, exist_ok=True)
            for name in (ent.csv, WAYS_FILE, STOPS_FILE, SHOTS_FILE, TOPICS_FILE, MIGRATION_FILE):
                src = root / name
                if src.exists():
                    atomic_write(dest / name, src.read_bytes())
        at = now_iso()
        n = 0
        for ep_id, ways in plan:
            for i, w in enumerate(ways):
                wid = _mint("ew_", ep_id, "migration", w["url"])
                if wid in known_ways:
                    continue
                append_row(root / WAYS_FILE, ENTRYPOINT_WAY_COLUMNS, {
                    "id": wid, "entrypoint_id": ep_id, **w, "note": "", "position": str(i * 10 + 10),
                    "created_at": at, "updated_at": at, "actor": "migration", "removed_at": ""})
                known_ways.add(wid)
                n += 1
            done[ep_id] = at
        atomic_write(marker, json.dumps({"version": MIGRATION_VERSION, "done": done}, indent=1).encode("utf-8"))
        return {"migrated": [e for e, _ in plan], "ways": n}
