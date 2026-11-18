"""The terminal window's tab strip (tk_a9306fb1): light reads for each tab.

The window at /term draws a tab per terminal. Three things it needs that the
terminal list does not carry, read here in one call for the whole strip:

* the title the program in the terminal set for itself (OSC 0/2 — Claude
  Code sets the chat's name there). tmux keeps it as ``pane_title``; a
  pane whose program set none answers with the computer's name, which is
  not a title. Plain terminals: only the page sees it (xterm.js).
* the chat behind the terminal, from what Slightly Parallel recorded: its
  name, its tool, the tasks it worked on (closed / all — tasks named in its
  turns, as the agent profile counts them), its branches (chats branched
  from it: ``branch`` links from it and the chats it started, helpers left
  out), and the context it uses — Claude Code's own figure from its status
  line (``.usage/sessions``); a tool without a status line has none — and
  its rhythm: messages, commits, tasks closed and tokens in each of the last
  six clock hours (rhythm.py; the tab's six dots, tk_d2e11125).
* the agents this computer has (the "+" menu offers only those), the chats
  of a project that can be resumed, and the command that branches a chat.

Reads only. Nothing here starts a terminal: the window opens one through
``POST /api/terminal/sessions`` as it always did.
"""

from __future__ import annotations

import re
import shlex
import socket
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import rhythm, termlib, usagelib
from ..db import ViewStore
from ..entities import DONE_STATUSES
from ..sessions import is_helper
from .deps import get_store, not_found, rows_or_empty
from .terminal import _guard

router = APIRouter()

#: A resumable chat list is short: the newest few of a project.
RESUMABLE_MAX = 12
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def pane_titles(data_root: Path) -> dict[str, str]:
    """terminal id → the title its program set (tmux's pane_title); none for
    a pane whose title is still the computer's name (nothing set one)."""
    if termlib.tmux_path() is None:
        return {}
    got = termlib.tmux_read(data_root, "list-panes", "-a", "-F", "#{session_name}\t#{pane_title}")
    host = {socket.gethostname(), socket.gethostname().split(".")[0]}
    out: dict[str, str] = {}
    for line in got.stdout.splitlines():
        name, _, title = line.partition("\t")
        title = title.strip()
        if not name.startswith(termlib.PREFIX) or not title or title in host:
            continue
        out.setdefault(name[len(termlib.PREFIX):], title)
    return out


def _name_of(a: dict[str, Any]) -> str:
    aid = str(a.get("agent_id") or "")
    name = str(a.get("agent_name") or "")
    if name and name != aid:
        return name
    return str(a.get("chat_title") or "")


def chat_facts(store: ViewStore, agent_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Per agent: name, tool, tasks closed and all, branches, context used, rhythm."""
    ids = [a for a in dict.fromkeys(agent_ids) if a]
    if not ids:
        return {}
    agents = store.agents()
    by_id = {str(a.get("agent_id") or ""): a for a in agents}
    ph = ",".join("?" * len(ids))
    tasks: dict[str, dict[str, str]] = {}
    for r in rows_or_empty(
        store,
        "SELECT DISTINCT m.agent_id AS aid, m.task_id AS tid, COALESCE(t.status, '') AS status "
        f"FROM task_mentions m JOIN tasks_mutual t ON t.id = m.task_id WHERE m.agent_id IN ({ph})",
        tuple(ids),
    ):
        tasks.setdefault(str(r["aid"]), {})[str(r["tid"])] = str(r["status"] or "")
    branched: dict[str, set[str]] = {}
    for r in rows_or_empty(
        store, f"SELECT from_id, to_id FROM agent_links_mutual WHERE kind = 'branch' AND from_id IN ({ph})", tuple(ids),
    ):
        branched.setdefault(str(r["from_id"]), set()).add(str(r["to_id"]))
    wanted = set(ids)
    for a in agents:
        parent = str(a.get("parent_agent_id") or "")
        if parent in wanted and not is_helper(a):
            branched.setdefault(parent, set()).add(str(a.get("agent_id") or ""))
    now = usagelib.now()
    since = rhythm.periods(now)[0]
    closed = rhythm.closed_at(store, {t for mine in tasks.values() for t in mine}, since)
    out: dict[str, dict[str, Any]] = {}
    for aid in ids:
        a = by_id.get(aid)
        if a is None:
            continue
        tool = str(a.get("tool") or "")
        mine = tasks.get(aid, {})
        state = usagelib.session_state(store.data_root, tool, str(a.get("session_ref") or ""))
        ctx = state.get("context") if isinstance(state.get("context"), dict) else {}
        used = ctx.get("used_pct")
        out[aid] = {
            "name": _name_of(a),
            "tool": tool,
            "tasks_done": sum(1 for s in mine.values() if s.strip().lower() in DONE_STATUSES),
            "tasks_all": len(mine),
            "branches": len(branched.get(aid, set()) - {aid}),
            # Claude Code's status line: the share of the window in use. None: not known.
            "ctx_pct": float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) else None,
            "ctx_size": int(ctx["size"]) if isinstance(ctx.get("size"), (int, float)) and not isinstance(ctx.get("size"), bool) else None,
            "ctx_at": str(state.get("at") or ""),
            "rhythm": rhythm.rhythm(a, set(mine), closed, now),
        }
    return out


@router.get("/api/terminal/tabs")
def terminal_tabs(request: Request, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{tabs: {sid: {title, agent_id, chat}}}`` for every terminal: the title
    its program set (tmux only), the chat linked to it and that chat's facts."""
    _guard(request)
    root = request.app.state.settings.data_root
    rows = termlib.rows(root)
    links = termlib.agent_links(root) if rows else {}
    titles = pane_titles(root) if any(r.get("backend") == "tmux" for r in rows) else {}
    aid_of = {str(r.get("id")): str((links.get(str(r.get("id"))) or {}).get("agent_id") or r.get("agent_id") or "") for r in rows}
    facts = chat_facts(store, list(aid_of.values()))
    return {"tabs": {
        sid: {"title": titles.get(sid, ""), "agent_id": aid, "chat": facts.get(aid)}
        for sid, aid in aid_of.items()
    }}


@router.get("/api/terminal/agents")
def terminal_agents(request: Request) -> dict[str, Any]:
    """The agents this computer has, for the window's "+" menu."""
    _guard(request)
    from .setup import tools_installed
    got = tools_installed()
    return {"agents": {k: bool(got.get(k)) for k in ("claude", "codex", "opencode")}}


@router.get("/api/terminal/resumable")
def terminal_resumable(request: Request, project: str = Query(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """The newest chats of a project that a terminal can resume (their tool
    and session are known) and that no open terminal holds now."""
    _guard(request)
    root = request.app.state.settings.data_root
    held = {str(v.get("agent_id") or "") for v in termlib.agent_links(root).values()}
    held |= {str(r.get("agent_id") or "") for r in termlib.rows(root)}
    out = []
    for a in store.agents():
        aid = str(a.get("agent_id") or "")
        if a.get("project") != project or is_helper(a) or aid in held:
            continue
        if not termlib.resume_command(str(a.get("tool") or ""), str(a.get("session_ref") or "")):
            continue
        out.append({"agent_id": aid, "name": _name_of(a) or aid, "tool": str(a.get("tool") or ""),
                    "last_active": str(a.get("last_active") or a.get("created_date") or "")})
    out.sort(key=lambda x: x["last_active"], reverse=True)
    return {"chats": out[:RESUMABLE_MAX]}


def branch_command(tool: str, session_ref: str, cwd: str, family: str | None = None) -> str:
    """The command that opens a copy of a chat to go on from where it stands:
    Claude Code resumes the session into a new one (``--fork-session``),
    Codex forks it. "" for a tool that cannot or a chat with no session."""
    if not session_ref or not _SAFE_REF.match(session_ref):
        return ""
    if tool == "claude-code":
        run = f"claude -r {session_ref} --fork-session"
    elif tool == "codex":
        run = f"codex fork {session_ref}"
    else:
        return ""
    if not cwd:
        return run
    family = family or termlib.command_family()
    if family == "powershell":
        return f"Set-Location -LiteralPath {termlib.ps_quote(cwd, literal=True)}; if ($?) {{ {run} }}"
    if family == "cmd":
        return f"cd /d {termlib.cmd_quote(cwd, literal=True)} && {run}"
    return f"cd {shlex.quote(cwd)} && {run}"


@router.get("/api/terminal/branch/{agent_id}")
def terminal_branch(agent_id: str, request: Request, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{command, project, cwd, name}``: what the window types into a new
    terminal to branch this chat. 422 when its tool cannot branch."""
    _guard(request)
    a = next((x for x in store.agents() if str(x.get("agent_id") or "") == agent_id), None)
    if a is None:
        raise not_found("agent", agent_id)
    cmd = branch_command(str(a.get("tool") or ""), str(a.get("session_ref") or ""), str(a.get("cwd") or ""))
    if not cmd:
        raise HTTPException(status_code=422, detail="This chat cannot be branched: only Claude Code and Codex chats with a recorded session can.")
    return {"command": cmd, "project": str(a.get("project") or ""), "cwd": str(a.get("cwd") or ""), "name": _name_of(a) or agent_id}
