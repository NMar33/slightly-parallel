"""File-lens entries — the agent's per-path judgment, with the mechanics
filled in from git.

A file entry is written by the agent after a scan (``trigger_lens: scan``).
Its ``paths`` list carries what only the agent knows — importance, blast
radius, coverage, ``why`` — while everything git can answer (action, line
deltas, the diff itself) is filled here so the agent never has to count.

Range resolution, in order:

* ``commit_from`` / ``commit_to`` given in the body — used as-is;
* otherwise ``commit_from`` = the previous entry's ``commit_to`` for the
  same project (read from its frontmatter), ``commit_to`` = HEAD, and the
  diff is taken against the *working tree* so uncommitted work counts
  (``dirty: true`` records that);
* no previous entry → ``commit_from`` = HEAD (uncommitted work since the
  last commit), or git's empty tree when the repo has no commits yet, so a
  fresh ``git init`` fills too. ``range_basis`` records which rule applied.

Every git failure is swallowed — a missing repo path or a non-git project
degrades to the agent's own numbers, never to an error; ``git_status``
says which happened so the reader is not misled.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


from . import frontmatter
from .csvio import read_rows
from .db import ViewStore
from .gitwork import git
from .docs_md import resolve_under
from .file_safety import given_path

_EMPTY_TREE = "4b825dc642cb6eb9a0060e64d5c3f2dd6f2c8b8f"  # git's well-known empty tree
_L4_MAX_LINES = 80
_ASSESSMENT_KEYS = (
    "importance", "blast_radius", "novelty", "test_coverage",
    "security_surface", "agent_confidence", "tags", "why",
)


# ---------------------------------------------------------------------------
# paths normalisation
# ---------------------------------------------------------------------------

def normalize_paths(raw: Any) -> list[dict[str, Any]]:
    """Coerce the posted ``paths`` into a clean list of path records.

    Strings become ``{path}``; records without a path are dropped; ``action``
    defaults to ``modified``. Unknown keys are kept — the heatmap ignores
    what it does not score.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        rec = dict(item)
        rec["path"] = path
        rec["action"] = str(rec.get("action") or "modified")
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# git — the one wrapper (gitwork.git), imported under its own name.
# ---------------------------------------------------------------------------

def project_path(store: ViewStore, project: str) -> Path | None:
    """The registered working directory of ``project`` (Setup → integrations)."""
    for row in read_rows(store.data_root / "integrations.csv"):
        if row.get("project") != project:
            continue
        p = given_path(row.get("path"))
        if p is not None and p.is_dir():
            return p
    return None


def _is_repo(path: Path) -> bool:
    return bool(git(path, "rev-parse", "--is-inside-work-tree"))


def project_repo(store: ViewStore, project: str) -> Path | None:
    """The registered working directory of ``project`` when it is a git repo."""
    p = project_path(store, project)
    return p if p is not None and _is_repo(p) else None


def previous_entry(store: ViewStore, project: str) -> dict[str, Any] | None:
    return store.query_one(
        "SELECT id, md_ref FROM files_mutual WHERE project = ? "
        "ORDER BY created_date DESC, created_time DESC, id DESC LIMIT 1",
        (project,),
    )


def file_frontmatter(store: ViewStore, md_ref: str) -> dict[str, Any]:
    md_path = resolve_under(store.data_root, md_ref or "")
    if md_path is None or not md_path.exists():
        return {}
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return frontmatter.meta(text)[0] or {}


def _match(paths: list[dict[str, Any]], git_path: str) -> dict[str, Any] | None:
    for rec in paths:
        if rec["path"] == git_path:
            return rec
    tail = [r for r in paths if git_path.endswith("/" + r["path"].lstrip("./"))
            or r["path"].endswith("/" + git_path)]
    return tail[0] if len(tail) == 1 else None


def git_fill(
    repo: Path, paths: list[dict[str, Any]], commit_from: str, commit_to: str | None,
) -> dict[str, Any]:
    """Fill missing ``lines_add``/``lines_del``/``action`` from git; return
    ``{filled: n, l4: str}`` (l4 = ``git diff --stat`` over the range)."""
    rng = [commit_from, commit_to] if commit_to else [commit_from]
    numstat = git(repo, "diff", "--numstat", *rng)
    status = git(repo, "diff", "--name-status", *rng)
    # A repo with no commits has no diff base at all (even the empty tree is
    # "bad object" there): every listed file that exists is new. A diff that
    # failed in a repo that has commits is not that: every file was called
    # created, at its whole length.
    no_base = numstat is None and git(repo, "rev-parse", "--verify", "--quiet", "HEAD") is None
    numstat = numstat or ""

    filled = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add, dele, gpath = parts[0], parts[1], parts[-1]
        rec = _match(paths, gpath)
        if rec is None:
            continue
        if rec.get("lines_add") in (None, "") and add.isdigit():
            rec["lines_add"] = int(add)
            filled += 1
        if rec.get("lines_del") in (None, "") and dele.isdigit():
            rec["lines_del"] = int(dele)

    if status:
        letters = {"A": "created", "M": "modified", "D": "deleted", "R": "renamed"}
        for line in status.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            rec = _match(paths, parts[-1])
            if rec is not None and not rec.get("_action_given"):
                rec["action"] = letters.get(parts[0][:1], rec.get("action", "modified"))

    # Files the agent created but has not `git add`ed yet (or any listed file
    # when the repo has no commits): count their lines as new.
    if not commit_to:
        untracked = git(repo, "ls-files", "--others", "--exclude-standard") or ""
        fresh = {g.strip() for g in untracked.splitlines() if g.strip()}
        for rec in paths:
            if rec.get("lines_add") not in (None, ""):
                continue
            gpath = rec["path"]
            if not (no_base or gpath in fresh or any(f.endswith("/" + gpath) for f in fresh)):
                continue
            try:
                with open(repo / gpath, encoding="utf-8", errors="replace") as fh:
                    n = sum(1 for _ in fh)
            except OSError:
                continue
            rec["lines_add"], rec["lines_del"] = n, 0
            rec["action"] = "created"
            filled += 1

    only = [r["path"] for r in paths]
    stat = git(repo, "diff", "--stat", *rng, "--", *only) if only and not no_base else ""
    l4 = "\n".join((stat or "").rstrip().splitlines()[:_L4_MAX_LINES])
    return {"filled": filled, "l4": l4}


# ---------------------------------------------------------------------------
# entry point used by the file pre-create hook
# ---------------------------------------------------------------------------

# What a commit named in a body may look like: a hash, a ref, HEAD~2, a
# tag — never an option. ``--output=/any/path`` given as ``commit_to`` reached
# ``git diff`` as its own argument and wrote a file wherever the server could.
_REV_RE = re.compile(r"[0-9A-Za-z@][0-9A-Za-z._/~^@{}+-]{0,127}")


def _checked_rev(body: dict, key: str) -> str:
    raw = str(body.get(key) or "")
    if raw and not _REV_RE.fullmatch(raw):
        raise ValueError(f"{key} is not a commit or ref: {raw[:40]!r}")
    return raw


def prepare_file_entry(store: ViewStore, body: dict) -> None:
    """Chain, normalise and git-fill one file entry in place."""
    project = str(body.get("project") or "")
    for key in ("commit_from", "commit_to"):
        _checked_rev(body, key)
    prev = previous_entry(store, project) if project else None
    if not body.get("prev_file_id") and prev:
        body["prev_file_id"] = prev.get("id", "")

    paths = normalize_paths(body.get("paths"))
    for rec in paths:
        rec["_action_given"] = "action" in rec and rec["action"] != "modified"
    body["paths"] = paths

    if paths and not body.get("files_important_n"):
        body["files_important_n"] = len(paths)

    registered = project_path(store, project) if project else None
    repo = registered if registered is not None and _is_repo(registered) else None
    if repo is None:
        body["git_status"] = "not-a-repo" if registered is not None else "no-path"
    else:
        commit_from = str(body.get("commit_from") or "")
        commit_to = str(body.get("commit_to") or "")
        basis = "given" if commit_from else ""
        if not commit_from and prev:
            commit_from = str(file_frontmatter(store, prev.get("md_ref", "")).get("commit_to") or "")
            basis = "previous-entry" if commit_from else ""
        head = (git(repo, "rev-parse", "HEAD") or "").strip()
        if commit_from and commit_from != _EMPTY_TREE and git(
            repo, "rev-parse", "--verify", "--quiet", commit_from + "^{commit}",
        ) is None:
            # The commit is gone (a rebase, an amend and a gc) or never was:
            # count from HEAD rather than call every file new.
            commit_from, basis = "", ""
        if not commit_from:
            # First entry: everything since the last commit — or, in a repo
            # with no commits yet, everything there is.
            commit_from, basis = (head, "head") if head else (_EMPTY_TREE, "empty-tree")
        result = git_fill(repo, paths, commit_from, commit_to or None)
        if not body.get("l4") and result["l4"]:
            body["l4"] = "```\n" + result["l4"] + "\n```"
        body["git_filled"] = result["filled"]
        body["git_status"] = "filled"
        body["range_basis"] = basis
        body["commit_from"] = commit_from
        body["commit_to"] = commit_to or head
        if not commit_to:
            body["dirty"] = bool((git(repo, "status", "--porcelain") or "").strip())

    for rec in paths:
        rec.pop("_action_given", None)


def assessment_summary(paths: list[dict[str, Any]]) -> dict[str, int]:
    """How many paths carry any judgment fields at all — for response warnings."""
    judged = sum(1 for r in paths if any(r.get(k) not in (None, "", []) for k in _ASSESSMENT_KEYS))
    return {"paths": len(paths), "judged": judged}
