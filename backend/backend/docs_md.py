"""Markdown detail documents — the L2/L3/L4 rich layer behind every CSV row.

Every entity row carries an ``md_ref`` pointing at a Markdown file with YAML
frontmatter plus ``## L2`` / ``## L3`` / ``## L4`` sections. This module
builds and parses that format, and reads referenced documents safely (an
``md_ref`` is data from a CSV — it must never escape the data root).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import frontmatter

# Section header (## L2 / ## L3 / ## L4) matcher — tolerant of leading spaces.
_SECTION_RE = re.compile(r"^\s*##\s+(L2|L3|L4)\b.*$", re.MULTILINE | re.IGNORECASE)


def resolve_under(root: Path, ref: str) -> Path | None:
    """Resolve ``ref`` against ``root``; None when it escapes the root.

    Guards against ``../`` traversal and absolute paths smuggled in through
    CSV columns or request bodies.
    """
    if not ref:
        return None
    try:
        candidate = (root / ref).resolve()
        root_resolved = root.resolve()
    except OSError:
        return None
    if candidate == root_resolved or root_resolved not in candidate.parents:
        return None
    return candidate


def parse_sections(text: str) -> tuple[str, list[str], str]:
    """Split a detail MD into (l2, l3_bullets, l4_body).

    L2 = paragraph text between ``## L2`` and the next ``##``
    L3 = list of bullet strings (lines starting ``- ``/``* ``) in the section
    L4 = raw body between ``## L4`` and EOF (may contain nested markdown)

    Frontmatter is ignored here — index metadata comes from the CSV row.
    """
    body = frontmatter.block(text)[1]

    sections: dict[str, str] = {"l2": "", "l3": "", "l4": ""}
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[name] = body[start:end].strip("\n")

    l2 = sections["l2"].strip()
    l4 = sections["l4"].strip()

    l3: list[str] = []
    for line in sections["l3"].splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            l3.append(s[2:].strip())
        elif l3:
            # An item written with a line break in it (build_detail writes
            # "- first\nsecond") goes on past its bullet; read only by its
            # bullets, it lost every line after the first.
            l3[-1] += "\n" + line.rstrip()
    return l2, [item.rstrip() for item in l3], l4


def read_detail(data_root: Path, md_ref: str) -> tuple[str, list[str], str]:
    """Parsed (l2, l3, l4) of a referenced detail doc; empties when unreadable."""
    path = resolve_under(data_root, md_ref)
    if path is None or not path.exists():
        return "", [], ""
    try:
        return parse_sections(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return "", [], ""


def _yaml_scalar(v: object) -> str:
    """One frontmatter scalar, quoted only when YAML would misread it bare."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    dumped = yaml.safe_dump(s, default_flow_style=True, allow_unicode=True,
                            width=10**6).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[:-4].rstrip()
    return dumped


def build_detail(body: dict, eid: str) -> str:
    """Frontmatter + L2/L3/L4 document for a generic entity create.

    The frontmatter is valid YAML: scalars are quoted when needed and list
    or mapping values (a file entry's ``paths``) are emitted as block YAML,
    so readers such as the file heatmap can ``safe_load`` it.
    """
    lines = ["---", f"id: {eid}"]
    for k, v in body.items():
        if k in ("l2", "l3", "l4") or v is None or v == "":
            continue
        if isinstance(v, (list, dict)):
            if not v:
                continue
            block = yaml.safe_dump(
                {k: v}, default_flow_style=False, allow_unicode=True,
                sort_keys=False, width=10**6,
            ).rstrip("\n")
            lines.append(block)
            continue
        lines.append(f"{k}: {_yaml_scalar(v)}")
    lines.append("---\n")
    l2 = body.get("l2", "")
    if l2:
        lines.extend(["## L2", str(l2), ""])
    l3 = body.get("l3", [])
    if l3:
        lines.append("## L3")
        if isinstance(l3, list):
            lines.extend(f"- {item}" for item in l3)
        else:
            lines.append(str(l3))
        lines.append("")
    l4 = body.get("l4", "")
    if l4:
        lines.extend(["## L4", str(l4), ""])
    return "\n".join(lines)


_UNSAFE_REF_CHARS = re.compile(r"[^A-Za-z0-9_.:-]+")


def safe_ref_part(value: str, fallback: str = "unknown") -> str:
    """Fold arbitrary text into a filename-safe path segment.

    Used for the date/time/project/agent parts of a minted ``md_ref`` so a
    hostile request body cannot steer the write path (``../``, ``/`` and
    anything else outside a conservative charset collapse to ``-``).
    """
    folded = _UNSAFE_REF_CHARS.sub("-", str(value)).strip("-.")
    return folded or fallback
