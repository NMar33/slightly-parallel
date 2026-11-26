"""An agent's projects as a reference (tk_d1d25a4d step 2, note nt_9de63b9e §3).

The ledger ``<data root>/agent_memberships.csv`` is folded by
``membership_fold`` (the one copy the hooks will load too). This module is
the server's side of it:

- ``current(store)``: the fold for this request, cached on the ledger's
  size, mtime and inode and the store's version. Never kept in the agent
  cache or the session tables: a join changes what a list shows without a
  chat file or a table being written.
- ``listed_in``, ``projects_of``, ``with_projects``: what the LIST readers ask.
- ``write``: one row, checked against the ledger and the disk under the
  ledger's lock (``csvio.append_checked``); a refusal writes nothing.
  ``locked`` holds that lock for a caller with several steps (the project
  delete, the one-chat move), which then writes with ``held=True``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import chatstore
from . import membership_fold as mf
from .csvio import append_checked, lock_path
from .file_safety import acquire_flock

log = logging.getLogger(__name__)

COLUMNS = mf.COLUMNS
LEVEL_WORDS = mf.LEVEL_WORDS
#: The ops the operator's route writes; ``moved`` is the move's alone.
ROUTE_OPS: tuple[str, ...] = ("join", "leave", "home", "level")
HOME_WAITS = "moving the home arrives with routing and accounting (steps 3 and 8)"
ORIGIN_WAITS = "the origin is left after the home moves"
#: How long a write waits for the ledger's lock (a delete or a move holds it).
LOCK_WAIT_S = 30.0


class Refused(Exception):
    """A write the ledger's rules refuse: an HTTP status and one line."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def ledger(root: str | Path) -> Path:
    return Path(mf.path(root))


UNREADABLE = "the membership ledger cannot be read ({}); nothing was written"


class LedgerUnreadable(Exception):
    """The ledger exists and cannot be read: a write that needs it refuses
    (P17), the routes answer 503 with ``detail``."""

    def __init__(self, exc: BaseException) -> None:
        self.detail = UNREADABLE.format(type(exc).__name__)
        super().__init__(self.detail)


def read_ledger(root: str | Path) -> tuple[list[dict[str, str]], int]:
    """``membership_fold.read`` of the root's ledger, an unreadable file
    raised as ``LedgerUnreadable``."""
    try:
        return mf.read(ledger(root))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise LedgerUnreadable(exc) from exc


def existing_codes(root: str | Path) -> set[str]:
    """The projects that exist on disk now: their folders, as the store
    discovers them (db.ViewStore._discover_projects)."""
    base = Path(root) / chatstore.PROJECTS
    try:
        return {p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")}
    except OSError:
        return set()


def _read_meta(folder: Path) -> dict[str, Any]:
    try:
        got = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def chats_on_disk(root: str | Path, agent: str) -> list[tuple[str, Path, dict[str, Any]]]:
    """``(origin, folder, meta)`` for each chat folder of ``agent``, read
    from the disk (under the lock, not from the store's cache)."""
    out = []
    for _proj, folder in chatstore.folders_of(root, agent, has="meta.json"):
        meta = _read_meta(folder)
        out.append((chatstore.project_of(folder, meta), folder, meta))
    return out


# ---------------------------------------------------------------------------
# Reading, per request
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[tuple, mf.Membership]] = {}
_cache_lock = threading.Lock()


def _sig(path: Path) -> tuple:
    try:
        st = path.stat()
    except OSError:
        return (None,)
    return (st.st_size, st.st_mtime_ns, st.st_ino)


def origins_of(agents: Iterable[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """agent id → the projects its chat folders file it under (one, unless
    a resumed session left a second folder)."""
    out: dict[str, list[str]] = {}
    for a in agents:
        ag = str(a.get("agent_id") or "")
        code = str(a.get("project") or "")
        if ag and code and code not in out.setdefault(ag, []):
            out[ag].append(code)
    return {k: tuple(v) for k, v in out.items()}


def current(store: Any) -> mf.Membership:
    """The fold for this request. An unreadable ledger reads as no rows,
    with the failure counted under ``unreadable`` and logged: the lists
    show what they showed before the ledger, and doctor says why."""
    path = ledger(store.data_root)
    key = (_sig(path), store.view_mtime)
    cache_key = str(store.data_root)
    with _cache_lock:
        hit = _cache.get(cache_key)
    if hit is not None and hit[0] == key:
        return hit[1]
    origins = origins_of(store.agents())
    existing = {pf.code for pf in store.projects}
    try:
        rows, cut = mf.read(path)
        m = mf.fold(rows, existing, origins, cut)
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("membership ledger unreadable (%s): lists show origins only", exc)
        m = mf.fold([], existing, origins)
        m.skips["unreadable"] += 1
    with _cache_lock:
        _cache[cache_key] = (key, m)
    return m


def listed_in(store: Any, code: str) -> set[str]:
    """The agents a LIST reader shows in ``code``: those filed there and its members."""
    return current(store).listed_in(code)


class Listing:
    """Who a LIST reader shows in one project, as a test on a row's own
    ``project`` and ``agent_id``: the rows filed there (minus agents that
    left their origin) and every row of the agents that joined it.

    Built on the row's own project rather than on a set of agents, so a
    chat with folders in two projects (a session resumed elsewhere) lists
    each folder's rows where they are, as before the ledger: an empty
    ledger changes no list."""

    def __init__(self, code: str, joined: set[str], left: set[str]) -> None:
        self.code = code
        self.joined = joined
        self.left = left

    def has(self, project: Any, agent_id: Any) -> bool:
        ag = str(agent_id or "")
        if ag in self.joined:
            return True
        return str(project or "") == self.code and ag not in self.left

    def sql(self, project_col: str = "project", agent_col: str = "agent_id") -> tuple[str, tuple[str, ...]]:
        """The same test as a WHERE fragment and its parameters."""
        own = f"{project_col} = ?"
        params: list[str] = [self.code]
        if self.left:
            own += f" AND COALESCE({agent_col}, '') NOT IN ({','.join('?' * len(self.left))})"
            params.extend(sorted(self.left))
        if not self.joined:
            return f"({own})", tuple(params)
        params.extend(sorted(self.joined))
        return f"(({own}) OR {agent_col} IN ({','.join('?' * len(self.joined))}))", tuple(params)

    def agents(self, agents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """The agent rows (store.agents()) this project lists, each once: a
        member with chat folders in two projects is one row here (its first
        folder's), as the rows filed in this project are one per folder."""
        out, seen = [], set()
        for a in agents:
            ag = str(a.get("agent_id") or "")
            key = ag if ag in self.joined else (ag, a.get("project"))
            if self.has(a.get("project"), ag) and key not in seen:
                seen.add(key)
                out.append(a)
        return out


def listing(store: Any, code: str) -> Listing:
    """``Listing`` for ``code`` from the fold of this request."""
    m = current(store)
    joined: set[str] = set()
    left: set[str] = set()
    for ag in m.agents():
        origins = m.origins(ag)
        if code in m.members(ag):
            # Filed in ``code`` already: its rows there list as they are,
            # and the rows of its other folder stay in theirs.
            if code not in origins:
                joined.add(ag)
        elif code in origins:
            left.add(ag)
    return Listing(code, joined, left)


def projects_of(store: Any, agent_id: str) -> str:
    """The agent's projects as a comma string, the shape tasks carry."""
    return current(store).projects(agent_id)


def row_projects(m: mf.Membership, agent: str, own: str) -> str:
    """The projects that list one row of a chat: the row's own project
    (unless the agent left it) and the projects the agent joined — never the
    project of its other folder. The ``Listing`` rule, applied to one row:
    with no ledger it is the row's own project, as before."""
    codes = [own] if own and own not in m.left(agent) else []
    codes += [c for c in m.joined(agent) if c not in codes] if agent else []
    return ",".join(codes) or own


def with_projects(store: Any, rows: list[dict[str, Any]], key: str = "agent_id") -> list[dict[str, Any]]:
    """Each row with ``projects`` added (copies; the store's cache is never
    written), by ``row_projects``."""
    m = current(store)
    return [{**r, "projects": row_projects(m, str(r.get(key) or ""), str(r.get("project") or ""))} for r in rows]


def skip_counts(store: Any) -> dict[str, int]:
    """The rows the fold skipped, by reason (doctor shows them)."""
    return dict(current(store).skips)


# ---------------------------------------------------------------------------
# Project aliases (note nt_258a7ed7 §3): read per request, written checked
# ---------------------------------------------------------------------------

ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
_alias_cache: dict[str, tuple[tuple, dict[str, str]]] = {}


def aliases_file(root: str | Path) -> Path:
    return Path(mf.aliases_path(root))


def alias_map(store: Any) -> dict[str, str]:
    """alias → project for this request, cached on the file and the store.
    An unreadable file reads as no aliases, logged: the braces then name
    projects by their codes only."""
    path = aliases_file(store.data_root)
    key = (_sig(path), store.view_mtime)
    hit = _alias_cache.get(str(store.data_root))
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        rows, _cut = mf.read(path)
        got = mf.aliases(rows, {pf.code for pf in store.projects})
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("project aliases unreadable (%s): braces name projects by code only", exc)
        got = {}
    _alias_cache[str(store.data_root)] = (key, got)
    return got


def write_alias(root: str | Path, op: str, project: str, alias: str, actor: str = "operator") -> dict[str, str]:
    """Add or remove one alias; checked against the file and the projects on
    disk under the file's lock (``append_checked``): an alias is unique, any
    case, across every code and every alias. Raises ``Refused``; nothing is
    written then."""
    root = Path(root)
    if op not in mf.ALIAS_OPS:
        raise Refused(422, f"op is one of: {', '.join(mf.ALIAS_OPS)}")
    if not ALIAS_RE.match(alias):
        raise Refused(422, "an alias is 1–40 letters, digits, dots, dashes or underscores, starting with a letter or digit")
    row = {"id": "pa_" + uuid.uuid4().hex[:12],
           "at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "project": project, "alias": alias, "op": op, "actor": actor}
    why: list[Refused] = []

    def check(rows: list[dict[str, str]]) -> str | None:
        existing = existing_codes(root)
        if project not in existing:
            why.append(Refused(404, f"no project «{project}»"))
            return why[-1].detail
        now = mf.aliases(rows, existing)
        taken = {a.lower(): (a, c) for a, c in now.items()}
        if op == "add":
            if alias.lower() in {c.lower() for c in existing}:
                why.append(Refused(409, f"«{alias}» is a project's code"))
            elif alias.lower() in taken:
                a, c = taken[alias.lower()]
                why.append(Refused(409, f"«{a}» is an alias of {c} already"))
        elif taken.get(alias.lower(), ("", ""))[1] != project:
            why.append(Refused(409, f"«{alias}» is not an alias of {project}"))
        return why[-1].detail if why else None

    refusal = append_checked(aliases_file(root), mf.ALIAS_COLUMNS, row, check)
    if refusal:
        raise why[0] if why else Refused(409, refusal)
    _alias_cache.pop(str(root), None)
    return row


# ---------------------------------------------------------------------------
# Who may write where (tk_d1d25a4d step 3, note nt_258a7ed7 §2)
# ---------------------------------------------------------------------------

NOT_MEMBER = ("agent {agent} is not a member of {project}; its projects: {projects}. "
              "The operator adds it on the agent card")
NOT_MEMBER_ROW = ("agent {agent} is not a member of {project}; this {what} is {project}'s. "
                  "The operator adds it on the agent card")
#: A row shown on several projects (a task's ``projects``): each would let it in.
NOT_MEMBER_ROWS = ("agent {agent} is not a member of {projects}; this {what} is on {listed}. "
                   "The operator adds it on the agent card")
UNINDEXED = ("agent {agent} is not a chat Slightly Parallel has recorded; nothing was written. "
             "Tell the operator")


class AgentView:
    """One agent's projects now: ``members`` (home first when it is the
    origin), ``home`` and the task ``level``."""

    __slots__ = ("agent", "members", "home", "level", "origins")

    def __init__(self, agent: str, members: list[str], home: str, level: int,
                 origins: tuple[str, ...] = ()) -> None:
        self.agent = agent
        self.members = members
        self.home = home
        self.level = level
        # The projects its chat folders are filed under as spelled there (not
        # those it left): on a file system without case, the same folders as
        # the codes that spell them otherwise.
        self.origins = origins


_folds: dict[str, bool] = {}


def folds_case(root: str | Path) -> bool:
    """Is the data root on a file system that does not tell letter case
    apart (Windows, macOS by default)? There ``projects/alpha`` is the
    folder ``projects/ALPHA``: one project spelled two ways (docs/testing.md
    #10), so a code compares without case."""
    key = str(root)
    if key not in _folds:
        base = Path(root) / chatstore.PROJECTS
        other = Path(root) / chatstore.PROJECTS.swapcase()
        try:
            _folds[key] = base.is_dir() and other.is_dir() and os.path.samefile(base, other)
        except OSError:
            _folds[key] = False
    return _folds[key]


def _member(store: Any, view: AgentView, project: str) -> bool:
    if project in view.members:
        return True
    if not folds_case(store.data_root):
        return False
    low = project.casefold()
    return any(c.casefold() == low for c in [*view.members, *view.origins])


def unrecorded(agent: str) -> AgentView | None:
    """What an agent with no chat is: nothing (refused). The test suite
    writes as agents it never recorded everywhere and replaces this
    (tests/conftest.py); the membership tests keep it (strict_membership)."""
    return None


def agent_view(store: Any, agent: str) -> AgentView | None:
    """The agent's member projects, home and level, or None when Slightly
    Parallel has no chat of it: not in the store's index and no chat folder
    on disk (a chat folder the watcher has not indexed yet counts). Never
    taken from a request's body."""
    agent = str(agent or "")
    if not agent:
        return None
    m = current(store)
    if m.origins(agent):
        stay = tuple(o for o in m.origins(agent) if o not in m.left(agent))
        return AgentView(agent, m.members(agent), m.home(agent), m.level(agent), stay)
    origins = tuple(dict.fromkeys(o for o, _f, _m in chats_on_disk(store.data_root, agent)))
    if not origins:
        return unrecorded(agent)
    try:
        rows, cut = mf.read(ledger(store.data_root))
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("membership ledger unreadable (%s): %s writes in its origin only", exc, agent)
        rows, cut = [], 0
    one = mf.fold([r for r in rows if r.get("agent_id") == agent], existing_codes(store.data_root),
                  {agent: origins}, cut)
    stay = tuple(o for o in origins if o not in one.left(agent))
    return AgentView(agent, one.members(agent), one.home(agent), one.level(agent), stay)


def may_write(store: Any, agent: str, project: str) -> tuple[bool, str]:
    """May ``agent`` write a new entry in ``project``? ``(True, "")`` for a
    member project; ``(False, line)`` otherwise, the line the refusal shows.
    An agent Slightly Parallel has not recorded is refused."""
    view = agent_view(store, agent)
    if view is None:
        return False, UNINDEXED.format(agent=agent)
    if _member(store, view, project):
        return True, ""
    return False, NOT_MEMBER.format(agent=agent, project=project or "(none)",
                                    projects=", ".join(view.members) or "none")


def may_write_row(store: Any, agent: str, project: str, what: str,
                  also: Iterable[str] = ()) -> tuple[bool, str]:
    """``may_write`` for a write on an existing row (a task, a note, a card,
    a topic) of ``project``: the refusal names whose row it is. A row with
    no project passes (nothing to compare)."""
    if not project:
        return True, ""
    view = agent_view(store, agent)
    if view is None:
        return False, UNINDEXED.format(agent=agent)
    # ``also``: the row's other projects (a task's ``projects``); a member of
    # any of them writes on it too.
    if any(_member(store, view, code) for code in (project, *also) if code):
        return True, ""
    codes = list(dict.fromkeys(c for c in (project, *also) if c))
    if len(codes) > 1:
        return False, NOT_MEMBER_ROWS.format(agent=agent, projects=" or ".join(codes), what=what,
                                             listed=", ".join(codes))
    return False, NOT_MEMBER_ROW.format(agent=agent, project=project, what=what)


# ---------------------------------------------------------------------------
# The operator summary (spec nt_27a4fff5 §5)
# ---------------------------------------------------------------------------

def summary(store: Any, agent: dict[str, Any]) -> dict[str, Any]:
    m = current(store)
    ag = str(agent.get("agent_id") or "")
    origin = str(agent.get("project") or "")
    members = m.members(ag) or [origin]
    home = m.home(ag) or origin
    level = m.level(ag)
    text = mf.summary_text(ag, home, members, origin, level)
    return {
        "agent_id": ag, "origin": origin, "home": home, "members": members,
        "joined": [c for c in members if c != origin], "projects": ",".join(members),
        "level": level, "level_words": LEVEL_WORDS[level], "runs_from_folder": origin,
        "helper": agent.get("helper") is True, "summary": text,
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

@contextmanager
def locked(root: str | Path) -> Iterator[None]:
    """Hold the ledger's lock across several steps; write with ``held=True``."""
    with acquire_flock(lock_path(ledger(root)), mode="a", timeout_s=LOCK_WAIT_S):
        yield


def new_row(agent: str, op: str, project: str = "", value: str = "", actor: str = "operator") -> dict[str, str]:
    return {
        "id": "am_" + uuid.uuid4().hex[:12],
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent_id": agent, "op": op, "project": project, "value": value, "actor": actor,
    }


def _rule(root: Path, agent: str, op: str, project: str, value: str,
          rows: list[dict[str, str]]) -> Refused | None:
    """Why this row may not be written now, or None. Runs under the lock,
    against the disk: the projects that exist and the agent's chat folders."""
    chats = chats_on_disk(root, agent)
    if not chats:
        return Refused(404, f"agent not found: {agent}")
    if any(meta.get("helper") is True for _o, _f, meta in chats):
        return Refused(409, f"{agent} is a helper chat: it goes where its parent goes (step 5)")
    origins = tuple(dict.fromkeys(o for o, _f, _m in chats))
    existing = existing_codes(root)
    m = mf.fold([r for r in rows if r.get("agent_id") == agent], existing, {agent: origins})
    members = m.members(agent)
    home = m.home(agent)
    if op == "level":
        try:
            n = int(value)
        except ValueError:
            n = 0
        if n not in mf.LEVELS:
            return Refused(422, "level is 1, 2 or 3")
        if n == m.level(agent):
            return Refused(409, f"{agent} is at task level {n} already")
        return None
    if project not in existing:
        return Refused(404, f"no project «{project}»")
    if op == "home":
        return Refused(409, HOME_WAITS)
    if op == "join":
        if project in members:
            return Refused(409, f"{agent} is in {project} already")
        return None
    if op == "leave":
        if project in origins and project == home:
            return Refused(409, ORIGIN_WAITS)
        if project == home:
            return Refused(409, f"{project} is the home of {agent}: move the home first")
        if project not in members:
            return Refused(409, f"{agent} is not in {project}")
        return None
    if op == "moved":
        frm = value[len(mf.MOVED_FROM):] if value.startswith(mf.MOVED_FROM) else ""
        if not frm:
            return Refused(422, f"a move names where it came from: «{mf.MOVED_FROM}<project>»")
        return None
    return Refused(422, f"op is one of: {', '.join(ROUTE_OPS)}")


def write(root: str | Path, agent: str, op: str, project: str = "", value: str = "",
          *, actor: str = "operator", held: bool = False) -> dict[str, str]:
    """Append one row when the rules allow it; raise ``Refused`` otherwise
    (nothing written). ``held``: the caller holds ``locked(root)``."""
    root = Path(root)
    row = new_row(agent, op, project, value, actor)
    why: list[Refused] = []

    def check(rows: list[dict[str, str]]) -> str | None:
        r = _rule(root, agent, op, project, value, rows)
        if r is not None:
            why.append(r)
            return r.detail
        return None

    path = ledger(root)
    if held:
        refusal = append_checked(path, COLUMNS, row, check, held=True)
    else:
        with acquire_flock(lock_path(path), mode="a", timeout_s=LOCK_WAIT_S):
            refusal = append_checked(path, COLUMNS, row, check, held=True)
    if refusal:
        raise why[0] if why else Refused(409, refusal)
    return row
