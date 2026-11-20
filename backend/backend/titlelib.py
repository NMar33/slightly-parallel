"""A task made from a message — its title waits for the chat's agent.

The terminal's message menu makes a task from one message of a chat (the
operator's, or the agent's reply), as the operator, in To do. Its first line
is a poor title — an agent's reply opens with "Понял: …" or "Done." — so the
server gives a provisional one (``provisional_title``) and keeps a flag: the
title waits for that chat's agent (``task_titles.csv``, hookshared.py names
it). On the chat's next turn the capture hook tells the agent once
(``#task-title``), and the agent sets the title with ``task_update {id,
title}``.

The rule (routers/tasks_extra.py asks ``agent_refusal``): while the flag
waits, the source chat's agent may set the title once, and the flag clears;
any other agent is refused. The operator renaming the task first clears it
too, and the agent's later attempt is refused, saying so. A task never made
from a message has no row here and keeps the usual rules. A chat that never
takes another turn leaves the provisional title in place.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import hookshared
from .csvio import append_row
from .date_utils import now_iso
from .nowlib import _ANY_TAG_RE, _cut

#: The create request's field that asks for this (POST /api/tasks), and its value.
TITLE_FROM_FIELD, TITLE_FROM_MESSAGE = "title_from", "message"
#: The message the task was made from: ``<agent_id>#<turn>`` or ``…/reply``.
TITLE_SOURCE_FIELD = "title_source"

# A line that only opens a reply: "Понял", "Готово.", "Ok, …", "Got it —".
# Matched at the start of a line, the word whole, then the end or a mark.
_OPENERS = (
    "понял", "поняла", "понятно", "принял", "принято", "готово", "ок", "окей", "ok", "okay",
    "сделал", "сделала", "сделано", "хорошо", "да", "отлично", "ясно", "конечно", "ладно",
    "согласен", "верно", "супер",
    "got it", "done", "sure", "understood", "yes", "alright", "all right", "great", "noted",
    "fine", "perfect",
)
_OPENER_RE = re.compile(
    r"^(?:" + "|".join(sorted((re.escape(o) for o in _OPENERS), key=len, reverse=True)) + r")"
    r"(?![\w])[\s,.:;!—–-]*", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LINE_MARK_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+•]\s+|\d{1,3}[.)]\s+|\[[ xX]\]\s+)+")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_EMPH_RE = re.compile(r"(\*\*|__|\*|`+|~~)")
_TABLE_RULE_RE = re.compile(r"^[\s|:\-+]+$")
_LETTER_RE = re.compile(r"[^\W\d_]")


def _plain(line: str) -> str:
    """One line without its markdown: the heading and list marks, links
    (their text kept), emphasis and code marks, table pipes, tags."""
    s = _LINE_MARK_RE.sub("", line)
    s = _LINK_RE.sub(r"\1", s)
    s = _EMPH_RE.sub("", s)
    s = s.replace("|", " ")
    s = _ANY_TAG_RE.sub(" ", s)
    return " ".join(s.split())


def provisional_title(message: str) -> str:
    """The server's title for a task made from a message: its first
    meaningful line — service openers ("Понял", "Готово", "Ok", "Got it" …)
    skipped, as are empty lines, code blocks and table rules — without
    markdown, cut at a word to 80 characters. A message of openers only
    gives its first line with more than the opener ("Сделал всё"), else its
    first line; an empty one, ''."""
    lines: list[str] = []
    in_code = False
    for raw in (message or "").splitlines():
        if _FENCE_RE.match(raw):
            in_code = not in_code
            continue
        if in_code or _TABLE_RULE_RE.match(raw):
            continue
        s = _plain(raw)
        if _LETTER_RE.search(s):
            lines.append(s)
    for s in lines:
        if not _OPENER_RE.match(s):
            return _cut(s)
    for s in lines:
        if _LETTER_RE.search(_OPENER_RE.sub("", s, count=1)):
            return _cut(s)
    return _cut(lines[0]) if lines else ""


def _row(task_id: str, project: str, agent: str, turn: int, side: str, provisional: str,
         state: str, by: str) -> dict[str, str]:
    at = now_iso()
    return {"id": f"tt_{task_id[3:]}_{state}", "task_id": task_id, "project": project, "agent_id": agent,
            "turn": str(turn), "side": side, "provisional": provisional, "state": state, "at": at, "by": by}


def state_of(data_root: Path, task_id: str) -> dict[str, str] | None:
    """The newest ledger row of one task, or None for a task not made from a message."""
    return hookshared.title_states(data_root).get(task_id)


def open_wait(data_root: Path, task_id: str, project: str, source: str, provisional: str) -> None:
    """The flag: this task's title waits for the agent of the chat ``source`` is in."""
    parsed = hookshared.parse_target(source)
    if parsed is None:
        return
    agent, turn, side = parsed
    append_row(Path(data_root) / hookshared.TITLES_CSV, hookshared.TITLE_COLUMNS,
               _row(task_id, project, agent, turn, side, provisional, hookshared.TITLE_WAITING, "operator"))


def close_wait(data_root: Path, row: dict[str, str], state: str, by: str) -> None:
    """The flag cleared: the agent gave the title, or the operator renamed the task first."""
    append_row(Path(data_root) / hookshared.TITLES_CSV, hookshared.TITLE_COLUMNS,
               _row(str(row.get("task_id") or ""), str(row.get("project") or ""), str(row.get("agent_id") or ""),
                    int(row.get("turn") or 0), str(row.get("side") or ""), str(row.get("provisional") or ""),
                    state, by))


def agent_refusal(row: dict[str, str], actor: str, task_id: str) -> tuple[str, str] | None:
    """Why this agent may not set the title of a task made from a message
    (reason, what to do instead); None when it may — the source chat's
    agent, once, while the title waits."""
    source = hookshared.mark_target(row.get("agent_id") or "", row.get("turn") or 0, row.get("side") or "")
    state = row.get("state") or ""
    if state == hookshared.TITLE_WAITING:
        if (row.get("agent_id") or "") == actor:
            return None
        return (f"the title of {task_id} waits for the agent of the chat it was made from ({source})",
                "another agent does not set it; add your words with task_update {id, comment} if needed.")
    if state == hookshared.TITLE_BY_OPERATOR:
        return (f"the operator renamed {task_id} before its title was given: the title is theirs now",
                "leave it as it is.")
    return (f"the title of {task_id} was given once already, by {row.get('by') or 'its chat'}; "
            "it is the operator's now", "leave it as it is.")
