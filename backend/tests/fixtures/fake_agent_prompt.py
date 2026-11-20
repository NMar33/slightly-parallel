"""A stand-in for an agent's terminal: draws Claude Code's input box (or
Codex's composer) and logs every line typed into it.

    fake_agent_prompt.py <log> <claude-code|codex> [text already typed]

The text already typed is drawn on the input row, as if the operator were
typing there. It goes away when ``<log>.clear`` appears (the operator
cleared the line), or after a line was read (the prompt was submitted).
Used by tests/test_agent_messages.py and desktop/e2e/messages.spec.ts.

With ``SP_FAKE_CRUMB`` (a path) and ``SP_FAKE_AGENT`` (an agent id) in the
environment it first writes the breadcrumb the capture hook would write on a
prompt: the processes above a hook this program started, nearest first —
this program, then its shell. The server types into a terminal only for the
chat that breadcrumb says runs there (msgdeliver.occupant_why).
"""

from __future__ import annotations

import importlib.util
import json
import os
import select
import sys
import time
from pathlib import Path

log, tool = sys.argv[1], sys.argv[2]
typed = sys.argv[3] if len(sys.argv) > 3 else ""
clear = log + ".clear"

crumb, agent = os.environ.get("SP_FAKE_CRUMB", ""), os.environ.get("SP_FAKE_AGENT", "")
if crumb and agent:
    spec = importlib.util.spec_from_file_location(
        "sp_fake_hookshared", Path(__file__).resolve().parents[2] / "backend" / "hookshared.py")
    shared = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(shared)  # type: ignore[union-attr]
    Path(crumb).parent.mkdir(parents=True, exist_ok=True)
    Path(crumb).write_text(json.dumps({"agent_id": agent, "session_id": agent, "at": time.time(),
                                       "pids": [os.getpid(), *shared.ancestors()]}), encoding="utf-8")


got: list[str] = []


def draw(text: str) -> None:
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 80
    rule = "\x1b[38;5;244m" + "─" * max(10, cols - 2) + "\x1b[39m\n"
    out = "\x1b[2J\x1b[Hfake agent ready\n" + "".join(f"got: {g}\n" for g in got[-5:]) + "\n"
    if tool == "codex":
        shown = text or "\x1b[2mAsk Codex to do anything\x1b[0m"
        out += f"\x1b[1m›\x1b[0m {shown}\n\n  fake-model · ~/work\n"
    else:
        out += rule + f"\x1b[39m❯ {text}\n" + rule + "  ? for shortcuts\n"
    sys.stdout.write(out)
    sys.stdout.flush()


draw(typed)
while True:
    ready, _, _ = select.select([sys.stdin], [], [], 0.2)
    if ready:
        line = sys.stdin.readline()
        if not line:
            break
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(line)
        got.append(line.rstrip("\n"))
        typed = ""
        draw(typed)
    elif typed and os.path.exists(clear):
        typed = ""
        draw(typed)
