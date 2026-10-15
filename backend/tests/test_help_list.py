"""#help answers from one list; every command of the contract is on it, and nothing else."""

from __future__ import annotations

import re
from pathlib import Path

PARTS = Path(__file__).resolve().parents[2] / "prompts" / "contract"


def _tag(s: str) -> str:
    return " ".join(re.sub(r"<[^>]*>", " ", s).split()).lstrip("#")


def test_the_help_list_names_every_command_and_no_other() -> None:
    commands: set[str] = set()
    help_body = ""
    for path in PARTS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for line in re.findall(r"^command:\s*(.+)$", text, re.M):
            commands.add(_tag(line.partition("|")[0]))
        if re.search(r"^key: help$", text, re.M):
            help_body = text.split("\n---\n", 1)[1]
    listed = {_tag(c) for c in re.findall(r"^\| `([^`]+)`", help_body, re.M)}
    # `#important-agent · -task · -message` is one row for the three forms.
    listed = {c.split(" ·")[0] for c in listed}
    assert commands <= listed, f"not on the #help list: {sorted(commands - listed)}"
    assert listed <= commands | {"important-agent"}, f"on the list, not in the contract: {sorted(listed - commands)}"
