"""The hook lines Setup writes, run by the shells each tool really uses, with
the PATH a tool started from the Dock or a login item has, in folders whose
names hold a space, a letter outside ASCII and the characters shells treat
as their own. Each line must record the prompt; it always exits 0, so the
recorded turn is the proof, not the exit code.

- Linux and macOS: ``sh -c`` with ``PATH=/usr/bin:/bin`` (a macOS app started
  from the Dock gets that PATH, and ``python3`` is then /usr/bin/python3).
- Windows: Claude Code runs hooks through Git Bash; Codex through
  PowerShell 7 (``pwsh``) when it is there, else Windows PowerShell 5.1.

Before round 5 the lines ran only through ``shell=True`` (cmd on Windows).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.routers import setup
from tests.conftest import need

POSIX = os.name != "nt"
# Folder names a person has: a space and ü everywhere; on POSIX also the
# characters sh reads inside double quotes ($, `, \) and the ones it does not.
NAMES = ["data dir ü", "it's 50% data"] + (["cost $HOME `x` back\\slash"] if POSIX else [])


def _shells(tool: str) -> list[tuple[str, list[str]]]:
    if POSIX:
        return [("sh", ["/bin/sh", "-c"])]
    if tool == "codex":
        found = [(n, [p, "-NoProfile", "-NonInteractive", "-Command"])
                 for n, p in (("pwsh", shutil.which("pwsh")), ("powershell", shutil.which("powershell"))) if p]
        return found or [("powershell", [])]
    bash = next((str(p) for p in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",)
                 if p.exists()), shutil.which("bash"))
    return [("git-bash", [bash, "-c"] if bash else [])]


def _env(home: Path) -> dict[str, str]:
    if POSIX:
        return {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C"}
    keep = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "PROGRAMFILES",
            "LOCALAPPDATA", "APPDATA", "USERPROFILE", "SYSTEMDRIVE")
    return {**{k: v for k, v in os.environ.items() if k.upper() in keep}, "HOME": str(home)}


@pytest.mark.parametrize("tool", ["claude-code", "codex"])
@pytest.mark.parametrize("name", NAMES)
def test_the_hook_line_records_a_prompt_in_the_shell_the_tool_uses(tmp_path: Path, tool: str, name: str) -> None:
    if POSIX and not Path("/usr/bin/python3").exists():
        need("/usr/bin/python3 (the python3 a tool started from the Dock finds)")
    data_root = tmp_path / name / "data"
    work = tmp_path / name / "work"
    (data_root / "projects" / "alpha").mkdir(parents=True)
    work.mkdir(parents=True)
    line = setup._hook_command("alpha", data_root, tool)
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "shell-one", "cwd": str(work),
                          "prompt": "hello from the shell", "transcript_path": ""})
    for shell, argv in _shells(tool):
        if not argv:
            need(f"{shell} for the {tool} hook line")
        r = subprocess.run([*argv, line], input=payload, capture_output=True, text=True, timeout=60,
                           env=_env(tmp_path), cwd=str(work), encoding="utf-8")
        chats = list((data_root / "projects" / "alpha" / "chats").glob("*/chat.md"))
        said = "".join(p.read_text(encoding="utf-8") for p in chats)
        assert "hello from the shell" in said, (
            f"{shell}: no turn recorded\nline: {line}\nexit {r.returncode}\nstdout: {r.stdout[-800:]}\n"
            f"stderr: {r.stderr[-1500:]}\nerrors: {_errors(data_root)}")
        for p in chats:
            shutil.rmtree(p.parent)


def _errors(data_root: Path) -> str:
    f = data_root / ".capture" / "errors.jsonl"
    return f.read_text(encoding="utf-8")[-800:] if f.exists() else ""

