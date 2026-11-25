"""An agent's projects, read from the membership ledger (tk_d1d25a4d, step 2).

``<data root>/agent_memberships.csv`` is append-only, one row per act:
``id, at, agent_id, op, project, value, actor``. This module folds it into
what each agent is now: its member projects, its home, its task level.

- ``join P``: becomes a member of P.
- ``leave P``: no longer listed in P (never the home).
- ``home P``: P becomes its home (it must be a member).
- ``level`` with value 1–3: task rights (spec nt_27a4fff5 §2).
- ``moved P``: its chat folder was moved to P; value ``moved from <Q>``.

The origin of a chat — the project of the folder it started in, meta.json's
``project`` — is given by the caller; a chat with no rows is a member of its
origin only, home is the origin, level 2.

The fold follows file order (``at`` is read only by ``home_at``) and is total:
a row that does not apply is skipped and counted, never raised. Codes that no
longer exist (the caller passes the codes that do) drop out of the answers.

Standard library only and no relative imports: the capture hooks load this
file by path, as they load chatstore (tests/test_hook_parity.py).
"""

from __future__ import annotations

import csv
import io
import os
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping

LEDGER = "agent_memberships.csv"
COLUMNS: tuple[str, ...] = ("id", "at", "agent_id", "op", "project", "value", "actor")
OPS: tuple[str, ...] = ("join", "leave", "home", "level", "moved")
LEVELS: tuple[int, ...] = (1, 2, 3)
DEFAULT_LEVEL = 2
MOVED_FROM = "moved from "
#: What follows the origin in a ``moved`` value when the move has a warning
#: (chatmove: a write that went to the trash, not to the target).
MOVED_NOTE = "; "
#: The value the delete writes on its ``leave`` rows (project_admin).
DELETED = "project deleted"

#: Why a row was skipped — the keys of ``Membership.skips``.
SKIP_REASONS: tuple[str, ...] = (
    "join_twice",        # join of a project it is already in
    "leave_non_member",  # leave of a project it is not in
    "leave_home",        # leave of its home
    "home_non_member",   # home in a project it is not a member of
    "bad_level",         # level outside 1–3
    "unknown_op",        # an op this fold does not know
    "cut_off",           # a last line cut short (a write under way, a crash)
    "no_agent",          # a row with no agent or no project
    "bad_move",          # moved with no "moved from <origin>", or from a project not its origin
    "join_origin",       # a join of the project its chat is filed in now: the trace of a
                         # one-chat move whose moved row was never written (a crash); not a fault
)
#: Skips that record what happened rather than a fault: doctor stays quiet.
QUIET_SKIPS: frozenset[str] = frozenset({"join_origin"})


def path(root: str | os.PathLike[str]) -> str:
    """The ledger's path in a data root."""
    return os.path.join(os.fspath(root), LEDGER)


def read(file: str | os.PathLike[str]) -> tuple[list[dict[str, str]], int]:
    """The ledger's rows in file order, and how many were cut off.

    A missing file is no rows. A file that cannot be read raises (OSError,
    UnicodeDecodeError): an unreadable ledger is not an empty one."""
    try:
        with open(file, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    except FileNotFoundError:
        return [], 0
    return parse(text)


def parse(text: str) -> tuple[list[dict[str, str]], int]:
    """``read`` on text already in hand."""
    if not text:
        return [], 0
    cut = 0
    if not text.endswith(("\n", "\r")):
        # The last line has no end: a write was cut short, or is under way.
        head, _sep, _tail = text.rpartition("\n")
        text = head + "\n" if _sep else ""
        cut = 1
    rd = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(rd, [])]
    rows: list[dict[str, str]] = []
    for cells in rd:
        if not cells:
            continue
        if len(cells) < len(header):
            cut += 1
            continue
        rows.append({h: cells[i] for i, h in enumerate(header)})
    return rows, cut


def _when(at: Any) -> datetime | None:
    if isinstance(at, datetime):
        moment = at
    else:
        try:
            moment = datetime.fromisoformat(str(at or "").strip())
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.astimezone()


def _origins(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(v for v in value if v)


class _Agent:
    __slots__ = ("origins", "left", "joined", "home", "level", "events")

    def __init__(self, origins: tuple[str, ...]) -> None:
        self.origins: list[str] = list(origins)
        self.left: set[str] = set()      # origins left (a soft leave, after the home moved)
        self.joined: list[str] = []
        self.home: str = ""              # "" while the home is the origin
        self.level = DEFAULT_LEVEL
        self.events: list[tuple[datetime | None, str, str, str]] = []  # (at, op, code, from)

    def members(self) -> list[str]:
        out = [o for o in self.origins if o not in self.left]
        out.extend(c for c in self.joined if c not in out)
        return out

    def current_home(self) -> str:
        return self.home or (self.origins[0] if self.origins else "")


class Membership:
    """The fold's answer. Every reader asks it; none reads the ledger."""

    def __init__(self, agents: dict[str, _Agent], origins: Mapping[str, Any],
                 existing: set[str] | None, skips: Counter) -> None:
        self._agents = agents
        self._origins = origins
        self._existing = existing
        self.skips = skips

    def _ok(self, code: str) -> bool:
        return bool(code) and (self._existing is None or code in self._existing)

    def _of(self, agent: str) -> _Agent:
        got = self._agents.get(agent)
        return got if got is not None else _Agent(_origins(self._origins.get(agent)))

    def origins(self, agent: str) -> tuple[str, ...]:
        """The projects its chat folders are filed under now (as given)."""
        return _origins(self._origins.get(agent))

    def left(self, agent: str) -> list[str]:
        """The origins it left (a soft leave after its home moved)."""
        return sorted(self._of(agent).left)

    def has_rows(self, agent: str) -> bool:
        return agent in self._agents

    def agents(self) -> list[str]:
        """The agents the ledger names."""
        return list(self._agents)

    def members(self, agent: str) -> list[str]:
        """Its projects: the origin first (unless left), then those joined."""
        return [c for c in self._of(agent).members() if self._ok(c)]

    def joined(self, agent: str) -> list[str]:
        """The projects it joined, beyond its origin."""
        a = self._of(agent)
        return [c for c in a.joined if self._ok(c) and c not in a.origins]

    def home(self, agent: str) -> str:
        a = self._of(agent)
        h = a.current_home()
        if self._ok(h):
            return h
        return next((o for o in a.origins if self._ok(o)), h)

    def home_at(self, agent: str, at: Any) -> str:
        """Its home at the moment ``at`` (ISO text or a datetime)."""
        a = self._of(agent)
        moment = _when(at)
        start = a.origins[0] if a.origins else ""
        # The origin before the first move is where that move came from.
        for _t, op, _code, frm in a.events:
            if op == "moved":
                start = frm or start
                break
        cur = start
        for t, op, code, frm in a.events:
            if moment is not None and t is not None and t > moment:
                break
            if op == "home":
                cur = code
            elif op == "moved" and cur == frm:
                cur = code
        return cur

    def level(self, agent: str) -> int:
        return self._of(agent).level

    def listed_in(self, code: str) -> set[str]:
        """The agents a LIST reader shows in ``code``: its origin agents
        (those the caller passed) and its members."""
        if not self._ok(code):
            return set()
        out = {ag for ag, o in self._origins.items() if code in _origins(o)}
        for ag, a in self._agents.items():
            if code in a.members():
                out.add(ag)
            elif code in a.left:
                out.discard(ag)
        return out

    def projects(self, agent: str) -> str:
        """``members`` as the comma string tasks carry."""
        return ",".join(self.members(agent))


def fold(rows: Iterable[Mapping[str, Any]], existing: Iterable[str] | None = None,
         origins: Mapping[str, Any] | None = None, cut_off: int = 0) -> Membership:
    """Fold the ledger's rows, in file order.

    ``existing``: the project codes that exist now (None: every code does).
    ``origins``: agent id → its origin code (or codes, for a chat with a
    folder in two projects)."""
    origins = dict(origins or {})
    rows = list(rows)
    skips: Counter = Counter()
    if cut_off:
        skips["cut_off"] += cut_off
    # A moved row changes the origin from then on: before it, the origin was
    # the project it moved from (meta.json already names the new one).
    first_from: dict[str, str] = {}
    for r in rows:
        if str(r.get("op") or "").strip() == "moved":
            ag = str(r.get("agent_id") or "").strip()
            frm = _moved_from(r)
            if ag and frm and ag not in first_from:
                first_from[ag] = frm
    agents: dict[str, _Agent] = {}
    for r in rows:
        ag = str(r.get("agent_id") or "").strip()
        op = str(r.get("op") or "").strip()
        code = str(r.get("project") or "").strip()
        if op not in OPS:
            skips["unknown_op"] += 1
            continue
        if not ag or (op != "level" and not code):
            skips["no_agent"] += 1
            continue
        a = agents.get(ag)
        if a is None:
            start = (first_from[ag],) if ag in first_from else _origins(origins.get(ag))
            a = agents[ag] = _Agent(start)
        at = _when(r.get("at"))
        if op == "join":
            if code in a.members():
                # The chat filed there now with no moved row for it: a move
                # that stopped between its trash and its row.
                skips["join_origin" if code in _origins(origins.get(ag)) and ag not in first_from
                      else "join_twice"] += 1
                continue
            if code in a.left:
                a.left.discard(code)
            else:
                a.joined.append(code)
        elif op == "leave":
            if code == a.current_home():
                skips["leave_home"] += 1
                continue
            if code not in a.members():
                skips["leave_non_member"] += 1
                continue
            if code in a.joined:
                a.joined.remove(code)
            else:
                a.left.add(code)
        elif op == "home":
            if code not in a.members():
                skips["home_non_member"] += 1
                continue
            a.home = "" if code == (a.origins[0] if a.origins else "") else code
            a.events.append((at, "home", code, ""))
        elif op == "level":
            try:
                n = int(str(r.get("value") or "").strip())
            except ValueError:
                n = 0
            if n not in LEVELS:
                skips["bad_level"] += 1
                continue
            a.level = n
        elif op == "moved":
            frm = _moved_from(r)
            if not frm or frm not in a.origins or code == frm:
                skips["bad_move"] += 1
                continue
            a.origins = [code if o == frm else o for o in a.origins]
            a.left.discard(code)
            if code in a.joined:
                a.joined.remove(code)
            if a.home == frm:
                a.home = ""
            a.events.append((at, "moved", code, frm))
    # Agents the ledger never names keep their origins as given; the ones it
    # names end on the origin meta.json gives now, whatever the rows said.
    for ag, a in agents.items():
        now = _origins(origins.get(ag))
        if now and set(now) != set(a.origins):
            a.origins = list(now)
            if a.home and a.home not in a.members():
                a.home = ""
    return Membership(agents, origins, set(existing) if existing is not None else None, skips)


def _moved_from(r: Mapping[str, Any]) -> str:
    v = str(r.get("value") or "").strip()
    return v[len(MOVED_FROM):].split(MOVED_NOTE, 1)[0].strip() if v.startswith(MOVED_FROM) else ""


def load(root: str | os.PathLike[str], existing: Iterable[str] | None = None,
         origins: Mapping[str, Any] | None = None) -> Membership:
    """Read and fold the ledger of a data root."""
    rows, cut = read(path(root))
    return fold(rows, existing, origins, cut)
