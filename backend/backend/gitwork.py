"""What a turn changed — commits attributed to the turns they landed in.

The chat log says what was asked and what was answered; git says what
actually changed. This joins them, per turn: each chat's ``meta.json``
carries the ``cwd`` the agent ran in, that folder's repository is read once
per HEAD, and a commit belongs to the turn whose window contains it — from
that turn's start until the next turn's, the last turn stretching a little
past the session's end, because the commit usually lands after the reply
that describes it.

Two sources, one shape. When the capture hook stamped the turn
(``work.jsonl`` beside ``chat.md``: HEAD, the commits since the previous
stamp, the uncommitted change), the turn's commits are exact — by ancestry,
whoever else was committing — and its uncommitted edits are visible. When
it did not (chats captured before the stamp existed), commits are attributed
by clock inside the repository: exact when one agent works a repo,
approximate when several do at once. A turn says which it was.
"""

from __future__ import annotations

import json
import os as _os
import re as _re
import subprocess
import sys as _sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

GIT_TIMEOUT = 5

#: Git is run in repositories an agent works in, and a repository's own
#: config can name programs for git to run (a file-system monitor, hooks).
#: These switch that off for every call made from here.
from .file_safety import given_path  # noqa: E402
from .hookshared import GIT_PLAIN_PATHS, numstat_path  # noqa: E402 — shared with the hook

SAFE_GIT = ("-c", "core.fsmonitor=", "-c", f"core.hooksPath={_os.devnull}", *GIT_PLAIN_PATHS)


def git(repo: Path, *args: str, timeout: float = GIT_TIMEOUT) -> str | None:
    """Run git in ``repo``; its stdout, or ``None`` when it did not succeed.

    The one wrapper. There were three: this one, a copy in
    ``file_entries`` and a third in ``projectfacts`` that never looked at
    the return code — so a git that failed handed back its empty stdout and
    the Architecture page rendered "no commits" as if that were the answer.
    ``None`` is failure, ``""`` is a command that ran and said nothing;
    every caller can tell them apart.
    """
    try:
        proc = subprocess.run(
            ["git", *SAFE_GIT, *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout



# How long after the last turn a commit still counts as that turn's. The
# reply that says "committed" is written before the commit exists.
TAIL = timedelta(minutes=45)

# How far back a repo is read. A chat older than this still renders; its
# turns simply carry no work, and the number is one line to change.
HORIZON_DAYS = 120

_RS, _US = "\x1e", "\x1f"
# The trailers a commit carries: the Claude-Session one, and the two the
# contract asks agents to write — ``Task: tk_…`` (one line per task) and
# ``Agent: <agent_id>``. Each comes out on one line, comma-separated.
# The subject comes last: whatever it holds cannot move the other fields.
_FORMAT = (f"{_RS}%H{_US}%aI{_US}%cI{_US}%an{_US}%(trailers:key=Claude-Session,valueonly,separator=%x2C)"
           f"{_US}%(trailers:key=Task,valueonly,separator=%x2C){_US}%(trailers:key=Agent,valueonly,separator=%x2C){_US}%s")
TASK_ID_RE = _re.compile(r"\btk_[a-z0-9][a-z0-9_-]{2,40}\b")


@dataclass
class Commit:
    sha: str
    at: datetime                      # local, naive — comparable to turn stamps
    author: str
    subject: str
    session: str                      # the Claude-Session trailer, if any
    files: list[tuple[str, int, int]] = field(default_factory=list)  # path, +, −
    tasks: list[str] = field(default_factory=list)   # its ``Task:`` lines: the agent's word on what it is for
    agent: str = ""                                   # its ``Agent:`` line: the chat that made it

    # When the commit object was made (the committer date): a cherry-pick,
    # rebase or amend keeps the old author date in ``at``.
    made: datetime | None = None

    @property
    def add(self) -> int:
        return sum(a for _, a, _ in self.files)

    @property
    def dele(self) -> int:
        return sum(d for _, _, d in self.files)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha[:7], "at": self.at.strftime("%Y-%m-%dT%H:%M:%S"),
            "author": self.author, "subject": self.subject,
            "files": [{"path": p, "add": a, "del": d} for p, a, d in self.files],
            "files_n": len(self.files), "add": self.add, "del": self.dele,
            "tasks": list(self.tasks), "agent": self.agent,
        }


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

_repo_of_chat: dict[str, Path | None] = {}
# chat → when "no repository" was found. Kept for a while, not for good: a
# git that timed out once on a busy disk, or a `git init` after the chat
# began, left the chat with no commits until the server restarted.
_no_repo_at: dict[str, float] = {}
NO_REPO_RETRY_S = 300.0
# repo → (HEAD, its commits, the day the log was last read in full).
_log_cache: dict[str, tuple[str, list[Commit], str]] = {}
# work.jsonl path → (its time and size, its stamps); see read_stamps.
_stamps_cache: dict[str, tuple[tuple[int, int], dict[int, dict[str, Any]]]] = {}


def repo_for_chat(chat_path: Path) -> Path | None:
    """The repository the agent ran in, from the capture's own ``cwd``."""
    key = str(chat_path)
    if key in _repo_of_chat:
        if _repo_of_chat[key] is not None or time.monotonic() - _no_repo_at.get(key, 0.0) < NO_REPO_RETRY_S:
            return _repo_of_chat[key]
    repo: Path | None = None
    try:
        meta = json.loads((chat_path.parent / "meta.json").read_text(encoding="utf-8"))
        cwd = given_path(meta.get("cwd"))
        if cwd is not None and cwd.is_dir():
            top = git(cwd, "rev-parse", "--show-toplevel")
            if top:
                repo = Path(top.strip())
    except (OSError, ValueError):
        repo = None
    _repo_of_chat[key] = repo
    if repo is None:
        _no_repo_at[key] = time.monotonic()
    return repo


def forget() -> None:
    """Drop every cache — for tests, and for a data root swap."""
    _repo_of_chat.clear()
    _no_repo_at.clear()
    _log_cache.clear()
    _stamps_cache.clear()
    _owners_cache.clear()


def head(repo: Path) -> str:
    """HEAD's sha, read from the repository's own files when they say it
    plainly; git answers when they do not (a packed ref, a worktree).

    Every session's turns ask for it, and a process per ask made the whole
    history — 261 sessions — a three-second request.
    """
    dot = repo / ".git"
    try:
        if dot.is_dir():
            ref = (dot / "HEAD").read_text(encoding="utf-8").strip()
            if ref.startswith("ref: "):
                target = dot / ref[5:]
                if target.is_file():
                    sha = target.read_text(encoding="utf-8").strip()
                    if len(sha) in (40, 64):
                        return sha
            elif len(ref) in (40, 64):
                return ref
    except (OSError, UnicodeDecodeError):
        pass
    return (git(repo, "rev-parse", "HEAD") or "").strip()


def commits(repo: Path, since_days: int = HORIZON_DAYS) -> list[Commit]:
    """The repo's commits, newest first, read once per HEAD.

    ``--numstat`` is the slow part — a diff per commit, two and a half
    seconds over 700 commits — and agents commit all day, each commit a new
    HEAD. So when the new HEAD descends from the one read, only the commits
    between them are read and put on top. The whole log is read again when
    that cannot be done exactly (a rebase, a branch switch, a commit dated
    before the newest one held) and once a day, which keeps the horizon
    where a full read would put it.
    """
    head_sha = head(repo)
    key = str(repo)
    today = datetime.now().date().isoformat()
    cached = _log_cache.get(key)
    if cached and cached[0] == head_sha:
        return cached[1]
    if cached and cached[2] == today and cached[0] and head_sha:
        newer = _commits_since(repo, cached[0], head_sha, since_days, cached[1])
        if newer is not None:
            out = newer + cached[1]
            _log_cache[key] = (head_sha, out, today)
            return out
    raw = git(
        repo, "log", f"--since={since_days} days ago", "--date=iso-strict",
        "--numstat", f"--format={_FORMAT}",
    )
    if raw is None:
        # git did not answer (a timeout on a busy disk). Nothing is kept: an
        # empty list stored under this HEAD was "no commits" on every page
        # until the next commit. The log read before, if any, is the best
        # there is, and the next ask tries again.
        return cached[1] if cached else []
    out = _parse_log(raw)
    _log_cache[key] = (head_sha, out, today)
    return out


def _commits_since(repo: Path, old: str, new: str, since_days: int, held: list[Commit]) -> list[Commit] | None:
    """The commits ``new`` has and ``old`` has not, newest first — or None
    when they cannot simply go on top of ``held`` (old's whole log)."""
    if git(repo, "merge-base", "--is-ancestor", old, new) is None:
        return None
    raw = git(
        repo, "log", f"--since={since_days} days ago", "--date=iso-strict",
        "--numstat", f"--format={_FORMAT}", f"{old}..{new}",
    )
    if raw is None:
        return None
    newer = _parse_log(raw)
    if held and any(c.at < held[0].at for c in newer):
        return None      # a full read would interleave it with the commits held
    return newer


def _parse_log(raw: str) -> list[Commit]:
    out: list[Commit] = []
    for rec in raw.split(_RS):
        if not rec.strip():
            continue
        head, _, body = rec.partition("\n")
        parts = head.split(_US)
        if len(parts) < 8:
            continue
        sha, at_iso, made_iso, author, session = parts[0], parts[1], parts[2], parts[3], parts[4].strip()
        tasks = list(dict.fromkeys(TASK_ID_RE.findall(parts[5])))
        agent = parts[6].split(",")[0].strip()[:64]
        subject = _US.join(parts[7:])
        try:
            at = datetime.fromisoformat(at_iso).astimezone().replace(tzinfo=None)
        except ValueError:
            continue
        try:
            made = datetime.fromisoformat(made_iso).astimezone().replace(tzinfo=None)
        except ValueError:
            made = at
        files: list[tuple[str, int, int]] = []
        for line in body.splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            a, d, path = cols
            files.append((numstat_path(path), int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0))
        out.append(Commit(sha=sha, at=at, author=author, subject=subject.strip(),
                          session=session, files=files, tasks=tasks, agent=agent, made=made))
    return out


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def turn_stamps(created_date: str, turns: list[dict[str, Any]]) -> list[datetime | None]:
    """A turn's clock as a datetime, from the session's YYMM-DD and its HH:MM.

    A session that crosses midnight has later turns with earlier clocks; a
    turn whose time reads below the previous one is taken as the next day.
    """
    try:
        yy, mm, dd = int(created_date[:2]), int(created_date[2:4]), int(created_date[5:7])
        day = datetime(2000 + yy, mm, dd)
    except (ValueError, IndexError):
        return [None] * len(turns)
    out: list[datetime | None] = []
    prev: datetime | None = None
    for t in turns:
        try:
            hh, mi = str(t.get("at") or "").split(":")
            at = day.replace(hour=int(hh), minute=int(mi))
        except ValueError:
            out.append(None)
            continue
        if prev and at < prev:
            day = day + timedelta(days=1)
            at = at + timedelta(days=1)
        out.append(at)
        prev = at
    return out


def attribute(
    log: list[Commit], stamps: list[datetime | None], end: datetime | None,
) -> list[list[Commit]]:
    """Per turn, the commits that landed in its window, oldest first."""
    per: list[list[Commit]] = [[] for _ in stamps]
    if not log or not stamps:
        return per
    known = [(i, s) for i, s in enumerate(stamps) if s is not None]
    if not known:
        return per
    last_i, last_at = known[-1]
    close = (end if end and end > last_at else last_at) + TAIL
    for c in sorted(log, key=lambda c: c.at):
        if c.at < known[0][1] or c.at >= close:
            continue
        # The last known turn at or before the commit.
        owner = known[0][0]
        for i, s in known:
            if s <= c.at:
                owner = i
            else:
                break
        per[owner].append(c)
    return per


def read_stamps(chat_path: Path) -> dict[int, dict[str, Any]]:
    """The hook's per-turn stamps, by turn number. Absent file, no stamps.

    Parsed once per version of the file: every session of a chat asks for
    all of it, and a long chat's work.jsonl is megabytes. Read-only for the
    caller — the answer is the cached one.
    """
    path = chat_path.parent / "work.jsonl"
    out: dict[int, dict[str, Any]] = {}
    try:
        st = path.stat()
        version = (st.st_mtime_ns, st.st_size)
        hit = _stamps_cache.get(str(path))
        if hit is not None and hit[0] == version:
            return hit[1]
        # On "\n" only (newline="\n"): the hook writes JSON with ensure_ascii
        # off, so a commit subject may hold U+2028, which splitlines() cut a
        # record at. One line at a time: a long chat's file runs to megabytes.
        with open(path, encoding="utf-8", errors="replace", newline="\n") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("turn"), int):
                    out[obj["turn"]] = obj
    except OSError:
        return {}
    _stamps_cache[str(path)] = (version, out)
    return out


def _path_matches(commit_path: str, touched: str) -> bool:
    """A repository path and a path a tool named, relative to the chat's
    folder (which may be a subfolder of the repository)."""
    t = touched.strip("/")
    return bool(t) and (commit_path == t or commit_path.endswith("/" + t))


class Claim(NamedTuple):
    """One chat's stamp that lists a commit: the chat, when the turn began and
    ended, the files its tools touched (None: not recorded), and its shell
    calls that may make a commit (None: the tool cannot tell)."""
    folder: str
    started: str
    at: str
    touched: list[str] | None
    calls: list[list[str]] | None


_owners_cache: dict[str, tuple[tuple, dict[str, list[Claim]]]] = {}
_owners_checked: dict[str, float] = {}
OWNERS_RECHECK_S = 2.0
# A commit made by a call: its time between the call's start and end, give or
# take this (the commit's time is whole seconds, the call's is not).
CALL_SLACK_S = 2
# A commit in a turn: between its start (a little earlier: the prompt hook
# runs after the agent may already have started) and its end.
TURN_SLACK_BEFORE_S = 60
TURN_SLACK_AFTER_S = 5


def _turn_starts(chat: Path) -> dict[int, str]:
    """Turn → when it began, from turns.jsonl (stamps written before they
    carried ``started``)."""
    out: dict[int, str] = {}
    try:
        with open(chat / "turns.jsonl", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("turn"), int) and r.get("start"):
                    # The first stamp of a turn is its start; a later one is
                    # the reply after the tool woke the agent (a continuation).
                    out.setdefault(r["turn"], str(r["start"]))
    except OSError:
        pass
    return out


def _stamped_by(chat_path: Path) -> dict[str, list[Claim]]:
    """sha → every chat of the same project whose stamps list it. Read once
    per change of any work.jsonl in the project."""
    chats = chat_path.parent.parent
    # One pass over a task's sessions asks for every commit: the folder is
    # listed again only after OWNERS_RECHECK_S, not once per commit (a
    # thousand listings of a hundred chats made the cores' timeline slow).
    hit = _owners_cache.get(str(chats))
    now = time.monotonic()
    if hit is not None and now - _owners_checked.get(str(chats), 0.0) < OWNERS_RECHECK_S:
        return hit[1]
    _owners_checked[str(chats)] = now
    files = sorted(chats.glob("*/work.jsonl"))
    try:
        key = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    except OSError:
        key = ()
    if hit is not None and hit[0] == key:
        return hit[1]
    out: dict[str, list[Claim]] = {}
    for f in files:
        starts: dict[int, str] | None = None
        for turn, st in read_stamps(f.parent / "chat.md").items():
            listed = [sha for sha in st.get("commits") or [] if isinstance(sha, str) and sha]
            if not listed:
                continue
            started = str(st.get("started") or "")
            if not started:
                if starts is None:
                    starts = _turn_starts(f.parent)
                started = starts.get(int(turn), "")
            touched = st.get("touched")
            calls = st.get("commit_calls")
            claim = Claim(f.parent.name, started, str(st.get("at") or ""),
                          touched if isinstance(touched, list) else None,
                          calls if isinstance(calls, list) else None)
            for sha in listed:
                out.setdefault(sha, []).append(claim)
    _owners_cache[str(chats)] = (key, out)
    return out


def _secs(stamp: str) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp)[:19]).timestamp()
    except ValueError:
        return None


def maker_of(commit: "Commit", claims: list[Claim]) -> str | None:
    """The chat that made a commit several chats saw appear, or None when the
    evidence does not tell. Each test narrows the chats still in question;
    the first that leaves one decides:

    1. its shell call that may make a commit was running when the commit was
       made (Claude Code, Codex and OpenCode report these);
    2. its tools touched one of the commit's files;
    3. its turn was running when the commit was made.

    Measured on the operator's data (429 commits several chats saw): the
    call matched in every case it could be read; the files agreed with it
    38 times out of 38, the turn 222 times out of 232. The chat that stamped
    first, the rule before this one, was wrong in 60 of 375; it stays only
    for stamps from before the calls were recorded.
    """
    folders = list(dict.fromkeys(c.folder for c in claims))
    if len(folders) <= 1:
        return folders[0] if folders else None
    made = (commit.made or commit.at).timestamp()
    paths = [p for p, _a, _d in commit.files]

    def by_call(c: Claim) -> bool:
        for call in c.calls or []:
            a, b = (_secs(call[0]), _secs(call[1])) if len(call) == 2 else (None, None)
            if a is not None and b is not None and a - CALL_SLACK_S <= made <= b + CALL_SLACK_S:
                return True
        return False

    def by_files(c: Claim) -> bool:
        return bool(c.touched) and any(_path_matches(p, t) for p in paths for t in c.touched or [])

    def by_turn(c: Claim) -> bool:
        a, b = _secs(c.started), _secs(c.at)
        return a is not None and b is not None and a - TURN_SLACK_BEFORE_S <= made <= b + TURN_SLACK_AFTER_S

    left = folders
    for test in (by_call, by_files, by_turn):
        hits = [f for f in left if any(test(c) for c in claims if c.folder == f)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            left = hits
    # Stamps written before the calls were recorded cannot tell: the chat
    # still in question that stamped it first keeps it, as it always did (a
    # change of rule must not take history's commits away). A commit the
    # calls could have told about stays nobody's.
    if not any(c.calls is not None for c in claims):
        return min((c for c in claims if c.folder in left), key=lambda c: c.at or "9999").folder
    return None


def owns_commit(chat_path: Path, commit: "Commit", stamp: dict[str, Any]) -> bool:
    """Whether a commit listed in this chat's stamp was made by this chat.

    A stamp lists every commit HEAD gained during the turn, another agent's
    in the same repository too. A commit only this chat saw is its own. One
    several chats saw goes to the chat maker_of names; when the evidence
    does not tell, to none of them: the commit is then linked by hand
    (task_commits), never guessed.
    """
    me = chat_path.parent.name
    # Signed by its agent: the line says whose it is, nothing to guess.
    if commit.agent:
        return commit.agent == me
    claims = _stamped_by(chat_path).get(commit.sha, [])
    if not claims:
        return True
    return maker_of(commit, claims) == me


def session_work(
    chat_path: Path, created_date: str, end_time: str, turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any] | None], dict[str, Any]]:
    """(per-turn work or None, session totals) for one session's turns.

    A stamped turn takes its commits from the stamp (exact) and carries its
    uncommitted change; an unstamped one falls back to the clock. Commits a
    stamp claimed are not offered to a clock-attributed turn as well.
    """
    repo = repo_for_chat(chat_path)
    empty = {"commits": 0, "files": 0, "add": 0, "del": 0}
    if repo is None or not turns:
        return [None] * len(turns), empty
    stamps = read_stamps(chat_path)
    turn_clock = turn_stamps(created_date, turns)
    end: datetime | None = None
    last = next((s for s in reversed(turn_clock) if s is not None), None)
    if last is not None:
        try:
            hh, mi = end_time.split(":")
            end = last.replace(hour=int(hh), minute=int(mi))
            if end < last:
                end = end + timedelta(days=1)
        except ValueError:
            end = None
    log = commits(repo)
    by_sha = {c.sha: c for c in log}
    claimed: set[str] = set()
    exact: dict[int, list[Commit]] = {}
    for i, t in enumerate(turns):
        st = stamps.get(int(t.get("n") or 0))
        if st is None:
            continue
        listed = [by_sha[sha] for sha in st.get("commits") or [] if sha in by_sha]
        exact[i] = [c for c in listed if owns_commit(chat_path, c, st)]
        claimed.update(c.sha for c in listed)   # another chat's are not offered to the clock either
    # The clock places what no stamp of this chat listed — never a commit
    # signed by another agent, nor one another chat's stamp listed: those
    # are known to be someone else's (two agents in one repository).
    me = chat_path.parent.name
    elsewhere = {sha for sha, owners in _stamped_by(chat_path).items() if any(c.folder != me for c in owners)}
    per = attribute([c for c in log if c.sha not in claimed and c.sha not in elsewhere and not (c.agent and c.agent != me)],
                    turn_clock, end)
    for i, cs in exact.items():
        # The stamp is written when the answer ends and lists the commits
        # since the previous stamp. A commit no stamp claimed — made after
        # the chat's last answer, or in a turn that was never stamped — is
        # still placed by the clock: take the stamp's commits and whatever
        # else the clock puts in this turn's window. Replacing one with the
        # other used to drop every commit an agent made after its own stamp.
        known = {c.sha for c in cs}
        per[i] = cs + [c for c in per[i] if c.sha not in known]

    work: list[dict[str, Any] | None] = []
    total = dict(empty)
    seen: set[str] = set()
    for i, cs in enumerate(per):
        st = stamps.get(int(turns[i].get("n") or 0))
        dirty = (st or {}).get("dirty") or {}
        uncommitted = None
        if st is not None and int(dirty.get("files") or 0) > 0:
            uncommitted = {
                "files_n": int(dirty.get("files") or 0),
                "add": int(dirty.get("add") or 0), "del": int(dirty.get("del") or 0),
                "paths": [
                    {"path": str(f.get("path") or ""), "add": int(f.get("add") or 0),
                     "del": int(f.get("del") or 0), "new": bool(f.get("new"))}
                    for f in (dirty.get("paths") or [])[:200]
                ],
            }
        if not cs and uncommitted is None:
            work.append(None)
            continue
        files = {p for c in cs for p, _, _ in c.files}
        work.append({
            "commits": [c.as_dict() for c in cs],
            "files_n": len(files),
            "add": sum(c.add for c in cs), "del": sum(c.dele for c in cs),
            "uncommitted": uncommitted,
            # Exact when the hook stamped the turn; by the clock otherwise.
            "exact": st is not None,
        })
        for c in cs:
            if c.sha not in seen:
                seen.add(c.sha)
                total["commits"] += 1
                total["add"] += c.add
                total["del"] += c.dele
    total["files"] = len({p for cs in per for c in cs for p, _, _ in c.files})
    return work, total


# ---------------------------------------------------------------------------
# The change itself — a diff, and a way to open the file
# ---------------------------------------------------------------------------

_SHA_RE = _re.compile(r"^[0-9a-f]{4,40}$")


def _inside(repo: Path, rel: str) -> Path | None:
    """The file's absolute path, refused if it escapes the repository."""
    if not rel or rel.startswith("/") or "\x00" in rel:
        return None
    full = (repo / rel).resolve()
    try:
        full.relative_to(repo.resolve())
    except ValueError:
        return None
    return full


def diff(repo: Path, sha: str | None, path: str | None) -> dict[str, Any] | None:
    """A unified diff: one commit's file, one whole commit, or the live tree.

    With ``sha`` the diff is what that commit did — to one ``path`` or to
    everything — and it is exact forever. Without ``sha`` it is the working
    tree against HEAD *right now*: the only diff an uncommitted edit can
    have, and stale the moment the file changes again, which the response
    says with ``live``.
    """
    args: list[str]
    if sha:
        if not _SHA_RE.match(sha):
            return None
        args = ["show", "--no-color", "--no-ext-diff", "--no-textconv", "--format=", sha]
    else:
        args = ["diff", "--no-color", "--no-ext-diff", "--no-textconv", "HEAD"]
    if path:
        full = _inside(repo, path)
        if full is None:
            return None
        args += ["--", path]
    text = git(repo, *args)
    if text is None:
        return None
    if not sha and path and not text.strip():
        # An untracked file has no diff against HEAD: the whole file is new.
        full = _inside(repo, path)
        if full is not None and full.is_file() and full.stat().st_size <= 1_000_000:
            try:
                body = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
            lines = body.splitlines()
            text = (f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
                    + "".join(f"+{ln}\n" for ln in lines))
    return {"sha": (sha or "")[:7], "path": path or "", "live": not sha, "diff": text}


#: Files the desktop would run rather than show. An agent writes the files
#: of its repository, so one of these is shown in its folder, never opened.
#: Per desktop, because they differ: Linux opens a script in an editor,
#: Windows runs it.
_RUNS_WHEN_OPENED = {
    "win": frozenset({
        ".exe", ".bat", ".cmd", ".com", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi", ".scr",
        ".lnk", ".jar", ".hta", ".cpl", ".reg", ".py", ".pyw", ".ps1", ".url",
    }),
    "darwin": frozenset({".command", ".app", ".workflow", ".action", ".jar", ".pkg", ".terminal", ".tool"}),
    "linux": frozenset({".desktop", ".appimage", ".run", ".jar"}),
}


def runs_when_opened(full: Path, platform: str = "") -> bool:
    platform = platform or _sys.platform
    kind = "win" if platform.startswith("win") else "darwin" if platform == "darwin" else "linux"
    if full.is_dir() or full.suffix.lower() in _RUNS_WHEN_OPENED[kind]:
        return True
    # macOS runs a file with no extension in Terminal when it is executable.
    return kind == "darwin" and not full.suffix and _os.access(full, _os.X_OK)


def open_file(repo: Path, path: str, editor: str = "") -> tuple[bool, str]:
    """Show the file on this laptop: in the operator's editor when one is
    set, else with what the desktop opens it with. A file the desktop would
    run is shown in its folder instead."""
    full = _inside(repo, path)
    if full is None or not full.exists():
        return False, f"{path} is not in the repository"
    if editor:
        from . import termlib
        try:
            termlib.open_in_editor(editor, full)
        except (OSError, ValueError, KeyError) as exc:
            return False, f"could not start {editor}: {exc}"
        return True, str(full)
    if runs_when_opened(full):
        from .backup import reveal
        ok, why = reveal(full)
        return ok, str(full) if ok else why
    try:
        if _sys.platform.startswith("win"):
            # The shell's own "open", with no command line for a name to break.
            _os.startfile(str(full))  # type: ignore[attr-defined]
            return True, str(full)
        argv = ["open", str(full)] if _sys.platform == "darwin" else ["xdg-open", str(full)]
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except (OSError, ValueError) as exc:
        return False, f"could not open {full.name}: {exc}"
    return True, str(full)
