"""The daily standup: one per project per day, written from the day's chats.

Agents live one to three days, so a standup per agent said little. The
standup is the project's: what happened in every chat of one day, written
the next time anyone works on the project. The first agent of the day is
told there is none; it asks the operator, and a helper agent on a cheaper
model reads the day's messages and writes it.

This module answers three questions and keeps two small facts:

- is a standup owed for a day (``state``), and is someone writing it
  (``claim``) or did the operator put it off (``postpone``);
- what happened that day (``material``): every message, trimmed, with the
  commits each turn made;
- how to write it (``instructions``): the contract's own parts, so the
  prompt lives in one place and the operator can edit it there.

The capture hook reads the same two files to decide what to tell an agent,
because it runs with no server (scripts/hooks/capture.py: _standup_notice).
"""

from __future__ import annotations

import re

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import frontmatter, sessions
from .date_utils import day_before, day_of
from .db import ViewStore
from .file_safety import edit_json, safe_read_json

STATE_FILE = "standup_state.json"
CLAIM_MINUTES = 45
USER_MAX = 1500
AGENT_MAX = 900
PARTS = ("31-writing.md", "49-standup.md")


def yymm_dd(day: datetime) -> str:
    """A day as Slightly Parallel writes it (date_utils is the one reading)."""
    return day_of(day)


def yesterday(now: datetime | None = None) -> str:
    return yymm_dd((now or datetime.now()) - timedelta(days=1))


def _key(project: str, day: str) -> str:
    return f"{project}|{day}"


def _load(root: Path) -> dict[str, Any]:
    try:
        data = safe_read_json(root / STATE_FILE)
    except (OSError, ValueError):
        data = None
    return data if isinstance(data, dict) else {}


def _edit(root: Path, change) -> dict[str, Any]:
    """The one read-modify-write cycle (file_safety.edit_json)."""
    return edit_json(root / STATE_FILE, change)


def written(store: ViewStore, project: str, day: str) -> str:
    """The id of the standup that covers ``day``, or ''.

    A standup says which day it covers in ``for_date``. An older one has
    none and covers the day before it was written.
    """
    rows = store.query(
        "SELECT id, created_date, for_date FROM standups_mutual WHERE project = ?", (project,)
    )
    for r in rows:
        if str(r.get("for_date") or "") == day:
            return str(r["id"])
    # An older standup names no day. It was asked for on a new day, about the
    # day before, so it covers the day before it was written.
    for r in rows:
        if not str(r.get("for_date") or "") and day_before(str(r.get("created_date") or "")) == day:
            return str(r["id"])
    return ""




def state(store: ViewStore, project: str, day: str, now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    data = _load(store.data_root).get(_key(project, day)) or {}
    claim = data.get("claim") or {}
    claimed = bool(claim) and now - float(claim.get("at") or 0) < CLAIM_MINUTES * 60
    until = float(data.get("postponed_until") or 0)
    return {
        "project": project,
        "date": day,
        "standup_id": written(store, project, day),
        "claimed_by": str(claim.get("agent_id") or "") if claimed else "",
        "postponed": until > now,
    }


def claim(store: ViewStore, project: str, day: str, agent_id: str) -> dict[str, Any]:
    """Say "I am writing it". The first claim stands for 45 minutes."""
    taken: dict[str, str] = {}

    def change(data: dict) -> None:
        entry = data.setdefault(_key(project, day), {})
        old = entry.get("claim") or {}
        fresh = old and time.time() - float(old.get("at") or 0) < CLAIM_MINUTES * 60
        if fresh and old.get("agent_id") != agent_id:
            taken["by"] = str(old.get("agent_id") or "")
            return
        entry["claim"] = {"agent_id": agent_id, "at": time.time()}

    _edit(store.data_root, change)
    return {"claimed": not taken, "claimed_by": taken.get("by") or agent_id}


def postpone(store: ViewStore, project: str, day: str, hours: float) -> dict[str, Any]:
    until = time.time() + max(0.5, min(float(hours), 72.0)) * 3600

    def change(data: dict) -> None:
        data.setdefault(_key(project, day), {})["postponed_until"] = until

    _edit(store.data_root, change)
    return {"postponed_until": datetime.fromtimestamp(until).strftime("%Y-%m-%dT%H:%M")}


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    head = int(limit * 0.72)
    return text[:head] + " […] " + text[-(limit - head - 5):]


def material(store: ViewStore, project: str, day: str, clip: bool = False) -> dict[str, Any]:
    """Every message of the day, by chat, with what each turn committed.

    Messages and answers come whole: a standup written from the first and
    last lines of each answer missed what was done in the middle. ``clip``
    (the operator's choice when the day is large) keeps the start and the end
    of each, as before. ``chars`` is the size either way, for the next ask.
    """
    rows = store.query(
        "SELECT * FROM sessions WHERE project = ? AND created_date = ? ORDER BY start_time",
        (project, day),
    )
    names = {str(a.get("agent_id") or ""): a for a in store.agents()}
    chats: list[dict[str, Any]] = []
    messages = 0
    full_chars = 0
    for row in rows:
        agent = names.get(str(row.get("agent_id") or ""), {})
        title = str(agent.get("chat_title") or "") or (
            str(agent.get("agent_name") or "") if agent.get("agent_name") != row.get("agent_id") else ""
        )
        turns = []
        for t in sessions.turns_with_work(store, row):
            work = t.get("work") or {}
            user, agent = str(t.get("user") or ""), str(t.get("agent") or "")
            full_chars += len(user) + len(agent)
            turns.append({
                "at": t.get("at"),
                "user": _clip(user, USER_MAX) if clip else user,
                "agent": _clip(agent, AGENT_MAX) if clip else agent,
                "commits": [str(c.get("subject") or "") for c in (work.get("commits") or [])][:10],
            })
            messages += 1
        chats.append({
            "agent_id": row.get("agent_id"), "chat": title,
            "from": row.get("start_time"), "to": row.get("end_time"), "turns": turns,
        })
    clipped_chars = sum(len(t["user"]) + len(t["agent"]) for c in chats for t in c["turns"])
    return {"messages_n": messages, "chats_n": len({c["agent_id"] for c in chats}), "chats": chats,
            "clipped": clip, "chars": {"full": full_chars, "clipped": clipped_chars if clip else
                                        sum(len(_clip(t["user"], USER_MAX)) + len(_clip(t["agent"], AGENT_MAX))
                                            for c in chats for t in c["turns"])},
            "previous": previous(store, project, day)}


_TASK_RE = re.compile(r"\btk_[0-9a-f]{8}\b")

# Entries the day may have created, shown under "Created": table, kind word.
_CREATED = (("visions_mutual", "vision"), ("rules_mutual", "rule"), ("problems_mutual", "problem"),
            ("entrypoints_mutual", "entry point"),
            ("skills_mutual", "skill"), ("artifacts_mutual", "artifact"), ("ideas_mutual", "idea"))


def day_record(store: ViewStore, project: str, day: str, tasks_changed: list[dict[str, Any]]) -> dict[str, Any]:
    """What the standup page shows beside the text, built from the record
    with no model: the tasks of the day (moved, or named in a chat), the
    agents of the day (what each chat was, when, how many turns, the commits
    it made, how to resume it) and what the day created."""
    rows = store.query(
        "SELECT * FROM sessions WHERE project = ? AND created_date = ? ORDER BY start_time", (project, day))
    agents_by_id = {str(a.get("agent_id") or ""): a for a in store.agents()}
    named: dict[str, set[str]] = {}
    per_agent: dict[str, dict[str, Any]] = {}
    for row in rows:
        aid = str(row.get("agent_id") or "")
        a = agents_by_id.get(aid, {})
        rec = per_agent.setdefault(aid, {
            "agent_id": aid, "chat": str(a.get("chat_title") or a.get("l1_headline") or ""),
            "from": str(row.get("start_time") or ""), "to": str(row.get("end_time") or ""),
            "turns_n": 0, "commits_n": 0, "agent_min": 0, "tasks": [],
            "tool": a.get("tool") or "", "cwd": a.get("cwd") or "", "session_ref": a.get("session_ref") or "",
        })
        rec["to"] = str(row.get("end_time") or rec["to"])
        rec["agent_min"] += int(row.get("agent_min") or 0)
        for t in sessions.turns_with_work(store, row):
            rec["turns_n"] += 1
            rec["commits_n"] += len((t.get("work") or {}).get("commits") or [])
            for tid in _TASK_RE.findall(f"{t.get('user') or ''}\n{t.get('agent') or ''}"):
                named.setdefault(tid, set()).add(aid)
                if tid not in rec["tasks"]:
                    rec["tasks"].append(tid)
    changed = {str(t.get("id") or ""): t for t in tasks_changed}
    ids = list(changed) + [tid for tid in named if tid not in changed]
    titles: dict[str, dict[str, Any]] = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        for r in store.query(f"SELECT id, title, status FROM tasks_mutual WHERE id IN ({marks})", tuple(ids)):
            titles[str(r["id"])] = r
    tasks = []
    for tid in ids:
        if tid not in titles:
            continue
        moves = [c for c in (changed.get(tid) or {}).get("changes") or [] if c.get("field") == "status"]
        tasks.append({"id": tid, "title": str(titles[tid].get("title") or ""), "status": str(titles[tid].get("status") or ""),
                      "moves": [{"from": c.get("from"), "to": c.get("to"), "at": c.get("at"), "actor": c.get("actor")} for c in moves],
                      "agents": sorted(named.get(tid, set()))})
    created = []
    for table, kind in _CREATED:
        try:
            for r in store.query(f"SELECT id, l1 FROM {table} WHERE project = ? AND created_date = ? ORDER BY created_time",
                                 (project, day)):
                created.append({"kind": kind, "id": str(r["id"]), "title": str(r.get("l1") or "")[:160]})
        except Exception:  # noqa: BLE001 — a lens table missing on an older data folder
            continue
    return {"tasks": tasks, "agents": list(per_agent.values()), "created": created}


def previous(store: ViewStore, project: str, day: str) -> dict[str, Any] | None:
    """The standup before this day, for continuity: the story picks up
    where it left off ("the rename started on Tuesday is done")."""
    rows = store.query(
        "SELECT * FROM standups_mutual WHERE project = ? AND COALESCE(NULLIF(for_date, ''), created_date) < ? "
        "ORDER BY COALESCE(NULLIF(for_date, ''), created_date) DESC LIMIT 1", (project, day))
    if not rows:
        return None
    r = rows[0]
    return {"date": str(r.get("for_date") or r.get("created_date") or ""), "summary": str(r.get("l1") or "")}


def instructions(repo_root: Path) -> str:
    """How to write it: the contract parts, bodies only, in order."""
    out = []
    for name in PARTS:
        try:
            text = (repo_root / "prompts" / "contract" / name).read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(frontmatter.body_of(text).strip())
    return "\n\n".join(out)
