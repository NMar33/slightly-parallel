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


def run(name: str, argv: list[str], cwd: Path = REPO, timeout: int = 7200, env: dict | None = None) -> bool:
    """One step: its output to OUT/<name>.log, its result to OUT/steps.json."""
    print(f"\n== {name}: {' '.join(argv)}", flush=True)
    log = OUT / f"{name}.log"
    t0 = time.time()
    try:
        with open(log, "w", encoding="utf-8") as fh:
            done = subprocess.run(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout,
                                  env={**os.environ, **(env or {})}, shell=WINDOWS and argv[0] in ("npm", "npx"))
        ok = done.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        ok = False
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


def bundle(fresh_root: Path | None) -> Path:
    """The archive to send: what the steps wrote, never a login."""
    (OUT / "versions.json").write_text(json.dumps(versions(), indent=1), encoding="utf-8")
    name = REPO.parent / f"sp-machine-{platform.node() or 'machine'}-{STAMP}.zip"
    skip = ("auth.json", ".credentials.json", ".env", "operator.token")
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob("*"):
            if p.is_file():
                z.write(p, f"run/{p.relative_to(OUT)}")
        fresh = REPO / ".sp" / "fresh-user"
        for p in fresh.rglob("*") if fresh.is_dir() else []:
            if p.is_file() and p.name not in skip:
                z.write(p, f"fresh-user/{p.relative_to(fresh)}")
        # The page the agents built, without its git history.
        for p in (fresh_root.glob("sample*/*") if fresh_root else []):
            if p.is_file() and p.suffix in (".html", ".js", ".css", ".md", ".py", ".json") and p.name not in skip:
                z.write(p, f"built/{p.parent.name}/{p.name}")
        for p in REPO.glob("slightly-parallel-report-*.md"):
            z.write(p, f"report/{p.name}")
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

    run("browser", ["npm", "ci"], cwd=REPO / "frontend")
    run("browser-chromium", ["npx", "playwright", "install", *([] if WINDOWS or sys.platform == "darwin" else ["--with-deps"]), "chromium"],
        cwd=REPO / "frontend")
    run("fresh-user", [py, "scripts/fresh_user/run.py", "--tools", args.tools, "--scenario", "site",
                       "--model", args.model, "--keep"])
    fresh_root = None
    try:
        notes = json.loads((REPO / ".sp" / "fresh-user" / "report.json").read_text(encoding="utf-8")).get("notes", {})
        fresh_root = Path(notes["root"]) if notes.get("root") else None
    except (OSError, ValueError, KeyError):
        pass
    if fresh_root is None:
        found = sorted(Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp").glob("sp fresh*"),
                       key=lambda p: p.stat().st_mtime)
        fresh_root = found[-1] if found else None

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
    if fresh_root and fresh_root.is_dir():
        shutil.rmtree(fresh_root, ignore_errors=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
