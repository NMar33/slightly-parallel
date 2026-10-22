"""Artifacts — folders an agent writes under the Slightly Parallel directory.

An artifact is a result worth keeping in one place: a dataset, a document,
a page, an app. The agent writes the folder itself — any size, any files —
at ``<data_root>/projects/<project>/artifacts/<name>/``, with ``ARTIFACT.md`` on top
(a ``---`` header with name, kind and description, then any text) and the
files beside it. One small MCP tool, ``artifact_write``, makes the record:
it checks the folder, refreshes the header, and fills the row the Artifacts
page lists. Calling it again after edits is the update.

The folder is the artifact. The row is its record. Slightly Parallel reads the
folder the way it reads chat logs: nothing is copied, and a hand edit in
the folder is what the page shows next.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import keeplib
from .csvio import append_row
from .db import ViewStore
from .docs_md import build_detail, read_detail, resolve_under, safe_ref_part
from .entities import ENTITIES
from .file_safety import atomic_write
from . import limits
from .skilllib import MAX_NAME, NAME_RE, parse

KINDS: tuple[str, ...] = ("dataset", "document", "page", "app", "other")
ROOT_DIR = "artifacts"
MANIFEST = "ARTIFACT.md"
# Folders that are never part of an artifact: dependencies, build output,
# version control, caches. They are skipped in every scan and preview.
SKIP_DIRS = frozenset({"node_modules", ".git", "dist", "build", "__pycache__", ".venv"})
MAX_DESCRIPTION = 1024
PREVIEW_ROWS = 5
TREE_DEPTH = 3
TREE_LIMIT = 200
DOCUMENT_MAX_CHARS = limits.MAX_DOCUMENT_CHARS
_PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _view() -> str:
    return ENTITIES["artifact"].view


# ---------------------------------------------------------------------------
# The folder
# ---------------------------------------------------------------------------


def root(store: ViewStore) -> Path:
    """The projects folder: every project keeps its artifacts inside its own
    folder, ``projects/<project>/artifacts/``, so everything about a project
    is in one place."""
    return store.data_root / "projects"


def project_root(store: ViewStore, project: str) -> Path:
    if not _PROJECT_RE.match(project or ""):
        raise ValueError(f"not a project code: {project!r}")
    return root(store) / project / ROOT_DIR


def folder(store: ViewStore, project: str, name: str) -> Path:
    """Where an artifact lives — the only place. A name or project that
    could leave the project's artifacts folder is refused."""
    base = project_root(store, project)
    if not name or len(name) > MAX_NAME or not NAME_RE.match(name):
        raise ValueError(
            "an artifact name is lowercase letters, digits and single hyphens, "
            f"up to {MAX_NAME} characters — the folder name under projects/<project>/artifacts/"
        )
    resolved = base.resolve()
    dest = (resolved / name).resolve()
    if resolved not in dest.parents:
        raise ValueError(f"{name!r} would leave the project's artifacts folder")
    return dest


def _is_text(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def scan(dest: Path) -> list[dict[str, Any]]:
    """Every file of the folder: relative path, size, whether it is text.
    Dependencies, build output and dotfiles are not the artifact."""
    out: list[dict[str, Any]] = []
    if not dest.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(dest):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            if p.is_symlink() or not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            out.append({"path": p.relative_to(dest).as_posix(), "bytes": size, "is_text": _is_text(p)})
    return out


def read_manifest(dest: Path) -> tuple[dict[str, Any] | None, str]:
    """The ``---`` header of ARTIFACT.md and the text under it."""
    try:
        text = (dest / MANIFEST).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, ""
    meta, body = parse(text)
    return meta, body


def _render_manifest(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key in ("id", "name", "kind", "description", "project", "run", "updated"):
        if key in meta and str(meta[key]) != "":
            lines.append(f"{key}: {json.dumps(str(meta[key]), ensure_ascii=False)}")
    for key, value in meta.items():
        if key not in ("id", "name", "kind", "description", "project", "run", "updated"):
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=False)}")
    lines.append("---")
    text = "\n".join(lines) + "\n"
    if body.strip():
        text += "\n" + body.strip() + "\n"
    return text


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _set_fields(store: ViewStore, kid: str, fields: dict[str, Any]) -> None:
    keeplib._set_fields(store, "artifact", kid, fields)


def _checked(
    store: ViewStore, project: str, name: str, kind: str, description: str, kid: str = "",
    then: str = "call again",
) -> tuple[str, str, str, Path]:
    """Every check a record must pass, before anything is written: the
    name, kind, description and folder as they will be kept. Raises
    ValueError naming the first problem."""
    name = (name or "").strip()
    kind = (kind or "").strip().lower()
    description = " ".join((description or "").split())
    if kind not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(KINDS)}")
    if not description:
        raise ValueError("an artifact needs a description — what it is and what it is for, one or two sentences")
    if len(description) > MAX_DESCRIPTION:
        raise ValueError(f"the description is at most {MAX_DESCRIPTION} characters")
    dest = folder(store, project, name)  # raises on a bad name
    if not dest.is_dir():
        raise ValueError(f"the folder does not exist yet: write it at {dest}, then {then}")
    if not [f for f in scan(dest) if f["path"] != MANIFEST]:
        raise ValueError(f"the folder holds nothing beside {MANIFEST}: put the files in {dest} first")
    clash = store.query_one(
        f"SELECT id FROM {_view()} WHERE name = ? AND project = ? AND id <> ?", (name, project, kid),
    )
    if clash is not None:
        raise ValueError(f"another artifact of {project} is already named {name}: {clash['id']}")
    return name, kind, description, dest


def write_record(
    store: ViewStore, row: dict[str, Any], *, name: str, kind: str, description: str,
    actor: str = "", now: datetime | None = None,
) -> dict[str, Any]:
    """The tool's work: check the folder, refresh the header, fill the row.

    Returns what the row now holds. Raises ValueError naming the problem
    when the folder is missing or empty, or the name or kind is wrong.
    """
    kid = str(row["id"])
    project = str(row.get("project") or "")
    name, kind, description, dest = _checked(store, project, name, kind, description, kid)

    at = now or datetime.now()
    stamp = at.strftime("%Y-%m-%dT%H:%M:%S")
    meta, body = read_manifest(dest)
    meta = dict(meta or {})
    meta.update({"id": kid, "name": name, "kind": kind, "description": description,
                 "project": project, "updated": stamp})
    atomic_write(dest / MANIFEST, _render_manifest(meta, body))
    files = scan(dest)

    fields: dict[str, Any] = {
        "name": name, "kind": kind, "description": description, "status": "active",
        "path": str(dest), "files_n": len(files), "bytes": sum(int(f["bytes"]) for f in files),
        "updated_at": stamp,
    }
    if str(row.get("source") or "") != "captured" or not str(row.get("l1") or "").strip():
        fields["l1"] = name
    _set_fields(store, kid, fields)
    md_ref = str(row.get("md_ref") or "")
    doc = resolve_under(store.data_root, md_ref)
    if doc is not None:
        _l2, l3, l4 = read_detail(store.data_root, md_ref)
        fresh = store.query_one(f"SELECT * FROM {_view()} WHERE id = ?", (kid,)) or row
        base = {k: v for k, v in fresh.items() if k != "id" and v not in (None, "")}
        doc.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(doc, build_detail({**base, "l2": description, "l3": l3, "l4": l4}, kid))
    return store.query_one(f"SELECT * FROM {_view()} WHERE id = ?", (kid,)) or {**row, **fields}


def create_written(
    store: ViewStore, *, project: str, name: str, kind: str, description: str,
    tags: str = "", now: datetime | None = None,
) -> str:
    """A folder the operator wrote by hand, registered on the page. Returns the id."""
    ent = ENTITIES["artifact"]
    at = now or datetime.now()
    date, time = f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}", at.strftime("%H:%M")
    kid = ent.id_prefix + hashlib.sha256(f"written|{project}|{name}|{at.isoformat()}".encode()).hexdigest()[:8]
    md_ref = (
        f"{ent.detail_dir}/{date.replace('-', '')}-{time.replace(':', '')}__"
        f"{safe_ref_part((project or 'none').lower())}__operator__{kid}.md"
    )
    row: dict[str, Any] = {
        "created_date": date, "created_time": time, "project": project, "agent_id": "operator",
        "l1": name, "name": "", "kind": "", "description": "", "status": "draft", "path": "",
        "files_n": 0, "bytes": 0, "updated_at": "", "md_ref": md_ref, "source": "written",
        "session_id": "", "source_turn": 0, "tags": tags,
    }
    # Everything is checked before a row exists, so a refusal leaves nothing
    # behind: the record's own checks too, which used to run only after the
    # row was written and left a draft on the page for each refused try.
    _checked(store, project, name, kind, description, kid, then="register it")
    doc = store.data_root / md_ref
    doc.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(doc, build_detail(row, kid))
    append_row(store.data_root / ent.csv, ent.columns, {"id": kid, **row})
    store.rebuild()
    write_record(store, {"id": kid, **row}, name=name, kind=kind, description=description, now=at)
    return kid


# ---------------------------------------------------------------------------
# What the page reads
# ---------------------------------------------------------------------------


def fingerprint(store: ViewStore) -> str:
    """The artifact folders as they are right now, in 16 characters — for the
    ETag, because the store never stats them."""
    h = hashlib.sha256()
    projects = root(store)
    bases = sorted(p / ROOT_DIR for p in projects.iterdir() if p.is_dir()) if projects.is_dir() else []
    for base in bases:
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                except OSError:
                    continue
                h.update(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode())
    return h.hexdigest()[:16]


def _folder_of(store: ViewStore, row: dict[str, Any]) -> Path | None:
    raw = str(row.get("path") or "")
    if raw:
        p = Path(raw)
        base = root(store).resolve()
        try:
            r = p.resolve()
            # projects/<project>/artifacts/<name>: two levels under a project, in its artifacts folder.
            if base in r.parents and r.parent.name == ROOT_DIR and r.parent.parent.parent == base and p.is_dir():
                return p
        except OSError:
            return None
    try:
        p = folder(store, str(row.get("project") or ""), str(row.get("name") or ""))
    except ValueError:
        return None
    return p if p.is_dir() else None


def tree(dest: Path, depth: int = TREE_DEPTH, limit: int = TREE_LIMIT) -> list[dict[str, Any]]:
    """The folder as a flat list of entries with their depth, capped."""
    out: list[dict[str, Any]] = []
    if not dest.is_dir():
        return out
    base_depth = len(dest.parts)
    for dirpath, dirnames, filenames in os.walk(dest):
        level = len(Path(dirpath).parts) - base_depth
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        if level >= depth:
            dirnames[:] = []
        rel_dir = Path(dirpath).relative_to(dest).as_posix()
        for d in dirnames:
            out.append({"path": f"{rel_dir}/{d}" if rel_dir != "." else d, "dir": True, "depth": level})
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            try:
                size = p.stat().st_size
            except OSError:
                continue
            out.append({"path": f"{rel_dir}/{fn}" if rel_dir != "." else fn, "dir": False,
                        "depth": level, "bytes": size})
        if len(out) >= limit:
            return out[:limit]
    return out


def _table_preview(path: Path) -> dict[str, Any]:
    """Fields, row count and the first rows of a CSV or JSONL file. A file
    that cannot be read is reported in ``error``, never raised."""
    out: dict[str, Any] = {"file": path.name, "fields": [], "rows": 0, "sample": []}
    try:
        if path.suffix.lower() == ".jsonl":
            fields: list[str] = []
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        out["error"] = f"line {out['rows'] + 1}: {exc.msg}"
                        break
                    out["rows"] += 1
                    if isinstance(rec, dict):
                        for k in rec:
                            if k not in fields:
                                fields.append(str(k))
                        if len(out["sample"]) < PREVIEW_ROWS:
                            out["sample"].append({k: _short(v) for k, v in rec.items()})
            out["fields"] = fields
        else:
            with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                out["fields"] = [h.strip() for h in header]
                for raw in reader:
                    out["rows"] += 1
                    if len(out["sample"]) < PREVIEW_ROWS:
                        out["sample"].append({h: _short(v) for h, v in zip(out["fields"], raw)})
    except (OSError, csv.Error) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _short(v: Any, n: int = 200) -> Any:
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + "…"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return _short(json.dumps(v, ensure_ascii=False))


def preview(store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
    """What the page shows for this kind, read from the folder right now."""
    dest = _folder_of(store, row)
    kind = str(row.get("kind") or "other")
    if dest is None:
        return {"kind": kind, "missing": True}
    meta, body = read_manifest(dest)
    out: dict[str, Any] = {"kind": kind, "missing": False, "readme": body.strip()}
    files = scan(dest)
    if kind == "dataset":
        tables = [f for f in files if f["path"].lower().endswith((".csv", ".jsonl"))]
        out["tables"] = [_table_preview(dest / f["path"]) for f in tables[:20]]
    elif kind == "document":
        docs = [f for f in files if f["path"].lower().endswith(".md") and f["path"] != MANIFEST]
        if docs:
            biggest = max(docs, key=lambda f: int(f["bytes"]))
            try:
                text = (dest / biggest["path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            out["document"] = {"file": biggest["path"], "text": text[:DOCUMENT_MAX_CHARS],
                               "truncated": len(text) > DOCUMENT_MAX_CHARS}
        else:
            out["document"] = {"file": MANIFEST, "text": body.strip(), "truncated": False}
    elif kind == "page":
        htmls = [f["path"] for f in files if f["path"].lower().endswith((".html", ".htm"))]
        entry = next((h for h in htmls if h.lower() in ("index.html", "index.htm")), None)
        if entry is None and len(htmls) == 1:
            entry = htmls[0]
        out["entry"] = entry
        out["pages"] = htmls
    elif kind == "app":
        out["tree"] = tree(dest)
        out["run"] = str((meta or {}).get("run") or "")
    else:
        out["tree"] = tree(dest)
    return out


def enrich(store: ViewStore, row: dict[str, Any]) -> dict[str, Any]:
    """Lens detail for an artifact: the message it was kept from, and its folder."""
    out = keeplib.enrich(store, "artifact", row)
    if "kept" not in out:
        out["kept"] = {"kind": "artifact", "from": None, "message": "", "turn": None,
                       "before": [], "after": [], "versions": [], "current": None}
    dest = _folder_of(store, row)
    meta, body = read_manifest(dest) if dest else (None, "")
    out["artifact"] = {
        "path": str(dest) if dest else str(row.get("path") or ""),
        "exists": dest is not None,
        "files": scan(dest) if dest else [],
        "manifest": {"meta": meta or {}, "body": body.strip()},
        "preview": preview(store, row),
    }
    return out
