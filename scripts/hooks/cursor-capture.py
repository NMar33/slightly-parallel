#!/usr/bin/env python3
"""Cursor adapter — automatic verbatim chat capture for Slightly Parallel.

Installed by the Setup page into a project's ``.cursor/hooks.json``
(schema ``"version": 1``; https://cursor.com/docs/agent/hooks) as three
hook entries invoking this script, one per event. Cursor starts the
command with one JSON event on stdin and reads one JSON answer from stdout:

- ``beforeSubmitPrompt`` — ``prompt`` is the user's literal message; the
  turn opens with it. The answer ``{"continue": true}`` lets the prompt
  through; this script never blocks (and never exits 2, which Cursor reads
  as a block too).
- ``afterAgentResponse`` — ``text`` is the assistant's final text; it
  completes the turn verbatim. Observational: the answer is ``{}``.
- ``stop`` — the agent loop ended (``status``: completed, aborted or
  error). The event carries no reply, so a turn still open here — a
  response event that never came, or came empty — is closed as a visible
  gap rather than left to swallow the next turn's answer. The answer is
  ``{}`` (no ``followup_message``).

Common fields of every event (the docs' base fields): ``conversation_id``
(stable for the chat: the agent is keyed by it, ``cursor-<8>``),
``generation_id`` (one per user message), ``hook_event_name``,
``workspace_roots`` (the open folders), ``transcript_path``,
``cursor_version``, ``user_email``, ``model``. There is no ``cwd`` field: the
working directory is the first workspace root, else the directory Cursor
started this process in (the project root, for a project-level hook).

The project comes from ``--project`` (Setup writes one hooks.json per
project). Without it — a user-level ``~/.cursor/hooks.json`` serving every
folder — it is resolved from the workspace roots by longest-prefix match
against ``integrations.csv``, as the Codex notify adapter does; events
from unregistered folders are ignored.

Cursor reads stdout as JSON, so no ``[slightly-parallel]`` notice is
printed into the model's context; identity reaches the agent through the
breadcrumb (``GET /api/whoami``) and the MCP server. The model itself
never logs anything.

Usage (as written by Setup):
    cursor-capture.py --data-root <path> [--project <code>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import TurnCapture, record_failure  # noqa: E402

TOOL = "cursor"
PREFIX = "cursor"

# The script's one answer per event. Cursor documents only ``continue``
# and ``user_message`` for beforeSubmitPrompt, ``followup_message`` for
# stop, and nothing for afterAgentResponse. ``{"continue": true}`` is the
# allow answer; an empty object is the harmless answer everywhere else.
ALLOW = {"continue": True}
NOTHING: dict = {}


def _load_beside(name: str):
    """A sibling script by path (hyphens in the names: no import)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"sp_{name.replace('-', '_')}", Path(__file__).resolve().parent / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def agent_name(conversation_id: str) -> str:
    return f"{PREFIX}-{(conversation_id or 'unknown')[:8]}"


def first_text(payload: dict, *keys: str) -> str:
    """The first of ``keys`` the event carries as text. The docs name one
    key per event (``prompt``, ``text``); the others are read in case a
    build sends a different name, so a renamed field costs a wrong guess
    and not a lost turn. A list of strings (parts) is joined."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            value = "\n".join(str(v) for v in value if isinstance(v, str) and v)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def workspace_roots(payload: dict) -> list[str]:
    """``workspace_roots`` as the docs give it (a list of paths); read
    defensively — a single string, or ``workspace_root``/``cwd`` from a
    build that names it otherwise — since the docs show no example value."""
    for key in ("workspace_roots", "workspace_root", "cwd"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return [value]
        if isinstance(value, list):
            roots = [str(v) for v in value if isinstance(v, str) and v.strip()]
            if roots:
                return roots
    return []


def resolve_project(data_root: Path, roots: list[str]) -> str:
    """The project registered for the first root (or the process's
    directory) that integrations.csv knows."""
    codex = _load_beside("codex-capture")
    for folder in [*roots, os.getcwd()]:
        code = codex.resolve_project(data_root, folder)
        if code:
            return code
    return ""


def answer(obj: dict) -> None:
    """The one line Cursor reads. Flushed at once: the process may be ended
    the moment the loop has what it needs."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def handle(payload: dict, data_root: Path, project: str) -> dict:
    """One event, recorded; returns the answer for stdout. Raises only
    inside the capture — main() keeps the agent going whatever happens."""
    event = str(payload.get("hook_event_name") or "")
    conversation = str(payload.get("conversation_id") or payload.get("session_id") or "")
    agent = agent_name(conversation)
    roots = workspace_roots(payload)
    cwd = roots[0] if roots else os.getcwd()
    cap = TurnCapture(data_root, project, agent)
    if event == "beforeSubmitPrompt":
        prompt = first_text(payload, "prompt", "text", "message")
        if not prompt.strip():
            return ALLOW
        cap.note_origin(TOOL, conversation, cwd)
        _load_beside("claude-code-capture").write_breadcrumb(
            str(data_root), project, conversation, cwd, tool=TOOL, agent_id=agent)
        cap.open_turn(prompt)
        return ALLOW
    if event == "afterAgentResponse":
        text = first_text(payload, "text", "response", "message", "last_assistant_message")
        # An empty reply leaves the turn open: stop closes it as a gap.
        cap.complete_turn(text)
        return NOTHING
    if event == "stop":
        # A build that hands the reply here instead would still be recorded.
        text = first_text(payload, "text", "response", "last_assistant_message")
        pending = cap.meta_path.exists() and cap._load_meta().get("pending_turn") is not None
        # Diagnostics in meta.json: which keys this build sends on stop, and
        # whether the turn had its reply (from the response event, or here).
        cap.note_stop(sorted(str(k) for k in payload), found_text=bool(text) or not pending)
        if pending:
            cap.complete_turn(text, close_if_missing=True)
        return NOTHING
    return NOTHING


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--project", default="")
    args = ap.parse_args()

    payload: dict = {}
    try:
        got = json.load(sys.stdin)
        if isinstance(got, dict):
            payload = got
    except ValueError:
        pass  # malformed event — still answered, never a blocked prompt
    event = str(payload.get("hook_event_name") or "")
    reply = ALLOW if event == "beforeSubmitPrompt" or not event else NOTHING
    if not payload:
        answer(reply)
        return 0

    data_root = Path(args.data_root).expanduser()
    project = args.project
    agent = agent_name(str(payload.get("conversation_id") or ""))
    try:
        if not data_root.is_dir():
            # Never build a data root from here: an unmounted drive or a
            # moved folder would get a stray tree. Said on stderr, where
            # Cursor shows a hook's noise, and kept for the dashboard.
            raise FileNotFoundError(f"the data root {data_root} does not exist")
        if not project:
            project = resolve_project(data_root, workspace_roots(payload))
        if project:
            reply = handle(payload, data_root, project)
        # No registered project for this folder: nothing to record.
    except Exception as exc:  # noqa: BLE001 — capture must never take down the session it observes
        print(f"[slightly-parallel] capture failed: {type(exc).__name__}: {exc} — this turn was not recorded.",
              file=sys.stderr)
        if data_root.is_dir():  # the failure file never founds a data root either
            record_failure(data_root, project or "?", agent, TOOL, f"{event}: {type(exc).__name__}: {exc}")
    answer(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
