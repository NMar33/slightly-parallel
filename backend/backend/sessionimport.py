"""Import a session nothing recorded, from the tool's own log.

The hooks record a chat as it happens (scripts/hooks). When they did not —
the tool was not connected in that folder, or its hooks did not run — the
tool still keeps its own log: Claude Code in ``~/.claude/projects/<folder>/
<session>.jsonl``, Codex in ``~/.codex/sessions/<y>/<m>/<d>/rollout-*.jsonl``.
capturewatch.py finds those sessions; this module reads one into a chat,
in the same format the hook writes, under the same agent name the hook
would have used, with the times the messages were written.

It only writes the chat. A command in an old message (#task, #vision …) is
not carried out, no standup is asked about, nothing in the ledgers changes.
A session already recorded, or still active in the last hour, is skipped.

The logs are the tools' own, undocumented formats; they change between
versions. What cannot be read is skipped and said so, never guessed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import capturewatch
from .db import ViewStore
from .file_safety import atomic_write, atomic_write_json
from .hookshared import (
    NOT_OPERATOR, TRANSCRIPT_NOISE, codex_home, escape_content, is_human_prompt, local_iso, session_key, yymm_dd,
)

#: A session with a message in the last hour may still be going on: the hook
#: may yet record it, and an import now would race it.
ACTIVE_SECONDS = 3600

#: What Codex adds to the person's side itself, part by part: context in
#: tags, the AGENTS.md it read, the frame around an attached image.
_CODEX_OWN = ("<environment_context", "<user_instructions", "<image", "</image>", "# AGENTS.md instructions")


def _codex_person(content: Any) -> str:
    """The person's own words in a Codex user message. Codex sends a message
    in parts and adds its own among them; they are left out one by one. A
    message was dropped whole when it began with one of them: every message
    with an attached image (``<image …>`` comes first), and every message the
    person began with ``<``."""
    if not isinstance(content, list):
        return _text(content, ("input_text",))
    return "\n".join(
        str(p.get("text")) for p in content
        if isinstance(p, dict) and p.get("type") == "input_text" and p.get("text")
        and not str(p.get("text")).lstrip().startswith(_CODEX_OWN))


def _text(content: Any, kinds: tuple[str, ...]) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(p.get("text") or "") for p in content
                         if isinstance(p, dict) and p.get("type") in kinds and p.get("text"))
    return ""


def claude_turns(path: Path) -> list[dict[str, str]]:
    """The person's messages and the last reply to each, from a Claude Code
    transcript. Tool results, the harness's notes, helper agents and the
    compact summary are not the person; the reply is the turn's last text,
    as the hook records it."""
    turns: list[dict[str, str]] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain") or rec.get("isCompactSummary"):
                continue
            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            if rec.get("type") == "user" and not rec.get("isMeta") and is_human_prompt(rec):
                text = _text(msg.get("content"), ("text",)).strip()
                if not text or text.startswith(NOT_OPERATOR + TRANSCRIPT_NOISE):
                    continue
                turns.append({"user": text, "at": local_iso(rec.get("timestamp")), "agent": "", "end": ""})
            elif rec.get("type") == "assistant" and turns:
                text = _text(msg.get("content"), ("text",)).strip()
                if text:
                    turns[-1]["agent"], turns[-1]["end"] = text, local_iso(rec.get("timestamp"))
    return turns


def codex_turns(path: Path) -> list[dict[str, str]]:
    """The same from a Codex rollout: the person's messages, and the last
    thing the agent said in each turn (its final answer)."""
    turns: list[dict[str, str]] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue  # "null", "[]": a line that is JSON and no record
            pl = rec.get("payload")
            if rec.get("type") != "response_item" or not isinstance(pl, dict) or pl.get("type") != "message":
                continue
            if pl.get("role") == "user":
                text = _codex_person(pl.get("content")).strip()
                if not text:
                    continue
                turns.append({"user": text, "at": local_iso(rec.get("timestamp")), "agent": "", "end": ""})
            elif pl.get("role") == "assistant" and turns:
                text = _text(pl.get("content"), ("output_text",)).strip()
                if text:
                    turns[-1]["agent"], turns[-1]["end"] = text, local_iso(rec.get("timestamp"))
    return turns


_READERS = {"claude": claude_turns, "codex": codex_turns}
_TOOL = {"claude": "claude-code", "codex": "codex"}
_TOOL_NAME = {"claude": "Claude Code", "codex": "Codex"}


def agent_name(tool: str, session: str) -> str:
    """The name the hook gives this session's agent."""
    return f"cc-{session[:8]}" if tool == "claude" else f"codex-{session_key('codex', session)}"


def candidates(store: ViewStore, project: str, tool: str, claude_root: Path | None = None,
               codex_root: Path | None = None, now: float | None = None) -> list[dict[str, Any]]:
    """The sessions of this project and tool that can be imported: not
    recorded, not active in the last hour, with something the person wrote."""
    now = now or time.time()
    croot = claude_root or Path.home() / ".claude" / "projects"
    xroot = codex_root or codex_home() / "sessions"
    out = []
    for r in capturewatch.unrecorded(store, croot, xroot, now):
        if r["project"] != project or r["tool"] != tool or now - r["last_at"] < ACTIVE_SECONDS:
            continue
        try:
            turns = _READERS[tool](Path(r["file"]))
        except OSError:
            continue
        if not turns:
            continue
        out.append({**r, "turns": turns, "agent_id": agent_name(tool, r["session"])})
    return out


def preview(store: ViewStore, project: str, tool: str, **roots: Any) -> list[dict[str, Any]]:
    """What an import would write: one row per session, no file touched."""
    return [{"session": c["session"], "agent_id": c["agent_id"], "turns": len(c["turns"]),
             "started": c["turns"][0]["at"], "ended": c["turns"][-1]["end"] or c["turns"][-1]["at"],
             "first": c["turns"][0]["user"][:160]} for c in candidates(store, project, tool, **roots)]


def _write(store: ViewStore, project: str, tool: str, c: dict[str, Any]) -> str:
    folder = store.data_root / "projects" / project / "chats" / c["agent_id"]
    if (folder / "meta.json").exists() or (folder / "chat.md").exists():
        return "recorded already"
    turns = c["turns"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    parts = [f"# Chat log — {c['agent_id']}\n",
             f"*Started {turns[0]['at']}. Imported on {now} from {_TOOL_NAME[tool]}'s own session log: "
             f"these turns were not recorded while they happened.*\n\n---\n"]
    for n, t in enumerate(turns, start=1):
        parts.append(f"\n## Turn {n} · {t['at']}\n**User**: {escape_content(t['user'].rstrip())}\n")
        parts.append(f"**Agent**: {escape_content((t['agent'] or '(no reply in the log)').rstrip())}\n")
    first = turns[0]["at"] or now
    meta = {
        "agent_id": c["agent_id"], "agent_name": c["agent_id"], "project": project,
        "created_date": yymm_dd(datetime.fromisoformat(first)),
        "message_count": len(turns), "schema_version": 2,
        # Not "hooks": this chat came from the tool's log afterwards.
        "capture": "import", "imported_at": now, "imported_from": str(c["file"]),
        "tool": _TOOL[tool], "session_ref": c["session"], "cwd": str(c["cwd"]),
        "last_active": turns[-1]["end"] or turns[-1]["at"],
    }
    folder.mkdir(parents=True, exist_ok=True)
    atomic_write(folder / "chat.md", "".join(parts))
    atomic_write_json(folder / "meta.json", meta)
    return ""


def run(store: ViewStore, project: str, tool: str, sessions: list[str] | None = None, **roots: Any) -> dict[str, Any]:
    """Import the sessions (all that can be, or the ids given). Answers what
    was written and what was skipped, with why."""
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for c in candidates(store, project, tool, **roots):
        if sessions and c["session"] not in sessions:
            continue
        why = _write(store, project, tool, c)
        if why:
            skipped.append({"session": c["session"], "why": why})
        else:
            imported.append({"session": c["session"], "agent_id": c["agent_id"], "turns": len(c["turns"])})
    if imported:
        capturewatch._cache.clear()
        store.rebuild()
    return {"imported": imported, "skipped": skipped}
