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
from typing import Any, Callable

from . import capturewatch
from .db import ViewStore
from .file_safety import atomic_write, atomic_write_json
from .hookshared import (
    HISTORY_SLACK_S, NOT_OPERATOR, TRANSCRIPT_NOISE, assign_turns, codex_home, epoch_of, escape_content,
    helper_starts, is_compact, is_human_prompt, local_iso, session_key, usage_line_claude, usage_records_claude,
    usage_records_codex, yymm_dd,
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


def _claude_prompt(rec: dict[str, Any]) -> str:
    """The person's message in one Claude Code record ("" when it is none):
    tool results, the harness's notes, helper agents and the compact
    summary are not the person."""
    if rec.get("isSidechain") or rec.get("isCompactSummary"):
        return ""
    if rec.get("type") != "user" or rec.get("isMeta") or not is_human_prompt(rec):
        return ""
    msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
    text = _text(msg.get("content"), ("text",)).strip()
    return "" if not text or text.startswith(NOT_OPERATOR + TRANSCRIPT_NOISE) else text


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
            if rec.get("type") == "user":
                text = _claude_prompt(rec)
                if not text:
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


def _jsonl(path: Path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def _prompt_turns(times: list[float | None]) -> tuple[list[list[Any]], float | None]:
    """The turn history of an imported chat (hookshared.assign_turns): each
    prompt begins a turn; what was written more than a minute before the
    first one is earlier history, as the hook counts it."""
    turns = [[n, t, False] for n, t in enumerate(times, start=1)]
    first = next((t for t in times if t is not None), None)
    return turns, (first - HISTORY_SLACK_S if first is not None else None)


_Parts = tuple[list[float | None], list[str], Callable[..., list[dict[str, Any]]]]


def claude_usage_parts(path: Path, session: str) -> _Parts:
    """(the transcript's human prompts, as epochs; their texts; a function
    that gives its usage lines their turns): claude_usage in two steps, so
    the backfill (usagebackfill.py) can number the turns by the chat's own
    chat.md. The function takes (turns, cutoff, default) as
    hookshared.assign_turns."""
    lines: dict[str, dict[str, Any]] = {}
    starts: dict[str, dict[str, Any]] = {}
    compacts: list[float] = []
    prompts: list[float | None] = []
    texts: list[str] = []
    for rec in _jsonl(path):
        said = _claude_prompt(rec) if rec.get("type") == "user" else ""
        if said:
            prompts.append(epoch_of(rec.get("timestamp")))
            texts.append(said)
            continue
        try:
            if is_compact(rec):
                at = epoch_of(rec.get("timestamp"))
                if at is not None:
                    compacts.append(at)
            line = usage_line_claude(rec, session)
            if line is not None:
                lines[line["id"]] = line
            for call in helper_starts(rec):
                starts.setdefault(call, {"t": epoch_of(rec.get("timestamp")), "parent": ""})
        except Exception:  # noqa: BLE001 — one bad record never stops the import
            continue
    helper_lines: list[dict[str, Any]] = []
    base = path.with_suffix("") / "subagents"
    try:
        helpers = sorted(base.rglob("*.jsonl")) if base.is_dir() else []
    except OSError:
        helpers = []
    for f in helpers:
        try:
            call = str(json.loads(f.with_name(f.stem + ".meta.json").read_text(encoding="utf-8")).get("toolUseId") or "")
        except (OSError, ValueError, AttributeError):
            call = ""
        try:
            recs = [r for r in _jsonl(f) if r.get("type") == "assistant"]
        except OSError:
            continue
        helper_lines.extend({**line, "tool_use": call}
                            for line in usage_records_claude(recs, session, helper=f.stem.removeprefix("agent-") or f.stem))
        for rec in recs:
            for inner in helper_starts(rec):
                starts.setdefault(inner, {"t": epoch_of(rec.get("timestamp")), "parent": call})

    def assign(turns: list[list[Any]], cutoff: float | None, default: int) -> list[dict[str, Any]]:
        out, _left = assign_turns(list(lines.values()) + helper_lines, turns, starts=dict(starts),
                                  compacts=compacts, cutoff=cutoff, default=default)
        return out
    return prompts, texts, assign


def claude_usage(path: Path, session: str) -> list[dict[str, Any]]:
    """The usage lines of a Claude Code transcript, each with the turn the
    import gives it (the same prompts claude_turns counts): one per API
    message, the copies of another session skipped (hookshared). The helper
    agents' transcripts beside it (``<session>/subagents``) go to the turn
    whose Agent call started them, else to the turn they began in. The turns
    are given by the hook's own rule (hookshared.assign_turns), so a chat
    imported and the same chat recorded hold the same usage."""
    prompts, _texts, assign = claude_usage_parts(path, session)
    if not prompts:
        return []
    turns, cutoff = _prompt_turns(prompts)
    return assign(turns, cutoff, len(turns))


def codex_usage_parts(path: Path, session: str = "") -> _Parts:
    """codex_usage in two steps, as claude_usage_parts."""
    recs: list[dict[str, Any]] = []
    prompts: list[float | None] = []
    texts: list[str] = []
    for rec in _jsonl(path):
        pl = rec.get("payload")
        if not isinstance(pl, dict):
            continue
        if rec.get("type") == "response_item" and pl.get("type") == "message" and pl.get("role") == "user":
            said = _codex_person(pl.get("content")).strip()
            if said:
                prompts.append(epoch_of(rec.get("timestamp")))
                texts.append(said)
            continue
        recs.append(rec)
    lines = usage_records_codex(recs)

    def assign(turns: list[list[Any]], cutoff: float | None, default: int) -> list[dict[str, Any]]:
        out, _left = assign_turns(list(lines), turns, cutoff=cutoff, default=default)
        return out
    return prompts, texts, assign


def codex_usage(path: Path, session: str = "") -> list[dict[str, Any]]:
    """The usage lines of a Codex rollout, each with the turn the import
    gives it (the same messages codex_turns counts), by the hook's rule."""
    prompts, _texts, assign = codex_usage_parts(path, session)
    if not prompts:
        return []
    turns, cutoff = _prompt_turns(prompts)
    return assign(turns, cutoff, len(turns))


_READERS = {"claude": claude_turns, "codex": codex_turns}
_USAGE = {"claude": claude_usage, "codex": codex_usage}
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
    # The tokens of each turn, from the same log (the Usage page). A log
    # whose usage cannot be read leaves the chat without it.
    try:
        usage = _USAGE[tool](Path(c["file"]), str(c["session"]))
    except (OSError, ValueError):
        usage = []
    if usage:
        atomic_write(folder / "usage.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in usage))
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
