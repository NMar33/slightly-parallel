"""The one-chat move: an agent's chat folder from its origin to one of its
member projects (tk_d1d25a4d step 2, note nt_9de63b9e §5).

The operator's explicit act, one chat per call, on the way to deleting a
project that holds the chat of an agent that is a member elsewhere. Not a
mass move: transcripts stay where they started otherwise.

1. Checks, each a one-line refusal that writes nothing: the target is one of
   the agent's member projects other than its origin; the agent is not
   running (no turn open in meta.json, no change in the last minute); no hook
   holds any of its locks (a non-blocking try); no folder for the agent at
   the target.
2. The agent's locks (meta, turns, usage, carried) are held for the whole
   move, inside the membership ledger's lock.
3. The folder is copied to ``projects/<to>/chats/.incoming-<agent>``,
4. the copy verified (bytes and sha256 of every file; the turns: ``## Turn``
   headers, turns.jsonl lines, meta ``message_count``),
5. the original checked again: changed since the copy, the copy goes and
   the move is refused,
6. ``project`` set to the target in the copy's meta.json (atomic write),
7. the copy renamed into place,
8. the original moved to ``.trash/move-<agent>-<stamp>/`` (never deleted),
9. the ``moved`` row written to the ledger.

A failure before 7 leaves the original untouched. One between 7 and 8 leaves
two folders: the next call finds the target and refuses; a project delete
then goes ahead, the chat being filed at the target.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any

from . import chatstore
from . import membership_fold as mf
from . import memberships
from .file_safety import FileSafetyError, acquire_flock, atomic_write_json

#: The agent counts as running when a file of its chat changed this recently.
QUIET_S = 60
#: The files whose locks a hook takes (capture.py, hookshared.append_locked).
LOCKED_FILES: tuple[str, ...] = ("meta.json", "turns.jsonl", "usage.jsonl", "carried.jsonl")
TRASH_DIR = ".trash"
WROTE_DURING = "the agent wrote during the move; stop it and try again"
EFFECTS = (
    "all of the chat's past minutes and tokens now count to {to} (its home is its origin until step 8)",
    "its session ids change: their seed is project|agent|start",
    "commit ownership for its turns moves to {to}'s chats",
    "pins and marks point at agent#turn, which does not change",
    # The hook builds its folder from the folder the agent runs in
    # (capture.py TurnCapture) and writes without the lock after 2 s
    # (hookshared.locked): an agent still running there writes a new folder.
    "close the agent first; if it is started again from the old folder, it starts a new chat folder there",
)


class MoveRefused(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _files(folder: Path) -> list[Path]:
    """The chat's files, lock sidecars aside (taking a lock makes one)."""
    return sorted(p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(".lock"))


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(folder: Path) -> dict[str, tuple[int, int, str]]:
    """Every file: (size, mtime_ns, sha256), by its path inside the folder."""
    out = {}
    for p in _files(folder):
        st = p.stat()
        out[p.relative_to(folder).as_posix()] = (st.st_size, st.st_mtime_ns, _sha(p))
    return out


def turns_of(folder: Path) -> dict[str, int]:
    """The turns three ways: chat.md's headers, turns.jsonl's lines, meta's count."""
    def count(name: str, test) -> int:
        try:
            with open(folder / name, encoding="utf-8", errors="replace") as fh:
                return sum(1 for line in fh if test(line))
        except FileNotFoundError:
            return 0
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        n = int(meta.get("message_count") or 0) if isinstance(meta, dict) else 0
    except (OSError, ValueError):
        n = 0
    return {
        "chat_md_turns": count("chat.md", lambda s: s.startswith("## Turn")),
        "turns_jsonl_lines": count("turns.jsonl", lambda s: bool(s.strip())),
        "message_count": n,
    }


def _check(root: Path, agent: str, to: str) -> tuple[str, Path, dict[str, Any]]:
    """The checks of step 1 that need no lock of the chat: the agent's one
    origin folder, the target a member project, nothing at the target."""
    chats = memberships.chats_on_disk(root, agent)
    if not chats:
        raise MoveRefused(404, f"agent not found: {agent}")
    if any(meta.get("helper") is True for _o, _f, meta in chats):
        raise MoveRefused(409, f"{agent} is a helper chat: it goes where its parent goes")
    if len(chats) > 1:
        where = ", ".join(sorted(o for o, _f, _m in chats))
        if to in {o for o, _f, _m in chats}:
            raise MoveRefused(409, f"{agent} has a folder in {to} already")
        raise MoveRefused(409, f"{agent} has chat folders in {where}: move one chat folder at a time")
    origin, folder, meta = chats[0]
    if to == origin:
        raise MoveRefused(409, f"{to} is the origin of {agent}: its chat is there already")
    rows, cut = memberships.read_ledger(root)
    fold = mf.fold([r for r in rows if r.get("agent_id") == agent], memberships.existing_codes(root),
                   {agent: (origin,)}, cut)
    if to not in fold.joined(agent):
        raise MoveRefused(409, f"{agent} is not a member of {to}: a chat moves only to one of its projects")
    if chatstore.folder(root, to, agent).exists() or chatstore.folder(root, to, agent).is_symlink():
        raise MoveRefused(409, f"{to} has a folder for {agent} already")
    if meta.get("pending_turn") is not None:
        raise MoveRefused(409, f"{agent} has a turn open: stop it and try again")
    newest = max((p.stat().st_mtime for p in _files(folder)), default=0.0)
    if time.time() - newest < QUIET_S:
        raise MoveRefused(409, f"{agent} wrote in the last {QUIET_S} s: stop it and try again")
    return origin, folder, meta


def _trash(root: Path, folder: Path, agent: str) -> Path:
    """Step 8: the original into the trash, never deleted."""
    dest = root / TRASH_DIR / f"move-{agent}-{datetime.now():%Y%m%d-%H%M%S}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(dest))
    return dest


def move(root: str | Path, agent: str, to: str) -> dict[str, Any]:
    """Move the agent's chat folder to ``to``; raise ``MoveRefused`` with a
    one-line reason when it may not, leaving everything as it was."""
    root = Path(root)
    with memberships.locked(root), ExitStack() as held:
        origin, folder, _meta = _check(root, agent, to)
        for name in LOCKED_FILES:
            try:
                held.enter_context(acquire_flock(folder / f"{name}.lock", mode="a", timeout_s=0))
            except FileSafetyError:
                raise MoveRefused(409, f"a hook holds the {name} lock of {agent}: the agent is running") from None
        before = fingerprint(folder)
        copy = chatstore.incoming(root, to, agent)
        if copy.exists():
            shutil.rmtree(copy)  # a move that died before its rename
        made = [p for p in (copy.parent.parent, copy.parent) if not p.exists()]
        copy.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(folder, copy, symlinks=True)
            # Step 5 before step 4: a chat that changed under the copy is the
            # agent writing, not a bad copy.
            if fingerprint(folder) != before:
                raise MoveRefused(409, WROTE_DURING)
            want = {k: (v[0], v[2]) for k, v in before.items()}
            if fingerprint_bytes(copy) != want or turns_of(copy) != turns_of(folder):
                raise MoveRefused(500, "the copy does not match the chat; nothing was moved")
            meta_path = copy / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["project"] = to
            atomic_write_json(meta_path, meta)
            if fingerprint(folder) != before:
                raise MoveRefused(409, WROTE_DURING)
        except BaseException:
            shutil.rmtree(copy, ignore_errors=True)
            for p in reversed(made):  # a refusal leaves no folder behind either
                try:
                    p.rmdir()
                except OSError:
                    pass
            raise
        turns = turns_of(copy)
        target = chatstore.folder(root, to, agent)
        copy.rename(target)                                   # step 7
        trashed = _trash(root, folder, agent)                 # step 8
        row = memberships.write(root, agent, "moved", to, f"{mf.MOVED_FROM}{origin}", held=True)  # step 9
    return {
        "agent_id": agent, "from": origin, "to": to, "folder": str(target), "trash": str(trashed),
        "turns": turns, "files": len(before), "row": row,
        "effects": [e.format(to=to) for e in EFFECTS],
    }


def fingerprint_bytes(folder: Path) -> dict[str, tuple[int, str]]:
    """Every file: (size, sha256) — what a copy must match (times differ)."""
    return {k: (v[0], v[2]) for k, v in fingerprint(folder).items()}
