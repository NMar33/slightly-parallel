"""The grammar shared by task turns, chat mentions and Git trailers."""

import re

# Minted ids are tk_ + 8 hex, but imported or hand-written boards may use
# readable ids (tk_bc_replica); accept both — consumers keep only ids that
# exist as tasks, so a stray token in prose is not a mention. Storyboard
# docs (dc_…) are found the same way, so a doc's history shows who worked
# on it.
# A reference may carry the task's turn — tk_28b1b490.2 — so a chat turn
# can be tied to the round of instruction that asked for it. The id is
# group 1, the turn (when written) group 2.
TASK_REF_RE = re.compile(r"\b((?:tk|dc)_[a-z0-9][a-z0-9_-]{2,40})(?:\.(\d{1,3}))?\b")


def task_ids(text: str, *, include_documents: bool = False) -> list[str]:
    """Return unique IDs in mention order, without their optional turn suffix."""
    return list(dict.fromkeys(
        match[1] for match in TASK_REF_RE.finditer(text)
        if include_documents or match[1].startswith("tk_")
    ))
