"""The architecture page: what a project is, as claims with their evidence.

The architecture ledger (routers/architecture.py) is a log: what each scan
added, changed or removed. It never answered "what is this project, and
what can it do now?", and its eight groups fit a web service and little
else. The page is the picture. One per project, written by the agent that
works there, for a team lead who was not in the chat, in a layout that holds
for a web service, a data analysis, a book or a folder of documents alike.

Trials on five real projects of different kinds (artifact
architecture-page-trials) shaped the three rules built in here:

- **Computed facts are not written by a model.** Standing, size, what
  changed when, recent commits: projectfacts.py.
- **Every item is a claim with its evidence**: where it lives, how the
  writer knows, who made it, who checked it. The server checks each `where`
  against the folder, and marks a claim whose file changed after the page
  was written.
- **The page grows by versions.** A cold reader of a large folder opens
  forty files out of thousands, and which forty is luck. Each version keeps
  what is verified, corrects what is wrong and adds what its writer touched.

The page lives in the project's own folder of the data root:
``projects/<project>/architecture/v001.md`` … — the newest is the page.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import frontmatter, versioned
from .db import ViewStore
from .file_entries import project_path

WORD_BUDGET = 1200
from .limits import MAX_PAGE_CHARS as MAX_CHARS  # noqa: E402 — the one cap
from .date_utils import now_iso
REQUIRED = ("What it is", "The live work", "What it does or has produced", "What is owed")
PART = "45-architecture-page.md"
PROSE_SECTIONS = ("how the main thing works", "words", "not read", "the live work")

_HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$")
_SLOTS = ("where", "seen", "made by", "checked by")
_SLOT_RE = re.compile(r"(?i)(?:^|[\s·.;,(—-])\**(where|seen|made by|checked by)\**\s*:\**\s*")
_PATHISH_RE = re.compile(r"`([^`\s]*(?:/|\.[A-Za-z0-9]{1,5})[^`\s]*)`")


KIND = "architecture"


def folder(store: ViewStore, project: str) -> Path:
    return versioned.folder(store, project, KIND)


def versions(store: ViewStore, project: str) -> list[dict[str, Any]]:
    def read(text: str) -> dict[str, Any]:
        meta, body = _split(text)
        return {"at": meta.get("at", ""), "agent_id": meta.get("agent_id", ""),
                "note": meta.get("note", ""), "words": len(body.split()), "_body": body}

    return versioned.versions(store, project, KIND, read)


def _split(text: str) -> tuple[dict[str, str], str]:
    """The page's own ``---`` block: last key wins, and a quoted note is
    unquoted (``write`` quotes it so a colon in the note survives)."""
    pairs, body = frontmatter.pairs(text)
    return {k: v.strip('"') for k, v in pairs}, body


def _first_path(where: str) -> str:
    """The path inside a `where:` slot: backticks off, `file:Symbol` cut, prose ignored."""
    m = re.search(r"`([^`]+)`", where)
    raw = (m.group(1) if m else where.split(",")[0].split(" (")[0]).strip().rstrip(".")
    return raw.split(":")[0].strip() if not re.match(r"^[a-z]+://", raw) else ""


def _claim(item: str) -> dict[str, Any] | None:
    """One list item as a claim. Writers format loosely: slots may be joined by
    "·", a full stop or a dash, in any case, and a path may stand alone in
    backticks at the end. An item with neither a slot nor a path is prose."""
    marks = list(_SLOT_RE.finditer(item))
    claim: dict[str, Any] = {}
    if marks:
        claim["text"] = item[:marks[0].start()].strip(" ·.;,—-")
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(item)
            claim[m.group(1).lower().replace(" ", "_")] = item[m.end():end].strip(" ·;,—-").rstrip(".")
    else:
        claim["text"] = item.strip()
    if "where" not in claim:
        paths = _PATHISH_RE.findall(item)
        if paths:
            claim["where"] = f"`{paths[-1]}`"
    if not marks and "where" not in claim:
        return None
    claim["text"] = re.sub(r"\*\*", "", claim["text"]).strip()
    return claim


def parse(body: str) -> list[dict[str, Any]]:
    """Sections, and inside each the items that are claims (carry a slot)."""
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in body.splitlines():
        h = _HEADING_RE.match(line)
        if h:
            current = {"title": h.group(1), "lines": [], "claims": []}
            sections.append(current)
            continue
        if current is None:
            continue
        current["lines"].append(line)
    for sec in sections:
        text = "\n".join(sec.pop("lines")).strip()
        sec["body"] = text
        # An item may wrap over lines: join a list item with its continuation lines.
        items, buf = [], ""
        for line in text.splitlines():
            if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line):
                if buf:
                    items.append(buf)
                buf = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line)
            elif buf and line.strip():
                buf += " " + line.strip()
            else:
                if buf:
                    items.append(buf)
                buf = ""
        if buf:
            items.append(buf)
        title = sec["title"].lower().strip()
        if title == "what it is" or any(w in title for w in PROSE_SECTIONS):
            continue        # steps, words and "not read" lists name paths in passing: prose, not claims
        for item in items:
            claim = _claim(item)
            if claim:
                sec["claims"].append(claim)
    return sections


def check(store: ViewStore, project: str, sections: list[dict[str, Any]], written_at: str = "") -> dict[str, int]:
    """Mark each claim's path: found or not, and changed since the page was written."""
    root = project_path(store, project)
    try:
        since = datetime.fromisoformat(written_at).timestamp() if written_at else 0.0
    except ValueError:
        since = 0.0
    counts = {"claims": 0, "with_path": 0, "missing": 0, "changed_since": 0}
    for sec in sections:
        for claim in sec["claims"]:
            counts["claims"] += 1
            rel = _first_path(claim.get("where", ""))
            if not rel or root is None:
                continue
            counts["with_path"] += 1
            target = (root / rel).resolve()
            claim["path"] = rel
            # Inside the folder, not merely a name that starts the same way:
            # /work/proj-secret is not inside /work/proj.
            if not target.is_relative_to(root.resolve()) or not target.exists():
                claim["path_found"] = False
                counts["missing"] += 1
                continue
            claim["path_found"] = True
            if since:
                try:
                    changed = target.stat().st_mtime
                except OSError:
                    continue
                if changed > since + 60:
                    claim["changed_since"] = datetime.fromtimestamp(changed).strftime("%Y-%m-%d")
                    counts["changed_since"] += 1
    return counts


def current(store: ViewStore, project: str) -> dict[str, Any] | None:
    all_ = versions(store, project)
    if not all_:
        return None
    last = all_[-1]
    sections = parse(last["_body"])
    counts = check(store, project, sections, last["at"])
    return {"n": last["n"], "at": last["at"], "agent_id": last["agent_id"], "note": last["note"],
            "words": last["words"], "text": last["_body"], "sections": sections, "counts": counts}


def write(store: ViewStore, project: str, agent_id: str, text: str, note: str = "") -> dict[str, Any]:
    body = (text or "").strip()
    if not body:
        raise ValueError("text is required: the whole page, in markdown")
    if len(body) > MAX_CHARS:
        raise ValueError(f"the page is over {MAX_CHARS} characters")
    sections = parse(body)
    titles = [s["title"].lower() for s in sections]
    missing = [r for r in REQUIRED if not any(r.lower() in t for t in titles)]
    if missing:
        raise ValueError("the page lacks the required heading(s): " + ", ".join(f"“{m}”" for m in missing)
                         + " — see the layout in the instructions (architecture_material)")
    warnings: list[str] = []
    counts = check(store, project, sections)
    if counts["claims"] == 0:
        raise ValueError("no item carries its evidence — each item is a claim: "
                         "`name — what it is · where: <path> · seen: <how you know> · made by: … · checked by: …`")
    for sec in sections:
        for claim in sec["claims"]:
            if claim.get("path_found") is False:
                warnings.append(f"“{claim['text'][:60]}”: where `{claim['path']}` is not in the project folder")

    unseen = sum(1 for sec in sections for c in sec["claims"] if not c.get("seen"))
    if unseen:
        warnings.insert(0, f"{unseen} of {counts['claims']} items do not say how you know: add `seen: <what you ran or opened>` "
                           "or write \"per <file> of <date>, not checked\"")
    words = len(body.split())
    if words > WORD_BUDGET:
        warnings.append(f"{words} words against a budget of {WORD_BUDGET}: shorten old material first")
    with versioned.numbering(store, project, KIND):
        prior = versions(store, project)
        if prior and prior[-1]["_body"].strip() == body:
            return {"n": prior[-1]["n"], "existing": True, "warnings": warnings[:20], "counts": counts}
        n = versioned.next_number(prior)
        at = now_iso()
        versioned.write(store, project, KIND, n, "md",
                        f'---\nn: {n}\nat: {at}\nagent_id: {agent_id}\nnote: "{versioned.note_of(note)}"\n---\n{body}\n')
    return {"n": n, "existing": False, "at": at, "warnings": warnings[:20], "counts": counts}


def instructions(repo_root: Path) -> str:
    try:
        text = (repo_root / "prompts" / "contract" / PART).read_text(encoding="utf-8")
    except OSError:
        return ""
    return frontmatter.body_of(text).strip()


def fingerprint(store: ViewStore) -> str:
    """For ETags: the page lives outside the CSV ledgers."""
    return versioned.fingerprint(store, KIND)
