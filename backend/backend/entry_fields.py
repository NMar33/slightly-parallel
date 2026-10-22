"""What an entry holds, by name.

Entries used to be written as four numbered levels — ``l1`` a headline,
``l2`` a why, ``l3`` bullets, ``l4`` proof — one framing laid over every
kind of entry. That was a draft. The pages are the truth now, and each page
shows its own thing: a decision has alternatives, a problem has attempts, a
standup has the movement per task. So agents write those things by name.

The four slots stay as storage: the ledgers, the detail documents and the
pages read them, and renaming them would be a data migration with nothing
to show for it. This module is the one place that knows which name lands in
which slot. Nothing agent-facing says ``l1…l4`` any more; a body that still
sends them is accepted, so an older session keeps working.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class TextField(NamedTuple):
    name: str
    slot: str          # l1 · l2 · l3 · l4 — storage, never shown to an agent
    kind: str          # "text" or "list"
    holds: str         # what the page of this lens shows there


def _f(name: str, slot: str, holds: str) -> TextField:
    return TextField(name, slot, "list" if slot == "l3" else "text", holds)


# For a lens with nothing more specific to say.
DEFAULT: tuple[TextField, ...] = (
    _f("headline", "l1", "one line: what this entry is"),
    _f("summary", "l2", "a paragraph: what a reader needs to know"),
    _f("points", "l3", "the specifics, one per item"),
    _f("detail", "l4", "the long part: output, excerpts, what to check"),
)

BY_LENS: dict[str, tuple[TextField, ...]] = {
    "scan": (
        _f("summary", "l1", "one sentence: the change that matters most, as a fact about the product"),
        _f("why", "l2", "two sentences: what was asked for, and whether the result matches"),
        _f("deltas", "l3", "at most 7 items: one change a user or an agent can see, each"),
        _f("proof", "l4", "at most 5 lines: the claim, what checks it, checked or not"),
    ),
    "file": (
        _f("summary", "l1", "one line: N files · +X/−Y · the theme"),
        _f("narrative", "l2", "the overall story, then a line per file"),
        _f("per_file", "l3", "one item per file: the functions and classes touched"),
        _f("diff", "l4", "the diff; git fills it when left empty"),
    ),
    "decision": (
        _f("decision", "l1", "one line: what was chosen"),
        _f("why", "l2", "one or two sentences: the reason, then the state"),
        _f("alternatives", "l3", 'only options someone proposed: "<option> — rejected: <reason>"'),
        _f("excerpt", "l4", "for a major decision: the lines of chat where it was decided"),
    ),
    "problem": (
        _f("problem", "l1", "one line: what is blocked"),
        _f("impact", "l2", "what it affects, and who or what owns the fix"),
        _f("attempts", "l3", 'one item per attempt: "<tried> — <result>"'),
        _f("excerpt", "l4", "the error, the log, the chat excerpt"),
    ),
    "standup": (
        _f("summary", "l1", "one sentence: the one or two changes that matter most"),
        _f("deviation", "l2", "what broke, was redone, or was corrected"),
        _f("movement", "l3", "one outcome a user or an agent can see, each"),
        TextField("story", "l4", "text", "the day told: what happened and why it matters, one to three paragraphs"),
        TextField("decisions", "l4", "list", 'one per decision made that day: "<decision> — <reason> · <who>, <HH:MM>"'),
        TextField("forgotten", "l4", "list", "asked or promised in a chat and not taken up there, one each"),
        _f("detail", "l4", "needs an answer, next, state"),
    ),
    "task": (
        _f("title", "l1", "the thing, in the user's words"),
    ),
    "sprint": (
        _f("headline", "l1", "one line: the block of work"),
        _f("retro", "l2", "when it ends: what happened against the plan"),
        _f("points", "l3", "the specifics, one per item"),
        _f("detail", "l4", "anything longer"),
    ),
}

SLOTS: tuple[str, ...] = ("l1", "l2", "l3", "l4")

# Lenses whose headline an update may change: a standup is rewritten whole
# when the rules for it change. Every other headline is fixed once written.
HEADLINE_MUTABLE: frozenset[str] = frozenset({"standup"})


def merge_parts(lens: str, body: dict[str, Any], old_l4: str) -> None:
    """An update that sends some of the parts sharing the l4 slot keeps the
    others from the document, so changing the story leaves the decisions."""
    parts = PARTS.get(lens)
    if not parts or "l4" in body or not any(n in body for n, _h in parts):
        return
    old = _split(lens, old_l4 or "")
    for name, _h in parts:
        if name not in body and old.get(name):
            body[name] = old[name]

# Fields of one lens that share the l4 slot, each under its own heading in
# the detail document, in this order. A slot written by an older session
# with no headings reads back as the last field (the plain detail).
PARTS: dict[str, tuple[tuple[str, str], ...]] = {
    "standup": (("story", "The day"), ("decisions", "Decisions"),
                ("forgotten", "Maybe forgotten"), ("detail", "More")),
}


def _compose(lens: str, body: dict[str, Any]) -> None:
    parts = PARTS.get(lens)
    if not parts or body.get("l4") not in (None, ""):
        return
    names = [n for n, _h in parts]
    if not any(n in body for n in names[:-1]):
        return                      # only the plain detail: stored as it always was
    blocks = []
    for name, heading in parts:
        value = body.pop(name, None)
        if isinstance(value, list):
            value = "\n".join(f"- {str(v).strip()}" for v in value if str(v).strip())
        if value not in (None, ""):
            blocks.append(f"### {heading}\n{str(value).strip()}")
    body["l4"] = "\n\n".join(blocks)


def _split(lens: str, l4: str) -> dict[str, Any]:
    parts = PARTS.get(lens) or ()
    out: dict[str, Any] = {}
    by_heading = {h: n for n, h in parts}
    import re
    chunks = re.split(r"(?m)^### (.+)$", l4 or "")
    if len(chunks) < 3 or not all(h.strip() in by_heading for h in chunks[1::2]):
        return {parts[-1][0]: l4} if parts else {}
    for heading, text in zip(chunks[1::2], chunks[2::2]):
        out[by_heading[heading.strip()]] = text.strip()
    return out


def fields_for(lens: str, columns: tuple[str, ...] | list[str] = ()) -> tuple[TextField, ...]:
    """The named text fields of a lens. A name that is also a real column of
    the lens is not offered twice: the column is the field, and the server
    copies the headline into it as it always did."""
    taken = set(columns)
    return tuple(f for f in BY_LENS.get(lens, DEFAULT) if f.name not in taken or f.slot == "l1")


def to_slots(lens: str, body: dict[str, Any], columns: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Move named text fields into their storage slots, in place.

    A slot already sent wins over its name (an older session). A name that is
    a real column of the lens stays where it is, and also fills the headline
    slot when it is the headline.
    """
    taken = set(columns)
    _compose(lens, body)
    for f in fields_for(lens, columns):
        if f.name not in body:
            continue
        value = body[f.name]
        if f.slot not in body or body[f.slot] in (None, "", []):
            if f.kind == "list" and isinstance(value, str):
                value = [ln.strip() for ln in value.splitlines() if ln.strip()]
            elif f.kind == "text" and isinstance(value, list):
                # A few short items sent where the page shows text: a standup's
                # deviation. Kept as a list the page can read, one line each.
                value = "\n".join(f"- {str(v).strip()}" for v in value if str(v).strip())
            body[f.slot] = value
        if f.name not in taken:
            body.pop(f.name)
    return body


def from_slots(
    lens: str, headline: Any, l2: Any, l3: Any, l4: Any,
    columns: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """The same entry, read back by name — what `to_slots` took apart.

    Every name of the lens is present, empty when the entry has nothing
    there, so a reader never has to know the slots exist.
    """
    values = {"l1": headline or "", "l2": l2 or "", "l3": list(l3 or []), "l4": l4 or ""}
    if lens in PARTS:
        split = _split(lens, str(l4 or ""))
        out: dict[str, Any] = {}
        for f in fields_for(lens, columns):
            if f.slot != "l4":
                out[f.name] = values[f.slot]
            elif f.kind == "list":
                out[f.name] = [ln[2:].strip() for ln in str(split.get(f.name) or "").splitlines() if ln.startswith("- ")]
            else:
                out[f.name] = split.get(f.name, "")
        return out
    return {f.name: values[f.slot] for f in fields_for(lens, columns)}
