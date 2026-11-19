"""A stand-in for an agent's terminal: draws Claude Code's input box (or
Codex's composer) and logs every line typed into it.

    fake_agent_prompt.py <log> <claude-code|codex> [text already typed]

The text already typed is drawn on the input row, as if the operator were
typing there. It goes away when ``<log>.clear`` appears (the operator
cleared the line), or after a line was read (the prompt was submitted).
Used by tests/test_agent_messages.py and desktop/e2e/messages.spec.ts.
"""

from __future__ import annotations

import os
import select
import sys

log, tool = sys.argv[1], sys.argv[2]
typed = sys.argv[3] if len(sys.argv) > 3 else ""
clear = log + ".clear"


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
