"""A task's history: one row per changed field, appended to
``task_events.csv``. Every router that changes a task writes it here, the
board's own updates and links, sprints, evidence, marks, the story and
#done alike; the task window's History reads it back."""

from __future__ import annotations

import hashlib
import time

from .csvio import append_rows_raw
from .db import ViewStore
from .entities import TASK_EVENT_COLUMNS

#: Who a change is stamped with when the body names nobody: the board.
DEFAULT_ACTOR = "operator"


def append_events(
    store: ViewStore, task_id: str, actor: str, changes: list[tuple[str, str, str]]
) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    for i, (field, old_v, new_v) in enumerate(changes):
        # The clock in nanoseconds and the position in the batch are part
        # of the seed: two identical changes written in one second (the
        # same body edit twice, two "(updated)" markers) must not share an
        # id — the timeline keys on it, and drops the second.
        seed = f"{task_id}{time.time_ns()}{i}{actor or DEFAULT_ACTOR}{field}{new_v}".encode()
        event_id = "ev_" + hashlib.sha256(seed).hexdigest()[:10]
        rows.append([event_id, task_id, ts, actor or DEFAULT_ACTOR, field, old_v, new_v])
    append_rows_raw(
        store.data_root / "task_events.csv", TASK_EVENT_COLUMNS, rows
    )
