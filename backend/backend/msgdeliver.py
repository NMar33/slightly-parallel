"""Typing a message into the chat's terminal (tk_c1caab80).

A message waits in the ledger (msgledger.py) until a way takes it. The
quickest is the chat's own terminal: the capture hook fires only when a
prompt comes in, so an agent left idle would never hear of it otherwise.
The server types the message there as one prompt that opens with the
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
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from . import msgledger, termlib
from .hookshared import process_started

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


def input_empty(screen: str, tool: str) -> bool:
    """Is the tool's input line on this screen (``capture-pane -p -e``) there
    and empty? False whenever it cannot be told: the message then waits."""
    rows = [_cells(r) for r in screen.split("\n")]
    while rows and not _text(rows[-1]).strip():
        rows.pop()
    glyph = _CLAUDE_PROMPT if tool == "claude-code" else _CODEX_PROMPT if tool == "codex" else ""
    if not glyph:
        return False
    at = next((i for i in range(len(rows) - 1, -1, -1) if _after_prompt(rows[i], glyph) is not None), None)
    if at is None:
        return False
    rest = _after_prompt(rows[at], glyph) or []
    if _typed(rest):
        return False
    if tool == "claude-code":
        # The box: a rule above the input row and one straight under it. A
        # second row of input, or a menu's "❯ 1. Yes" with no rule, is no.
        return at > 0 and _is_rule(rows[at - 1]) and at + 1 < len(rows) and _is_rule(rows[at + 1])
    # Codex: the composer is the last "›" row; a row of input under it would
    # be the operator's second line.
    return at + 1 >= len(rows) or not _typed(rows[at + 1])


# ---------------------------------------------------------------------------
# The chat's terminal
# ---------------------------------------------------------------------------


def chat_meta(data_root: Path, agent_id: str) -> dict[str, Any] | None:
    if not msgledger.AGENT_RE.match(agent_id or ""):
        return None
    for p in sorted(Path(data_root).glob(f"projects/*/chats/{agent_id}/meta.json")):
        try:
            got = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(got, dict):
            got.setdefault("project", p.parent.parent.parent.name)
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
                            "#{pane_current_command}\t#{pane_in_mode}\t#{pane_dead}\t#{pane_pid}")
    if got.returncode != 0:
        return None
    parts = (got.stdout or "").rstrip("\n").split("\t")
    if len(parts) < 4:
        return None
    return {"fg": parts[0], "in_mode": parts[1], "dead": parts[2], "pid": parts[3]}


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


def check(data_root: Path, agent_id: str) -> tuple[str, str]:
    """(terminal id, why not) for typing into this chat's terminal now:
    why is '' when it may be typed into."""
    if termlib.tmux_path() is None:
        return "", "no tmux"
    meta = chat_meta(data_root, agent_id)
    if meta is None:
        return "", "no such chat"
    tool = str(meta.get("tool") or "")
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
    if pane["in_mode"] == "1":
        return sid, "the terminal is in copy mode"
    screen = termlib.tmux_read(data_root, "capture-pane", "-p", "-e", "-t", termlib.PREFIX + sid).stdout or ""
    if not input_empty(screen, tool):
        return sid, "the input line is not empty (or cannot be read)"
    try:
        pane_pid = int(pane["pid"])
    except ValueError:
        return sid, "the pane's process cannot be read"
    why = occupant_why(data_root, agent_id, pane_pid)
    return sid, why


def _type(data_root: Path, sid: str, text: str) -> bool:
    """The text as one paste (bracketed, when the program asked for that), then Enter."""
    target = termlib.PREFIX + sid
    buf = f"sp-msg-{sid}"
    if termlib.tmux(data_root, "load-buffer", "-b", buf, "-", input=text).returncode != 0:
        return False
    if termlib.tmux(data_root, "paste-buffer", "-p", "-d", "-b", buf, "-t", target).returncode != 0:
        return False
    time.sleep(ENTER_AFTER_S)
    return termlib.tmux(data_root, "send-keys", "-t", target, "Enter").returncode == 0


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
    try:
        sid, why = check(data_root, row["to_agent"])
    except termlib.TmuxError as exc:
        return False, str(exc)
    if why:
        return False, why
    claimed = msgledger.claim_terminal(data_root, msg_id)
    if claimed is None:
        return False, "taken by another way meanwhile"
    try:
        ok = _type(data_root, sid, msgledger.terminal_text(claimed))
    except termlib.TmuxError as exc:
        ok, why = False, str(exc)
    if not ok:
        msgledger.release_terminal(data_root, msg_id)
        return False, why or "tmux refused the paste"
    return True, ""


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
            ok, _ = try_terminal(data_root, r["id"])
        except Exception:  # noqa: BLE001 — one message must not stop the round
            log.exception("message %s not typed", r["id"])
            ok = False
        typed += ok
    try:
        st = path.stat()
        _last_seen[key] = (st.st_mtime, st.st_size, len(rows) > typed)
    except OSError:
        pass
    return typed
