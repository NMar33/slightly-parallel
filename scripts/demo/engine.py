"""The machinery behind build_demo.py: a simulated month, played in order.

The demo is not written as finished CSV rows. It is *played*: a clock is
set to a moment in September 2026, and at that moment the operator types a
message, an agent answers and commits, a card moves, a scan is written. Every
write goes through the product's own code — the capture core for chats, the
API (in-process, through FastAPI's TestClient) for everything else — so each
file has exactly the shape the product would have written, derived fields
included. Only the clock is faked: every ``datetime.now()``, ``date.today()``
and ``time.time()`` the backend reads during the build answers with the
simulated moment, and git commits carry the same moment in their author and
committer dates.
"""

from __future__ import annotations

import datetime as _real_dt_mod
import heapq
import importlib.util
import itertools
import json
import os
import random
import re
import struct
import subprocess
import sys
import time as _real_time
import types
import zlib
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]

_RealDT = _real_dt_mod.datetime
_RealDate = _real_dt_mod.date
timedelta = _real_dt_mod.timedelta


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

class Clock:
    now: _RealDT = _RealDT(2026, 9, 1, 8, 0)  # set again by set_start


CLOCK = Clock()


class _AcceptsReal(type):
    """isinstance(real_datetime, FakeDT) must stay true: code checks
    ``isinstance(x, date)`` against the name it imported, which is patched."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls.__mro__[1])

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls.__mro__[1])


class FakeDT(_RealDT, metaclass=_AcceptsReal):
    @classmethod
    def now(cls, tz=None):  # noqa: D401
        n = CLOCK.now
        if tz is not None:
            return n.astimezone(tz)
        return _RealDT(n.year, n.month, n.day, n.hour, n.minute, n.second, n.microsecond)

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        return CLOCK.now.astimezone(_real_dt_mod.timezone.utc).replace(tzinfo=None)


class FakeDate(_RealDate, metaclass=_AcceptsReal):
    @classmethod
    def today(cls):
        n = CLOCK.now
        return _RealDate(n.year, n.month, n.day)


def _fake_epoch() -> float:
    return CLOCK.now.timestamp()


class _FakeTime(types.ModuleType):
    """``time`` with the wall clock replaced; everything else passes through."""

    def __getattr__(self, name):
        return getattr(_real_time, name)

    @staticmethod
    def time() -> float:
        return _fake_epoch()

    @staticmethod
    def localtime(secs=None):
        return _real_time.localtime(_fake_epoch() if secs is None else secs)

    @staticmethod
    def strftime(fmt, t=None):
        return _real_time.strftime(fmt, _real_time.localtime(_fake_epoch()) if t is None else t)


FAKE_TIME = _FakeTime("time")
FAKE_DT_MOD = types.ModuleType("datetime")
FAKE_DT_MOD.__dict__.update(_real_dt_mod.__dict__)
FAKE_DT_MOD.datetime = FakeDT
FAKE_DT_MOD.date = FakeDate

# Modules whose `time` must stay real: they compare against file mtimes,
# sleep, or measure durations.
_REAL_TIME_MODULES = {
    "backend.db", "backend.file_safety", "backend.idle", "backend.logbook",
    "backend.searchlib", "backend.termlib", "backend.sysmon", "backend.capturewatch",
    "backend.projectfacts", "backend.repomap", "backend.routers.terminal",
    "backend.routers.monitor", "backend.routers.doctor", "backend.doctorlib", "backend.routers.logs",
    "backend.watcher", "backend.analytics", "backend.statslib",
}


def patch_clock(prefixes: tuple[str, ...] = ("backend",), extra: list[types.ModuleType] = ()) -> int:
    n = 0
    mods = [m for name, m in list(sys.modules.items())
            if m is not None and name.split(".")[0] in prefixes]
    mods += list(extra)
    for mod in mods:
        d = getattr(mod, "__dict__", {})
        if d.get("datetime") is _RealDT:
            mod.datetime = FakeDT
            n += 1
        elif d.get("datetime") is _real_dt_mod:
            mod.datetime = FAKE_DT_MOD
            n += 1
        if d.get("date") is _RealDate:
            mod.date = FakeDate
        if d.get("_dt") is _real_dt_mod:
            mod._dt = FAKE_DT_MOD
        if d.get("time") is _real_time and getattr(mod, "__name__", "") not in _REAL_TIME_MODULES:
            mod.time = FAKE_TIME
    return n


def yymmdd(d: _RealDT) -> str:
    return f"{d.year % 100:02d}{d.month:02d}-{d.day:02d}"


def hhmm(d: _RealDT) -> str:
    return d.strftime("%H:%M")


# Day 1 of the played month. September 2026 for the demo dataset; the
# example project (build_example.py) moves it so the month ends yesterday.
START: _RealDate = _RealDate(2026, 9, 1)


def set_start(day_one: _RealDate) -> None:
    global START
    START = day_one
    CLOCK.now = D(1, 8, 0)


def D(day: int, h: int = 10, m: int = 0, s: int = 0) -> _RealDT:
    """A moment of the played month: ``day`` 1 is START, 31 the day after
    day 30, whatever the calendar month."""
    d = START + timedelta(days=day - 1)
    return _RealDT(d.year, d.month, d.day, h, m, s)


# Dates written into the content as tokens, so they move with START:
# {iso:22} 2026-09-22 · {ymd:22} 2609-22 · {dm:22} 22 September · {dsh:22} 22 Sep.
_DATE_RE = re.compile(r"\{(iso|ymd|dm|dsh):(\d+)\}")


def dated(text: str) -> str:
    def sub(m: re.Match) -> str:
        d = D(int(m.group(2)))
        kind = m.group(1)
        if kind == "iso":
            return d.date().isoformat()
        if kind == "ymd":
            return yymmdd(d)
        if kind == "dm":
            return f"{d.day} {d.strftime('%B')}"
        return f"{d.day} {d.strftime('%b')}"
    return _DATE_RE.sub(sub, text) if isinstance(text, str) and "{" in text else text


def dated_deep(value: Any) -> Any:
    if isinstance(value, str):
        return dated(value)
    if isinstance(value, list):
        return [dated_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: dated_deep(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# A tiny PNG writer (evidence screenshots), standard library only
# ---------------------------------------------------------------------------

def png(width: int, height: int, paint: Callable[[int, int], tuple[int, int, int]]) -> bytes:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(paint(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def mock_screen(kind: str, seed: int = 0, w: int = 480, h: int = 300) -> bytes:
    """A flat UI mock: a header bar, a sidebar or cards, a chart — enough to
    read as a screenshot thumbnail on an evidence card."""
    rng = random.Random(seed)
    accent = [(37, 99, 235), (22, 163, 74), (217, 119, 6), (147, 51, 234)][seed % 4]
    boxes: list[tuple[int, int, int, int, tuple[int, int, int]]] = []
    boxes.append((0, 0, w, 36, (17, 24, 39)))
    boxes.append((16, 12, 90, 24, (255, 255, 255)))
    if kind == "cards":
        for i in range(3):
            for j in range(2):
                x0, y0 = 24 + i * 150, 56 + j * 118
                boxes.append((x0, y0, x0 + 136, y0 + 104, (243, 244, 246)))
                boxes.append((x0 + 8, y0 + 8, x0 + 128, y0 + 62, (209, 213, 219)))
                boxes.append((x0 + 8, y0 + 70, x0 + 90, y0 + 78, (107, 114, 128)))
                boxes.append((x0 + 8, y0 + 86, x0 + 50, y0 + 96, accent))
    elif kind == "form":
        boxes.append((w // 2 - 150, 56, w // 2 + 150, h - 24, (249, 250, 251)))
        for i in range(4):
            y0 = 76 + i * 42
            boxes.append((w // 2 - 130, y0, w // 2 - 60, y0 + 8, (107, 114, 128)))
            boxes.append((w // 2 - 130, y0 + 14, w // 2 + 130, y0 + 34, (229, 231, 235)))
        boxes.append((w // 2 - 130, h - 60, w // 2 + 130, h - 36, accent))
    else:  # chart
        boxes.append((24, 56, w - 24, h - 24, (249, 250, 251)))
        n = 12
        bw = (w - 80) // n
        for i in range(n):
            bh = rng.randint(30, h - 110)
            x0 = 40 + i * bw
            boxes.append((x0, h - 40 - bh, x0 + bw - 8, h - 40, accent))

    def paint(x: int, y: int) -> tuple[int, int, int]:
        c = (255, 255, 255)
        for x0, y0, x1, y1, col in boxes:
            if x0 <= x < x1 and y0 <= y < y1:
                c = col
        return c

    return png(w, h, paint)


# ---------------------------------------------------------------------------
# Git repositories with a backdated history
# ---------------------------------------------------------------------------

class Repo:
    def __init__(self, path: Path, author: str = "operator", email: str = "operator@shopfront.dev"):
        self.path = path
        self.author, self.email = author, email
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", author)
        self.git("config", "user.email", email)
        self.git("config", "commit.gpgsign", "false")
        self.commits: list[tuple[str, str]] = []

    def git(self, *args: str, env: dict | None = None) -> str:
        e = dict(os.environ)
        e.pop("GIT_DIR", None)
        e.update(env or {})
        out = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True, env=e)
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
        return out.stdout

    def write(self, rel: str, text: str) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(dated(text), encoding="utf-8")

    def append(self, rel: str, text: str) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        if old and not old.endswith("\n"):
            old += "\n"
        p.write_text(old + dated(text), encoding="utf-8")

    def remove(self, rel: str) -> None:
        p = self.path / rel
        if p.exists():
            p.unlink()

    def commit(self, subject: str, at: _RealDT, body: str = "", author: str | None = None) -> str:
        self.git("add", "-A")
        stamp = f"{int(at.timestamp())} {_tz_offset(at)}"
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        if author:
            env["GIT_AUTHOR_NAME"] = author
        msg = dated(subject + (f"\n\n{body}" if body else ""))
        self.git("commit", "-q", "--allow-empty", "-m", msg, env=env)
        sha = self.git("rev-parse", "HEAD").strip()
        self.commits.append((sha, subject))
        return sha


def _tz_offset(at: _RealDT) -> str:
    off = at.astimezone().utcoffset() or timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    mins = abs(mins)
    return f"{sign}{mins // 60:02d}{mins % 60:02d}"


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------

class ApiError(RuntimeError):
    pass


class _Answer:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code, self.content = status, body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.content)


class AsgiClient:
    """Requests straight into the app, in this process: the example project
    is built on a user's machine, where the test client's package is not
    installed. Addressed to 127.0.0.1:8123, as the server only answers to
    this computer's names."""

    def __init__(self, app: Any, cookie: str = "") -> None:
        import asyncio
        self.app, self.cookie = app, cookie
        self.loop = asyncio.new_event_loop()

    def _send(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> _Answer:
        raw, _, query = path.partition("?")
        hdrs = [(b"host", b"127.0.0.1:8123"), (b"content-length", str(len(body)).encode())]
        if body:
            hdrs.append((b"content-type", b"application/json"))
        if self.cookie:
            hdrs.append((b"cookie", self.cookie.encode()))
        hdrs += [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                 "scheme": "http", "path": urllib_unquote(raw), "raw_path": raw.encode(),
                 "query_string": query.encode(), "headers": hdrs, "server": ("127.0.0.1", 8123),
                 "client": ("127.0.0.1", 50000), "root_path": ""}
        sent = False
        status = 500
        chunks: list[bytes] = []

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        self.loop.run_until_complete(self.app(scope, receive, send))
        return _Answer(status, b"".join(chunks))

    def get(self, path: str, headers: dict[str, str] | None = None) -> _Answer:
        return self._send("GET", path, b"", headers or {})

    def post(self, path: str, json: Any = None, headers: dict[str, str] | None = None) -> _Answer:
        import json as _json
        return self._send("POST", path, _json.dumps(json).encode("utf-8"), headers or {})

    def close(self) -> None:
        self.loop.close()


def urllib_unquote(s: str) -> str:
    from urllib.parse import unquote
    return unquote(s)


class Sim:
    """One data root, one in-process server, one clock, one queue of events."""

    def __init__(self, target: Path, seed: int = 20260930, repos_dir: Path | None = None):
        self.target = target
        self.root = target / "data"
        self.repos_dir = repos_dir or target / "repos"
        self.rng = random.Random(seed)
        self.queue: list[tuple[_RealDT, int, Callable[[], None]]] = []
        self._seq = itertools.count()
        self.tasks: dict[str, str] = {}      # key → tk_ id
        self.task_rows: dict[str, dict] = {}  # key → spec
        self.ids: dict[str, str] = {}        # any other key → id (sprints, scans, …)
        self.repos: dict[str, Repo] = {}
        self.chats: dict[str, Any] = {}
        self.log: list[str] = []
        self.counts: dict[str, int] = {}
        os.environ["SP_EXAMPLES"] = "0"
        os.environ.setdefault("SHELL", "/bin/sh")
        os.environ["SP_SANDBOX"] = "1"
        # The server's settings name this root: with nothing named it would
        # seed ~/.slightly-parallel on the way (config.Settings.from_env).
        os.environ["SP_DATA_ROOT"] = str(self.root)
        sys.path.insert(0, str(REPO / "backend"))
        CLOCK.now = D(1, 7, 30)
        self.root.mkdir(parents=True, exist_ok=True)
        self.repos_dir.mkdir(parents=True, exist_ok=True)

        import warnings
        warnings.filterwarnings("ignore")
        import logging
        logging.getLogger("sp").setLevel(logging.ERROR)
        from backend.server import create_app  # noqa: E402
        import backend.routers  # noqa: F401,E402

        # Load every backend module now, so the clock patch reaches all of them.
        import pkgutil
        import backend as _pkg
        for info in pkgutil.walk_packages(_pkg.__path__, "backend."):
            try:
                importlib.import_module(info.name)
            except Exception:  # noqa: BLE001
                pass
        # The capture core, exactly as the hooks load it.
        spec = importlib.util.spec_from_file_location(
            "sp_capture", REPO / "scripts" / "hooks" / "capture.py")
        self.capture = importlib.util.module_from_spec(spec)
        sys.modules["sp_capture"] = self.capture
        spec.loader.exec_module(self.capture)  # type: ignore[union-attr]
        patch_clock(extra=[self.capture])

        self.app = create_app(data_root=self.root, watch=False, run_monitor=False)
        # The operator's writes carry the operator's cookie, as a page's do.
        from backend.server import operator_cookie  # noqa: E402
        self.client = AsgiClient(self.app, cookie="=".join(operator_cookie(self.app)))
        self.store = self.app.state.store

    # -- the queue ---------------------------------------------------------

    def at(self, when: _RealDT, fn: Callable[[], None]) -> None:
        heapq.heappush(self.queue, (when, next(self._seq), fn))

    def run(self) -> None:
        while self.queue:
            when, _, fn = heapq.heappop(self.queue)
            if when > CLOCK.now:
                CLOCK.now = when
            fn()

    def set_clock(self, when: _RealDT) -> None:
        CLOCK.now = when

    def tick(self, seconds: int = 20) -> None:
        CLOCK.now = CLOCK.now + timedelta(seconds=seconds)

    # -- the API -----------------------------------------------------------

    def call(self, method: str, path: str, body: Any = None, *, agent: bool = False,
             ok: tuple[int, ...] = (200, 201)) -> Any:
        headers = {"x-sp-via": "mcp"} if agent else {}
        path, body = dated(path), dated_deep(body)
        if method == "GET":
            r = self.client.get(path, headers=headers)
        else:
            r = self.client.post(path, json=body, headers=headers)
        if r.status_code not in ok:
            raise ApiError(f"{method} {path} → {r.status_code}: {r.text[:600]}\nbody={json.dumps(body)[:600]}")
        self.counts[path.split("?")[0]] = self.counts.get(path.split("?")[0], 0) + 1
        try:
            return r.json()
        except ValueError:
            return r.text

    def post(self, path: str, body: Any, **kw) -> Any:
        return self.call("POST", path, body, **kw)

    def get(self, path: str, **kw) -> Any:
        return self.call("GET", path, **kw)

    def stamp(self, body: dict) -> dict:
        body.setdefault("created_date", yymmdd(CLOCK.now))
        body.setdefault("created_time", hhmm(CLOCK.now))
        return body

    # -- task references in text ------------------------------------------

    _REF_RE = re.compile(r"\{(tk|id):([a-z0-9_.:-]+)\}")

    def fill(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            kind, key = m.group(1), m.group(2)
            if kind == "tk":
                base, _, turn = key.partition(".")
                tid = self.tasks.get(base)
                if not tid:
                    raise KeyError(f"task {base!r} is referenced before it exists ({CLOCK.now})")
                return tid + (f".{turn}" if turn else "")
            if key not in self.ids:
                raise KeyError(f"id {key!r} is referenced before it exists ({CLOCK.now})")
            return self.ids[key]
        return dated(self._REF_RE.sub(sub, text))

    def adopt(self) -> None:
        """What the server does on its next read: #done, #important, kept
        messages and #prompt join their ledgers."""
        from backend import donelib, keeplib, marklib, promptlib
        self.store.rebuild()
        for mod in (donelib, marklib, keeplib, promptlib):
            mod.adopt(self.store)


# ---------------------------------------------------------------------------
# Chats, played through the capture core
# ---------------------------------------------------------------------------

_TOOL_PREFIX = {"claude-code": "cc", "codex": "codex", "opencode": "oc"}


class Chat:
    """One agent chat: a session id, a tool, a working directory."""

    def __init__(self, sim: Sim, project: str, session_ref: str, tool: str = "claude-code",
                 title: str = "", repo: Repo | None = None, headline: str = ""):
        self.sim, self.project, self.tool = sim, project, tool
        self.session_ref = session_ref
        self.agent_id = f"{_TOOL_PREFIX[tool]}-{session_ref[:8]}"
        self.title, self.repo, self.headline = dated(title), repo, dated(headline)
        self.cap = sim.capture.TurnCapture(sim.root, project, self.agent_id)
        self.last_end: _RealDT | None = None
        self.turns = 0
        sim.chats[self.agent_id] = self

    def turn(self, at: _RealDT, user: str, agent: str, minutes: float = 6,
             commits: list[tuple[float, str, Callable[[Repo], None]]] = (),
             actions: list[tuple[float, Callable[[], None]]] = (),
             helpers: list[tuple[float, float]] = (), skills: list[str] = (),
             dirty: Callable[[Repo], None] | None = None) -> _RealDT:
        """Schedule one turn. ``commits`` and ``actions`` are (minute offset,
        …) inside the turn; ``helpers`` are (start offset, length) in minutes.
        Returns when the answer ends."""
        sim = self.sim
        if self.last_end and at <= self.last_end:
            raise ValueError(f"{self.agent_id}: turn at {at} overlaps the previous one")
        end = at + timedelta(seconds=int(minutes * 60) + sim.rng.randint(5, 50))
        self.last_end = end
        first = self.turns == 0
        self.turns += 1
        self.last_n = self.turns

        def open_() -> None:
            if first:
                cwd = str(self.repo.path) if self.repo else ""
                self.cap.note_origin(self.tool, self.session_ref, cwd)
                if self.title:
                    self.cap.note_chat_title(self.title)
            self.cap.open_turn(sim.fill(user))

        sim.at(at, open_)
        for off, subject, change in commits:
            def do_commit(subject=subject, change=change):
                change(self.repo)
                self.repo.commit(subject, CLOCK.now)
            sim.at(at + timedelta(minutes=off), do_commit)
        for off, fn in actions:
            sim.at(at + timedelta(minutes=off), fn)

        def close() -> None:
            if dirty is not None:
                dirty(self.repo)
            # The agent's activity: a message or tool result every few minutes.
            pts, t = [], at
            while t < end:
                t = t + timedelta(seconds=sim.rng.randint(25, 200))
                if t < end:
                    pts.append(t)
            hs = []
            for h_off, h_len in helpers:
                h0 = at + timedelta(minutes=h_off)
                h1 = min(end, h0 + timedelta(minutes=h_len))
                hp, t = [], h0
                while t < h1:
                    hp.append(t)
                    t = t + timedelta(seconds=sim.rng.randint(20, 150))
                hs.append([int(p.timestamp() * 1000) for p in hp])
            if skills:
                self.cap.record_skills([
                    {"skill": s, "at": (at + timedelta(seconds=40)).strftime("%Y-%m-%dT%H:%M:%S"), "how": "auto"}
                    for s in skills])
            self.cap.complete_turn(sim.fill(agent), times={
                "points": [int(p.timestamp() * 1000) for p in pts], "helpers": hs})
            if self.headline and first:
                meta = json.loads(self.cap.meta_path.read_text(encoding="utf-8"))
                meta["l1_headline"] = self.headline
                self.cap.meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            sim.adopt()

        sim.at(end, close)
        return end
