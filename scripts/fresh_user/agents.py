"""The agent tools, each driven headless: one message in, the turn runs to
its end, the next message continues the same chat.

Claude Code, Codex and OpenCode are each run here and in CI (the Agents
workflow). A tool that is not installed is skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from common import Space

VERSION_TIMEOUT_S = 15
OPENCODE_SDK_INSTALL_TIMEOUT_S = 60


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

    def version(self) -> str:
        cli = shutil.which(self.binary)
        if not cli:
            return "not installed"
        try:
            result = subprocess.run([cli, "--version"], capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=VERSION_TIMEOUT_S, check=True)
        except (subprocess.SubprocessError, OSError):
            return "unavailable"
        return result.stdout.strip() or result.stderr.strip() or "unavailable"

    def command(self, message: str, model: str, space: Space) -> list[str]:
        raise NotImplementedError

    def read(self, out: str) -> Turn:
        return Turn(ok=True, text=out.strip())

    def learn_session(self, output: str) -> None:
        """A tool that picks its own session id says it here (Claude Code is told one)."""

    def stdin(self, message: str) -> str | None:
        """The message on stdin instead of in the command, for a tool that reads it there."""
        return None

    def last_log(self, space: Space) -> str:
        try:
            return (space.root / f"{self.name}-turn-{self.turns:02d}.log").read_text(encoding="utf-8")
        except OSError:
            return ""

    def helpers(self, space: Space) -> list[str]:
        """The helper agents the last turn started, each as how it was told
        to run: the model asked for, "chat" for none."""
        return []

    def extra_env(self) -> dict[str, str]:
        """What this tool's process gets on top of the run's environment."""
        return {}

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
            fed = self.stdin(message)
            p = subprocess.run(args, cwd=folder or space.sample, env={**env, **self.extra_env()},
                               **({"input": fed} if fed is not None else {"stdin": subprocess.DEVNULL}),
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=seconds)
        except subprocess.TimeoutExpired:
            return Turn(False, "", error=f"no answer in {seconds} s")
        self.turns += 1
        # The tool's own answer, kept beside the report (a CI run keeps only that):
        # what it said, which tools it called, which were denied.
        try:
            (space.root / f"{self.name}-turn-{self.turns:02d}.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
        except OSError:
            pass
        self.learn_session(p.stdout + "\n" + p.stderr)
        if p.returncode != 0:
            return Turn(False, p.stdout[-2000:], error=(p.stderr or p.stdout)[-800:].strip(), seconds=time.time() - start)
        turn = self.read(p.stdout)
        turn.seconds = time.time() - start
        return turn


class ClaudeCode(Tool):
    #: What a user would allow when asked: Slightly Parallel's tools, file edits, git and python.
    ALLOWED = ["mcp__slightly-parallel", "Read", "Edit", "Write", "Glob", "Grep", "Task", "Agent", "Skill",
               "Bash(git:*)", "Bash(python3:*)", "Bash(python:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(node:*)"]

    def extra_env(self) -> dict[str, str]:
        # The MCP tools loaded at the start, not searched for: haiku on a
        # Windows runner searched for write_entry twelve times in one turn and
        # never called it. SP_CLAUDE_TOOL_SEARCH=true runs Claude Code's default.
        import os
        return {"ENABLE_TOOL_SEARCH": os.environ.get("SP_CLAUDE_TOOL_SEARCH", "false")}

    def command(self, message: str, model: str, space: Space) -> list[str]:
        pick = ["--session-id", self.session] if self.turns == 0 else ["--resume", self.session]
        return ["claude", "-p", message, "--model", model, *pick,
                # The project's own .mcp.json, which a user approves once in the terminal.
                # The stream: every tool call and its answer, kept in the turn's log;
                # the last line is the same result the plain JSON gave.
                "--mcp-config", ".mcp.json", "--allowedTools", *self.ALLOWED, "--output-format", "stream-json", "--verbose"]

    def read(self, out: str) -> Turn:
        d = None
        for line in reversed(out.splitlines()):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("type") == "result":
                d = rec
                break
        if d is None:
            return Turn(False, out[-2000:], error="no result in the answer")
        return Turn(ok=not d.get("is_error"), text=str(d.get("result") or ""),
                    cost_usd=float(d.get("total_cost_usd") or 0), error=str(d.get("subtype") or "") if d.get("is_error") else "")


    def helpers(self, space: Space) -> list[str]:
        out = []
        for line in self.last_log(space).splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            content = ((rec.get("message") or {}).get("content") if isinstance(rec, dict) and rec.get("type") == "assistant" else None) or []
            for c in content if isinstance(content, list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
                    out.append(str((c.get("input") or {}).get("model") or "chat"))
        return out


class Codex(Tool):
    hooks_trusted: bool = False

    def helpers(self, space: Space) -> list[str]:
        # `codex exec` prints no tool calls: the session logs have them (a
        # helper gets a log of its own), in the order they were made.
        calls = []
        for log in (space.home / ".codex" / "sessions").rglob("rollout-*.jsonl"):
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                pl = rec.get("payload") if isinstance(rec, dict) else None
                if isinstance(pl, dict) and pl.get("type") == "function_call" and str(pl.get("name") or "").endswith("spawn_agent"):
                    try:
                        args = json.loads(pl.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    calls.append((str(rec.get("timestamp") or ""), str(args.get("model") or "chat")))
        return [model for _, model in sorted(calls)]

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
        again = ["codex", "exec", "resume", "--last", *unattended, *(["--model", model] if model else []), message]
        return [*base, message] if self.turns == 0 else again


class OpenCode(Tool):
    """`opencode run`, its events as JSON lines. The message goes on stdin:
    given as an argument, `opencode run` puts quotes around a message with
    spaces, and the chat would record the quotes as typed. No --auto: the
    permissions are the project's own, as Setup writes them."""

    def extra_env(self) -> dict[str, str]:
        # Keep the pinned CLI in the test. Updater and Node warnings can
        # overwrite OpenCode's Windows PTY before the composer is detected.
        return {"OPENCODE_DISABLE_AUTOUPDATE": "1", "NODE_NO_WARNINGS": "1"}

    def prepare_interactive(self, space: Space, folder: Path, env: dict[str, str]) -> None:
        """Install the SDK before the CLI starts drawing, in the disposable profile only."""
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("OpenCode's plugin SDK requires npm")
        package = f"@opencode-ai/plugin@{self.version()}"
        config = space.home / ".config"
        for prefix in (config / "opencode", folder / ".opencode"):
            prefix.mkdir(parents=True, exist_ok=True)
            subprocess.run([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts", "--prefix", str(prefix), package],
                           env=space.env(), check=True, timeout=OPENCODE_SDK_INSTALL_TIMEOUT_S, capture_output=True)
        exclude = folder / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as ignored:
            ignored.write("\n/.opencode/node_modules/\n/.opencode/package.json\n/.opencode/package-lock.json\n")
        env.update(XDG_CONFIG_HOME=str(config), XDG_DATA_HOME=str(space.home / ".local" / "share"),
                   XDG_CACHE_HOME=str(space.home / ".cache"), XDG_STATE_HOME=str(space.home / ".local" / "state"))

    def stdin(self, message: str) -> str | None:
        return message

    def learn_session(self, output: str) -> None:
        # Every event names its session; the test cannot choose the id.
        if self.turns == 1:
            for line in output.splitlines():
                try:
                    sid = json.loads(line).get("sessionID")
                except (ValueError, AttributeError):
                    continue
                if sid:
                    self.session = str(sid)
                    return

    def command(self, message: str, model: str, space: Space) -> list[str]:
        base = ["opencode", "run", "--format", "json"]
        if model:
            base += ["--model", model]
        return base if self.turns == 0 else [*base, "--session", self.session]

    def helpers(self, space: Space) -> list[str]:
        """As subagent:model — OpenCode's task tool names a subagent, not a model."""
        out = []
        for line in self.last_log(space).splitlines():
            try:
                part = json.loads(line).get("part") or {}
            except (ValueError, AttributeError):
                continue
            if isinstance(part, dict) and part.get("tool") == "task":
                state = part.get("state") or {}
                model = (state.get("metadata") or {}).get("model") or {}
                out.append(f"{(state.get('input') or {}).get('subagent_type')}:{model.get('providerID')}/{model.get('modelID')}")
        return out

    def read(self, out: str) -> Turn:
        texts, errors, cost = [], [], 0.0
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            part = ev.get("part") if isinstance(ev.get("part"), dict) else {}
            if ev.get("type") == "text" and part.get("text"):
                texts.append(str(part["text"]))
            elif ev.get("type") == "step_finish":
                cost += float(part.get("cost") or 0)
            elif ev.get("type") == "error":
                errors.append(json.dumps(ev.get("error") or ev)[:400])
        if errors:
            return Turn(False, "\n".join(texts), cost_usd=cost, error="; ".join(errors))
        return Turn(ok=True, text=texts[-1] if texts else "", cost_usd=cost)


def tools() -> dict[str, Tool]:
    return {
        "claude-code": ClaudeCode("claude-code", "claude", "cc-", (".claude/.credentials.json",),
                                  ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"), "write_claude_hooks"),
        # Codex answers only from its login file: OPENAI_API_KEY in the
        # environment gave it a 401 (codex login --with-api-key writes the file).
        "codex": Codex("codex", "codex", "codex-", (".codex/auth.json",), (), "write_codex_hooks"),
        "opencode": OpenCode("opencode", "opencode", "oc-", (".local/share/opencode/auth.json",),
                             ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"), "write_opencode_plugin"),
    }


#: The model each tool is given when the run says "sonnet" (the default).
def model_for(tool: str, model: str) -> str:
    """Map --model unless the workflow pins this particular CLI's model."""
    import os
    return os.environ.get(MODEL_ENV[tool]) or MODELS[tool].get(model, model)


MODEL_ENV = {"claude-code": "SP_CLAUDE_MODEL", "codex": "CODEX_MODEL", "opencode": "SP_OPENCODE_MODEL"}
MODELS = {
    "claude-code": {"sonnet": "sonnet", "haiku": "haiku", "opus": "opus"},
    "codex": {"sonnet": "", "haiku": "", "opus": ""},          # Codex runs its own default model
    "opencode": {"sonnet": "anthropic/claude-sonnet-5-5", "haiku": "anthropic/claude-haiku-4-5", "opus": "anthropic/claude-opus-5-5"},
}


def give_login(tool: Tool, real_home: Path, space: Space, env: dict[str, str]) -> str:
    """Let the tool in the throwaway home answer as the person running the
    test. Returns how, or '' when there is no login to give."""
    import os
    login_keys = tool.login_env
    if tool.name == "opencode" and os.environ.get(MODEL_ENV[tool.name], "").startswith("openai/"):
        login_keys = ("OPENAI_API_KEY",)
    for key in login_keys:
        if os.environ.get(key):
            env[key] = os.environ[key]
            if tool.name == "claude-code" and key == "ANTHROPIC_API_KEY":
                # The CLI stores its approval as a suffix of the supplied key.
                # Seed only the disposable profile so startup never renders it.
                config = space.home / ".claude.json"
                profile = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
                responses = profile.setdefault("customApiKeyResponses", {})
                tail = env[key][-20:]
                responses["approved"] = list(dict.fromkeys([*responses.get("approved", []), tail]))
                responses["rejected"] = [value for value in responses.get("rejected", []) if value != tail]
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(json.dumps(profile), encoding="utf-8")
                config.chmod(0o600)
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
