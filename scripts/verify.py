#!/usr/bin/env python3
"""Run the fast terminal checks on one committed snapshot in a machine-local queue."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
LOCK = Path(tempfile.gettempdir()) / "slightly-parallel-terminal-verify.lock"
FAST_TERMINAL = (
    ("scroll.spec.ts", "the first wheel frame moves while terminal output is streaming"),
    ("paste.spec.ts", "a mouse selection writes|typing after a mouse drag|Shift-click extends|Ctrl\\+Shift\\+V pastes|the context menu pastes"),
    ("tabs.spec.ts", "Alt\\+N, Alt|Alt\\+W jumps"),
    ("tab-rename.spec.ts", "double-click renames"),
    ("tab-order.spec.ts", "dragging tabs saves"),
    ("tab-split.spec.ts", "opening a tab on the right"),
    ("msgmenu.spec.ts", "a right click on a reply in a narrow window"),
    ("sidebar-mode.spec.ts", "inward sidebar controls can be clicked"),
    ("layout.spec.ts", "Alt|Ctrl\\+Shift"),
)
DEPENDENCY_DIRS = ("frontend/node_modules", "desktop/node_modules", "backend/.venv")
FAST_PYTEST_WORKERS = min(12, getattr(os, "process_cpu_count", os.cpu_count)() or 1)


@contextmanager
def machine_queue(path: Path = LOCK):
    """The OS releases the lock if this runner dies."""
    with path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        if WINDOWS:
            import msvcrt

            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.5)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(*args: str, cwd: Path = REPO) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def link_dependencies(snapshot: Path) -> None:
    for lock in ("frontend/package-lock.json", "desktop/package-lock.json", "backend/requirements.lock"):
        if (snapshot / lock).read_bytes() != (REPO / lock).read_bytes():
            raise RuntimeError(f"{lock} differs from the installed checkout. Install that revision's dependencies first.")
    for name in DEPENDENCY_DIRS:
        src, dst = REPO / name, snapshot / name
        if not src.is_dir():
            raise RuntimeError(f"Missing {src}. Install project dependencies first.")
        if WINDOWS:
            subprocess.run(
                [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "mklink", "/j", str(dst), str(src)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        else:
            dst.symlink_to(src, target_is_directory=True)


def terminal_args() -> list[str]:
    files = [file for file, _ in FAST_TERMINAL]
    titles = "|".join(f"(?:{re.escape(file)}.*(?:{pattern}))" for file, pattern in FAST_TERMINAL)
    return [*files, "--grep", titles]


def run_step(command: list[str], cwd: Path, log: Path, env: dict[str, str], timeout: int) -> int:
    with log.open("wb") as output:
        child = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=not WINDOWS,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0,
        )
        try:
            return child.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if WINDOWS:
                subprocess.run(["taskkill", "/pid", str(child.pid), "/t", "/f"], check=False)
            else:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait()
            if isinstance(error, KeyboardInterrupt):
                raise
            return 124


def load() -> tuple[float, float, float] | None:
    return os.getloadavg() if hasattr(os, "getloadavg") else None


def test_counts(log: Path) -> dict[str, int]:
    counts = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if re.match(r"^(Tests\s+|=+\s*|\d+\s+(passed|failed|skipped)\b)", line):
            counts.update({label: int(number) for number, label in re.findall(r"(\d+) (passed|failed|skipped|deselected)\b", line)})
    return counts


def fast(sha: str, report_dir: Path) -> int:
    report: dict = {
        "sha": sha, "profile": "fast", "load_start": load(),
        "pytest_workers": FAST_PYTEST_WORKERS, "steps": {},
    }
    snapshot = report_dir / "worktree"
    try:
        npm = shutil.which("npm.cmd" if WINDOWS else "npm")
        if not npm:
            raise RuntimeError("npm is not on PATH.")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("node is not on PATH.")
        git("worktree", "add", "--detach", str(snapshot), sha)
        link_dependencies(snapshot)
        port = free_port()
        report["port"] = port
        env = {key: value for key, value in os.environ.items() if not key.startswith("SP_")}
        env.update(SP_E2E_NO_BUILD="1", SP_DESKTOP_E2E_PORT=str(port))
        # Linux always uses its own headless display for this quick profile.
        if sys.platform.startswith("linux"):
            env["SP_E2E_HEADLESS"] = "1"
        python = snapshot / "backend" / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
        steps = (
            ("build", [node, "node_modules/vite/bin/vite.js", "build"], "frontend", 240),
            ("vitest", [npm, "test"], "frontend", 240),
            ("pytest", [
                str(python), "-m", "pytest", "-o", "addopts=", "-q",
                "-n", str(FAST_PYTEST_WORKERS), "--dist", "loadfile",
                "-m", "not heavy and not slow", "--durations", "15",
            ], "backend", 480),
            ("electron", [node, "e2e/run.mjs", *terminal_args(), "--output", str(report_dir / "electron-artifacts")], "desktop", 240),
        )
        for name, command, folder, limit in steps:
            log = report_dir / f"{name}.log"
            started = time.monotonic()
            code = run_step(command, snapshot / folder, log, env, limit)
            result = {"exit_code": code, "seconds": round(time.monotonic() - started, 2), "log": log.name}
            if name != "build":
                result.update(test_counts(log))
            elif code == 0:
                index = snapshot / "frontend" / "dist" / "index.html"
                report["index_sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
            report["steps"][name] = result
            print(f"{name}: {code} · {log}", flush=True)
            if code:
                return code
        return 0
    finally:
        report["load_finish"] = load()
        (report_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if snapshot.exists():
            if WINDOWS:
                # Remove directory junctions themselves before Git walks the worktree.
                for name in DEPENDENCY_DIRS:
                    linked = snapshot / name
                    if linked.exists():
                        linked.rmdir()
            git("worktree", "remove", "--force", str(snapshot))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["fast"])
    parser.add_argument("--ref", default="HEAD", help="commit to snapshot before waiting for the queue")
    args = parser.parse_args()
    sha = git("rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}")
    directory = Path(tempfile.mkdtemp(prefix=f"sp-verify-{sha[:8]}-"))
    print(f"{sha} · waiting for the machine test queue · {directory}", flush=True)
    with machine_queue():
        return fast(sha, directory)


if __name__ == "__main__":
    raise SystemExit(main())
