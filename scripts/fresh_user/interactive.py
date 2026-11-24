"""Check the operator's first two turns through the real CLI terminal."""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import scenario
import core_mcp
from agents import OpenCode, Tool, give_login, model_for
from common import (
    Report,
    Space,
    WINDOWS,
    chatstore,
    get,
    is_provider_billing_failure,
    new_task_rows,
    redact_diagnostics,
    rows,
)
from screen import DOWN, ENTER, Screen, codex_pty_args

POLL_S = 0.2
UP = "\x1b[A"
COMPOSER_SETTLE_S = 1.0
PROMPT_PAINT_TIMEOUT_S = 8
CLAUDE_MCP_QUESTION = "New MCP server found in this project:"
CLAUDE_MCP_ACCEPTED = "Claude Code accepted the Slightly Parallel MCP server"
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
    (("newmcpserverfoundinthisproject:",), "Claude Code project MCP consent"),
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
            # Windows can render the choice cursor as an ASCII chevron.
            selected = re.search(r"(?im)^ *[❯>] *(?:\d+\. *)?(no, exit|yes, i trust this folder) *$", frame)
            if not selected:
                return False
            if selected[1].lower() == "no, exit":
                if previous_move != shown:
                    yes_first = shown.find("yes,itrustthisfolder") < shown.find("no,exit")
                    screen.send(UP if yes_first else DOWN)
                    previous_move = shown
                time.sleep(POLL_S)
                continue  # confirm only after the next frame shows the Yes row selected
            screen.send(ENTER)
            answered.append("Claude Code project folder trusted")
        elif tool.name == "claude-code" and "newmcpserverfoundinthisproject:" in shown:
            lines = [line.strip() for line in frame.splitlines()]
            questions = [line for line in lines if line.startswith(CLAUDE_MCP_QUESTION)]
            if questions != [f"{CLAUDE_MCP_QUESTION} slightly-parallel"]:
                return False
            selected = [line.removeprefix("❯").strip() for line in lines if line.startswith("❯")]
            if CLAUDE_MCP_ACCEPTED not in answered:
                if selected == ["Use this MCP server"]:
                    screen.send(ENTER)
                    answered.append(CLAUDE_MCP_ACCEPTED)
                elif selected in (["Continue without using this MCP server"],
                                  ["Use this and all future MCP servers in this project"]):
                    if previous_move != selected[0]:
                        screen.send(UP)
                        previous_move = selected[0]
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


def _operator_core_prompt(space: Space, state: scenario.State, step: scenario.Step) -> str:
    message = scenario.step_prompt(space, state, step)
    if step[0] != "#scan":
        return message
    filename = "scan-payloads.json"
    if state.tool.name == "codex":
        spec = space.root / filename
    else:
        # OpenCode asks before reading an external directory. Keep its test
        # inputs in the disposable project, outside the scan's Git changes.
        spec = state.folder / filename
        exclude = state.folder / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as ignored:
            ignored.write(f"\n/{filename}\n")
    spec.write_text(json.dumps({
        "scan": core_mcp.scan_fields(dict.fromkeys(("files_n", "lines_add", "lines_del", "decisions_n"), "COUNTER")),
        "file": core_mcp.file_fields("SCAN_ID"),
        "architecture": core_mcp.form_fields("SCAN_ID"),
    }, indent=2), encoding="utf-8")
    return (message + " Call scan_material without arguments. Read the exact fields from "
            f"{json.dumps(str(spec))}. Write the scan, file entry, and architecture form in order. "
            "Replace COUNTER with the corresponding number from scan_material, and SCAN_ID with "
            "the returned scan ID. Copy all other values exactly. No other MCP calls.")


def _wait_for_turn(screen: Screen, check: Callable[[], bool], seconds: int,
                   *, approval: Callable[[], str] | None = None) -> str:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        # Drain the PTY while the CLI is working so a full buffer cannot hold up the hook.
        screen.read()
        if is_provider_billing_failure(screen.rendered + "\n" + screen.text):
            verdict = "L4 provider error (L0-billing)"
            break
        if approval is not None and (verdict := approval()):
            break
        if check():
            return ""
        time.sleep(POLL_S)
    else:
        verdict = "turn timed out"
    screen.save_frame(verdict)
    return verdict


def _approve_task_write(screen: Screen, title: str) -> bool:
    frame = screen.rendered
    if ('Allow the slightly-parallel MCP server to run tool "write_entry"?' not in frame
            or not re.search(r"(?m)^\s*› 1\. Allow\b", frame)
            or not re.search(r'"title"\s*:\s*' + re.escape(json.dumps(title)), frame)
            or not re.search(r"(?m)^\s*lens:\s*task\s*$", frame)):
        return False
    screen.send(ENTER)
    return True



# In the Codex approval overlay, the displayed parameters sit between the
# tool question and the numbered choices. Reject a truncated preview.
_MCP_APPROVAL = re.compile(
    r'(?m)^ *Allow the (?P<server>[^\n]+?) MCP server to run tool "(?P<tool>[^"\n]+)"\? *$'
    r'(?P<parameters>.*?)^ *› (?P<choice>[1-4])\. [^\n]+', re.DOTALL,
)


_COMMAND_APPROVAL = re.compile(
    r"(?m)^ *Would you like to run the following command\? *$"
    r".*?^ *\$ (?P<command>.*?)^ *› (?P<choice>[^\n]+)", re.DOTALL,
)
RULE_INTERPRETATION = core_mcp.RULE_TEXT


def _core_approval(screen: Screen, step: str, rule_id: Callable[[], str] | None = None,
                   *, command: str = "", offline_command: str = "") -> Callable[[], str]:
    expected = {
        "#decision": ("write_entry", {
            "lens": "decision",
            "fields": {"decision": scenario.DECISION_TEXT},
        }),
        "#scan": ("scan_material", {}),
        "#done": ("task_done", {}),
        "#rule": ("interpret", {"lens": "rule", "text": RULE_INTERPRETATION}),
    }.get(step)
    handled = ""
    commands = tuple(filter(None, (offline_command, command)))
    command_index = 0

    def check() -> str:
        nonlocal handled, command_index
        if shell := _COMMAND_APPROVAL.search(screen.rendered):
            if shell.group() == handled:
                return ""
            shown = " ".join(shell["command"].split())
            if (command_index >= len(commands) or shown != " ".join(commands[command_index].split())
                    or shell["choice"].strip() != "1. Yes, proceed (y)"):
                return "unexpected Codex command approval"
            handled = shell.group()
            command_index += 1
            screen.send(ENTER)
            return ""
        match = _MCP_APPROVAL.search(screen.rendered)
        if match is None or match.group() == handled:
            return ""
        if (not expected or handled or match["server"] != "slightly-parallel"
                or match["tool"] != expected[0] or match["choice"] != "1"
                or not re.search(r"(?m)^ *› 1\. Allow\b", match.group())):
            return "unexpected Codex MCP approval"
        arguments = {}
        for line in match["parameters"].splitlines():
            if not line.strip():
                continue
            key, sep, value = line.strip().partition(": ")
            if not sep or key in arguments:
                return "unreadable Codex MCP approval arguments"
            try:
                arguments[key] = json.loads(value) if key == "fields" else value
            except ValueError:
                return "unreadable Codex MCP approval arguments"
        required = expected[1]
        if step == "#rule":
            current = rule_id() if rule_id else ""
            if not current:
                return ""  # the hook's new rule may not be in the API view yet
            required = {**required, "id": current}
        if arguments != required:
            return "unexpected Codex MCP approval arguments"
        handled = match.group()
        screen.send(ENTER)
        return ""

    return check

def smoke(space: Space, report: Report, code: str, folder: Path, tool: Tool, model: str, home: Path,
          seconds: int, *, core: bool = False, one_turn: bool = False,
          offline_provider: str = "") -> SmokeResult | None:
    stage = f"interactive:{tool.name}"
    verdicts = {"L1": "fail", "L2": "blocked by L1", "L3": "blocked by L2"}
    if one_turn:
        report.notes[f"{stage} layers"] = verdicts
    if not report.add(stage, "the interactive CLI is installed", tool.installed()):
        return None
    env = space.env()
    if not report.add(stage, "the CLI has a login", bool(offline_provider or give_login(tool, home, space, env))):
        return None
    if WINDOWS and isinstance(tool, OpenCode):
        try:
            tool.prepare_interactive(space, folder, env)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            report.add(stage, "L1 the pinned OpenCode plugin is ready", False, type(error).__name__)
            return None

    if one_turn and tool.name == "claude-code":
        # Setup made this scratch project. The full PTY tests exercise the
        # first-run dialogs, so the one-turn check can start at the composer.
        profile = space.home / ".claude.json"
        settings = json.loads(profile.read_text(encoding="utf-8")) if profile.exists() else {}
        settings.update(theme="dark", hasCompletedOnboarding=True)
        folder = folder.resolve()
        projects = settings.setdefault("projects", {})
        for path in {str(folder), folder.as_posix()}:
            projects.setdefault(path, {})["hasTrustDialogAccepted"] = True
        space.home.mkdir(parents=True, exist_ok=True)
        profile.write_text(json.dumps(settings), encoding="utf-8")
        # The freshly generated sample has exactly one project MCP server.
        (space.home / "settings.json").write_text(
            json.dumps({"enableAllProjectMcpServers": True}), encoding="utf-8",
        )
        env["CLAUDE_CONFIG_DIR"] = str(space.home)

    marker = uuid4().hex[:12]
    reply = f"sp-reply-{marker}"
    prompt = f"Reply with exactly {reply} on one line. Do not use any tools."
    title = f"sp-task-{marker}"
    task_prompt = (f"#task {title}. Use the Slightly Parallel write_entry tool with lens task. "
                   f"Set the title to {title} and tags to [\"ag_followup\"].")
    if one_turn:
        prompt = f"{task_prompt} After creating it, reply with exactly {reply} on one line."
    chosen = model_for(tool.name, model)
    args = {"claude-code": ["claude", "--session-id", tool.session, "--mcp-config", ".mcp.json",
                            "--allowedTools", *getattr(tool, "ALLOWED", ())],
            "codex": codex_pty_args(),
            "opencode": ["opencode"]}[tool.name]
    if chosen:
        args += ["--model", chosen]
    wait_for_prompt = tool.name == "codex" and (WINDOWS or core)
    if wait_for_prompt:
        args += ["-c", "disable_paste_burst=true"]
    policy = None
    if core and tool.name == "codex":
        policy = core_mcp.Plan(space.root)
        policy.start("hello")
        script = Path(core_mcp.__file__).resolve()
        prefix = "mcp_servers.slightly-parallel"
        args += ["-c", f'{prefix}.args={json.dumps([str(script), str(policy.policy), str(policy.trace)])}',
                 "-c", f'{prefix}.default_tools_approval_mode="approve"',
                 "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                 "-c", "sandbox_workspace_write.exclude_slash_tmp=true"]
        if WINDOWS:
            # ConPTY's process and Codex's sandboxed shell resolve a scratch
            # directory differently. Give both the exact disposable project.
            project = str(folder.resolve())
            args += ["--cd", project, "-c", 'sandbox_mode="workspace-write"',
                     "-c", f"sandbox_workspace_write.writable_roots={json.dumps([project])}"]
    if offline_provider:
        args += ["-c", 'model_provider="sp_stub"', "-c", 'model_providers.sp_stub.name="local stub"',
                 "-c", f'model_providers.sp_stub.base_url={json.dumps(offline_provider)}',
                 "-c", 'model_providers.sp_stub.wire_api="responses"']
    screen = Screen(args, folder, {**env, **tool.extra_env()}, trace=space.root / f"terminal-{tool.name}-{marker}.log",
                    reply_to_kitty_query=tool.name != "claude-code")

    def policy_error() -> str:
        return policy.result()[1] if policy else ""

    def policy_complete() -> bool:
        return not policy or policy.result() == (policy.expected, "")

    def type_prompt(text: str) -> None:
        screen.send(text)
        if wait_for_prompt and not screen.wait_for(text, PROMPT_PAINT_TIMEOUT_S):
            raise RuntimeError("Codex did not display the prompt before Enter")
        screen.send(ENTER)

    def cards() -> list[dict]:
        return rows(get(space, f"/api/tasks?project={code}"), "tasks")

    try:
        answered: list[str] = []
        codex_config = space.home / ".codex" / "config.toml" if tool.name == "codex" else None
        ready = _ready(screen, tool, seconds, answered, codex_config)
        report.notes[f"{stage} onboarding"] = answered
        if not ready:
            screen.save_frame("startup failed")
        if not report.add(stage, "L1 CLI composer", ready, "" if ready else _startup_failure(screen)):
            return None
        verdicts.update(L1="pass", L2="fail")
        existing = {row.get("id") for row in cards()} if one_turn else set()
        type_prompt(prompt)
        captured: list[tuple[str, Path]] = []
        task_write_approved = False

        def approve_task_write() -> None:
            nonlocal task_write_approved
            if tool.name == "codex" and not task_write_approved:
                task_write_approved = _approve_task_write(screen, title)

        def find_chat() -> bool:
            if one_turn:
                approve_task_write()
            candidates = ((agent, directory / "chat.md") for _, agent, directory in
                          chatstore.iter_chats(space.data, code, has="chat.md", sort=False))
            captured[:] = [(agent, chat) for agent, chat in candidates
                           if agent.startswith(tool.id_prefix) and _recorded_turn(chat, prompt, reply)]
            return bool(captured)

        error = (_wait_for_turn(screen, find_chat, seconds, approval=policy_error) if policy
                 else _wait_for_turn(screen, find_chat, seconds))
        if not report.add(stage, "the chat contains the exact prompt and final reply in one turn",
                          not error and len(captured) == 1,
                          f"{error}\n{captured or [chatstore.chats_root(space.data, code)]}\n{_screen_tail(screen)}"):
            return None
        agent, chat = captured[0]
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
        verdicts.update(L2="pass", L3="fail")

        if not one_turn:
            existing = {row.get("id") for row in cards()}
            if policy:
                fields = {"title": title, "description": "Verify the disposable calculator task is recorded.",
                          "tags": ["ag_followup"]}
                policy.start("#task", [["write_entry", {"lens": "task", "fields": fields}]])
                task_prompt += " Pass exactly these fields and nothing else: " + json.dumps(fields)
            type_prompt(task_prompt)

            def find_task_turn() -> bool:
                if not policy:
                    approve_task_write()
                return policy_complete() and bool(_last_reply(chat, task_prompt))

            error = (_wait_for_turn(screen, find_task_turn, seconds, approval=policy_error) if policy
                     else _wait_for_turn(screen, find_task_turn, seconds))
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
                message = _operator_core_prompt(space, state, step)
                approval = None
                if policy:
                    command = ""
                    offline_command = ""
                    rule = None
                    calls = []
                    if name == "a plain request" and offline_provider:
                        offline_command = core_mcp.OFFLINE_EDIT
                    elif name == "#rule":
                        rule = {"project": code, "agent": agent, "before": [
                            row["id"] for row in scenario.listed(space, "/api/rules", "rules", state)
                        ]}
                        calls = [["interpret", {"$rule_id": {"lens": "rule", "text": RULE_INTERPRETATION}}]]
                        message += f' Call interpret with only lens, the new rule ID and text "{RULE_INTERPRETATION}".'
                    elif name == "the work":
                        if offline_provider:
                            offline_command = core_mcp.OFFLINE_TESTS
                        command = ("git add calc.py test_calc.py && git commit -m 'Add calculator tests' "
                                   f"-m 'Task: {state.task}' -m 'Agent: {state.agent}'")
                        message += f" Run this exact command to stage and commit: {command}"
                    elif name == "#decision":
                        fields = {"decision": scenario.DECISION_TEXT, "weight": "normal"}
                        calls = [["write_entry", {"lens": "decision", "fields": fields}]]
                        message += " Call write_entry with lens decision and exactly these fields: " + json.dumps(fields)
                    elif name == "#scan":
                        calls = core_mcp.requests_for_scan()
                    elif name == "#sp":
                        calls = [["checkup", {}]]
                        message += " Call checkup with no arguments once. Report its result in chat."
                    elif name == "#done":
                        fields = {"id": task, "summary": "Added subtraction and tests for both calculator operations."}
                        calls = [["task_done", {}], ["task_report", fields]]
                        message += (" Call task_done with no arguments once, then task_report with exactly "
                                    + json.dumps(fields) + ". No other MCP calls. Summarize the result in chat.")
                    policy.start(name, calls, rule=rule, shell=tuple(filter(None, (offline_command, command))))

                    command_approval = _core_approval(screen, name, command=command, offline_command=offline_command)

                    def approval(command_approval=command_approval):
                        return policy_error() or command_approval()

                type_prompt(message)
                error = _wait_for_turn(screen, lambda message=message: policy_complete() and bool(_last_reply(chat, message)), seconds,
                                       approval=approval)
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
        verdicts["L3"] = "pass"
        return SmokeResult(agent, str(added[0]["id"]), tool)
    return None
