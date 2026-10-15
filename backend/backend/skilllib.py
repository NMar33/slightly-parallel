"""Skills — procedures an agent loads when a task matches, kept and installed by Slightly Parallel.

A skill is a folder: ``SKILL.md`` (a ``---`` block with ``name`` and
``description``, then the instructions) and the files it links. Claude Code
reads ``.claude/skills/<name>/``, Codex reads ``.agents/skills/<name>/``,
OpenCode reads both. Slightly Parallel is the source of truth: every change is a
version, and an installed folder is a copy Slightly Parallel writes, keeps current and
watches for edits made on disk.

Where things live:

- ``skills.csv`` — one row per skill. A skill kept from a ``#skill`` message
  also carries the message and its context (keeplib.py).
- ``kept_versions/<id>.md`` — every SKILL.md with who, when and why; the
  other files of version n sit in ``kept_versions/<id>/v<n>/``.
- ``<project>/.claude/skills/<name>/`` and ``.agents/skills/<name>/`` — the
  installed copies, each holding ``.sp-skill.json`` with the skill, the
  version and a hash. A folder without it is not Slightly Parallel's and is never
  overwritten or removed.
- ``skill_installs.json`` — where each skill is installed.
- ``skills.jsonl`` beside a chat — the skills that ran in each turn, written
  by the capture hook or read back from past Claude Code logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple


from . import frontmatter, keeplib, limits
from .csvio import append_row, read_rows, rewrite_rows
from .db import ViewStore
from .docs_md import build_detail, read_detail, resolve_under, safe_ref_part
from .entities import ENTITIES
from .file_safety import (
    acquire_flock, atomic_write, atomic_write_json, lock_path, safe_read_json,
)
# One copy for the capture hook and for the backfill here (hookshared.py).
from .hookshared import local_iso, skill_uses as uses_in_record
from .promptlib import Version, render_doc

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = limits.MAX_NAME
MAX_DESCRIPTION = 1024      # OpenCode's limit, the strictest of the three tools
MAX_LINES = 500
MAX_FILES = 50
MAX_FILE_BYTES = 200_000
TOOL_DIRS = (".claude/skills", ".agents/skills")
# The same folders under the operator's home: every agent on this machine
# reads them, whatever project it works in.
ALL_PROJECTS = "all"
MARKER = ".sp-skill.json"
# The marker's name before the product was renamed: a copy installed then is
# still recognised as ours.
OLD_MARKER = ".merkhet-skill.json"
INSTALLS = "skill_installs.json"
USES_FILE = "skills.jsonl"


def _view() -> str:
    return ENTITIES["skill"].view


# ---------------------------------------------------------------------------
# SKILL.md
# ---------------------------------------------------------------------------


def parse(skill_md: str) -> tuple[dict[str, Any] | None, str]:
    """(the ``---`` block, or None when it is missing or does not read; the body)."""
    text = (skill_md or "").replace("\r\n", "\n").strip()
    return frontmatter.meta(text)


_LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_LOCAL_PATH_RE = re.compile(r"(/home/[^/\s]+/|/Users/[^/\s]+/|[A-Za-z]:\\Users\\)")
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def checks(skill_md: str, files: dict[str, str]) -> list[dict[str, str]]:
    """What stops a skill from working in Claude Code, Codex and OpenCode, and what makes agents skip it."""
    out: list[dict[str, str]] = []

    def error(text: str) -> None:
        out.append({"level": "error", "text": text})

    def warning(text: str) -> None:
        out.append({"level": "warning", "text": text})

    meta, body = parse(skill_md)
    if meta is None:
        error("SKILL.md must start with a --- block that holds name and description.")
        meta = {}
    name = str(meta.get("name") or "").strip()
    if not name:
        error("Add a name.")
    elif len(name) > MAX_NAME or not NAME_RE.match(name):
        error("The name must use lowercase letters, digits and single hyphens, up to 64 characters.")
    description = " ".join(str(meta.get("description") or "").split())
    if not description:
        error("Add a description. Agents read only the description when they choose a skill.")
    else:
        if len(description) > MAX_DESCRIPTION:
            error(f"The description has {len(description)} characters. The limit is {MAX_DESCRIPTION}.")
        if not re.search(r"\bwhen\b", description, re.IGNORECASE):
            warning("The description does not say when to use the skill. Agents may not choose it.")
    if not body.strip():
        error("Add the instructions under the --- block.")
    elif len(body.splitlines()) > MAX_LINES:
        warning(f"SKILL.md has more than {MAX_LINES} lines. Move reference text into a separate file.")
    for m in _LINK_RE.finditer(body):
        target = m.group(1)
        # Anything with a scheme is not a file in the folder: a URL, a
        # mailto:, or Slightly Parallel's own image:1 reference in task evidence.
        if _SCHEME_RE.match(target) or target.startswith("/"):
            continue
        if str(PurePosixPath(target)) not in files:
            error(f"The linked file is missing: {target}")
    everything = (skill_md or "") + "\n" + "\n".join(files.values())
    if _SECRET_RE.search(everything):
        error("The skill appears to contain a secret key.")
    local = _LOCAL_PATH_RE.search(everything)
    if local:
        warning(f"The skill contains a path from this computer: {local.group(0)}")
    return out


_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


def clean_files(files: Any) -> dict[str, str]:
    """``{relative path: text}``, refused when a path could leave the skill folder."""
    if files in (None, ""):
        return {}
    if not isinstance(files, dict):
        raise ValueError("files must be an object of path → text")
    if len(files) > MAX_FILES:
        raise ValueError(f"a skill holds at most {MAX_FILES} files")
    out: dict[str, str] = {}
    for raw, text in files.items():
        path = str(PurePosixPath(str(raw).strip()))
        parts = path.split("/")
        if (not _FILE_RE.match(path) or "." in parts or ".." in parts
                or path in ("SKILL.md", MARKER, OLD_MARKER)):
            raise ValueError(f"not a file path inside a skill: {raw}")
        # A copy on disk is read back with newlines translated; the same
        # text must hash the same both ways, or every save is a version.
        body = "" if text is None else str(text).replace("\r\n", "\n")
        if len(body.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"{path} is larger than {MAX_FILE_BYTES // 1000} KB")
        out[path] = body
    for path in out:
        if any(other.startswith(path + "/") for other in out):
            raise ValueError(f"{path} cannot be both a file and a folder")
    return out


def content_hash(skill_md: str, files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path, text in [("SKILL.md", (skill_md or "").strip()), *sorted(files.items())]:
        h.update(path.encode())
        h.update(b"\0")
        h.update(text.encode())
        h.update(b"\0")
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def _version_dir(store: ViewStore, kid: str, n: int) -> Path:
    return store.data_root / keeplib.VERSIONS_DIR / kid / f"v{n}"


def read_version(store: ViewStore, kid: str, n: int | None = None) -> dict[str, Any] | None:
    versions = keeplib.read_versions(store, kid)
    if not versions:
        return None
    v = versions[-1] if n is None else next((x for x in versions if x.n == n), None)
    if v is None:
        return None
    files: dict[str, str] = {}
    root = _version_dir(store, kid, v.n)
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return {"n": v.n, "at": v.at, "how": v.how, "note": v.note, "skill_md": v.text,
            "files": files, "hash": content_hash(v.text, files)}


def _validate(store: ViewStore, kid: str, skill_md: str, files: Any) -> tuple[str, dict[str, str], str, str]:
    text = (skill_md or "").strip()
    if not text:
        raise ValueError("SKILL.md cannot be empty")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"SKILL.md is larger than {MAX_FILE_BYTES // 1000} KB")
    clean = clean_files(files)
    meta, _body = parse(text)
    name = str((meta or {}).get("name") or "").strip()
    if meta is None or not name or len(name) > MAX_NAME or not NAME_RE.match(name):
        raise ValueError("SKILL.md needs a --- block with a name of lowercase letters, digits and single hyphens")
    # The name is the folder agents load, so it is unique whatever the status:
    # an archived skill may still be installed under it.
    clash = store.query_one(f"SELECT id, status FROM {_view()} WHERE name = ? AND id <> ?", (name, kid))
    if clash is not None:
        what = "an archived skill" if str(clash.get("status") or "") == "archived" else "another skill"
        raise ValueError(f"{what} is already named {name}: {clash['id']}")
    description = " ".join(str(meta.get("description") or "").split())
    return text, clean, name, description


def _set_fields(store: ViewStore, kid: str, fields: dict[str, Any], rebuild: bool = True) -> None:
    ent = ENTITIES["skill"]
    values = {k: str(v) for k, v in fields.items()}

    def mutate(rows: list[dict[str, str]]) -> bool:
        touched = False
        for r in rows:
            if r.get("id") == kid and any(r.get(k) != v for k, v in values.items()):
                r.update(values)
                touched = True
        return touched

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    if rebuild:
        store.rebuild()


def write_version(
    store: ViewStore, row: dict[str, Any], skill_md: str, files: Any = None,
    *, how: str, note: str = "", now: datetime | None = None, rebuild: bool = True,
) -> dict[str, Any]:
    """Save SKILL.md and its files as the next version. The same content twice is one version.

    ``files`` left out keeps the files of the current version — an agent
    rewriting SKILL.md must not silently drop the scripts beside it. An
    empty object is the way to remove them all.
    """
    kid = str(row["id"])
    if files is None:
        last = read_version(store, kid)
        files = last["files"] if last else {}
    text, clean, name, description = _validate(store, kid, skill_md, files)
    # The same content as the current version writes nothing — asked first,
    # without the lock: every start asks it of each built-in skill.
    last = read_version(store, kid)
    if last is not None and last["hash"] == content_hash(text, clean):
        return last
    history = store.data_root / keeplib.versions_ref(kid)
    history.parent.mkdir(parents=True, exist_ok=True)
    # Read, number and write under one lock: an agent's draft and an edit
    # on the page at the same moment were both version n+1, and one was lost.
    with acquire_flock(lock_path(history)):
        versions = keeplib.read_versions(store, kid)
        if versions:
            last = read_version(store, kid)
            if last is not None and last["hash"] == content_hash(text, clean):
                return last
        at = now or datetime.now()
        n = versions[-1].n + 1 if versions else 1
        versions.append(Version(
            n, f"{at.year % 100:02d}{at.month:02d}-{at.day:02d} {at:%H:%M}", how,
            (note or "").strip()[:keeplib.MAX_NOTE], text,
        ))
        atomic_write(history, render_doc(f"---\nid: {kid}\nkind: skill\n---\n", versions))
        root = _version_dir(store, kid, n)
        for rel, body in clean.items():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(dest, body)
    fields: dict[str, Any] = {"name": name, "description": description[:2000], "versions_n": n}
    if str(row.get("source") or "") != "captured" or not str(row.get("l1") or "").strip():
        fields["l1"] = name
    _set_fields(store, kid, fields, rebuild=rebuild)
    # The entry's L2 is the description, so every reader of skills sees it.
    md_ref = str(row.get("md_ref") or "")
    doc = resolve_under(store.data_root, md_ref)
    if doc is not None:
        _l2, l3, l4 = read_detail(store.data_root, md_ref)
        fresh = (store.query_one(f"SELECT * FROM {_view()} WHERE id = ?", (kid,)) if rebuild else None) or {**row, **fields}
        base = {k: v for k, v in fresh.items() if k != "id" and v not in (None, "")}
        doc.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(doc, build_detail({**base, "l2": description, "l3": l3, "l4": l4}, kid))
    return read_version(store, kid, n) or {}


def create_written(
    store: ViewStore, skill_md: str, files: Any = None, *,
    project: str = "", tags: str = "", source: str = "written", note: str = "",
    now: datetime | None = None,
) -> str:
    """A skill written on the Skills page, or taken in from a folder. Returns its id."""
    ent = ENTITIES["skill"]
    at = now or datetime.now()
    meta, _ = parse(skill_md)
    name = str((meta or {}).get("name") or "")
    kid = ent.id_prefix + hashlib.sha256(f"written|{name}|{at.isoformat()}".encode()).hexdigest()[:8]
    _validate(store, kid, skill_md, files)
    date, time = f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}", at.strftime("%H:%M")
    md_ref = (
        f"{ent.detail_dir}/{date.replace('-', '')}-{time.replace(':', '')}__"
        f"{safe_ref_part((project or 'none').lower())}__operator__{kid}.md"
    )
    row: dict[str, Any] = {
        "created_date": date, "created_time": time, "project": project, "agent_id": "operator",
        "l1": name, "name": "", "description": "", "status": "draft", "md_ref": md_ref,
        "source": source, "session_id": "", "source_turn": 0, "versions_n": 0, "tags": tags,
    }
    doc = store.data_root / md_ref
    doc.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(doc, build_detail(row, kid))
    append_row(store.data_root / ent.csv, ent.columns, {"id": kid, **row})
    store.rebuild()
    write_version(store, {"id": kid, **row}, skill_md, files, how="edited",
                  note=note or "Written on the Skills page", now=at)
    return kid


# ---------------------------------------------------------------------------
# Installed copies
# ---------------------------------------------------------------------------


def _targets(store: ViewStore) -> dict[str, str]:
    return {
        str(r.get("project") or ""): str(r.get("path") or "")
        for r in read_rows(store.data_root / "integrations.csv")
        if r.get("project") and r.get("path")
    }


def _installs(store: ViewStore) -> list[dict[str, Any]]:
    try:
        data = safe_read_json(store.data_root / INSTALLS)
    except (OSError, ValueError):
        return []
    rows = data.get("installs") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict) and r.get("skill_id")] if isinstance(rows, list) else []


def _save_installs(store: ViewStore, rows: list[dict[str, Any]]) -> None:
    atomic_write_json(store.data_root / INSTALLS, {"installs": rows})


@contextmanager
def _ledger(store: ViewStore) -> Iterator[list[dict[str, Any]]]:
    """The install rows, read and written under one lock.

    Two installs at once (two tabs, a script over several projects) each
    read the ledger, add a row and write it back; without the lock the
    second write forgets the first row while its folders stay on disk.
    """
    store.data_root.mkdir(parents=True, exist_ok=True)
    path = store.data_root / INSTALLS
    with acquire_flock(lock_path(path)):
        rows = _installs(store)
        before = json.dumps(rows, sort_keys=True)
        yield rows
        # A reader of the ledger writes nothing: every start used to rewrite
        # the file once per built-in skill, with what it already held.
        if json.dumps(rows, sort_keys=True) != before:
            _save_installs(store, rows)


def _dests(folder: Path, name: str) -> list[Path]:
    return [folder / rel / name for rel in TOOL_DIRS]


def _folder(store: ViewStore, project: str) -> Path:
    """Where a skill is written for that project — the home folder for "all"."""
    if project == ALL_PROJECTS:
        return Path.home()
    raw = _targets(store).get(project)
    if not raw:
        raise LookupError(f"{project or 'that project'} is not set up — add it in Setup first")
    folder = Path(raw)
    if not folder.is_dir():
        raise ValueError(f"the folder for {project} does not exist: {folder}")
    return folder


def _marker(dest: Path) -> dict[str, Any] | None:
    for name in (MARKER, OLD_MARKER):
        try:
            data = json.loads((dest / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return data if isinstance(data, dict) else None
    return None


class FolderRead(NamedTuple):
    skill_md: str
    files: dict[str, str]
    # Files a skill cannot hold: binary or larger than MAX_FILE_BYTES. They
    # are named, never read as text — a PNG read with replacement characters
    # and written back is a broken PNG.
    skipped: list[str]


def _read_folder(dest: Path) -> FolderRead | None:
    try:
        skill_md = (dest / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    files, skipped = _text_files(dest)
    return FolderRead(skill_md, files, skipped)


def _disk_hash(dest: Path) -> str | None:
    """What the copy holds; a file the skill cannot hold still counts as a change."""
    found = _read_folder(dest)
    if found is None:
        return None
    return content_hash(found.skill_md, {**found.files, **{rel: "\0binary" for rel in found.skipped}})


def _changed(dest: Path, marker: dict[str, Any]) -> bool:
    """The copy no longer holds what Slightly Parallel wrote there."""
    return _disk_hash(dest) != marker.get("hash")


def _write_folder(dest: Path, kid: str, version: dict[str, Any]) -> None:
    if dest.exists():
        shutil.rmtree(dest)  # only reached for a folder whose marker names this skill
    dest.mkdir(parents=True)
    atomic_write(dest / "SKILL.md", version["skill_md"].strip() + "\n")
    for rel, body in version["files"].items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, body)
    atomic_write_json(dest / MARKER, {"skill_id": kid, "version": version["n"], "hash": version["hash"]})


def _skill_name(store: ViewStore, kid: str) -> str:
    row = store.query_one(f"SELECT name FROM {_view()} WHERE id = ?", (kid,))
    return str((row or {}).get("name") or "")


def _foreign(store: ViewStore, dest: Path, kid: str, marker: dict[str, Any] | None) -> str | None:
    """Why a folder cannot be written: it is someone else's, or another skill's."""
    if not dest.exists():
        return None
    if marker is None:
        return f"{dest} holds a skill Slightly Parallel did not write. Rename one of them."
    other = str(marker.get("skill_id") or "")
    if other != kid:
        return f"{dest} is installed there for {other} ({_skill_name(store, other) or 'archived'}). Rename one of them."
    return None


def install(
    store: ViewStore, row: dict[str, Any], project: str, *, dry_run: bool = False, force: bool = False,
) -> dict[str, Any]:
    """Write the current version into a project's skill folders, or the home ones for "all".

    A copy the operator edited on disk is never overwritten by accident:
    the answer is ``changed`` and a real write needs ``force``.
    """
    kid, name = str(row["id"]), str(row.get("name") or "")
    current = read_version(store, kid)
    if current is None or not NAME_RE.match(name):
        raise ValueError("the skill has no version to install yet")
    # An example is there to show what the page does. It is never written
    # into anyone's project, whatever the operator clicks.
    if str(row.get("source") or "") == "demo":
        raise ValueError("this is an example — examples are never written into a project")
    folder = _folder(store, project)
    dests = _dests(folder, name)
    actions: list[str] = []
    edited: list[Path] = []
    for dest in dests:
        marker = _marker(dest)
        problem = _foreign(store, dest, kid, marker)
        if problem:
            raise ValueError(problem)
        if marker is None:
            actions.append("created")
        elif _changed(dest, marker):
            actions.append("changed")
            edited.append(dest)
        elif marker.get("hash") == current["hash"]:
            actions.append("unchanged")
        else:
            actions.append("updated")
    with _ledger(store) as rows:
        old = next((e for e in rows if e.get("skill_id") == kid and e.get("project") == project), None)
        # A renamed skill leaves its old folders behind unless they are taken out.
        stale_dests = _dests(folder, str(old["name"])) if old and old.get("name") and old["name"] != name else []
        for dest in stale_dests:
            marker = _marker(dest)
            if marker is not None and marker.get("skill_id") == kid and _changed(dest, marker):
                edited.append(dest)
        action = next((a for a in ("changed", "updated", "created") if a in actions), "unchanged")
        if dry_run:
            return {"project": project, "paths": [str(d) for d in dests], "action": action,
                    "version": current["n"], "dry_run": True, "edited": [str(d) for d in edited]}
        if edited and not force:
            raise ValueError(
                f"{edited[0]} was edited after Slightly Parallel wrote it. Keep this copy first, or overwrite it."
            )
        for dest in stale_dests:
            if (_marker(dest) or {}).get("skill_id") == kid:
                shutil.rmtree(dest)
        if action != "unchanged":
            for dest in dests:
                _write_folder(dest, kid, current)
        rows[:] = [e for e in rows if not (e.get("skill_id") == kid and e.get("project") == project)]
        # `written_at` is when Slightly Parallel last wrote these files. An install that
        # changed nothing wrote nothing, so the stamp stays where it was —
        # moving it made every server start rewrite this ledger and leave the
        # repository dirty for a time nobody touched.
        kept = (
            str(old.get("written_at") or "")
            if old
            and action == "unchanged"
            and str(old.get("path") or "") == str(folder)
            and str(old.get("name") or "") == name
            and str(old.get("version") or "") == str(current["n"])
            else ""
        )
        rows.append({"skill_id": kid, "project": project, "path": str(folder), "name": name,
                     "version": current["n"],
                     "written_at": kept or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
    return {"project": project, "paths": [str(d) for d in dests],
            "action": "overwritten" if edited else action, "version": current["n"], "dry_run": False}


def install_status(store: ViewStore, row: dict[str, Any], entry: dict[str, Any]) -> str:
    """fresh · stale (an older version) · changed (edited on disk) · missing."""
    kid = str(row["id"])
    current = read_version(store, kid)
    states: list[str] = []
    for dest in _dests(Path(str(entry.get("path") or "")), str(entry.get("name") or row.get("name") or "")):
        marker = _marker(dest)
        if marker is None or marker.get("skill_id") != kid:
            states.append("missing")
        elif _changed(dest, marker):
            states.append("changed")
        elif current is None or marker.get("hash") != current["hash"] or entry.get("name") != row.get("name"):
            states.append("stale")
        else:
            states.append("fresh")
    return next((s for s in ("changed", "missing", "stale") if s in states), "fresh")


def install_fingerprint(store: ViewStore) -> str:
    """What the installed copies look like right now, in 16 characters.

    A copy lives in a project folder the store never stats, so a hand edit
    there changes an answer without changing ``view_mtime``. Endpoints that
    report install state put this in their ETag, or a change on disk is
    served from the browser's cache.
    """
    h = hashlib.sha256()
    for entry in _installs(store):
        h.update(f"{entry.get('skill_id')}|{entry.get('project')}|{entry.get('name')}|{entry.get('version')}".encode())
        for dest in _dests(Path(str(entry.get("path") or "")), str(entry.get("name") or "")):
            try:
                for p in sorted(dest.rglob("*")):
                    st = p.stat()
                    h.update(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode())
            except OSError:
                h.update(b"gone")
    return h.hexdigest()[:16]


def _differs(store: ViewStore, row: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """Which files a copy on disk no longer matches — SKILL.md included."""
    kid = str(row["id"])
    current = read_version(store, kid)
    if current is None:
        return []
    mine = {"SKILL.md": current["skill_md"].strip(), **current["files"]}
    out: set[str] = set()
    for dest in _dests(Path(str(entry.get("path") or "")), str(entry.get("name") or row.get("name") or "")):
        if (_marker(dest) or {}).get("skill_id") != kid:
            continue
        found = _read_folder(dest)
        if found is None:
            continue
        theirs = {"SKILL.md": found.skill_md.strip(), **found.files}
        out |= {p for p in set(mine) | set(theirs) if mine.get(p, "").strip() != theirs.get(p, "").strip()}
        out |= set(found.skipped)
    return sorted(out)


def read_copy(store: ViewStore, row: dict[str, Any], project: str) -> dict[str, Any]:
    """A copy as it is on disk right now — what the page shows against the current version."""
    kid = str(row["id"])
    entry = next((e for e in _installs(store) if e.get("skill_id") == kid and e.get("project") == project), None)
    if entry is None:
        raise LookupError(f"the skill is not installed in {project}")
    for dest in _dests(Path(str(entry["path"])), str(entry.get("name") or row.get("name") or "")):
        found = _read_folder(dest) if (_marker(dest) or {}).get("skill_id") == kid else None
        if found is not None:
            return {"project": project, "path": str(dest), "skill_md": found.skill_md, "files": found.files,
                    "skipped": found.skipped, "differs": _differs(store, row, entry)}
    raise LookupError(f"no copy of the skill was found in {project}")


def installs_for(store: ViewStore, row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for e in _installs(store):
        if e.get("skill_id") != row["id"]:
            continue
        status = install_status(store, row, e)
        # Only a changed copy needs the comparison; the rest is a hash check.
        out.append({**e, "status": status, "differs": _differs(store, row, e) if status == "changed" else []})
    return out


def uninstall(store: ViewStore, row: dict[str, Any], project: str, *, force: bool = False) -> list[str]:
    """Take the skill's folders out of a project. Folders Slightly Parallel did not write stay.

    Idempotent: a skill that is not installed there gives an empty list. A
    copy edited on disk is kept unless ``force`` says otherwise.
    """
    kid = str(row["id"])
    removed: list[str] = []
    with _ledger(store) as rows:
        entry = next((e for e in rows if e.get("skill_id") == kid and e.get("project") == project), None)
        if entry is None:
            return []
        dests = _dests(Path(str(entry["path"])), str(entry.get("name") or row.get("name") or ""))
        mine = [(d, m) for d in dests if (m := _marker(d)) is not None and m.get("skill_id") == kid]
        if not force:
            edited = [d for d, m in mine if _changed(d, m)]
            if edited:
                raise ValueError(
                    f"{edited[0]} was edited after Slightly Parallel wrote it. Keep this copy first, or remove it anyway."
                )
        for dest, _m in mine:
            shutil.rmtree(dest)
            removed.append(str(dest))
        rows[:] = [e for e in rows if e is not entry]
    return removed


def keep_disk(store: ViewStore, row: dict[str, Any], project: str, path: str = "") -> dict[str, Any]:
    """An installed copy was edited on disk: save it as the next version, then install that.

    ``path`` names the copy when the project's two copies differ from each
    other; without it, two different copies are refused rather than one
    silently overwriting the other.
    """
    kid = str(row["id"])
    entry = next((e for e in _installs(store) if e.get("skill_id") == kid and e.get("project") == project), None)
    if entry is None:
        raise LookupError(f"the skill is not installed in {project}")
    copies: list[tuple[Path, FolderRead, bool]] = []
    for dest in _dests(Path(str(entry["path"])), str(entry.get("name") or row.get("name") or "")):
        marker = _marker(dest)
        found = _read_folder(dest) if (marker or {}).get("skill_id") == kid else None
        if found is not None and marker is not None:
            copies.append((dest, found, _changed(dest, marker)))
    if not copies:
        raise LookupError(f"no copy of the skill was found in {project}")
    if path:
        copies = [c for c in copies if str(c[0]) == path]
        if not copies:
            raise LookupError(f"{path} is not a copy of the skill in {project}")
    # Only an edited copy is a candidate; the other one still says what Slightly Parallel wrote.
    edited = [c for c in copies if c[2]] or copies
    if len({_disk_hash(d) for d, _f, _c in edited}) > 1:
        raise ValueError(
            "both copies were edited and differ from each other. Send `path` to say which one to keep: "
            + " or ".join(str(d) for d, _f, _c in edited)
        )
    dest, found, _c = edited[0]
    if found.skipped:
        raise ValueError(
            f"{found.skipped[0]} in {dest} is not a text file. A skill holds text files only; take it out first."
        )
    version = write_version(store, row, found.skill_md, found.files, how="edited", note=f"Taken from {project}")
    fresh = store.query_one(f"SELECT * FROM {_view()} WHERE id = ?", (kid,)) or row
    install(store, fresh, project, force=True)
    return version


# ---------------------------------------------------------------------------
# Skills already on disk
# ---------------------------------------------------------------------------

# Where the three tools read skills from. Slightly Parallel writes the first two; a
# folder in any of them that Slightly Parallel did not write is someone's own skill.
SCAN_DIRS = TOOL_DIRS + (".opencode/skills",)


def _scan_roots(store: ViewStore) -> list[tuple[str, Path]]:
    return [(ALL_PROJECTS, Path.home()), *((p, Path(raw)) for p, raw in _targets(store).items())]


def _text_files(dest: Path) -> tuple[dict[str, str], list[str]]:
    """The folder's files besides SKILL.md; what could not be taken in is named."""
    files: dict[str, str] = {}
    skipped: list[str] = []
    for p in sorted(dest.rglob("*")):
        rel = p.relative_to(dest).as_posix()
        if not p.is_file() or rel in ("SKILL.md", MARKER, OLD_MARKER):
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("too large")
            files[rel] = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            skipped.append(rel)
    return files, skipped


def found_skills(store: ViewStore) -> list[dict[str, Any]]:
    """Skill folders on this machine that Slightly Parallel does not keep, with where they sit.

    The same folder is usually copied into several projects; identical copies
    are one entry. A folder whose name is already a Slightly Parallel skill is listed
    too, marked, because installing over it is refused until one is renamed.
    """
    names = {
        str(r["name"]) for r in store.query(
            f"SELECT name FROM {_view()} WHERE COALESCE(name, '') <> '' AND COALESCE(status, '') <> 'archived'")
    }
    uses = {str(r["skill"]): int(r["n"]) for r in store.query(
        "SELECT skill, COUNT(*) AS n FROM skill_uses GROUP BY skill")}
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for project, folder in _scan_roots(store):
        for rel in SCAN_DIRS:
            base = folder / rel
            if not base.is_dir():
                continue
            for d in sorted(p for p in base.iterdir() if p.is_dir()):
                if not (d / "SKILL.md").is_file() or (_marker(d) or {}).get("skill_id"):
                    continue
                read = _read_folder(d)
                if read is None:
                    continue
                skill_md, files = read.skill_md, read.files
                meta, _body = parse(skill_md)
                name = str((meta or {}).get("name") or "").strip() or d.name
                key = (name, content_hash(skill_md, files))
                entry = entries.setdefault(key, {
                    "name": name,
                    "description": " ".join(str((meta or {}).get("description") or "").split())[:400],
                    "hash": key[1], "files_n": len(files), "lines": len(skill_md.splitlines()),
                    "uses": uses.get(name, 0), "clash": name in names, "where": [],
                })
                entry["where"].append({"project": project, "path": str(d)})
    return sorted(entries.values(), key=lambda e: (-e["uses"], -len(e["where"]), e["name"]))


def import_skill(store: ViewStore, path: str, *, tags: str = "") -> dict[str, Any]:
    """Take a skill folder on disk into Slightly Parallel as version 1. The folder is not changed."""
    dest = Path(path).expanduser()
    allowed = any(
        dest.parent == folder / rel for _p, folder in _scan_roots(store) for rel in SCAN_DIRS
    )
    if not allowed or not (dest / "SKILL.md").is_file():
        raise LookupError(f"not a skill folder Slightly Parallel reads: {path}")
    if (_marker(dest) or {}).get("skill_id"):
        raise ValueError("Slightly Parallel wrote this folder already")
    skill_md = (dest / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    files, skipped = _text_files(dest)
    meta, body = parse(skill_md)
    name = str((meta or {}).get("name") or "").strip() or dest.name
    if meta is None or not NAME_RE.match(name):
        # Folders written by hand often have no --- block; the folder name is the name.
        name = dest.name
        if not NAME_RE.match(name) or len(name) > MAX_NAME:
            raise ValueError(
                f"{dest.name} cannot be a skill name: lowercase letters, digits and single hyphens, "
                f"up to {MAX_NAME} characters. Rename the folder first."
            )
        description = " ".join(body.split())[:limits.MAX_TITLE] if meta is None else ""
        skill_md = f"---\nname: {name}\ndescription: {description or name}\n---\n\n{body or skill_md}"
    kid = create_written(store, skill_md, files, tags=tags, source="imported",
                         note=f"Taken in from {dest}")
    return {"id": kid, "name": name, "skipped": skipped}


# ---------------------------------------------------------------------------
# The skills Slightly Parallel ships with
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_DIR = _REPO_ROOT / "templates" / "skills"
BUILTIN_SOURCE = "builtin"


def builtin_id(name: str) -> str:
    """One id per built-in skill, the same on every data root."""
    return ENTITIES["skill"].id_prefix + hashlib.sha256(f"builtin|{name}".encode()).hexdigest()[:8]


WRITING_RULES_MARK = "{{writing-rules}}"
_PART_MARK_RE = re.compile(r"\{\{part:([a-z0-9-]+)\}\}")


def _part_body(templates: Path, key: str) -> str:
    """The body of the contract part with this key (prompts/contract/NN-<key>.md)."""
    folder = templates.resolve().parents[1] / "prompts" / "contract"
    for path in sorted(folder.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        pairs, body = frontmatter.pairs(text)
        if any(k == "key" and v == key for k, v in pairs):
            return body.strip()
    return ""


def _with_writing_rules(skill_md: str, templates: Path) -> str:
    """A built-in skill takes its text from the contract's own parts.

    ``{{part:<key>}}`` in a template becomes that part's body when the skill
    is seeded (``{{writing-rules}}`` is the writing part). The contract keeps
    a brief of such a part and the skill carries the whole of it, so the two
    can never say different things.
    """
    out = skill_md.replace(WRITING_RULES_MARK, "{{part:writing}}")
    return _PART_MARK_RE.sub(lambda m: _part_body(templates, m.group(1)), out)


def seed_builtin_skills(store: ViewStore, templates: Path | None = None) -> list[str]:
    """Write the skills under templates/skills into the store. Returns the ids
    that gained a version (a new skill, or a changed template). The Skills
    page is never empty, and examples.remove leaves these alone."""
    base = templates or BUILTIN_DIR
    if not base.is_dir():
        return []
    ent = ENTITIES["skill"]
    touched: list[str] = []
    created = False
    for d in sorted(p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
        skill_md = _with_writing_rules((d / "SKILL.md").read_text(encoding="utf-8"), base)
        files, _skipped = _text_files(d)
        meta, _body = parse(skill_md)
        name = str((meta or {}).get("name") or "").strip()
        if not NAME_RE.match(name):
            raise ValueError(f"{d.name}/SKILL.md has no valid name")
        kid = builtin_id(name)
        rows = read_rows(store.data_root / ent.csv)
        row = next((r for r in rows if r.get("id") == kid), None)
        if row is None:
            at = datetime.now()
            date, time = f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}", at.strftime("%H:%M")
            md_ref = f"{ent.detail_dir}/{date.replace('-', '')}-{time.replace(':', '')}__builtin__slightly-parallel__{kid}.md"
            row = {
                "created_date": date, "created_time": time, "project": "", "agent_id": "slightly-parallel",
                "l1": name, "name": "", "description": "", "status": "active", "md_ref": md_ref,
                "source": BUILTIN_SOURCE, "session_id": "", "source_turn": 0, "versions_n": 0, "tags": "builtin",
            }
            doc = store.data_root / md_ref
            doc.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(doc, build_detail(row, kid))
            append_row(store.data_root / ent.csv, ent.columns, {"id": kid, **row})
            created = True          # one rebuild for all of them, below: seven skills
            row = {"id": kid, **row}  # were seven rebuilds on every start and every test
        before = read_version(store, kid)
        version = write_version(store, row, skill_md, files, how="edited", note="Built into Slightly Parallel", rebuild=False)
        if before is None or version.get("n") != before.get("n"):
            touched.append(kid)
    retired = _retire_builtins(store, base)
    if created or touched or retired:
        store.rebuild()
    return touched


def _retire_builtins(store: ViewStore, base: Path) -> list[str]:
    """A built-in skill whose template folder is gone (one renamed, say
    help → sp-help) is archived, and the copies Slightly Parallel
    installed are taken out. Returns the ids retired."""
    ent = ENTITIES["skill"]
    present = {
        builtin_id(str((parse(_with_writing_rules((d / "SKILL.md").read_text(encoding="utf-8"), base))[0] or {}).get("name") or "").strip())
        for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
    }
    rows = read_rows(store.data_root / ent.csv)
    gone = [r for r in rows if r.get("source") == BUILTIN_SOURCE and r.get("status") == "active" and r.get("id") not in present]
    if not gone:
        return []
    for row in gone:
        for project in {e.get("project") for e in _installs(store) if e.get("skill_id") == row["id"]}:
            try:
                uninstall(store, row, str(project), force=True)
            except (OSError, ValueError):
                pass
    ids = {r["id"] for r in gone}

    def mutate(all_rows: list[dict[str, str]]) -> bool:
        hit = False
        for r in all_rows:
            if r.get("id") in ids and r.get("status") != "archived":
                r["status"] = "archived"; hit = True
        return hit

    rewrite_rows(store.data_root / ent.csv, ent.columns, mutate)
    return sorted(ids)


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

# What a transcript record says of skills (``uses_in_record``) and its time
# (``local_iso``) are read by the capture hook too: hookshared.py has them.


def read_uses(chats: list[tuple[str, str, Path]], sessions: list[Any]) -> list[tuple[Any, ...]]:
    """skill_uses rows from every chat's skills.jsonl, each placed in its session."""
    by_agent: dict[tuple[str, str], list[Any]] = {}
    for s in sessions:
        by_agent.setdefault((s.project, s.agent_id), []).append(s)
    out: list[tuple[Any, ...]] = []
    for project, agent_id, chat_path in chats:
        try:
            lines = (Path(chat_path).parent / USES_FILE).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        mine = by_agent.get((project, agent_id), [])
        for line in lines:
            try:
                u = json.loads(line)
            except json.JSONDecodeError:
                continue
            skill, at = str(u.get("skill") or "").strip(), str(u.get("at") or "")
            if not skill or len(at) < 16:
                continue
            raw_turn = u.get("turn")
            n = int(raw_turn) if isinstance(raw_turn, int) or (isinstance(raw_turn, str) and raw_turn.isdigit()) else 0
            sid = next((s.id for s in mine if n and any(int(t.get("n") or 0) == n for t in s.turns)), "")
            if not sid:
                day, hm = f"{at[2:4]}{at[5:7]}-{at[8:10]}", at[11:16]
                earlier = [s for s in mine if s.created_date == day and s.start_time <= hm]
                if earlier:
                    s = max(earlier, key=lambda x: x.start_time)
                    sid = s.id
                    if not n:
                        prior = [int(t.get("n") or 0) for t in s.turns if str(t.get("at") or "") <= hm]
                        n = max(prior) if prior else 0
            out.append((project, agent_id, sid, n, at, skill, str(u.get("how") or "auto")))
    return out


def backfill(store: ViewStore, claude_root: Path | None = None) -> dict[str, int]:
    """Read skill uses out of past Claude Code logs into the chats Slightly Parallel captured. Idempotent."""
    root = claude_root or Path.home() / ".claude" / "projects"
    targets = sorted(
        ((p, os.path.realpath(path)) for p, path in _targets(store).items()),
        key=lambda x: -len(x[1]),
    )
    seen: dict[Path, set[tuple[str, str]]] = {}
    scanned = added = 0
    for transcript in (sorted(root.glob("*/*.jsonl")) if root.is_dir() else []):
        scanned += 1
        try:
            with open(transcript, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"Skill"' not in line and "<command-name>" not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    uses = uses_in_record(rec)
                    raw_cwd, sid = str(rec.get("cwd") or ""), str(rec.get("sessionId") or "")
                    at = local_iso(str(rec.get("timestamp") or ""))
                    if not uses or not raw_cwd or not sid or not at:
                        continue
                    cwd = os.path.realpath(raw_cwd)
                    project = next((p for p, path in targets if cwd == path or cwd.startswith(path + os.sep)), None)
                    chat = store.data_root / "projects" / str(project) / "chats" / f"cc-{sid[:8]}"
                    if project is None or not chat.is_dir():
                        continue
                    if chat not in seen:
                        seen[chat] = _known_uses(chat)
                    lines = []
                    for name, how in uses:
                        if (at, name) in seen[chat]:
                            continue
                        seen[chat].add((at, name))
                        lines.append(json.dumps({"turn": None, "at": at, "skill": name, "how": how, "from": "transcript"}))
                    if lines:
                        with open(chat / USES_FILE, "a", encoding="utf-8") as out:
                            out.write("\n".join(lines) + "\n")
                        added += len(lines)
        except OSError:
            continue
    if added:
        store.rebuild()
    return {"transcripts": scanned, "added": added}


def _known_uses(chat: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    try:
        for line in (chat / USES_FILE).read_text(encoding="utf-8").splitlines():
            try:
                u = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((str(u.get("at") or ""), str(u.get("skill") or "")))
    except OSError:
        pass
    return keys


def usage(store: ViewStore, days: int = 30) -> dict[str, Any]:
    """Uses per skill Slightly Parallel holds, and skills that ran but are not in Slightly Parallel."""
    names = {
        str(r["name"]) for r in store.query(f"SELECT name FROM {_view()} WHERE COALESCE(name, '') <> ''")
    }
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    agg: dict[str, dict[str, Any]] = {}
    for r in store.query("SELECT skill, project, at_ts, how FROM skill_uses"):
        a = agg.setdefault(str(r["skill"]), {"uses": 0, "recent": 0, "typed": 0, "projects": set(), "last_used": ""})
        at = str(r["at_ts"] or "")
        a["uses"] += 1
        a["recent"] += int(at >= cutoff)
        a["typed"] += int(str(r["how"]) == "typed")
        if r["project"]:
            a["projects"].add(str(r["project"]))
        a["last_used"] = max(a["last_used"], at)
    shaped = {n: {**a, "projects": sorted(a["projects"])} for n, a in agg.items()}
    return {
        "days": days,
        "skills": {n: a for n, a in shaped.items() if n in names},
        "unknown": sorted(
            ({"name": n, **a} for n, a in shaped.items() if n not in names),
            key=lambda x: (-x["uses"], x["name"]),
        ),
    }


def usage_for(store: ViewStore, name: str, days: int = 30, limit: int = 50) -> dict[str, Any]:
    rows = store.query(
        "SELECT project, agent_id, session_id, turn, at_ts, how FROM skill_uses WHERE skill = ? ORDER BY at_ts DESC",
        (name,),
    ) if name else []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "uses": len(rows),
        "recent": sum(1 for r in rows if str(r["at_ts"] or "") >= cutoff),
        "days": days,
        "projects": sorted({str(r["project"]) for r in rows if r["project"]}),
        "last_used": str(rows[0]["at_ts"]) if rows else "",
        "sessions": [
            {"at": str(r["at_ts"]), "project": str(r["project"] or ""), "agent_id": str(r["agent_id"] or ""),
             "session_id": str(r["session_id"] or ""), "turn": int(r["turn"] or 0), "how": str(r["how"] or "")}
            for r in rows[:limit]
        ],
    }


# ---------------------------------------------------------------------------
# The detail
# ---------------------------------------------------------------------------


def enrich(store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
    """Lens detail for a skill: the message it was kept from, the current SKILL.md, checks, copies, usage."""
    out = keeplib.enrich(store, "skill", row)
    if "kept" not in out:  # written on the page: no message, the same versions
        versions = keeplib.read_versions(store, str(row["id"]))
        out["kept"] = {
            "kind": "skill", "from": None, "message": "", "turn": None, "before": [], "after": [],
            "versions": [v.as_dict() for v in versions],
            "current": versions[-1].as_dict() if versions else None,
        }
    current = read_version(store, str(row["id"]))
    out["skill"] = {
        "current": current,
        "checks": checks(current["skill_md"], current["files"]) if current else [],
        "installs": installs_for(store, row),
        "usage": usage_for(store, str(row.get("name") or "")),
    }
    return out


# ---------------------------------------------------------------------------
# Built-in skills are on from the start
# ---------------------------------------------------------------------------

BUILTIN_OFFERED = "skills_builtin.json"


def autoinstall_builtin(store: ViewStore) -> list[dict[str, str]]:
    """Put each built-in skill into All projects once, and keep that copy current.

    Once means once: the ids already offered are remembered, so a skill the
    operator took out stays out. A copy that is still there follows its
    template's versions; one edited on disk is left alone, like any install.
    Called only by the real server (server.py) — it writes under the home
    folder, which a test must never reach by accident.
    """
    path = store.data_root / BUILTIN_OFFERED
    try:
        offered = set((safe_read_json(path) or {}).get("offered") or [])
    except (OSError, ValueError):
        offered = set()  # never offered anything yet
    view = _view()
    rows = store.query(
        f"SELECT * FROM {view} WHERE source = ? AND status = 'active'", (BUILTIN_SOURCE,)
    )
    out: list[dict[str, str]] = []
    for row in rows:
        kid = str(row["id"])
        with _ledger(store) as ledger:
            installed = any(
                e.get("skill_id") == kid and e.get("project") == ALL_PROJECTS for e in ledger
            )
        if kid in offered and not installed:
            continue  # offered before and taken out since: the operator's call
        try:
            done = install(store, row, ALL_PROJECTS)
        except ValueError as exc:
            # A folder of the same name that is not Slightly Parallel's, or a copy
            # edited by hand. Said once per start, never forced.
            out.append({"skill": str(row.get("name") or kid), "action": "skipped", "why": str(exc)})
            continue
        offered.add(kid)
        if done["action"] != "unchanged":
            out.append({"skill": str(row.get("name") or kid), "action": done["action"], "why": ""})
    atomic_write_json(path, {"offered": sorted(offered)})
    return out

