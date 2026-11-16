"""Next tasks offered after #done, and the operator's answer.

After the operator closes a task with ``#done``, the agent may offer up to
three next tasks — only steps without which the finished work stays
unfinished. The steps:

1. **the offer** — the agent calls ``task_done`` again with ``proposals``
   (``[{title, line}]``). The server compares each with the project's open
   tasks (similarlib), records the offer in ``next_tasks.csv`` and answers
   the line to show, numbered as recorded: ``Make these tasks? 1) … 2) …``.
   Only right after the ``#done`` (its turn is the chat's latest operator
   message), only when the ``#done`` moved a task, never in a helper chat.
   Sent again before the operator has chosen, it replaces the offer.
2. **the answer** — the operator's next message (the first turn after the
   offer that carries the operator's words). The agent calls
   ``next_tasks {numbers}``; the server reads that message from chat.md,
   which only the capture hook writes:

   - a message of numbers only (``2``, ``1, 3``, ``1 и 3``) chooses exactly
     those: the agent's numbers must be the same;
   - ``yes``/``all``/``да``/``все`` alone chooses every offered task;
   - a message with a command in it (``#now …``, ``#done``), or a question,
     chooses nothing: the operator moved on or asked;
   - any other message: the agent's numbers must each be written in it (the
     server checks that the operator wrote them, the agent reads what they
     meant: "1 and 3, not 2").

   Chosen proposals become tasks in the `agent` column, tag ag_followup, in
   the offer's project, never through the #task gate (which reads the
   operator's latest message as a command). Each is stamped with the
   answer's time, so a retry mints the same id and finds it.

Why the agent's call and not the hook: the hook would read this ledger on
every message for an event of a few times a day; the agent has to answer
the operator anyway; and the server still checks the operator's own words.
An offer nobody answered stays ``offered``; ``offers()`` shows the numbers
the operator did write, without writing anything.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .date_utils import now_iso
from .db import ViewStore
from .hookshared import command_text, plain_text
from .sessions import Turn, _operator_text, chat_path, helper_ids, parse_turns
from . import similarlib

NEXT_CSV = "next_tasks.csv"
NEXT_COLUMNS: tuple[str, ...] = (
    "id", "project", "agent_id", "done_turn", "closed", "offered_turn", "offered_at",
    "proposals", "state", "answered_turn", "answer", "chosen", "made", "answered_at",
)
# state: offered · made · skipped
PROPOSALS_MAX = 3
TITLE_MAX = 80
LINE_MAX = 300
TAG = "ag_followup"

MORE_THAN_THREE = ("at most three next tasks: when more honest next steps are left, the task is not "
                   "finished — say so to the operator in one line instead of offering them")

_lock = threading.Lock()


class NextRefused(Exception):
    """A request the operator's words do not support; nothing was written."""


# ---------------------------------------------------------------------------
# The shape an agent sends
# ---------------------------------------------------------------------------


def proposals_given(raw: Any) -> bool:
    """Whether a request carries proposals at all: absent, null, "" and []
    are the plain task_done."""
    return not (raw is None or raw == "" or raw == [])


def parse_proposals(raw: Any) -> list[dict[str, str]]:
    """``[{title, line}]`` from what an agent sends, or a 422 sentence.

    Taken: a list of objects; a plain string item as a title; the list
    written as JSON text (MCP clients send that). Refused by its shape: an
    object, a number, true; an item that is a list or a number; a field
    other than title and line, by name."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ValueError("proposals is a list of {title, line}, not text") from None
    if not isinstance(raw, list):
        raise ValueError(f"proposals is a list of {{title, line}}, not {type(raw).__name__}")
    if len(raw) > PROPOSALS_MAX:
        raise ValueError(MORE_THAN_THREE + f" ({len(raw)} sent)")
    out: list[dict[str, str]] = []
    for n, item in enumerate(raw, 1):
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            raise ValueError(f"proposal {n} is an object {{title, line}}, not {type(item).__name__}")
        extra = sorted(str(k) for k in item if k not in ("title", "line"))
        if extra:
            raise ValueError(f"proposal {n}: unknown field {', '.join(extra)} — a proposal has title and line")
        title, line = item.get("title"), item.get("line")
        if not isinstance(title, str) or (line is not None and not isinstance(line, str)):
            raise ValueError(f"proposal {n}: title and line are text")
        title = " ".join(title.split())
        line = " ".join((line or "").split())
        if not title:
            raise ValueError(f"proposal {n} needs a title")
        if len(title) > TITLE_MAX:
            raise ValueError(f"proposal {n}: a title is at most {TITLE_MAX} characters ({len(title)} sent)")
        if len(line) > LINE_MAX:
            raise ValueError(f"proposal {n}: a line is at most {LINE_MAX} characters ({len(line)} sent)")
        if any(p["title"].lower() == title.lower() for p in out):
            raise ValueError(f"proposal {n} repeats the title of another one")
        out.append({"title": title, "line": line})
    return out


def parse_numbers(raw: Any) -> list[int]:
    """The chosen numbers from what an agent sends: ``[1, 3]``, ``["1", "3"]``,
    ``"1,3"``, ``"[1,3]"``; [] and null choose none. Else a 422 sentence."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except ValueError:
            loaded = None
        raw = loaded if isinstance(loaded, list) else re.split(r"[\s,;]+", raw.strip())
    if isinstance(raw, bool) or isinstance(raw, int):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"numbers is a list such as [1, 3], not {type(raw).__name__}")
    out: list[int] = []
    for x in raw:
        if isinstance(x, bool):
            raise ValueError("numbers is a list such as [1, 3]: true and false are not numbers")
        if isinstance(x, str) and x.strip().isdigit():
            x = int(x.strip())
        if not isinstance(x, int):
            raise ValueError(f"numbers is a list such as [1, 3]: {x!r} is not a number")
        if x not in out:
            out.append(x)
    return sorted(out)


# ---------------------------------------------------------------------------
# The ledger and the chat
# ---------------------------------------------------------------------------


def rows(store: ViewStore) -> list[dict[str, str]]:
    return read_rows(store.data_root / NEXT_CSV)


def _rid(agent_id: str, done_turn: int) -> str:
    return "nx_" + hashlib.sha256(f"{agent_id}|{done_turn}".encode()).hexdigest()[:8]


def _save(store: ViewStore, rid: str, changes: dict[str, str]) -> None:
    def mutate(rs: list[dict[str, str]]) -> bool:
        for r in rs:
            if r.get("id") == rid:
                r.update(changes)
                return True
        return False
    rewrite_rows(store.data_root / NEXT_CSV, NEXT_COLUMNS, mutate)


def _turns(store: ViewStore, agent_id: str) -> list[Turn]:
    path = chat_path(store, agent_id)
    if path is None or agent_id in helper_ids(store):
        return []
    try:
        return parse_turns(path)
    except OSError:
        return []


def _said(t: Turn) -> str:
    return _operator_text(t).strip()


def _answer_turn(turns: list[Turn], after: int) -> Turn | None:
    """The operator's next message after turn ``after``: a turn the tool
    wrote (a notice, a tool result) is not one."""
    return next((t for t in turns if t.number > after and _said(t)), None)


_COMMAND_RE = re.compile(r"(?<![\w#])#[^\W\d_]")
# A number standing alone: not inside a date, a version, an id, a time, a
# percentage or another number.
_NUMBER_RE = re.compile(r"(?<![\w.,:/#-])(\d+)(?![\w%]|[.,:/-]\d)")
_FILLER = frozenset("""and и & + or make made please ok okay yes да сделай сделать создай создать
these them those the tasks task задачи задачу эти номер номера number numbers""".split())
_ALL = frozenset("yes all both да все всё оба обе ok okay ок давай sure go".split())


def read_answer(text: str, offered: int) -> dict[str, Any]:
    """What the operator's message says about an offer of ``offered`` tasks:
    ``{kind, numbers}``. kind: ``numbers`` (only numbers: exactly those),
    ``all``, ``command`` (a command in it: no choice), ``question``,
    ``text`` (anything else: ``numbers`` are the ones written in it)."""
    loud = command_text(text or "")
    if _COMMAND_RE.search(loud):
        return {"kind": "command", "numbers": []}
    body = plain_text(text or "").strip()
    if "?" in body:
        return {"kind": "question", "numbers": []}
    found = [int(m.group(1)) for m in _NUMBER_RE.finditer(body)]
    numbers = sorted({n for n in found if 1 <= n <= offered})
    words = re.findall(r"[^\W\d_]+", body.lower())
    rest = [w for w in words if w not in _FILLER]
    leftover = _NUMBER_RE.sub(" ", body)
    if found and not rest and all(1 <= n <= offered for n in found) and not re.search(r"\d", leftover):
        return {"kind": "numbers", "numbers": numbers}
    if not found and any(w in _ALL for w in words) and all(w in _ALL or w in _FILLER for w in words):
        return {"kind": "all", "numbers": list(range(1, offered + 1))}
    return {"kind": "text", "numbers": numbers}


# ---------------------------------------------------------------------------
# The offer
# ---------------------------------------------------------------------------


def offer(store: ViewStore, agent_id: str, project: str, done_turn: int, closed: list[str],
          proposals: list[dict[str, str]]) -> dict[str, Any]:
    """Record the offer of this #done and answer each proposal with its
    similar open tasks, and the line to show. Refused (NextRefused) when the
    #done is not the chat's latest operator message, or its offer was
    already made into tasks."""
    with _lock:
        turns = _turns(store, agent_id)
        said = [t for t in turns if _said(t)]
        if not said:
            raise NextRefused("next tasks are offered only in the operator's own chat")
        if said[-1].number != done_turn:
            raise NextRefused(
                f"next tasks are offered right after the #done (turn {done_turn}); the operator has "
                f"written since (turn {said[-1].number}): nothing is offered")
        rid = _rid(agent_id, done_turn)
        ledger = rows(store)
        old = next((r for r in ledger if r.get("id") == rid), None)
        if old is not None and old.get("state") == "made":
            raise NextRefused(f"the offer of this #done was made into tasks ({old.get('made')}): nothing changed")
        board = similarlib.board_for(store, project)
        out = []
        for n, p in enumerate(proposals, 1):
            out.append({"n": n, **p, "similar": similarlib.similar_tasks(
                store, project, p["title"], p["line"], tasks=board)})
        last = turns[-1].number
        row = {
            "id": rid, "project": project, "agent_id": agent_id, "done_turn": str(done_turn),
            "closed": ",".join(closed), "offered_turn": str(last), "offered_at": now_iso(),
            "proposals": json.dumps(out, ensure_ascii=False), "state": "offered",
            "answered_turn": "", "answer": "", "chosen": "", "made": "", "answered_at": "",
        }
        if old is None:
            append_row(store.data_root / NEXT_CSV, NEXT_COLUMNS, row)
        else:
            _save(store, rid, row)
    line = "Make these tasks? " + " ".join(f"{p['n']}) {p['title']}" for p in out)
    return {"offer": rid, "proposals": out, "show": line}


def _latest(store: ViewStore, agent_id: str) -> dict[str, str] | None:
    mine = [r for r in rows(store) if r.get("agent_id") == agent_id]
    if not mine:
        return None
    return max(mine, key=lambda r: (int(r.get("offered_turn") or 0), int(r.get("done_turn") or 0)))


def make(store: ViewStore, agent_id: str, numbers: list[int]) -> dict[str, Any]:
    """Make the tasks the operator chose from the chat's latest offer."""
    with _lock:
        row = _latest(store, agent_id)
        if row is None:
            raise NextRefused("no next tasks were offered in this chat: offer them with task_done after a #done")
        proposals = json.loads(row.get("proposals") or "[]")
        if row.get("state") == "made":
            return _answer(row, proposals, again=True)
        if row.get("state") == "skipped":
            raise NextRefused("the operator's answer to this offer chose nothing: nothing was made")
        turns = _turns(store, agent_id)
        nxt = _answer_turn(turns, int(row.get("offered_turn") or 0))
        if nxt is None:
            raise NextRefused("the operator has not answered the offer yet: wait for their reply, then call "
                              "next_tasks; do not ask again")
        said = read_answer(_said(nxt), len(proposals))
        bad = [n for n in numbers if not 1 <= n <= len(proposals)]
        if bad:
            raise NextRefused(f"{', '.join(map(str, bad))}: the offer has {len(proposals)} tasks, numbered from 1")
        if said["kind"] in ("command", "question"):
            _save(store, row["id"], {"state": "skipped", "answered_turn": str(nxt.number),
                                     "answer": said["kind"], "answered_at": now_iso()})
            why = ("their message is a command: they moved on" if said["kind"] == "command"
                   else "they asked a question: answer it; offer again with task_done after a new #done only")
            return {"offer": row["id"], "made": [], "chosen": [], "skipped": True,
                    "next": f"Nothing was made: {why}."}
        if said["kind"] in ("numbers", "all") and numbers != said["numbers"]:
            raise NextRefused(
                f"the operator chose {', '.join(map(str, said['numbers']))}"
                f"{' (all)' if said['kind'] == 'all' else ''}: send exactly those numbers")
        missing = [n for n in numbers if n not in said["numbers"]]
        if missing:
            raise NextRefused(f"{', '.join(map(str, missing))} is not in the operator's answer "
                              f"(turn {nxt.number}): send only numbers they wrote")
        if not numbers:
            _save(store, row["id"], {"state": "skipped", "answered_turn": str(nxt.number),
                                     "answer": said["kind"], "answered_at": now_iso()})
            return {"offer": row["id"], "made": [], "chosen": [], "skipped": True,
                    "next": "Nothing was made: the operator chose none."}
        made: list[str] = []
        for n in numbers:
            p = proposals[n - 1]
            made.append(_create(store, row, p, n, nxt))
            # Each id is in the ledger as it is made: a refusal of the next
            # one leaves the first recorded, and a retry finds it.
            _save(store, row["id"], {"made": ",".join(made)})
        _save(store, row["id"], {"state": "made", "answered_turn": str(nxt.number), "answer": said["kind"],
                                 "chosen": ",".join(map(str, numbers)), "made": ",".join(made),
                                 "answered_at": now_iso()})
        row = next(r for r in rows(store) if r.get("id") == row["id"])
    store.rebuild()
    return _answer(row, proposals)


def _create(store: ViewStore, row: dict[str, str], p: dict[str, Any], n: int, answer: Turn) -> str:
    """One chosen proposal as an agent's task, in the `agent` column."""
    from .tasklib import create_task

    closed = ", ".join(x for x in (row.get("closed") or "").split(",") if x)
    text = ((p.get("line") or "").strip() + "\n\n" if (p.get("line") or "").strip() else "") + (
        f"Follows from {closed}, closed with #done; the operator chose it from the next tasks offered then "
        f"(number {n}).")
    # The stamp is the operator's answer, not this moment: the same body
    # mints the same id, so a retry finds the task instead of making two.
    out = create_task(store, {
        "created_date": answer.at.strftime("%y%m-%d"), "created_time": answer.at.strftime("%H:%M"),
        "project": row.get("project") or "", "agent_id": row.get("agent_id") or "",
        "title": p["title"], "status": "agent", "tags": TAG, "description": text,
    }, chosen=True)
    return str((out.get("metadata") or {}).get("id") or "")


def _answer(row: dict[str, str], proposals: list[dict[str, Any]], again: bool = False) -> dict[str, Any]:
    made = [x for x in (row.get("made") or "").split(",") if x]
    chosen = [int(x) for x in (row.get("chosen") or "").split(",") if x.isdigit()]
    lines = [f"{tid} · {proposals[n - 1]['title']}" for tid, n in zip(made, chosen)]
    return {"offer": row["id"], "made": made, "chosen": chosen, "skipped": False, "existing": again,
            "next": "Say in one line which tasks were made, in the agent column: " + "; ".join(lines) + "."}


# ---------------------------------------------------------------------------
# Reading, for the two-week check
# ---------------------------------------------------------------------------


def offers(store: ViewStore, project: str = "", agent_id: str = "") -> list[dict[str, Any]]:
    """Every offer, newest first, with what the operator answered. An offer
    still ``offered`` shows the operator's next message read (``answer_in_chat``):
    nothing is written by this read."""
    out = []
    chats: dict[str, list[Turn]] = {}
    for r in rows(store):
        if project and r.get("project") != project or agent_id and r.get("agent_id") != agent_id:
            continue
        try:
            proposals = json.loads(r.get("proposals") or "[]")
        except ValueError:
            proposals = []
        item: dict[str, Any] = {**r, "proposals": proposals,
                                "closed": [x for x in (r.get("closed") or "").split(",") if x],
                                "made": [x for x in (r.get("made") or "").split(",") if x],
                                "chosen": [int(x) for x in (r.get("chosen") or "").split(",") if x.isdigit()]}
        if r.get("state") == "offered":
            agent = r.get("agent_id") or ""
            if agent not in chats:
                chats[agent] = _turns(store, agent)
            nxt = _answer_turn(chats[agent], int(r.get("offered_turn") or 0))
            item["answer_in_chat"] = (
                {"turn": nxt.number, **read_answer(_said(nxt), len(proposals))} if nxt else None)
        out.append(item)
    out.sort(key=lambda x: str(x.get("offered_at") or ""), reverse=True)
    return out
