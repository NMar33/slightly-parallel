"""The keep-alive enrollment and delivery state shared by the scheduler and hooks."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    from . import hookshared as shared
except ImportError:  # capture loads this module by file path
    _spec = importlib.util.spec_from_file_location("sp_hookshared_for_ping", Path(__file__).with_name("hookshared.py"))
    assert _spec is not None and _spec.loader is not None
    shared = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(shared)

DIRECTORY = ".ping"
HEADER_SUFFIX = " · ping"
WINDOW_SECONDS = 120
_PROMPT_RE = re.compile(r"\[SP ping\] ([0-9a-f]{32}) Reply with one word\.")
AGENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
COMMAND_RE = re.compile(
    r"(?<![\w#])#ping(?![\w-])(?:[ \t]+([A-Za-z0-9][A-Za-z0-9_.-]{0,79})(?![\w.-])"
    r"(?:[ \t]+(off)(?![\w-]))?)?",
    re.IGNORECASE,
)


def read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("invalid keep-alive state")
    return value


def state_path(root: Path, agent: str) -> Path:
    if AGENT_RE.fullmatch(agent) is None:
        raise ValueError("invalid keep-alive agent id")
    return root / DIRECTORY / f"{agent}.json"


def _write(path: Path, value: dict[str, Any]) -> None:
    fd, name = tempfile.mkstemp(prefix=".ping-", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        shared.replace_file(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def edit(path: Path) -> Iterator[dict[str, Any]]:
    """Read and replace one agent's state under a strict cross-process lock."""
    with path.with_suffix(".lock").open("a", encoding="utf-8") as lock:
        deadline = time.monotonic() + 2
        while not shared.try_lock(lock):
            if time.monotonic() >= deadline:
                raise TimeoutError("keep-alive state is busy")
            time.sleep(shared.HOOK_LOCK_POLL_INTERVAL_S)
        try:
            state = read(path)
            before = dict(state)
            yield state
            if state != before:
                _write(path, state)
        finally:
            shared.unlock(lock)


def enroll(root: Path, agent: str, *, enabled: bool) -> None:
    path = state_path(root, agent)
    path.parent.mkdir(exist_ok=True)
    with edit(path) as state:
        state["enabled"] = enabled



def take(root: Path, agent: str, terminal: str, prompt: str) -> bool:
    """Consume a terminal prompt only for its intended chat, pane and window."""
    match = _PROMPT_RE.fullmatch(prompt)
    if match is None or not terminal:
        return False
    path = state_path(root, agent)
    if not path.is_file():
        return False
    with edit(path) as state:
        now = shared.now_epoch()
        sent = state.get("sent_at")
        expires = state.get("expires_at")
        if not (
            state.get("nonce") == match.group(1) and state.get("terminal") == terminal
            and isinstance(sent, (int, float)) and isinstance(expires, (int, float))
            and sent <= now < expires
        ):
            return False
        state.pop("nonce")
        return True


def envelope() -> tuple[str, str]:
    nonce = secrets.token_hex(16)
    return nonce, f"[SP ping] {nonce} Reply with one word."


def reserve(path: Path, nonce: str, terminal: str, now: float, interval: int) -> bool:
    """Record the exact prompt before its paste, under the enrollment lock."""
    with edit(path) as state:
        if not due(state, now, interval):
            return False
        state.update(nonce=nonce, terminal=terminal, sent_at=now, expires_at=now + WINDOW_SECONDS)
        return True


def due(state: dict[str, Any], now: float, interval: int) -> bool:
    sent = state.get("sent_at")
    wait = max(interval, WINDOW_SECONDS) if state.get("nonce") else interval
    return state.get("enabled") is True and (sent is None or now - float(sent) >= wait)
