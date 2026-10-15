"""Task documents — a description, then the rounds it was asked again.

A task is worked on more than once: you write what you want, an agent
does it, you want the next thing on the same task. That next thing is a
**turn**, and it lives in the task's document rather than in a new task —
same work, next instruction. (When a step really is its own unit of work,
with its own status, that is a stack: ``stack_id``.)

The document is frontmatter plus one section per round::

    ---
    id: tk_28b1b490
    …
    ---
    ## Description

    the first instruction

    ## Turn 2 · 2608-29 22:55

    the next instruction

Turn 1 *is* the description and carries no stamp — the task's own
``created_date`` is its date. Chronological on disk; the dashboard renders
newest first. The reference a turn is copied under is ``tk_28b1b490.2`` —
turn 1 keeps the bare id, so every copy of a single-turn task reads
exactly as before. The chat mention harvester understands the suffix,
which is what ties a turn of the task to the turns of the conversation
that answered it.

Task documents written before this format (a ``## L2`` section with
``--- turn N · date time ---`` marker lines inside it) are read the same
way and rewritten once at startup by :func:`migrate_task_docs`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from . import frontmatter
from .file_safety import atomic_write

# "## Turn 2 · 2608-29 22:55" on a line of its own. The date is Slightly Parallel's
# YYMM-DD; the time is optional so a hand-written heading still parses.
TURN_HEAD_RE = re.compile(
    r"^##\s+Turn\s+(\d+)(?:\s+·\s+(\d{4}-\d{2})(?:\s+(\d{2}:\d{2}))?)?[ \t]*$",
    re.MULTILINE,
)
DESCRIPTION_HEAD_RE = re.compile(r"^##\s+Description[ \t]*$", re.MULTILINE)

# The format before this one: a generic L2 section carrying marker lines.
_LEGACY_SECTION_RE = re.compile(r"^\s*##\s+(L2|L3|L4)\b.*$", re.MULTILINE | re.IGNORECASE)
_LEGACY_MARK_RE = re.compile(
    r"^--- turn (\d+) · (\d{4}-\d{2})(?: (\d{2}:\d{2}))? ---[ \t]*$",
    re.MULTILINE,
)

# A task/doc id, optionally carrying a turn: tk_28b1b490.2
TASK_REF_RE = re.compile(
    r"\b((?:tk|dc)_[a-z0-9][a-z0-9_-]{2,40})(?:\.(\d{1,3}))?\b"
)

MAX_TURNS = 200


@dataclass(frozen=True)
class Turn:
    n: int
    date: str  # "" for turn 1 — the task's own created_date is its date
    time: str
    text: str

    def as_dict(self) -> dict:
        return {"n": self.n, "date": self.date, "time": self.time, "text": self.text}


def heading(n: int, date: str, time: str) -> str:
    """The section heading that opens turn ``n``."""
    if n <= 1:
        return "## Description"
    stamp = f"{date} {time}".strip()
    return f"## Turn {n} · {stamp}" if stamp else f"## Turn {n}"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter block including both fences, body) — ('', text) if none."""
    return frontmatter.block(text)


def _parse_legacy(body: str) -> list[Turn]:
    """The rounds of a document from before this format. Nothing written is
    left out: text above the first heading opens the description, and the
    ``## L3`` and ``## L4`` sections close it under their own sub-headings."""
    sections: dict[str, str] = {"l2": ""}
    matches = list(_LEGACY_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[name] = "\n\n".join(x for x in (sections.get(name, ""), body[start:end].strip("\n")) if x)
    if matches:
        above = body[: matches[0].start()].strip()
        text = "\n\n".join(x for x in (above, sections["l2"]) if x)
    else:
        text = body
    rest = "\n\n".join(
        f"### {title}\n\n{sections[key].strip()}"
        for key, title in (("l3", "Detail"), ("l4", "Original message"))
        if sections.get(key, "").strip()
    )
    marks = list(_LEGACY_MARK_RE.finditer(text))
    first = (text[: marks[0].start()] if marks else text).strip()
    first = "\n\n".join(x for x in (first, rest) if x)
    if not marks:
        return [Turn(1, "", "", first)] if first else []
    out = [Turn(1, "", "", first)]
    for i, m in enumerate(marks):
        chunk = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        out.append(Turn(int(m.group(1)), m.group(2), m.group(3) or "", chunk.strip()))
    return out


def is_task_doc(text: str) -> bool:
    """True when the body is in this format (a Description or Turn heading)."""
    _, body = _split_frontmatter(text)
    return bool(DESCRIPTION_HEAD_RE.search(body) or TURN_HEAD_RE.search(body))


def parse_task_doc(text: str) -> list[Turn]:
    """The rounds of a task document, oldest first; turn 1 is the description.

    Reads both this format and the legacy ``## L2`` + marker one, so a
    document that predates the format is one turn (or several) either way.
    """
    _, body = _split_frontmatter(text or "")
    if not (DESCRIPTION_HEAD_RE.search(body) or TURN_HEAD_RE.search(body)):
        return _parse_legacy(body)
    heads = [(m.start(), m.end(), 1, "", "") for m in DESCRIPTION_HEAD_RE.finditer(body)]
    heads += [
        (m.start(), m.end(), int(m.group(1)), m.group(2) or "", m.group(3) or "")
        for m in TURN_HEAD_RE.finditer(body)
    ]
    heads.sort()
    out: list[Turn] = []
    for i, (_start, end, n, date, time) in enumerate(heads):
        stop = heads[i + 1][0] if i + 1 < len(heads) else len(body)
        out.append(Turn(n, date, time, body[end:stop].strip()))
    # A document may hold turns without a Description (never seen, but
    # cheap to keep honest): renumber from 1 in order.
    if out and out[0].n != 1:
        out = [replace(t, n=i + 1) for i, t in enumerate(out)]
    return out


def render_turns(turns: list[Turn]) -> str:
    """The body of a task document from its rounds."""
    parts: list[str] = []
    for t in turns:
        parts.append(heading(t.n, t.date, t.time))
        parts.append("")
        parts.append(t.text.strip())
        parts.append("")
    return "\n".join(parts)


def build_task_doc(frontmatter: str, turns: list[Turn]) -> str:
    """Frontmatter block (with its fences) + the rounds as sections."""
    fm = frontmatter.rstrip("\n")
    body = render_turns(turns)
    return f"{fm}\n\n{body}" if body else f"{fm}\n"


def description_of(turns: list[Turn]) -> str:
    return turns[0].text if turns else ""


def append_turn(turns: list[Turn], text: str, date: str, time: str) -> list[Turn]:
    """The rounds with ``text`` added as the next one.

    An empty task gains a description, not a turn 2.
    """
    body = (text or "").strip()
    if not body:
        raise ValueError("a turn needs text")
    if not turns:
        return [Turn(1, "", "", body)]
    if len(turns) >= MAX_TURNS:
        raise ValueError(f"a task holds at most {MAX_TURNS} turns")
    return [*turns, Turn(turns[-1].n + 1, date, time, body)]


def replace_turn(turns: list[Turn], text: str, n: int | None = None) -> list[Turn]:
    """The rounds with turn ``n`` (default: the newest) re-worded — an edit,
    not a new round. Replacing turn 1 of an empty task creates it."""
    body = (text or "").strip()
    if not turns:
        return [Turn(1, "", "", body)] if body else []
    target = turns[-1].n if n is None else n
    if not any(t.n == target for t in turns):
        raise ValueError(f"no turn {target}")
    return [replace(t, text=body) if t.n == target else t for t in turns]


def turn_ref(task_id: str, n: int) -> str:
    """How turn ``n`` is written when it is copied: ``tk_…`` or ``tk_….2``."""
    return task_id if n <= 1 else f"{task_id}.{n}"


def parse_ref(ref: str) -> tuple[str, int]:
    """``tk_28b1b490.2`` → ``("tk_28b1b490", 2)``; a bare id → turn 1."""
    m = TASK_REF_RE.fullmatch((ref or "").strip())
    if not m:
        return (ref or "").strip(), 1
    return m.group(1), int(m.group(2) or 1)


def migrate_task_docs(data_root: Path) -> int:
    """Rewrite legacy task documents into this format, once. Returns the count.

    A legacy document is one under ``task_details/`` whose body is a
    ``## L2`` section (with or without marker lines). Idempotent: documents
    already carrying a Description or Turn heading are left alone.
    """
    folder = data_root / "task_details"
    if not folder.is_dir():
        return 0
    n = 0
    for path in sorted(folder.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if is_task_doc(text):
            continue
        fm, body = _split_frontmatter(text)
        if not body.strip() and not fm:
            continue
        turns = _parse_legacy(body)
        # Nothing was read out of it: rewriting would leave only the frontmatter.
        if not turns:
            continue
        atomic_write(path, build_task_doc(fm, turns))
        n += 1
    return n
