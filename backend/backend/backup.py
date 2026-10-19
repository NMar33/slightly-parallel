"""Backups — a rotating copy of the data root, kept outside the data root.

Slightly Parallel's database is a folder of text files. That is what makes it
readable, greppable and diffable by anything; it is also what makes it
deletable by one wrong command. This module takes the whole folder, tars
it, and keeps a dated ladder of the results.

Three properties, in order of how much they matter:

1. **The archive does not need Slightly Parallel.** It is a plain ``.tar.gz`` whose
   single top-level directory is the data root's own folder name. Recovery
   is ``tar -xzf`` — no server, no Python, no schema, no version match. A
   backup only this program can read is a second thing that can fail at
   exactly the worst moment.
2. **The archives live outside the data root.** Inside it they would be
   swept into the next archive, rebuilt through the file watcher on every
   write, and deleted by the very accident they exist for.
3. **Rotation is bounded and by age.** Six rungs — a day, three days, a
   week, two weeks, a month, three months — cut the past into intervals, and
   one archive is kept in each, plus the newest. So there are never more than
   seven automatic archives on disk, and there is always a restore point at
   roughly each of those ages. The one kept in an interval is the *oldest*
   there, so it is the one about to cross into the next rung: every rung is
   fed by the one below it instead of starving behind the boundary.

Three folders are left out (``EXCLUDE_DIRS``): ``tour_shots``, the tour's
page photographs — two thirds of the archive, and two minutes to regenerate —
and ``monitor`` and ``terminal``, this machine's own record and its open
terminals. Everything else goes in.

Manual archives are the operator's own bookmarks: kept by count rather than
by date. A pin overrules the ladder outright — on any archive, of either
kind — and is the one thing rotation will not touch.

Everything here is import-safe and framework-free — the router calls it, and
so does ``scripts/backup.py``, which is what you reach for when the server
is the thing that is broken.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from . import limits
from .file_safety import atomic_write_json

log = logging.getLogger("sp.backup")

ARCHIVE_SUFFIX = ".tar.gz"
SIDECAR_SUFFIX = ".json"
PART_SUFFIX = ".part"

# Lock files are ``fcntl.flock`` handles: zero bytes, meaningless the moment
# they leave this machine.
# ``operator.token`` is this machine's cookie secret for the operator's pages
# (server.OperatorCookie): a restore elsewhere makes its own.
EXCLUDE_GLOBS: tuple[str, ...] = ("*.lock", "operator.token")

# Folders left out wholesale. ``tour_shots`` is the tour's page photographs:
# two thirds of the archive by size, PNGs that gzip barely touches, and
# regenerable in about two minutes by re-running the capture. ``monitor`` is
# the system monitor's samples of this machine and ``terminal`` the registry
# of its open terminals: neither is project data, neither means anything on
# another day. Nothing else
# belongs here — a backup that quietly leaves things out is the class of bug
# this feature exists against, so both lists are reported by the API and
# shown on the page rather than living only in this file.
EXCLUDE_DIRS: tuple[str, ...] = ("tour_shots", "monitor", "terminal")

KINDS = ("auto", "manual")

# One backup operation at a time in this process: the schedule, Back up now,
# a restore, a prune and a trial all read or rewrite the same folders. Re-
# entrant, because a restore takes its safety archive inside its own hold.
# Callers wait; the scheduled run does not wait — it skips a turn (BUSY).
BUSY = threading.RLock()

# Folders a restore leaves beside the archives. ``sp-restore-`` and
# ``sp-trial-`` are unpacking space, removed once stale; ``sp-replaced-``
# holds the data a failed restore could not put back, and ``sp-arrived-``
# what was written into the data root while a failed restore ran: those two
# are the operator's data and are listed, never deleted.
SCRATCH_PREFIXES = ("sp-restore-", "sp-trial-")
KEPT_PREFIXES = ("sp-replaced-", "sp-arrived-")
STALE_SECONDS = 3600

_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(\d{2})(\d{2})__(auto|manual)$")


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rung:
    """One restore point: "the oldest backup younger than this age"."""

    name: str
    age: timedelta


# The ages the operator asked for, and the only ones this feature promises.
# Consecutive rungs cut the past into intervals — [0, a day), [a day, 3 days),
# … — and rotation keeps exactly one archive in each.
RUNGS: tuple[Rung, ...] = (
    Rung("a day", timedelta(days=1)),
    Rung("3 days", timedelta(days=3)),
    Rung("a week", timedelta(days=7)),
    Rung("2 weeks", timedelta(days=14)),
    Rung("a month", timedelta(days=30)),
    Rung("3 months", timedelta(days=90)),
)

DEFAULT_KEEP: dict[str, int] = {"horizon_days": 90, "manual": 10}


def keep_budget(data_root: Path) -> dict[str, int]:
    """The operator's rotation budget from Settings, for every pruner.

    The server's schedule, the page's Back up now and ``scripts/backup.py``
    all prune; one that fell back to the defaults would delete the manual
    archives and the deep restore points the operator asked to keep.
    """
    from . import app_settings

    values = app_settings.load(data_root)
    return {
        "horizon_days": int(values.get("backup.horizon_days", DEFAULT_KEEP["horizon_days"])),
        "manual": int(values.get("backup.keep_manual", DEFAULT_KEEP["manual"])),
    }


# ---------------------------------------------------------------------------
# What one archive is
# ---------------------------------------------------------------------------


@dataclass
class Archive:
    """One ``.tar.gz`` and the sidecar that describes it.

    The sidecar is a convenience, not a dependency: a listing still works
    from the filename and ``stat`` alone, so losing it costs the checksum,
    never the archive.
    """

    name: str                       # 2609-07-1518__manual
    at: datetime
    kind: str                       # auto | manual
    bytes: int = 0
    label: str = ""
    files: int = 0
    sha256: str = ""
    source_bytes: int = 0
    source_files: int = 0
    source_mtime: float = 0.0
    skipped_links: int = 0          # symbolic links in the data root, left out
    pinned: bool = False
    path: Path | None = None
    # Filled in by ``plan_prune``: why this one is being kept.
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "at": self.at.isoformat(timespec="seconds"),
            "kind": self.kind,
            "bytes": self.bytes,
            "label": self.label,
            "files": self.files,
            "sha256": self.sha256,
            "source_bytes": self.source_bytes,
            "source_files": self.source_files,
            "source_mtime": self.source_mtime,
            "skipped_links": self.skipped_links,
            "pinned": self.pinned,
            "reasons": list(self.reasons),
        }


def archive_name(at: datetime, kind: str) -> str:
    """``2609-07-151833__manual`` — Slightly Parallel's YYMM-DD stamp, plus the clock.

    Down to the second: a restore takes a safety archive and then reads the
    one it is restoring, both inside the same call. At minute resolution
    those two collide, and the second one silently becomes the first.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    return f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}-{at:%H%M%S}__{kind}"


def parse_name(name: str) -> tuple[datetime, str] | None:
    """``2609-07-151833__auto`` → (datetime, kind). None when it is not ours."""
    m = _NAME_RE.match(name)
    if not m:
        return None
    ym, day, hh, mm, ss, kind = m.groups()
    try:
        at = datetime(
            2000 + int(ym[:2]), int(ym[2:]), int(day), int(hh), int(mm), int(ss)
        )
    except ValueError:
        return None
    return at, kind


# ---------------------------------------------------------------------------
# Where they live
# ---------------------------------------------------------------------------


def backup_root_for(data_root: Path) -> Path:
    """``SP_BACKUP_ROOT``, else a sibling of the data root.

    A sibling, not a child: same disk (the operator's job to mirror it off
    the machine — that is what download is for), but never inside the folder
    a backup is supposed to survive.
    """
    env = os.environ.get("SP_BACKUP_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (data_root.parent / f"{data_root.name}-backups").resolve()


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


class BackupError(RuntimeError):
    """Something that must stop a backup or a restore, with a reason to show."""


def check_roots(data_root: Path, backup_root: Path) -> None:
    if _is_inside(backup_root, data_root):
        raise BackupError(
            f"the backup root ({backup_root}) is inside the data root — "
            "each archive would swallow the last one; set SP_BACKUP_ROOT"
        )
    if _is_inside(data_root, backup_root):
        raise BackupError(
            f"the data root ({data_root}) is inside the backup root — refusing"
        )


# ---------------------------------------------------------------------------
# Reading the source
# ---------------------------------------------------------------------------


def _excluded(rel: Path) -> bool:
    if rel.parts and rel.parts[0] in EXCLUDE_DIRS:
        return True
    return any(rel.match(g) for g in EXCLUDE_GLOBS)


def walk_source(data_root: Path) -> Iterator[tuple[Path, str]]:
    """Every file to archive, as (absolute path, name inside the tar)."""
    top = data_root.name or "data"
    for path in sorted(data_root.rglob("*")):
        # Symlinks are followed by nothing here: a link is copied as neither
        # its target nor itself, because restoring one would either duplicate
        # data or point at a path that does not exist on the restoring
        # machine. Slightly Parallel data roots are plain trees; this is a corner.
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(data_root)
        if _excluded(rel):
            continue
        yield path, f"{top}/{rel.as_posix()}"


def walk_dirs(data_root: Path) -> Iterator[tuple[Path, str]]:
    """Every directory, so an empty one survives the round trip."""
    top = data_root.name or "data"
    yield data_root, top
    for path in sorted(data_root.rglob("*")):
        if not path.is_dir() or path.is_symlink():
            continue
        rel = path.relative_to(data_root)
        if _excluded(rel):
            continue
        yield path, f"{top}/{rel.as_posix()}"


def skipped_links(data_root: Path) -> list[str]:
    """The symbolic links ``walk_source`` leaves out, as paths inside the
    data root — counted and shown, so the operator knows they are not in
    the archive. Links inside the excluded folders are not counted."""
    out: list[str] = []
    for path in sorted(data_root.rglob("*")):
        if not path.is_symlink():
            continue
        rel = path.relative_to(data_root)
        if not _excluded(rel):
            out.append(rel.as_posix())
    return out


def source_stats(data_root: Path) -> tuple[int, int, float]:
    """(files, bytes, newest mtime) over what would go into an archive."""
    files = 0
    total = 0
    newest = 0.0
    for path, _ in walk_source(data_root):
        try:
            st = path.stat()
        except OSError:
            continue
        files += 1
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return files, total, newest


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def _read_sidecar(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def list_archives(backup_root: Path) -> list[Archive]:
    """Newest first. Built from the filenames, enriched by the sidecars."""
    if not backup_root.is_dir():
        return []
    out: list[Archive] = []
    for path in backup_root.iterdir():
        if not path.name.endswith(ARCHIVE_SUFFIX):   # a ``.part`` is not one yet
            continue
        name = path.name[: -len(ARCHIVE_SUFFIX)]
        parsed = parse_name(name)
        if parsed is None:
            continue
        at, kind = parsed
        try:
            size = path.stat().st_size
        except OSError:
            continue
        side = _read_sidecar(path.with_name(name + SIDECAR_SUFFIX))
        out.append(Archive(
            name=name, at=at, kind=kind, bytes=size, path=path,
            label=str(side.get("label") or ""),
            files=int(side.get("files") or 0),
            sha256=str(side.get("sha256") or ""),
            source_bytes=int(side.get("source_bytes") or 0),
            source_files=int(side.get("source_files") or 0),
            source_mtime=float(side.get("source_mtime") or 0.0),
            skipped_links=int(side.get("skipped_links") or 0),
            pinned=bool(side.get("pinned")),
        ))
    out.sort(key=lambda a: a.at, reverse=True)
    return out


def find(backup_root: Path, name: str) -> Archive | None:
    for a in list_archives(backup_root):
        if a.name == name:
            return a
    return None


# ---------------------------------------------------------------------------
# Rotation — pure, so it can be argued with in a test
# ---------------------------------------------------------------------------


def plan_prune(
    archives: list[Archive], now: datetime, keep: dict[str, int] | None = None,
) -> tuple[list[Archive], list[Archive]]:
    """(keep, drop) — the ladder applied to a listing. Nothing is touched.

    Consecutive rungs cut the past into intervals: younger than a day, one to
    three days, three days to a week, and so on out to the horizon. Rotation
    keeps **the oldest** automatic archive in each interval, plus the newest
    archive overall.

    The oldest, not the newest, and that is the whole trick. An archive ages
    across an interval and then arrives in the next one; keeping the oldest
    means the archive kept in "one to three days" is the one about to become
    the three-days-to-a-week restore point, so each rung is fed by the one
    below it. Keeping the newest in each interval instead looks identical on
    day one and quietly starves every deep rung — the archive that would have
    crossed the boundary is dropped the day before it gets there.

    ``reasons`` is set on every survivor, because "why is this one still
    here" is the question an operator actually asks of a backup list.
    """
    budget = {**DEFAULT_KEEP, **(keep or {})}
    horizon = timedelta(days=max(1, int(budget.get("horizon_days", 90))))
    ordered = sorted(archives, key=lambda a: a.at, reverse=True)
    for a in ordered:
        a.reasons = []

    kept: dict[str, Archive] = {}

    def hold(a: Archive, why: str) -> None:
        kept[a.name] = a
        if why not in a.reasons:
            a.reasons.append(why)

    # A pin is the operator overruling the ladder, and it means the same
    # thing on an automatic archive as on a manual one: this is the state I
    # want to be able to come back to, whatever the rotation thinks.
    for a in ordered:
        if a.pinned:
            hold(a, "pinned")
        elif a.kind == "auto" and a.at > now:
            # Stamped in the future (a clock jump, a hand-copied file): not
            # evidence of anything, so keep it rather than reason about it.
            hold(a, "newer than the clock")

    autos = [a for a in ordered if a.kind == "auto" and a.at <= now]
    if autos:
        hold(autos[0], "newest")

    floor = timedelta(0)
    # A horizon past the last rung gets one more: the setting goes to two
    # years, and every automatic backup older than three months was dropped
    # however far it reached.
    rungs = RUNGS + ((Rung("the horizon", horizon),) if horizon > RUNGS[-1].age else ())
    for rung in rungs:
        if floor >= horizon:
            break
        ceiling = min(rung.age, horizon)
        inside = [a for a in autos if floor <= now - a.at < ceiling]
        if inside:
            hold(inside[-1], rung.name)      # ordered newest first, so [-1] is oldest
        floor = rung.age

    room = int(budget.get("manual", 0))
    for a in ordered:
        if a.kind != "manual" or a.pinned:
            continue
        if room > 0:
            room -= 1
            hold(a, "manual")

    drop = [a for a in ordered if a.name not in kept]
    return [a for a in ordered if a.name in kept], drop


def prune(
    backup_root: Path, now: datetime, keep: dict[str, int] | None = None,
) -> list[str]:
    """Apply the ladder, and remove stale leftovers (``clean_leftovers``).
    Returns the archive names deleted."""
    with BUSY:
        clean_leftovers(backup_root)
        _, drop = plan_prune(list_archives(backup_root), now, keep)
        gone: list[str] = []
        for a in drop:
            if a.path is None:
                continue
            try:
                a.path.unlink(missing_ok=True)
                a.path.with_name(a.name + SIDECAR_SUFFIX).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("could not prune %s: %s", a.name, exc)
                continue
            gone.append(a.name)
        return gone


def clean_leftovers(backup_root: Path, now: float | None = None) -> list[str]:
    """Remove what an interrupted run left in the backup folder and nobody
    will finish: ``.part`` files (an archive or a sidecar being written) and
    the ``sp-restore-`` / ``sp-trial-`` unpacking folders, once older than
    an hour — younger ones may belong to a run still going (the command
    line runs in another process). ``sp-replaced-`` and ``sp-arrived-``
    folders are the operator's data and are left alone (``kept_aside``).
    Returns the names removed."""
    if not backup_root.is_dir():
        return []
    cutoff = (now if now is not None else time.time()) - STALE_SECONDS
    gone: list[str] = []
    for path in backup_root.iterdir():
        try:
            if path.is_symlink() or path.stat().st_mtime > cutoff:
                continue
            if path.is_file() and path.name.endswith(PART_SUFFIX):
                path.unlink()
            elif path.is_dir() and path.name.startswith(SCRATCH_PREFIXES):
                shutil.rmtree(path)
            else:
                continue
        except OSError as exc:
            log.warning("could not remove the leftover %s: %s", path.name, exc)
            continue
        gone.append(path.name)
    if gone:
        log.info("removed %d leftovers from %s: %s", len(gone), backup_root, ", ".join(sorted(gone)))
    return gone


def kept_aside(backup_root: Path) -> list[dict[str, Any]]:
    """The folders a failed restore left with the operator's data in them
    (``sp-replaced-``, ``sp-arrived-``), oldest first: shown, never deleted."""
    if not backup_root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in backup_root.iterdir():
        if path.is_dir() and not path.is_symlink() and path.name.startswith(KEPT_PREFIXES):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            out.append({"name": path.name, "path": str(path),
                        "at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds")})
    return sorted(out, key=lambda d: d["at"])


# ---------------------------------------------------------------------------
# Making one
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_whole(tar: tarfile.TarFile, path: Path, arcname: str) -> tuple[int, float]:
    """Add one file of a live root, read whole before its header is written.

    ``tar.add`` stats the path, writes a header with that size, then opens
    the path and copies that many bytes. On a root the server is writing,
    the file can be replaced (an atomic write) or rewritten shorter between
    the two: the copy then ends early, ``tarfile`` raises with half a member
    already in the stream, and every member after it is unreadable — the
    archive is written, listed and offered as a restore point anyway.

    So the file is opened once, copied to a spool through that one handle,
    and the header is written from what was actually read. A replace after
    the open does not reach the handle; the member is always whole.
    """
    with open(path, "rb") as fh:
        info = tar.gettarinfo(arcname=arcname, fileobj=fh)
        with tempfile.SpooledTemporaryFile(max_size=32 << 20) as spool:
            shutil.copyfileobj(fh, spool, 1 << 20)
            info.size = spool.tell()
            spool.seek(0)
            tar.addfile(info, spool)
    return info.size, float(info.mtime)


def create(
    data_root: Path,
    backup_root: Path,
    *,
    kind: str = "auto",
    label: str = "",
    now: datetime | None = None,
    whole: bool = False,
) -> Archive:
    """Tar the data root into ``backup_root``. Returns the finished archive.

    ``whole``: every file or none — a file that is there and cannot be read
    refuses the archive, naming it. The safety archive before a restore is
    taken so: it skipped such a file with a line in the log, and the restore
    then deleted the original.

    Written as ``<name>.tar.gz.part`` and renamed only once it is complete
    and hashed, so an interrupted run leaves no half archive that a later
    listing would offer as a restore point.
    """
    with BUSY:
        return _create(data_root, backup_root, kind=kind, label=label, now=now, whole=whole)


def _create(data_root: Path, backup_root: Path, *, kind: str, label: str, now: datetime | None,
            whole: bool = False) -> Archive:
    if not data_root.is_dir():
        raise BackupError(f"data root does not exist: {data_root}")
    check_roots(data_root, backup_root)
    at = now or datetime.now()
    backup_root.mkdir(parents=True, exist_ok=True)

    # A taken name gets the next free second. Returning the existing archive
    # instead would be a silent no-op, and the one caller that would hit it is
    # the safety archive a restore takes before overwriting everything.
    for _ in range(120):
        name = archive_name(at, kind)
        final = backup_root / (name + ARCHIVE_SUFFIX)
        if not final.exists() and not final.with_name(final.name + PART_SUFFIX).exists():
            break
        at += timedelta(seconds=1)
    else:
        raise BackupError("could not find a free name for the archive")
    part = backup_root / (name + ARCHIVE_SUFFIX + PART_SUFFIX)

    files = 0
    total = 0
    newest = 0.0
    unreadable: list[str] = []
    try:
        with tarfile.open(part, "w:gz") as tar:
            for path, arcname in walk_dirs(data_root):
                try:
                    tar.add(path, arcname=arcname, recursive=False)
                except OSError as exc:
                    log.warning("skipping %s: %s", path, exc)
            for path, arcname in walk_source(data_root):
                try:
                    size, mtime = _add_whole(tar, path, arcname)
                except FileNotFoundError:
                    continue    # deleted mid-walk: normal on a live root
                except OSError as exc:
                    # A file that cannot be read is worth a line in the log.
                    log.warning("skipping %s: %s", path, exc)
                    unreadable.append(f"{arcname} ({exc.strerror or exc})")
                    continue
                files += 1
                total += size
                newest = max(newest, mtime)
        digest = _sha256(part)
        size = part.stat().st_size
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise BackupError(f"could not write the archive: {exc}") from exc
    if whole and unreadable:
        part.unlink(missing_ok=True)
        raise BackupError(
            f"cannot read {', '.join(unreadable[:5])}{' …' if len(unreadable) > 5 else ''}: "
            "a restore deletes what it replaces, so it waits until every file can be copied first"
        )

    archive = Archive(
        name=name, at=at, kind=kind, bytes=size, label=label[:limits.MAX_TITLE], files=files,
        sha256=digest, source_bytes=total, source_files=files,
        source_mtime=newest, skipped_links=len(skipped_links(data_root)), path=final,
    )
    part.replace(final)
    _write_sidecar(backup_root, archive)
    log.info("backup %s — %d files, %d bytes", name, files, size)
    return archive


def _write_sidecar(backup_root: Path, archive: Archive) -> None:
    payload = archive.as_dict()
    payload.pop("reasons", None)
    tmp = backup_root / (archive.name + SIDECAR_SUFFIX + PART_SUFFIX)
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(backup_root / (archive.name + SIDECAR_SUFFIX))


def set_pinned(backup_root: Path, name: str, pinned: bool) -> Archive:
    archive = find(backup_root, name)
    if archive is None:
        raise BackupError(f"no such backup: {name}")
    archive.pinned = pinned
    _write_sidecar(backup_root, archive)
    return archive


def delete(backup_root: Path, name: str) -> None:
    archive = find(backup_root, name)
    if archive is None or archive.path is None:
        raise BackupError(f"no such backup: {name}")
    archive.path.unlink(missing_ok=True)
    (backup_root / (name + SIDECAR_SUFFIX)).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Proving one is good, and using it
# ---------------------------------------------------------------------------


def verify(backup_root: Path, name: str) -> dict[str, Any]:
    """Re-hash the archive and read its table of contents.

    An unverified backup is a belief, not a backup — so this is a first-class
    button, not a debugging aid.
    """
    archive = find(backup_root, name)
    if archive is None or archive.path is None:
        raise BackupError(f"no such backup: {name}")
    problems: list[str] = []
    digest = _sha256(archive.path)
    if archive.sha256 and digest != archive.sha256:
        problems.append(
            f"checksum changed since it was written "
            f"({archive.sha256[:12]}… → {digest[:12]}…)"
        )
    members = 0
    try:
        with tarfile.open(archive.path, "r:gz") as tar:
            links: list[str] = []
            for member in tar:
                if member.isfile():
                    members += 1
                elif member.issym() or member.islnk():
                    links.append(member.name)
        if links:
            problems.append(_links_problem(links))
    except (OSError, EOFError, tarfile.TarError) as exc:   # EOFError: cut short
        problems.append(f"the archive will not read: {exc}")
    if archive.files and members and members != archive.files:
        problems.append(f"holds {members} files where it recorded {archive.files}")
    return {
        "name": name, "ok": not problems, "files": members,
        "sha256": digest, "problems": problems,
    }


def _links_problem(links: list[str]) -> str:
    return (f"it holds {len(links)} link{'s' if len(links) != 1 else ''} ({links[0]}"
            f"{', …' if len(links) > 1 else ''}); an archive this program writes holds none, "
            "so it is not unpacked")


NO_FILTER = "this Python cannot unpack a backup safely: Python 3.11.4 or newer is needed"


def _extract(archive_path: Path, dest: Path) -> None:
    """Unpack an archive into ``dest``, trusting it no further than that.

    ``filter="data"`` refuses absolute paths, ``..`` escapes and device
    nodes; it still lets through a link that points inside ``dest`` — and
    ``root/projects -> ..`` points at the unpacking folder itself. An
    archive this program writes holds no links (``walk_source`` skips
    them), so one that does is refused whole."""
    if not hasattr(tarfile, "data_filter"):
        raise BackupError(NO_FILTER)
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        links = [m.name for m in members if m.issym() or m.islnk()]
        if links:
            raise BackupError(_links_problem(links))
        try:
            tar.extractall(dest, members=members, filter="data")
        except TypeError as exc:          # an extractall without the filter
            raise BackupError(NO_FILTER) from exc


CHECKED = "checked.json"


def trial(backup_root: Path, name: str) -> dict[str, Any]:
    """Restore an archive for real — into a temporary folder, never over the
    data — and read it as the dashboard would.

    ``verify`` proves the bytes are the ones written; this proves they are a
    data root: every file loads, the data check finds no error, and each
    ledger holds as many rows in the dashboard as in its file. The result is
    kept in ``checked.json`` beside the archives, for the Health and
    Backups pages.
    """
    with BUSY:
        return _trial(backup_root, name)


def _trial(backup_root: Path, name: str) -> dict[str, Any]:
    import csv

    from .db import ViewStore
    from .entities import ENTITIES
    from .routers.doctor import doctor

    started = time.time()
    out = verify(backup_root, name)
    problems: list[str] = list(out["problems"])
    counts: dict[str, int] = {}
    archive = find(backup_root, name)
    if archive is not None and archive.path is not None and not problems:
        # Beside the archives, as a restore unpacks: the same disk, and not
        # the system temp folder, which may be small (a tmpfs) or shared.
        with tempfile.TemporaryDirectory(prefix="sp-trial-", dir=str(backup_root)) as tmp:
            try:
                _extract(archive.path, Path(tmp))
            except BackupError as exc:
                problems.append(str(exc))
            except (OSError, EOFError, tarfile.TarError) as exc:
                problems.append(f"it does not unpack: {exc}")
            tops = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if not problems and len(tops) != 1:
                problems.append(f"it unpacks to {len(tops)} folders, not one data root")
            if not problems:
                root = tops[0]
                store = ViewStore(root)
                for e in store.load_errors:
                    problems.append(f"{Path(e.get('file', '')).name} does not load: {e.get('error', '')}")
                report = doctor(store=store)
                for issue in report.get("issues", []):
                    if issue.get("severity") == "error":
                        problems.append(f"data check: {issue.get('file', '')} — {issue.get('detail', '')}")
                for ent in ENTITIES.values():
                    path = root / ent.csv
                    if not path.exists():
                        continue
                    with open(path, encoding="utf-8", newline="") as fh:
                        in_file = sum(1 for _ in csv.DictReader(fh))
                    loaded = store.query_one(f"SELECT COUNT(*) AS n FROM {ent.view}")
                    n = int(loaded["n"]) if loaded else 0
                    counts[ent.name] = n
                    # Overlays add rows beyond the file; a view never holds fewer.
                    if n < in_file:
                        problems.append(f"{ent.csv}: {in_file} rows in the file, {n} readable")
    result = {"name": name, "ok": not problems, "problems": problems[:20], "counts": counts,
              "at": datetime.now().isoformat(timespec="seconds"), "seconds": round(time.time() - started, 1)}
    atomic_write_json(backup_root / CHECKED, result)
    return result


def last_trial(backup_root: Path) -> dict[str, Any] | None:
    try:
        return json.loads((backup_root / CHECKED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def restore_with_safety(backup_root: Path, name: str, data_root: Path) -> tuple[dict[str, Any], Archive]:
    """A restore as the page and the command line make it: the state being
    replaced is archived first, since a restore to the wrong point is
    otherwise the one mistake this feature cannot undo.

    The archive is verified before the safety archive is taken. A refused
    restore that still took one left a "before restoring" bookmark per try,
    and manual archives are kept by count: a few tries of a broken archive
    pushed the operator's own oldest bookmarks out at the next rotation.
    """
    # Checked before anything is written: a Python that cannot unpack
    # safely would otherwise leave a safety archive per refused try.
    if not hasattr(tarfile, "data_filter"):
        raise BackupError(NO_FILTER)
    check_roots(data_root, backup_root)
    with BUSY:
        if find(backup_root, name) is None:
            raise BackupError(f"no such backup: {name}")
        report = verify(backup_root, name)
        if not report["ok"]:
            raise BackupError("; ".join(report["problems"]))
        safety = create(data_root, backup_root, kind="manual", label=f"before restoring {name}", whole=True)
        return restore(backup_root, name, data_root), safety


def restore(backup_root: Path, name: str, data_root: Path) -> dict[str, Any]:
    """Put an archive back, in place.

    The order matters and is the whole safety argument: the archive is
    verified, then extracted somewhere else entirely, and only once there is
    a complete tree on disk is the data root's content moved aside and the
    restored one moved in. A failure before that leaves the live data
    untouched; a failure during it puts back what was moved, and what was
    there before is deleted only after the last new piece is in place. If
    the swap fails, both folders stay beside the archives and the error
    names them.

    Emptied, not replaced: the running server holds an inotify watch on the
    data root itself, and swapping the directory out from under it leaves it
    watching a folder nobody writes to any more. Emptied of what an archive
    holds only: the excluded folders and the lock files stay in place.
    """
    with BUSY:
        return _restore(backup_root, name, data_root)


def _restore(backup_root: Path, name: str, data_root: Path) -> dict[str, Any]:
    if not hasattr(tarfile, "data_filter"):
        raise BackupError(NO_FILTER)
    check_roots(data_root, backup_root)
    report = verify(backup_root, name)
    if not report["ok"]:
        raise BackupError("; ".join(report["problems"]))
    archive = find(backup_root, name)
    assert archive is not None and archive.path is not None

    staged = Path(tempfile.mkdtemp(prefix="sp-restore-", dir=str(backup_root)))
    try:
        _extract(archive.path, staged)
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)   # nothing of the data was touched
        raise
    tops = [p for p in staged.iterdir()]
    source = tops[0] if len(tops) == 1 and tops[0].is_dir() else staged

    data_root.mkdir(parents=True, exist_ok=True)
    aside = Path(tempfile.mkdtemp(prefix="sp-replaced-", dir=str(backup_root)))
    out: list[str] = []      # what left the data root, in order
    came: list[str] = []     # what arrived in it
    try:
        for child in list(data_root.iterdir()):
            # What no archive holds stays where it is: the tour's photographs,
            # this machine's monitor and terminals, the lock files. Moved
            # aside they would be deleted with the rest, and the safety
            # archive taken before the restore does not hold them either.
            if _excluded(Path(child.name)):
                continue
            shutil.move(str(child), str(aside / child.name))
            out.append(child.name)
        for child in list(source.iterdir()):
            here = data_root / child.name
            if here.exists() or here.is_symlink():
                if _excluded(Path(child.name)):
                    # A kept entry (an archive from before it was excluded):
                    # the machine's own copy wins.
                    continue
                # Written into the data root after it was emptied — a hook
                # or an MCP write in the gap. Skipping it would drop the
                # archive's copy and still report success.
                raise BackupError(f"{child.name} was written into the data root while the restore ran")
            shutil.move(str(child), str(here))
            came.append(child.name)
    except Exception as exc:
        # Back to how it was: the new pieces out again, the old ones in.
        back = True
        for piece in reversed(came):
            try:
                shutil.move(str(data_root / piece), str(source / piece))
            except OSError:
                back = False
        arrived: Path | None = None
        for piece in reversed(out):
            try:
                target = data_root / piece
                if target.exists() or target.is_symlink():
                    # Something was written here in the gap. Moving the old
                    # piece onto it would nest one inside the other; keep
                    # the newcomer beside the archives instead.
                    if arrived is None:
                        arrived = Path(tempfile.mkdtemp(prefix="sp-arrived-", dir=str(backup_root)))
                    shutil.move(str(target), str(arrived / piece))
                shutil.move(str(aside / piece), str(target))
            except OSError:
                back = False
        log.error("restore of %s failed in the swap: %s", archive.name, exc)
        if back:
            try:
                aside.rmdir()             # empty again: everything went back
            except OSError:
                pass
        raise BackupError(
            f"could not put {archive.name} in place: {exc}. "
            + ("The data is as it was before." if back
               else f"Not everything could be put back: what was there is in {aside}.")
            + (f" What was written during the restore is in {arrived}." if arrived else "")
            + f" The restored copy is in {staged}."
        ) from exc
    moved = len(came)
    shutil.rmtree(aside, ignore_errors=True)
    shutil.rmtree(staged, ignore_errors=True)

    files, total, _ = source_stats(data_root)
    log.warning("restored %s into %s — %d files", name, data_root, files)
    return {"name": name, "entries": moved, "files": files, "bytes": total}


# ---------------------------------------------------------------------------
# Showing the operator where they are
# ---------------------------------------------------------------------------


def reveal(path: Path) -> tuple[bool, str]:
    """Open a folder — or the folder holding a file — in the file manager.

    A web page cannot open a local directory, so the server does it. Returns
    (opened, why) rather than raising, and never waits on the process: a file
    manager runs for as long as it is left open.
    """
    target = path if path.is_dir() else path.parent
    if not target.exists():
        return False, f"{target} does not exist"

    if sys.platform == "darwin":
        # -R selects the file in Finder instead of opening the folder blind.
        argv = ["open", "-R", str(path)] if path.is_file() else ["open", str(target)]
    elif sys.platform.startswith("win"):
        argv = (["explorer", f"/select,{path}"] if path.is_file()
                else ["explorer", str(target)])
    elif shutil.which("xdg-open") is None:
        return False, "xdg-open is not installed"
    else:
        # No portable way to select a file, so open the folder it is in.
        argv = ["xdg-open", str(target)]

    try:
        subprocess.Popen(
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return False, f"could not run {argv[0]}: {exc}"
    return True, str(target)


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def due_now(data_root: Path, backup_root: Path, now: datetime, every_hours: int) -> tuple[bool, str, list[Archive]]:
    """``due`` for the scheduler, asked every few minutes: the clock first,
    and the walk of the data root (``source_stats`` — every file of every
    chat) only once the interval has passed. With the interval at six hours,
    71 of 72 walks answered a question the clock had already closed."""
    archives = list_archives(backup_root)
    ready, why = due(archives, now, every_hours, 0.0)
    if ready and archives:
        _, _, mtime = source_stats(data_root)
        ready, why = due(archives, now, every_hours, mtime)
    return ready, why, archives


def due(
    archives: list[Archive], now: datetime, every_hours: int, source_mtime: float,
) -> tuple[bool, str]:
    """Should the scheduler take one now? Returns (yes/no, why).

    Two gates, both of which have to open. The clock says the interval has
    passed; the data says something actually changed since the last archive.
    Without the second gate an idle week produces seven identical archives
    and pushes the real history off the bottom of the ladder.
    """
    if every_hours <= 0:
        return False, "automatic backups are off"
    autos = [a for a in archives if a.kind == "auto"]
    if not autos:
        return True, "no automatic backup yet"
    last = max(autos, key=lambda a: a.at)
    waited = now - last.at
    if waited < timedelta(hours=every_hours):
        left = timedelta(hours=every_hours) - waited
        return False, f"next in {int(left.total_seconds() // 60)} min"
    if last.source_mtime and source_mtime and source_mtime <= last.source_mtime:
        return False, "nothing has changed since the last backup"
    return True, f"{int(waited.total_seconds() // 3600)}h since the last one"
