#!/usr/bin/env python3
"""Claude Code adapter — automatic verbatim chat capture for Slightly Parallel.

Installed by the Setup page into a project's ``.claude/settings.local.json``
as two hook entries invoking this script:

- ``UserPromptSubmit`` — stdin JSON carries the user's literal prompt; the
  turn opens with it. Due signals (standup / decision hint / contract
  refresh) are printed to stdout, which Claude Code injects into the
  model's context.
- ``Stop`` — the response is finished; the assistant's final message
  arrives in the payload (``last_assistant_message``) and completes the
  turn verbatim. Builds without that field fall back to the transcript —
  only text written after the last human prompt counts — and when there
  is none the turn closes with a visible gap rather than the previous
  answer.

The model itself never logs anything.

Codex's hooks send the same two events in the same shape (stdin JSON with
``prompt`` on UserPromptSubmit and ``last_assistant_message`` on Stop), so
the same script serves it: ``--tool codex`` names the agent ``codex-…``
and records the origin as Codex. Codex documents stdout as JSON control
output, not injected context, so with ``--tool codex`` nothing is printed;
identity reaches the model through the breadcrumb (``GET /api/whoami``)
and the MCP server instead.

Usage (as written by Setup):
    claude-code-capture.py --project <code> --data-root <path> [--tool codex]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import TurnCapture, _turntimes, format_signals, record_failure, shared, usage_only  # noqa: E402


_PREFIX = {"claude-code": "cc", "codex": "codex"}


def agent_name(session_id: str, tool: str = "claude-code") -> str:
    return f"{_PREFIX.get(tool, 'cc')}-{shared.session_key(tool, session_id)}"


# Harness-generated payloads (background-task notifications, command echo, a
# helper agent's report handed back into the chat) arrive through the same
# prompt event but are not the user speaking — their #tags must never act as
# commands. The one list of them: backend/backend/hookshared.py.
_SYSTEM_PREFIXES = shared.NOT_OPERATOR


def is_system_payload(prompt: str) -> bool:
    return prompt.lstrip().startswith(_SYSTEM_PREFIXES)


_is_human_prompt = shared.is_human_prompt


#: The tools whose results facts.jsonl counts apart; ``mcp__*`` is ``MCP``,
#: the rest ``other``. ``Task`` is the Agent tool's older name.
_FACT_TOOLS = ("Read", "Bash", "Grep", "Glob", "Edit", "Write", "Agent", "WebFetch", "WebSearch")


def _chars(content) -> tuple[int, int]:
    """(characters, images) of a message content: text, or a list of blocks."""
    if isinstance(content, str):
        return len(content), 0
    n = images = 0
    for p in content if isinstance(content, list) else ():
        if not isinstance(p, dict):
            continue
        if p.get("type") == "image":
            images += 1
        elif isinstance(p.get("text"), str):
            n += len(p["text"])
        elif isinstance(p.get("content"), (str, list)):
            more, pics = _chars(p["content"])
            n, images = n + more, images + pics
    return n, images


class Facts:
    """What a stretch of the transcript added to the chat, for facts.jsonl:
    characters by kind (``operator``, ``notices``, ``agent_text``,
    ``agent_tool_calls``, ``thinking``, ``result_<tool>``), ``images``
    counted, and the tool calls by name. Counted while Segment reads, so the
    transcript is read once; never reset at a prompt."""

    def __init__(self) -> None:
        self.appended: dict[str, int] = {}
        self.tools: dict[str, int] = {}
        self._calls: dict[str, str] = {}    # tool_use id → the bucket of its result

    def _add(self, kind: str, n: int) -> None:
        if n:
            self.appended[kind] = self.appended.get(kind, 0) + n

    @staticmethod
    def _bucket(name: str) -> str:
        if name.startswith("mcp__"):
            return "MCP"
        if name == "Task":
            return "Agent"
        return name if name in _FACT_TOOLS else "other"

    def take(self, rec: dict) -> None:
        kind = rec.get("type")
        if kind == "attachment":
            # What the model reads of an attachment is its rendered text
            # (system reminders, a prompt hook's output); a Stop hook's
            # message has none.
            for r in rec.get("rendered") or []:
                if isinstance(r, dict):
                    n, pics = _chars(r.get("content"))
                    self._add("notices", n)
                    self._add("images", pics)
            return
        content = (rec.get("message") or {}).get("content")
        if kind == "assistant":
            for p in content if isinstance(content, list) else ():
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    self._add("agent_text", len(str(p.get("text") or "")))
                elif t == "thinking":
                    self._add("thinking", len(str(p.get("thinking") or "")))
                elif t == "tool_use":
                    name = str(p.get("name") or "")
                    self.tools[name] = self.tools.get(name, 0) + 1
                    self._calls[str(p.get("id") or "")] = self._bucket(name)
                    self._add("agent_tool_calls", len(json.dumps(p.get("input"), ensure_ascii=False)))
            return
        if kind != "user":
            return
        aside = bool(rec.get("isMeta") or rec.get("isCompactSummary"))
        if isinstance(content, str):
            self._add("notices" if aside or is_system_payload(content) else "operator", len(content))
            return
        for p in content if isinstance(content, list) else ():
            if not isinstance(p, dict):
                continue
            t = p.get("type")
            if t == "tool_result":
                n, pics = _chars(p.get("content"))
                self._add("result_" + self._calls.get(str(p.get("tool_use_id") or ""), "other"), n)
                self._add("images", pics)
            elif t == "image":
                self._add("images", 1)
            elif t == "text":
                text = str(p.get("text") or "")
                self._add("notices" if aside or is_system_payload(text) else "operator", len(text))


class Segment:
    """What a stretch of the tool's JSONL transcript says, read once.

    ``text`` — this turn's answer: the last assistant message's text blocks
    joined (tool calls and thinking are not part of it) **written after the
    last human prompt**. Anchoring to the prompt is what keeps a turn from
    inheriting the previous answer: the transcript is flushed by another
    process, and on a Stop that lands before the flush (or a reply the tool
    never persisted) the newest text in the file is the *previous* turn's.
    Better an honest gap than a wrong reply. ``title`` — the last
    ``custom-title`` record, written when the user runs ``/rename`` or
    ``/branch <name>``. ``skills`` — the skills that ran in this turn:
    ``Skill`` calls after the last human prompt, and a ``/skill`` the person
    typed as that prompt. ``points`` — when each message and tool result was
    written (given ``tt``, the backend's turntimes.py), for the turn's times.
    ``usage`` — the API messages of the stretch, one per message id (the
    last record wins), from every prompt in it: an interrupted turn's
    tokens are read at the next Stop. ``starts`` — the Agent calls in it,
    by id, with their time: a helper's tokens go to the turn that started it.
    ``compacts`` — when the context was compacted (epoch seconds).
    ``from_top`` — this read began at the file's first byte.

    The stretch starts at ``pos`` bytes — where the previous Stop stopped
    (TurnCapture.transcript_pos) — so a long chat's transcript, tens of
    megabytes of it, is not read again at every answer; three readers each
    used to read all of it. ``read`` may be called again: it goes on from
    ``end``, which only ever stands after a whole line.
    """

    def __init__(self, transcript_path: str, pos: int = 0, tt=None) -> None:
        self.path, self.end, self.tt = transcript_path, max(0, int(pos)), tt
        self.text = ""
        self.title = ""
        self.skills: list[dict] = []
        self.touched: list[str] = []
        self.committed = False
        self.points: list = []
        # The turn's shell calls that may make a commit, with their times.
        self.calls = shared.CommitCalls()
        self.session_id = ""
        self.usage: dict[str, dict] = {}
        self.starts: dict[str, dict] = {}
        self.compacts: list[float] = []
        self.from_top = self.end == 0
        self.facts = Facts()
        # The last prompt in the stretch was the tool's own — a helper's
        # report, a background task's notification — not the operator's: the
        # reply after it continues the operator's last turn (no
        # UserPromptSubmit came for it, so no turn is pending).
        self.woken = False

    def usage_lines(self) -> list[dict]:
        return list(self.usage.values())

    def read(self) -> "Segment":
        try:
            with open(self.path, "rb") as fh:
                size = fh.seek(0, 2)
                if self.end > size:
                    self.end = 0        # another file under the old name
                if self.end:
                    fh.seek(self.end - 1)
                    if fh.read(1) != b"\n":
                        self.end = 0    # not where a line begins: trust nothing
                if self.end == 0:
                    self.from_top = True
                fh.seek(self.end)
                for raw in fh:
                    # A last line with no newline yet may still be written:
                    # it is read if it is whole, and read again next time.
                    if raw.endswith(b"\n"):
                        self.end += len(raw)
                    try:
                        rec = json.loads(raw.decode("utf-8", errors="replace"))
                    except ValueError:
                        continue
                    if isinstance(rec, dict):
                        try:
                            self._take(rec)
                        except Exception:  # noqa: BLE001 — a record of an unknown shape is skipped, never the turn
                            continue
        except OSError:
            pass
        return self

    def _take(self, rec: dict) -> None:
        try:
            self.facts.take(rec)
        except Exception:  # noqa: BLE001 — a count never costs the turn
            pass
        kind = rec.get("type")
        if self.tt is not None and kind in self.tt._ACTIVITY:
            at = self.tt._parse(rec.get("timestamp"))
            if at is not None:
                self.points.append(at)
        if kind == "custom-title":
            self.title = str(rec.get("customTitle") or "") or self.title
            return
        if kind == "assistant":
            # Usage is not reset at a prompt: records before it belong to an
            # earlier turn, and record_usage gives them that turn. A record it
            # cannot read costs its tokens, never the turn.
            try:
                line = shared.usage_line_claude(rec, self.session_id)
                if line is not None:
                    self.usage[line["id"]] = line
                for call in shared.helper_starts(rec):
                    self.starts.setdefault(call, {"t": shared.epoch_of(rec.get("timestamp")), "parent": ""})
            except Exception:  # noqa: BLE001
                pass
        elif shared.is_compact(rec):
            at = shared.epoch_of(rec.get("timestamp"))
            if at is not None and at not in self.compacts:
                self.compacts.append(at)
        if _is_human_prompt(rec):
            # Everything before this prompt belongs to an earlier turn.
            self.text, self.skills, self.touched = "", [], []
            self.committed = False
            self.calls = shared.CommitCalls()
            content = (rec.get("message") or {}).get("content")
            said = content if isinstance(content, str) else "\n".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
            self.woken = is_system_payload(said)
        elif kind == "assistant":
            content = (rec.get("message") or {}).get("content") or []
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            text = "\n".join(t for t in parts if t).strip()
            if text:
                self.text = text
        for path in shared.touched_files(rec):
            if path not in self.touched:
                self.touched.append(path)
        if shared.ran_commit(rec):
            self.committed = True
        self.calls.take(rec)
        uses = shared.skill_uses(rec)
        if uses:
            at = _local_iso(rec.get("timestamp") or "")
            self.skills.extend({"skill": name, "how": how, "at": at} for name, how in uses)


_HELPERS_POS = "helpers.json"
_HELPERS_FRESH_S = 30 * 60


class Helpers:
    """What this session's helper agents did since the last look.

    Claude Code writes each helper's transcript beside the session's, under
    ``<session>/subagents/`` (nested for workflows); its Edit and Write
    calls never reach the main transcript. Each file is read on from where
    the previous Stop left it (``helpers.json`` in the chat folder), so a
    helper still running at one Stop is counted at the next. ``save`` keeps
    the new positions — only after the usage read is kept, so a failed write
    is read again. Never raises.

    ``touched`` — the files they changed; ``usage`` — their API messages,
    each with ``helper`` (its id) and ``tool_use`` (the Agent call that
    started it, from ``<agent>.meta.json`` beside its transcript);
    ``starts`` — the Agent calls made inside a helper, with that helper's
    call as ``parent``; ``replay`` — a file was read again from its start
    (no positions kept, a file that shrank): its ids are looked for in all
    of usage.jsonl.
    """

    def __init__(self, transcript_path: str, folder: Path, session_id: str = "") -> None:
        self.touched: list[str] = []
        self.usage: list[dict] = []
        self.starts: dict[str, dict] = {}
        self.replay = False
        self._pos_path = folder / _HELPERS_POS
        self._pos: dict | None = None
        if not transcript_path:
            return
        base = Path(transcript_path).with_suffix("") / "subagents"
        if not base.is_dir():
            return
        try:
            pos = json.loads(self._pos_path.read_text(encoding="utf-8"))
            if not isinstance(pos, dict):
                pos = {}
            first = False
        except (OSError, ValueError):
            pos, first = {}, True
        try:
            files = sorted(base.rglob("*.jsonl"))
        except OSError:
            return
        for f in files:
            self._read(f, pos, first, session_id)
        self._pos = pos

    def _read(self, f: Path, pos: dict, first: bool, session_id: str) -> None:
        key = str(f)
        start = int(pos.get(key) or 0) if isinstance(pos.get(key), int) else 0
        # The first look at a session already running: a helper finished long
        # before is not this turn's work — its edits are not counted. Its
        # tokens are read (the cutoff in record_usage keeps out what is older
        # than the chat), so none is lost.
        stale = False
        if first and key not in pos:
            try:
                stale = time.time() - f.stat().st_mtime > _HELPERS_FRESH_S
            except OSError:
                return
        try:
            with open(f, "rb") as fh:
                size = fh.seek(0, 2)
                if start > size:
                    start = 0        # another file under the old name
                if start == 0:
                    self.replay = self.replay or first or key in pos
                fh.seek(start)
                end = start
                recs: list[dict] = []
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break        # a line still being written: read it next time
                    end += len(raw)
                    try:
                        rec = json.loads(raw.decode("utf-8", errors="replace"))
                    except ValueError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if not stale:
                        try:
                            for path in shared.touched_files(rec):
                                if path not in self.touched:
                                    self.touched.append(path)
                        except Exception:  # noqa: BLE001 — a record of an unknown shape
                            pass
                    if rec.get("type") == "assistant":
                        recs.append(rec)
                pos[key] = end
        except OSError:
            return
        if recs:
            self._take(f, recs, session_id)

    def _take(self, path: Path, recs: list[dict], session_id: str) -> None:
        """A helper transcript's usage lines, each naming the helper and the
        Agent call that started it; the calls it made itself."""
        helper = path.stem.removeprefix("agent-") or path.stem
        try:
            call = str(json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8")).get("toolUseId") or "")
        except (OSError, ValueError, AttributeError):
            call = ""
        self.usage.extend({**line, "tool_use": call}
                          for line in shared.usage_records_claude(recs, session_id, helper=helper))
        for rec in recs:
            try:
                for inner in shared.helper_starts(rec):
                    self.starts.setdefault(inner, {"t": shared.epoch_of(rec.get("timestamp")), "parent": call})
            except Exception:  # noqa: BLE001
                continue

    def save(self) -> None:
        if self._pos is None:
            return
        # A temp name of this process's own: the Stop and SessionEnd hooks of
        # one chat can save at once, and one fixed name let the second replace
        # move the first's half-written file, or find none.
        tmp = self._pos_path.with_name(f"{self._pos_path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(self._pos), encoding="utf-8")
            os.replace(tmp, self._pos_path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass


def helper_touched(transcript_path: str, folder: Path, usage: list[dict] | None = None,
                   session_id: str = "") -> list[str]:
    """The files this session's helper agents changed since the last look
    (Helpers, its positions kept at once); ``usage`` receives their API
    messages."""
    got = Helpers(transcript_path, folder, session_id)
    got.save()
    if usage is not None:
        usage.extend(got.usage)
    return got.touched


def read_transcript(transcript_path: str) -> tuple[str, str]:
    """(this turn's assistant text, custom chat title) from a whole transcript."""
    seg = Segment(transcript_path).read()
    return seg.text, seg.title


# The transcript is appended by Claude Code around the same moment the Stop
# hook fires; a read that lands first sees no answer yet. A few short
# re-reads — of what was added since, not of the file — cover that window
# without holding the user's prompt hostage.
_STOP_RETRIES = 4
_STOP_RETRY_S = 0.25


# Commands built into Claude Code are not skills (hookshared.BUILTIN_COMMANDS).
_BUILTINS = shared.BUILTIN_COMMANDS
_local_iso = shared.local_iso


def skills_in_turn(transcript_path: str) -> list[dict]:
    """The skills that ran in the last turn of a whole transcript."""
    return Segment(transcript_path).read().skills


# This process's parents, nearest first: the MCP server finds its own chat by
# the tool process the two share (hookshared.ancestors).
ancestors = shared.ancestors


def write_breadcrumb(data_root: str, project: str, session_id: str, cwd: str,
                     tool: str = "claude-code", agent_id: str = "") -> None:
    """Per-cwd identity file for local MCP/CLI clients (GET /api/whoami).

    The hook is the one process that knows which session runs in which
    directory; leaving that fact on disk lets tools stamp agent_id and
    project themselves instead of asking the model to copy them.

    Two files: ``<cwd>.json`` is the newest chat in the folder, and
    ``<cwd>/<session>.json`` is this chat with the processes above this hook.
    When two chats share a folder, an MCP server finds its own by the
    process they have in common; the newest one is the fallback. Never
    breaks the user's session.
    """
    if not cwd:
        return
    try:
        import os
        import time as _time
        sessions = Path(data_root) / ".sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        digest = shared.folder_digest(cwd)
        path = sessions / f"{digest}.json"
        # Two chats in one folder write this file at once: each its own temp.
        tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
        crumb = {
            "agent_id": agent_id or agent_name(session_id, tool), "project": project,
            "session_id": session_id, "cwd": cwd, "at": _time.time(),
        }
        try:
            # This chat's own file, and a sweep of the ones a week old.
            mine = sessions / digest
            mine.mkdir(exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:80] or "session"
            own = mine / f"{safe}.json"
            own_tmp = own.with_suffix(f".json.{os.getpid()}.tmp")
            own_tmp.write_text(json.dumps({**crumb, "pids": ancestors()}), encoding="utf-8")
            shared.replace_file(own_tmp, own)
            for old in mine.glob("*.json"):
                if _time.time() - old.stat().st_mtime > 7 * 86400:
                    old.unlink()
        except OSError:
            pass
        tmp.write_text(json.dumps(crumb), encoding="utf-8")
        shared.replace_file(tmp, path)
    except OSError:
        pass


def codex_usage(payload: dict, session_id: str, since: float | None = None) -> tuple[list[dict], dict | None]:
    """The usage lines and the plan-limits reading of the Codex turn a Stop
    ends, from the session file (rollout-…-<thread>.jsonl): the payload's
    transcript when it names one, else found by the thread id. ``since``:
    the newest call already kept (TurnCapture.codex_read_at) — every call
    written after it is read, of whatever turn, so one written after its
    turn's Stop is kept at the next. Without it (the chat's first Stop),
    the turn and the one before it."""
    given = str(payload.get("transcript_path") or "")
    rollout = Path(given) if given and Path(given).name.startswith("rollout-") and Path(given).is_file() \
        else shared.codex_rollout(session_id)
    if rollout is None:
        return [], None
    if since is not None:
        return shared.codex_turn_usage(rollout, since=since)
    return shared.codex_turn_usage(rollout, str(payload.get("turn_id") or ""), back=1)


#: Events that only record the tokens read so far: the session ended, or the
#: turn ended on an API error (Stop does not come then). No turn closes, no
#: read position moves: the next Stop reads the same records, and the ids
#: already kept are skipped.
_USAGE_ONLY_EVENTS = ("SessionEnd", "StopFailure")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--tool", choices=sorted(_PREFIX), default="claude-code")
    args = ap.parse_args()

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # malformed event — never break the user's session
    if not isinstance(payload, dict):
        return 0  # not an event at all

    event = str(payload.get("hook_event_name") or "")
    session_id = str(payload.get("session_id") or "")
    agent = agent_name(session_id, args.tool)
    # Where a notice is seen: on UserPromptSubmit stdout joins the agent's
    # context; on Stop Claude Code ignores stdout and shows stderr.
    say = sys.stderr if event == "Stop" else sys.stdout

    def tell(text: str) -> None:
        """A notice for the agent on a prompt. Claude Code reads plain stdout;
        Codex reads only JSON, as the prompt's additional context, and drops
        plain text without a word (checked with Codex 0.163)."""
        if args.tool == "codex" and event == "UserPromptSubmit":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
        else:
            print(text, file=say)
    if not Path(args.data_root).is_dir():
        # Never build a data root from here: an unmounted drive or a moved
        # folder would get a stray tree. Say so, where it is read.
        tell(f"[slightly-parallel] capture failed: the data root {args.data_root} does not exist — tell the user.")
        return 0

    try:
        cap = TurnCapture(args.data_root, args.project, agent)
        if event == "UserPromptSubmit":
            prompt = str(payload.get("prompt") or "")
            if is_system_payload(prompt):
                return 0
            cwd = str(payload.get("cwd") or "")
            cap.note_origin(args.tool, session_id, cwd)
            write_breadcrumb(args.data_root, args.project, session_id, cwd, tool=args.tool)
            if args.tool == "claude-code" and usage_only(prompt):
                # #usage, #usage-on, #usage-off alone: answered here, shown to
                # the user only, and the prompt never reaches the model
                # (UserPromptSubmit decision "block": its reason is shown to
                # the user and not added to context). The exchange is a turn
                # of the chat, so the chat viewer has it too.
                answer = cap.answer_usage(prompt)
                print(json.dumps({"decision": "block", "reason": answer,
                                  "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "suppressOriginalPrompt": True}}, ensure_ascii=False))
                return 0
            signals = cap.open_turn(prompt)
            notice = format_signals(signals, args.tool)
            if notice:
                tell(notice)
        elif event == "Stop" or event in _USAGE_ONLY_EVENTS:
            # The payload carries the reply itself; the transcript is not
            # guaranteed to hold the final message at Stop time (the docs say
            # so, and 2.1.251 dropped the text record of three replies in one
            # session). Read the payload first; the transcript is the fallback
            # for builds that predate the field, and the source of the title,
            # the skills and the times — all from one read of what was
            # written since the previous Stop.
            stop = event == "Stop"
            given = str(payload.get("last_assistant_message") or "").strip() if stop else ""
            transcript_path = str(payload.get("transcript_path") or "")
            seg = Segment(transcript_path, cap.transcript_pos(transcript_path), _turntimes() if stop else None)
            seg.session_id = session_id
            if transcript_path:
                seg.read()
                tries = 0
                while stop and not given and not seg.text and tries < _STOP_RETRIES:
                    time.sleep(_STOP_RETRY_S)
                    seg.read()
                    tries += 1
            helpers = Helpers(transcript_path, cap.folder, session_id) if transcript_path and args.tool != "codex" else None
            # Tokens of the API messages since the last Stop (usage.jsonl),
            # first: the turn number is the pending one, and no read position
            # moves until they are kept.
            if args.tool == "codex":
                lines, limits = codex_usage(payload, session_id, cap.codex_read_at())
                shared.limits_append(args.data_root, limits)
                turn, _ = cap.record_usage(lines)
                if not cap.usage_failed:
                    cap.note_codex_read(lines)
            else:
                turn, _ = cap.record_usage(
                    seg.usage_lines() + (helpers.usage if helpers else []),
                    {**seg.starts, **(helpers.starts if helpers else {})}, compacts=seg.compacts,
                    whole=bool(transcript_path) and (seg.from_top or bool(helpers and helpers.replay)))
            if not stop:
                return 0
            kept = not cap.usage_failed
            if helpers is not None and kept:
                helpers.save()
            text = given or seg.text
            # What this build hands us on Stop — keys only, never values — so
            # a gap can be diagnosed from meta.json instead of guessed at.
            cap.note_stop(sorted(str(k) for k in payload), found_text=bool(text),
                          transcript=(transcript_path, seg.end) if transcript_path and kept else None)
            cap.record_skills(seg.skills)
            helper_paths = helpers.touched if helpers else []
            cap.complete_turn(text, close_if_missing=True, transcript=transcript_path or None,
                              continuation=seg.woken,
                              points=seg.points if transcript_path else None,
                              touched=(seg.touched + [p for p in helper_paths if p not in seg.touched])
                              if transcript_path else None,
                              committed=seg.committed if transcript_path else None,
                              commit_calls=seg.calls.finish(shared.local_iso(datetime.now().astimezone().isoformat()))
                              if transcript_path else None)
            cap.note_chat_title(seg.title)
            if args.tool == "claude-code":
                # The line under the reply, then a usage warning on its own
                # line: Stop's JSON systemMessage is shown to the user (stdout
                # carries nothing else on Stop). A Stop that comes again for
                # the turn (stop_hook_active) shows each once.
                parts = []
                if cap.usage_shown():
                    line = cap.usage_line(turn)
                    if line and cap.line_due(turn):
                        parts.append(line)
                warned = cap.usage_warning(turn) if cap.usage_warned() else None
                if warned:
                    parts.append(warned[1])
                if parts:
                    print(json.dumps({"systemMessage": "\n".join(parts)}, ensure_ascii=False))
                facts = seg.facts
                if transcript_path and (facts.appended or facts.tools or warned):
                    cap.record_facts(turn, facts.appended, facts.tools, [warned[0]] if warned else [])
    except Exception as exc:  # noqa: BLE001 — capture must never take down the session it observes
        # Exit 0 keeps the session alive; the notice goes where it is shown
        # (stdout on a prompt, stderr on Stop), so the loss is named instead
        # of silent — and it is kept for the dashboard's warning.
        tell(f"[slightly-parallel] capture failed: {type(exc).__name__}: {exc} — this turn was not recorded; tell the user.")
        record_failure(args.data_root, args.project, agent, args.tool, f"{event}: {type(exc).__name__}: {exc}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
