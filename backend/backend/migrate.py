"""Schema migration for agent meta.json files.

Scans ``{DATA_ROOT}/projects/**/chats/*/meta.json`` and adds any missing v2
fields with safe defaults:

    l1_headline:      ""
    parent_agent_id:  None
    files_touched:    []
    schema_version:   2

Idempotent: files already at ``schema_version >= 2`` are skipped.
Non-destructive: existing values are never overwritten.

Usage
-----

Dry run (report what *would* change, don't write)::

    python -m backend.migrate --dry-run

Apply migrations::

    python -m backend.migrate

Custom root::

    python -m backend.migrate --root /path/to/projects
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .db import default_data_root
from .file_safety import atomic_write_json, safe_read_json

DEFAULT_ROOT = default_data_root() / "projects"
TARGET_VERSION = 2

# Field name → default value. Order preserved in output for readability.
# Note: l1_headline defaults to "" (not None) — the API's Agent model types
# it as a plain string, and an explicit null would fail validation.
V2_DEFAULTS: List[Tuple[str, Any]] = [
    ("l1_headline", ""),
    ("parent_agent_id", None),
    ("files_touched", []),
    ("schema_version", TARGET_VERSION),
]


@dataclass
class MigrationReport:
    scanned: int = 0
    migrated: int = 0
    skipped_current: int = 0
    skipped_invalid: int = 0
    errors: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"scanned={self.scanned}",
            f"migrated={self.migrated}",
            f"skipped_current={self.skipped_current}",
            f"skipped_invalid={self.skipped_invalid}",
            f"errors={len(self.errors)}",
        ]
        return " ".join(parts)


def _needs_migration(meta: Dict[str, Any]) -> bool:
    """True iff any v2 field is missing OR schema_version < TARGET_VERSION."""
    if meta.get("schema_version", 0) < TARGET_VERSION:
        return True
    return any(key not in meta for key, _ in V2_DEFAULTS)


def _apply_v2_defaults(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict with any missing v2 fields set to defaults.

    Never overwrites existing values (idempotent, non-destructive).
    Deep-copies mutable defaults so callers can't share state.
    """
    out = dict(meta)
    for key, default in V2_DEFAULTS:
        if key not in out:
            # copy mutable defaults so the module-level list is never aliased
            if isinstance(default, list):
                out[key] = list(default)
            elif isinstance(default, dict):
                out[key] = dict(default)
            else:
                out[key] = default
    # Force schema_version up regardless (marks as fully migrated).
    out["schema_version"] = TARGET_VERSION
    return out


def find_meta_files(root: Path) -> List[Path]:
    """Return every ``chats/*/meta.json`` under ``root``, sorted for determinism."""
    if not root.exists():
        return []
    return sorted(root.glob("*/chats/*/meta.json"))


def migrate_file(path: Path, *, dry_run: bool) -> str:
    """Migrate one meta.json. Returns a status string:

    - ``"migrated"``        — write happened (or would have, in dry-run)
    - ``"skipped_current"`` — already at v2, nothing missing
    - ``"invalid"``         — could not parse
    """
    try:
        meta = safe_read_json(path)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "invalid"

    if not isinstance(meta, dict):
        return "invalid"

    if not _needs_migration(meta):
        return "skipped_current"

    new_meta = _apply_v2_defaults(meta)
    if new_meta == meta:  # defensive: nothing actually changed
        return "skipped_current"

    if not dry_run:
        atomic_write_json(path, new_meta)
    return "migrated"


def run(root: Path, *, dry_run: bool) -> MigrationReport:
    report = MigrationReport()
    for meta_path in find_meta_files(root):
        report.scanned += 1
        try:
            status = migrate_file(meta_path, dry_run=dry_run)
        except Exception as exc:  # pragma: no cover — defensive top-level
            report.errors.append(f"{meta_path}: {exc}")
            continue

        if status == "migrated":
            report.migrated += 1
            report.changed_files.append(str(meta_path))
        elif status == "skipped_current":
            report.skipped_current += 1
        elif status == "invalid":
            report.skipped_invalid += 1
            report.errors.append(f"{meta_path}: unparseable")
    return report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backend.migrate",
        description="Backfill v2 fields on meta.json files (idempotent).",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"projects root (default: {DEFAULT_ROOT})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change; do not write",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="list each changed file",
    )
    return p


def main(argv: List[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run(args.root, dry_run=args.dry_run)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}{report.summary()}")
    if args.verbose:
        for path in report.changed_files:
            print(f"  {prefix}migrated: {path}")
    for err in report.errors:
        print(f"  error: {err}", file=sys.stderr)

    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
