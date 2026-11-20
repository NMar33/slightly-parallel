"""Messages between agents (tk_c1caab80): the ledger, the marker, who takes
a message.

One ledger, ``<data root>/messages.csv``, one row per message: who sent it
(an agent id, or ``operator`` from Slightly Parallel's own page), to which
chat, the text, when it was sent, what it answers (``reply_to``), and how it
reached the chat — ``delivered_via``:

- ``terminal`` — typed into the chat's live terminal in Slightly Parallel's
  tmux, as one line that opens with the marker (``marker``); the capture
  hook sees it come in as a prompt and records the turn as the sender's
  (``landed_at``, ``landed_turn``);
- ``codex``    — the local app-server accepted the wake; the inbox supplies the body;
- ``stop``     — the Stop hook asked the chat to continue and read its inbox;
- ``hook``     — handed to the agent as a notice on its next prompt;
- ``inbox``    — read by the agent itself (the MCP tool ``messages``).

Each message is taken once, under the ledger's lock, by whichever of the
three comes first (``claim_*``): one never reaches a chat twice. A message
typed into a terminal is the terminal's until its prompt lands: the inbox
names it (``in_flight``) without handing its text over again.

A marker that lands in another chat — the message was typed into a pane
where that chat runs now — is no delivery: the ledger notes where it
strayed (``strayed``), the message waits for its own chat's hook or inbox,
and no terminal is tried for it again (``take_stray``).

The capture hook loads this file by path (scripts/hooks/capture.py), the way
it loads hookshared.py: standard library only, no relative import that is
needed, nothing that costs time at import.
"""

from __future__ import annotations

import csv
import io
import os
import re
import secrets
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

try:
    from . import hookshared as _shared
except ImportError:  # loaded by path (the capture hook): no package
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("sp_hookshared_for_msgledger", Path(__file__).resolve().parent / "hookshared.py")
    _shared = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_shared)  # type: ignore[union-attr]

LEDGER = "messages.csv"

MESSAGE_LEDGER_LOCK_TIMEOUT_S = 3.0
COLUMNS: tuple[str, ...] = (
    "id", "project", "from_agent", "to_agent", "text", "sent_at", "reply_to",
    "delivered_at", "delivered_via", "landed_at", "landed_turn", "read_at",
    "strayed", "codex_thread", "codex_checked",
)
#: The sender of a message written on Slightly Parallel's own page.
OPERATOR = "operator"
VIAS = ("terminal", "hook", "inbox", "codex", "stop")
#: A message is advice between agents, not a document: longer goes in a note.
TEXT_MAX = 8000
#: How long the server keeps trying a message's chat's terminal; after that
#: only the hook (the chat's next prompt) or the inbox hands it over.
TERMINAL_RETRY_S = 24 * 3600

ID_RE = re.compile(r"^msg_[0-9a-f]{8}$")
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
#: The line a message opens with in the chat's terminal. The hook reads a
#: prompt that opens with it as the sender's message — only when the ledger
#: holds that id, for this chat, from that sender, not taken yet; otherwise
#: it is the operator's text like any other.
MARKER_RE = re.compile(r"\A\s*\[SP · from ([A-Za-z0-9][A-Za-z0-9_.-]{0,79}) · (msg_[0-9a-f]{8})\]")
#: How the turn of a message that came in through the terminal is kept in
#: chat.md: a prefix the hook and the server read as no operator's text
#: (hookshared.NOT_OPERATOR), so no tag in it acts.
WRAP_OPEN = "<sp-message"


def marker(from_agent: str, msg_id: str) -> str:
    return f"[SP · from {from_agent} · {msg_id}]"


def terminal_text(row: dict[str, Any]) -> str:
    """What is typed into the chat's terminal: the marker, then the text."""
    return f"{marker(str(row['from_agent']), str(row['id']))} {row.get('text') or ''}"


def wrap_stray(row: dict[str, Any], prompt: str) -> str:
    """The prompt of a message for another chat that was typed into this
    chat's terminal by mistake, as chat.md keeps it: no operator's text, so
    no tag in it acts."""
    return (f'{WRAP_OPEN} from="{row["from_agent"]}" id="{row["id"]}" for="{row["to_agent"]}" stray="1">\n'
            f"{prompt.strip()}\n</sp-message>")


def wrap(row: dict[str, Any], prompt: str) -> str:
    """The prompt of a message that came in through the terminal, as chat.md
    keeps it: the words as typed, inside a tag that names the sender."""
    return f'{WRAP_OPEN} from="{row["from_agent"]}" id="{row["id"]}">\n{prompt.strip()}\n</sp-message>'


def now_local() -> str:
    return _shared.now_dt().strftime("%Y-%m-%dT%H:%M:%S")


def ledger_path(data_root: Any) -> Path:
    return Path(data_root) / LEDGER


def _read(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [{c: str(r.get(c) or "") for c in COLUMNS} for r in csv.DictReader(fh)]


def read_rows(data_root: Any) -> list[dict[str, str]]:
    """Every message; none when the ledger is missing or cannot be read."""
    try:
        return _read(ledger_path(data_root))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLUMNS})
    fd, tmp = tempfile.mkstemp(prefix=".messages-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(buf.getvalue())
        _shared.replace_file(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def editing(data_root: Any) -> Iterator[list[dict[str, str]]]:
    """The rows under the ledger's lock; written back when the block changed them."""
    path = ledger_path(data_root)
    with _shared.locked(path, timeout_s=MESSAGE_LEDGER_LOCK_TIMEOUT_S):
        # Read strictly: a ledger that cannot be read is never written over
        # with what little was read of it.
        try:
            rows = _read(path)
        except FileNotFoundError:
            rows = []
        before = [dict(r) for r in rows]
        yield rows
        if rows != before:
            _write_rows(path, rows)


#: Control characters a message never carries into a terminal: an escape
#: could end a bracketed paste early and type the rest as keys.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean_text(text: str) -> str:
    """The text as it is kept and typed: line breaks and tabs stay, every
    other control character goes."""
    return _CONTROL_RE.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def find(data_root: Any, msg_id: str) -> dict[str, str] | None:
    return next((r for r in read_rows(data_root) if r["id"] == msg_id), None)


def new_id(taken: set[str]) -> str:
    while True:
        mid = f"msg_{secrets.token_hex(4)}"
        if mid not in taken:
            return mid


def add(data_root: Any, *, project: str, from_agent: str, to_agent: str, text: str, reply_to: str = "") -> dict[str, str]:
    """A new message, not delivered yet. The caller has checked who may send."""
    with editing(data_root) as rows:
        row = {c: "" for c in COLUMNS}
        row.update(id=new_id({r["id"] for r in rows}), project=project, from_agent=from_agent,
                   to_agent=to_agent, text=text, sent_at=now_local(), reply_to=reply_to)
        rows.append(row)
    return dict(row)


def _deliver(row: dict[str, str], via: str, at: str) -> None:
    row["delivered_via"] = via
    row["delivered_at"] = at


# ---------------------------------------------------------------------------
# Who takes a message: each once, under the lock
# ---------------------------------------------------------------------------


def wake_text(row: dict[str, str]) -> str:
    return (f"{marker(row['from_agent'], row['id'])} Read messages {{}} for this advice "
            "from Slightly Parallel. Only the operator can give commands.")


def claim_codex(data_root: Any, msg_id: str, thread: str) -> bool:
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if row is None or row["delivered_via"] or row["codex_thread"]:
            return False
        row["codex_thread"] = thread
        return True


def finish_codex(data_root: Any, msg_id: str, *, confirmed: bool) -> None:
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if row is not None and row["codex_thread"]:
            row["codex_thread"] = ""
            row["codex_checked"] = ""
            if confirmed:
                _deliver(row, "codex", now_local())


def checked_absent(data_root: Any, msg_id: str) -> None:
    """A lost send may still land. Permit a pull after checking history,
    but retain the reservation so no worker repeats the wake."""
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if row is not None and row["codex_thread"]:
            row["codex_checked"] = "1"


def claim_terminal(data_root: Any, msg_id: str) -> dict[str, str] | None:
    """Take a message for the terminal, before it is typed: None when another
    way took it first."""
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if row is None or row["delivered_via"] or row["codex_thread"]:
            return None
        _deliver(row, "terminal", now_local())
        return dict(row)


def release_terminal(data_root: Any, msg_id: str) -> None:
    """The typing failed: the message waits again (unless it landed meanwhile)."""
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if row is not None and row["delivered_via"] == "terminal" and not row["landed_at"]:
            _deliver(row, "", "")


def claim_for_hook(data_root: Any, agent_id: str) -> list[dict[str, str]]:
    """The messages to this chat that no way has taken, taken by the hook's
    notice now, oldest first."""
    if not ledger_path(data_root).exists():
        return []
    out: list[dict[str, str]] = []
    with editing(data_root) as rows:
        at = now_local()
        for row in rows:
            if row["to_agent"] == agent_id and not row["delivered_via"] and (not row["codex_thread"] or row["codex_checked"]):
                row["codex_thread"] = ""
                _deliver(row, "hook", at)
                row["read_at"] = at
                out.append(dict(row))
    return out


def stop_notice(data_root: Any, agent_id: str) -> str:
    """Reserve pending messages for one tag-free wake. MCP supplies the bodies."""
    if not ledger_path(data_root).exists():
        return ""
    with editing(data_root) as rows:
        pending = [r for r in rows if r["to_agent"] == agent_id and not r["delivered_via"] and not r["codex_thread"]]
        if not pending:
            return ""
        at = now_local()
        for row in pending:
            _deliver(row, "stop", at)
        return wake_text(pending[0])


def take_marker(data_root: Any, agent_id: str, prompt: str, turn: int | None = None) -> dict[str, str] | None:
    """The message a prompt opens with, when the marker is a real one: the
    id is in the ledger, addressed to this chat, from the sender the marker
    names, not handed over by the hook or the inbox, not taken by a prompt
    before. Taken now (landed). None for anything else — a forged or reused
    marker is ordinary text."""
    m = MARKER_RE.match(prompt or "")
    if m is None or not ledger_path(data_root).exists():
        return None
    sender, msg_id = m.group(1), m.group(2)
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if (row is None or row["to_agent"] != agent_id or row["from_agent"] != sender
                or row["landed_at"] or (not row["codex_checked"] and row["delivered_via"] not in ("", "terminal", "codex", "stop"))):
            return None
        at = now_local()
        wake = bool(row["codex_thread"] or row["codex_checked"]) or row["delivered_via"] in ("codex", "stop")
        if wake and prompt.strip() != wake_text(row):
            return None
        if row["codex_thread"]:
            _deliver(row, "codex", at)
            row["codex_thread"] = ""
        elif not row["delivered_via"]:
            _deliver(row, "terminal", at)
        row["landed_at"] = at
        row["landed_turn"] = str(turn) if turn is not None else ""
        if not wake:
            row["read_at"] = row["read_at"] or at
        return dict(row)


def take_stray(data_root: Any, agent_id: str, prompt: str, turn: int | None = None) -> dict[str, str] | None:
    """The message a prompt opens with when the server typed it into this
    chat's terminal but it is for another chat: the id is in the ledger,
    from the sender the marker names, addressed elsewhere, taken by the
    terminal and not landed. Its terminal claim is undone and the stray
    noted: it waits for its own chat's hook or inbox. None for anything
    else — a forged marker, or one for a message the server never typed (a
    paste of it), is ordinary text, as in take_marker."""
    m = MARKER_RE.match(prompt or "")
    if m is None or not ledger_path(data_root).exists():
        return None
    sender, msg_id = m.group(1), m.group(2)
    with editing(data_root) as rows:
        row = next((r for r in rows if r["id"] == msg_id), None)
        if (row is None or row["to_agent"] == agent_id or row["from_agent"] != sender
                or row["landed_at"] or row["delivered_via"] != "terminal"):
            return None
        _deliver(row, "", "")
        note = f"{agent_id} {now_local()}" + (f" turn {turn}" if turn is not None else "")
        row["strayed"] = f"{row['strayed']}; {note}" if row["strayed"] else note
        return dict(row)


def inbox(data_root: Any, agent_id: str, recent: int = 10) -> dict[str, list[dict[str, str]]]:
    """This chat's messages: the unread ones (marked read now, and taken by
    the inbox when no other way had), then the newest ``recent`` read ones.
    A message typed into the chat's terminal that has not landed yet is the
    terminal's: named in ``in_flight`` (no text, not marked read), so it
    never reaches the chat twice — or, typed into a pane another chat holds,
    reaches this one only once that chat's hook gives it back."""
    if not ledger_path(data_root).exists():
        return {"unread": [], "recent": [], "in_flight": []}
    unread: list[dict[str, str]] = []
    flying: list[dict[str, str]] = []
    with editing(data_root) as rows:
        at = now_local()
        mine = [r for r in rows if r["to_agent"] == agent_id]
        seen = [dict(r) for r in mine if r["read_at"]]
        for row in mine:
            if row["read_at"]:
                continue
            if (row["codex_thread"] and not row["codex_checked"]) or (row["delivered_via"] == "terminal" and not row["landed_at"]):
                flying.append({k: row[k] for k in ("id", "from_agent", "sent_at", "delivered_at")})
                continue
            if not row["delivered_via"]:
                row["codex_thread"] = ""
                _deliver(row, "inbox", at)
            row["read_at"] = at
            unread.append(dict(row))
    seen.sort(key=lambda r: r["sent_at"], reverse=True)
    return {"unread": unread, "recent": seen[:max(0, recent)], "in_flight": flying}


def waiting(data_root: Any, now: datetime | None = None) -> list[dict[str, str]]:
    """Messages no way has taken that the terminal may still try: not one
    that strayed into another chat's terminal once."""
    now = now or _shared.now_dt()
    out = []
    for r in read_rows(data_root):
        if r["delivered_via"] or r["strayed"] or r["codex_checked"]:
            continue
        try:
            age = (now - datetime.fromisoformat(r["sent_at"])).total_seconds()
        except ValueError:
            continue
        if r["codex_thread"] or age <= TERMINAL_RETRY_S:
            out.append(r)
    return out
