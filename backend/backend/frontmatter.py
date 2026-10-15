"""The one reader of a ``---`` block.

Thirteen places in this backend split the opening fence by hand, with three
different offsets and three different ideas of what closes it. A detail
document written by one of them read differently in another: the body came
back with the frontmatter still glued on, and landed in an agent's prompt.

The convention here is ``contract_parts``' — the oldest and the strictest:

* the block opens only at the very start of the text, with ``---`` followed
  by a newline (``---`` on its own last line is not an opening fence);
* it closes at the first ``\\n---`` after that, whatever follows the dashes
  (a trailing newline is not required — a file that ends on its closing
  fence is still frontmatter);
* the body is everything after the closing fence, with leading blank lines
  taken off.

Two conventions were dropped on the way in, and both were looser:
``turns`` searched for the closing fence from offset 3, so ``---\\n---\\n``
(an empty block) read as frontmatter; ``promptlib`` demanded ``\\n---\\n``,
so a document ending on its fence read as having none. Neither difference
is observable in the ledgers — an empty block carries nothing, and every
writer here ends a document with a newline.

Three readings of the same block, by what the caller wants back:

* ``block(text)`` — the fence block verbatim (both fences) and the rest, for
  writers that keep the frontmatter untouched and re-render it.
* ``pairs(text)`` — ``key: value`` lines in order, repeats kept.
* ``meta(text)`` — the block through ``yaml.safe_load``; ``None`` when there
  is no block or it does not parse.
"""

from __future__ import annotations

from typing import Any

import yaml

__all__ = ["end_of", "block", "pairs", "meta", "body_of"]

_OPEN = "---\n"
_CLOSE = "\n---"


def end_of(text: str) -> int:
    """Index just past the closing fence, or ``-1`` when there is no block."""
    if not text.startswith(_OPEN):
        return -1
    end = text.find(_CLOSE, len(_OPEN))
    if end == -1:
        return -1
    return end + len(_CLOSE)


def block(text: str) -> tuple[str, str]:
    """``(the fence block including both fences, the rest)``.

    The rest keeps its leading newline — the callers that re-render a
    document (``turns``, ``promptlib``) join the two halves back together.
    """
    cut = end_of(text)
    return ("", text) if cut < 0 else (text[:cut], text[cut:])


def body_of(text: str) -> str:
    """Everything after the block, leading blank lines off."""
    cut = end_of(text)
    return text if cut < 0 else text[cut:].lstrip("\n")


def _head(text: str) -> str:
    cut = end_of(text)
    return "" if cut < 0 else text[len(_OPEN):cut - len(_CLOSE)]


def pairs(text: str) -> tuple[list[tuple[str, str]], str]:
    """``(pairs, body)`` — pairs keep their order and their repeats.

    A line with no colon is skipped; the contract's parts carry ``command``
    twice and more, so a dict would lose half of them.
    """
    cut = end_of(text)
    if cut < 0:
        return [], text
    out: list[tuple[str, str]] = []
    for line in _head(text).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out.append((k.strip(), v.strip()))
    return out, text[cut:].lstrip("\n")


def meta(text: str) -> tuple[dict[str, Any] | None, str]:
    """``(the block as YAML, body)`` — ``None`` when missing or unreadable.

    ``None`` and ``{}`` say different things: no block at all, against a
    block that parsed to nothing. The skill reader depends on the first.
    """
    cut = end_of(text)
    if cut < 0:
        return None, text
    try:
        data = yaml.safe_load(_head(text))
    except yaml.YAMLError:
        return None, text
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, text
    return data, text[cut:].lstrip("\n")
