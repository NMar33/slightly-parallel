#!/usr/bin/env python3
"""Slightly Parallel on a real machine: everything a person would do, then one file to send.

Run by bootstrap.sh / bootstrap.ps1 after they installed the tools and you
logged in; or by hand from the repository folder on a machine that has
them: python scripts/machine/run.py

What it does, each step logged and checked:
1. The browser the checks drive (Playwright's Chromium).
2. The fresh-user test with Claude Code, Codex and OpenCode: from a clone to
   Setup, the hooks, MCP, and a real agent building a small notes page with
   #now, #task, #scan, #sp and #done (scripts/fresh_user, scenario "site").
3. This machine's own start: sp up, the monitor reads the machine, #sp and
   the report, sp down, sp check with the server down, start at login and
   the shortcut, for real (scripts/ci).
4. One archive beside the repository: the report of every step, the
   pictures, the logs, the versions of the system and every tool, and the
   page the agents built. Send it back for review.

Your logins are copied into the test's own folder and removed with it; the
archive holds none of them.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"
STAMP = time.strftime("%y%m%d-%H%M")
OUT = REPO / ".sp" / "machine" / STAMP


def kill_tree(proc: subprocess.Popen) -> None:
    """The step and everything it started: a server, a browser, an agent."""
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=60)
        else:
            os.killpg(proc.pid, 9)
    except (OSError, subprocess.SubprocessError):
        proc.kill()


def run(name: str, argv: list[str], cwd: Path = REPO, timeout: int = 900, env: dict | None = None) -> bool:
    """One step: its output to OUT/<name>.log, its result to OUT/steps.json.
    Past its time the whole process tree goes, and the log keeps what came."""
    print(f"\n== {name}: {' '.join(argv)}", flush=True)
    log = OUT / f"{name}.log"
    t0 = time.time()
    ok = False
    with open(log, "w", encoding="utf-8") as fh:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})},
                                    shell=WINDOWS and argv[0] in ("npm", "npx"), start_new_session=not WINDOWS)
            try:
                ok = proc.wait(timeout) == 0
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                proc.wait(60)
                fh.write(f"\n[run.py] stopped after {timeout} s\n")
        except OSError as exc:
            fh.write(f"\n[run.py] {type(exc).__name__}: {exc}\n")
    steps = json.loads((OUT / "steps.json").read_text(encoding="utf-8")) if (OUT / "steps.json").is_file() else []
    steps.append({"step": name, "ok": ok, "seconds": round(time.time() - t0), "log": log.name})
    (OUT / "steps.json").write_text(json.dumps(steps, indent=1), encoding="utf-8")
    print(f"   {'ok' if ok else 'FAILED'} in {round(time.time() - t0)} s — {log}", flush=True)
    return ok


def version(argv: list[str]) -> str:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=60, shell=WINDOWS)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else "?"
    except (OSError, subprocess.TimeoutExpired):
        return "not found"


def versions() -> dict[str, str]:
    return {
        "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python (this)": platform.python_version(),
        "git": version(["git", "--version"]),
        "node": version(["node", "--version"]),
        "npm": version(["npm", "--version"]),
        "tmux": "not on Windows" if WINDOWS else version(["tmux", "-V"]),
        "claude": version(["claude", "--version"]),
        "codex": version(["codex", "--version"]),
        "opencode": version(["opencode", "--version"]),
        "slightly parallel": version(["git", "-C", str(REPO), "describe", "--tags", "--always"]),
    }


def secrets() -> list[str]:
    """Every value that must not leave the machine: the keys in the
    environment and the strings in the agents' login files."""
    found = [os.environ.get(k, "") for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "SP_TOKEN")]
    home = Path.home()
    for rel in (".claude/.credentials.json", ".codex/auth.json", ".local/share/opencode/auth.json"):
        try:
            data = json.loads((home / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stack = [data]
        while stack:
            v = stack.pop()
            if isinstance(v, dict):
                stack.extend(v.values())
            elif isinstance(v, list):
                stack.extend(v)
            elif isinstance(v, str):
                found.append(v)
    return [v for v in found if len(v) >= 16]


def bundle(fresh_root: Path | None) -> Path:
    """The archive to send: only the files listed here, from this run, with
    every secret value cut out of the text ones."""
    (OUT / "versions.json").write_text(json.dumps(versions(), indent=1), encoding="utf-8")
    where = Path(os.environ.get("SP_ARCHIVE_DIR") or REPO.parent)       # CI keeps it in its workspace
    where.mkdir(parents=True, exist_ok=True)
    name = where / f"sp-machine-{platform.node() or 'machine'}-{STAMP}.zip"
    hide = secrets()
    started = OUT.stat().st_mtime - 5
    fresh = REPO / ".sp" / "fresh-user"
    picked: list[tuple[Path, str]] = [(p, f"run/{p.relative_to(OUT)}") for p in OUT.rglob("*")
                                      if p.suffix in (".json", ".log", ".png")]
    if fresh.is_dir():
        picked += [(p, f"fresh-user/{p.relative_to(fresh)}") for p in
                   [fresh / "report.json", *fresh.glob("logs/*.log"), *fresh.glob("screens/*.png")]]
    for p in (fresh_root.glob("sample*/*") if fresh_root else []):       # the page the agents built
        if p.suffix in (".html", ".js", ".css", ".md"):
            picked.append((p, f"built/{p.parent.name}/{p.name}"))
    picked += [(p, f"report/{p.name}") for p in REPO.glob("slightly-parallel-report-*.md")]
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arc in picked:
            if not path.is_file() or path.is_symlink() or path.stat().st_mtime < started:
                continue                      # an earlier run's file, or not a plain file
            if path.suffix == ".png":
                z.write(path, arc)
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for v in hide:
                text = text.replace(v, "[secret]")
            z.writestr(arc, text)
    return name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tools", default="claude-code,codex,opencode")
    ap.add_argument("--model", default="haiku", help="for Claude Code and OpenCode; Codex runs its own default")
    ap.add_argument("--skip-autostart", action="store_true", help="leave the login entry and the shortcut alone")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    print(f"Slightly Parallel on this machine — everything goes to {OUT}", flush=True)
    (OUT / "versions.json").write_text(json.dumps(versions(), indent=1), encoding="utf-8")

    run("browser", ["npm", "ci"], cwd=REPO / "frontend", timeout=1200)
    run("browser-chromium", ["npx", "playwright", "install", *([] if WINDOWS or sys.platform == "darwin" else ["--with-deps"]), "chromium"],
        cwd=REPO / "frontend")
    run("fresh-user", [py, "scripts/fresh_user/run.py", "--tools", args.tools, "--scenario", "site",
                       "--model", args.model, "--keep"], timeout=5400)
    fresh_root = None
    try:
        notes = json.loads((REPO / ".sp" / "fresh-user" / "report.json").read_text(encoding="utf-8")).get("notes", {})
        fresh_root = Path(notes["root"]) if notes.get("root") else None
    except (OSError, ValueError, KeyError):
        pass

    # This machine's own start, in the real home.
    if run("sp-up", [py, "sp.py", "up"]):
        run("monitor", [py, "scripts/ci/monitor_check.py"])
        run("topbar", ["node", "scripts/ci/topbar_check.mjs"])
        run("checkup", [py, "scripts/ci/checkup_check.py", "up"])
        run("report", [py, "sp.py", "report"])
    run("sp-down", [py, "sp.py", "down"])
    run("checkup-down", [py, "scripts/ci/checkup_check.py", "down"])
    if not args.skip_autostart:
        run("autostart", [py, "scripts/ci/autostart_check.py"])
    for p in (REPO / ".sp" / "ci").glob("*.png"):
        shutil.copy2(p, OUT / p.name)

    archive = bundle(fresh_root)
    steps = json.loads((OUT / "steps.json").read_text(encoding="utf-8"))
    bad = [s["step"] for s in steps if not s["ok"]]
    print(f"\n{len(steps) - len(bad)} of {len(steps)} steps passed" + (f"; failed: {', '.join(bad)}" if bad else ""))
    print(f"send this file: {archive}")
    # Only the folder this run's test made and named in its report.
    if fresh_root and fresh_root.is_dir() and fresh_root.name.startswith("sp fresh"):
        shutil.rmtree(fresh_root, ignore_errors=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
