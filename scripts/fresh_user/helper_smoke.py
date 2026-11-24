"""Check the same task command from a real headless helper."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from agents import Tool, give_login, model_for
from common import Report, Space, eventually, get, new_task_rows, redact_diagnostics, rows

HELPER_KINDS = {"claude-code": "claude-print", "codex": "codex-exec", "opencode": "opencode-run"}


def _mcp_refused(space: Space, tool: Tool, reason: str) -> bool:
    if tool.name == "codex":
        root = space.home / ".codex" / "sessions"
        logs = (p.read_text(encoding="utf-8") for p in root.rglob(f"rollout-*{tool.session}.jsonl"))
    else:
        logs = [tool.last_log(space)]
    for log in logs:
        for line in log.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or reason not in line:
                continue
            if tool.name == "claude-code" and row.get("type") == "user":
                return any(block.get("type") == "tool_result" and block.get("is_error") and reason in str(block.get("content"))
                           for block in row.get("message", {}).get("content", []) if isinstance(block, dict))
            if tool.name == "opencode" and row.get("type") == "tool_use":
                state = row.get("part", {}).get("state", {})
                return state.get("status") == "error" and reason in str(state.get("error"))
            if tool.name == "codex" and row.get("type") == "response_item":
                payload = row.get("payload", {})
                if payload.get("type") == "function_call_output" and reason in str(payload.get("output")):
                    return True
    if tool.name == "codex":
        # Newer Codex prints this tool failure in stderr rather than
        # retaining it as a function_call_output in the rollout.
        _, separator, stderr = tool.last_log(space).partition("\n--- stderr ---\n")
        return bool(separator and re.search(
            r"(?m)^mcp: slightly-parallel/write_entry \(failed\)\r?\n"
            r"(?:codex\r?\n)?422: " + re.escape(reason) + r"(?!\w)", redact_diagnostics(stderr),
        ))
    return False


def helper_smoke(space: Space, report: Report, code: str, folder: Path, tool: Tool, model: str, home: Path,
                 seconds: int, operator_agent: str) -> None:
    stage = f"helper:{tool.name}"
    if not report.add(stage, "the headless CLI is installed", tool.installed()):
        return
    env = space.env()
    if not report.add(stage, "the helper CLI has a login", bool(give_login(tool, home, space, env))):
        return

    def task_ids() -> set[str]:
        return {row["id"] for row in rows(get(space, f"/api/tasks?project={code}"), "tasks")}

    existing = task_ids()
    title = f"sp-helper-{uuid4().hex[:12]}"
    prompt = (f"#task {title}. Call the Slightly Parallel write_entry tool with lens task, title {title}, "
              "and text describing a test. Report its result exactly.")
    turn = tool.say(prompt, model_for(tool.name, model), space, env, seconds, folder)
    if not report.add(stage, "the headless helper answers", turn.ok, turn.error):
        return

    def captured() -> tuple[Path, dict] | None:
        for path in (space.data / "projects" / code / "chats").glob("*/meta.json"):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if meta.get("session_ref") == tool.session:
                return path, meta
        return None

    raw = eventually(captured)
    if not report.add(stage, "the helper has its own captured session", raw is not None, tool.session):
        return
    assert raw is not None
    path, meta = raw
    report.add(stage, "the helper uses a different chat from the operator", path.parent.name != operator_agent, path.parent.name)

    def chat_turn() -> list[str]:
        chat = path.with_name("chat.md")
        if not chat.is_file():
            return []
        return [line for line in chat.read_text(encoding="utf-8").splitlines() if line.startswith(("**User**: ", "**Agent**: "))]

    lines = eventually(lambda: found if len(found := chat_turn()) >= 2 else []) or chat_turn()
    report.add(stage, "the helper's board command is captured as a prompt",
               any(line.startswith("**User**: ") and title in line for line in lines), f"{path.parent.name}: {len(lines)} prompt/reply lines")
    report.add(stage, "the helper's final reply is captured",
               any(line.startswith("**Agent**: ") and line.removeprefix("**Agent**: ").strip() for line in lines),
               f"{path.parent.name}: {len(lines)} prompt/reply lines")
    expected = HELPER_KINDS[tool.name]
    report.add(stage, "the chat is classified as a helper", meta.get("helper") is True and meta.get("helper_kind") == expected,
               str(meta.get("helper_kind")))
    expected_refusal = f"this chat ({path.parent.name}) is marked a helper chat ({expected}); operator commands do not apply here"
    refused = _mcp_refused(space, tool, expected_refusal)
    report.add(stage, "the real MCP call explicitly refuses the helper task", refused, expected_refusal if refused else turn.text[-450:])
    added = new_task_rows(space, code, existing)
    report.add(stage, "the helper added zero cards", not added, str([row["id"] for row in added]))
