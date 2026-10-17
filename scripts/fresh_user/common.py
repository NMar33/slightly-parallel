"""What every stage of the fresh-user test shares: the workspace, the
report, and plain HTTP to the server under test. Standard library only."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"


@dataclass
class Check:
    stage: str
    name: str
    ok: bool
    detail: str = ""
    #: A soft check is reported and does not fail the run: an agent may word
    #: or order things differently and still be right.
    soft: bool = False


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def add(self, stage: str, name: str, ok: bool, detail: str = "", soft: bool = False) -> bool:
        self.checks.append(Check(stage, name, bool(ok), detail, soft))
        mark = "ok  " if ok else ("soft" if soft else "FAIL")
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""), flush=True)
        return bool(ok)

    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and not c.soft]

    def write(self, path: Path) -> None:
        path.write_text(json.dumps({
            "passed": not self.failed(),
            "notes": self.notes,
            "checks": [c.__dict__ for c in self.checks],
        }, indent=2), encoding="utf-8")


@dataclass
class Space:
    """The throwaway machine: a home folder, the clone, the data folder and
    a sample project, all under one temporary directory."""
    root: Path
    port: int

    @property
    def home(self) -> Path: return self.root / "home"
    @property
    def clone(self) -> Path: return self.root / "slightly-parallel"
    @property
    def data(self) -> Path: return self.root / "data"
    @property
    def sample(self) -> Path: return self.root / "sample"
    @property
    def url(self) -> str: return f"http://127.0.0.1:{self.port}"

    def env(self) -> dict[str, str]:
        """A new user's environment: their own home, nothing of Slightly Parallel set."""
        keep = ("PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "NVM_DIR", "NVM_BIN")
        if WINDOWS:
            # What Windows itself needs to run a program (sockets fail without SYSTEMROOT).
            keep += ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
                     "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
        env = {k: v for k, v in os.environ.items() if k.upper() in keep}
        if WINDOWS:
            # Windows finds the home in USERPROFILE, and the per-user folders under it.
            env.update(USERPROFILE=str(self.home), APPDATA=str(self.home / "AppData" / "Roaming"),
                       LOCALAPPDATA=str(self.home / "AppData" / "Local"))
        # Codex finds its home through the system on Windows, not USERPROFILE:
        # CODEX_HOME is what both the server under test and Codex read.
        env["CODEX_HOME"] = str(self.home / ".codex")
        env.update(HOME=str(self.home), SP_PORT=str(self.port), SHELL="/bin/sh",
                   # git in the sample project and in the clone needs an author
                   GIT_AUTHOR_NAME="Fresh User", GIT_AUTHOR_EMAIL="fresh@example.com",
                   GIT_COMMITTER_NAME="Fresh User", GIT_COMMITTER_EMAIL="fresh@example.com")
        return env


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


_COOKIES: dict[str, str] = {}


def _operator_cookie(url: str) -> str:
    """The cookie the server hands its own pages (server.OperatorCookie):
    the run stands in for the person at the browser, so it asks as a page."""
    base = "/".join(url.split("/")[:3])
    if base not in _COOKIES:
        req = urllib.request.Request(base + "/api/health", headers={"Sec-Fetch-Site": "same-origin"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _COOKIES[base] = (r.headers.get("Set-Cookie") or "").split(";", 1)[0]
    return _COOKIES[base]


def http(url: str, body: dict | None = None, timeout: float = 30) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Cookie": _operator_cookie(url)} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")


def get(space: Space, path: str) -> Any:
    return http(space.url + path)


def wait_for(space: Space, path: str, seconds: float, alive=lambda: True) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if not alive():
            return False
        try:
            http(space.url + path, timeout=3)
            return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(1)
    return False


def rows(payload: Any, key: str) -> list[dict]:
    """The list in an API answer, under its key or as the answer itself."""
    if isinstance(payload, list):
        return payload
    got = payload.get(key) if isinstance(payload, dict) else None
    return got if isinstance(got, list) else []


def eventually(read, seconds: float = 20):
    """The pages follow the files through a watcher: give a read a moment
    to become true. Returns the last value read."""
    end = time.time() + seconds
    got = read()
    while not got and time.time() < end:
        time.sleep(1)
        got = read()
    return got
