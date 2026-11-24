"""Where a chat's folder lives: the one resolver (tk_d1d25a4d).

Every chat is a folder ``<data root>/projects/<project>/chats/<agent>/``
(chat.md, meta.json, turns.jsonl, work.jsonl, usage.jsonl …). The server,
the capture hooks and the scripts all build that path here, so the layout is
named once (tests/test_chat_paths_guard.py fails on a path built by hand).

Standard library only and no relative imports: the hooks load this file by
path (scripts/hooks/capture.py, ``_backend_module``).

The listings mirror what the code they replace did with ``Path.glob``:
hidden entries count, a symlink to a folder counts as a folder, a folder
that cannot be listed yields nothing. ``sort=False`` keeps the order the
file system lists in, which is the order glob gave.

``has=`` keeps a folder when the named entry exists, even as a broken
symlink (``os.path.lexists``), on every Python version. The globs it
replaced differed by version there: Python 3.12 and later match a literal
last part by name from the listing (a broken symlink matches), 3.11 checks
it with ``Path.exists`` (it does not). The replaced code ran on 3.12 in the
no-change proof; a chat whose meta.json is a broken symlink is listed, and
its reader then fails to read it as before.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePath
from typing import Any, Iterator

PROJECTS = "projects"
CHATS = "chats"


def project_dir(root: str | os.PathLike[str], project: str) -> Path:
    """``<root>/projects/<project>``."""
    return Path(root) / PROJECTS / project


def chats_in(project_folder: str | os.PathLike[str]) -> Path:
    """The chats folder of a project's folder: ``<project folder>/chats``."""
    return Path(project_folder) / CHATS


def chats_root(root: str | os.PathLike[str], project: str) -> Path:
    """``<root>/projects/<project>/chats``: the folder of the project's chats."""
    return chats_in(project_dir(root, project))


def chats_root_of(folder: str | os.PathLike[str]) -> Path:
    """The chats folder a chat's folder sits in (its siblings' parent)."""
    return Path(folder).parent


def folder(root: str | os.PathLike[str], project: str, agent: str) -> Path:
    """``<root>/projects/<project>/chats/<agent>``: the chat's folder."""
    return Path(root) / PROJECTS / project / CHATS / agent


def is_chat_file(rel: str | os.PathLike[str]) -> bool:
    """A path relative to the data root that lies in a project's chats
    folder: ``projects/<project>/chats/…``."""
    parts = PurePath(rel).parts
    return len(parts) >= 3 and parts[0] == PROJECTS and parts[2] == CHATS


def folders_in(chats: str | os.PathLike[str], *, skip_symlinks: bool = False) -> list[Path]:
    """The chat folders in a chats folder, sorted; [] when it is not a
    folder. Raises OSError when it cannot be listed (as ``iterdir`` does)."""
    chats = Path(chats)
    if not chats.is_dir():
        return []
    return sorted(p for p in chats.iterdir() if p.is_dir() and not (skip_symlinks and p.is_symlink()))


def _listed(path: Path, sort: bool) -> list[Path]:
    """The folders in ``path`` (a symlink to a folder counts); [] when it
    cannot be listed — glob's way."""
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError:
        return []
    out: list[Path] = []
    for e in entries:
        try:
            if e.is_dir():
                out.append(path / e.name)
        except OSError:
            continue
    return sorted(out) if sort else out


def iter_chats(root: str | os.PathLike[str], project: str | None = None, *, has: str | None = None,
               sort: bool = True) -> Iterator[tuple[str, str, Path]]:
    """``(project, agent, folder)`` for every chat folder under ``root``, or
    under one project. ``has`` keeps only the folders where that entry
    exists; ``sort`` orders by project, then agent (else the listing's own
    order)."""
    if project is None:
        projects = _listed(Path(root) / PROJECTS, sort)
    else:
        projects = [project_dir(root, project)]
    for proj in projects:
        for f in _listed(chats_in(proj), sort):
            if has is None or os.path.lexists(f / has):
                yield proj.name, f.name, f


def folders_of(root: str | os.PathLike[str], agent: str, *, has: str | None = None) -> Iterator[tuple[str, Path]]:
    """``(project, folder)`` for every project that has a chat folder named
    ``agent``, by project; with ``has``, only where that entry exists."""
    for proj in _listed(Path(root) / PROJECTS, True):
        f = folder(root, proj.name, agent)
        if os.path.lexists(f / has) if has is not None else f.is_dir():
            yield proj.name, f


def project_of(folder: str | os.PathLike[str], meta: dict[str, Any] | None = None) -> str:
    """The chat's project: meta.json's ``project`` when it names one, else
    the project folder the chat sits in. ``meta`` is the chat's meta.json
    when the caller has read it already."""
    folder = Path(folder)
    if meta is None:
        try:
            got = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            got = None
        meta = got if isinstance(got, dict) else {}
    named = meta.get("project")
    return named if named else folder.parent.parent.name
