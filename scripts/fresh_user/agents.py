"""The agent tools, each driven headless: one message in, the turn runs to
its end, the next message continues the same chat.

Claude Code is run and checked here. Codex and OpenCode are written from
their documented commands and have not been run by the author of this
file: a tool that is not installed is skipped, and the first run on a
machine that has one is the test of its adapter too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from common import Space


@dataclass
class Turn:
    ok: bool
    text: str
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str = ""


@dataclass
class Tool:
    """One agent tool. `id_prefix` is how its captured agents are named."""
    name: str
    binary: str
    id_prefix: str
    #: Files under the real home that hold the login, relative to it. They
    #: are copied into the throwaway home and removed with it.
    login_files: tuple[str, ...]
    #: Environment variables that carry a login instead of a file.
    login_env: tuple[str, ...]
    #: Setup's switch for this tool's capture, in the integrate request.
    integrate_flag: str
    session: str = field(default_factory=lambda: str(uuid.uuid4()))
    turns: int = 0

    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def command(self, message: str, model: str, space: Space) -> list[str]:
        raise NotImplementedError

    def read(self, out: str) -> Turn:
        return Turn(ok=True, text=out.strip())

    def learn_session(self, output: str) -> None:
        """A tool that picks its own session id says it here (Claude Code is told one)."""

    def say(self, message: str, model: str, space: Space, env: dict[str, str], seconds: int, folder: Path | None = None) -> Turn:
        import time
        start = time.time()
        try:
            # stdin closed: `codex exec` reads more of the prompt from an open
            # stdin and waits for it ("Reading additional input from stdin").
            args = self.command(message, model, space)
            # On Windows the tools are claude.cmd and codex.cmd: a program list
            # finds them only by their full path.
            args = [shutil.which(args[0]) or args[0], *args[1:]]
            p = subprocess.run(args, cwd=folder or space.sample, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=seconds)
        except subprocess.TimeoutExpired:
            return Turn(False, "", error=f"no answer in {seconds} s")
        self.turns += 1
        self.learn_session(p.stdout + "\n" + p.stderr)
        if p.returncode != 0:
            return Turn(False, p.stdout[-2000:], error=(p.stderr or p.stdout)[-800:].strip(), seconds=time.time() - start)
        turn = self.read(p.stdout)
        turn.seconds = time.time() - start
        return turn


class ClaudeCode(Tool):
    #: What a user would allow when asked: Slightly Parallel's tools, file edits, git and python.
    ALLOWED = ["mcp__slightly-parallel", "Read", "Edit", "Write", "Glob", "Grep", "Task", "Agent", "Skill",
               "Bash(git:*)", "Bash(python3:*)", "Bash(python:*)", "Bash(ls:*)", "Bash(cat:*)"]

    def command(self, message: str, model: str, space: Space) -> list[str]:
        pick = ["--session-id", self.session] if self.turns == 0 else ["--resume", self.session]
        return ["claude", "-p", message, "--model", model, *pick,
                # The project's own .mcp.json, which a user approves once in the terminal.
                "--mcp-config", ".mcp.json", "--allowedTools", *self.ALLOWED, "--output-format", "json"]

    def read(self, out: str) -> Turn:
        try:
            d = json.loads(out)
        except ValueError:
            return Turn(False, out[-2000:], error="the answer was not JSON")
        return Turn(ok=not d.get("is_error"), text=str(d.get("result") or ""),
                    cost_usd=float(d.get("total_cost_usd") or 0), error=str(d.get("subtype") or "") if d.get("is_error") else "")


class Codex(Tool):
    hooks_trusted: bool = False

    def learn_session(self, output: str) -> None:
        # `codex exec` prints its header with "session id: <uuid>"; the test
        # cannot choose it, so it reads it off the first turn.
        import re
        m = re.search(r"session id:\s*([0-9a-f-]{36})", output)
        if m and self.turns == 1:
            self.session = m.group(1)

    def command(self, message: str, model: str, space: Space) -> list[str]:
        # Codex 0.163 dropped --full-auto: the same, said as settings. It
        # also runs a project's hooks only once the user has trusted them
        # (a hash per hook in ~/.codex/config.toml).
        # Full access: the test's folder is a throwaway, and Codex's own Linux
        # sandbox (bubblewrap) cannot start where user namespaces are closed,
        # as on Ubuntu 24 and later ("bwrap: Operation not permitted").
        unattended = ["-c", 'sandbox_mode="danger-full-access"', "-c", 'approval_policy="never"']
        # Once the test has trusted the hooks on Codex's own screen (screen.py),
        # they run as for a person; only if that step failed is the trust bypassed.
        if not self.hooks_trusted:
            unattended.append("--dangerously-bypass-hook-trust")
        base = ["codex", "exec", "--skip-git-repo-check", *unattended]
        if model:
            base += ["--model", model]
        # `resume --last` continues the newest chat of this folder.
        return [*base, message] if self.turns == 0 else ["codex", "exec", "resume", "--last", *unattended, message]


class OpenCode(Tool):
    def command(self, message: str, model: str, space: Space) -> list[str]:
        base = ["opencode", "run"]
        if model:
            base += ["--model", model]
        return [*base, message] if self.turns == 0 else [*base, "--continue", message]


def tools() -> dict[str, Tool]:
    return {
        "claude-code": ClaudeCode("claude-code", "claude", "cc-", (".claude/.credentials.json",),
                                  ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"), "write_claude_hooks"),
        "codex": Codex("codex", "codex", "codex-", (".codex/auth.json",), ("OPENAI_API_KEY",), "write_codex_hooks"),
        "opencode": OpenCode("opencode", "opencode", "oc-", (".local/share/opencode/auth.json",),
                             ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"), "write_opencode_plugin"),
    }


#: The model each tool is given when the run says "sonnet" (the default).
MODELS = {
    "claude-code": {"sonnet": "sonnet", "haiku": "haiku", "opus": "opus"},
    "codex": {"sonnet": "", "haiku": "", "opus": ""},          # Codex runs its own default model
    "opencode": {"sonnet": "anthropic/claude-sonnet-5-5", "haiku": "anthropic/claude-haiku-4-5", "opus": "anthropic/claude-opus-5-5"},
}


def give_login(tool: Tool, real_home: Path, space: Space, env: dict[str, str]) -> str:
    """Let the tool in the throwaway home answer as the person running the
    test. Returns how, or '' when there is no login to give."""
    import os
    for key in tool.login_env:
        if os.environ.get(key):
            env[key] = os.environ[key]
            return f"${key}"
    for rel in tool.login_files:
        src = real_home / rel
        if src.is_file():
            dst = space.home / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            dst.chmod(0o600)
            return f"a copy of ~/{rel}"
    return ""
