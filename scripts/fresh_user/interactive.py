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
from common import (
    Report,
    Space,
    get,
    is_provider_billing_failure,
    new_task_rows,
    redact_diagnostics,
    rows,
)
from screen import DOWN, ENTER, Screen

POLL_S = 0.2
UP = "\x1b[A"
COMPOSER_SETTLE_S = 1.0
STARTUP_DIALOGS = {
    "claude-code": (
        (("choosethetextstyle",), "Claude Code default theme accepted"),
        (("securitynotes:", "pressentertocontinue"), "Claude Code security notes acknowledged"),
    ),
    "codex": ((("trustthisfolder", "trustandcontinue"), "Codex project folder trusted"),),
    "opencode": (),
}
STARTUP_FAILURES = (
    (("selectloginmethod:",), "Claude Code requires login"),
    (("doyouwanttousethisapikey?",), "Claude Code API key confirmation"),
    (("yes,itrustthisfolder",), "Claude Code project folder trust"),
    (("choosethetextstyle",), "Claude Code theme selection"),
    (("securitynotes:", "pressentertocontinue"), "Claude Code security notes"),
    (("trustallandcontinue",), "Codex project hooks trust"),
    (("trustthisfolder", "trustandcontinue"), "Codex project folder trust"),
    (("setupthecodexagentsandbox",), "Codex Windows sandbox setup"),
)


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


def _composer(tool: str, text: str, shown: str) -> bool:
    if tool == "claude-code":
        return (bool(re.search(r"(?m)(?:^|\r)[ \t]*❯[^\S\r\n]*(?:Try\b|$)", text))
                and any(hint in shown for hint in ("ctrl+gtoeditinvscode", "?forshortcuts", "automodeon(shift+tabtocycle)")))
    if tool == "codex":
        return "›askcodextodoanything" in shown and "forshortcuts" in shown
    return "askanything" in shown and "tabagents" in shown and "ctrl+pcommands" in shown


def _ready(screen: Screen, tool: Tool, seconds: int, answered: list[str], codex_config: Path | None = None) -> bool:
    deadline = time.monotonic() + seconds
    ready_since = None
    previous_move = ""
    while time.monotonic() < deadline:
        screen.read()
        if getattr(screen, "exited", False):
            return False
        frame = getattr(screen, "rendered", "") or screen.text
        shown = re.sub(r"\s+", "", frame.lower())
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
                ready_since = None
        elif tool.name == "claude-code" and "doyouwanttousethisapikey?" in shown:
            if re.search(r"❯(?:\d+\.)?no\(recommended\)", shown):
                screen.send(UP)
            elif not re.search(r"❯(?:\d+\.)?yes", shown):
                return False
            screen.send(ENTER)
            answered.append("Claude Code accepted CI API key")
        elif tool.name == "claude-code" and "yes,itrustthisfolder" in shown:
            if re.search(r"❯(?:\d+\.)?no,exit", shown):
                if previous_move != shown:
                    yes_first = shown.find("yes,itrustthisfolder") < shown.find("no,exit")
                    screen.send(UP if yes_first else DOWN)
                    previous_move = shown
                time.sleep(POLL_S)
                continue  # confirm only after the next frame shows the Yes row selected
            elif not re.search(r"❯(?:\d+\.)?yes,itrustthisfolder", shown):
                return False
            screen.send(ENTER)
            answered.append("Claude Code project folder trusted")
        elif dialog := next((name for signature, name in STARTUP_DIALOGS[tool.name]
                             if all(word in shown for word in signature)), None):
            screen.send(ENTER)
            answered.append(dialog)
        elif _composer(tool.name, frame, shown):
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
    shown = screen.rendered.strip()
    safe = redact_diagnostics(shown or screen.history)
    return re.sub(r"[ \t]{3,}", " ", safe)[-900:]


def _startup_failure(screen: Screen) -> str:
    frame = redact_diagnostics(screen.rendered or screen.text)
    shown = re.sub(r"\s+", "", frame.lower())
    reason = next((name for signature, name in STARTUP_FAILURES if all(word in shown for word in signature)),
                  "unknown screen")
    return f"L1 {reason}:\n{frame}"


def _wait_for_turn(screen: Screen, check: Callable[[], bool], seconds: int) -> str:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        # Drain the PTY while the CLI is working so a full buffer cannot hold up the hook.
        screen.read()
        if is_provider_billing_failure(screen.rendered + "\n" + screen.text):
            verdict = "L4 provider error (L0-billing)"
            break
        if check():
            return ""
        time.sleep(POLL_S)
    else:
        verdict = "turn timed out"
    screen.save_frame(verdict)
    return verdict


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
    screen = Screen(args, folder, {**env, **tool.extra_env()}, trace=space.root / f"terminal-{tool.name}-{marker}.log")

    def type_prompt(text: str) -> None:
        screen.send(text)
        screen.send(ENTER)

    try:
        answered: list[str] = []
        codex_config = space.home / ".codex" / "config.toml" if tool.name == "codex" else None
        ready = _ready(screen, tool, seconds, answered, codex_config)
        report.notes[f"{stage} onboarding"] = answered
        if not ready:
            screen.save_frame("startup failed")
        if not report.add(stage, "L1 CLI composer", ready, "" if ready else _startup_failure(screen)):
            return None
        type_prompt(prompt)
        chats = space.data / "projects" / code / "chats"
        captured: list[Path] = []

        def find_chat() -> bool:
            captured[:] = [chat for chat in chats.glob(f"{tool.id_prefix}*/chat.md") if _recorded_turn(chat, prompt, reply)]
            return bool(captured)

        error = _wait_for_turn(screen, find_chat, seconds)
        if not report.add(stage, "the chat contains the exact prompt and final reply in one turn",
                          not error and len(captured) == 1, f"{error}\n{captured or [chats]}\n{_screen_tail(screen)}"):
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

        error = _wait_for_turn(screen, project_has_session, seconds)
        if not report.add(stage, "the project lists the interactive session", not error, f"{error}\n{agent}"):
            return None
        tool.session = str(session)

        def cards() -> list[dict]:
            return rows(get(space, f"/api/tasks?project={code}"), "tasks")

        existing = {row.get("id") for row in cards()}
        type_prompt(task_prompt)
        error = _wait_for_turn(screen, lambda: bool(_last_reply(chat, task_prompt)), seconds)
        if not report.add(stage, "the operator task turn is captured to completion", not error,
                          f"{error}\n{agent}\n{_screen_tail(screen)}"):
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
                error = _wait_for_turn(screen, lambda message=message: bool(_last_reply(chat, message)), seconds)
                if not report.add(stage, f"{name}: the operator turn and answer are captured", not error,
                                  f"{error}\n{_screen_tail(screen)}"):
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
