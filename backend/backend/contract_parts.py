"""The agent contract as parts — short files composed into SLIGHTLY-PARALLEL.md.

``prompts/contract/NN-key.md`` in the repo holds one block of the contract
each: a small frontmatter (what the block is, which section it opens,
the ``/command`` rows it contributes, whether it is on) and the markdown
body. ``compose`` joins the enabled parts in filename order into the one
file agents read, generating the commands table from the parts' rows so
it cannot drift from the blocks. Editing happens per part (Settings →
Agent prompts); every save recomposes SLIGHTLY-PARALLEL.md.

Frontmatter — plain ``key: value`` lines, no YAML machinery::

    ---
    key: scan
    section: 4
    heading: ## 4. When and what to post     (only the part that opens a section)
    title: Checkpoint
    enabled: true
    command: /scan | Checkpoint: POST a scan, …   (repeatable)
    ---
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter
from .file_safety import atomic_write

PARTS_DIR = "prompts/contract"
CONTRACT_FILE = "SLIGHTLY-PARALLEL.md"
COMMANDS_MARKER = "<!-- commands -->"

_FILE_RE = re.compile(r"^(\d+)-([a-z0-9-]+)\.md$")


@dataclass
class Part:
    key: str
    filename: str
    title: str
    section: str
    heading: str
    enabled: bool
    commands: list[tuple[str, str]]
    body: str
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def order(self) -> int:
        m = _FILE_RE.match(self.filename)
        return int(m.group(1)) if m else 0

    def meta(self) -> dict:
        return {
            "part": self.key,
            "filename": self.filename,
            "title": self.title,
            "section": self.section,
            "heading": self.heading,
            "enabled": self.enabled,
            "commands": [{"cmd": c, "what": w} for c, w in self.commands],
        }


# ---------------------------------------------------------------------------
# One file
# ---------------------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[list[tuple[str, str]], str]:
    """``(pairs, body)`` — pairs keep order and repeats; body without the fence.

    The convention this module set is now the backend's only one; the
    parser itself lives in ``frontmatter.py``, which every reader of a
    ``---`` block imports. This name stays: the contract is read by it.
    """
    return frontmatter.pairs(text)


def parse_part(text: str, filename: str) -> Part:
    pairs, body = split_frontmatter(text)
    meta: dict[str, str] = {}
    commands: list[tuple[str, str]] = []
    for k, v in pairs:
        if k == "command":
            cmd, _, what = v.partition(" | ")
            commands.append((cmd.strip(), what.strip()))
        else:
            meta[k] = v
    m = _FILE_RE.match(filename)
    key = meta.get("key") or (m.group(2) if m else filename.removesuffix(".md"))
    known = {"key", "title", "section", "heading", "enabled"}
    return Part(
        key=key,
        filename=filename,
        title=meta.get("title") or key,
        section=meta.get("section", ""),
        heading=meta.get("heading", ""),
        enabled=meta.get("enabled", "true").lower() not in ("false", "no", "off", "0"),
        commands=commands,
        body=body.rstrip("\n") + "\n" if body.strip() else "",
        extra={k: v for k, v in meta.items() if k not in known},
    )


def render_part(part: Part) -> str:
    lines = ["---", f"key: {part.key}"]
    if part.section:
        lines.append(f"section: {part.section}")
    if part.heading:
        lines.append(f"heading: {part.heading}")
    lines.append(f"title: {part.title}")
    lines.append(f"enabled: {'true' if part.enabled else 'false'}")
    for cmd, what in part.commands:
        lines.append(f"command: {cmd} | {what}")
    for k, v in part.extra.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + part.body


# ---------------------------------------------------------------------------
# The folder
# ---------------------------------------------------------------------------


def parts_dir(prompt_root: Path) -> Path:
    return Path(prompt_root) / PARTS_DIR


def has_parts(prompt_root: Path) -> bool:
    d = parts_dir(prompt_root)
    return d.is_dir() and any(_FILE_RE.match(p.name) for p in d.iterdir())


def load_parts(prompt_root: Path) -> list[Part]:
    d = parts_dir(prompt_root)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir(), key=lambda p: p.name):
        if not _FILE_RE.match(p.name):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(parse_part(text, p.name))
    return out


def find_part(prompt_root: Path, key: str) -> Part | None:
    for p in load_parts(prompt_root):
        if p.key == key:
            return p
    return None


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def commands_table(parts: list[Part]) -> str:
    rows = ["| Command | What you do |", "|---|---|"]
    for p in parts:
        if not p.enabled:
            continue
        for cmd, what in p.commands:
            rows.append(f"| `{cmd}` | {what} |")
    return "\n".join(rows)


def compose(parts: list[Part]) -> str:
    """The contract: enabled parts in order, headings before bodies, the
    commands table generated where a body carries the marker."""
    blocks: list[str] = []
    table = commands_table(parts)
    for p in parts:
        if not p.enabled:
            continue
        body = p.body.replace(COMMANDS_MARKER, table) if COMMANDS_MARKER in p.body else p.body
        # A part whose steps live in a skill says so in `brief`: the contract
        # carries those few lines, and the whole body reaches an agent only
        # when it is needed — through the skill's tool and the MCP prompt.
        if p.extra.get("brief"):
            body = p.extra["brief"].strip() + "\n"
        piece = (p.heading.rstrip() + "\n\n" if p.heading else "") + body.rstrip("\n")
        if piece.strip():
            blocks.append(piece)
    return "\n\n".join(blocks) + "\n"


def write_contract(prompt_root: Path) -> str | None:
    """Recompose SLIGHTLY-PARALLEL.md from the parts; None when there are no parts."""
    parts = load_parts(prompt_root)
    if not parts:
        return None
    text = compose(parts)
    atomic_write(Path(prompt_root) / CONTRACT_FILE, text)
    return text
