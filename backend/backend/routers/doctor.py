"""The data doctor — fsck for a data root made of files.

Slightly Parallel's database is text on disk, and text on disk gets edited by hand,
restored from backups, and written by tools that are not this server. The
API can gate what it accepts; nothing gates what is already there. This
endpoint examines every source the dashboard reads and names what is wrong,
so damage is a report — never a mystery 500 or a silently missing row.

Read-only by design: the doctor diagnoses, the operator decides.
"""

from __future__ import annotations

import csv
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ..db import ViewStore
from ..docs_md import resolve_under
from ..entities import ENTITIES, LEDGERS
from ..models import ScanRow
from .deps import clean, get_store
from .lenses import ENUM_FIELDS, READ_MODELS

router = APIRouter()

_MAX_ISSUES = 500


def _issue(
    issues: list[dict[str, Any]], severity: str, kind: str, file: str,
    detail: str, *, row_id: str = "", line: int | None = None,
) -> None:
    if len(issues) >= _MAX_ISSUES:
        return
    entry: dict[str, Any] = {
        "severity": severity, "kind": kind, "file": file, "detail": detail,
    }
    if row_id:
        entry["id"] = row_id
    if line is not None:
        entry["line"] = line
    issues.append(entry)


def _scan_csv_structure(path: Path, issues: list[dict[str, Any]]) -> int:
    """Ragged rows, blank ids, duplicate ids — straight off the raw file."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = [c.strip() for c in next(reader, [])]
            if not header:
                if path.stat().st_size > 0:
                    _issue(issues, "error", "unreadable-header", path.name,
                           "file has bytes but no readable header row")
                return 0
            id_idx = header.index("id") if "id" in header else None
            ids: Counter[str] = Counter()
            n = 0
            for lineno, raw in enumerate(reader, start=2):
                n += 1
                if len(raw) != len(header):
                    _issue(issues, "warning", "ragged-row", path.name,
                           f"{len(raw)} fields where the header has {len(header)} — "
                           "a rewrite of this file may drop the extras",
                           line=lineno)
                if id_idx is not None and id_idx < len(raw):
                    rid = raw[id_idx].strip()
                    if not rid:
                        _issue(issues, "error", "blank-id", path.name,
                               "row has no id — updates and details cannot address it",
                               line=lineno)
                    else:
                        ids[rid] += 1
            for rid, count in ids.items():
                if count > 1:
                    _issue(issues, "error", "duplicate-id", path.name,
                           f"This id is used by {count} rows. Only the first one is updated.", row_id=rid)
            return n
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        _issue(issues, "error", "unreadable-file", path.name,
               f"{type(exc).__name__}: {exc}")
        return 0


@router.get("/api/doctor")
def doctor(store: ViewStore = Depends(get_store)) -> dict:
    issues: list[dict[str, Any]] = []
    root = store.data_root
    files_checked = 0
    rows_checked = 0

    # 1. The load seam: files that already failed and were degraded to empty.
    for err in getattr(store, "load_errors", []):
        _issue(issues, "error", "load-error", Path(err.get("file", "")).name,
               f"{err.get('stage', '')}: {err.get('error', '')} — "
               "this source is being served as empty")

    # 2. Raw structure of every CSV the dashboard reads.
    csv_paths = [root / ent.csv for ent in ENTITIES.values()]
    csv_paths.append(root / "scans.csv")
    csv_paths.extend(root / name for _, name, _ in LEDGERS)
    for proj in store.projects:
        for attr in ("goals_csv", "decisions_csv", "activity_csv"):
            p = getattr(proj, attr)
            if p is not None:
                csv_paths.append(p)
    for path in csv_paths:
        if path.exists():
            files_checked += 1
            rows_checked += _scan_csv_structure(path, issues)

    # 3. What the strict readers demand, row by row, through the same views
    #    the pages read — overlays and normalisation included.
    view_models = [(ENTITIES[name].view, model, ENTITIES[name].csv)
                   for name, model in READ_MODELS.items()]
    view_models.append(("scans", ScanRow, "scans.csv"))
    for view, model, csv_name in view_models:
        for r in store.query(f"SELECT * FROM {view}"):
            try:
                model(**clean(r))
            except ValidationError as exc:
                fields = ", ".join(str(e["loc"][0]) for e in exc.errors()[:3])
                _issue(issues, "error", "unreadable-row", csv_name,
                       f"row fails the {model.__name__} reader (fields: {fields}) — "
                       "aggregate pages skip it", row_id=str(r.get("id") or ""))

    # 4. Detail references: escapes and dangling files.
    for ent in ENTITIES.values():
        if "md_ref" not in ent.columns:
            continue
        for r in store.query(
            f"SELECT id, md_ref FROM {ent.view} "
            "WHERE md_ref IS NOT NULL AND md_ref <> ''"
        ):
            ref = str(r.get("md_ref") or "")
            resolved = resolve_under(root, ref)
            if resolved is None:
                _issue(issues, "error", "md-ref-escape", ent.csv,
                       f"md_ref {ref!r} points outside the data root",
                       row_id=str(r.get("id") or ""))
            elif not resolved.exists():
                _issue(issues, "warning", "md-ref-missing", ent.csv,
                       f"md_ref {ref!r} has no file behind it — "
                       "L2/L3/L4 read as empty", row_id=str(r.get("id") or ""))

    # 5. Vocabulary drift: values the filtered views would silently hide.
    for ent_name, fields in ENUM_FIELDS.items():
        ent = ENTITIES[ent_name]
        for field, allowed in fields.items():
            for r in store.query(
                f"SELECT id, {field} AS v FROM {ent.view} "
                f"WHERE {field} IS NOT NULL AND {field} <> ''"
            ):
                if str(r["v"]) not in allowed:
                    _issue(issues, "warning", "unknown-value", ent.csv,
                           f"{field}={str(r['v'])!r} is outside the known set — "
                           "filtered boards will not show this row",
                           row_id=str(r.get("id") or ""))

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    return {
        "ok": not issues,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checked": {"files": files_checked, "rows": rows_checked},
        "errors": errors,
        "warnings": warnings,
        "truncated": len(issues) >= _MAX_ISSUES,
        "issues": issues,
    }
