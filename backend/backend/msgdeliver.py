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
- the active pane has no unregistered tmux client and its window belongs
  to this session alone. The operator's SP views and direct SP terminal
  writes share an input lock with automatic delivery;
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
from pathlib import Path
from typing import Any

from . import chatstore, codexdelivery, msgledger, termlib
from .file_safety import FileSafetyError, acquire_flock
from .hookshared import process_started

log = logging.getLogger("sp.messages")

#: Tools whose input line this module can read.
TOOLS = ("claude-code", "codex")
_RULE = "─"
_CLAUDE_PROMPT = "❯"
_CODEX_PROMPT = "›"
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
    # Codex indents continuation rows. A draft that starts one with › is
    # text inside the composer, not a new composer.
    if k >= len(cells) or cells[k][0] != glyph or (k and glyph == _CODEX_PROMPT):
        return None
    return cells[k + 1:]


def _input_state(screen: str, tool: str) -> bool | None:
    """True for an empty composer, False for a draft, None when unreadable."""
    rows = [_cells(r) for r in screen.split("\n")]
    while rows and not _text(rows[-1]).strip():
        rows.pop()
    glyph = _CLAUDE_PROMPT if tool == "claude-code" else _CODEX_PROMPT if tool == "codex" else ""
    if not glyph:
        return None
    at = next((i for i in range(len(rows) - 1, -1, -1) if _after_prompt(rows[i], glyph) is not None), None)
    if at is None:
        return None
    rest = _after_prompt(rows[at], glyph) or []
    if tool == "claude-code":
        if at == 0 or not _is_rule(rows[at - 1]):
            return None
        bottom = next((i for i in range(at + 1, len(rows)) if _is_rule(rows[i])), None)
        if bottom is None:
            return None
        return bottom == at + 1 and not _typed(rest)
    # Codex may put a blank row before a later line of the draft. A footer
    # that the TUI did not draw dim is ambiguous, so we leave it alone.
    return not _typed(rest) and not any(_typed(row) for row in rows[at + 1:])


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


def _client_ids_format(name: str) -> str:
    # Use client_session, not session_id: a non-attached command client
    # can inherit the command's session context.
    return "#{L:#{?#{==:#{client_session}," + name + "},#{client_pid}|,}}"


def _pane(data_root: Path, sid: str) -> dict[str, str] | None:
    name = termlib.PREFIX + sid
    fields = {
        "fg": "#{pane_current_command}", "in_mode": "#{pane_in_mode}", "dead": "#{pane_dead}",
        "pid": "#{pane_pid}", "id": "#{pane_id}", "session": "#{session_id}",
        "linked": "#{window_linked}", "attached": "#{session_attached}",
        "clients": _client_ids_format(name), "cursor_y": "#{cursor_y}", "cursor_x": "#{cursor_x}",
        "width": "#{pane_width}",
    }
    got = termlib.tmux_read(data_root, "display-message", "-p", "-t", f"={name}:",
                            "\t".join(fields.values()))
    parts = (got.stdout or "").rstrip("\n").split("\t")
    return dict(zip(fields, parts)) if got.returncode == 0 and len(parts) == len(fields) else None


def _clients_owned(data_root: Path, sid: str, pane: dict[str, str]) -> bool:
    attached, ids = pane["attached"], pane["clients"]
    if not attached.isdecimal() or not re.fullmatch(r"(?:[0-9]+\|)*", ids):
        return False
    pids = {int(pid) for pid in ids.split("|") if pid}
    if len(pids) != int(attached) or not termlib.owns_clients(data_root, sid, pids):
        return False
    if not pids:
        return True
    clients = termlib.tmux_read(data_root, "list-clients", "-t", termlib.PREFIX + sid, "-F", "#{client_pid}")
    listed = (clients.stdout or "").split()
    return clients.returncode == 0 and set(listed) == {str(pid) for pid in pids}


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
WHY_FOREIGN = "terminal input is not controlled by Slightly Parallel"
_PASSING = (WHY_INPUT, WHY_COPY_MODE)


def _check(data_root: Path, agent_id: str) -> tuple[str, dict[str, str] | None, str]:
    if termlib.tmux_path() is None:
        return "", None, "no tmux"
    meta = chat_meta(data_root, agent_id)
    if meta is None:
        return "", None, "no such chat"
    tool = str(meta.get("tool") or "")
    if tool not in TOOLS:
        return "", None, f"the chat's tool ({tool or 'unknown'}) has no input line this server can read"
    sid = str(meta.get("terminal") or "")
    row = termlib.get(data_root, sid) if sid else None
    if row is None or row.get("backend") != "tmux":
        return "", None, "the chat has no live terminal in Slightly Parallel"
    pane = _pane(data_root, sid)
    if pane is None or pane["dead"] != "0":
        return sid, None, "the terminal is gone"
    name = pane["fg"].split("/")[-1].lstrip("-")
    if not name or name in termlib.SHELLS:
        return sid, None, "a shell is in front: the agent is not running there"
    if not pane["pid"].isdecimal():
        return sid, None, "the pane's process cannot be read"
    why = occupant_why(data_root, agent_id, int(pane["pid"]))
    if why:
        return sid, None, why
    if not (re.fullmatch(r"%[0-9]+", pane["id"]) and re.fullmatch(r"\$[0-9]+", pane["session"])
            and re.fullmatch(r"[A-Za-z0-9_./:+-]+", pane["fg"])):
        return sid, None, WHY_FOREIGN
    if pane["linked"] != "0" or not _clients_owned(data_root, sid, pane):
        return sid, None, WHY_FOREIGN
    if pane["in_mode"] == "1":
        return sid, None, WHY_COPY_MODE
    if pane["in_mode"] != "0":
        return sid, None, WHY_FOREIGN
    if termlib.operator_waiting(data_root, sid):
        return sid, None, WHY_INPUT
    screen = termlib.tmux_read(data_root, "capture-pane", "-p", "-e", "-t", pane["id"])
    state = _input_state(screen.stdout or "", tool) if screen.returncode == 0 else None
    if state is None:
        return sid, None, WHY_UNREADABLE_INPUT
    return (sid, pane, "") if state else (sid, None, WHY_INPUT)


def check(data_root: Path, agent_id: str) -> tuple[str, str]:
    """The chat's terminal and why automatic typing must defer, if anything."""
    sid, _, why = _check(data_root, agent_id)
    return sid, why


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


def _submit(data_root: Path, sid: str, pane: dict[str, str], buf: str) -> bool | None:
    """True if submitted, False if tmux refused before writing, else uncertain."""
    target = pane["id"]
    # An immediate format test and synchronous command list in tmux. Native
    # client changes and selection changes cannot get between paste and Enter.
    guards = {
        "#{session_id}": pane["session"], "#{pane_pid}": pane["pid"],
        "#{pane_current_command}": pane["fg"], "#{window_active}": "1", "#{pane_active}": "1",
        "#{window_linked}": "0", "#{pane_dead}": "0", "#{pane_in_mode}": "0",
        "#{cursor_y}": pane["cursor_y"], "#{cursor_x}": pane["cursor_x"], "#{pane_width}": pane["width"],
        "#{session_attached}": pane["attached"], _client_ids_format(termlib.PREFIX + sid): pane["clients"],
    }
    condition = "1"
    for key, value in guards.items():
        condition = f"#{{&&:{condition},#{{==:{key},{value}}}}}"
    out = termlib.tmux(data_root, "if-shell", "-F", "-t", target, condition,
                       f"paste-buffer -p -d -b {buf} -t {target} ; send-keys -t {target} Enter ; display-message -p sent",
                       "display-message -p deferred")
    if out.returncode != 0:
        return None
    result = (out.stdout or "").strip()
    return {"sent": True, "deferred": False}.get(result)


def _type(data_root: Path, sid: str, pinned: dict[str, str], row: dict[str, str]) -> bool | None:
    buf = "sp-" + row["id"]
    if termlib.tmux(data_root, "load-buffer", "-b", buf, "-", input=msgledger.terminal_text(row)).returncode != 0:
        return False
    sent = None
    try:
        if not msgledger.begin_terminal(data_root, row["id"]):
            return False
        current, pane, _ = _check(data_root, row["to_agent"])
        if (current != sid or pane is None or any(pane[k] != pinned[k] for k in ("id", "session", "pid"))
                or termlib.operator_waiting(data_root, sid)):
            return False
        sent = _submit(data_root, sid, pane, buf)
        return sent
    finally:
        if sent is not True:
            termlib.tmux(data_root, "delete-buffer", "-b", buf)


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
        with acquire_flock(termlib.input_lock(data_root, sid), timeout_s=0):
            return _try_in_pane(data_root, sid, msg_id)
    except FileSafetyError:
        return False, "terminal input is busy"


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
    current, pane, why = _check(data_root, row["to_agent"])
    if pane is None:
        return False, why
    if current != sid:
        return False, "the chat's terminal changed"
    claimed = msgledger.claim_terminal(data_root, msg_id, sid)
    if claimed is None:
        return False, "taken by another way meanwhile"
    try:
        ok = _type(data_root, sid, pane, claimed)
    except termlib.TmuxError as exc:
        ok, why = None, str(exc)
    msgledger.finish_terminal(data_root, msg_id, sent=ok is True, untouched=ok is False)
    if ok is True:
        return True, ""
    if ok is False:
        return False, "the pane or its input changed before submission"
    return False, why or "tmux did not confirm the submission"


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
