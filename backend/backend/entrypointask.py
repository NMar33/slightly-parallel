"""The #entrypoint command's question: which topic the operator means.

The operator does not remember topic names. So ``#entrypoint`` with any
text (a name, a description, or nothing) makes nothing when it is seen
(keeplib.adopt keeps the command as pending, entrypointlib.take_command).
Only the exact name of one named topic of the project opens a new version
of that topic at once; the agent then says which topic it was.

1. **the question** — the agent calls ``entrypoint_ask {id, name}`` right
   after the notice, ``name`` its proposal for a new topic (the server
   cannot name a topic from a description, nor from the command alone).
   The server finds the candidates, of the chat's project only, at most
   three, taken in turn from three sources so each is heard:

   - the message's text, compared with each topic's name, first line, What
     and ways in (entrypointlib.similar: similarlib's word search);
   - the topics this chat already worked on: the commands it answered, the
     versions it wrote, its stops, its ways in, its shots; newest first;
   - the topics of the tasks named in this chat, the latest mention first.

   The last line is always "A new topic: «name»". The numbered lines are
   recorded in ``entrypoint_asks.csv`` with the chat's last turn; the
   agent shows ``show`` as it is. With no candidate the line is one: "A new
   topic: «name»?". Asked again before the operator answered, the question
   is replaced; after an answer that was not read yet, it is refused.
2. **the answer** — the operator's next message after the question. The
   agent calls ``entrypoint_answer {number, name?}``; the server reads the
   message from chat.md, which only the capture hook writes (as nextlib
   does for next tasks):

   - a command in it chooses nothing (the operator moved on), and the
     command is dropped; a question chooses nothing yet: the agent answers
     it and asks again;
   - one number of the list chooses that line, and the agent's number must
     be the same; text after it is a name (``3 Консоль текстов``); two
     numbers, or one outside the list, choose nothing: the agent asks again;
   - ``yes`` alone chooses the only line; ``no`` alone chooses nothing; a
     message without a number, when the only line is the new topic, may be
     its name: the agent says so by sending 1;
   - the agent's ``name`` must be written in the operator's message.

   An existing topic chosen opens a new version of its record for this
   chat (an unnamed one takes the name given). The new-topic line chosen
   makes the topic then, from the command's message (its kept text, turn
   and chat), with the name given or the one proposed. A retry answers the
   same; the topic's id is the command's, so it is never made twice.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from typing import Any

from . import entrypointlib as E
from . import keeplib
from .csvio import append_row, as_int, read_rows, rewrite_rows
from .date_utils import now_iso
from .db import ViewStore
from .entities import ENTRYPOINT_ASK_COLUMNS
from .hookshared import command_text, plain_text
from .nextlib import _COMMAND_RE, _NUMBER_RE, _answer_turn, _said, _turns
from .sessions import helper_ids

ASKS_FILE = "entrypoint_asks.csv"
CANDIDATES_MAX = 3
STOP_SHOWN = 60
OPEN = ("offered",)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_lock = threading.Lock()


class AskRefused(Exception):
    """A request the chat or the operator's words do not support; nothing was written."""


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def rows(store: ViewStore) -> list[dict[str, str]]:
    return read_rows(store.data_root / ASKS_FILE)


def _save(store: ViewStore, rid: str, changes: dict[str, str]) -> None:
    def mutate(rs: list[dict[str, str]]) -> bool:
        for r in rs:
            if r.get("id") == rid:
                r.update(changes)
                return True
        return False
    rewrite_rows(store.data_root / ASKS_FILE, ENTRYPOINT_ASK_COLUMNS, mutate)


def _lines(row: dict[str, str]) -> list[dict[str, Any]]:
    try:
        got = json.loads(row.get("lines") or "[]")
    except ValueError:
        return []
    return got if isinstance(got, list) else []


def _mark(store: ViewStore, cmd: dict[str, str]) -> dict[str, Any] | None:
    """The command's message as the chat log holds it (keep_marks)."""
    return store.query_one(
        "SELECT kind, project, agent_id, session_id, turn, at_ts, title, body FROM keep_marks "
        "WHERE kind = 'entrypoint' AND agent_id = ? AND project = ? AND turn = ?",
        (cmd.get("agent_id") or "", cmd.get("project") or "", as_int(cmd.get("turn"))))


# ---------------------------------------------------------------------------
# The candidates
# ---------------------------------------------------------------------------


def _day(at: str) -> str:
    try:
        d = datetime.fromisoformat(str(at or "")[:19])
    except ValueError:
        return ""
    return f"{d.day} {_MONTHS[d.month - 1]}"


def _worked_on(store: ViewStore, agent: str) -> list[str]:
    """The topics this chat wrote on, newest first."""
    seen: dict[str, str] = {}

    def add(ep_id: str, at: str) -> None:
        if ep_id and at >= seen.get(ep_id, ""):
            seen[ep_id] = at
    for c in E.commands(store):
        if c.get("agent_id") == agent and c.get("entrypoint_id"):
            add(str(c["entrypoint_id"]), str(c.get("chosen_at") or c.get("at") or ""))
    for r in read_rows(store.data_root / E.AUTHORS_FILE):
        if r.get("agent_id") == agent:
            add(str(r.get("entrypoint_id") or ""), str(r.get("at") or ""))
    for r in read_rows(store.data_root / E.STOPS_FILE):
        if r.get("author") == agent and E._live(r):
            add(str(r.get("entrypoint_id") or ""), str(r.get("at") or ""))
    for r in read_rows(store.data_root / E.WAYS_FILE):
        if r.get("actor") == agent and E._live(r):
            add(str(r.get("entrypoint_id") or ""), str(r.get("updated_at") or r.get("created_at") or ""))
    for r in read_rows(store.data_root / E.SHOTS_FILE):
        if r.get("agent_id") == agent and E._live(r):
            add(str(r.get("entrypoint_id") or ""), str(r.get("at") or ""))
    return [k for k, _ in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)]


def _of_tasks(store: ViewStore, agent: str) -> list[str]:
    """The topics of the tasks named in this chat, the latest mention first."""
    by_task = E.topics_by_task(store)
    if not by_task:
        return []
    out: list[str] = []
    for m in store.query("SELECT task_id, max(turn) AS turn FROM task_mentions WHERE agent_id = ? "
                         "GROUP BY task_id ORDER BY max(turn) DESC, task_id", (agent,)):
        ep_id = by_task.get(str(m.get("task_id") or ""))
        if ep_id and ep_id not in out:
            out.append(ep_id)
    return out


def candidates(store: ViewStore, project: str, agent: str, text: str) -> list[dict[str, Any]]:
    """At most three topics of ``project`` the command may mean, each with
    why (text · work · task), taken in turn from the three sources."""
    live = {r["id"]: r for r in E.entries(store, project)}
    if not live:
        return []
    sources = [
        ("text", [h["id"] for h in E.similar(store, project, text)] if text.strip() else []),
        ("work", _worked_on(store, agent)),
        ("task", _of_tasks(store, agent)),
    ]
    picked: list[tuple[str, str]] = []
    queues = [(why, [i for i in ids if i in live]) for why, ids in sources]
    while len(picked) < CANDIDATES_MAX and any(q for _, q in queues):
        for why, q in queues:
            while q and any(q[0] == p for p, _ in picked):
                q.pop(0)
            if q and len(picked) < CANDIDATES_MAX:
                picked.append((q.pop(0), why))
    out = []
    for ep_id, why in picked:
        row = live[ep_id]
        stops = E.stops_of(store, ep_id)
        out.append({"id": ep_id, "name": E.name_of(row) or E._title(row), "named": bool(E.name_of(row)),
                    "why": why, "stop": " ".join(str(stops[0].get("text") or "").split()) if stops else "",
                    "stop_at": str(stops[0].get("at") or "") if stops else ""})
    return out


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _line(item: dict[str, Any]) -> str:
    if item["kind"] == "new":
        return f"A new topic: «{item['name']}»"
    head = _clip(item["name"], E.NAME_MAX)
    if item.get("stop"):
        return f"{head} — last stop {_day(item['stop_at'])}: {_clip(item['stop'], STOP_SHOWN)}"
    return f"{head} — no stop yet"


def show_of(lines: list[dict[str, Any]]) -> str:
    if len(lines) == 1:
        return _line(lines[0]) + "?"
    return "Is this one of the topics? " + " ".join(f"{x['n']}) {_line(x)}" for x in lines)


# ---------------------------------------------------------------------------
# The question
# ---------------------------------------------------------------------------


def _clean_name(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise AskRefused("name is text: the name you propose for a new topic, about four words")
    name = " ".join(raw.split()).strip(" «»\"'")
    if len(name) > E.NAME_MAX:
        raise AskRefused(f"a topic's name is at most {E.NAME_MAX} characters ({len(name)} sent)")
    return name


def _command_for(store: ViewStore, agent: str, cmd_id: str) -> dict[str, str]:
    if agent in helper_ids(store):
        raise AskRefused("a helper chat keeps no entry point: nothing was written")
    cmd = E.command_of(store, cmd_id)
    if cmd is None:
        raise LookupError(cmd_id)
    if cmd.get("agent_id") != agent:
        raise AskRefused(f"{cmd_id} was typed in another chat ({cmd.get('agent_id')}): its agent asks the "
                         "operator. Nothing was written")
    return cmd


def ask(store: ViewStore, agent: str, cmd_id: str, name: Any = None) -> dict[str, Any]:
    """Record the question for this chat's pending #entrypoint and answer
    the line to show. A command already answered answers what it opened."""
    proposed = _clean_name(name)
    with _lock:
        cmd = _command_for(store, agent, cmd_id)
        if cmd.get("how") != "pending":
            view = E.command_view(store, cmd_id)
            if view.get("id"):
                view["next"] = f"{view['next']} {after_record(store, view, cmd)}"
            return {"asked": False, **view}
        turns = _turns(store, agent)
        if not turns:
            raise AskRefused("the chat's log is not readable: nothing was asked")
        old = next((r for r in rows(store) if r.get("id") == cmd_id), None)
        if old is not None and old.get("state") in OPEN:
            nxt = _answer_turn(turns, as_int(old.get("offered_turn")))
            if nxt is not None:
                raise AskRefused(
                    f"the operator answered the question (turn {nxt.number}): call entrypoint_answer with the "
                    "number they chose (0 when none). Nothing was asked again")
        mark = _mark(store, cmd)
        body = str((mark or {}).get("body") or "").strip()
        if not proposed:
            forms = E._name_forms(str((mark or {}).get("title") or ""))
            proposed = " ".join((forms[-1] if forms else "").split())[:E.NAME_MAX].strip()
        if not proposed:
            raise AskRefused("the command has no words: send name, the name you propose for a new topic "
                             "(about four words, from this chat). Nothing was asked")
        found = candidates(store, str(cmd.get("project") or ""), agent, body)
        lines: list[dict[str, Any]] = [{"n": i, "kind": "topic", **c} for i, c in enumerate(found, 1)]
        lines.append({"n": len(lines) + 1, "kind": "new", "name": proposed})
        rev = as_int((old or {}).get("rev")) + 1
        row = {
            "id": cmd_id, "project": cmd.get("project") or "", "agent_id": agent,
            "command_turn": str(cmd.get("turn") or ""), "rev": str(rev),
            "offered_turn": str(turns[-1].number), "offered_at": now_iso(), "proposed": proposed,
            "lines": json.dumps(lines, ensure_ascii=False), "state": "offered",
            "answered_turn": "", "answer": "", "chosen": "", "name": "", "made": "", "answered_at": "",
        }
        if old is None:
            append_row(store.data_root / ASKS_FILE, ENTRYPOINT_ASK_COLUMNS, row)
        else:
            _save(store, cmd_id, row)
    show = show_of(lines)
    how = ("a number, or yes" if len(lines) == 1 else "a number") + "; for a new topic, its number and a name"
    return {
        "asked": True, "command": cmd_id, "rev": rev, "lines": lines, "show": show,
        "next": (f"Show the operator this line as it is, as the last line of your reply: {show} Nothing is "
                 f"made until they answer ({how}). Then call entrypoint_answer {{number, name?}}: number the "
                 f"line they chose, 0 when they chose none; name only when they wrote one, as they wrote it."),
    }


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------

# How the operator agrees, in English or Russian or both: the words, the
# softeners around them ("думаю да", "I think so", "yes please"), the signs.
_YES = frozenset("""yes yep yup yeah ya yah ok okay k sure go fine good great right correct agreed alright
perfect absolutely definitely exactly да ага угу ок окей ok давай верно точно конечно ладно хорошо годится
подходит идет идёт норм нормально отлично согласен согласна пойдет пойдёт""".split())
_SOFT = frozenset("""i think so guess suppose probably believe sounds looks seems that that's thats it is
please then let's lets do this one just думаю наверное пожалуй вроде кажется так пусть будет это вот тогда
пожалуйста давайте да-да""".split())
_YES_SIGNS = ("+", "👍", "✅", "✔", "👌", "🙂", "😊")
# A no: the words alone end the question; with more words, it is asked again.
_NO = frozenset("no nope nah none neither not never don't dont cancel нет неа не никакой никакая ничего отмена".split())
# The words that come before a name: "call it Review feed", "назови Консоль".
_NAMING = re.compile(r"^(?:call it|name it|named|called|назови(?:те)?(?: его| её| ее)?|пусть называется|"
                     r"название|имя)\b[\s:,—–-]*", re.I)
_EDGE = " \t\n,.;:!—–-()«»\"'+"
# Words beside a number that name nothing: "3 please", "the second, this one".
_FILLER = _YES | _SOFT | frozenset("the пожалуйста этот эта эту тот та".split())
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")


def _drop_yes(text: str) -> str:
    """The text with the agreement and the naming words in front of it taken
    off: what is left is a name, or nothing."""
    text = text.strip(_EDGE)
    while True:
        m = re.match(r"^[\W_]*?([^\W\d_]+(?:['’][^\W\d_]+)?)[\W_]*", text)
        n = _NAMING.match(text)
        if n is not None and n.end():
            text = text[n.end():].strip(_EDGE)
            continue
        if m is None or m.group(1).lower() not in (_YES | _SOFT):
            return text.strip(_EDGE)
        text = text[m.end():]


def _agrees(body: str, words: list[str]) -> bool:
    return any(w in _YES for w in words) or any(sign in body for sign in _YES_SIGNS) or (
        {"think", "so"} <= set(words))


def read_choice(text: str, offered: int) -> dict[str, Any]:
    """What the operator's message says about a list of ``offered`` lines:
    ``{kind, number, rest}``. kind: ``command`` (a command in it),
    ``question``, ``number`` (one number of the list; ``rest`` the name
    beside it), ``unclear`` (two numbers, one outside the list, or a no
    with more words), ``yes`` (agreement, in either language; ``rest`` a
    name written with it), ``no`` (a no alone), ``text`` (no number and no
    agreement: ``rest`` may be a name)."""
    if _COMMAND_RE.search(command_text(text or "")):
        return {"kind": "command", "number": 0, "rest": ""}
    body = plain_text(text or "").strip()
    if "?" in body:
        return {"kind": "question", "number": 0, "rest": ""}
    words = [w.lower() for w in _WORD.findall(body)]
    if words and all(w in _NO for w in words) and not re.search(r"\d", body):
        return {"kind": "no", "number": 0, "rest": ""}
    if any(w in _NO for w in words):
        return {"kind": "unclear", "number": 0, "rest": ""}
    found = [int(m.group(1)) for m in _NUMBER_RE.finditer(body)]
    if found:
        if len(set(found)) > 1 or not 1 <= found[0] <= offered:
            return {"kind": "unclear", "number": 0, "rest": ""}
        rest = _drop_yes(_NUMBER_RE.sub(" ", body, count=1))
        if all(w.lower() in _FILLER for w in _WORD.findall(rest)):
            rest = ""
        return {"kind": "number", "number": found[0], "rest": " ".join(rest.split())}
    rest = " ".join(_drop_yes(body).split())
    if _agrees(body, words):
        if all(w.lower() in _FILLER for w in _WORD.findall(rest)):
            rest = ""
        return {"kind": "yes", "number": 0, "rest": rest}
    return {"kind": "text", "number": 0, "rest": rest}


def _parse_number(raw: Any) -> int:
    if raw is None or raw == "":
        return 0
    if isinstance(raw, bool):
        raise ValueError("number is the number of the line the operator chose, 0 when none: not true or false")
    if isinstance(raw, list) and len(raw) <= 1:
        return _parse_number(raw[0] if raw else None)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    if not isinstance(raw, int) or raw < 0:
        raise ValueError(f"number is the number of the line the operator chose, 0 when none: not {raw!r}")
    return raw


def parse_number(raw: Any) -> int:
    """The agent's number: 1, "1", [1]; 0, null, "" and [] for none. Else a 422 sentence."""
    return _parse_number(raw)


def _open_ask(store: ViewStore, agent: str, cmd_id: str) -> dict[str, str] | None:
    mine = [r for r in rows(store) if r.get("agent_id") == agent and (not cmd_id or r.get("id") == cmd_id)]
    if not mine:
        return None
    opened = [r for r in mine if r.get("state") in OPEN]
    return max(opened or mine, key=lambda r: (as_int(r.get("offered_turn")), as_int(r.get("command_turn"))))


def _close(store: ViewStore, row: dict[str, str], turn: int, kind: str, state: str) -> None:
    _save(store, row["id"], {"state": state, "answered_turn": str(turn), "answer": kind,
                             "answered_at": now_iso()})


def _nothing(row: dict[str, str], state: str, why: str) -> dict[str, Any]:
    return {"command": row["id"], "state": state, "chosen": None, "opened": "nothing", "next": why}


def answer(store: ViewStore, agent: str, number: int, name: Any = None, cmd_id: str = "") -> dict[str, Any]:
    """The operator's answer to this chat's question: the topic they chose,
    opened or made; or nothing, and why."""
    given = _clean_name(name)
    with _lock:
        if agent in helper_ids(store):
            raise AskRefused("a helper chat keeps no entry point: nothing was written")
        row = _open_ask(store, agent, cmd_id)
        if row is None:
            raise AskRefused("no topic was asked about in this chat: after the operator's #entrypoint, call "
                             "entrypoint_ask first")
        lines = _lines(row)
        if row.get("state") == "chosen":
            return _result(store, row, lines, again=True)
        if row.get("state") == "dropped":
            return _nothing(row, "dropped", "The operator's answer chose no topic: nothing was made.")
        if row.get("state") != "offered":
            raise AskRefused("the question is not open: call entrypoint_ask to show the line again")
        turns = _turns(store, agent)
        nxt = _answer_turn(turns, as_int(row.get("offered_turn")))
        if nxt is None:
            raise AskRefused("the operator has not answered yet: wait for their reply, then call "
                             "entrypoint_answer; do not ask again")
        said = read_choice(_said(nxt), len(lines))
        kind = said["kind"]
        if kind == "command":
            _close(store, row, nxt.number, kind, "dropped")
            E.resolve_command(store, row["id"], ep_id="", how="dropped", at=nxt.at.isoformat(timespec="seconds"))
            return _nothing(row, "dropped", "Nothing was made: their message is a command, they moved on. To keep "
                                            "a topic they type the command again.")
        if kind == "question":
            _close(store, row, nxt.number, kind, "question")
            return _nothing(row, "question", "Nothing was chosen: they asked a question. Answer it, then call "
                                             "entrypoint_ask again and show its line.")
        single = len(lines) == 1
        if kind == "no":
            if number:
                raise AskRefused(f"the operator answered no (turn {nxt.number}): send number 0")
            _close(store, row, nxt.number, kind, "dropped")
            E.resolve_command(store, row["id"], ep_id="", how="dropped", at=nxt.at.isoformat(timespec="seconds"))
            return _nothing(row, "dropped", "Nothing was made: the operator answered no.")
        chosen = 0
        rest = said["rest"]
        if kind == "number":
            chosen = said["number"]
            if number != chosen:
                raise AskRefused(f"the operator chose {chosen} (turn {nxt.number}): send number {chosen}")
        elif kind == "yes" and single:
            chosen = 1
            if number != 1:
                raise AskRefused(f"the operator answered yes to the one line (turn {nxt.number}): send number 1")
        elif kind == "text" and single and number == 1:
            chosen = 1
        elif number:
            raise AskRefused(f"the operator's answer (turn {nxt.number}) has no number of the list in it: send 0, "
                             "then ask again")
        if not chosen:
            _close(store, row, nxt.number, kind, "unclear")
            why = ("they wrote two numbers or one not in the list" if kind == "unclear"
                   else "yes chooses only when there is one line" if kind == "yes" else "it has no number")
            return _nothing(row, "unclear", f"Nothing was chosen: {why}. Ask them for the number in one line and "
                                            "call entrypoint_ask again.")
        if given and E.name_key(given) not in E.name_key(rest):
            raise AskRefused(f"«{given}» is not in the operator's answer (turn {nxt.number}): send the name as "
                             "they wrote it, or none")
        if kind == "text" and not (given or rest):
            raise AskRefused("the operator's answer has no name in it: send number 0, then ask again")
        line = lines[chosen - 1]
        name_given = given or rest
        at = nxt.at.isoformat(timespec="seconds")
        if line.get("kind") == "new":
            made = _make_new(store, row, name_given or str(line.get("name") or ""), at)
        else:
            made = _open_existing(store, row, line, name_given, at)
            if made is None:
                _close(store, row, nxt.number, kind, "unclear")
                return _nothing(row, "unclear", f"«{line.get('name')}» was archived after the question: nothing "
                                                "was chosen. Call entrypoint_ask again and show its line.")
        _save(store, row["id"], {"state": "chosen", "answered_turn": str(nxt.number), "answer": kind,
                                 "chosen": str(chosen), "name": name_given, "made": made,
                                 "answered_at": now_iso()})
        row = next(r for r in rows(store) if r.get("id") == row["id"])
    store.rebuild()
    return _result(store, row, lines)


def _make_new(store: ViewStore, row: dict[str, str], name: str, at: str) -> str:
    """The new topic, from the command's message; its id is the command's."""
    cmd = E.command_of(store, row["id"]) or {}
    mark = _mark(store, cmd)
    if mark is None:
        raise AskRefused("the command's message is no longer in the chat log: nothing was made")
    with keeplib._adopt_lock:
        keeplib.make_row(store, "entrypoint", row["id"], mark, title=name if not str(mark.get("body") or "").strip()
                         else "", fields={"topic": name})
        E.resolve_command(store, row["id"], ep_id=row["id"], how="new", at=at)
    return row["id"]


def _open_existing(store: ViewStore, row: dict[str, str], line: dict[str, Any], name: str, at: str) -> str | None:
    """A new version of the chosen topic, for this chat; the name given to
    a topic that had none. None when the topic is gone from the project."""
    ep_id = str(line.get("id") or "")
    topic = E.entry_of(store, ep_id)
    if topic is None or str(topic.get("archived_at") or "").strip() or topic.get("project") != row.get("project"):
        return None
    if name and not E.name_of(topic):
        E._rewrite_entry(store, ep_id, {"topic": name})
    E.resolve_command(store, row["id"], ep_id=ep_id, how="chosen", at=at)
    return ep_id


def _result(store: ViewStore, row: dict[str, str], lines: list[dict[str, Any]], again: bool = False) -> dict[str, Any]:
    chosen = as_int(row.get("chosen"))
    line = lines[chosen - 1] if 1 <= chosen <= len(lines) else {}
    view = E.command_view(store, row["id"])
    topic = E.entry_of(store, str(view.get("id") or "")) or {}
    said = ""
    if line.get("kind") == "new":
        said = f"Say in one line that the new topic «{view['name']}» ({view['id']}) was made. "
    elif row.get("name") and E.name_of(topic) == row.get("name") and not line.get("named"):
        said = f"Say in one line that «{view['name']}» ({view['id']}) was chosen and now has this name. "
    elif row.get("name"):
        said = (f"Say in one line that «{view['name']}» ({view['id']}) was chosen; it keeps its name (the operator "
                f"renames it on the Entry points page). ")
    else:
        said = f"Say in one line that «{view['name']}» ({view['id']}) was chosen. "
    return {**view, "state": "chosen", "chosen": chosen, "existing": again,
            "next": said + str(view.get("next") or "") + " " + after_record(store, view, row)}


def after_record(store: ViewStore, view: dict[str, Any], row: dict[str, str]) -> str:
    """What follows the record, in order: the ways in, one stop, a shot of
    each way that is up, the topic of the tasks this chat named."""
    ep_id = str(view.get("id") or "")
    agent = str(row.get("agent_id") or "")
    by_task = E.topics_by_task(store)
    named = [str(m.get("task_id") or "") for m in store.query(
        "SELECT task_id, max(turn) AS turn FROM task_mentions WHERE agent_id = ? AND project = ? "
        "GROUP BY task_id ORDER BY max(turn) DESC, task_id", (agent, row.get("project") or ""))]
    loose = [t for t in named if t and by_task.get(t) != ep_id][:10]
    tasks = (f"the tasks of this topic named in this chat ({', '.join(loose)}: only those whose work is this "
             f"topic's)" if loose else "each task of this topic named in this chat")
    ways = E.ways_of(store, ep_id) if ep_id else []
    up = [w for w, p in zip(ways, E.check_ports(ways)) if p.get("up")] if ways else []
    names = [f"{w.get('name')} ({w.get('id')})" for w in up]
    known = f" Up now: {', '.join(names)}." if names else ""
    return (f"After the record, in this order: (1) each way in this chat used or made, with entrypoint_way "
            f'{{id: "{ep_id}", way}} (a page, a site, an app, a file, a folder, a script: where it opens, the '
            f"command that starts it, its folder and port); (2) one message of where the work stopped, with "
            f'entrypoint_stop {{id: "{ep_id}", text}}, one or two plain sentences; (3) for each way in that is up '
            f"now (the topic's ports: GET /api/entrypoints/{ep_id}/ports, or open it), a screenshot with "
            f'entrypoint_shot {{id: "{ep_id}", way_id, path, caption}};{known} (4) the topic of {tasks}, with task_topic '
            f'{{id, topic: "{ep_id}"}}. Then say in one line what was written.')


def asks(store: ViewStore, agent_id: str = "") -> list[dict[str, Any]]:
    """Every question, newest first, with its lines; reads only."""
    out = [{**r, "lines": _lines(r)} for r in rows(store) if not agent_id or r.get("agent_id") == agent_id]
    out.sort(key=lambda r: str(r.get("offered_at") or ""), reverse=True)
    return out
