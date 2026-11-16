"""What a refusal must and must not do, for the tests that send wrong shapes
(test_agent_shaped_writes.py, test_write_fuzzer.py).

- It must not contradict itself: a value refused by name must not be listed
  among the allowed ones in the same message (docs/testing.md case 5: the
  tags list refused with ``ag_followup`` named as allowed).
- It must change no file of the data root.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Where a message lists what is allowed: "… one of: a, b, c", "1–3 of: a, b".
_ALLOWED = re.compile(r"\bof:\s*(.+)$", re.S)
# A message about the shape is not about the value: ["agent"] for a single
# value is refused for being a list, though "agent" is allowed.
_SHAPE = re.compile(r"\bnot (a |an )?(list|dict|int|bool|float|NoneType|object|array|number)\b|is one text value|tags is text")


def sent_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def contradicts(detail: str, sent: Any) -> str:
    """The value the message both refuses and allows, or ''."""
    m = _ALLOWED.search(detail or "")
    if not m or _SHAPE.search(detail):
        return ""
    allowed = {a.strip(" .`'\"") for a in re.split(r"[,·]", m.group(1))}
    head = detail[:m.start()]
    for name in sent_names(sent):
        # The refused value as the message shows it: repr of a list, or the name.
        if name in allowed and (repr(sent) in head or str(sent) in head):
            return name
    return ""


def snapshot(root: Path, skip: tuple[str, ...] = ()) -> dict[str, tuple[int, int]]:
    """Every file under root: (size, mtime_ns). Cheap enough per request."""
    out: dict[str, tuple[int, int]] = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            # A lock's sidecar file is made by taking the lock, not a write.
            if rel.startswith(skip) or rel.endswith(".lock"):
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[rel] = (st.st_size, st.st_mtime_ns)
    return out


def changed(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
