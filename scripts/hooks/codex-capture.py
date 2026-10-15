#!/usr/bin/env python3
"""Codex CLI adapter — end-of-turn chat capture for Slightly Parallel.

Installed once, globally, via ``notify`` in ``~/.codex/config.toml``:

    notify = ["python3", "<slightly-parallel>/scripts/hooks/codex-capture.py",
              "--data-root", "<data-root>"]

Codex invokes it with one JSON argument on ``agent-turn-complete``,
carrying the user's input and the agent's final message. Because notify is
global, the project is resolved from the event's working directory by
longest-prefix match against the folders registered in
``integrations.csv`` — events from unregistered folders are ignored.

Codex calls ``notify`` legacy now; its hooks system (``UserPromptSubmit``
and ``Stop`` on stdin, the same shape as Claude Code's) is served by
``claude-code-capture.py --tool codex`` and installed per project by the
Setup page. This adapter stays for installs that predate hooks.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import TurnCapture, record_failure  # noqa: E402


def resolve_project(data_root: Path, cwd: str) -> str:
    """Project code whose registered folder contains ``cwd`` (longest wins)."""
    if not cwd:
        return ""
    try:
        cwd_path = Path(cwd).resolve()
    except OSError:
        return ""
    best_code, best_len = "", -1
    try:
        with open(data_root / "integrations.csv", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                raw = (row.get("path") or "").strip()
                code = (row.get("project") or "").strip()
                if not raw or not code:
                    continue
                folder = Path(raw)
                if (
                    cwd_path == folder or folder in cwd_path.parents
                ) and len(str(folder)) > best_len:
                    best_code, best_len = code, len(str(folder))
    except OSError:
        return ""
    return best_code


def joined(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v).strip()
    return str(value or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("payload", nargs="?", default="")
    args = ap.parse_args()

    try:
        event = json.loads(args.payload)
    except json.JSONDecodeError:
        return 0

    if str(event.get("type") or "") != "agent-turn-complete":
        return 0

    data_root = Path(args.data_root).expanduser()
    project = resolve_project(data_root, str(event.get("cwd") or ""))
    if not project:
        return 0  # not a Slightly Parallel-registered folder

    # thread-id is the session; turn-id changes every turn. The agent is
    # the session, so one Codex conversation stays one chat.
    thread_id = str(event.get("thread-id") or event.get("thread_id") or "")
    turn_id = str(event.get("turn-id") or event.get("turn_id") or "session")
    session = thread_id or turn_id
    user_text = joined(
        event.get("input-messages") or event.get("input_messages")
    )
    agent_text = joined(
        event.get("last-assistant-message")
        or event.get("last_assistant_message")
        # the name this adapter shipped with; never emitted by Codex
        or event.get("last-agent-message")
        or event.get("last_agent_message")
    )
    try:
        cap = TurnCapture(data_root, project, f"codex-{session[:8]}")
        cap.note_origin("codex", session, str(event.get("cwd") or ""))
        cap.full_turn(user_text, agent_text)
    except Exception as exc:  # noqa: BLE001 — capture must never break the host tool
        record_failure(data_root, project, f"codex-{session[:8]}", "codex", f"{type(exc).__name__}: {exc}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
