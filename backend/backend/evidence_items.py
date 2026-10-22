"""The two structured evidence items: what was touched, and what was done.

Evidence has always been text and screenshots. These two kinds carry the
same facts a scan's file entry and architecture form carry — the same field
names, the same closed vocabularies — scoped to one task and stored with the
task's other evidence.

They are deliberately not written into ``files.csv`` and
``architecture.csv``: the file heatmap sums per file per day across file
entries, so a task's files landing there as well would count one edit twice,
and a scan would stop meaning "what changed since the last look". Same
words, different ledger, linked both ways when it is read.
"""

from __future__ import annotations

import json
from typing import Any

from . import limits
from .archvocab import GROUPS, OPS, TYPE_GROUP

MAX_PATHS = 200
MAX_CHANGES = 50
MAX_PATH = 400
MAX_WHY = 500
MAX_NAME = limits.MAX_ITEM_NAME
MAX_NOTE = limits.MAX_EVIDENCE_NOTE

# The file entry's own vocabulary (file_entries.py), and the spellings an
# agent is likely to reach for instead.
ACTIONS: tuple[str, ...] = ("created", "modified", "deleted", "renamed")
_ACTION_ALIAS = {
    "added": "created", "add": "created", "new": "created",
    "changed": "modified", "change": "modified", "edited": "modified",
    "removed": "deleted", "remove": "deleted", "delete": "deleted",
    "rename": "renamed",
}
COVERAGE: tuple[str, ...] = ("covered", "partial", "untested")


def _text(value: Any, limit: int, field: str) -> str:
    out = " ".join(str(value or "").split())
    if len(out) > limit:
        raise ValueError(f"{field} is at most {limit} characters")
    return out


def _bounded_int(value: Any, lo: int, hi: int, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number between {lo} and {hi}")
    if not lo <= n <= hi:
        raise ValueError(f"{field} must be between {lo} and {hi}")
    return n


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def clean_files(item: dict[str, Any]) -> dict[str, Any]:
    """``{start_here, paths}`` — one record per file the agent says it touched."""
    raw = item.get("paths")
    if not isinstance(raw, list) or not raw:
        raise ValueError("a files item needs a `paths` list: one record per file you touched")
    if len(raw) > MAX_PATHS:
        raise ValueError(f"at most {MAX_PATHS} files in one item")
    paths: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            entry = {"path": entry}
        if not isinstance(entry, dict):
            raise ValueError(f"paths[{i}]: not an object")
        path = _text(entry.get("path"), MAX_PATH, f"paths[{i}].path")
        if not path:
            raise ValueError(f"paths[{i}] has no path")
        if path in seen:
            continue  # the same file named twice is one file
        seen.add(path)
        action = str(entry.get("action") or "modified").strip().lower()
        action = _ACTION_ALIAS.get(action, action)
        if action not in ACTIONS:
            raise ValueError(
                f"paths[{i}].action must be one of {', '.join(ACTIONS)} — not {action!r}"
            )
        coverage = str(entry.get("test_coverage") or "").strip().lower()
        if coverage and coverage not in COVERAGE:
            raise ValueError(
                f"paths[{i}].test_coverage must be one of {', '.join(COVERAGE)}"
            )
        rec: dict[str, Any] = {
            "path": path,
            "action": action,
            "lines_add": _count(entry.get("lines_add")),
            "lines_del": _count(entry.get("lines_del")),
            "why": _text(entry.get("why"), MAX_WHY, f"paths[{i}].why"),
        }
        importance = _bounded_int(entry.get("importance"), 1, 5, f"paths[{i}].importance")
        if importance is not None:
            rec["importance"] = importance
        blast = _bounded_int(entry.get("blast_radius"), 1, 10, f"paths[{i}].blast_radius")
        if blast is not None:
            rec["blast_radius"] = blast
        if coverage:
            rec["test_coverage"] = coverage
        if entry.get("security_surface") is not None:
            rec["security_surface"] = bool(entry.get("security_surface"))
        paths.append(rec)
    start = _text(item.get("start_here"), MAX_PATH, "start_here")
    return {"start_here": start, "paths": paths}


def clean_changes(item: dict[str, Any]) -> dict[str, Any]:
    """``{changes}`` — what landed, in the architecture vocabulary."""
    raw = item.get("changes")
    if not isinstance(raw, list) or not raw:
        raise ValueError("a change item needs a `changes` list: one record per thing that landed")
    if len(raw) > MAX_CHANGES:
        raise ValueError(f"at most {MAX_CHANGES} changes in one item")
    out: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"changes[{i}]: not an object")
        op = str(entry.get("op") or "add").strip().lower()
        if op not in OPS:
            raise ValueError(f"changes[{i}].op must be one of {', '.join(OPS)}")
        kind = str(entry.get("type") or "").strip().lower()
        if kind not in TYPE_GROUP:
            raise ValueError(
                f"changes[{i}].type must be one of "
                + "; ".join(f"{g}: {', '.join(ts)}" for g, ts in GROUPS.items())
            )
        name = _text(entry.get("name"), MAX_NAME, f"changes[{i}].name")
        if not name:
            raise ValueError(f"changes[{i}] needs a name")
        where = entry.get("path")
        if isinstance(where, str):
            where = [where]
        if where is None:
            where = []
        if not isinstance(where, list):
            raise ValueError(f"changes[{i}].path must be a path or a list of paths")
        out.append({
            "op": op,
            "type": kind,
            "group": TYPE_GROUP[kind],
            "name": name,
            "path": [_text(p, MAX_PATH, f"changes[{i}].path") for p in where[:5] if str(p).strip()],
            "note": _text(entry.get("note"), MAX_NOTE, f"changes[{i}].note"),
        })
    return {"changes": out}


def dump(payload: dict[str, Any]) -> str:
    """The item's body as stored: JSON in the column that already holds text."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def load(body: str) -> dict[str, Any]:
    """Back out of the column. A body that does not read is an empty item."""
    try:
        out = json.loads(body or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return out if isinstance(out, dict) else {}
