"""A task's thread in the chats: the turns the task window's Chat section reads.

Three kinds of turn, each marked with why it is there (``why``):

- ``mention`` — the turn names the task: its id in the operator's message or
  the agent's reply, or the operator's ``#now`` that started it (a card the
  agent or the server wrote for that turn has no id in the message).
- ``done`` — inside a stretch a ``#done`` closed (donelib.py): from the turn
  after the previous #done, or after another task was named, up to the #done.
  The work between the mentions, which names no id.
- ``next`` — after a mention no #done covers, up to the turn where the
  operator names another task (its id, a ``#now``, a ``#done``), or the end
  of the chat. A guess, so the window offers it off by default.

Only the operator's naming ends a stretch: an agent's reply that mentions
another task in passing does not — the rule #done itself follows.
"""

from __future__ import annotations

import json
from typing import Any

from .db import ViewStore


def thread(store: ViewStore, task_id: str, mentions: list[dict]) -> dict[str, Any]:
    """The turns of every chat that touched the task, in the mentions' order
    of chats, each once; and how many turns each switch adds."""
    from . import donelib, nowlib
    from .sessions import chat_path, parse_turns

    roles: dict[tuple[str, int], list[str]] = {}
    for m in mentions:
        roles.setdefault((str(m["agent_id"]), int(m["turn"] or 0)), [])
        if m["role"] not in roles[(str(m["agent_id"]), int(m["turn"] or 0))]:
            roles[(str(m["agent_id"]), int(m["turn"] or 0))].append(m["role"])
    # The #now that started the card names it, though its message has no id.
    started = [(a, n) for a, n, tid in nowlib.card_turns(store, {a for a, _ in roles} | _now_agents(store, task_id), ("started",))
               if tid == task_id]
    started += [(r["agent_id"], int(r["turn"] or 0)) for r in nowlib.rows(store) if r.get("task_id") == task_id]
    for key in started:
        roles.setdefault(key, [])
        if "user" not in roles[key]:
            roles[key].append("user")

    done = donelib.stretches_raw(store, task_id)
    agents = sorted({a for a, _ in roles} | {a for a, _, _ in done})
    out: list[dict[str, Any]] = []
    added = {"done": 0, "next": 0}
    agent_rows = {str(m["agent_id"]): m.get("agent") for m in mentions}
    for agent in agents:
        path = chat_path(store, agent)
        try:
            turns = parse_turns(path) if path else []
        except OSError:
            turns = []
        if not turns:
            continue
        by_n = {t.number: t for t in turns}
        sessions = _sessions_of(store, agent)
        named = {n for a, n in roles if a == agent}
        in_done = {n for a, s, e in done if a == agent for n in range(s, e + 1)}
        others = _other_tasks_named(store, agent, task_id)
        nexts: set[int] = set()
        last = max(by_n)
        # Only a turn where the operator named the task opens a "next" stretch:
        # an agent's reply naming it in passing does not start the task there.
        for n in sorted(k for k in named if "user" in roles.get((agent, k), [])):
            if n in in_done:
                continue
            k = n + 1
            while k <= last and k not in others and k not in named and k not in in_done:
                nexts.add(k)
                k += 1
        project = next((str(m.get("project") or "") for m in mentions if str(m["agent_id"]) == agent), "")
        for n in sorted(named | in_done | nexts):
            t = by_n.get(n)
            if t is None:
                continue
            why = "mention" if n in named else "done" if n in in_done else "next"
            if why != "mention":
                added[why] += 1
            out.append({
                "project": project, "agent_id": agent, "session_id": sessions.get(n, ""),
                "turn": n, "at": t.at.strftime("%Y-%m-%dT%H:%M:%S"), "why": why,
                "roles": roles.get((agent, n), []), "agent": agent_rows.get(agent),
                "said": t.user_summary or "", "reply": t.agent_summary or "",
            })
    if any(r["agent"] is None for r in out):
        from .routers.deps import attach_agent
        missing = [r for r in out if r["agent"] is None]
        attach_agent(store, missing)
    return {"turns": out, "done_turns": added["done"], "next_turns": added["next"],
            "has_done": bool(done)}


def _now_agents(store: ViewStore, task_id: str) -> set[str]:
    row = store.query_one("SELECT agent_id FROM tasks_mutual WHERE id = ?", (task_id,)) or {}
    return {str(row.get("agent_id") or "")} - {""}


def _sessions_of(store: ViewStore, agent: str) -> dict[int, str]:
    """Turn number → the session it belongs to, for opening the chat there."""
    out: dict[int, str] = {}
    for s in store.query("SELECT id, turns_json FROM sessions WHERE agent_id = ?", (agent,)):
        try:
            for t in json.loads(s.get("turns_json") or "[]"):
                out[int(t.get("n") or 0)] = str(s["id"])
        except (ValueError, TypeError):
            continue
    return out


def _other_tasks_named(store: ViewStore, agent: str, task_id: str) -> set[int]:
    """The turns where the operator named another task: its id, a #now, a #done."""
    turns = {int(r["turn"] or 0) for r in store.query(
        "SELECT turn FROM task_mentions WHERE agent_id = ? AND role = 'user' AND task_id <> ?", (agent, task_id))}
    for table in ("now_tags", "done_tags"):
        turns |= {int(r["turn"] or 0) for r in store.query(f"SELECT turn FROM {table} WHERE agent_id = ?", (agent,))}
    return turns
