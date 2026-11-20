"""Pins, carried messages and forks for later — marks on one message.

Three things the operator says about a message, each beside the ★ and none
of them a star (marklib.py keeps all of them in marks.csv, adopts their tags
the way it adopts ``#important``'s, and an unmark stamps ``removed_at``):

- ``#pin`` (kind ``pin``): I will come back to this message.
- ``#carry`` / ``#carry-brief`` (kinds ``carry``, ``carry-brief``): what
  survives a context compaction. After one, the capture hook gives the
  chat's carried messages back to the agent — a ``#carry`` message whole
  with the reply that followed it, a ``#carry-brief`` one as the brief the
  agent wrote for it (``carry_briefs.csv``, through the MCP tool
  ``carry_brief``). One message has one level: setting one takes the other
  off. Each time the hook gives them back it writes a line to
  ``carried.jsonl`` beside the chat (hookshared.py holds the rules the hook
  and this module share).
- ``#fork-later`` (kind ``fork``): work another agent could take later, in
  parallel. Listed with the command that starts it — the chat's session
  resumed into a new one with the message as its first prompt — and a state
  the operator sets: waiting, started, dropped. The server never starts
  anything; it only gives the command.

A message is ``<agent_id>#<turn>`` (the operator's) or
``<agent_id>#<turn>/reply`` (the agent's reply in that turn).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import hookshared, limits, marklib, termlib
from .actors import is_agent
from .csvio import append_row
from .date_utils import now_iso
from .db import ViewStore
from .viewrows import agents_by_id

#: The lists, by the name a route and the MCP tool use, and the mark kinds in each.
LISTS: dict[str, tuple[str, ...]] = {
    "pin": ("pin",),
    "carry": hookshared.CARRY_KINDS,
    "fork": ("fork",),
}
BRIEF_COLUMNS: tuple[str, ...] = ("id", "target", "project", "agent_id", "text", "written_at", "written_by")
#: How much of a message a list shows when it is not asked for whole.
PREVIEW = 800
_FORK_TAG_RE = re.compile(r"(?<![\w#])#fork-later(?![\w-])", re.IGNORECASE)


def _chat_folder(agent: dict[str, Any]) -> Path | None:
    path = Path(str(agent.get("_chat_path") or ""))
    return path.parent if str(path) not in ("", ".") else None


class _Chats:
    """The chats the marks point at, each read once per listing."""

    def __init__(self, store: ViewStore) -> None:
        self.raw = {str(a.get("agent_id") or ""): a for a in store.agents()}
        self.public = agents_by_id(store)
        self._turns: dict[str, dict[int, tuple[str, str, str]]] = {}

    def turns(self, agent_id: str) -> dict[int, tuple[str, str, str]]:
        if agent_id not in self._turns:
            a = self.raw.get(agent_id) or {}
            path = str(a.get("_chat_path") or "")
            self._turns[agent_id] = {n: (at, u, r) for n, at, u, r in hookshared.chat_turns(path)} if path else {}
        return self._turns[agent_id]

    def deliveries(self, agent_id: str) -> list[dict[str, Any]]:
        folder = _chat_folder(self.raw.get(agent_id) or {})
        return hookshared.carried_deliveries(folder) if folder else []


def message_text(chats: _Chats, agent_id: str, turn: int, side: str) -> tuple[str, str, str]:
    """(the message, the reply after it, when) of a message's turn."""
    at, user, reply = chats.turns(agent_id).get(turn, ("", "", ""))
    return (reply, "", at) if side == hookshared.REPLY_SIDE else (user, reply, at)


#: The words around a reply a branch starts from, in the operator's language.
#: Neutral on purpose: the branch picks up from the reply and waits — it is
#: not told to carry the reply out (a reply that says what it did would be
#: done again, on the parent's records). ``#mute`` makes every tag in the
#: message plain text, the quoted ones included (hookshared.command_text):
#: the hook and the server read none of them as the operator's command.
FORK_WORDS: dict[str, tuple[str, str]] = {
    "en": ("We continue from this message (turn {turn}):", "I will say what comes next. #mute"),
    "ru": ("Продолжаем с этого сообщения (ход {turn}):", "Что дальше — скажу. #mute"),
}
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
#: Anything a command reader could take for a tag (they all read ``(?<![\w#])#word``).
_TAG_RE = re.compile(r"(?<![\w#])#(?=[A-Za-z])")
#: How many of the chat's last operator messages tell its language.
_LANG_TURNS = 5


def fork_lang(store: ViewStore, said: list[str]) -> str:
    """The operator's language for a branch's first message: ru when their
    last messages in the chat have Cyrillic in them, else the app's language
    setting (en when none is saved). The app's setting alone is not enough:
    an operator may keep the app in English and write Russian."""
    if any(_CYRILLIC.search(t or "") for t in said[-_LANG_TURNS:]):
        return "ru"
    from .entrypointask import lang_of  # the app's setting, read in one place
    got = lang_of(store, "")
    return got if got in FORK_WORDS else "en"


def fork_prompt(text: str, turn: int, side: str, lang: str = "en") -> str:
    """The first prompt of a fork. From the agent's reply: the reply quoted
    between a neutral line on where the chat goes on and a line that the
    operator says what comes next, with ``#mute``. From the operator's own
    message: the message without its ``#fork-later``; with ``#mute`` added
    when a tag in it would run again (it ran in the parent already)."""
    if side == hookshared.REPLY_SIDE:
        head, tail = FORK_WORDS.get(lang) or FORK_WORDS["en"]
        quote = "\n".join(f"> {line}" if line.strip() else ">" for line in text.strip().splitlines())
        return f"{head.format(turn=turn)}\n\n{quote}\n\n{tail}"
    said = _FORK_TAG_RE.sub("", text).strip()
    if _TAG_RE.search(said):
        said += "\n\n#mute"
    return said


def listing(store: ViewStore, which: str, *, project: str = "", agent_id: str = "", q: str = "",
            full: bool = False) -> dict[str, Any]:
    """The marks of one list in force, newest first, each with its message.

    ``full``: the message whole (the MCP tool), else its first PREVIEW
    characters. ``q`` keeps the ones whose message, brief, excerpt or chat
    name holds it. A carried list also answers when each chat's carried
    messages were given back (``deliveries``)."""
    kinds = LISTS[which]
    chats = _Chats(store)
    briefs = hookshared.briefs_of(store.data_root)
    needle = q.strip().lower()
    items: list[dict[str, Any]] = []
    for r in marklib.active(store, project):
        if r.get("kind") not in kinds:
            continue
        parsed = hookshared.parse_target(r.get("target") or "")
        if parsed is None:
            continue
        agent, turn, side = parsed
        if agent_id and agent != agent_id:
            continue
        text, reply, at = message_text(chats, agent, turn, side)
        item: dict[str, Any] = {
            **r, "turn": turn, "side": side, "agent_id": agent, "at": at,
            "agent": chats.public.get(agent),
            "chars": len(text),
            "text": text if full or len(text) <= PREVIEW else text[:PREVIEW].rstrip() + "…",
        }
        if r["kind"] in hookshared.CARRY_KINDS:
            b = briefs.get(r["target"])
            item["brief"] = str(b.get("text") or "") if b else ""
            item["brief_at"] = str(b.get("written_at") or "") if b else ""
            item["brief_by"] = str(b.get("written_by") or "") if b else ""
            if r["kind"] == "carry" and side != hookshared.REPLY_SIDE:
                item["reply"] = reply[:limits.CARRY_REPLY_CAP] if full else reply[:PREVIEW]
        if r["kind"] == "fork":
            a = chats.raw.get(agent) or {}
            item["tool"] = str(a.get("tool") or "")
            lang = fork_lang(store, [u for _n, (_at, u, _r) in sorted(chats.turns(agent).items())])
            item["command"] = termlib.fork_command(
                str(a.get("tool") or ""), str(a.get("session_ref") or ""), str(a.get("cwd") or ""),
                fork_prompt(text, turn, side, lang))
        if needle:
            name = (item["agent"] or {}).get("agent_name") or ""
            hay = " ".join((text, item.get("brief") or "", r.get("excerpt") or "", name, agent)).lower()
            if needle not in hay:
                continue
        items.append(item)
    out: dict[str, Any] = {"total": len(items), "items": items}
    if which == "carry":
        deliveries: list[dict[str, Any]] = []
        for agent in sorted({i["agent_id"] for i in items} | ({agent_id} if agent_id else set())):
            for d in chats.deliveries(agent):
                deliveries.append({**d, "agent_id": agent})
        deliveries.sort(key=lambda d: str(d.get("at") or ""), reverse=True)
        out["deliveries"] = deliveries
        for i in items:
            given = [d for d in deliveries if d["agent_id"] == i["agent_id"]
                     and i["target"] in (d.get("given") or [])]
            left = [d for d in deliveries if d["agent_id"] == i["agent_id"]
                    and i["target"] in (d.get("left_out") or [])]
            i["given_at"] = str(given[0].get("at") or "") if given else ""
            i["left_out_at"] = str(left[0].get("at") or "") if left else ""
    return out


def mark(store: ViewStore, kind: str, agent_id: str, turn: int, side: str, fields: dict[str, Any]) -> dict[str, str]:
    """Mark a message by hand. A carry level takes the other one off."""
    if kind not in marklib.MESSAGE_KINDS:
        raise ValueError(f"kind must be one of {', '.join(marklib.MESSAGE_KINDS)}")
    if not agent_id or turn <= 0:
        raise ValueError("a message is its chat's agent and a turn number")
    target = marklib.message_target(agent_id, turn, side)
    if kind in hookshared.CARRY_KINDS:
        for other in hookshared.CARRY_KINDS:
            if other != kind:
                marklib.unmark(store, other, target)
    return marklib.mark(store, kind, target, {**fields, "agent_id": agent_id, "turn": turn})


def unmark(store: ViewStore, kinds: tuple[str, ...], target: str) -> int:
    return sum(marklib.unmark(store, k, target) for k in kinds)


def write_brief(store: ViewStore, target: str, text: str, by: str) -> dict[str, str]:
    """The brief of a #carry-brief message: what is given back for it after
    a compaction. Each write is kept; the newest counts."""
    body = (text or "").strip()
    if not body:
        raise ValueError("a brief cannot be empty")
    if len(body) > limits.MAX_CARRY_BRIEF:
        raise ValueError(f"a brief is at most {limits.MAX_CARRY_BRIEF} characters: the message it stands for "
                         "is given back whole with #carry")
    parsed = hookshared.parse_target(target)
    if parsed is None:
        raise ValueError("a message is <agent_id>#<turn>, or <agent_id>#<turn>/reply for the agent's reply")
    if is_agent(by) and parsed[0] != by:
        # A chat's brief is its own agent's: the hook asks a chat only for its
        # own messages. A branch (claude --fork-session, codex fork) holds its
        # parent's turns in its history and once rewrote the parent's brief.
        raise PermissionError(
            f"{target} is a message of another chat ({parsed[0]}); you are {by}. An agent writes briefs only "
            f"for its own chat's messages ({by}#<turn>): a branch carries its parent's history, not its "
            "records. The parent's brief is written in the parent chat, after the operator marks it there.")
    on = lambda: any(r.get("kind") == "carry-brief" and r.get("target") == target  # noqa: E731
                     for r in marklib.active(store))
    if not on():
        # The tag may be in a turn the view has not read yet.
        store.rebuild()
        marklib.adopt(store)
    if not on():
        raise LookupError(f"{target} is not marked #carry-brief: the operator marks it (the tag, or the "
                          "carry button on the chat page) before its brief is written")
    agent = parsed[0]
    project = next((str(a.get("project") or "") for a in store.agents() if a.get("agent_id") == agent), "")
    now = now_iso()
    row = {"id": marklib._id("brief", target, by, now), "target": target, "project": project,
           "agent_id": agent, "text": body, "written_at": now, "written_by": by}
    append_row(store.data_root / hookshared.BRIEFS_CSV, BRIEF_COLUMNS, row)
    return row
