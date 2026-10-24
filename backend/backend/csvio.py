"""CSV read/append/rewrite primitives for the mutual tables.

Concurrency model: every mutating operation on ``<table>.csv`` takes an
exclusive ``flock`` on a *sidecar* lock file (``<table>.csv.lock``). The lock
file is never replaced, so the lock stays meaningful across the
write-temp-then-rename pattern used by :func:`rewrite_rows` — locking the data
file itself would leave a second writer holding a lock on a deleted inode.
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import file_safety
from .file_safety import acquire_flock


def lock_path(csv_path: Path) -> Path:
    return csv_path.with_name(csv_path.name + ".lock")


def csv_escape(value: Any) -> str:
    """RFC-4180 minimal-quoting single-field encoder."""
    if value is None:
        return ""
    s = str(value)
    if any(ch in s for ch in (",", '"', "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


class DamagedFile(Exception):
    """A ledger that cannot be read row for row: rewriting it from what was
    read would lose the rows it hides. The server answers 409 with this text."""


def swallowed_rows(csv_path: Path) -> list[int]:
    """Lines where a quote left open makes the reader take the next rows as
    part of one field: the record numbers (the header is 1) whose fields hold
    whole rows of this file. Empty when the file reads row for row, and for a
    file with no ``id`` column (nothing to tell a row from prose by).

    A text field may hold line breaks and commas — a note's paragraphs do.
    It does not hold a line that parses into as many fields as the header
    and starts with an id of this file's kind (``tk_…``, ``nt_…``).
    """
    if not csv_path.exists():
        return []
    out: list[int] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = [c.strip() for c in next(reader, [])]
        if len(header) < 4 or "id" not in header:
            return []
        width, at = len(header), header.index("id")
        kinds: set[str] = set()
        try:
            for n, row in enumerate(reader, start=2):
                if at < len(row) and "_" in row[at]:
                    kinds.add(row[at].split("_", 1)[0] + "_")
                for field in row:
                    if "\n" not in field:
                        continue
                    for ln in field.split("\n")[1:]:
                        cells = next(csv.reader([ln]), []) if ln.strip() else []
                        if len(cells) >= width - 1 and at < len(cells) and \
                                any(cells[at].startswith(k) and len(cells[at]) > len(k) + 2 for k in kinds):
                            out.append(n)
                            break
                    else:
                        continue
                    break
        except csv.Error:
            out.append(reader.line_num)
    return out


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    """All rows as dicts (empty list if the file is missing)."""
    if not csv_path.exists():
        return []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        # A header cell with spaces around it ("id, title") names the same
        # column as the stripped header the writers use; keyed raw, every
        # r.get("title") read "" and the first rewrite emptied the column.
        rd.fieldnames = [f.strip() for f in rd.fieldnames or []]
        return list(rd)


def append_row(csv_path: Path, columns: Sequence[str], row: dict[str, Any]) -> None:
    """Append one row, writing the header first when the file is new.

    The header check happens *inside* the lock so two concurrent creators
    cannot both write a header.
    """
    with acquire_flock(lock_path(csv_path), mode="a"):
        _append_locked(csv_path, columns, row)


def append_if_absent(
    csv_path: Path,
    columns: Sequence[str],
    row: dict[str, Any],
    same: "Callable[[dict[str, str]], bool] | None" = None,
) -> dict[str, str] | None:
    """Append ``row`` unless the file already holds it; the check and the
    write are one step under the lock.

    ``same`` says which stored row counts as this one (by default: the same
    ``id``). Returns the stored row when there is one — nothing is written —
    and ``None`` when the row was appended. A create that looked first and
    appended after let two identical posts both pass the look.
    """
    if same is None:
        rid = str(row.get("id") or "")
        same = lambda r: r.get("id") == rid  # noqa: E731
    with acquire_flock(lock_path(csv_path), mode="a"):
        for r in read_rows(csv_path):
            if same(r):
                return r
        _append_locked(csv_path, columns, row)
        return None


def _append_locked(csv_path: Path, columns: Sequence[str], row: dict[str, Any]) -> None:
    """The append itself. Caller holds the lock."""
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    cols: list[str] = list(columns)
    if not write_header:
        # The file may predate a schema extension (a column added to the
        # registry). Appending by the registry's order would misalign the
        # row under the old header, so upgrade the header first: existing
        # order kept, new columns appended, every old row padded.
        cols = _upgrade_header(csv_path, columns)
    line = ",".join(csv_escape(row.get(c, "")) for c in cols) + "\n"
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        if write_header:
            fh.write(",".join(cols) + "\n")
        elif _ends_open(csv_path):
            fh.write("\n")
        fh.write(line)
        fh.flush()


def _ends_open(csv_path: Path) -> bool:
    """True when the file's last line has no line break: a file saved by
    hand without one, or an append cut short. The next row written straight
    after it would be glued onto that line."""
    with open(csv_path, "rb") as fh:
        fh.seek(-1, os.SEEK_END)
        return fh.read(1) not in (b"\n", b"\r")


def _upgrade_header(csv_path: Path, columns: Sequence[str]) -> list[str]:
    """Make the file's header a superset of ``columns``; return the file's
    column order to append by. Caller holds the lock."""
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        first = next(csv.reader(fh), [])
    existing = [c.strip() for c in first if c.strip()]
    missing = [c for c in columns if c not in existing]
    if not existing:
        return list(columns)
    if not missing:
        return existing
    merged = existing + missing
    rows = read_rows(csv_path)
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    # Written as rewrite_rows writes: "\n" endings, on disk before the
    # rename, and a rename that waits out a Windows reader.
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=merged, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in merged})
        fh.flush()
        if file_safety.DURABLE:
            os.fsync(fh.fileno())
    file_safety.replace_file(tmp, csv_path)
    return merged


def rewrite_rows(
    csv_path: Path,
    columns: Sequence[str],
    mutate: Callable[[list[dict[str, str]]], bool],
) -> bool:
    """Read-modify-write the whole file under the sidecar lock.

    ``mutate`` receives the row list (dicts) and edits it in place, returning
    True when a change was made. Columns present in the file but missing from
    ``columns`` are preserved, so a rewrite never silently drops data written
    by a newer schema.

    Returns ``mutate``'s result. The read happens inside the lock, so
    concurrent rewrites cannot lose each other's changes.
    """
    with acquire_flock(lock_path(csv_path), mode="a"):
        damaged = swallowed_rows(csv_path)
        if damaged:
            raise DamagedFile(
                f"{csv_path.name} is damaged near record {damaged[0]}: a quote is left open and the rows "
                "after it read as one. Nothing was written. Fix that line (Internals › Run the data check "
                "names it), or restore the file from a backup."
            )
        rows = read_rows(csv_path)
        existing_cols: list[str] = []
        if csv_path.exists():
            with open(csv_path, encoding="utf-8-sig", newline="") as fh:
                first = next(csv.reader(fh), [])
            existing_cols = [c.strip() for c in first if c.strip()]
        fieldnames = list(columns) + [c for c in existing_cols if c not in columns]

        changed = mutate(rows)
        if not changed:
            return False

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

        tmp = csv_path.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(buf.getvalue())
            fh.flush()
            if file_safety.DURABLE:
                os.fsync(fh.fileno())  # the bytes are on disk before the rename points at them
        file_safety.replace_file(tmp, csv_path)
        return True


def append_rows_raw(
    csv_path: Path, columns: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    """Append multiple pre-ordered rows (used by the task-events log)."""
    with acquire_flock(lock_path(csv_path), mode="a"):
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", encoding="utf-8", newline="") as fh:
            if write_header:
                fh.write(",".join(columns) + "\n")
            elif _ends_open(csv_path):
                fh.write("\n")
            for row in rows:
                fh.write(",".join(csv_escape(v) for v in row) + "\n")
            fh.flush()
