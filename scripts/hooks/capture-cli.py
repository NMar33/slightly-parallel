#!/usr/bin/env python3
"""CLI face of the capture core — for adapters that shell out (OpenCode).

    capture-cli.py --phase open|complete|full --project X --data-root Y \
                   --agent NAME --text "..." [--agent-text "..."]

``open`` records the user's message, ``complete`` attaches the assistant's
answer to the pending turn, ``full`` does both at once.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import TurnCapture, format_signals, record_failure, shared  # noqa: E402


def _write_breadcrumb(data_root: str, project: str, agent_id: str, session: str, cwd: str, tool: str) -> None:
    """The per-cwd identity file the MCP server reads (GET /api/whoami), by
    the one writer of it, claude-code-capture.py (a hyphen in the name: load
    it by path). Written with the agent id this adapter was given, so the
    breadcrumb and the chat folder agree."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sp_claude_code_capture", Path(__file__).resolve().parent / "claude-code-capture.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.write_breadcrumb(data_root, project, session, cwd, tool=tool, agent_id=agent_id)


def _local(ms: float) -> str:
    """Epoch milliseconds as local, naive ``YYYY-MM-DDTHH:MM:SS``."""
    from datetime import datetime
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("open", "complete", "full"), required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--text", default="")
    # The text on stdin instead: an argument has a size limit (128 KB on
    # Linux, the whole command 32 767 characters on Windows), and a long
    # paste failed to start the process and was lost. --text stays for the
    # plugins Setup wrote before this.
    ap.add_argument("--text-stdin", action="store_true")
    # Or one JSON object on stdin: {text, times?, touched?, commit_calls?,
    # usage?}. The times of a long session as an argument passed the same
    # limit as the paste did. ``usage``: the turn's API messages with their
    # tokens (hookshared.usage_records_opencode reads them).
    ap.add_argument("--json-stdin", action="store_true")
    ap.add_argument("--agent-text", default="")
    # Origin (optional): lets the dashboard print a resume command.
    ap.add_argument("--tool", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--cwd", default="")
    # complete: an empty --text still closes the turn, as a visible gap.
    ap.add_argument("--close-if-missing", action="store_true")
    # complete: the answer's activity times, when the tool has no session
    # file to read — {"points": [epoch ms], "helpers": [[epoch ms], …]}.
    ap.add_argument("--times", default="")
    # complete: the files the turn's tool calls changed, as a JSON list.
    ap.add_argument("--touched", default="")
    args = ap.parse_args()

    if not Path(args.data_root).is_dir():
        # Never build a data root from here: an unmounted drive or a moved
        # folder would get a stray tree (the same rule as claude-code-capture.py).
        if args.phase == "open":
            print(f"[slightly-parallel] capture failed: the data root {args.data_root} does not exist — tell the user.")
        return 0
    try:
        if args.json_stdin:
            given = json.loads(sys.stdin.read() or "{}")
            if not isinstance(given, dict):
                given = {}
            args.text = str(given.get("text") or "")
            # "opencode-run": the plugin runs inside `opencode run`, no chat
            # the operator types in (hookshared.HELPER_KINDS).
            args.helper = str(given.get("helper") or "") if given.get("helper") in shared.HELPER_KINDS else ""
            if "times" in given:
                args.times = json.dumps(given["times"])
            if "touched" in given:
                args.touched = json.dumps(given["touched"])
            # [[start, end] epoch ms] of the turn's shell calls that may commit.
            args.usage = shared.usage_records_opencode(given.get("usage"))
            calls = given.get("commit_calls")
            args.commit_calls = [[_local(a), _local(b)] for a, b in calls
                                 if isinstance(a, (int, float)) and isinstance(b, (int, float))] \
                if isinstance(calls, list) and all(isinstance(c, list) and len(c) == 2 for c in calls) else None
        elif args.text_stdin:
            args.text = sys.stdin.read()
        cap = TurnCapture(args.data_root, args.project, args.agent)
        # A completion with no chat behind it (a helper session, a plugin
        # loaded mid-session) leaves no trace: noting its origin made the
        # folder of an agent with no messages.
        if (args.tool or args.session or args.cwd) and (args.phase != "complete" or cap.meta_path.exists()):
            kind = getattr(args, "helper", "")
            # Who started it: the environment this process inherited from
            # the tool, which inherited it from its parent.
            parent = shared.helper_parent(args.tool or "cli", args.session, data_root=args.data_root) if kind else ""
            cap.note_origin(args.tool, args.session, args.cwd, helper_kind=kind, helper_of=parent,
                            helper_of_by="env" if parent else "")
        if args.phase == "open" and args.cwd:
            # The per-cwd identity file the MCP server reads (GET /api/whoami).
            # Without it every write from an OpenCode agent failed with
            # "is the hook installed?" while the contract promised identity.
            _write_breadcrumb(args.data_root, args.project, args.agent, args.session, args.cwd, args.tool or "cli")
        if args.phase == "open":
            notice = format_signals(cap.open_turn(args.text), args.tool)
            if notice:
                print(notice)
        elif args.phase == "complete":
            try:
                times = json.loads(args.times) if args.times else None
            except ValueError:
                times = None
            try:
                touched = json.loads(args.touched) if args.touched else None
            except ValueError:
                touched = None
            # The turn's tokens, before it closes (the turn is the pending one).
            if getattr(args, "usage", None):
                cap.record_usage(args.usage)
            cap.complete_turn(args.text, close_if_missing=args.close_if_missing,
                              times=times if isinstance(times, dict) else None,
                              touched=[str(t) for t in touched] if isinstance(touched, list) else None,
                              commit_calls=getattr(args, "commit_calls", None))
        else:
            cap.full_turn(args.text, args.agent_text)
    except Exception as exc:  # noqa: BLE001 — capture must never break the host tool
        # Kept for the dashboard's warning, like the other adapters' failures.
        record_failure(args.data_root, args.project, args.agent, args.tool or "cli",
                       f"{args.phase}: {type(exc).__name__}: {exc}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
