"""What agents posted, read once per store version.

Eight CSV-backed views, each re-parsed by DuckDB on every query: scanning
them per request made the sessions list cost 1.2–1.9 s, and scanning them
per *send* made a prompt's detail cost half a second. The store already
knows when anything changed — ``view_mtime`` moves on every rebuild — so the
posts are read once per version and every caller buckets from memory.
"""

from __future__ import annotations

import logging

import duckdb

from .db import ViewStore

# (view, label): the entries an agent can post during a run. Everything the
# contract lets an agent write belongs here — a kind left out simply never
# shows on the chat that produced it, which is how standups, skills
# and artifacts stayed invisible on the chat page.
VIEWS: tuple[tuple[str, str], ...] = (
    ("scans_mutual", "scans"), ("decisions_mutual", "decisions"),
    ("files_mutual", "files"), ("problems_mutual", "problems"),
    ("rules_mutual", "rules"), ("visions_mutual", "visions"),
    ("architecture_mutual", "architecture"), ("task_evidence_mutual", "evidence"),
    ("standups_mutual", "standups"), ("skills_mutual", "skills"),
    ("artifacts_mutual", "artifacts"),
    ("notes_mutual", "notes"),
)
# Sprints are not here: the operator plans them and their rows name no
# agent. Evidence is stamped with one ISO moment, not a date and a time.
_SELECT = "SELECT agent_id, created_date, created_time FROM {view}"
_SELECT_STAMPED = (
    "SELECT agent_id, substr(created_at, 3, 2) || substr(created_at, 6, 2) || '-' || "
    "substr(created_at, 9, 2) AS created_date, substr(created_at, 12, 5) AS created_time FROM {view}"
)
_STAMPED = frozenset({"task_evidence_mutual"})

# The caches hang on the store instance, keyed by its version: two stores
# with the same mtime (every test has its own) must never share one.


def posts(store: ViewStore) -> dict[str, list[tuple[str, str, str]]]:
    """Every post by kind, as (agent, date, time) — one read per store version."""
    version = float(getattr(store, "view_mtime", 0.0) or 0.0)
    cached = store._posts_cache
    if cached is not None and cached[0] == version:
        return cached[1]
    out: dict[str, list[tuple[str, str, str]]] = {}
    for view, label in VIEWS:
        try:
            rows = store.query((_SELECT_STAMPED if view in _STAMPED else _SELECT).format(view=view))
        except duckdb.Error:
            # Said out loud: a query that does not fit its view used to read
            # as "nothing posted", and evidence went uncounted that way.
            logging.getLogger("sp.produced").warning("posts: %s unreadable", view, exc_info=True)
            rows = []
        out[label] = [
            (str(r.get("agent_id") or ""), str(r.get("created_date") or ""),
             str(r.get("created_time") or ""))
            for r in rows
        ]
    store._posts_cache = (version, out)
    return out


def count_in(
    store: ViewStore, agent_id: str, date: str, start: str, end: str,
) -> dict[str, int]:
    """Posts by ``agent_id`` on ``date`` with a time inside [start, end]."""
    out: dict[str, int] = {}
    for label, rows in posts(store).items():
        n = sum(1 for a, d, t in rows if a == agent_id and d == date and start <= t <= end)
        if n:
            out[label] = n
    return out


def task_mentions(store: ViewStore) -> dict[str, int]:
    """Distinct tasks mentioned per session — one query per store version."""
    version = float(getattr(store, "view_mtime", 0.0) or 0.0)
    cached = store._mentions_cache
    if cached is not None and cached[0] == version:
        return cached[1]
    from .routers.deps import rows_or_empty
    rows = rows_or_empty(
        store, "SELECT session_id, count(DISTINCT task_id) AS n FROM task_mentions GROUP BY session_id"
    )
    out = {str(r["session_id"]): int(r["n"] or 0) for r in rows}
    store._mentions_cache = (version, out)
    return out


def marks(store: ViewStore) -> dict[str, dict[str, int]]:
    """What was marked in a chat, per session — one read per store version.

    A chat is not only what came out of it: it can be started from a saved
    prompt, and a message in it can be kept as a vision, a rule, a problem,
    a skill or an artifact. Both are recorded against the session and the
    turn, so they say where the work came in, which nothing else on the
    page shows.
    """
    # marks.csv is one of the store's file sources: a ★ moves view_mtime.
    version = float(getattr(store, "view_mtime", 0.0) or 0.0)
    cached = store._marks_cache
    if cached is not None and cached[0] == version:
        return cached[1]
    from .routers.deps import rows_or_empty
    out: dict[str, dict[str, int]] = {}
    # A ledger with no file yet is empty; any other failure is a real one.
    for r in rows_or_empty(store, "SELECT session_id, count(*) AS n FROM prompt_marks GROUP BY session_id"):
        out.setdefault(str(r["session_id"]), {})["prompt"] = int(r["n"] or 0)
    for r in rows_or_empty(store, "SELECT session_id, kind, count(*) AS n FROM keep_marks GROUP BY session_id, kind"):
        kind = str(r.get("kind") or "").strip() or "kept"
        out.setdefault(str(r["session_id"]), {})[f"kept-{kind}"] = int(r["n"] or 0)
    # Messages the operator starred (#important, or the ★ in the reader).
    from . import marklib
    for m in marklib.active(store):
        if m.get("kind") == "message" and m.get("session_id"):
            d = out.setdefault(str(m["session_id"]), {})
            d["important"] = d.get("important", 0) + 1
    store._marks_cache = (version, out)
    return out
