"""Check the operator's first two turns through the real CLI terminal."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import scenario
from agents import Tool, give_login, model_for
from common import Report, Space, get, new_task_rows, rows
from screen import DOWN, ENTER, Screen

POLL_S = 0.2
UP = "\x1b[A"
COMPOSER_SETTLE_S = 1.0


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


def _last_reply(chat: Path, prompt: str) -> str:
    turn = chat.read_text(encoding="utf-8").rsplit("\n## Turn ", 1)[-1]
    user, _, reply = turn.partition("\n**Agent**: ")
    return reply.strip() if f"\n**User**: {prompt}\n" in user + "\n" else ""


def _ready(screen: Screen, tool: Tool, seconds: int, answered: list[str], codex_config: Path | None = None) -> bool:
    deadline = time.monotonic() + seconds
    ready_since = None
    while time.monotonic() < deadline:
        screen.read()
        shown = re.sub(r"\s+", "", screen.text.lower())
        trusted = codex_config is None or (codex_config.is_file() and
                                            "trusted_hash" in codex_config.read_text(encoding="utf-8"))
        if tool.name == "claude-code" and "selectloginmethod:" in shown:
            return False
        if tool.name == "codex" and "trustallandcontinue" in shown:
            # A redraw can contain both the old menu and the composer. Read
            # the selected row before sending Enter, once for this dialog.
            selected = re.findall(r"›\d+\.(reviewhooks|trustallandcontinue|continuewithouttrusting)", shown)
            if selected and not trusted and "Codex project hooks trusted" not in answered:
                option = selected[-1]
                if option == "trustallandcontinue":
                    screen.send(ENTER)
                    answered.append("Codex project hooks trusted")
                else:
                    screen.send(DOWN if option == "reviewhooks" else UP)
            elif trusted:
                screen.text = shown.rsplit("trustallandcontinue", 1)[-1]
        elif tool.name == "claude-code" and "doyouwanttousethisapikey?" in shown:
            if re.search(r"❯(?:\d+\.)?no\(recommended\)", shown):
                screen.send(UP)
            elif not re.search(r"❯(?:\d+\.)?yes", shown):
                return False
            screen.send(ENTER)
            answered.append("Claude Code accepted CI API key")
        elif tool.name == "claude-code" and "yes,itrustthisfolder" in shown:
            if re.search(r"❯(?:\d+\.)?no,exit", shown):
                yes_first = shown.find("yes,itrustthisfolder") < shown.find("❯")
                screen.send(UP if yes_first else DOWN)
            elif not re.search(r"❯(?:\d+\.)?yes,itrustthisfolder", shown):
                return False
            screen.send(ENTER)
            answered.append("Claude Code project folder trusted")
        elif tool.name == "claude-code" and "choosethetextstyle" in shown:
            screen.send(ENTER)
            answered.append("Claude Code default theme accepted")
        elif tool.name == "claude-code" and "securitynotes:" in shown and "pressentertocontinue" in shown:
            screen.send(ENTER)
            answered.append("Claude Code security notes acknowledged")
        elif tool.name == "codex" and "trustthisfolder" in shown:
            screen.send(ENTER)
            answered.append("Codex project folder trusted")
        elif {"claude-code": "❯", "codex": "askcodex", "opencode": "askanything"}[tool.name] in shown:
            # The composer can draw before a trust modal arrives. For a new
            # Codex home also require the CLI to have persisted hook trust.
            if trusted:
                now = time.monotonic()
                ready_since = now if ready_since is None else ready_since
                if now - ready_since >= COMPOSER_SETTLE_S:
                    return True
                time.sleep(POLL_S)
                continue
        ready_since = None
        time.sleep(POLL_S)
    return False


def _screen_tail(screen: Screen) -> str:
    shown = screen.text.strip()
    safe = re.sub(r"sk-[^\s]+", "[redacted]", shown or screen.history)
    return re.sub(r"[ \t]{3,}", " ", safe)[-900:]


def smoke(space: Space, report: Report, code: str, folder: Path, tool: Tool, model: str, home: Path,
          seconds: int, *, core: bool = False) -> SmokeResult | None:
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
                            "--allowedTools", *getattr(tool, "ALLOWED", ())],
            "codex": ["codex", "--no-daemon", "-c", "check_for_update_on_startup=false"],
            "opencode": ["opencode"]}[tool.name]
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
            if "credit balance too low" in screen.text.lower() or "insufficient_quota" in screen.text.lower():
                return False
            time.sleep(POLL_S)
        return False

    def type_prompt(text: str) -> None:
        screen.send(text)
        screen.send(ENTER)

    try:
        answered: list[str] = []
        codex_config = space.home / ".codex" / "config.toml" if tool.name == "codex" else None
        ready = _ready(screen, tool, seconds, answered, codex_config)
        report.notes[f"{stage} onboarding"] = answered
        if not report.add(stage, "the CLI presents a usable prompt", ready, _screen_tail(screen)):
            return None
        type_prompt(prompt)
        chats = space.data / "projects" / code / "chats"
        captured: list[Path] = []

        def find_chat() -> bool:
            captured[:] = [chat for chat in chats.glob(f"{tool.id_prefix}*/chat.md") if _recorded_turn(chat, prompt, reply)]
            return bool(captured)

        if not report.add(stage, "the chat contains the exact prompt and final reply in one turn",
                          wait(find_chat) and len(captured) == 1, f"{captured or [chats]}\n{_screen_tail(screen)}"):
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
        type_prompt(task_prompt)
        finished = wait(lambda: bool(_last_reply(chat, task_prompt)))
        if not report.add(stage, "the operator task turn is captured to completion", finished, f"{agent}\n{_screen_tail(screen)}"):
            return None
        initial = new_task_rows(space, code, existing)
        match = [t for t in initial if t.get("agent_id") == agent and t.get("project") == code
                 and t.get("title") == title and t.get("status") == "agent"]
        if not report.add(stage, "the board lists the operator's new task in the agent column", len(initial) == len(match) == 1,
                          str(initial)[:1000]):
            return None
        task = str(match[0]["id"])
        if core:
            state = scenario.State(code, folder, tool)
            state.agent, state.task = agent, task
            for step in scenario.CORE:
                name, _, check = step
                if name == "#task":
                    continue
                message = scenario.step_prompt(space, state, step)
                type_prompt(message)
                finished = wait(lambda message=message: bool(_last_reply(chat, message)))
                if not report.add(stage, f"{name}: the operator turn and answer are captured", finished, _screen_tail(screen)):
                    break
                state.said.append(_last_reply(chat, message))
                if name == "#scan":
                    scenario.after_scan(space, report, stage, state, soft=True)
                elif name == "#sp":
                    scenario.after_sp(space, report, stage, state, soft=True)
                else:
                    check(space, report, stage, state)
    finally:
        screen.close()
    added = new_task_rows(space, code, existing)
    ok = len(added) == 1 and added[0].get("id") == task
    if report.add(stage, "exactly one task reaches the board under the same agent", ok, str(added)[:1000]):
        return SmokeResult(agent, str(added[0]["id"]), tool)
    return None
