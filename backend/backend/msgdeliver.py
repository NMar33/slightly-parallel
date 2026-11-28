"""Typing a message into the chat's terminal (tk_c1caab80).

A message waits in the ledger (msgledger.py) until a way takes it. The
quickest is the chat's own terminal: the capture hook fires only when a
prompt comes in, so an agent left idle would never hear of it otherwise.
The server types a short notice there as one prompt that opens with the
marker, and presses Enter — only when all of this holds:

- the chat has a live terminal in Slightly Parallel's tmux: the capture hook
  recorded the terminal it was started in (chat meta ``terminal``,
  termlib.agent_links), and that tmux session is still there;
- the program in front is not a shell (the agent has not quit), and the
  pane is not in copy mode;
- the chat is the one running in that pane now (``occupant_why``): the
  terminal a chat's meta names is only where it was last seen starting, and
  a terminal is reused — a newer chat started there, or a tool that serves
  every session from one shared process (Codex's app-server daemon) handed
  its own terminal to chats that run elsewhere. The hook's breadcrumb (the
  processes above it at the chat's last prompt) must hold the pane's shell,
  the program under it must be the same process still, and no newer chat
  may have prompted from that program since;
- the tool is one whose input line can be read: Claude Code (``❯`` on a
  row under a rule, a rule straight under it) or Codex (``›`` on the last
  such row, nothing typed under it);
- that input line is empty. A placeholder the tool draws dim (Codex's "Ask
  Codex to do anything") counts as empty; anything else is the operator
  typing, and the message waits. A busy agent is fine: both tools queue what
  is typed while they work.

When in doubt, nothing is typed. A message that waits is tried again on the
server's next round (``retry_waiting``) and is handed over by the hook on the
chat's next prompt, whichever comes first (each takes it once, under the
ledger's lock).

The Stop hook asks the same check before it blocks a Claude Code Stop
(``stop_leaves``, ``GET /api/messages/terminal``): where this server types
into the chat's terminal, now or once the operator's line is empty, the
message is left for that typed prompt, and Claude Code shows no "Stop hook
reported a problem" for it (tk_40450bfa).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import app_settings, chatstore, codexdelivery, msgledger, pingstate, termlib
from .file_safety import FileSafetyError, acquire_flock, lock_path
from .hookshared import epoch_of, process_started

log = logging.getLogger("sp.messages")

#: Tools whose input line this module can read.
TOOLS = ("claude-code", "codex")
_RULE = "─"
_CLAUDE_PROMPT = "❯"
_CODEX_PROMPT = "›"
#: Pause between the paste and Enter: a tool that reads a paste in pieces
#: (Codex's paste burst) must have all of it before Enter submits.
ENTER_AFTER_S = 0.3

_SGR_RE = re.compile(r"\x1b\[([0-9;:]*)m")
_OTHER_ESC_RE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][A-Za-z0-9]|.)")


def _cells(line: str) -> list[tuple[str, bool]]:
    """A captured row (with tmux's escapes, ``capture-pane -e``) as its
    visible characters, each with whether it was drawn dim (SGR 2)."""
    out: list[tuple[str, bool]] = []
    dim = False
    i = 0
    while i < len(line):
        if line[i] == "\x1b":
            m = _SGR_RE.match(line, i)
            if m:
                params = [p for p in re.split(r"[;:]", m.group(1))] or ["0"]
                j = 0
                while j < len(params):
                    p = params[j]
                    if p in ("", "0"):
                        dim = False
                    elif p == "2":
                        dim = True
                    elif p == "22":
                        dim = False
                    elif p in ("38", "48", "58"):
                        # An extended colour: its own arguments follow.
                        kind = params[j + 1] if j + 1 < len(params) else ""
                        j += 2 if kind == "5" else 4 if kind == "2" else 1
                    j += 1
                i = m.end()
                continue
            m = _OTHER_ESC_RE.match(line, i)
            i = m.end() if m else i + 1
            continue
        out.append((line[i], dim))
        i += 1
    return out


def _text(cells: list[tuple[str, bool]]) -> str:
    return "".join(c for c, _ in cells)


def _blank(ch: str) -> bool:
    return ch.isspace() or ch == " "


def _typed(cells: list[tuple[str, bool]]) -> bool:
    """Is anything typed in these cells? Spaces are not, nor a dim placeholder."""
    return any(not _blank(c) and not dim for c, dim in cells)


def _is_rule(cells: list[tuple[str, bool]]) -> bool:
    """A rule of the input box. Claude Code writes the chat's name into its
    top rule (``──── name ─``): a row that opens with the rule is one."""
    return _text(cells).strip().startswith(_RULE * 3)


def _after_prompt(cells: list[tuple[str, bool]], glyph: str) -> list[tuple[str, bool]] | None:
    """The cells after the prompt glyph when the row opens with it (spaces
    before it allowed), else None."""
    k = 0
    while k < len(cells) and _blank(cells[k][0]):
        k += 1
    if k >= len(cells) or cells[k][0] != glyph:
        return None
    return cells[k + 1:]


def _input_state(screen: str, tool: str, *, expected: str = "", cursor_row: int | None = None) -> bool | None:
    """True for an empty composer, False for a draft, None when unreadable."""
    rows = [_cells(r) for r in screen.split("\n")]
    while rows and not _text(rows[-1]).strip():
        rows.pop()
    glyph = _CLAUDE_PROMPT if tool == "claude-code" else _CODEX_PROMPT if tool == "codex" else ""
    if not glyph:
        return None
    at = next((i for i in range(len(rows) - 1, -1, -1) if _after_prompt(rows[i], glyph) is not None), None)
    if at is None or (cursor_row is not None and at != cursor_row):
        return None
    rest = _after_prompt(rows[at], glyph) or []
    matches = _text(rest).strip() == expected if expected else not _typed(rest)
    if tool == "claude-code":
        if at == 0 or not _is_rule(rows[at - 1]):
            return None
        bottom = next((i for i in range(at + 1, len(rows)) if _is_rule(rows[i])), None)
        if bottom is None:
            return None
        return bottom == at + 1 and matches
    # Codex: the composer is the last "›" row; a row of input under it would
    # be the operator's second line.
    return matches and (at + 1 >= len(rows) or not _typed(rows[at + 1]))


def input_empty(screen: str, tool: str) -> bool:
    """An input line is safe to type into only when known empty."""
    return _input_state(screen, tool) is True


# ---------------------------------------------------------------------------
# The chat's terminal
# ---------------------------------------------------------------------------


def chat_meta(data_root: Path, agent_id: str) -> dict[str, Any] | None:
    if not msgledger.AGENT_RE.match(agent_id or ""):
        return None
    for _project, folder in chatstore.folders_of(data_root, agent_id, has="meta.json"):
        try:
            got = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(got, dict):
            # Present, the meta's project stays as it is (even empty); absent, the folder's.
            got.setdefault("project", chatstore.project_of(folder, got))
            return got
    return None


def terminal_of(data_root: Path, agent_id: str) -> str:
    """The terminal the chat's hook last said it started in (its id), ''
    when none. Only a claim: several chats can name one terminal (a reused
    one, a shared Codex daemon), and the page's link (termlib.agent_links)
    gives it to the one active last (a Codex chat only when occupant_why
    proves it there). Who is in the pane now is checked against the
    processes (occupant_why)."""
    meta = chat_meta(data_root, agent_id) or {}
    return str(meta.get("terminal") or "")


def _pane(data_root: Path, sid: str) -> dict[str, str] | None:
    got = termlib.tmux_read(data_root, "display-message", "-p", "-t", termlib.PREFIX + sid,
                            "#{pane_current_command}\t#{pane_in_mode}\t#{pane_dead}\t#{pane_pid}"
                            "\t#{cursor_y}\t#{pane_width}")
    if got.returncode != 0:
        return None
    parts = (got.stdout or "").rstrip("\n").split("\t")
    if len(parts) < 4:
        return None
    keys = ("fg", "in_mode", "dead", "pid", "cursor_y", "width")
    return dict(zip(keys, parts))


#: A process that started more than this after the breadcrumb was written
#: is not the one the breadcrumb names (process numbers come back).
_SAME_PROCESS_S = 2.0


def _crumbs(data_root: Path) -> list[dict[str, Any]]:
    """Every chat's own breadcrumb (``.sessions/<folder>/<session>.json``,
    written by the capture hook on each prompt): its agent, when, and the
    processes above the hook then, nearest first."""
    out: list[dict[str, Any]] = []
    for p in (Path(data_root) / ".sessions").glob("*/*.json"):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            pids = [int(x) for x in c.get("pids") or []]
            at = float(c.get("at") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if isinstance(c, dict) and pids and at:
            out.append({**c, "pids": pids, "at": at})
    return out


def occupant_why(data_root: Path, agent_id: str, pane_pid: int) -> str:
    """'' when the chat is the one running in the pane whose shell is
    ``pane_pid``; else why that cannot be said (nothing is typed then)."""
    crumbs = _crumbs(data_root)
    own = [c for c in crumbs if str(c.get("agent_id") or "") == agent_id]
    if not own:
        return "no breadcrumb says which processes the chat runs under"
    mine = max(own, key=lambda c: c["at"])
    pids, at = mine["pids"], mine["at"]
    if pane_pid not in pids:
        return "the chat does not run in this terminal (its hook's processes do not include the pane's shell)"
    i = pids.index(pane_pid)
    # The program under the pane's shell the chat ran in at its last prompt
    # (claude, codex): still that process, or the chat has left the pane.
    program = pids[i - 1] if i else pane_pid
    for pid in {pane_pid, program}:
        started = process_started(pid)
        if started is None or started > at + _SAME_PROCESS_S:
            return "the program the chat ran in has quit; the terminal may hold another chat now"
    # One program, two chats: a /clear or a resume inside it. The newer one
    # prompted from that same process, at the same depth (a helper the chat
    # started sits deeper and is no rival).
    depth = i - 1 if i else i
    for c in crumbs:
        if c is mine or str(c.get("agent_id") or "") == agent_id or c["at"] <= at:
            continue
        if len(c["pids"]) > depth and c["pids"][depth] == program:
            return f"a newer chat ({c.get('agent_id') or '?'}) has prompted in that program since"
    return ""


#: Why nothing is typed now that passes: the server's next round types it.
WHY_INPUT = "the input line is not empty"
WHY_UNREADABLE_INPUT = "the input line cannot be read"
WHY_COPY_MODE = "the terminal is in copy mode"
_PASSING = (WHY_INPUT, WHY_COPY_MODE)


def check(data_root: Path, agent_id: str, *, idle_only: bool = False, expected: str = "",
          columns: int = 0) -> tuple[str, str]:
    """(terminal id, why not) for typing into this chat's terminal now:
    why is '' when it may be typed into."""
    if termlib.tmux_path() is None:
        return "", "no tmux"
    meta = chat_meta(data_root, agent_id)
    if meta is None:
        return "", "no such chat"
    tool = str(meta.get("tool") or "")
    if idle_only and (meta.get("pending_turn") is not None or meta.get("helper")):
        return "", "the agent is working or is a helper"
    if idle_only and tool == "codex" and not meta.get("prompt_hook"):
        return "", WHY_UNREADABLE_INPUT
    if tool not in TOOLS:
        return "", f"the chat's tool ({tool or 'unknown'}) has no input line this server can read"
    sid = terminal_of(data_root, agent_id)
    row = termlib.get(data_root, sid) if sid else None
    if row is None or row.get("backend") != "tmux":
        return "", "the chat has no live terminal in Slightly Parallel"
    pane = _pane(data_root, sid)
    if pane is None or pane["dead"] == "1":
        return sid, "the terminal is gone"
    name = pane["fg"].split("/")[-1].lstrip("-")
    if not name or name in termlib.SHELLS:
        return sid, "a shell is in front: the agent is not running there"
    try:
        pane_pid = int(pane["pid"])
    except ValueError:
        return sid, "the pane's process cannot be read"
    why = occupant_why(data_root, agent_id, pane_pid)
    if why:
        return sid, why
    if pane["in_mode"] == "1":
        return sid, WHY_COPY_MODE
    width = pane.get("width", "")
    if columns and (not width.isdecimal() or int(width) < columns):
        return sid, WHY_UNREADABLE_INPUT
    cursor = pane.get("cursor_y", "")
    if idle_only and tool == "codex" and not cursor.isdecimal():
        return sid, WHY_UNREADABLE_INPUT
    cursor_row = int(cursor) if idle_only and tool == "codex" else None
    screen = termlib.tmux_read(data_root, "capture-pane", "-p", "-e", "-t", termlib.PREFIX + sid)
    display = screen.stdout or ""
    if idle_only and any("esc to interrupt" in _text(_cells(line)).lower()
                         for line in display.split("\n")):
        return sid, "the agent is working"
    state = _input_state(display, tool, expected=expected, cursor_row=cursor_row) if screen.returncode == 0 else None
    if state is None:
        return sid, WHY_UNREADABLE_INPUT
    return sid, "" if state else WHY_INPUT


def stop_leaves(data_root: Path, agent_id: str) -> tuple[str, str]:
    """(terminal id, why not) for leaving this chat's waiting messages to
    its terminal instead of a Stop hook's block: why is '' when this server
    types them there, now or on a later round — the operator's half-typed
    line or copy mode only delays it. Every other reason the terminal is
    refused (no live terminal, another chat in the pane, a shell in front)
    keeps the block."""
    if not msgledger.AGENT_RE.match(agent_id or "") or agent_id.startswith("codex-"):
        # Codex is woken through its app-server (codexdelivery), not here.
        return "", "not a chat whose terminal this server types into"
    if msgledger.stop_needs_wake(data_root, agent_id):
        return "", "a waiting message cannot be retried in the terminal"
    try:
        sid, why = check(data_root, agent_id)
    except termlib.TmuxError as exc:
        return "", str(exc)
    return sid, "" if why in _PASSING else why


def _paste(data_root: Path, sid: str, buffer_id: str, text: str,
           before_paste: Callable[[], bool], before_enter: Callable[[], bool] | None = None) -> bool:
    """Load and paste one buffer, then Enter if it may still be submitted."""
    target = termlib.PREFIX + sid
    buf = "sp-" + buffer_id
    if termlib.tmux(data_root, "load-buffer", "-b", buf, "-", input=text).returncode != 0:
        return False
    pasted = False
    try:
        if not before_paste():
            return False
        if termlib.tmux(data_root, "paste-buffer", "-p", "-d", "-b", buf, "-t", target).returncode != 0:
            return False
        pasted = True
    finally:
        # paste-buffer -d normally removes it. A refusal before the paste leaves it.
        if not pasted:
            termlib.tmux(data_root, "delete-buffer", "-b", buf)
    time.sleep(ENTER_AFTER_S)
    if before_enter is not None and not before_enter():
        return False
    return termlib.tmux(data_root, "send-keys", "-t", target, "Enter").returncode == 0


def _type(data_root: Path, sid: str, row: dict[str, str]) -> bool:
    def begin() -> bool:
        return check(data_root, row["to_agent"]) == (sid, "") and msgledger.begin_terminal(data_root, row["id"])

    return _paste(data_root, sid, row["id"], msgledger.terminal_text(row), begin)


def _pane_lock(data_root: Path, sid: str) -> Path:
    return lock_path(termlib.folder(data_root) / ("deliver-" + sid))


def try_terminal(data_root: Path, msg_id: str) -> tuple[bool, str]:
    """Type one waiting message into its chat's terminal, when that is safe.
    (typed, why not)."""
    row = msgledger.find(data_root, msg_id)
    if row is None:
        return False, "no such message"
    if row["delivered_via"]:
        return False, f"already delivered ({row['delivered_via']})"
    if row["strayed"]:
        return False, "typed once into a terminal another chat held: its own chat's next prompt or inbox takes it"
    agent = row["to_agent"]
    sid = row["terminal_sid"] or terminal_of(data_root, agent)
    if not re.fullmatch(r"t[0-9a-f]{8}", sid):
        return False, "the chat has no live terminal in Slightly Parallel"
    try:
        with acquire_flock(_pane_lock(data_root, sid), timeout_s=0):
            return _try_in_pane(data_root, sid, msg_id)
    except FileSafetyError:
        return False, "another message is being typed into this terminal"


def _try_in_pane(data_root: Path, sid: str, msg_id: str) -> tuple[bool, str]:
    row = msgledger.find(data_root, msg_id)
    if row is None or row["delivered_via"]:
        return False, "taken by another way meanwhile"
    if row["terminal_sid"] == sid:
        # We hold the pane lock, so its previous sender is gone. The claim
        # itself tells us whether we can retry or may still see a prompt.
        msgledger.finish_terminal(data_root, msg_id)
        row = msgledger.find(data_root, msg_id)
        if row is None or row["delivered_via"] or not msgledger.retryable(row):
            return False, "the earlier terminal send may have landed; the inbox or next prompt takes it"
    if row["terminal_state"]:
        return False, "this message already has a terminal send"
    current, why = check(data_root, row["to_agent"])
    if why:
        return False, why
    if current != sid:
        return False, "the chat's terminal changed"
    claimed = msgledger.claim_terminal(data_root, msg_id, sid)
    if claimed is None:
        return False, "taken by another way meanwhile"
    try:
        ok = _type(data_root, sid, claimed)
    except termlib.TmuxError as exc:
        ok, why = False, str(exc)
    msgledger.finish_terminal(data_root, msg_id, sent=ok)
    return ok, "" if ok else why or "tmux refused the paste"


def try_delivery(data_root: Path, msg_id: str) -> tuple[bool, str]:
    row = msgledger.find(data_root, msg_id)
    if row and row["to_agent"].startswith("codex-"):
        if row["delivered_via"]:
            return False, "already delivered"
        return codexdelivery.try_delivery(data_root, row, chat_meta(data_root, row["to_agent"]) or {})
    return try_terminal(data_root, msg_id)


_last_seen: dict[str, tuple[float, int, bool]] = {}


def retry_waiting(data_root: Path) -> int:
    """One round of the server's loop: each waiting message tried in its
    terminal. Nothing read past a stat when the ledger has not changed since
    a round that found nothing waiting."""
    path = msgledger.ledger_path(data_root)
    try:
        st = path.stat()
    except OSError:
        return 0
    key = str(path)
    seen = _last_seen.get(key)
    if seen is not None and seen[0] == st.st_mtime and seen[1] == st.st_size and not seen[2]:
        return 0
    rows = msgledger.waiting(data_root)
    typed = 0
    for r in rows:
        try:
            ok, _ = try_delivery(data_root, r["id"])
        except Exception:  # noqa: BLE001 — one message must not stop the round
            log.exception("message %s not typed", r["id"])
            ok = False
        typed += ok
    # Cache the snapshot we inspected. A concurrent arrival after waiting()
    # must be picked up next round, even when all earlier rows were delivered.
    _last_seen[key] = (st.st_mtime, st.st_size, len(rows) > typed)
    return typed


def _not_answered_recently(root: Path, agent: str, now: float, seconds: int) -> bool:
    meta = chat_meta(root, agent) or {}
    if not meta.get("message_count") or meta.get("pending_turn") is not None or meta.get("helper"):
        return False
    ended = epoch_of(meta.get("last_answer_at", meta.get("last_active")))
    return ended is not None and now - ended >= seconds


def _ping_one(root: Path, path: Path, now: float, seconds: int) -> bool:
    agent = path.stem
    if not pingstate.due(pingstate.read(path), now, seconds) or not _not_answered_recently(root, agent, now, seconds):
        return False
    sid = terminal_of(root, agent)
    if not re.fullmatch(r"t[0-9a-f]{8}", sid):
        return False
    nonce, text = pingstate.envelope()
    columns = len(text) + 5

    def begin() -> bool:
        return (
            check(root, agent, idle_only=True, columns=columns) == (sid, "")
            and _not_answered_recently(root, agent, now, seconds)
            and pingstate.reserve(path, nonce, sid, now, seconds)
        )

    def submit() -> bool:
        return (
            check(root, agent, idle_only=True, expected=text, columns=columns) == (sid, "")
            and pingstate.read(path).get("enabled") is True
        )

    with acquire_flock(_pane_lock(root, sid), timeout_s=0):
        if check(root, agent, idle_only=True, columns=columns) != (sid, ""):
            return False
        return _paste(root, sid, nonce, text, begin, submit)


def ping_due(root: Path, *, now: datetime | None = None) -> int:
    """Try the enrolled chats once. The ordinary terminal proof still has to pass."""
    paths = sorted((root / pingstate.DIRECTORY).glob("*.json"))
    if not paths:
        return 0
    now = now or datetime.now().astimezone()
    settings = app_settings.load(root)
    quiet_hours = settings["ping.quiet_hours"]
    if quiet_hours:
        start, end = quiet_hours.split("-")
        local = now.strftime("%H:%M")
        in_quiet_hours = start <= local < end if start <= end else local >= start or local < end
        if in_quiet_hours:
            return 0
    seconds = int(settings["ping.interval_minutes"]) * 60
    sent = 0
    for path in paths:
        if not pingstate.AGENT_RE.fullmatch(path.stem):
            continue
        try:
            sent += _ping_one(root, path, now.timestamp(), seconds)
        except FileSafetyError:
            continue  # another sender holds the pane
        except (OSError, ValueError, TypeError, termlib.TmuxError):
            log.warning("keep-alive could not be sent to %s", path.stem, exc_info=True)
    return sent
