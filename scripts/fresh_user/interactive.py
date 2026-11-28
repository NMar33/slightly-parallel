"""Check the operator's first two turns through the real CLI terminal."""

from __future__ import annotations

import json
import ntpath
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import scenario
import core_mcp
from agents import OpenCode, OpenCodeSDKError, Tool, give_login, model_for
from common import (
    PROVIDER_ACCOUNT_FAILURE_CLASSES,
    Report,
    Space,
    WINDOWS,
    chatstore,
    get,
    provider_account_error,
    new_task_rows,
    redact_diagnostics,
    rows,
)
from screen import COLS, DOWN, ENTER, Screen, codex_pty_args

_PROVIDER_TURN_FAILURES = {f"L4 provider error ({code})": classification
                           for code, classification in PROVIDER_ACCOUNT_FAILURE_CLASSES.items()}
POLL_S = 0.2
UP = "\x1b[A"
STARTUP_TIMEOUT_S = 60
PROMPT_PAINT_TIMEOUT_S = 8
CLAUDE_MCP_STABLE_S = 1.0
MENU_SELECTION_STABLE_S = 0.6
MENU_DIRECTION_RETRY_S = 1.0
CLAUDE_MCP_QUESTION = "New MCP server found in this project:"
CLAUDE_MCP_ACCEPTED = "Claude Code accepted the Slightly Parallel MCP server"
CLAUDE_MCP_CHOICES = (
    "Use this MCP server",
    "Use this and all future MCP servers in this project",
    "Continue without using this MCP server",
)
WINDOWS_CORE_APPROVAL_COLUMNS = 640
SCAN_PAYLOADS_NAME = "scan-payloads.json"
WINDOWS_CORE_WORK_SECTION = "Calculator core work commands"
CLAUDE_THEME_SELECTION = re.compile(
    r"(?im)^ *[❯>] *(?:[✔√] *)?(?:auto \(match terminal\)|(?:dark|light) mode(?: \(.*\))?) *$"
)
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
    _, separator, captured = user.partition("\n**User**: ")
    if not separator:
        return ""
    expanded = re.sub(r'\n\n<pasted_content id="([\w-]+)">\n(.*?)\n</pasted_content id="\1">(?:\n|$)',
                      lambda paste: paste[2], captured, flags=re.S)
    return reply.strip() if prompt in (captured, expanded) else ""


def _opencode_shell_arguments(command: object, workdir: object, workspace: Path) -> dict[str, str]:
    location = "[redacted]"
    if workdir is None or workdir == "":
        location = "default workspace"
    elif isinstance(workdir, str):
        try:
            relative = os.path.relpath(workspace / workdir, workspace.parent)
        except ValueError:
            pass  # Windows drive mismatch or invalid path.
        else:
            # Keep the shape of an external path without publishing its names.
            known = {"..", workspace.name}
            location = "/".join(part if part in known else "[redacted]" for part in Path(relative).parts) or "."
    return {"command": "pytest -q" if command == "pytest -q" else "[redacted]", "workdir": location}


def _opencode_turn_evidence(home: Path, session: str, *, workspace: Path | None = None) -> dict:
    """Summarize the failed turn from the disposable CLI profile without exporting its payloads."""
    path = home / ".local" / "share" / "opencode" / "opencode.db"
    unavailable = {"state": "unavailable"}
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)) as database:
            user = database.execute(
                "SELECT id FROM message WHERE session_id = ? AND json_extract(data, '$.role') = 'user' "
                "ORDER BY time_created DESC, id DESC LIMIT 1", (session,),
            ).fetchone()
            if user is None:
                return {"state": "no_user_turn"}
            messages = list(database.execute(
                "SELECT id, json_extract(data, '$.finish') IS NOT NULL, json_extract(data, '$.error') IS NOT NULL "
                "FROM message WHERE session_id = ? AND json_extract(data, '$.parentID') = ? "
                "AND json_extract(data, '$.role') = 'assistant' ORDER BY time_created DESC, id DESC LIMIT 16",
                (session, user[0]),
            ))
            assistant = []
            for message, finished, error in reversed(messages):
                parts = list(database.execute(
                    "SELECT json_extract(data, '$.type'), json_extract(data, '$.tool'), "
                    "json_extract(data, '$.state.status'), length(json_extract(data, '$.text')) > 0, "
                    "json_extract(data, '$.state.input.command'), json_extract(data, '$.state.input.workdir') "
                    "FROM part WHERE session_id = ? AND message_id = ? ORDER BY time_created DESC, id DESC LIMIT 16",
                    (session, message),
                ))
                tools = []
                for part, tool, status, _, command, workdir in reversed(parts):
                    if part == "tool":
                        name = {"slightly-parallel_write_entry": "write_entry", "skill": "skill"}.get(tool, "other")
                        phase = status if status in {"pending", "running", "completed", "error"} else "unknown"
                        if workspace is not None and tool in {"bash", "shell"}:
                            tools.append({"tool": "shell", "status": phase,
                                          "arguments": _opencode_shell_arguments(command, workdir, workspace)})
                        else:
                            tools.append({"tool": name, "status": phase})
                assistant.append({"finished": bool(finished), "error": bool(error),
                                  "text_emitted": any(kind == "text" and text for kind, _, _, text, *_ in parts),
                                  "tools": tools})
    except (OSError, ValueError, sqlite3.Error):
        return unavailable
    return {"state": "sampled", "assistant": assistant}


def _composer(tool: str, text: str, shown: str) -> bool:
    if tool == "claude-code":
        return (bool(re.search(r"(?m)(?:^|\r)[ \t]*[❯>][^\S\r\n]*(?:Try\b|$)", text))
                and any(hint in shown for hint in ("ctrl+gtoeditinvscode", "?forshortcuts", "automodeon(shift+tabtocycle)")))
    if tool == "codex":
        return "›askcodextodoanything" in shown and "forshortcuts" in shown
    return "askanything" in shown and "tabagents" in shown and "ctrl+pcommands" in shown


@dataclass
class _MenuSelection:
    row: str = ""
    since: float = 0.0
    moved_from: str = ""
    moved_at: float = 0.0
    retried: bool = False

    def stable(self, row: str, now: float, seconds: float) -> bool:
        if row != self.row:
            self.row, self.since = row, now
        return bool(row and now - self.since >= seconds)

    def move(self, screen: Screen, key: str, now: float, action: str, answered: list[str]) -> None:
        if self.moved_from == self.row:
            if self.retried or now - self.moved_at < MENU_DIRECTION_RETRY_S:
                return
            self.retried = True
            answered.append(f"{action}: key not taken, retrying direction once")
        self.moved_from, self.moved_at = self.row, now
        screen.send(key)


def _ready(screen: Screen, tool: Tool, seconds: int, answered: list[str], codex_config: Path | None = None) -> bool:
    deadline = time.monotonic() + seconds
    composer_seen = False
    selections: dict[str, _MenuSelection] = {}
    previous_action = ""

    def choose(action: str, row: str, *, move: str = "", stable_for: float = MENU_SELECTION_STABLE_S) -> None:
        nonlocal previous_action
        if previous_action and previous_action != action:
            selections[previous_action].row = ""
        previous_action = action
        state = selections.setdefault(action, _MenuSelection())
        now = time.monotonic()
        if action in answered or not state.stable(row, now, stable_for):
            return
        if move:
            state.move(screen, move, now, action, answered)
        else:
            screen.send(ENTER)
            answered.append(action)

    while time.monotonic() < deadline:
        screen.read()
        if getattr(screen, "exited", False):
            return False
        frame = getattr(screen, "rendered", "") or screen.text
        if provider_account_error(frame):
            return False
        shown = re.sub(r"\s+", "", frame.lower())
        trusted = codex_config is None or (codex_config.is_file() and
                                            "trusted_hash" in codex_config.read_text(encoding="utf-8"))
        folder_dialog = tool.name == "codex" and "trustthisfolder" in shown and "trustandcontinue" in shown
        if tool.name == "claude-code" and "selectloginmethod:" in shown:
            return False
        if tool.name == "codex" and "trustallandcontinue" in shown:
            actions = ("review hooks", "trust all and continue", "continue without trusting")
            selected = re.findall(r"(?m)^ *› *[1-3]\. *(review hooks|trust all and continue|continue without trusting)",
                                  frame.lower())
            complete = all(name.replace(" ", "") in shown for name in actions) and "enterconfirm" in shown
            row = selected[0] if complete and len(selected) == 1 and not trusted else ""
            direction = DOWN if row == actions[0] else UP if row == actions[-1] else ""
            choose("Codex project hooks trusted", row, move=direction)
        elif tool.name == "claude-code" and "doyouwanttousethisapikey?" in shown:
            selected = re.findall(r"[❯>](?:\d+\.)?(yes|no\(recommended\))", shown)
            row = selected[0] if len(selected) == 1 else ""
            choose("Claude Code accepted CI API key", row, move=UP if row == "no(recommended)" else "")
        elif tool.name == "claude-code" and "yes,itrustthisfolder" in shown:
            selected = re.findall(r"(?im)^ *[❯>] *(?:\d+\. *)?(no, exit|yes, i trust this folder) *$", frame.lower())
            row = selected[0] if len(selected) == 1 and "no,exit" in shown else ""
            yes_first = shown.find("yes,itrustthisfolder") < shown.find("no,exit")
            direction = (UP if yes_first else DOWN) if row == "no, exit" else ""
            choose("Claude Code project folder trusted", row, move=direction)
        elif tool.name == "claude-code" and "newmcpserverfoundinthisproject:" in shown:
            lines = [line.strip() for line in frame.splitlines()]
            questions = [line for line in lines if line.startswith(CLAUDE_MCP_QUESTION)]
            if questions != [f"{CLAUDE_MCP_QUESTION} slightly-parallel"]:
                return False
            choices = [line.lstrip("❯> ") for line in lines if line.lstrip("❯> ") in CLAUDE_MCP_CHOICES]
            selected = [line[1:].strip() for line in lines if line.startswith(("❯", ">"))]
            row = selected[0] if len(selected) == 1 and choices == list(CLAUDE_MCP_CHOICES) else ""
            choose(CLAUDE_MCP_ACCEPTED, row, move=UP if row in CLAUDE_MCP_CHOICES[1:] else "",
                   stable_for=CLAUDE_MCP_STABLE_S)
        elif folder_dialog:
            selected = re.findall(r"(?m)^ *[›>❯] *(?:\d+\. *)?(trust and continue|back to agent command center) *$", frame.lower())
            row = selected[0] if len(selected) == 1 and "backtoagentcommandcenter" in shown else ""
            choose("Codex project folder trusted", row, move=UP if row == "back to agent command center" else "")
        elif tool.name == "claude-code" and "choosethetextstyle" in shown:
            selected = CLAUDE_THEME_SELECTION.findall(frame)
            choose("Claude Code default theme accepted", selected[0] if len(selected) == 1 else "")
        elif tool.name == "claude-code" and "securitynotes:" in shown and "pressentertocontinue" in shown:
            choose("Claude Code security notes acknowledged", "security notes")
        else:
            if previous_action:
                selections[previous_action].row = ""
                previous_action = ""
            if _composer(tool.name, frame, shown) and trusted:
                # A composer can draw briefly before the next trust modal.
                if composer_seen:
                    return True
                composer_seen = True
                time.sleep(POLL_S)
                continue
        composer_seen = False
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


def _powershell_path(file: Path) -> str:
    return "'" + file.resolve().as_posix().replace("'", "''") + "'"


def _workspace_file(folder: Path, name: str) -> Path:
    target = (folder / name).resolve()
    target.relative_to(folder.resolve())
    return target


def _windows_scan_command(folder: Path) -> str:
    path = _powershell_path(_workspace_file(folder, SCAN_PAYLOADS_NAME))
    return f"Get-Content -LiteralPath {path} -Raw"


def _windows_read_commands(folder: Path, *names: str) -> tuple[str, ...]:
    listing = f"Get-ChildItem -LiteralPath {_powershell_path(folder)}"
    reads = tuple(f"Get-Content -LiteralPath {_powershell_path(_workspace_file(folder, name))}" for name in names)
    return (listing, f"{listing} | Select-Object Name", *reads, *(f"{read} -Raw" for read in reads))


def _windows_core_contract(folder: Path) -> Path:
    # Approvals are limited to the disposable repository. Make the installed
    # instructions readable there without granting a path in the other clone.
    contract = _workspace_file(folder, "SLIGHTLY-PARALLEL.md")
    source = Path(__file__).resolve().parents[2] / contract.name
    contract.write_bytes(source.read_bytes())
    agents = folder / "AGENTS.md"
    if agents.is_file():
        body = agents.read_text(encoding="utf-8")
        body = re.sub(r"(?m)^(- Contract: read )`[^`]+`", lambda m: f"{m[1]}`{contract}`", body, count=1)
        agents.write_text(body, encoding="utf-8")
    exclude = folder / ".git" / "info" / "exclude"
    if exclude.is_file():
        with exclude.open("a", encoding="utf-8") as ignored:
            ignored.write(f"\n/{contract.name}\n")
    return contract


def _core_toolchain_hint() -> str:
    return (f"Pytest is already prepared. To run the tests within your sandbox, use `{sys.executable}` with"
            " arguments `-m pytest -q test_calc.py` from the current workspace. If execution is blocked, report it in chat."
            " Do not install packages or request permission to run the tests outside your sandbox.")


def _codex_work_prompt(message: str, command: str, tests: str, contract: Path) -> str:
    followup = ("If the sandbox refuses the Git command, ask once to run that exact command. "
                "Once the commit command succeeds, reply in chat without running any further commands.")
    if not WINDOWS:
        return f"{message} Run this exact command to stage and commit: `{command}`. {followup}"
    # Keep the Windows PTY prompt short, and put the exact commands in the
    # allowed, Git-excluded contract which the prompt tells the agent to read.
    with contract.open("a", encoding="utf-8") as instructions:
        instructions.write(f"\n\n## {WINDOWS_CORE_WORK_SECTION}\n\n"
                           f"{_core_toolchain_hint()}\n\n"
                           "Run these commands exactly, in order:\n"
                           f"```powershell\n{tests}\n{command}\n```\n\n"
                           f"{followup}\nThe test runner checks the files and commit separately.\n")
    return (f"{message} Use Get-Content -LiteralPath to read {contract.name} and run the two exact"
            f" commands in its {WINDOWS_CORE_WORK_SECTION} section, in order."
            " If the sandbox refuses either, ask once for that exact command.")


def _operator_core_prompt(space: Space, state: scenario.State, step: scenario.Step) -> str:
    message = scenario.step_prompt(space, state, step)
    if WINDOWS and state.tool.name == "codex" and step in (scenario.EDIT, scenario.WORK):
        message += (f" Set the command working directory to `{state.folder.resolve()}`"
                    " and use absolute paths under that directory for the calculator files.")
    if state.tool.name == "opencode" and step == scenario.EDIT:
        message += (" Edit calc.py with the file editing tool in the current workspace."
                    " Do not run shell commands or tests in this turn. Report the edit in chat.")
    if step == scenario.WORK and not (WINDOWS and state.tool.name == "codex"):
        message += " " + _core_toolchain_hint()
    if step[0] != "#scan":
        return message
    filename = SCAN_PAYLOADS_NAME
    if state.tool.name == "codex" and not WINDOWS:
        spec = space.root / filename
    else:
        # OpenCode and Windows Codex can ask before accessing another folder.
        # Keep the fixture readable in the project and out of the Git scan.
        spec = state.folder / filename
        exclude = state.folder / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as ignored:
            ignored.write(f"\n/{filename}\n")
    fields_by_lens = {
        "scan": core_mcp.scan_fields(dict.fromkeys(("files_n", "lines_add", "lines_del", "decisions_n"), "COUNTER")),
        "file": core_mcp.file_fields("SCAN_ID"),
        "architecture": core_mcp.form_fields("SCAN_ID"),
    }
    shown_path = json.dumps(str(spec), ensure_ascii=False)
    if state.tool.name == "codex":
        payload = {"scan_material": {"project": state.code}}
        for lens, fields in fields_by_lens.items():
            payload[lens] = {"lens": lens, "project": state.code, "fields": fields}
        read = f"Run `{_windows_scan_command(state.folder)}`" if WINDOWS else f"Read {shown_path}"
        instructions = (f" {read}. Call scan_material with the exact arguments under "
                        '"scan_material". Use the other objects as the complete write_entry arguments.')
    else:
        payload = fields_by_lens
        instructions = f" Call scan_material without arguments. Read the exact fields from {shown_path}."
    spec.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return (message + instructions + " Write the scan, file entry, and architecture form in order. "
            "Replace COUNTER with the corresponding number from scan_material, and SCAN_ID with "
            "the returned scan ID. Copy all other values exactly. No other MCP calls.")


def _wait_for_turn(screen: Screen, check: Callable[[], bool], seconds: int,
                   *, approval: Callable[[], str] | None = None) -> str:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        # Drain the PTY while the CLI is working so a full buffer cannot hold up the hook.
        screen.read()
        if account_error := provider_account_error(screen.rendered + "\n" + screen.text):
            verdict = f"L4 provider error ({account_error})"
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


def _opencode_permission_failure(screen: Screen) -> str:
    frame = screen.rendered or screen.text
    if (re.search(r"(?m)^ *┃ *△ Permission required\b", frame)
            and re.search(r"(?m)^ *┃ *Allow once +Allow always +Reject\b", frame)):
        return "unexpected OpenCode permission prompt"
    return ""


def _turn_failure_class(error: str) -> str:
    if error in _PROVIDER_TURN_FAILURES:
        return _PROVIDER_TURN_FAILURES[error]
    return "stand" if error == "tool missing in the stand" else "unclassified"


def _recover_core_composer(screen: Screen, tool: str, error: str) -> bool:
    if screen.exited or error in _PROVIDER_TURN_FAILURES:
        return False
    # Interrupt or dismiss the failed turn. An unapproved prompt is never accepted.
    screen.send("\x1b")
    deadline = time.monotonic() + PROMPT_PAINT_TIMEOUT_S
    ready = False
    while not screen.exited and time.monotonic() < deadline:
        screen.read()
        frame = screen.rendered
        empty = (_composer(tool, frame, re.sub(r"\s+", "", frame.lower()))
                 and not (_COMMAND_APPROVAL.search(frame) or _MCP_APPROVAL.search(frame))
                 and not _opencode_permission_failure(screen))
        if empty and ready:
            return True
        ready = empty
        time.sleep(POLL_S)
    return False


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
_COMMAND_APPROVAL_CHOICE = re.compile(r"[1-9]\. (?:No|[^\n]+ \([a-z]+\))")
RULE_INTERPRETATION = core_mcp.RULE_TEXT


def _command_text(value: str) -> str:
    # Ignore renderer wrapping outside literals. In particular, a different
    # path or Python indentation inside a quoted argument is a different command.
    parts = re.split(r'''('(?:[^']|'')*'|"[^"\r\n]*")''', value)
    return "".join(part if index % 2 else re.sub(r"\s+", " ", part)
                   for index, part in enumerate(parts)).strip()


_QUOTED_WINDOWS_PATH = r'''(?:'(?:[^'\r\n]|'')*'|"[^"$`\r\n]*")'''
_WINDOWS_FILE_COMMAND = re.compile(
    rf"(?P<operation>Get-ChildItem|Get-Content|Add-Content|Set-Content) -LiteralPath "
    rf"(?P<path>{_QUOTED_WINDOWS_PATH})(?P<options>.*)"
)
_WINDOWS_GIT_COMMAND = re.compile(
    rf"git -c core\.hooksPath=NUL -c protocol\.allow=never -c commit\.gpgsign=false "
    rf"-C (?P<path>{_QUOTED_WINDOWS_PATH}) (?P<operation>add|commit)(?P<options> .*)"
)
_PACKAGE_INSTALL = re.compile(r"^(?:(?:python(?:3(?:\.\d+)?)? -m )?pip(?:3)? install|npm (?:install|ci)|uv pip install)\b")


def _windows_absolute_literal(token: str) -> str | None:
    path = token[1:-1]
    if token.startswith("'"):
        path = path.replace("''", "'")
    path = path.replace("\\", "/")
    if re.fullmatch(r'[A-Za-z]:/[^\x00-\x1f:"<>|?*]+', path) is None:
        return None
    if any(part in {".", ".."} or part.endswith((" ", ".")) for part in path[3:].split("/")):
        return None
    return ntpath.normpath(path).replace("\\", "/")


def _approval_command(value: str) -> str | tuple:
    literal = _command_text(value)
    if (match := _WINDOWS_FILE_COMMAND.fullmatch(literal)) and (path := _windows_absolute_literal(match["path"])):
        # The generated fixture gives the only allowed file and option
        # text. Normalize the path spelling, never a write's contents.
        return ("powershell", match["operation"], path, match["options"])
    git_commands = literal.split(" && ")
    if len(git_commands) == 2:
        matches = [_WINDOWS_GIT_COMMAND.fullmatch(command) for command in git_commands]
        if all(matches):
            pairs = tuple((m["operation"], _windows_absolute_literal(m["path"]), m["options"])
                          for m in matches if m is not None)
            if all(path is not None for _, path, _ in pairs):
                return ("git", pairs)
    return literal


def _core_approval(screen: Screen, step: str, rule_id: Callable[[], str] | None = None,
                   *, command: str = "", offline_command: str = "",
                   read_commands: tuple[str, ...] = (), confirmed: set[str | tuple] | None = None) -> Callable[[], str]:
    expected = {
        "#decision": ("write_entry", {
            "lens": "decision",
            "fields": {"decision": scenario.DECISION_TEXT},
        }),
        "#scan": ("scan_material", {}),
        "#done": ("task_done", {}),
        "#rule": ("interpret", {"lens": "rule", "text": RULE_INTERPRETATION}),
    }.get(step)
    handled_shell = ""
    handled_mcp = ""
    # An earlier command can finish under the sandbox without a dialog.
    pending = {_approval_command(value) for value in (*read_commands, offline_command, command) if value}
    edit_batch = ()
    if step == "a plain request" and offline_command and command:
        edit_batch = (_approval_command(offline_command), _approval_command(command))

    def check() -> str:
        nonlocal handled_shell, handled_mcp
        if shell := _COMMAND_APPROVAL.search(screen.rendered):
            if shell.group() == handled_shell:
                return ""
            choice = shell["choice"].strip()
            # ConPTY can expose the preview and selection partway through a
            # redraw. Wait for a whole menu choice before deciding on it.
            if _COMMAND_APPROVAL_CHOICE.fullmatch(choice) is None:
                return ""
            shown = _approval_command(shell["command"])
            if choice != "1. Yes, proceed (y)":
                return "unexpected Codex command approval"
            approved = (shown,)
            if shown not in pending:
                lines = tuple(_approval_command(line) for line in shell["command"].strip().splitlines())
                if not edit_batch or lines != edit_batch or not pending.issuperset(edit_batch):
                    if isinstance(shown, str) and _PACKAGE_INSTALL.match(shown):
                        return "tool missing in the stand"
                    return "unexpected Codex command approval"
                approved = edit_batch
            pending.difference_update(approved)
            if confirmed is not None:
                confirmed.update(approved)
            handled_shell = shell.group()
            screen.send(ENTER)
            return ""
        match = _MCP_APPROVAL.search(screen.rendered)
        if match is None or match.group() == handled_mcp:
            return ""
        if (not expected or handled_mcp or match["server"] != "slightly-parallel"
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
        handled_mcp = match.group()
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
        seed = os.environ.get("SP_OPENCODE_SDK_SEED")
        try:
            tool.prepare_interactive(space, folder, env, sdk_seed=Path(seed) if seed is not None else None)
        except OpenCodeSDKError as error:
            report.add(stage, "L1 the pinned OpenCode plugin is ready", False, str(error))
            return None
        except subprocess.TimeoutExpired as error:
            report.add(stage, "L1 the pinned OpenCode plugin is ready", False,
                       f"npm install for the pinned OpenCode plugin SDK timed out after {error.timeout:g} seconds")
            return None
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
    opencode_core_task = core and not one_turn and tool.name == "opencode"
    task_fields = {"title": title, "description": "Verify the disposable calculator task is recorded.",
                   "status": "agent", "tags": ["ag_followup"]}
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
    if tool.name == "codex":
        args += ["-c", "disable_paste_burst=true"]
    policy = None
    workspace_shell = WINDOWS and core and tool.name == "codex"
    workspace_reads: tuple[str, ...] = ()
    project_contract = folder / "SLIGHTLY-PARALLEL.md"
    if core and tool.name == "codex":
        policy = core_mcp.Plan(space.root)
        policy.start("hello")
        script = Path(core_mcp.__file__).resolve()
        prefix = "mcp_servers.slightly-parallel"
        args += ["-c", f'{prefix}.args={json.dumps([str(script), str(policy.policy), str(policy.trace)])}',
                 "-c", f'{prefix}.default_tools_approval_mode="approve"',
                 "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                 "-c", "sandbox_workspace_write.exclude_slash_tmp=true"]
        if workspace_shell:
            # ConPTY's process and Codex's sandboxed shell resolve a scratch
            # directory differently. Give both the exact disposable project.
            project = str(folder.resolve())
            project_contract = _windows_core_contract(folder)
            workspace_reads = _windows_read_commands(folder, "AGENTS.md", project_contract.name, "README.md", "calc.py")
            args += ["--cd", project, "-c", 'sandbox_mode="workspace-write"', "-c", 'approval_policy="on-request"',
                     "-c", "sandbox_workspace_write.network_access=false",
                     "-c", f"sandbox_workspace_write.writable_roots={json.dumps([project])}"]
    if offline_provider:
        args += ["-c", 'model_provider="sp_stub"', "-c", 'model_providers.sp_stub.name="local stub"',
                 "-c", f'model_providers.sp_stub.base_url={json.dumps(offline_provider)}',
                 "-c", 'model_providers.sp_stub.wire_api="responses"']
    screen = Screen(args, folder, {**env, **tool.extra_env()}, trace=space.root / f"terminal-{tool.name}-{marker}.log",
                    reply_to_kitty_query=tool.name != "claude-code",
                    columns=WINDOWS_CORE_APPROVAL_COLUMNS if workspace_shell else COLS)

    def policy_error() -> str:
        return policy.result()[1] if policy else ""

    def policy_complete() -> bool:
        return not policy or policy.result() == (policy.expected, "")

    def type_prompt(text: str, turn: str) -> bool:
        screen.send(text, paste=tool.name == "claude-code" and len(text) > COLS)
        if not screen.wait_for(text, PROMPT_PAINT_TIMEOUT_S, tool=tool.name):
            screen.save_frame("prompt paint timed out")
            return report.add(stage, f"{turn}: {tool.name} did not display the prompt before Enter", False, _screen_tail(screen))
        screen.send(ENTER)
        return True

    def cards() -> list[dict]:
        return rows(get(space, f"/api/tasks?project={code}"), "tasks")

    attempted: set[str] = set()
    blocked_by = "interactive setup did not establish a captured session and task"
    try:
        answered: list[str] = []
        codex_config = space.home / ".codex" / "config.toml" if tool.name == "codex" else None
        ready = _ready(screen, tool, min(seconds, STARTUP_TIMEOUT_S), answered, codex_config)
        report.notes[f"{stage} onboarding"] = answered
        if not ready:
            screen.save_frame("startup failed")
        detail = "" if ready else _startup_failure(screen)
        failure_class = PROVIDER_ACCOUNT_FAILURE_CLASSES.get(provider_account_error(detail), "unclassified")
        if not report.add(stage, "L1 CLI composer", ready, detail, failure_class=failure_class):
            return None
        verdicts.update(L1="pass", L2="fail")
        existing = {row.get("id") for row in cards()} if one_turn else set()
        if not type_prompt(prompt, "hello" if not one_turn else "canary"):
            return None
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

        approve_hello = _core_approval(screen, "hello", read_commands=workspace_reads)
        error = (_wait_for_turn(screen, find_chat, seconds, approval=lambda: policy_error() or approve_hello()) if policy
                 else _wait_for_turn(screen, find_chat, seconds))
        if not report.add(stage, "the chat contains the exact prompt and final reply in one turn",
                          not error and len(captured) == 1,
                          f"{error}\n{captured or [chatstore.chats_root(space.data, code)]}\n{_screen_tail(screen)}",
                          failure_class=_turn_failure_class(error)):
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
            if policy or opencode_core_task:
                arguments = {"lens": "task", "fields": task_fields}
                if policy:
                    arguments["project"] = code
                    policy.start("#task", [["write_entry", arguments]])
                task_prompt = (f"#task {title}. Call the Slightly Parallel write_entry tool once, "
                               f"with exactly this JSON argument: {json.dumps(arguments)}.")
                if opencode_core_task:
                    task_prompt += " Do not call any other tool. Reply with only the returned task ID."
                else:
                    task_prompt += " Report the task ID."
            attempted.add("#task")
            if not type_prompt(task_prompt, "#task"):
                return None

            def find_task_turn() -> bool:
                if not policy:
                    approve_task_write()
                return policy_complete() and bool(_last_reply(chat, task_prompt))

            approve_task = _core_approval(screen, "#task", read_commands=workspace_reads)
            error = (_wait_for_turn(screen, find_task_turn, seconds, approval=lambda: policy_error() or approve_task()) if policy
                     else _wait_for_turn(screen, find_task_turn, seconds))
            if error == "turn timed out" and tool.name == "opencode":
                report.notes["OpenCode task timeout"] = _opencode_turn_evidence(space.home, str(session))
            if not report.add(stage, "the operator task turn is captured to completion", not error,
                              f"{error}\n{agent}\n{_screen_tail(screen)}", failure_class=_turn_failure_class(error)):
                return None
        initial = new_task_rows(space, code, existing)
        match = [t for t in initial if t.get("agent_id") == agent and t.get("project") == code
                 and t.get("title") == title and t.get("status") == "agent"]
        if not report.add(stage, "the board lists the operator's new task in the agent column", len(initial) == len(match) == 1,
                          str(initial)[:1000]):
            return None
        task = str(match[0]["id"])
        if opencode_core_task:
            saved = get(space, f"/api/tasks/{task}")
            tags = str((saved.get("metadata") or {}).get("tags", "")).split(",")
            same_id = _last_reply(chat, task_prompt) == task
            same_fields = saved.get("description") == task_fields["description"] and "ag_followup" in tags
            if not report.add(stage, "OpenCode recorded the ID and fields of the created task", same_id and same_fields,
                              f"Reply ID matches: {same_id}. Description and tag match: {same_fields}."):
                return None
        if core:
            state = scenario.State(code, folder, tool)
            state.agent, state.task = agent, task
            for step in scenario.CORE:
                name, _, check = step
                if name == "#task":
                    continue
                attempted.add(name)
                message = _operator_core_prompt(space, state, step)
                approval = None
                confirmed: set[str | tuple] = set()
                command = ""
                if policy:
                    offline_command = ""
                    contract_read = ""
                    read_commands = workspace_reads
                    rule = None
                    calls = []
                    if name == "a plain request":
                        if workspace_shell:
                            calc = _powershell_path(_workspace_file(folder, "calc.py"))
                            offline_command = f"Get-Content -LiteralPath {calc}"
                            contract_read = f"Get-Content -LiteralPath {_powershell_path(project_contract)}"
                            command = core_mcp.EDIT_POWERSHELL.format(path=calc)
                            message += (f" Read the file with `{offline_command}`, then run `{command}`."
                                        " If the sandbox refuses the operation, ask once to run that exact command."
                                        " This is an edit-only turn. The tests and commit follow later.")
                        elif offline_provider:
                            offline_command = core_mcp.OFFLINE_EDIT
                    elif name == "#rule":
                        rule = {"project": code, "agent": agent, "before": [
                            row["id"] for row in scenario.listed(space, "/api/rules", "rules", state)
                        ]}
                        calls = [["interpret", {"$rule_id": {"lens": "rule", "text": RULE_INTERPRETATION}}]]
                        message += f' Call interpret with only lens, the new rule ID and text "{RULE_INTERPRETATION}".'
                    elif name == "the work":
                        if workspace_shell:
                            tests = _powershell_path(_workspace_file(folder, "test_calc.py"))
                            offline_command = core_mcp.TESTS_POWERSHELL.format(path=tests)
                            read_commands += _windows_read_commands(folder, "test_calc.py")
                        elif offline_provider:
                            offline_command = core_mcp.OFFLINE_TESTS
                        git = (f"git -c core.hooksPath=NUL -c protocol.allow=never -c commit.gpgsign=false -C {_powershell_path(folder)}"
                               if workspace_shell else "git")
                        command = (f"{git} add calc.py test_calc.py && {git} commit -m 'Add calculator tests' "
                                   f"-m 'Task: {state.task}' -m 'Agent: {state.agent}'")
                        message = _codex_work_prompt(message, command, offline_command, project_contract)
                    elif name == "#decision":
                        fields = {"decision": scenario.DECISION_TEXT, "weight": "normal"}
                        arguments = {"lens": "decision", "project": code, "fields": fields}
                        calls = [["write_entry", arguments]]
                        message += " Call write_entry with exactly this JSON argument: " + json.dumps(arguments) + "."
                    elif name == "#scan":
                        calls = [[method, {**arguments, "project": code}]
                                 for method, arguments in core_mcp.requests_for_scan()]
                        if workspace_shell:
                            scan = _windows_scan_command(folder)
                            read_commands += (scan, scan.removesuffix(" -Raw"))
                            if offline_provider:
                                offline_command = scan
                    elif name == "#sp":
                        calls = [["checkup", {}]]
                        message += " Call checkup with no arguments once. Report its result in chat."
                    elif name == "#done":
                        fields = {"id": task, "summary": "Added subtraction and tests for both calculator operations."}
                        calls = [["task_done", {}], ["task_report", fields]]
                        message += (" Call task_done with no arguments once, then task_report with exactly "
                                    + json.dumps(fields) + ". No other MCP calls. Summarize the result in chat.")
                    policy.start(name, calls, rule=rule, shell=tuple(filter(None, (offline_command, contract_read, command))))

                    command_approval = _core_approval(screen, name, command=command, offline_command=offline_command,
                                                      read_commands=read_commands, confirmed=confirmed)

                    def approval(command_approval=command_approval):
                        return policy_error() or command_approval()
                elif tool.name == "opencode":
                    def approval():
                        return _opencode_permission_failure(screen)

                if not type_prompt(message, name):
                    if _recover_core_composer(screen, tool.name, "prompt paint timed out"):
                        continue
                    blocked_by = f"{name}: terminal did not recover an empty composer"
                    return None
                error = _wait_for_turn(screen, lambda message=message: policy_complete() and bool(_last_reply(chat, message)), seconds,
                                       approval=approval)
                if error and tool.name == "opencode":
                    report.notes["OpenCode failed core turn"] = {
                        "step": name, **_opencode_turn_evidence(space.home, str(session), workspace=folder),
                    }
                reason = f"Approval refused: {error}" if error.startswith("unexpected Codex command approval") else error
                if not report.add(stage, f"{name}: the operator turn and answer are captured", not error,
                                  f"{reason}\n{_screen_tail(screen)}",
                                  failure_class=_turn_failure_class(error)):
                    if _recover_core_composer(screen, tool.name, error):
                        continue
                    blocked_by = f"{name}: {error}" if error in _PROVIDER_TURN_FAILURES else f"{name}: terminal did not recover an empty composer"
                    break
                state.said.append(_last_reply(chat, message))
                if name == "#scan":
                    scenario.after_scan(space, report, stage, state, soft=True)
                elif name == "#sp":
                    scenario.after_sp(space, report, stage, state, soft=True)
                elif check is scenario.after_work and policy:
                    check(space, report, stage, state, codex_git_approval=_approval_command(command) in confirmed)
                else:
                    check(space, report, stage, state)
    finally:
        screen.close()
        if core:
            for name, _, _ in scenario.CORE:
                if name not in attempted:
                    report.add(stage, f"{name}: blocked", False, blocked_by)
    added = new_task_rows(space, code, existing)
    ok = len(added) == 1 and added[0].get("id") == task
    if report.add(stage, "exactly one task reaches the board under the same agent", ok, str(added)[:1000]):
        verdicts["L3"] = "pass"
        return SmokeResult(agent, str(added[0]["id"]), tool)
    return None
