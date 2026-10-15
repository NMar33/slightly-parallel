"""What Slightly Parallel can say about a project folder with no model.

The architecture page has two layers. This is the first: facts a program
can compute — is the folder alive, how big is it, which folders changed
when, what the newest files and the recent commits are, which repositories
sit inside it, how it is built. A model guessing these was the first source
of wrong statements in the page trials (a project idle for sixteen weeks
called "active"; a nested repository with a live remote called "not found").

The second layer, the agent's claims, is written against these facts
(archpage.py). Everything here reads the project's registered folder and
never writes to it.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import folderwalk, gitwork
from .db import ViewStore
from .file_entries import project_path

MAX_FILES = folderwalk.MAX_FILES
NEWEST = 30
SUBJECTS = 60
ACTIVE_WEEKS, PAUSED_WEEKS = 2, 8


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def standing(last_change: float, now: float) -> str:
    """active · paused · dormant, from the date of the last file change."""
    weeks = (now - last_change) / 604800
    word = "active" if weeks < ACTIVE_WEEKS else "paused" if weeks < PAUSED_WEEKS else "dormant"
    return f"{word} — last file change {_day(last_change)}, {weeks:.0f} weeks before today"


def _repo_facts(repo: Path, subjects: int) -> dict[str, Any]:
    return {
        "commits": int(gitwork.git(repo, "rev-list", "--count", "HEAD") or 0),
        "first_commit": (gitwork.git(repo, "log", "--reverse", "--date=short", "--format=%ad") or "").splitlines()[:1],
        "last_commit": gitwork.git(repo, "log", "-1", "--date=short", "--format=%ad %s") or "",
        "remote": (gitwork.git(repo, "remote", "-v") or "").splitlines()[:1],
        "tags": (gitwork.git(repo, "tag") or "").splitlines()[-5:],
        "uncommitted_files": len((gitwork.git(repo, "status", "--short") or "").splitlines()),
        "recent_commit_subjects": (gitwork.git(repo, "log", f"-{subjects}", "--date=short", "--format=%ad %s") or "").splitlines(),
    }


def scan_folder(root: Path, now: float | None = None) -> dict[str, Any]:
    """How alive the folder is, and what it holds — from one walk
    (folderwalk.py), the same walk the map reads."""
    now = now or time.time()
    seen = folderwalk.walk(root)
    return {
        "today": _day(now),
        "folder": str(root),
        "files": seen.files,
        "standing": standing(seen.last_change, now) if seen.files else "empty",
        "file_types": seen.suffixes.most_common(8),
        "top_level": sorted(
            ({"name": k, "files": int(v["files"]), "mb": round(v["bytes"] / 1e6, 1), "last_change": _day(v["last"])}
             for k, v in seen.by_top.items()),
            key=lambda r: r["last_change"], reverse=True),
        "newest_files": [{"path": p, "changed": _day(t)} for t, p in seen.newest[:NEWEST]],
        "git": _repo_facts(root, SUBJECTS) if gitwork.git(root, "rev-parse", "--git-dir") is not None else None,
        "nested_repositories": [{"path": rel, **_repo_facts(root / rel, 15)} for rel in seen.nested],
        "build_and_ci_files": seen.build_files(),
    }


_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_SECONDS = 120


def facts(store: ViewStore, project: str) -> dict[str, Any]:
    """The computed layer for one project, plus what only Slightly Parallel knows."""
    root = project_path(store, project)
    if root is None:
        return {"project": project, "folder": "", "note": "No folder is registered for this project (Setup)."}
    key = f"{store.data_root}|{project}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    out = {"project": project, **scan_folder(root)}
    # What a reader of the folder cannot know: where the real data lives, and
    # what Slightly Parallel has recorded about the project.
    out["slightly_parallel"] = {
        "data_root": str(store.data_root),
        "data_root_is_inside_the_folder": Path(store.data_root).resolve().is_relative_to(Path(root).resolve()),
        "open_tasks": [
            {"id": r["id"], "title": r.get("title") or "", "status": r.get("status") or ""}
            for r in store.query(
                "SELECT id, title, status FROM tasks_mutual WHERE project = ? AND status IN "
                "('doing','review','todo','next') ORDER BY status LIMIT 25", (project,))
        ],
        "recent_decisions": [
            {"id": r["id"], "date": r.get("created_date") or "", "decision": r.get("decision_text") or "",
             "weight": r.get("weight") or ""}
            for r in store.query(
                "SELECT id, created_date, decision_text, weight FROM decisions_mutual WHERE project = ? "
                "ORDER BY created_date DESC, created_time DESC LIMIT 10", (project,))
        ],
    }
    _cache[key] = (time.time(), out)
    return out


def forget() -> None:
    _cache.clear()
