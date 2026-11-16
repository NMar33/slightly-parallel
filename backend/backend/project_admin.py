"""Removing a project — two different verbs.

*Disconnect* stops observing: the registry row, the capture hooks, the
OpenCode plugin, the fenced ``AGENTS.md`` block and the ``CLAUDE.md`` bridge
line go; the project's files are otherwise untouched and its data stays
(a project exists in Slightly Parallel by its data, not by its registration).

*Delete data* is the destructive one, so it archives instead of erasing:
``projects/<code>/`` and every row of the project in every ledger — with
their detail documents — move to ``<data_root>/.trash/<code>-<stamp>/``,
preserving relative paths, so one bad click is recoverable by moving the
folder back. Sprints spanning several projects only lose the membership.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .csvio import append_row, read_rows, rewrite_rows
from .db import ViewStore
from .docs_md import resolve_under
from .entities import (
    AGENT_LINK_COLUMNS, CALENDAR_ENTRY_COLUMNS, DOC_COLUMNS, DOC_ITEM_COLUMNS,
    DOC_VERSION_COLUMNS, ENTITIES, MILESTONE_COLUMNS, MILESTONE_TASK_COLUMNS,
    STORY_IMAGE_COLUMNS, STORY_REQUEST_COLUMNS, TASK_EVENT_COLUMNS, TASK_EVIDENCE_COLUMNS,
    TASK_LINK_COLUMNS, TASK_NOTE_COLUMNS,
)
from .file_safety import write_in_place
from .keeplib import VERSIONS_DIR

_SCAN_COLUMNS = (
    "id", "created_date", "created_time", "project", "agent_id",
    "l1", "files_n", "lines_add", "lines_del", "decisions_n",
    "scope", "md_ref",
)
TRASH_DIR = ".trash"


# ---------------------------------------------------------------------------
# Disconnect helpers (file edits in the project folder)
# ---------------------------------------------------------------------------

def remove_block(existing: str, begin: str, end: str) -> tuple[str, str]:
    """Strip the fenced block; returns (new_text, action)."""
    if begin not in existing or end not in existing:
        return existing, "unchanged"
    start = existing.index(begin)
    stop = existing.index(end) + len(end)
    before, after = existing[:start].rstrip("\n"), existing[stop:].lstrip("\n")
    if before and after:
        new = before + "\n\n" + after
    else:
        new = before + after
    if new and not new.endswith("\n"):
        new += "\n"
    return new, "removed"


def remove_bridge(existing: str, bridge: str) -> tuple[str, str]:
    lines = existing.splitlines()
    kept = [ln for ln in lines if ln.strip() != bridge]
    if len(kept) == len(lines):
        return existing, "unchanged"
    new = "\n".join(kept)
    if new.strip():
        new = new.rstrip("\n") + "\n"
    else:
        new = ""
    return new, "removed"


def strip_file(path: Path, transform) -> str:
    """Apply ``transform(text) -> (new, action)``; delete the file when it ends
    up blank (Setup created it, so nothing of the user's is lost)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "absent"
    new, action = transform(text)
    if action == "unchanged":
        return action
    try:
        if not new.strip():
            path.unlink()
            return "deleted"
        write_in_place(path, new)  # the operator's own file: never half written, links kept
    except (OSError, UnicodeDecodeError):
        return "unwritable"
    return action


# ---------------------------------------------------------------------------
# Delete data (archive to trash)
# ---------------------------------------------------------------------------

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _archive_file(data_root: Path, trash: Path, rel: str) -> bool:
    src = resolve_under(data_root, rel)
    if src is None or not src.exists():
        return False
    dst = trash / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
    except OSError:
        return False
    return True


def _split_rows(
    data_root: Path, trash: Path, csv_name: str, columns: tuple[str, ...],
    belongs, on_removed=None,
) -> int:
    """Move rows where ``belongs(row)`` into ``trash/<csv_name>``; return count."""
    csv_path = data_root / csv_name
    if not csv_path.exists():
        return 0
    removed: list[dict[str, str]] = []

    def mutate(rows: list[dict[str, str]]) -> bool:
        keep = []
        for r in rows:
            (removed if belongs(r) else keep).append(r)
        if not removed:
            return False
        # Into the trash first: a write that fails there raises before the
        # ledger is rewritten, so a row is never in neither place.
        for r in removed:
            append_row(trash / csv_name, columns, r)
        rows[:] = keep
        return True

    rewrite_rows(csv_path, columns, mutate)
    if on_removed:
        for r in removed:
            on_removed(r)
    return len(removed)


def delete_project_data(store: ViewStore, code: str) -> dict[str, Any]:
    """Archive everything the project owns; returns what moved and where."""
    data_root = store.data_root
    trash = data_root / TRASH_DIR / f"{code}-{_stamp()}"
    trash.mkdir(parents=True, exist_ok=True)
    moved: dict[str, int] = {}
    docs = 0
    versions = 0

    def keep_doc(row: dict[str, str]) -> None:
        nonlocal docs
        if _archive_file(data_root, trash, str(row.get("md_ref") or "")):
            docs += 1

    is_project = lambda r: str(r.get("project") or "") == code  # noqa: E731

    def keep_versions(row: dict[str, str]) -> None:
        """The kept versions of an entry go with the entry.

        They live flat at the data root (``kept_versions/<id>.md`` and the
        skill's files under ``kept_versions/<id>/``), not inside
        ``projects/<code>/``, so archiving the project folder never took
        them. A deleted project used to leave every interpretation of its
        rules and problems on disk forever, with nothing pointing at them.
        """
        nonlocal versions
        rid = str(row.get("id") or "")
        if not rid:
            return
        if _archive_file(data_root, trash, f"{VERSIONS_DIR}/{rid}.md"):
            versions += 1
        folder = data_root / VERSIONS_DIR / rid
        if folder.is_dir():
            dest = trash / VERSIONS_DIR / rid
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(folder), str(dest))
                versions += 1
            except OSError:
                pass

    def keep_all(row: dict[str, str]) -> None:
        keep_doc(row)
        keep_versions(row)

    # The chats folder — capture's home.
    proj_dir = data_root / "projects" / code
    if proj_dir.exists():
        shutil.move(str(proj_dir), str(trash / "projects" / code))
        moved["projects_folder"] = 1

    # Scans have their own ledger and detail folder.
    moved["scans"] = _split_rows(
        data_root, trash, "scans.csv", _SCAN_COLUMNS, is_project, keep_doc
    )

    task_ids: set[str] = set()
    for ent in ENTITIES.values():
        if ent.name == "sprint":
            continue  # membership only, below

        def belongs(r, _ent=ent):
            if _ent.name == "task" and is_project(r):
                task_ids.add(str(r.get("id") or ""))
            return is_project(r)

        n = _split_rows(data_root, trash, ent.csv, ent.columns, belongs, keep_all)
        if n:
            moved[ent.list_key] = n

    if task_ids:
        moved["task_events"] = _split_rows(
            data_root, trash, "task_events.csv", TASK_EVENT_COLUMNS,
            lambda r: str(r.get("task_id") or "") in task_ids,
        )
        # Everything else that hangs off a task goes with it: links either
        # way, notes, and evidence rows with their image files.
        moved["task_links"] = _split_rows(
            data_root, trash, "task_links.csv", TASK_LINK_COLUMNS,
            lambda r: str(r.get("from_id") or "") in task_ids or str(r.get("to_id") or "") in task_ids,
        )
        moved["task_notes"] = _split_rows(
            data_root, trash, "task_notes.csv", TASK_NOTE_COLUMNS,
            lambda r: str(r.get("task_id") or "") in task_ids,
        )
        moved["task_evidence"] = _split_rows(
            data_root, trash, "task_evidence.csv", TASK_EVIDENCE_COLUMNS,
            lambda r: str(r.get("task_id") or "") in task_ids,
        )
        evidence_moved = 0
        for tid in sorted(task_ids):
            folder = data_root / "task_evidence" / tid
            if folder.is_dir():
                dest = trash / "task_evidence" / tid
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(folder), str(dest))
                except (OSError, UnicodeDecodeError):
                    continue  # left in place, as a detail document that will not move is
                evidence_moved += 1
        if evidence_moved:
            moved["task_evidence_folders"] = evidence_moved
        # The story prompts and images of the project's tasks, kept per task
        # (story_release.STORY_DIR): left behind, they outlived the task.
        story_moved = 0
        for tid in sorted(task_ids):
            folder = data_root / "task_story" / tid
            if folder.is_dir():
                dest = trash / "task_story" / tid
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(folder), str(dest))
                except (OSError, UnicodeDecodeError):
                    continue
                story_moved += 1
        if story_moved:
            moved["task_story_folders"] = story_moved

    # The side ledgers that carry the project: the operator's dates and
    # milestones, agent links, story requests and storyboard documents,
    # with the rows that hang off a milestone or a document. Left behind,
    # they stayed on the pages, and the project dropped out of the list a
    # second delete is made from.
    for name, cols in (("calendar_entries.csv", CALENDAR_ENTRY_COLUMNS),
                       ("agent_links.csv", AGENT_LINK_COLUMNS),
                       ("story_requests.csv", STORY_REQUEST_COLUMNS)):
        n = _split_rows(data_root, trash, name, cols, is_project)
        if n:
            moved[name.removesuffix(".csv")] = n
    doc_ids: set[str] = set()
    milestone_ids: set[str] = set()

    def owned(ids: set[str]):
        def belongs(r: dict[str, str]) -> bool:
            if is_project(r):
                ids.add(str(r.get("id") or ""))
                return True
            return False
        return belongs

    for name, cols, ids in (("docs.csv", DOC_COLUMNS, doc_ids),
                            ("milestones.csv", MILESTONE_COLUMNS, milestone_ids)):
        n = _split_rows(data_root, trash, name, cols, owned(ids))
        if n:
            moved[name.removesuffix(".csv")] = n
    for name, cols in (("doc_items.csv", DOC_ITEM_COLUMNS), ("doc_versions.csv", DOC_VERSION_COLUMNS)):
        if doc_ids:
            _split_rows(data_root, trash, name, cols, lambda r: str(r.get("doc_id") or "") in doc_ids)
    if milestone_ids or task_ids:
        _split_rows(data_root, trash, "milestone_tasks.csv", MILESTONE_TASK_COLUMNS,
                    lambda r: str(r.get("milestone_id") or "") in milestone_ids
                    or str(r.get("task_id") or "") in task_ids)

    # Story images live flat too (``task_story/<task_id>/`` named by each
    # row's ``path``), so the ledger rows and their files are swept by
    # project rather than carried along by the project folder.
    images = 0

    def keep_image(row: dict[str, str]) -> None:
        nonlocal images
        if _archive_file(data_root, trash, str(row.get("path") or "")):
            images += 1

    moved["story_images"] = _split_rows(
        data_root, trash, "story_images.csv", STORY_IMAGE_COLUMNS, is_project, keep_image
    )
    if images:
        moved["story_image_files"] = images

    # Sprints: strip the code from the membership list; a sprint that
    # belonged only to this project is archived like everything else.
    sprint = ENTITIES["sprint"]
    stripped = 0

    def mutate_sprints(rows: list[dict[str, str]]) -> bool:
        nonlocal stripped
        changed = False
        keep = []
        for r in rows:
            members = [p.strip() for p in str(r.get("projects") or "").split(",") if p.strip()]
            if code not in members:
                keep.append(r)
                continue
            rest = [p for p in members if p != code]
            changed = True
            if rest:
                r["projects"] = ",".join(rest)
                keep.append(r)
                stripped += 1
            else:
                append_row(trash / sprint.csv, sprint.columns, r)
                keep_all(r)
                moved["sprints"] = moved.get("sprints", 0) + 1
        rows[:] = keep
        return changed

    if (data_root / sprint.csv).exists():
        rewrite_rows(data_root / sprint.csv, sprint.columns, mutate_sprints)
    if stripped:
        moved["sprints_membership_stripped"] = stripped

    # The operator's marks and #done records name the project too; left
    # behind, a starred message pointed at a chat that was gone.
    from .donelib import DONE_COLUMNS, DONE_CSV
    from .marklib import MARK_COLUMNS, MARKS_CSV
    for name, cols in ((MARKS_CSV, MARK_COLUMNS), (DONE_CSV, DONE_COLUMNS)):
        n = _split_rows(data_root, trash, name, cols, is_project)
        if n:
            moved[name.removesuffix(".csv")] = n

    moved["detail_docs"] = docs
    moved["kept_versions"] = versions
    store.rebuild()
    return {"project": code, "trash": str(trash), "moved": moved}


def restore_project_archive(store: ViewStore, archive: Path) -> dict[str, Any]:
    """Put an archived project back: the reverse of ``delete_project_data``.

    The archive holds the project's rows in ledgers named as at the data
    root, and its files at their relative paths. Rows are appended (a header
    that lacks a column is widened); files are copied where nothing is yet,
    and a file already there is left as it is and counted. The example
    project is built this way: played in a folder of its own, archived
    there, and restored here.
    """
    import csv as _csv

    from .csvio import append_rows_raw

    data_root = store.data_root
    archive = Path(archive)
    rows_in: dict[str, int] = {}
    files = 0
    kept = 0
    for path in sorted(archive.rglob("*")):
        if not path.is_file() or path.suffix == ".lock":
            continue
        rel = path.relative_to(archive)
        if len(rel.parts) == 1 and path.suffix == ".csv":
            with open(path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.reader(fh)
                header = [c.strip() for c in next(reader, [])]
                rows = [r for r in reader if any(r)]
            if not header or not rows:
                continue
            dest = data_root / rel
            if dest.exists() and dest.stat().st_size:
                # Widen the ledger's header first, then append in its order.
                from .csvio import _upgrade_header, acquire_flock, lock_path
                with acquire_flock(lock_path(dest), mode="a"):
                    order = _upgrade_header(dest, header)
                at = {c: i for i, c in enumerate(header)}
                ordered = [[r[at[c]] if c in at and at[c] < len(r) else "" for c in order] for r in rows]
                append_rows_raw(dest, order, ordered)
            else:
                append_rows_raw(dest, header, rows)
            rows_in[rel.name.removesuffix(".csv")] = len(rows)
            continue
        dest = data_root / rel
        if dest.exists():
            kept += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        files += 1
    store.rebuild()
    return {"rows": rows_in, "files": files, "already_there": kept}


def known_projects(store: ViewStore) -> list[dict[str, Any]]:
    """Every project code Slightly Parallel knows about — from data folders and from
    ledger rows — with a rough size, so the UI can offer deletion for
    projects that were never registered (test leftovers, imports)."""
    codes: dict[str, dict[str, Any]] = {}

    def bump(code: str, key: str, n: int = 1) -> None:
        if not code:
            return
        entry = codes.setdefault(code, {"code": code, "chats": 0, "rows": 0})
        entry[key] += n

    for pf in store.projects:
        bump(pf.code, "chats", 0)
        chats = pf.chats_dir
        if chats is not None:
            bump(pf.code, "chats", sum(1 for d in chats.iterdir() if d.is_dir()))
    for csv_name in [e.csv for e in ENTITIES.values()] + ["scans.csv"]:
        for r in read_rows(store.data_root / csv_name):
            for code in str(r.get("project") or "").split(","):
                bump(code.strip(), "rows")
    return sorted(codes.values(), key=lambda c: c["code"])
