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

   The last line is always the new topic, with the agent's name. The
   numbered lines are recorded in ``entrypoint_asks.csv`` with the chat's
   last turn, and the server writes ``show``, the offer the agent gives as
   it is (show_of): a heading, each topic with its What, ways in, where it
   stopped, its last chat and open tasks and what choosing it does, the new
   topic, and how to answer with the real numbers; in the operator's
   language (lang_of). With no candidate it is one line: start the topic
   «name»? Asked again before the operator answered, the question is
   replaced; after an answer that was not read yet, it is refused.
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
   chat; a name written beside its number becomes its name (a named one is
   renamed, the old name kept in entrypoint_names.csv). The new-topic line chosen
   makes the topic then, from the command's message (its kept text, turn
   and chat), with the name given or the one proposed. A retry answers the
   same; the topic's id is the command's, so it is never made twice.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from . import entrypointlib as E
from . import keeplib
from .actors import is_agent
from .csvio import append_row, as_int, read_rows, rewrite_rows
from .date_utils import as_local, iso_moment, now_iso
from .db import ViewStore
from .entities import ENTRYPOINT_ASK_COLUMNS, is_done
from .file_safety import safe_read_json
from .hookshared import command_text, plain_text
from .nextlib import _COMMAND_RE, _NUMBER_RE, _answer_turn, _said, _turns
from .sessions import helper_ids

ASKS_FILE = "entrypoint_asks.csv"
CANDIDATES_MAX = 3
OPEN = ("offered",)

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


def _worked_on(store: ViewStore, agent: str) -> list[str]:
    """The topics this chat wrote on, newest first."""
    seen: dict[str, str] = {}

    def add(ep_id: str, at: str) -> None:
        at = _moment(at)
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
        out.append({"id": ep_id, "name": E.label_of(store, row), "named": bool(E.name_of(row)),
                    "why": why, "stop": " ".join(str(stops[0].get("text") or "").split()) if stops else "",
                    "stop_at": str(stops[0].get("at") or "") if stops else ""})
    return out


# ---------------------------------------------------------------------------
# The offer the operator reads
# ---------------------------------------------------------------------------

# Every word of the offer, in both languages, in one place. The offer is in
# the operator's language: the command message's (Cyrillic is Russian), else
# the app's language setting.
TEXTS: dict[str, dict[str, Any]] = {
    "en": {
        "heading": "Where should this entry point go?",
        "no_name": "No name",
        "states": {"active": "active", "paused": "paused", "dead": "closed"},
        "project": "project {project}",
        "what": "What: {what}",
        "no_record": "What: no record yet",
        "ways": "Ways in: {ways}",
        "no_ways": "Ways in: none yet",
        "stop": "Where it stopped ({day}, {who}): {text}",
        "no_stop": "Where it stopped: no messages yet",
        "you": "you",
        "chat": "Last chat: «{chat}», {day}",
        "no_chat": "Last chat: none yet",
        "tasks": "open tasks: {n}",
        "choose_topic": "→ I add a new version of its record",
        "new": "New topic «{name}»",
        "choose_new": "→ I start a separate topic",
        "footer": ("Answer with a number. You can give a name with it: «{first} Name» — topic {first} takes this "
                   "name (or a new one, if it has one already); «{new} Your name» — the new topic is called that."),
        "single": "Start the topic «{name}»? Answer «yes» or give your own name.",
        "months": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    },
    "ru": {
        "heading": "Куда записать эту точку входа?",
        "no_name": "Без названия",
        "states": {"active": "в работе", "paused": "на паузе", "dead": "закрыта"},
        "project": "проект {project}",
        "what": "Что: {what}",
        "no_record": "Что: записи пока нет",
        "ways": "Входы: {ways}",
        "no_ways": "Входы: пока нет",
        "stop": "Где остановились ({day}, {who}): {text}",
        "no_stop": "Где остановились: сообщений пока нет",
        "you": "ты",
        "chat": "Последний чат: «{chat}», {day}",
        "no_chat": "Последний чат: пока нет",
        "tasks": "открытых задач: {n}",
        "choose_topic": "→ допишу новую версию её записи",
        "new": "Новая тема «{name}»",
        "choose_new": "→ заведу отдельную тему",
        "footer": ("Ответь номером. Можно сразу дать название: «{first} Название» — тема {first} получит это "
                   "название (или новое, если оно уже есть); «{new} Своё название» — новая тема будет называться "
                   "так."),
        "single": "Завести тему «{name}»? Ответь «да» или дай своё название.",
        "months": ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    },
}
LANG_PREF = "sp-lang"
PREFS_FILE = "ui_prefs.json"
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def lang_of(store: ViewStore, text: str) -> str:
    """ru when the operator's message has Cyrillic in it; else the app's
    language setting (en when none is saved)."""
    if _CYRILLIC.search(text or ""):
        return "ru"
    try:
        prefs = safe_read_json(store.data_root / PREFS_FILE)
    except (OSError, ValueError):
        prefs = None
    got = str(prefs.get(LANG_PREF) or "") if isinstance(prefs, dict) else ""
    return got if got in TEXTS else "en"


_SHORT = re.compile(r"^(\d{4}-\d{2}) (\d{2}:\d{2})")


def _moment(at: str) -> str:
    """A ledger's stamp as local ISO to the second: ``2026-11-16T10:56:00``
    from ISO (a zone converted) or from a version's ``2611-16 10:56``."""
    at = str(at or "").strip()
    m = _SHORT.match(at)
    if m:
        return iso_moment(m.group(1), m.group(2))
    d = as_local(at)
    return d.strftime("%Y-%m-%dT%H:%M:%S") if d else ""


def _day(at: str, lang: str) -> str:
    d = as_local(_moment(at))
    return f"{d.day} {TEXTS[lang]['months'][d.month - 1]}" if d else ""


def _last_chat(store: ViewStore, row: dict[str, str]) -> tuple[str, str]:
    """The chat that worked on the topic last, and when: its commands, the
    versions it wrote, its stops, ways in and shots, the chat that kept it."""
    ep_id = str(row["id"])
    best = ("", "")

    def add(agent: str, at: str) -> None:
        nonlocal best
        at = _moment(at)
        if agent and is_agent(agent) and at and at > best[1]:
            best = (agent, at)
    add(str(row.get("agent_id") or ""), iso_moment(row.get("created_date"), row.get("created_time")))
    for c in E.commands(store):
        if c.get("entrypoint_id") == ep_id and c.get("how") != "dropped":
            add(str(c.get("agent_id") or ""), str(c.get("chosen_at") or c.get("at") or ""))
    for r in read_rows(store.data_root / E.AUTHORS_FILE):
        if r.get("entrypoint_id") == ep_id:
            add(str(r.get("agent_id") or ""), str(r.get("at") or ""))
    for s in E.stops_of(store, ep_id):
        add(str(s.get("author") or ""), str(s.get("at") or ""))
    for w in E.ways_of(store, ep_id):
        add(str(w.get("actor") or ""), str(w.get("updated_at") or w.get("created_at") or ""))
    for s in E.shots_of(store, ep_id):
        add(str(s.get("agent_id") or ""), str(s.get("at") or ""))
    return best


def _chat_names(store: ViewStore) -> dict[str, str]:
    return {str(a.get("agent_id") or ""): E._chat_name(a, str(a.get("agent_id") or "")) for a in store.agents()}


def _topic_block(store: ViewStore, item: dict[str, Any], lang: str, project: str,
                 names: dict[str, str]) -> list[str]:
    """One existing topic of the offer: its head, What, ways in, where it
    stopped, its last chat and open tasks, and what choosing it does."""
    tx = TEXTS[lang]
    row = E.entry_of(store, str(item.get("id") or "")) or {"id": str(item.get("id") or "")}
    name = E.name_of(row) or tx["no_name"]
    head = [name, tx["states"].get(E.state_of(row), E.state_of(row))]
    if row.get("project") and row.get("project") != project:
        head.append(tx["project"].format(project=row["project"]))
    out = [f"{item['n']}) " + " · ".join(head)]
    what = E.what_paragraph(E.record_of(store, row))
    out.append(tx["what"].format(what=what) if what else tx["no_record"])
    ways = E.ways_of(store, str(row["id"]))
    shown = [" — ".join(x for x in (str(w.get("name") or ""), str(w.get("url") or w.get("path") or "")) if x)
             for w in ways]
    out.append(tx["ways"].format(ways="; ".join(shown)) if shown else tx["no_ways"])
    stops = E.stops_of(store, str(row["id"]))
    if stops:
        s = stops[0]
        author = str(s.get("author") or "")
        who = tx["you"] if author in ("", "operator") else names.get(author) or author
        out.append(tx["stop"].format(day=_day(str(s.get("at") or ""), lang), who=who,
                                     text=" ".join(str(s.get("text") or "").split())))
    else:
        out.append(tx["no_stop"])
    agent, at = _last_chat(store, row)
    chat = tx["chat"].format(chat=names.get(agent) or agent, day=_day(at, lang)) if agent else tx["no_chat"]
    tasks = E.tasks_of_topic(store, row) if row.get("project") else []
    n_open = sum(1 for t in tasks if not is_done(t.get("status")) and not str(t.get("archived_at") or "").strip())
    out.append(f"{chat} · {tx['tasks'].format(n=n_open)}")
    out.append(tx["choose_topic"])
    return [out[0]] + ["   " + x for x in out[1:]]


def show_of(store: ViewStore, lines: list[dict[str, Any]], lang: str, project: str) -> str:
    """The offer, built by the server so its numbers are the ones recorded."""
    tx = TEXTS[lang]
    new = lines[-1]
    if len(lines) == 1:
        return tx["single"].format(name=new["name"])
    names = _chat_names(store)
    blocks = [tx["heading"]]
    for item in lines[:-1]:
        blocks.append("\n".join(_topic_block(store, item, lang, project, names)))
    blocks.append(f"{new['n']}) {tx['new'].format(name=new['name'])}\n   {tx['choose_new']}")
    blocks.append(tx["footer"].format(first=lines[0]["n"], new=new["n"]))
    return "\n\n".join(blocks)


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
        lang = lang_of(store, f"{(mark or {}).get('title') or ''} {body}")
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
        show = show_of(store, lines, lang, str(cmd.get("project") or ""))
    how = ("yes, or a name" if len(lines) == 1 else "a number, with a name beside it when they give one")
    return {
        "asked": True, "command": cmd_id, "rev": rev, "lines": lines, "show": show, "lang": lang,
        "next": (f"Give the operator the text in `show` exactly as it is, as the end of your reply: every line, "
                 f"in its language, nothing shortened, translated, reordered or retold. Nothing is made until "
                 f"they answer ({how}). Then call entrypoint_answer {{number, name?}}: number the line they "
                 f"chose, 0 when they chose none; name only when they wrote one, as they wrote it."),
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
    """A new version of the chosen topic, for this chat; the name the
    operator wrote beside its number becomes its name, a name it had
    before kept in its history. None when the topic is gone from the
    project."""
    ep_id = str(line.get("id") or "")
    topic = E.entry_of(store, ep_id)
    if topic is None or str(topic.get("archived_at") or "").strip() or topic.get("project") != row.get("project"):
        return None
    if name and name != E.name_of(topic):
        E.rename(store, ep_id, name, who=str(row.get("agent_id") or ""), at=at, command_id=row["id"])
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
    elif row.get("name") and E.name_of(topic) == row.get("name") and line.get("named"):
        said = (f"Say in one line that «{view['name']}» ({view['id']}) was chosen and renamed, as the operator "
                f"wrote (it was «{line.get('name')}»). ")
    elif row.get("name") and E.name_of(topic) == row.get("name"):
        said = f"Say in one line that «{view['name']}» ({view['id']}) was chosen and now has this name. "
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
