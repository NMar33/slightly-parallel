"""What a scan is written from: the project's work since its last scan.

A scan says what changed since the last one. The agent used to work that
out itself, with git by hand, and count `files_n` and the lines by hand
too. The server has all of it: the last scan's time, the repository the
agent runs in, and the log. ``material`` hands it over, with the counters
counted, and ``instructions`` carries how to write the three entries a scan
is made of — the contract's own parts, so the text has one source.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from . import frontmatter, gitwork, sessions
from .db import ViewStore
from .date_utils import iso_of
from .file_entries import project_repo

PARTS = ("31-writing.md", "40-scan.md", "41-file-entry.md", "42-architecture.md")
MAX_COMMITS = 200
MAX_FILES = 300


def _stamp(date: str, time: str) -> datetime | None:
    """YYMM-DD + HH:MM → a local datetime (date_utils reads the day)."""
    iso = iso_of(date)
    if not iso:
        return None
    try:
        return datetime.fromisoformat(f"{iso}T{(time or '00:00')[:5]}")
    except ValueError:
        return None


def last_scan(store: ViewStore, project: str, agent_id: str = "") -> dict[str, Any] | None:
    """The agent's last scan of the project: a scan's window is one agent's
    work since its own previous scan, so two agents on one project never
    close each other's window. Without an agent id: the project's last."""
    if agent_id:
        rows = store.query(
            "SELECT id, created_date, created_time, l1 FROM scans WHERE project = ? AND agent_id = ? "
            "ORDER BY created_date DESC, created_time DESC LIMIT 1",
            (project, agent_id),
        )
        return rows[0] if rows else None
    rows = store.query(
        "SELECT id, created_date, created_time, l1 FROM scans WHERE project = ? "
        "ORDER BY created_date DESC, created_time DESC LIMIT 1",
        (project,),
    )
    return rows[0] if rows else None


def _stamps_since(store: ViewStore, agent_id: str, since: datetime | None) -> list[dict[str, Any]] | None:
    """This chat's work stamps after ``since``; None when the chat has none."""
    chat = sessions.chat_path(store, agent_id) if agent_id else None
    if chat is None:
        return None
    stamps = gitwork.read_stamps(chat)
    if not stamps:
        return None
    out = []
    for stamp in stamps.values():
        at = str(stamp.get("at") or "")
        try:
            when = datetime.fromisoformat(at[:19]) if at else None
        except ValueError:
            when = None
        if since is not None and when is not None and when <= since:
            continue
        out.append(stamp)
    return out


def chat_touched(store: ViewStore, agent_id: str, since: datetime | None, key: str = "touched") -> list[str]:
    """Files from this chat's stamps after ``since``, in the order first seen.
    ``touched``: named by the turn's tool calls, the helpers' included.
    ``changed``: found changed in the folder by the hook's walk, where there
    is no git — a shell command's edits too, and anyone else's."""
    out: list[str] = []
    for stamp in _stamps_since(store, agent_id, since) or []:
        for path in stamp.get(key) or []:
            if isinstance(path, str) and path and path not in out:
                out.append(path)
    return out


def chat_commits(store: ViewStore, agent_id: str, since: datetime | None) -> set[str] | None:
    """The shas this chat's turns made after ``since``, from the hook's
    stamps (work.jsonl: the commits reachable from a turn's HEAD and not
    from the previous one). None when the chat has no stamps at all — an
    older chat, or a repository the hook never saw — so the caller can fall
    back to the project's commits and say so."""
    stamps = _stamps_since(store, agent_id, since)
    if stamps is None:
        return None
    if not any(stamp.get("head") for stamp in gitwork.read_stamps(sessions.chat_path(store, agent_id)).values()):
        return None     # stamps without git: files only, no commits to tell apart
    chat = sessions.chat_path(store, agent_id)
    repo = gitwork.repo_for_chat(chat) if chat is not None else None
    by_sha = {c.sha: c for c in gitwork.commits(repo)} if repo is not None else {}
    out: set[str] = set()
    for stamp in stamps:
        for sha in stamp.get("commits") or []:
            if not (isinstance(sha, str) and sha):
                continue
            c = by_sha.get(sha)
            # A stamp lists every commit HEAD gained in the turn, another
            # agent's too: keep the ones this chat made (gitwork.owns_commit).
            if c is None or chat is None or gitwork.owns_commit(chat, c, stamp):
                out.add(sha)
    return out


def _repo(store: ViewStore, project: str, agent_id: str) -> Path | None:
    """The project's repository: the folder Setup registered, which is what a
    day's numbers count (daynumbers.py). Only when none is registered does the
    asking agent's own folder stand in, then the project's latest agent's."""
    registered = project_repo(store, project)
    if registered is not None:
        return registered
    chat = sessions.chat_path(store, agent_id) if agent_id else None
    if chat is not None:
        repo = gitwork.repo_for_chat(chat)
        if repo is not None:
            return repo
    agents = sorted(
        (a for a in store.agents() if str(a.get("project") or "") == project),
        key=lambda a: str(a.get("last_active") or ""), reverse=True,
    )
    for a in agents[:20]:
        path = Path(a.get("_chat_path") or "")
        if path.exists():
            repo = gitwork.repo_for_chat(path)
            if repo is not None:
                return repo
    return None


def _uncommitted(repo: Path) -> list[dict[str, Any]]:
    raw = gitwork.git(repo, "diff", "--numstat", "HEAD") or ""
    out = []
    for line in raw.splitlines():
        cols = line.split("\t")
        if len(cols) == 3:
            a, d, path = cols
            out.append({"path": path, "lines_add": int(a) if a.isdigit() else 0,
                        "lines_del": int(d) if d.isdigit() else 0})
    return out


MARKS_FILE = "scan_marks.json"
MARKS_KEPT = 500


def mark(store: ViewStore, scan_id: str, project: str, agent_id: str) -> None:
    """Remember what the working tree held when this scan was written.

    A scan may describe work that is not committed yet. Those files get
    committed minutes later, and the next scan must not count them again.
    Never fails the scan: no repository, no mark.
    """
    from .file_safety import edit_json

    try:
        repo = _repo(store, project, agent_id)
        if repo is None:
            return
        entry = {"head": gitwork.head(repo), "uncommitted": sorted(f["path"] for f in _uncommitted(repo))}
        untracked = gitwork.git(repo, "ls-files", "--others", "--exclude-standard") or ""
        entry["uncommitted"] = sorted(set(entry["uncommitted"]) | {u for u in untracked.splitlines() if u})
        # The one read-modify-write cycle (file_safety.edit_json).
        edit_json(store.data_root / MARKS_FILE, lambda data: _keep_newest(
            {**{k: v for k, v in data.items() if k != scan_id}, scan_id: entry}))
    except (OSError, ValueError):
        return


def _keep_newest(data: dict[str, Any]) -> dict[str, Any]:
    """The newest ``MARKS_KEPT`` marks. Only a project's last scan is ever
    read again, and the file was read and rewritten whole on every scan
    while it grew by one mark each time, forever."""
    if len(data) <= MARKS_KEPT:
        return data
    return dict(list(data.items())[-MARKS_KEPT:])


def _described(store: ViewStore, scan_id: str, commits: list) -> set[str]:
    """The commits the last scan already described: made right after it,
    holding only files that were uncommitted when it was written. Walks
    oldest first and stops at the first commit with any other file; each
    file is used once, so later work on the same file counts."""
    from .file_safety import safe_read_json

    try:
        left = set(((safe_read_json(store.data_root / MARKS_FILE) or {}).get(scan_id) or {}).get("uncommitted") or [])
    except (OSError, ValueError):
        return set()
    out: set[str] = set()
    for c in sorted(commits, key=lambda c: c.at):
        files = {p for p, _, _ in c.files}
        if not left or not files or not files <= left:
            break
        out.add(c.sha)
        left -= files
    return out


def material(store: ViewStore, project: str, agent_id: str = "") -> dict[str, Any]:
    """What one agent's scan is written from.

    The window is this chat's own work since this agent's last scan of the
    project: the commits its turns made (by the hook's stamps), the files
    they touched, and the change in the working tree that is not committed.
    Another agent's commits in the same repository are not in it — they are
    that agent's window — so two scans never count one commit twice. A chat
    the hook never stamped gets the project's commits since this agent's
    last scan instead, and the answer says so.
    """
    last = last_scan(store, project, agent_id)
    since = _stamp(str(last["created_date"]), str(last.get("created_time") or "")) if last else None
    out: dict[str, Any] = {
        "project": project,
        "window": "this chat's commits since your last scan of the project, and what is not committed"
                  if agent_id else "the project's commits since its last scan",
        "last_scan": (
            {"id": last["id"], "date": last["created_date"], "time": last.get("created_time") or "",
             "summary": last.get("l1") or ""} if last else None
        ),
        "repo": "", "commits": [], "files": [], "uncommitted": [],
        # The files this chat's tools changed, from the capture stamps: what
        # moved, git or no git. With git the committed files below are the
        # count; without, these are.
        "touched": chat_touched(store, agent_id, since) if agent_id else [],
        "changed": chat_touched(store, agent_id, since, "changed") if agent_id else [],
        "counters": {"files_n": 0, "lines_add": 0, "lines_del": 0, "decisions_n": 0},
    }
    if since is not None:
        day = str(last["created_date"])
        logged = store.query(
            "SELECT created_date, created_time, agent_id FROM decisions_mutual WHERE project = ? AND created_date >= ?",
            (project, day),
        )
        out["counters"]["decisions_n"] = sum(
            1 for r in logged
            if (not agent_id or str(r.get("agent_id") or "") == agent_id)
            and (_stamp(str(r.get("created_date") or ""), str(r.get("created_time") or "")) or since) > since
        )
    repo = _repo(store, project, agent_id)
    if repo is None:
        both = out["touched"] + [p for p in out["changed"] if p not in out["touched"]]
        out["counters"]["files_n"] = len(both)
        out["note"] = ("No git repository found for this project. `touched` lists the files this chat's tool calls "
                       "changed; `changed` the files found changed in the folder during its turns (another agent's "
                       "too). Describe the change from the work you did." if both else
                       "No git repository found for this project: describe the change from the work you did.")
        return out
    out["repo"] = str(repo)
    commits = [c for c in gitwork.commits(repo) if since is None or c.at > since]
    mine = chat_commits(store, agent_id, since) if agent_id else None
    if mine is not None:
        others = [c for c in commits if c.sha not in mine]
        commits = [c for c in commits if c.sha in mine]
        out["others_commits_n"] = len(others)
        if others:
            out["others_note"] = (f"{len(others)} commits in the repository since your last scan were made outside "
                                  "this chat; they belong to the scan of whoever made them and are not in your window.")
    elif agent_id:
        out["window"] = "the project's commits since your last scan: this chat has no capture stamps, so its own commits cannot be told apart"
        out["note"] = "This chat has no capture stamps: the window is the project's commits since your last scan."
    # Work the last scan described before it was committed is not counted again.
    seen = _described(store, str(last["id"]), commits) if last else set()
    out["already_described"] = [
        {"sha": c.sha[:7], "subject": c.subject} for c in commits if c.sha in seen
    ]
    commits = [c for c in commits if c.sha not in seen]
    per: dict[str, list[int]] = {}
    for c in commits:
        for path, add, dele in c.files:
            rec = per.setdefault(path, [0, 0, 0])
            rec[0] += add
            rec[1] += dele
            rec[2] += 1
    files = sorted(
        ({"path": p, "lines_add": v[0], "lines_del": v[1], "commits_n": v[2]} for p, v in per.items()),
        key=lambda f: f["lines_add"] + f["lines_del"], reverse=True,
    )
    out["commits"] = [
        {"sha": c.sha[:7], "at": c.at.strftime("%Y-%m-%dT%H:%M"), "subject": c.subject,
         "files_n": len(c.files), "lines_add": c.add, "lines_del": c.dele}
        for c in commits[:MAX_COMMITS]
    ]
    out["commits_n"] = len(commits)
    out["files"] = files[:MAX_FILES]
    # The working tree is shared by every agent in the folder: each
    # uncommitted file says whether this chat's tools touched it, so a scan
    # describes its own and leaves another agent's alone.
    mine_paths = set(out["touched"])
    out["uncommitted"] = [
        {**f, "mine": f["path"] in mine_paths} if mine_paths else f for f in _uncommitted(repo)
    ]
    out["counters"].update({
        "files_n": len(files),
        "lines_add": sum(f["lines_add"] for f in files),
        "lines_del": sum(f["lines_del"] for f in files),
    })
    return out


def instructions(repo_root: Path) -> str:
    out = []
    for name in PARTS:
        try:
            text = (repo_root / "prompts" / "contract" / name).read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(frontmatter.body_of(text).strip())
    return "\n\n".join(out)
