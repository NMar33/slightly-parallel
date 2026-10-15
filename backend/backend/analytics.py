"""Analytics — Slightly Parallel's data as tables anyone can query.

A separate, in-memory DuckDB holds copies of a few tables built from the
store — ``messages``, ``chats``, ``tasks``, ``task_events`` — rebuilt when
the store is (``view_mtime``). Queries run there, never on the store: a
query cannot change a ledger, and once the tables are loaded the engine is
shut off from the file system (``enable_external_access = false``), so
``read_csv('/etc/…')`` is refused too. Only one statement, SELECT or WITH;
at most ``MAX_ROWS`` rows back; ``TIMEOUT_S`` seconds, then it is stopped.

The pages (the notebook, the builder, the pipeline) all end in SQL here.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from typing import Any

import duckdb

from . import statslib
from .db import ViewStore
from .sessions import _TASK_ID_RE

MAX_ROWS = 5000
MEMORY_LIMIT = "512MB"

#: What keeps a query from doing harm, in the order it is checked. The page
#: shows this list, so what it says is what the code does.
SAFETY: list[str] = [
    "It runs on a copy in memory. Slightly Parallel's own files are never opened by a query.",
    "One statement, and the database itself must read it as a SELECT: no DELETE, UPDATE, DROP, COPY, ATTACH, SET, INSTALL.",
    "The copy cannot reach the disk or the network: file and web access are switched off, and the setting is locked.",
    f"At most {MAX_ROWS} rows and 20 MB of text back, 512 MB of memory and no spilling to disk, and 10 seconds; then it is stopped.",
    "After every query the tables are counted; if anything changed, the copy is thrown away and made again.",
]
TIMEOUT_S = 10.0
_COMMAND = re.compile(r"(?<![\w#])#([a-z][a-z-]{1,24})\b", re.IGNORECASE)
_WORDS = re.compile(r"\S+")
_PASTED = re.compile(r"<pasted_content[^>]*>([\s\S]*?)</pasted_content[^>]*>")

# name → (description, [(column, type, what it holds)])
SCHEMA: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "messages": ("Every message you sent, with its answer.", [
        ("id", "VARCHAR", "agent#turn"), ("project", "VARCHAR", "project code"),
        ("agent_id", "VARCHAR", "the chat's agent"), ("agent_name", "VARCHAR", "the agent's name"),
        ("chat_id", "VARCHAR", "the chat"), ("turn", "INTEGER", "turn number in the agent's chat"),
        ("sent_at", "TIMESTAMP", "when you sent it"), ("day", "DATE", "the day"), ("hour", "INTEGER", "0–23"),
        ("weekday", "VARCHAR", "Mon … Sun"), ("words", "INTEGER", "words you typed (pasted text left out)"),
        ("pasted_words", "INTEGER", "words you pasted"), ("answer_words", "INTEGER", "words in the answer"),
        ("commands", "VARCHAR", "the #commands in it, comma-separated"), ("tasks", "VARCHAR", "task ids it names"),
        ("has_task", "BOOLEAN", "names a task"),
    ]),
    "chats": ("Every chat: a run of messages without a long pause.", [
        ("id", "VARCHAR", "chat id"), ("project", "VARCHAR", "project code"), ("agent_id", "VARCHAR", "agent"),
        ("agent_name", "VARCHAR", "the agent's name"), ("day", "DATE", "the day it started"),
        ("started", "TIMESTAMP", "first message"), ("minutes", "INTEGER", "its length, first message to last answer"),
        ("agent_minutes", "INTEGER", "of those, the agent or its helpers working"),
        ("helper_minutes", "INTEGER", "its helpers' own minutes, added up"),
        ("messages", "INTEGER", "messages in it"), ("title", "VARCHAR", "its first line"),
    ]),
    "tasks": ("Every task on the board, with what it took.", [
        ("id", "VARCHAR", "task id"), ("project", "VARCHAR", "project"), ("title", "VARCHAR", "title"),
        ("status", "VARCHAR", "status"), ("priority", "VARCHAR", "priority"), ("assignee", "VARCHAR", "assignee"),
        ("sprint_id", "VARCHAR", "sprint"), ("tags", "VARCHAR", "tags, comma-separated"),
        ("created", "TIMESTAMP", "created"), ("done_at", "TIMESTAMP", "finished"),
        ("messages", "INTEGER", "messages in its stretch"), ("minutes", "INTEGER", "time in the chat"),
        ("chats", "INTEGER", "chats that named it"), ("commits", "INTEGER", "commits"), ("files", "INTEGER", "files"),
        ("lines_add", "INTEGER", "lines added"), ("lines_del", "INTEGER", "lines removed"),
        ("lead_hours", "DOUBLE", "created → done"), ("work_hours", "DOUBLE", "first message → done"),
        ("closed", "VARCHAR", "#done or board"), ("stretch", "VARCHAR", "done (exact) · estimated · none"),
        ("reopened", "INTEGER", "times reopened"), ("moves", "INTEGER", "status changes"),
    ]),
    "task_events": ("Every change on the board.", [
        ("changed_at", "TIMESTAMP", "when"), ("task_id", "VARCHAR", "task"), ("actor", "VARCHAR", "operator or an agent"),
        ("field", "VARCHAR", "what changed"), ("old_value", "VARCHAR", "before"), ("new_value", "VARCHAR", "after"),
    ]),
}

EXAMPLES: list[tuple[str, str]] = [
    ("Messages a day, the last 30 days",
     "SELECT day, count(*) AS messages\nFROM messages\nWHERE day >= current_date - 30\nGROUP BY day\nORDER BY day"),
    ("When do you work? Messages by hour",
     "SELECT hour, count(*) AS messages\nFROM messages\nGROUP BY hour\nORDER BY hour"),
    ("The busiest agents",
     "SELECT agent_name, count(*) AS messages, sum(answer_words) AS words_back\nFROM messages\nGROUP BY agent_name\nORDER BY messages DESC\nLIMIT 10"),
    ("Commands you use",
     "SELECT trim(c) AS command, count(*) AS times\nFROM messages, unnest(string_split(commands, ',')) AS t(c)\nWHERE commands <> ''\nGROUP BY command\nORDER BY times DESC"),
    ("Tasks finished a week",
     "SELECT date_trunc('week', done_at) AS week, count(*) AS finished\nFROM tasks\nWHERE done_at IS NOT NULL\nGROUP BY week\nORDER BY week"),
    ("How long a task takes, by priority",
     "SELECT priority, count(*) AS tasks, round(median(lead_hours), 1) AS median_hours\nFROM tasks\nWHERE lead_hours IS NOT NULL\nGROUP BY priority\nORDER BY median_hours DESC"),
]

_lock = threading.Lock()
_state: dict[str, Any] = {"key": None, "con": None, "counts": {}}


def _ts(day: str, hm: str) -> str | None:
    if len(day) == 7 and day[4] == "-":
        return f"20{day[:2]}-{day[2:4]}-{day[5:7]} {(hm or '00:00')[:5]}:00"
    return None


def _count(text: str) -> int:
    # str.split() and \S+ split on the same whitespace (Py_UNICODE_ISSPACE);
    # split does it without building a match object per word.
    return len((text or "").split())


def _load(store: ViewStore) -> tuple[duckdb.DuckDBPyConnection, dict[str, int]]:
    # The label the pages show: the agent's name, else its chat's title, else the id.
    names: dict[str, str] = {}
    for a in store.agents():
        aid = str(a.get("agent_id") or "")
        name = str(a.get("agent_name") or "").strip()
        names[aid] = name if name and name != aid else (str(a.get("chat_title") or "").strip() or aid)
    messages: list[tuple] = []
    chats: list[tuple] = []
    for s in store.query("SELECT id, project, agent_id, created_date, start_time, duration_min, agent_min, helper_min, turns_n, l1, turns_json FROM sessions"):
        try:
            turns = json.loads(s.get("turns_json") or "[]")
        except ValueError:
            turns = []
        agent = str(s["agent_id"] or "")
        day = str(s["created_date"] or "")
        chats.append((s["id"], s["project"], agent, names.get(agent, ""), _ts(day, "00:00") and _ts(day, "00:00")[:10],
                      _ts(day, str(s["start_time"] or "")), int(s["duration_min"] or 0), int(s["agent_min"] or 0),
                      int(s["helper_min"] or 0),
                      int(s["turns_n"] or 0),
                      str(s["l1"] or "")[:200]))
        prev = -1
        roll = 0
        base = datetime.strptime(_ts(day, "00:00") or "2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        for t in turns:
            at = str(t.get("at") or "")
            mins = int(at[:2]) * 60 + int(at[3:5]) if len(at) >= 5 and at[:2].isdigit() else 0
            if mins < prev:
                roll += 1                     # past midnight within one chat
            prev = mins
            stamp = base.replace(hour=mins // 60, minute=mins % 60)
            if roll:
                stamp = stamp.fromordinal(stamp.toordinal() + roll).replace(hour=mins // 60, minute=mins % 60)
            user = str(t.get("user") or "")
            pasted = " ".join(m.group(1) for m in _PASTED.finditer(user))
            typed = _PASTED.sub(" ", user)
            cmds = sorted({m.group(1).lower() for m in _COMMAND.finditer(typed)})
            ids = sorted({m.group(1) for m in _TASK_ID_RE.finditer(user) if m.group(1).startswith("tk_")})
            messages.append((
                f"{agent}#{t.get('n')}", s["project"], agent, names.get(agent, ""), s["id"], int(t.get("n") or 0),
                stamp, stamp.date(), stamp.hour, stamp.strftime("%a"), _count(typed), _count(pasted),
                _count(str(t.get("agent") or "")), ",".join(cmds), ",".join(ids), bool(ids),
            ))
    tasks = [(
        r["id"], r["project"], r["title"], r["status"], r.get("priority") or "", r.get("assignee") or "",
        r["sprint_id"], ",".join(r.get("tags") or []), (r["created"] or None) and r["created"].replace("T", " ") + ":00",
        (r["done_at"] or None) and r["done_at"].replace("T", " ")[:16] + ":00",
        r["messages"], r["minutes"], r.get("named_in", 0), r["commits"], r["files"], r["add"], r["del"],
        r["lead_hours"], r["work_hours"], r["closed"], r["stretch"], r["reopened"], r.get("moves", 0),
    ) for r in statslib.task_rows(store)]
    events = [(str(e["timestamp"]).replace("T", " ")[:19] or None, e["task_id"], e["actor"], e["field"],
               e["old_value"], e["new_value"]) for e in store.query(
        "SELECT timestamp, task_id, actor, field, old_value, new_value FROM task_events_mutual")]

    con = duckdb.connect(":memory:")
    con.execute("SET threads TO 2")
    data = {"messages": messages, "chats": chats, "tasks": tasks, "task_events": events}
    for name, (_, cols) in SCHEMA.items():
        con.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t, _ in cols)})")
        rows = data[name]
        if rows:
            # One JSON document per table: row-by-row inserts took a second a
            # few thousand rows; this takes milliseconds.
            doc = json.dumps([{c: _plain(v) for (c, _, _), v in zip(cols, r)} for r in rows], default=str)
            shape = json.dumps([{c: t for c, t, _ in cols}])
            con.execute(f"INSERT INTO {name} SELECT unnest(from_json(?, '{shape}'), recursive := true)", [doc])
    # From here on the engine cannot reach a file: queries see these tables only.
    # No spilling (set first: with file access off it can no longer be set): a big sort would otherwise write gigabytes to a temp
    # folder beside the server — "cannot reach the disk" is meant literally.
    con.execute("SET temp_directory = ''")
    con.execute("SET max_temp_directory_size = '0B'")
    con.execute("SET enable_external_access = false")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute("SET lock_configuration = true")
    return con, {k: len(v) for k, v in data.items()}


def _engine(store: ViewStore) -> tuple[duckdb.DuckDBPyConnection, dict[str, int]]:
    key = (str(store.data_root), store.view_mtime)
    with _lock:
        if _state["key"] != key or _state["con"] is None:
            # The old copy is left to go when the last query on it ends: closing
            # it here would pull it from under a query still running.
            _state["con"], _state["counts"] = _load(store)
            _state["key"] = key
        return _state["con"], _state["counts"]


def schema(store: ViewStore) -> dict[str, Any]:
    _, counts = _engine(store)
    return {
        "tables": [{"name": n, "about": about, "rows": counts.get(n, 0),
                    "columns": [{"name": c, "type": t, "about": a} for c, t, a in cols]}
                   for n, (about, cols) in SCHEMA.items()],
        "examples": [{"title": t, "sql": q} for t, q in EXAMPLES],
        "safety": SAFETY,
    }


class QueryError(ValueError):
    pass


MAX_BYTES = 20_000_000   # of text in one answer, whatever the row count


def _size(row: tuple) -> int:
    return sum(len(v) if isinstance(v, (str, bytes)) else 16 for v in row)


def run(store: ViewStore, sql: str) -> dict[str, Any]:
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise QueryError("Write a query: SELECT … FROM messages, chats, tasks or task_events.")
    con, counts = _engine(store)
    # The database reads the text itself: one statement, and a SELECT —
    # a keyword check alone could be fooled by a comment or a WITH clause.
    try:
        statements = con.extract_statements(text)
    except duckdb.Error as exc:
        raise QueryError(str(exc).split("\n")[0])
    if len(statements) != 1:
        raise QueryError("One query at a time: take out the ';' between them.")
    kind = str(statements[0].type).rsplit(".", 1)[-1]
    if kind != "SELECT":
        raise QueryError(f"Only reading: this is a {kind} statement, and only SELECT runs here.")
    cur = con.cursor()
    timer = threading.Timer(TIMEOUT_S, cur.interrupt)
    t0 = time.perf_counter()
    timer.start()
    try:
        rel = cur.execute(text)
        cols = [{"name": d[0], "type": str(d[1])} for d in (rel.description or [])]
        # Fetched in slices, counting the text: 5000 rows of 200 kB each
        # were a gigabyte past the memory limit.
        rows: list[tuple] = []
        size = 0
        while len(rows) <= MAX_ROWS:
            part = rel.fetchmany(500)
            if not part:
                break
            for r in part:
                size += _size(r)
                rows.append(r)
            if size > MAX_BYTES:
                raise QueryError(f"The answer is larger than {MAX_BYTES // 1_000_000} MB of text: "
                                 "ask for fewer rows or shorter columns (LIMIT, left(text, 200)).")
    except duckdb.InterruptException:
        raise QueryError(f"The query ran longer than {TIMEOUT_S:.0f} seconds and was stopped.")
    except duckdb.Error as exc:
        raise QueryError(str(exc).split("\n")[0])
    finally:
        timer.cancel()
        cur.close()
    _check_intact(con, counts, text)
    truncated = len(rows) > MAX_ROWS
    out = [[_json(v) for v in r] for r in rows[:MAX_ROWS]]
    return {"columns": cols, "rows": out, "truncated": truncated,
            "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _check_intact(con: duckdb.DuckDBPyConnection, counts: dict[str, int], _sql: str = "") -> None:
    """The tables still hold what was loaded; if not, the copy is discarded."""
    # A cursor of its own: queries run side by side, and a shared connection
    # handed one thread's result to another.
    cur = con.cursor()
    try:
        now = {n: (cur.execute(f"SELECT count(*) FROM {n}").fetchone() or [None])[0] for n in SCHEMA}
    except duckdb.Error:
        now = {}
    finally:
        cur.close()
    if now != counts:
        with _lock:
            # Only this copy: a newer one loaded meanwhile is not thrown away.
            if _state.get("con") is con:
                _state["key"] = None      # the next query loads a fresh copy
        raise QueryError("The copy changed during the query and was thrown away. Your data is untouched.")


def _plain(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _json(v: Any) -> Any:
    if isinstance(v, (datetime,)):
        return v.isoformat(timespec="minutes")
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)
