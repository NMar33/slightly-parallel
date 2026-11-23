"""Check the operator's first two turns through the real CLI terminal."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agents import Tool, give_login, model_for
from common import Report, Space, get, rows
from screen import DOWN, ENTER, Screen

POLL_S = 0.2


@dataclass(frozen=True)
class SmokeResult:
    agent: str
    task: str
    tool: Tool


def _recorded_turn(chat: Path, prompt: str, reply: str) -> bool:
    if not chat.is_file():
        return False
    turns = chat.read_text(encoding="utf-8").split("\n## Turn ")[1:]
    return any(f"**User**: {prompt}\n" in turn and f"**Agent**: {reply}\n" in turn for turn in turns)


def _ready(screen: Screen, tool: Tool, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        screen.read()
        shown = re.sub(r"\s+", "", screen.text.lower())
        if tool.name == "codex" and "trustallandcontinue" in shown:
            screen.send(DOWN)
            screen.send(ENTER)
        elif tool.name == "claude-code" and "yes,itrustthisfolder" in shown:
            if "❯no,exit" in shown:
                screen.send(DOWN)
            screen.send(ENTER)
        elif any(prompt in shown for prompt in ("choosethetextstyle", "trustthisfolder", "yes,itrustthisfolder",
                                                "pressentertocontinue")):
            screen.send(ENTER)
        elif {"claude-code": "❯", "codex": "askcodex", "opencode": "askanything"}[tool.name] in shown:
            return True
        time.sleep(POLL_S)
    return False


def smoke(space: Space, report: Report, code: str, folder: Path, tool: Tool, model: str, home: Path,
          seconds: int) -> SmokeResult | None:
    stage = f"interactive:{tool.name}"
    if not report.add(stage, "the interactive CLI is installed", tool.installed()):
        return None
    env = space.env()
    if not report.add(stage, "the CLI has a login", bool(give_login(tool, home, space, env))):
        return None

    marker = uuid4().hex[:12]
    reply = f"sp-reply-{marker}"
    prompt = f"Reply with exactly {reply} on one line. Do not use any tools."
    title = f"sp-task-{marker}"
    task_prompt = f"#task {title}. Use Slightly Parallel to create one task with the exact title {title}."
    chosen = model_for(tool.name, model)
    args = {"claude-code": ["claude", "--session-id", tool.session, "--mcp-config", ".mcp.json",
                            "--allowedTools", "mcp__slightly-parallel__write_entry", "Skill"],
            "codex": ["codex", "--no-daemon"], "opencode": ["opencode"]}[tool.name]
    if chosen:
        args += ["--model", chosen]
    screen = Screen(args, folder, {**env, **tool.extra_env()})

    def wait(check: Callable[[], bool]) -> bool:
        # Drain the PTY while the CLI is working. Its screen can fill before the hook runs.
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            screen.read()
            if check():
                return True
            time.sleep(POLL_S)
        return False

    try:
        if not report.add(stage, "the CLI presents a usable prompt", _ready(screen, tool, seconds), screen.text[-900:]):
            return None
        screen.send(prompt)
        screen.send(ENTER)
        chats = space.data / "projects" / code / "chats"
        captured: list[Path] = []

        def find_chat() -> bool:
            captured[:] = [chat for chat in chats.glob(f"{tool.id_prefix}*/chat.md") if _recorded_turn(chat, prompt, reply)]
            return bool(captured)

        if not report.add(stage, "the chat contains the exact prompt and final reply in one turn",
                          wait(find_chat) and len(captured) == 1, f"{captured or [chats]}\n{screen.text[-900:]}"):
            return None
        chat = captured[0]
        agent = chat.parent.name
        meta = json.loads(chat.with_name("meta.json").read_text(encoding="utf-8"))
        session = meta.get("session_ref")

        def project_has_session() -> bool:
            if tool.name == "claude-code" and tool.session != session:
                return False
            return bool(session) and any(row.get("agent_id") == agent and row.get("session_ref") == session
                                         for row in rows(get(space, f"/api/project/{code}"), "agents"))

        if not report.add(stage, "the project lists the interactive session", wait(project_has_session), agent):
            return None
        tool.session = str(session)

        def cards() -> list[dict]:
            return rows(get(space, f"/api/tasks?project={code}"), "tasks")

        existing = {row.get("id") for row in cards()}
        screen.send(task_prompt)
        screen.send(ENTER)

        def finished() -> bool:
            turn = chat.read_text(encoding="utf-8").rsplit("\n## Turn ", 1)[-1]
            return f"**User**: {task_prompt}\n" in turn and "\n**Agent**: " in turn

        if not report.add(stage, "the operator task turn is captured to completion", wait(finished), agent):
            return None
        added: list[dict] = []

        def read_new_cards() -> bool:
            added[:] = [row for row in cards() if row.get("id") not in existing]
            return bool(added)

        wait(read_new_cards)
        ok = len(added) == 1 and added[0].get("agent_id") == agent and added[0].get("project") == code
        ok = ok and added[0].get("title") == title and added[0].get("status") == "agent"
        if report.add(stage, "exactly one task reaches the board under the same agent", ok, str(added)[:1000]):
            return SmokeResult(agent, str(added[0]["id"]), tool)
        return None
    finally:
        screen.close()
