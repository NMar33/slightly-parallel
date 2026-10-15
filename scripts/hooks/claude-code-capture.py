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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture import TurnCapture, _turntimes, format_signals, record_failure, shared  # noqa: E402


_PREFIX = {"claude-code": "cc", "codex": "codex"}


def agent_name(session_id: str, tool: str = "claude-code") -> str:
    return f"{_PREFIX.get(tool, 'cc')}-{(session_id or 'unknown')[:8]}"


# Harness-generated payloads (background-task notifications, command echo, a
# helper agent's report handed back into the chat) arrive through the same
# prompt event but are not the user speaking — their #tags must never act as
# commands. The one list of them: backend/backend/hookshared.py.
_SYSTEM_PREFIXES = shared.NOT_OPERATOR


def is_system_payload(prompt: str) -> bool:
    return prompt.lstrip().startswith(_SYSTEM_PREFIXES)


_is_human_prompt = shared.is_human_prompt


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
        self.points: list = []

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
                        self._take(rec)
        except OSError:
            pass
        return self

    def _take(self, rec: dict) -> None:
        kind = rec.get("type")
        if self.tt is not None and kind in self.tt._ACTIVITY:
            at = self.tt._parse(rec.get("timestamp"))
            if at is not None:
                self.points.append(at)
        if kind == "custom-title":
            self.title = str(rec.get("customTitle") or "") or self.title
            return
        if _is_human_prompt(rec):
            # Everything before this prompt belongs to an earlier turn.
            self.text, self.skills, self.touched = "", [], []
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
        uses = shared.skill_uses(rec)
        if uses:
            at = _local_iso(rec.get("timestamp") or "")
            self.skills.extend({"skill": name, "how": how, "at": at} for name, how in uses)


_HELPERS_POS = "helpers.json"
_HELPERS_FRESH_S = 30 * 60


def helper_touched(transcript_path: str, folder: Path) -> list[str]:
    """The files this session's helper agents changed since the last look.

    Claude Code writes each helper's transcript beside the session's, under
    ``<session>/subagents/`` (nested for workflows); its Edit and Write
    calls never reach the main transcript. Each file is read on from where
    the previous Stop left it (``helpers.json`` in the chat folder), so a
    helper still running at one Stop is counted at the next. Never raises.
    """
    if not transcript_path:
        return []
    base = Path(transcript_path).with_suffix("") / "subagents"
    if not base.is_dir():
        return []
    pos_path = folder / _HELPERS_POS
    try:
        pos = json.loads(pos_path.read_text(encoding="utf-8"))
        if not isinstance(pos, dict):
            pos = {}
        first = False
    except (OSError, ValueError):
        pos, first = {}, True
    out: list[str] = []
    try:
        files = sorted(base.rglob("*.jsonl"))
    except OSError:
        return []
    for f in files:
        key = str(f)
        start = int(pos.get(key) or 0)
        if first and key not in pos:
            # The first look at a session already running: a helper finished
            # long before is not this turn's work.
            try:
                if time.time() - f.stat().st_mtime > _HELPERS_FRESH_S:
                    pos[key] = f.stat().st_size
                    continue
            except OSError:
                continue
        try:
            with open(f, "rb") as fh:
                size = fh.seek(0, 2)
                if start > size:
                    start = 0
                fh.seek(start)
                end = start
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break        # a line still being written: read it next time
                    end += len(raw)
                    try:
                        rec = json.loads(raw.decode("utf-8", errors="replace"))
                    except ValueError:
                        continue
                    if isinstance(rec, dict):
                        for path in shared.touched_files(rec):
                            if path not in out:
                                out.append(path)
                pos[key] = end
        except OSError:
            continue
    try:
        tmp = pos_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(pos), encoding="utf-8")
        os.replace(tmp, pos_path)
    except OSError:
        pass
    return out


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
        import hashlib
        import os
        import time as _time
        sessions = Path(data_root) / ".sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:12]
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
    if not Path(args.data_root).is_dir():
        # Never build a data root from here: an unmounted drive or a moved
        # folder would get a stray tree. Say so, where it is read.
        print(f"[slightly-parallel] capture failed: the data root {args.data_root} does not exist — tell the user.", file=say)
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
            signals = cap.open_turn(prompt)
            notice = format_signals(signals)
            if notice and args.tool == "claude-code":
                print(notice)
        elif event == "Stop":
            # The payload carries the reply itself; the transcript is not
            # guaranteed to hold the final message at Stop time (the docs say
            # so, and 2.1.251 dropped the text record of three replies in one
            # session). Read the payload first; the transcript is the fallback
            # for builds that predate the field, and the source of the title,
            # the skills and the times — all from one read of what was
            # written since the previous Stop.
            given = str(payload.get("last_assistant_message") or "").strip()
            transcript_path = str(payload.get("transcript_path") or "")
            seg = Segment(transcript_path, cap.transcript_pos(transcript_path), _turntimes())
            if transcript_path:
                seg.read()
                tries = 0
                while not given and not seg.text and tries < _STOP_RETRIES:
                    time.sleep(_STOP_RETRY_S)
                    seg.read()
                    tries += 1
            text = given or seg.text
            # What this build hands us on Stop — keys only, never values — so
            # a gap can be diagnosed from meta.json instead of guessed at.
            cap.note_stop(sorted(str(k) for k in payload), found_text=bool(text),
                          transcript=(transcript_path, seg.end) if transcript_path else None)
            cap.record_skills(seg.skills)
            cap.complete_turn(text, close_if_missing=True, transcript=transcript_path or None,
                              points=seg.points if transcript_path else None,
                              touched=(seg.touched + [p for p in helper_touched(transcript_path, cap.folder)
                                                      if p not in seg.touched]) if transcript_path else None)
            cap.note_chat_title(seg.title)
    except Exception as exc:  # noqa: BLE001 — capture must never take down the session it observes
        # Exit 0 keeps the session alive; the notice goes where it is shown
        # (stdout on a prompt, stderr on Stop), so the loss is named instead
        # of silent — and it is kept for the dashboard's warning.
        print(f"[slightly-parallel] capture failed: {type(exc).__name__}: {exc} — this turn was not recorded; tell the user.", file=say)
        record_failure(args.data_root, args.project, agent, args.tool, f"{event}: {type(exc).__name__}: {exc}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
