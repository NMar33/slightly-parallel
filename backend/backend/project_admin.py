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

Every folder and file goes to the trash by one ``os.rename`` (the trash is
inside the data root, so on its volume), never ``shutil.move``: its
fallback copies, then deletes, and a delete that stops partway (Windows, a
handle open inside the folder) leaves the live project half deleted behind
a full copy in the trash (tk_dc394600). The renames come first, before any
ledger row moves; the first that fails puts back what was moved, newest
first, and the delete is refused in one line naming the path and the state
(``DeleteRefused``), as the backup restore's swap does.
"""

from __future__ import annotations

import errno
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from . import chatstore
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


def _volume(path: Path) -> int:
    return os.lstat(path).st_dev


def _rename(src: Path, dst: Path) -> None:
    """One rename into the trash; raises ``OSError`` and moves nothing when
    it cannot. Never a copy: the trash is on the data root's volume, and a
    path that is not (a mount inside the data root) is refused, not copied."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _volume(src) != _volume(dst.parent):
        raise OSError(errno.EXDEV, "it is on another volume than the trash", str(src))
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(errno.EEXIST, "the trash holds that path already", str(dst))
    os.rename(src, dst)


def _archive_file(data_root: Path, trash: Path, rel: str) -> bool:
    """A file that arrived after the delete's renames (a row written in
    between): one rename, or it stays whole where it is."""
    src = resolve_under(data_root, rel)
    if src is None or not src.exists():
        return False
    try:
        _rename(src, trash / rel)
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


def _header(path: Path) -> tuple[str, ...]:
    import csv as _csv
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return tuple(c.strip() for c in next(_csv.reader(fh), []))
    except (OSError, UnicodeDecodeError):
        return ()


def _archive_folder(data_root: Path, trash: Path, rel: str) -> bool:
    """``_archive_file`` for a folder."""
    src = data_root / rel
    if not src.is_dir():
        return False
    try:
        _rename(src, trash / rel)
    except OSError:
        return False
    return True


class DeleteRefused(Exception):
    """A rename into the trash failed: the delete stopped and put back what
    it had moved. 409 when everything is back in place, 500 when not."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class _Renames:
    """The first phase of a delete: every folder and file of the project,
    each by one rename into the trash. The first that fails puts the others
    back, newest first, and raises ``DeleteRefused``."""

    def __init__(self, trash: Path, code: str) -> None:
        self.trash = trash
        self.code = code
        self.done: list[tuple[Path, Path, str]] = []   # (where it was, where it is, rel)

    def move(self, src: Path | None, rel: str) -> bool:
        if src is None or not (src.exists() or src.is_symlink()):
            return False
        dst = self.trash / rel
        try:
            _rename(src, dst)
        except OSError as e:
            self.refuse(rel, e.strerror or str(e))
        self.done.append((src, dst, rel))
        return True

    def back(self) -> list[tuple[Path, Path, str]]:
        """Put back what moved, newest first; returns what could not go back."""
        left = []
        for src, dst, rel in reversed(self.done):
            try:
                if src.exists() or src.is_symlink():
                    # Something was written there since: never rename over it.
                    raise FileExistsError(errno.EEXIST, "written again since", str(src))
                os.rename(dst, src)
            except OSError:
                left.append((src, dst, rel))
        self.done = []
        if not left:
            for folder, _dirs, _files in os.walk(self.trash, topdown=False):
                try:
                    os.rmdir(folder)   # only the empty folders the delete made
                except OSError:
                    pass
        return left

    def refuse(self, rel: str, reason: str) -> NoReturn:
        left = self.back()
        head = f"Delete of {self.code} refused: {rel} could not move to the trash ({reason})"
        if not left:
            raise DeleteRefused(409, f"{head}; nothing deleted, everything is where it was. "
                                     "Close what holds it open (a running agent) and try again.")
        where = "; ".join(f"{r} is at {d}" for _s, d, r in left)
        raise DeleteRefused(500, f"{head}, and {len(left)} of what had moved could not be put back: "
                                 f"{where}. Move those back by hand; everything else is where it was.")


def _rename_all(data_root: Path, code: str, r: _Renames) -> dict[str, int]:
    """Every folder and file the delete takes, renamed into the trash in the
    order the ledgers name them, before any ledger row moves. Returns the
    counts by kind (the keys of the delete's ``moved``)."""
    counts: dict[str, int] = {}

    def bump(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def is_project(row: dict[str, str]) -> bool:
        return str(row.get("project") or "") == code

    def doc(row: dict[str, str], key: str = "detail_docs", col: str = "md_ref") -> None:
        rel = str(row.get(col) or "")
        if r.move(resolve_under(data_root, rel), rel):
            bump(key)

    def versions(row: dict[str, str]) -> None:
        rid = str(row.get("id") or "")
        if not rid:
            return
        for rel in (f"{VERSIONS_DIR}/{rid}.md", f"{VERSIONS_DIR}/{rid}"):
            if r.move(data_root / rel, rel):
                bump("kept_versions")

    def folder(rel: str, key: str) -> None:
        if (data_root / rel).is_dir() and r.move(data_root / rel, rel):
            bump(key)

    if r.move(data_root / "projects" / code, f"projects/{code}"):
        bump("projects_folder")
    for row in read_rows(data_root / "scans.csv"):
        if is_project(row):
            doc(row)
    owned: dict[str, set[str]] = {}
    for ent in ENTITIES.values():
        if ent.name == "sprint":
            continue
        for row in read_rows(data_root / ent.csv):
            if is_project(row):
                owned.setdefault(ent.name, set()).add(str(row.get("id") or ""))
                doc(row)
                versions(row)
    tasks = sorted(owned.get("task", set()) - {""})
    for tid in tasks:
        folder(f"task_evidence/{tid}", "task_evidence_folders")
    for tid in tasks:
        folder(f"task_story/{tid}", "task_story_folders")
    for row in read_rows(data_root / "story_images.csv"):
        if is_project(row):
            doc(row, "story_image_files", "path")
    for row in read_rows(data_root / ENTITIES["sprint"].csv):
        members = [p.strip() for p in str(row.get("projects") or "").split(",") if p.strip()]
        if members and set(members) == {code}:
            doc(row)
            versions(row)
    cards = sorted(owned.get("publish", set()) - {""})
    notes = sorted(owned.get("note", set()) - {""})
    eps = sorted(owned.get("entrypoint", set()) - {""})
    for rel in ([f"note_details/{i}" for i in notes] + [f"note_images/{i}" for i in notes]
                + [f"entrypoint_shots/{i}" for i in eps] + [f"publish_images/{i}" for i in cards]
                + [f"publish_files/{i}" for i in cards] + [f"publish_context/{i}" for i in cards]):
        folder(rel, "side_folders")
    return counts


def _sweep_side_ledgers(data_root: Path, trash: Path, code: str, owned: dict[str, set[str]],
                        task_ids: set[str], moved: dict[str, int]) -> None:
    """The ledgers that hang off a note, an entry point, a publish card or
    document, or a core, and the project's own rows of the newer ledgers,
    go with the project: left behind, a restored archive (the example
    project is built that way) lost every note's text and pictures, every
    topic's ways in and stops, and a deleted project's rows stayed on disk.
    The ledgers are read with their own header, so a column added later
    travels too."""
    notes = owned.get("note", set())
    eps = owned.get("entrypoint", set())
    cards = owned.get("publish", set())

    def project_ids(name: str) -> set[str]:
        return {str(r.get("id") or "") for r in read_rows(data_root / name)
                if str(r.get("project") or "") == code}

    publish_docs = project_ids("publish_docs.csv")
    cores = project_ids("cores.csv")
    is_project = lambda r: str(r.get("project") or "") == code  # noqa: E731

    def by(key: str, ids: set[str]):
        return lambda r: str(r.get(key) or "") in ids

    plan: list[tuple[str, Any]] = [
        ("note_versions.csv", by("note_id", notes)),
        ("note_images.csv", by("note_id", notes)),
        ("note_marks.csv", by("note_id", notes)),
        ("note_comments.csv", by("note_id", notes)),
        ("entrypoint_ways.csv", by("entrypoint_id", eps)),
        ("entrypoint_stops.csv", by("entrypoint_id", eps)),
        ("entrypoint_shots.csv", by("entrypoint_id", eps)),
        ("entrypoint_versions.csv", by("entrypoint_id", eps)),
        ("entrypoint_names.csv", by("entrypoint_id", eps)),
        ("task_topics.csv", lambda r: str(r.get("task_id") or "") in task_ids
         or str(r.get("entrypoint_id") or "") in eps),
        ("entrypoint_commands.csv", is_project),
        ("entrypoint_asks.csv", is_project),
        ("publish_docs.csv", is_project),
        ("publish_versions.csv", by("doc_id", publish_docs)),
        ("publish_items.csv", lambda r: str(r.get("doc_id") or "") in publish_docs
         or str(r.get("card_id") or "") in cards),
        ("publish_attachments.csv", by("card_id", cards)),
        ("publish_sources.csv", by("card_id", cards)),
        ("publish_writes.csv", by("card_id", cards)),
        ("cores.csv", is_project),
        ("core_notes.csv", by("core_id", cores)),
        ("core_links.csv", by("core_id", cores)),
        ("core_events.csv", by("core_id", cores)),
        ("commit_links.csv", by("task_id", task_ids)),
        ("carry_briefs.csv", is_project),
        ("messages.csv", is_project),
        ("task_titles.csv", by("task_id", task_ids)),
        ("now.csv", is_project),
        ("next_tasks.csv", is_project),
    ]
    for name, belongs in plan:
        cols = _header(data_root / name)
        if not cols:
            continue
        n = _split_rows(data_root, trash, name, cols, belongs)
        if n:
            moved[name.removesuffix(".csv")] = n
    folders = 0
    for rel in ([f"note_details/{i}" for i in sorted(notes)] + [f"note_images/{i}" for i in sorted(notes)]
                + [f"entrypoint_shots/{i}" for i in sorted(eps)] + [f"publish_images/{i}" for i in sorted(cards)]
                + [f"publish_files/{i}" for i in sorted(cards)] + [f"publish_context/{i}" for i in sorted(cards)]):
        if _archive_folder(data_root, trash, rel):
            folders += 1
    if folders:
        moved["side_folders"] = folders


class ProjectHeld(Exception):
    """Rule 1 of a project delete (tk_d1d25a4d, note nt_9de63b9e §5): the
    project holds the chat folder of an agent that is a member elsewhere."""

    def __init__(self, code: str, held: list[dict[str, Any]]) -> None:
        self.code = code
        self.held = held
        listed = ", ".join(f"{h['agent_id']} (also in {', '.join(h['also_in'])})" for h in held)
        first = held[0]
        self.detail = (
            f"Project {code} holds chats of agents that are members elsewhere: {listed}. "
            f"Move the chat of {first['agent_id']} to {first['also_in'][0]}? / "
            "Make them leave the other projects first?"
        )
        super().__init__(self.detail)


def memberships_unreadable() -> type[Exception]:
    from .memberships import LedgerUnreadable
    return LedgerUnreadable


def held_by_project(data_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Per project, the agents whose chat folder is there and that joined
    other projects, each with those projects (rule 1 of a delete). One read
    of the ledger and one walk of the chats for every project; only the
    metas of agents the ledger names are read."""
    from . import membership_fold as mf
    from . import memberships
    rows, cut = memberships.read_ledger(data_root)
    named = {str(r.get("agent_id") or "") for r in rows} - {""}
    if not named:
        return {}
    existing = memberships.existing_codes(data_root)
    folders: dict[str, list[str]] = {}      # agent → the projects of its folders
    origins: dict[str, list[str]] = {}      # agent → the projects its metas name
    for proj, agent, folder in chatstore.iter_chats(data_root, has="meta.json"):
        if agent in named:
            folders.setdefault(agent, []).append(proj)
            origin = chatstore.project_of(folder)
            if origin not in origins.setdefault(agent, []):
                origins[agent].append(origin)
    out: dict[str, list[dict[str, Any]]] = {}
    for agent, projs in folders.items():
        fold = mf.fold([r for r in rows if r.get("agent_id") == agent], existing,
                       {agent: tuple(origins[agent])}, cut)
        for code in dict.fromkeys(projs):
            also = [c for c in fold.joined(agent) if c != code]
            if also:
                out.setdefault(code, []).append({"agent_id": agent, "also_in": also})
    return out


def held_elsewhere(data_root: Path, code: str) -> list[dict[str, Any]]:
    """``held_by_project`` for one project (the delete calls it under the
    ledger's lock)."""
    return held_by_project(data_root).get(code, [])


def members_from_elsewhere(data_root: Path, code: str) -> list[str]:
    """The agents that joined ``code`` from another origin."""
    from . import membership_fold as mf
    from . import memberships
    rows, cut = memberships.read_ledger(data_root)
    existing = memberships.existing_codes(data_root)
    out = []
    for agent in dict.fromkeys(str(r.get("agent_id") or "") for r in rows):
        if not agent:
            continue
        origins = tuple(dict.fromkeys(o for o, _f, _m in memberships.chats_on_disk(data_root, agent)))
        if code in origins:
            continue
        fold = mf.fold([r for r in rows if r.get("agent_id") == agent], existing, {agent: origins}, cut)
        if code in fold.joined(agent):
            out.append(agent)
    return out


def delete_project_data(store: ViewStore, code: str) -> dict[str, Any]:
    """Archive everything the project owns; returns what moved and where.

    The membership ledger's lock is held from the check through the move to
    the trash (tk_d1d25a4d): a join of this project waits, then finds it
    gone; a join elsewhere by one of its chats either lands first, and the
    delete is refused, or finds the chat gone. Rule 1 refuses the delete
    while the project holds the chat of an agent that is a member elsewhere
    (``ProjectHeld``); rule 2 writes a ``leave`` for each member from
    elsewhere, value «project deleted». The ledger keeps its rows: a
    restored project re-joins nobody. A leave needs the project to exist,
    so the leaves come before the renames; a delete then refused
    (``DeleteRefused``) writes each of those agents a ``join`` back, value
    «project delete refused»."""
    from . import membership_fold as mf
    from . import memberships
    data_root = store.data_root
    with memberships.locked(data_root):
        held = held_elsewhere(data_root, code)
        if held:
            raise ProjectHeld(code, held)
        left = []
        for agent in members_from_elsewhere(data_root, code):
            memberships.write(data_root, agent, "leave", code, mf.DELETED, held=True)
            left.append(agent)
        # Then the files, all or nothing (DeleteRefused names a failure),
        # then the ledger rows.
        trash = data_root / TRASH_DIR / f"{code}-{_stamp()}"
        trash.mkdir(parents=True, exist_ok=True)
        renames = _Renames(trash, code)
        try:
            counts = _rename_all(data_root, code, renames)
        except DeleteRefused as refused:
            missed = _rejoin(data_root, code, left)
            if missed:
                refused.detail += f" {', '.join(missed)} left {code} and could not join it again."
                refused.args = (refused.detail,)
            raise
        except BaseException:
            renames.back()
            _rejoin(data_root, code, left)
            raise
        out = _delete_project_data(store, code, trash, counts)
    if left:
        out["left"] = left
    return out


#: The value of the join that undoes a leave of a delete that was refused.
REJOINED = "project delete refused"


def _rejoin(data_root: Path, code: str, agents: list[str]) -> list[str]:
    """The members from elsewhere that left ``code`` for a delete that was
    then refused join it again (the ledger is append-only: a leave, then a
    join). Returns the agents whose join could not be written."""
    from . import memberships
    missed = []
    for agent in agents:
        try:
            memberships.write(data_root, agent, "join", code, REJOINED, held=True)
        except Exception:  # noqa: BLE001 - named in the refusal instead
            missed.append(agent)
    return missed


def _delete_project_data(store: ViewStore, code: str, trash: Path,
                         renamed: dict[str, int]) -> dict[str, Any]:
    """The ledger rows, after ``_rename_all`` moved the files (``renamed``
    counts them); the caller holds the membership ledger's lock. A file that
    a row written in between names goes by one rename too, or stays whole
    where it is."""
    data_root = store.data_root
    moved: dict[str, int] = {k: n for k, n in renamed.items()
                             if k in ("projects_folder", "task_evidence_folders", "task_story_folders")}
    docs = renamed.get("detail_docs", 0)
    versions = renamed.get("kept_versions", 0)

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
        if _archive_folder(data_root, trash, f"{VERSIONS_DIR}/{rid}"):
            versions += 1

    def keep_all(row: dict[str, str]) -> None:
        keep_doc(row)
        keep_versions(row)

    # The chats folder — capture's home — went first, in _rename_all.

    # Scans have their own ledger and detail folder.
    moved["scans"] = _split_rows(
        data_root, trash, "scans.csv", _SCAN_COLUMNS, is_project, keep_doc
    )

    task_ids: set[str] = set()
    # The ids of the rows moved, by entity: their side ledgers follow them (below).
    owned_ids: dict[str, set[str]] = {}
    for ent in ENTITIES.values():
        if ent.name == "sprint":
            continue  # membership only, below

        def belongs(r, _ent=ent):
            if is_project(r):
                owned_ids.setdefault(_ent.name, set()).add(str(r.get("id") or ""))
                if _ent.name == "task":
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
        # Their evidence images and the story prompts and images kept per
        # task (story_release.STORY_DIR) went in _rename_all; a task written
        # since takes its folders here, or leaves them whole in place.
        for key, base in (("task_evidence_folders", "task_evidence"), ("task_story_folders", "task_story")):
            n = sum(_archive_folder(data_root, trash, f"{base}/{tid}") for tid in sorted(task_ids))
            if n:
                moved[key] = moved.get(key, 0) + n

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
    images = renamed.get("story_image_files", 0)

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

    _sweep_side_ledgers(data_root, trash, code, owned_ids, task_ids, moved)
    if renamed.get("side_folders"):
        moved["side_folders"] = moved.get("side_folders", 0) + renamed["side_folders"]

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
        chats = pf.chats_root
        if chats is not None:
            bump(pf.code, "chats", len(chatstore.folders_in(chats)))
    for csv_name in [e.csv for e in ENTITIES.values()] + ["scans.csv"]:
        for r in read_rows(store.data_root / csv_name):
            for code in str(r.get("project") or "").split(","):
                bump(code.strip(), "rows")
    # The agents whose chat holds a project back from a delete (rule 1,
    # tk_d1d25a4d), each with the projects its chat can move to.
    try:
        held = held_by_project(store.data_root)
    except memberships_unreadable():
        held = {}
    for entry in codes.values():
        entry["held"] = held.get(entry["code"], [])
    return sorted(codes.values(), key=lambda c: c["code"])
