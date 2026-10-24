"""Sessions — work blocks derived from per-turn chat logs.

Nothing writes sessions. The turn logger's ``chat.md`` files are the ground
truth (one timestamped header per turn); this module groups consecutive
turns into sessions wherever the pause between turns stays under the
operator's ``sessions.gap_minutes`` setting. Every number on the dashboard
that involves time (hours, heatmaps, "quiet for N days") comes from here —
real wall clock, no agent-claimed durations.

Four times per session (turntimes.py knows when each answer ended, and
when the agent and its helpers were active):
- ``duration_min`` — the session: first prompt → the last answer's end, or
  the last helper's, whichever is later;
- ``agent_min`` — the chat busy for the person: the agent or any of its
  helpers active (three helpers in one hour are one hour);
- ``helper_min`` — the helpers' own time, added up: the work they did;
- ``waiting_min`` — the agent waiting on the person: each answer's end to
  the next prompt, less any stretch a helper was still working.
What is left of the session (a laptop asleep mid-turn) is none of these.
``timed`` says ``exact`` when every turn's end is known, ``approx`` when a
turn had to be estimated (an old chat with no transcript).

``POST /api/activity`` remains as an escape hatch for external pipelines
that cannot run the turn logger; consumers union both sources.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .hookshared import NOT_OPERATOR, command_text, plain_text, yymm_dd as _yymm_dd

_TURN_RE = re.compile(r"^## Turn (\d+) · (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
# Quoted structure inside captured content is escaped at write time.
_ESCAPED_RE = re.compile(r"^\\(## Turn \d+ · |\*\*User\*\*: ?|\*\*Agent\*\*: ?)")
_USER_RE = re.compile(r"^\*\*User\*\*: ?(.*)")
_AGENT_RE = re.compile(r"^\*\*Agent\*\*: ?(.*)")


@dataclass
class Turn:
    number: int
    at: datetime
    line: int              # 1-based line of the header in chat.md
    user_summary: str = ""
    agent_summary: str = ""
    end: datetime | None = None      # when the answer ended (turntimes.py)
    active_sec: int | None = None    # the agent's working seconds in it
    # When the agent or a helper was active, since the previous answer; and
    # the helpers' own seconds in that window.
    busy: list[tuple[datetime, datetime]] | None = None
    helper_sec: int = 0


@dataclass
class Session:
    id: str
    project: str
    agent_id: str
    created_date: str      # YYMM-DD of the first turn
    start_time: str        # HH:MM
    end_time: str          # HH:MM of the last turn
    duration_min: int      # wall clock, first prompt → last answer's end (≥1)
    turns_n: int
    l1: str                # composed headline
    turns: list[dict]      # [{n, at, user, agent}] — the chat history
    chat_start_line: int
    chat_end_line: int     # last line of the block (inclusive)
    # Task ids seen in this block's turns — derived here because the turns
    # are already parsed; the store turns them into the task_mentions table.
    mentions: list[dict] = field(default_factory=list)
    # Prompt library, from the same parse: turns the operator tagged
    # ``#prompt``, and a fingerprint of every user turn so the library can
    # count where a saved prompt was used again.
    prompt_marks: list[dict] = field(default_factory=list)
    turn_prints: list[dict] = field(default_factory=list)
    # Turns tagged #vision, #rule, #problem or #skill — kept by keeplib.py.
    keep_marks: list[dict] = field(default_factory=list)
    # Turns tagged #important[-agent|-task|-message] — marked by marklib.py.
    important_tags: list[dict] = field(default_factory=list)
    # Turns tagged #done — the operator closing a task; donelib.py applies them.
    done_tags: list[dict] = field(default_factory=list)
    # Turns carrying #now — the task the chat starts on; nowlib.py writes the
    # card when the agent did not.
    now_tags: list[dict] = field(default_factory=list)
    # The agent's working minutes, the minutes it waited on the person, and
    # whether every turn's end was known ("exact") or one was estimated.
    agent_min: int = 0
    waiting_min: int = 0
    helper_min: int = 0
    timed: str = "exact"


# Minted ids are tk_ + 8 hex, but imported or hand-written boards may use
# readable ids (tk_bc_replica); accept both — consumers keep only ids that
# exist as tasks, so a stray token in prose is not a mention. Storyboard
# docs (dc_…) are found the same way, so a doc's history shows who worked
# on it.
# A reference may carry the task's turn — tk_28b1b490.2 — so a chat turn
# can be tied to the round of instruction that asked for it. The id is
# group 1, the turn (when written) group 2.
_TASK_ID_RE = re.compile(r"\b((?:tk|dc)_[a-z0-9][a-z0-9_-]{2,40})(?:\.(\d{1,3}))?\b")


def _mentions_of(session_id: str, project: str, agent_id: str, block: list[Turn]) -> list[dict]:
    out: list[dict] = []
    for t in block:
        for role, text in (("user", t.user_summary), ("agent", t.agent_summary)):
            if not text or ("tk_" not in text and "dc_" not in text):
                continue
            # One mention per task per chat turn, as before; the task turn
            # is taken from the first reference that names one.
            found: dict[str, int] = {}
            for m in _TASK_ID_RE.finditer(text):
                tid, ref_turn = m.group(1), int(m.group(2) or 0)
                if tid not in found or (found[tid] == 0 and ref_turn):
                    found[tid] = ref_turn
            for tid, task_turn in found.items():
                # A short window around the first occurrence — enough to see
                # what was said about it without shipping the whole turn.
                i = text.find(tid)
                excerpt = text[max(0, i - 80): i + 120].replace("\n", " ").strip()
                out.append({
                    "task_id": tid, "project": project, "agent_id": agent_id,
                    "session_id": session_id, "turn": t.number,
                    "task_turn": task_turn,
                    "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"), "role": role,
                    "excerpt": excerpt,
                })
    return out


# ---------------------------------------------------------------------------
# The prompt library, harvested from what the operator already typed
# ---------------------------------------------------------------------------

# ``#prompt`` anywhere in a user message saves that message to the library;
# ``#prompt(a name)`` names it. Written by a person mid-sentence, so it must
# not fire on ``##prompt``, ``#prompting`` or a URL fragment.
PROMPT_TAG_RE = re.compile(
    r"(?<![\w#])#prompt(?:\(([^)\n]{1,80})\))?(?![\w-])", re.IGNORECASE
)

# Everything an operator's evidence prompt or a task header staples onto a
# message. A prompt tagged inside one of those is still the prompt, not the
# boilerplate around it.
_BOILERPLATE_RE = re.compile(
    r"^Evidence required — collect it as you work.*", re.MULTILINE | re.DOTALL
)


# The other things an operator keeps by tagging a message. Same rules as
# #prompt, plus one: ``#problem solved <id>`` asks the agent to close a
# problem, so it is a command and not a new problem.
KEEP_KINDS = ("vision", "rule", "problem", "entrypoint", "skill", "artifact")
KEEP_TAG_RE = re.compile(
    r"(?<![\w#])#(vision|rule|problem|entrypoint|skill|artifact)(?:\(([^)\n]{1,80})\))?(?![\w-])(?!\s+solved\b)",
    re.IGNORECASE,
)


# ``#important`` marks the message, its agent and a task it names;
# ``#important-agent`` / ``-task`` / ``-message`` mark one of them.
IMPORTANT_TAG_RE = re.compile(
    r"(?<![\w#])#important(?:-(agent|task|message))?(?![\w-])", re.IGNORECASE
)
# ``#done`` closes a task: the one it names, else the last task named since
# the previous #done in the chat (donelib.py).
DONE_TAG_RE = re.compile(r"(?<![\w#])#done(?![\w-])", re.IGNORECASE)
# ``#task`` writes a card for later, ``#now`` one the chat starts on; either
# may name the board lane in braces: ``#now {ui} fix the login timeout``.
# ``#now-todo`` (``-next``, ``-backlog``, ``-review``, ``-parked``, ``-done``,
# ``-doing``) files the operator's message straight into that column.
# The hook (scripts/hooks/capture.py) holds the same pattern; the parity
# test keeps the two equal.
TASK_CMD_RE = re.compile(r"(?<![\w#])#(task|now(?:-(?:to-?do|next|backlog|doing|review|parked|done))?)(?![\w-])(?:[ \t]*\{([^}\n]{1,80})\})?", re.IGNORECASE)


# The column each #now names: plain #now is the task the chat starts on.
NOW_COLUMNS = {"": "doing", "doing": "doing", "todo": "todo", "to-do": "todo", "next": "next",
               "backlog": "backlog", "review": "review", "parked": "parked", "done": "done"}


def task_command(text: str) -> tuple[str, str, str]:
    """(command, lane, column) of the last #task or #now in an operator's
    message: ("task", "ui", "agent"), ("now", "", "doing"), ("now", "", "todo")
    for #now-todo … or ("", "", "") with neither."""
    hits = list(TASK_CMD_RE.finditer(text or ""))
    if not hits:
        return "", "", ""
    m = hits[-1]
    command, _, suffix = m.group(1).lower().partition("-")
    column = NOW_COLUMNS[suffix] if command == "now" else "agent"
    return command, " ".join((m.group(2) or "").split()), column


def normalise(text: str) -> str:
    """The form two messages are compared in: case, whitespace and tag out.

    Reuse is counted by equality on this, never by similarity. A prompt
    pasted again is byte-identical once whitespace is collapsed; anything
    looser would report reuse that did not happen, which is worse than
    reporting none.
    """
    stripped = PROMPT_TAG_RE.sub(" ", text or "")
    stripped = _BOILERPLATE_RE.sub("", stripped)
    return " ".join(stripped.lower().split())


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:16]


def prompt_body(text: str) -> str:
    """The message with the tag taken out, kept otherwise verbatim."""
    body = PROMPT_TAG_RE.sub("", text or "")
    body = _BOILERPLATE_RE.sub("", body)
    return body.strip()


def keep_body(text: str) -> str:
    """The message with every tag taken out, kept otherwise verbatim."""
    body = KEEP_TAG_RE.sub("", text or "")
    body = PROMPT_TAG_RE.sub("", body)
    body = _BOILERPLATE_RE.sub("", body)
    return body.strip()


def prompt_title(named: str, body: str) -> str:
    """The name in the tag, else the first real line, clipped."""
    if named.strip():
        return named.strip()[:120]
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return _clip(line, 90)
    return "untitled prompt"


# A prompt is almost never re-sent byte for byte. Over 563 captured turns
# only 7 of the 187 substantial ones have an exact twin — but one prompt was
# sent eight times with a single opening line swapped each time. Equality
# would report that prompt as used once, which is worse than useless: it is
# the page confidently wrong about the thing it exists to measure. So a
# second, looser signature rides along.
SHINGLE = 5
MIN_SHINGLES = 8          # below this a text is too short to judge by overlap
MAX_SHINGLES = 600        # a 5,800-word paste must not cost 5,800 comparisons


def shingles(text: str) -> frozenset[int]:
    """Hashed word 5-grams — the set two near-identical messages share.

    Word n-grams rather than characters: an edited opening sentence changes a
    handful of shingles and leaves the rest, while a genuinely different
    instruction shares almost none.
    """
    words = normalise(text).split()
    if len(words) < SHINGLE + MIN_SHINGLES:
        return frozenset()
    grams = [
        hash(" ".join(words[i:i + SHINGLE]))
        for i in range(len(words) - SHINGLE + 1)
    ]
    if len(grams) > MAX_SHINGLES:
        # Evenly spaced, so the sample still spans the whole text.
        step = len(grams) / MAX_SHINGLES
        grams = [grams[int(i * step)] for i in range(MAX_SHINGLES)]
    return frozenset(grams)


def resemblance(a: frozenset[int], b: frozenset[int]) -> float:
    """Jaccard. 1.0 is the same text; ~0.88 is one line swapped."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Calibrated on 563 real captured turns: at 0.6 the operator's most-repeated
# prompt clusters as the nine sends it actually was, and nothing unrelated
# joins it. Below 0.5 unrelated same-day follow-ups start merging.
SAME_PROMPT = 0.6

# Two texts of wildly different length are not the same prompt with a line
# swapped — they are a prompt and a prompt with an essay stapled to it.
# Skipping those pairs is both faster and the right answer.
LENGTH_BAND = 3.0

# How many shingles of each text go into the inverted index. Enough that two
# near-duplicates are near-certain to collide on one, small enough that a
# long paste does not flood it.
PROBE = 24


def cluster(signatures: list[tuple[str, frozenset[int], int]]) -> dict[str, str]:
    """(key, shingles, words) → key → cluster key. Union-find, no library.

    Comparing every pair is quadratic, and this runs inside a store rebuild
    that fires on every file write — 350 turns cost 164 ms that way, and a
    year of them would cost ten seconds. So an inverted index over a sample
    of each text's shingles proposes the pairs first: two messages that share
    no 5-word run are not 60% the same, and never need the comparison. What
    is left is a few hundred Jaccards instead of sixty thousand.

    The cluster key is the smallest member key, so the mapping is stable
    across rebuilds as long as the same texts are present.
    """
    parent: dict[str, str] = {k: k for k, _, _ in signatures}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # A fixed sample per text, so a 5,800-word paste indexes as cheaply as a
    # 40-word one and still overlaps its own near-duplicates.
    index: dict[int, list[str]] = {}
    sample: dict[str, list[int]] = {}
    by_key = {k: (sh, w) for k, sh, w in signatures}
    for k, sh, _ in signatures:
        picked = sorted(sh)[::max(1, len(sh) // PROBE)][:PROBE]
        sample[k] = picked
        for g in picked:
            index.setdefault(g, []).append(k)

    seen: set[tuple[str, str]] = set()
    for k, sh, w in signatures:
        partners: set[str] = set()
        for g in sample[k]:
            partners.update(index.get(g, ()))
        partners.discard(k)
        for other in partners:
            pair = (k, other) if k < other else (other, k)
            if pair in seen:
                continue
            seen.add(pair)
            osh, ow = by_key[other]
            if max(w, ow) > min(w, ow) * LENGTH_BAND:
                continue
            if resemblance(sh, osh) >= SAME_PROMPT:
                union(k, other)
    return {k: find(k) for k in parent}


#: Turns the tool hands in as "user" that the operator never typed: a
#: helper agent's report ("Another Claude session sent a message …"), a
#: task notification, the tool's own notes. Their #tags describe things;
#: they are no commands. The hook skips them by the same list
#: (hookshared.py); a chat captured before it did still holds them.
_NOT_OPERATOR = NOT_OPERATOR


def _operator_text(t: Turn) -> str:
    """What the operator said in a turn ("" when the turn is the tool's)."""
    text = t.user_summary or ""
    return "" if text.lstrip().startswith(_NOT_OPERATOR) else text


def _prompts_of(
    session_id: str, project: str, agent_id: str, block: list[Turn]
) -> tuple[list[dict], list[dict]]:
    """(tagged turns, a fingerprint of every user turn) for one session."""
    marks: list[dict] = []
    prints: list[dict] = []
    for t in block:
        text = _operator_text(t)
        if not text:
            continue
        prints.append({
            "print": fingerprint(text), "project": project,
            "agent_id": agent_id, "session_id": session_id,
            "turn": t.number, "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
            "words": len(text.split()),
            "head": _clip(text.strip().splitlines()[0] if text.strip() else "", 120),
            "body": text.strip(),
            "shingles": shingles(text),
        })
        m = PROMPT_TAG_RE.search(command_text(text))
        if m is None:
            continue
        body = prompt_body(plain_text(text))
        if not body:
            continue
        marks.append({
            "project": project, "agent_id": agent_id,
            "session_id": session_id, "turn": t.number,
            "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
            "title": prompt_title(m.group(1) or "", body),
            "body": body,
            "print": fingerprint(text),
        })
    return marks, prints


def _keeps_of(
    session_id: str, project: str, agent_id: str, block: list[Turn]
) -> list[dict]:
    """One mark per tagged kind per user turn, named by the first tag that names it."""
    out: list[dict] = []
    for t in block:
        text = _operator_text(t)
        if not text or "#" not in text:
            continue
        named: dict[str, str] = {}
        for m in KEEP_TAG_RE.finditer(command_text(text)):
            kind = m.group(1).lower()
            if not named.get(kind):
                named[kind] = m.group(2) or ""
        if not named:
            continue
        body = keep_body(plain_text(text))
        if not body:
            continue
        for kind, name in named.items():
            out.append({
                "kind": kind, "project": project, "agent_id": agent_id,
                "session_id": session_id, "turn": t.number,
                "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
                "title": prompt_title(name, body),
                "body": body,
            })
    return out


def _importants_of(
    session_id: str, project: str, agent_id: str, block: list[Turn]
) -> list[dict]:
    """One row per #important tag kind per user turn, with the tasks it names."""
    out: list[dict] = []
    for t in block:
        text = _operator_text(t)
        if not text or "#important" not in text.lower():
            continue
        kinds = {(m.group(1) or "all").lower() for m in IMPORTANT_TAG_RE.finditer(command_text(text))}
        if not kinds:
            continue
        named = []
        for m in _TASK_ID_RE.finditer(text):
            if m.group(1).startswith("tk_") and m.group(1) not in named:
                named.append(m.group(1))
        body = IMPORTANT_TAG_RE.sub("", plain_text(text)).strip()
        head = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        for kind in sorted(kinds):
            out.append({
                "kind": kind, "project": project, "agent_id": agent_id,
                "session_id": session_id, "turn": t.number,
                "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
                "excerpt": _clip(head, 160), "tasks": ",".join(named),
            })
    return out


def _dones_of(
    session_id: str, project: str, agent_id: str, block: list[Turn]
) -> list[dict]:
    """One row per user turn carrying #done, with the tasks the message names."""
    out: list[dict] = []
    for t in block:
        text = _operator_text(t)
        if not text or "#done" not in text.lower() or not DONE_TAG_RE.search(command_text(text)):
            continue
        named: list[str] = []
        for m in _TASK_ID_RE.finditer(text):
            if m.group(1).startswith("tk_") and m.group(1) not in named:
                named.append(m.group(1))
        body = DONE_TAG_RE.sub("", plain_text(text)).strip()
        head = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        out.append({
            "project": project, "agent_id": agent_id, "session_id": session_id,
            "turn": t.number, "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
            "excerpt": _clip(head, 160), "tasks": ",".join(named),
        })
    return out


def _nows_of(
    session_id: str, project: str, agent_id: str, block: list[Turn]
) -> list[dict]:
    """One row per user turn carrying #now (or #now-todo …): the column, the
    lane named in braces, the whole message, and whether the agent answered."""
    out: list[dict] = []
    for i, t in enumerate(block):
        text = _operator_text(t)
        if not text or "#now" not in text.lower():
            continue
        command, lane, column = task_command(command_text(text))
        if command != "now":
            continue
        out.append({
            "project": project, "agent_id": agent_id, "session_id": session_id,
            "turn": t.number, "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"),
            # Answered, or a later turn was: a message sent while the agent
            # still worked does not end the agent's chance.
            "column_": column, "lane": lane,
            "answered": "1" if any((x.agent_summary or "").strip() for x in block[i:]) else "",
            "body": text,
        })
    return out


def parse_turns(chat_path: Path) -> list[Turn]:
    """All turns of one chat.md, with their full texts and header lines."""
    return parse_chat(chat_path)[0]


def parse_chat(chat_path: Path) -> tuple[list[Turn], int]:
    """(all turns of one chat.md, the number of lines in it).

    Handles both formats: one-line summaries (legacy) and multiline verbatim
    blocks (hook capture) — a **User**/**Agent** marker starts a block that
    runs until the next marker or turn header.

    A line ends at "\n" and nowhere else. The hook escapes a quoted turn
    header at the start of such a line (capture.py escape_content);
    ``str.splitlines`` also breaks on \x0b, \x1c–\x1e, \x85 and the
    Unicode separators, so a header pasted behind one of those read as a
    real turn, and every line number after it was off.
    """
    try:
        text = chat_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], 0
    turns: list[Turn] = []
    user_buf: list[str] = []
    agent_buf: list[str] = []
    mode = ""

    def flush() -> None:
        nonlocal mode
        if turns:
            turns[-1].user_summary = "\n".join(user_buf).strip()
            turns[-1].agent_summary = "\n".join(agent_buf).strip()
        user_buf.clear()
        agent_buf.clear()
        mode = ""

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()   # the file ends with a newline: that is no line
    for i, line in enumerate(lines, start=1):
        m = _TURN_RE.match(line)
        if m:
            try:
                at = datetime.fromisoformat(m.group(2))
            except ValueError:
                continue
            flush()
            turns.append(Turn(number=int(m.group(1)), at=at, line=i))
            continue
        if not turns:
            continue
        mu = _USER_RE.match(line)
        if mu:
            mode = "user"
            user_buf.append(mu.group(1))
            continue
        ma = _AGENT_RE.match(line)
        if ma:
            mode = "agent"
            agent_buf.append(ma.group(1))
            continue
        if _ESCAPED_RE.match(line):
            line = line[1:]
        if mode == "user":
            user_buf.append(line)
        elif mode == "agent":
            agent_buf.append(line)
    flush()
    return turns, len(lines)


# The tags a pasted block arrives in (Claude Code's <pasted_content id="…">):
# the text stays, the tags go, so no headline opens with markup.
_PASTE_TAG = re.compile(r"</?pasted_content[^>]*>")


def _clip(text: str, limit: int = 140) -> str:
    text = " ".join(_PASTE_TAG.sub(" ", text).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _headline(turns: list[Turn]) -> str:
    first = _clip(turns[0].user_summary or turns[0].agent_summary)
    if len(turns) == 1:
        return first
    last = _clip(turns[-1].user_summary or turns[-1].agent_summary)
    if last and last != first:
        return f"{first} → {last}"
    return first


#: An unended turn (an old chat with no transcript) is counted up to the next
#: prompt, but never past this: the person's pause is not the agent's work.
ESTIMATE_CAP_SEC = 20 * 60


def _worked(block: list[Turn]) -> tuple[list[int], bool]:
    """Each turn's working seconds, and whether all of them are known."""
    out: list[int] = []
    exact = True
    for i, t in enumerate(block):
        if t.end is not None:
            span = max(0, int((t.end - t.at).total_seconds()))
            out.append(min(span, t.active_sec) if t.active_sec is not None else span)
            continue
        exact = False
        nxt = block[i + 1].at if i + 1 < len(block) else None
        out.append(min(ESTIMATE_CAP_SEC, int((nxt - t.at).total_seconds())) if nxt else 0)
    return out, exact


def _acts(block: list[Turn], worked: list[int], before: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """When the chat was busy: each turn's measured stretches, or — for a
    turn measured by its end alone — its prompt to its working time.
    ``before``: helpers' stretches recorded on the next session's first
    line that fall before its prompt (they worked for this one)."""
    from .turntimes import union
    out = list(before)
    for t, w in zip(block, worked):
        if t.busy is not None:
            out.extend(t.busy)
        elif w:
            out.append((t.at, t.at + timedelta(seconds=w)))
    return union(out)


def _waiting(block: list[Turn], worked: list[int], acts: list[tuple[datetime, datetime]]) -> int:
    """Minutes from each answer's end to the next prompt, less the stretches
    a helper was still working (an unended turn ends where its estimate does)."""
    from .turntimes import clip, length
    total = 0.0
    for i, t in enumerate(block[:-1]):
        done = t.end or t.at + timedelta(seconds=worked[i])
        nxt = block[i + 1].at
        if nxt > done:
            total += (nxt - done).total_seconds() - length(clip(acts, done, nxt))
    return round(max(0.0, total) / 60)


def group_sessions(
    project: str,
    agent_id: str,
    turns: list[Turn],
    gap_minutes: int,
    total_lines: int,
) -> list[Session]:
    """Split one agent's turn list into sessions at gaps > ``gap_minutes``."""
    if not turns:
        return []
    sessions: list[Session] = []
    block: list[Turn] = [turns[0]]
    for turn in turns[1:]:
        # Helpers still working after the last answer are recorded on this
        # turn's line, before its prompt: they belong to the block before.
        before = [(a, min(b, turn.at)) for a, b in (turn.busy or []) if a < turn.at]
        # The pause is the person's: from the last answer's end (or a
        # helper's, later), when known.
        last = max([block[-1].end or block[-1].at, *(b for _, b in before)])
        gap = (turn.at - last).total_seconds() / 60
        if gap > gap_minutes or turn.at.date() != block[-1].at.date():
            sessions.append(_close(project, agent_id, block, turn.line - 1, before, gap_minutes))
            block = [turn]
        else:
            block.append(turn)
    sessions.append(_close(project, agent_id, block, total_lines, None, gap_minutes))
    return sessions


def _close(
    project: str, agent_id: str, block: list[Turn], end_line: int,
    before: list[tuple[datetime, datetime]] | None = None,
    gap_minutes: int = 30,
) -> Session:
    first, last = block[0], block[-1]
    seed = f"{project}|{agent_id}|{first.at.isoformat()}"
    from .turntimes import clip, length
    worked, exact = _worked(block)
    acts = _acts(block, worked, before or [])
    # The session runs on from its last prompt while the chat stays busy,
    # and stops at the first silence longer than the session gap: a chat
    # picked up again days later is not one session across the days.
    end = last.at
    for a, b in sorted([*acts, *((t.end, t.end) for t in block if t.end)]):
        if b <= end:
            continue
        if (a - end).total_seconds() > gap_minutes * 60:
            break
        end = b
    acts = clip(acts, first.at, end)
    duration = max(1, round((end - first.at).total_seconds() / 60))
    agent_min = min(duration, round(length(clip(acts, first.at, end)) / 60))
    turns = [
        {
            "n": t.number,
            "at": t.at.strftime("%H:%M"),
            "user": t.user_summary,
            "agent": t.agent_summary,
            **({"worked_sec": w} if t.end is not None else {}),
        }
        for t, w in zip(block, worked)
    ]
    sid = "ses_" + hashlib.sha256(seed.encode()).hexdigest()[:8]
    marks, prints = _prompts_of(sid, project, agent_id, block)
    return Session(
        id=sid,
        project=project,
        agent_id=agent_id,
        created_date=_yymm_dd(first.at),
        start_time=first.at.strftime("%H:%M"),
        end_time=end.strftime("%H:%M"),
        duration_min=duration,
        agent_min=agent_min,
        waiting_min=_waiting(block, worked, acts),
        helper_min=round(sum(t.helper_sec for t in block) / 60),
        timed="exact" if exact else "approx",
        turns_n=len(block),
        l1=_headline(block),
        turns=turns,
        chat_start_line=first.line,
        chat_end_line=end_line,
        mentions=_mentions_of(sid, project, agent_id, block),
        prompt_marks=marks,
        turn_prints=prints,
        keep_marks=_keeps_of(sid, project, agent_id, block),
        important_tags=_importants_of(sid, project, agent_id, block),
        done_tags=_dones_of(sid, project, agent_id, block),
        now_tags=_nows_of(sid, project, agent_id, block),
    )


def derive_sessions(
    chats: list[tuple[str, str, Path]], gap_minutes: int
) -> list[Session]:
    """Sessions for every (project, agent_id, chat_path) triple."""
    out: list[Session] = []
    from . import turntimes

    for project, agent_id, chat_path in chats:
        turns, total = parse_chat(chat_path)
        if not turns:
            continue
        known = turntimes.times(chat_path.parent)
        for t in turns:
            got = known.get(t.number)
            if got is not None:
                t.end, t.active_sec, t.busy, t.helper_sec = got.end, got.active_sec, got.busy, got.helper_sec
        out.extend(group_sessions(project, agent_id, turns, gap_minutes, total))
    return out

# ---------------------------------------------------------------------------
# Where an agent's chat is, and what its turns changed
# ---------------------------------------------------------------------------


def chat_paths(store: Any) -> dict[str, Path | None]:
    """agent_id → chat.md, once per store version (``store.agents()`` walks
    the disk). Kept on the store instance, so two stores never share one."""
    version = float(getattr(store, "view_mtime", 0.0) or 0.0)
    cached = getattr(store, "_chat_paths_cache", None)
    if cached is not None and cached[0] == version:
        return cached[1]
    out: dict[str, Path | None] = {}
    for a in store.agents():
        path = Path(a.get("_chat_path") or "")
        out[str(a.get("agent_id") or "")] = path if path.exists() else None
    store._chat_paths_cache = (version, out)
    return out


def chat_path(store: Any, agent_id: str) -> Path | None:
    return chat_paths(store).get(agent_id)


def turns_with_work(store: Any, row: dict[str, Any]) -> list[dict[str, Any]]:
    """One chat's turns, each carrying what it changed when git knows."""
    from . import gitwork

    try:
        turns = json.loads(row.get("turns_json") or "[]")
    except json.JSONDecodeError:
        turns = []
    path = chat_path(store, str(row.get("agent_id") or ""))
    if path is not None and turns:
        work, _ = gitwork.session_work(
            path, str(row.get("created_date") or ""), str(row.get("end_time") or ""), turns,
        )
        for turn, changed in zip(turns, work):
            if changed:
                turn["work"] = changed
    return turns
