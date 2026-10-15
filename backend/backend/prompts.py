"""The files that tell agents how to act — readable and editable from Settings.

Two files: ``SLIGHTLY-PARALLEL.md`` (the contract every agent reads) and the
``AGENTS.md`` block template Setup writes into each project. Both live in
the repo, because that is where agents read them from; the data root holds
what makes editing safe — the original as first seen, and one version per
save, so any state can be restored.

The contract is composed from parts (``contract_parts.py``): short files
under ``prompts/contract/``, one block each. When the parts folder exists,
``SLIGHTLY-PARALLEL.md`` is read-only through this store — edits go to a part
(key ``contract.<part>``: text is the part's body, the frontmatter is
metadata) and every save recomposes the file.

The contract's key was ``merkhet`` (the working title) until 2026-10-14:
``merkhet`` and ``merkhet.<part>`` still resolve to the same records, and a
data root whose ``prompts/merkhet*`` folders hold the operator's versions
keeps using them — nothing is moved.

Layout under the data root::

    prompts/<key>/original.md          the file as it was before the first edit
    prompts/<key>/versions/<id>.md     the content a save or restore replaced
    prompts/<key>/history.json         [{id, at, note, size, lines}], oldest first
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import limits
from .contract_parts import (
    PARTS_DIR, Part, find_part, has_parts, load_parts, parse_part, render_part,
    split_frontmatter, write_contract,
)
from .file_safety import atomic_write, atomic_write_json, safe_read_json

_REPO_ROOT = Path(__file__).resolve().parents[2]

MAX_BYTES = 512 * 1024

CONTRACT_KEY = "contract"
PART_PREFIX = "contract."
# The names the contract had before the product was renamed — read as aliases.
OLD_CONTRACT_KEY = "merkhet"
OLD_PART_PREFIX = "merkhet."


def canonical_key(key: str) -> str:
    """The key a request means: the old spelling of the contract and its parts
    is answered as the new one."""
    if key == OLD_CONTRACT_KEY:
        return CONTRACT_KEY
    if key.startswith(OLD_PART_PREFIX):
        return PART_PREFIX + key[len(OLD_PART_PREFIX):]
    return key


def old_key(key: str) -> str:
    """The spelling a key had before the rename (the folder an older data root holds)."""
    if key == CONTRACT_KEY:
        return OLD_CONTRACT_KEY
    if key.startswith(PART_PREFIX):
        return OLD_PART_PREFIX + key[len(PART_PREFIX):]
    return key


@dataclass(frozen=True)
class PromptFile:
    key: str
    label: str
    about: str
    relpath: str  # relative to the prompt root (the repo)
    part: bool = False


PROMPT_FILES: tuple[PromptFile, ...] = (
    PromptFile(
        CONTRACT_KEY, "SLIGHTLY-PARALLEL.md — the agent contract",
        "Every agent reads this at session start: the commands, when to post "
        "which entry, and what each entry holds. "
        "Composed from the parts under prompts/contract/.",
        "SLIGHTLY-PARALLEL.md",
    ),
    PromptFile(
        "agents-block", "AGENTS.md block — what Setup writes into a project",
        "The Slightly Parallel section in each project's AGENTS.md. "
        "$project_code, $contract, $api_url, $data_root, $project_dir and "
        "$notes_line are filled in at integration time.",
        "templates/agents-block.md",
    ),
)

_BY_KEY = {p.key: p for p in PROMPT_FILES}
_ID_RE = re.compile(r"^[0-9]{6}-[0-9]{6}(-[0-9]+)?$")


class PromptStore:
    """Reads and writes one prompt file with its original and versions."""

    def __init__(self, data_root: Path, prompt_root: Path | None = None) -> None:
        self.data_root = Path(data_root)
        self.prompt_root = Path(prompt_root) if prompt_root else _REPO_ROOT

    # -- lookup ----------------------------------------------------------

    def spec(self, key: str) -> PromptFile | None:
        key = canonical_key(key)
        if key in _BY_KEY:
            return _BY_KEY[key]
        if key.startswith(PART_PREFIX):
            part = find_part(self.prompt_root, key[len(PART_PREFIX):])
            if part is not None:
                return PromptFile(
                    key, part.title,
                    f"One block of the contract ({PARTS_DIR}/{part.filename}).",
                    f"{PARTS_DIR}/{part.filename}", part=True,
                )
        return None

    def composed(self, spec: PromptFile) -> bool:
        """SLIGHTLY-PARALLEL.md is composed (read-only here) when the parts folder exists."""
        return spec.key == CONTRACT_KEY and has_parts(self.prompt_root)

    def path(self, spec: PromptFile) -> Path:
        return self.prompt_root / spec.relpath

    def _dir(self, spec: PromptFile) -> Path:
        """Where the original and the versions live. A folder named after
        the key's old spelling, written before the rename, is the one in use
        for as long as it exists: the operator's files stay where they are
        and their history stays whole. A new data root gets the new name."""
        new = self.data_root / "prompts" / spec.key
        old = self.data_root / "prompts" / old_key(spec.key)
        return old if old != new and old.is_dir() and not new.is_dir() else new

    def _history_path(self, spec: PromptFile) -> Path:
        return self._dir(spec) / "history.json"

    def _original_path(self, spec: PromptFile) -> Path:
        return self._dir(spec) / "original.md"

    def _version_path(self, spec: PromptFile, vid: str) -> Path:
        return self._dir(spec) / "versions" / f"{vid}.md"

    # -- reads -----------------------------------------------------------

    def _read_file(self, spec: PromptFile) -> str:
        try:
            return self.path(spec).read_text(encoding="utf-8")
        except OSError:
            return ""

    def read(self, spec: PromptFile) -> str:
        """The editable text: a part's body; a plain file's whole content."""
        text = self._read_file(spec)
        return split_frontmatter(text)[1] if spec.part else text

    def _part(self, spec: PromptFile) -> Part:
        return parse_part(self._read_file(spec), Path(spec.relpath).name)

    def history(self, spec: PromptFile) -> list[dict]:
        p = self._history_path(spec)
        if not p.exists():
            return []
        try:
            data = safe_read_json(p)
        except (OSError, ValueError):
            return []
        return [h for h in data if isinstance(h, dict) and h.get("id")] if isinstance(data, list) else []

    def _kept_text(self, p: Path, spec: PromptFile) -> str | None:
        try:
            text = p.read_text(encoding="utf-8") if p.exists() else None
        except OSError:
            return None
        if text is None:
            return None
        return split_frontmatter(text)[1] if spec.part else text

    def original(self, spec: PromptFile) -> str | None:
        return self._kept_text(self._original_path(spec), spec)

    def version_text(self, spec: PromptFile, vid: str) -> str | None:
        if vid == "original":
            return self.original(spec)
        if not _ID_RE.match(vid):
            return None
        return self._kept_text(self._version_path(spec, vid), spec)

    def summary(self, spec: PromptFile) -> dict:
        text = self.read(spec)
        orig = self.original(spec)
        p = self.path(spec)
        try:
            modified = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            modified = None
        out = {
            "key": spec.key,
            "label": spec.label,
            "about": spec.about,
            "path": str(p),
            "exists": p.exists(),
            "size": len(text.encode("utf-8")),
            "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            "modified": modified,
            "has_original": orig is not None,
            "is_original": orig is None or orig == text,
            "versions_n": len(self.history(spec)),
        }
        if spec.key == CONTRACT_KEY:
            out["composed"] = self.composed(spec)
            out["parts_n"] = len(load_parts(self.prompt_root)) if out["composed"] else 0
        if spec.part:
            out.update(self._part(spec).meta())
        return out

    def detail(self, spec: PromptFile) -> dict:
        out = self.summary(spec)
        out["text"] = self.read(spec)
        out["versions"] = list(reversed(self.history(spec)))  # newest first
        if spec.key == CONTRACT_KEY and out.get("composed"):
            out["parts"] = [self.part_detail(p) for p in load_parts(self.prompt_root)]
        return out

    def part_detail(self, part: Part) -> dict:
        spec = self.spec(PART_PREFIX + part.key)
        assert spec is not None
        out = self.summary(spec)
        out["text"] = part.body
        out["original"] = self.original(spec)
        out["versions"] = list(reversed(self.history(spec)))
        return out

    # -- writes ----------------------------------------------------------

    def _snapshot(self, spec: PromptFile, current: str, note: str) -> str:
        """Keep ``current`` (the whole file) as a version (and as the original, once)."""
        if not self._original_path(spec).exists():
            atomic_write(self._original_path(spec), current)
        hist = self.history(spec)
        base = datetime.now().strftime("%y%m%d-%H%M%S")
        vid, n = base, 1
        taken = {h["id"] for h in hist}
        while vid in taken:
            n += 1
            vid = f"{base}-{n}"
        atomic_write(self._version_path(spec, vid), current)
        body = split_frontmatter(current)[1] if spec.part else current
        hist.append({
            "id": vid,
            "at": datetime.now().isoformat(timespec="seconds"),
            "note": note[:limits.MAX_TITLE],
            "size": len(body.encode("utf-8")),
            "lines": body.count("\n"),
        })
        atomic_write_json(self._history_path(spec), hist)
        return vid

    def _after_part_write(self) -> None:
        write_contract(self.prompt_root)

    def save(self, spec: PromptFile, text: str, note: str = "") -> dict:
        """Write ``text`` as the live file (a part: as its body); the replaced
        content becomes a version. A composed SLIGHTLY-PARALLEL.md is not written."""
        if self.composed(spec):
            raise PermissionError("composed")
        current_file = self._read_file(spec)
        if spec.part:
            part = parse_part(current_file, Path(spec.relpath).name)
            new_body = text.rstrip("\n") + "\n" if text.strip() else ""
            if new_body == part.body:
                return {"action": "unchanged", "version": None}
            part.body = new_body
            new_file = render_part(part)
        else:
            if text == current_file:
                return {"action": "unchanged", "version": None}
            new_file = text
        vid = self._snapshot(spec, current_file, note or "edit")
        atomic_write(self.path(spec), new_file)
        if spec.part:
            self._after_part_write()
        return {"action": "saved", "version": vid}

    def set_enabled(self, spec: PromptFile, enabled: bool) -> dict:
        """Switch a part on or off; SLIGHTLY-PARALLEL.md loses or regains the block."""
        if not spec.part:
            raise PermissionError("not a part")
        current_file = self._read_file(spec)
        part = parse_part(current_file, Path(spec.relpath).name)
        if part.enabled == enabled:
            return {"action": "unchanged", "version": None}
        vid = self._snapshot(spec, current_file, "switched on" if enabled else "switched off")
        part.enabled = enabled
        atomic_write(self.path(spec), render_part(part))
        self._after_part_write()
        return {"action": "saved", "version": vid}

    def restore(self, spec: PromptFile, vid: str) -> dict:
        if self.composed(spec):
            raise PermissionError("composed")
        if vid == "original":
            kept_path = self._original_path(spec)
        elif _ID_RE.match(vid):
            kept_path = self._version_path(spec, vid)
        else:
            raise KeyError(vid)
        try:
            target = kept_path.read_text(encoding="utf-8") if kept_path.exists() else None
        except OSError:
            target = None
        if target is None:
            raise KeyError(vid)
        current_file = self._read_file(spec)
        if target == current_file:
            return {"action": "unchanged", "version": None}
        kept = self._snapshot(spec, current_file, f"before restore of {vid}")
        atomic_write(self.path(spec), target)
        if spec.part:
            self._after_part_write()
        return {"action": "restored", "version": kept}
