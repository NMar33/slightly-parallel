"""What every stage of the fresh-user test shares: the workspace, the
report, and plain HTTP to the server under test. Standard library only."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
import string
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OPERATOR_COOKIE_TIMEOUT_S = 10
API_REQUEST_TIMEOUT_S = 30
DOWNLOAD_TIMEOUT_S = 120
START_PROBE_TIMEOUT_S = 3
BOARD_SETTLE_S = 2
BOARD_POLL_S = 0.2

REPO = Path(__file__).resolve().parents[2]


def _chatstore() -> Any:
    """Where a chat's folder lives (backend/backend/chatstore.py), by path:
    this test imports nothing of the backend package."""
    spec = importlib.util.spec_from_file_location("sp_chatstore_fresh", REPO / "backend" / "backend" / "chatstore.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chatstore = _chatstore()
WINDOWS = os.name == "nt"
#: A key a new user has in their environment, as many do: the server's
#: report must never show it (stages.server_report).
PLANTED_KEY = "sk-proj-freshPlanted7f3a91c0e5b24d68aa"
# Codex needs this for redaction only. Consume it before any subprocess starts.
_DIAGNOSTIC_OPENAI_KEY = os.environ.pop("SP_DIAGNOSTIC_OPENAI_KEY", "")
_KEY_ALPHABET = frozenset(string.ascii_letters + string.digits + "_-")
_ROW_DECORATION = r"[ \t│║▌›>⎿|+#]*"
_ROW_LABEL = r"(?:(?:[0-9]{1,8}|-)[ \t]+|(?!(?i:sk)-)[A-Za-z][A-Za-z0-9_]{0,7}-(?=\S))"
_ROW_PREFIX = re.compile(r"(?m)^" + _ROW_DECORATION + _ROW_LABEL)
_NEXT_ROW = r"\r?\n" + _ROW_DECORATION + r"(?:" + _ROW_LABEL + r")?"
_DIAGNOSTIC_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_DIAGNOSTIC_KEY = re.compile(
    r"(?im)(?<![\w-])sk-(?:"
    # A PTY can wrap the prefix, the marker, or the suffix onto another row.
    r"(?:[a-z0-9]+(?:\r?\n[ \t]*[a-z0-9]+)?-)*[ \t]*(?:\r?\n[ \t]*)?"
    r"(?:…+|\.{2,}|\*{2,})[ \t]*[\w-]*"
    r"(?:\r?\n[ \t]*[\w-]+(?=[ \t]*(?:[│║][ \t]*)?$))?"
    r"|(?:ant|proj|svcacct|admin|live|test)-[a-z0-9_-]+|[a-z0-9_]{20,})"
)
_GITHUB_INSTALLATION_KEY = re.compile(
    r"(?<![\w-])" + (r"(?:" + _NEXT_ROW + r")?").join("ghs_")
    + r"(?:" + (r"(?:[A-Za-z0-9](?:" + _NEXT_ROW + r")?){35}[A-Za-z0-9](?![A-Za-z0-9])")
    + r"|[A-Za-z0-9]{20,})"
)
_MASKED_KEY_ECHO = re.compile(
    r"(?i)(?<![\w-])sk-[a-z0-9_-]*(?:\*(?:" + _NEXT_ROW + r")?){2,}"
    r"[ \t]*[a-z0-9_-]{0,4}(?![a-z0-9_-])"
)
_WRAPPED_KEY_PREFIX = re.compile(
    r"(?i)(?<![\w-])(?:" + "|".join(
        (r"(?:" + _NEXT_ROW + r")?").join(map(re.escape, "sk-" + kind + "-"))
        for kind in ("ant", "proj", "svcacct", "admin", "live", "test")
    ) + r")"
)
PROVIDER_ACCOUNT_FAILURE_CLASSES = {
    "L0-billing": "outside (billing)",
    "L0-eligibility": "outside (billing/eligibility)",
}
_ELIGIBILITY_ERROR = re.compile(
    r"\b(?:codex_byok_restricted_by_api_credit_promo|(?:account|organization)_(?:not_eligible|ineligible))\b",
    re.IGNORECASE,
)
_BILLING_ERROR = re.compile(
    r"\b(?:credit\s+balance\s+(?:is\s+)?too\s+low|insufficient_quota|billing_hard_limit_reached"
    r"|quota\s+exceeded\.\s*check\s+your\s+plan\s+and\s+billing\s+details"
    r"|exceeded\s+your\s+current\s+quota|402\s*:?\s+payment\s+required)\b", re.IGNORECASE,
)


def provider_account_error(text: str) -> str:
    if _ELIGIBILITY_ERROR.search(text):
        return "L0-eligibility"
    return "L0-billing" if _BILLING_ERROR.search(text) else ""


def _known_key_spans(text: str, known_key: str) -> list[tuple[int, int]]:
    keys = {known_key, _DIAGNOSTIC_OPENAI_KEY, os.environ.get("ANTHROPIC_API_KEY", ""),
            os.environ.get("OPENAI_API_KEY", ""), os.environ.get("CODEX_OPENAI_API_KEY", "")} - {""}
    if not keys:
        return []
    needles = {"".join(ch for ch in key if ch in _KEY_ALPHABET)
               for key in keys | {key[-20:] for key in keys if len(key) >= 20}} - {""}
    alphabet_positions = [i for i, ch in enumerate(text) if ch in _KEY_ALPHABET]
    projections = [alphabet_positions]
    if "\n" in text:
        label_positions = {i for label in _ROW_PREFIX.finditer(text) for i in range(*label.span())}
        if label_positions:
            projections.append([i for i in alphabet_positions if i not in label_positions])
    spans = []
    for positions in projections:
        compact = "".join(text[i] for i in positions)
        for needle in needles:
            start = compact.find(needle)
            while start != -1:
                spans.append((positions[start], positions[start + len(needle) - 1] + 1))
                start = compact.find(needle, start + len(needle))
    return spans


def redact_diagnostics(text: str, known_key: str = "") -> str:
    text = _DIAGNOSTIC_ANSI.sub("", text)
    spans = _known_key_spans(text, known_key)
    spans.extend(match.span() for pattern in (_DIAGNOSTIC_KEY, _MASKED_KEY_ECHO, _GITHUB_INSTALLATION_KEY)
                 for match in pattern.finditer(text))
    clean, end = [], 0
    for start, stop in sorted(spans):
        if start >= end:
            clean.extend((text[end:start], "[redacted]"))
        end = max(end, stop)
    clean.append(text[end:])
    return "".join(clean)


def contains_diagnostic_key(text: str) -> bool:
    text = _DIAGNOSTIC_ANSI.sub("", text)
    return bool(_known_key_spans(text, "") or _WRAPPED_KEY_PREFIX.search(text)
                or _DIAGNOSTIC_KEY.search(text) or _MASKED_KEY_ECHO.search(text)
                or _GITHUB_INSTALLATION_KEY.search(text))


@dataclass
class Check:
    stage: str
    name: str
    ok: bool
    detail: str = ""
    #: A soft check is reported and does not fail the run: an agent may word
    #: or order things differently and still be right.
    soft: bool = False
    failure_class: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def console_detail(detail: str) -> str:
        if not detail:
            return ""
        return "See the audited report artifact." if os.environ.get("GITHUB_ACTIONS") == "true" else detail

    def add(self, stage: str, name: str, ok: bool, detail: str = "", soft: bool = False,
            *, failure_class: str = "unclassified") -> bool:
        stage, name = redact_diagnostics(stage), redact_diagnostics(name)
        detail = redact_diagnostics(detail)
        self.checks.append(Check(stage, name, bool(ok), detail, soft, "" if ok else failure_class))
        mark = "ok  " if ok else ("soft" if soft else "FAIL")
        print(f"  [{mark}] {name}" + (f" — {self.console_detail(detail)}" if detail and not ok else ""), flush=True)
        return bool(ok)

    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and not c.soft]

    def write(self, path: Path) -> None:
        def scrub(value: Any) -> Any:
            if isinstance(value, str):
                return redact_diagnostics(value)
            if isinstance(value, dict):
                return {scrub(key): scrub(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [scrub(item) for item in value]
            return value

        path.write_text(json.dumps({
            "passed": not self.failed(),
            "notes": scrub(self.notes),
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
        # Keep the installed CLI version for the duration of a test run.
        env["DISABLE_AUTOUPDATER"] = "1"
        env["FRESH_PLANTED_API_KEY"] = PLANTED_KEY
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
        with urllib.request.urlopen(req, timeout=OPERATOR_COOKIE_TIMEOUT_S) as r:
            _COOKIES[base] = (r.headers.get("Set-Cookie") or "").split(";", 1)[0]
    return _COOKIES[base]


def http(url: str, body: dict | None = None, timeout: float = API_REQUEST_TIMEOUT_S) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    # The cookie on every request, a read too: the run stands in for the
    # person at the browser, and the terminal's state is handed only to
    # the operator's pages.
    headers = {"Cookie": _operator_cookie(url), **({"Content-Type": "application/json"} if data else {})}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")


def fetch_bytes(url: str, timeout: float = DOWNLOAD_TIMEOUT_S) -> bytes:
    """A file the page downloads (a backup), as it comes."""
    req = urllib.request.Request(url, headers={"Cookie": _operator_cookie(url)})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get(space: Space, path: str) -> Any:
    return http(space.url + path)


def wait_for(space: Space, path: str, seconds: float, alive=lambda: True) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if not alive():
            return False
        try:
            http(space.url + path, timeout=START_PROBE_TIMEOUT_S)
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


def new_task_rows(space: Space, code: str, known: set[str], seconds: float = BOARD_SETTLE_S) -> list[dict]:
    """Collect new cards while the file watcher catches up after the CLI has exited."""
    deadline = time.monotonic() + seconds
    seen: dict[str, dict] = {}
    while True:
        for row in rows(get(space, f"/api/tasks?project={code}"), "tasks"):
            if row["id"] not in known:
                seen[row["id"]] = row
        if time.monotonic() >= deadline:
            return list(seen.values())
        time.sleep(BOARD_POLL_S)
