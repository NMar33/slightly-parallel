#!/usr/bin/env python3
"""Run the fast terminal checks on one committed snapshot in a machine-local queue."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from threading import Event, Lock
import time

WINDOWS_QUEUE_POLL_S = 0.5
TASKKILL_TIMEOUT_S = 5
PROCESS_EXIT_TIMEOUT_S = 5
QUEUE_TIMEOUT_S = 45 * 60
PYTEST_TRACE_TIMEOUT_S = 300

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
TERMINAL_LOGIC = "src/features/terminal"
Step = tuple[str, list[str], str, int]
Wave = tuple[str, tuple[Step, ...]]


@contextmanager
def machine_queue(path: Path = LOCK):
    """Hold an OS lock tied to this open file, even across PID reuse.

    The kernel releases it when the holder dies. Keep the lock file in place:
    unlinking it could let separate waiters lock different file objects.
    """
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
                    time.sleep(WINDOWS_QUEUE_POLL_S)
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


def stop_process(child: subprocess.Popen) -> None:
    if WINDOWS:
        try:
            subprocess.run(["taskkill", "/pid", str(child.pid), "/t", "/f"], check=False, timeout=TASKKILL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            if child.poll() is None:
                child.kill()
    else:
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=PROCESS_EXIT_TIMEOUT_S)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        # The parent can already be gone while its descendants still run.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    child.wait(timeout=PROCESS_EXIT_TIMEOUT_S)


def run_step(command: list[str], cwd: Path, log: Path, env: dict[str, str], timeout: int, cancelled: Event) -> int:
    with log.open("wb") as output:
        child = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
            start_new_session=not WINDOWS,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0,
        )
        deadline = time.monotonic() + timeout
        try:
            while not cancelled.is_set() and (left := deadline - time.monotonic()) > 0:
                try:
                    code = child.wait(timeout=min(left, 0.25))
                    return code if code >= 0 else 128 - code
                except subprocess.TimeoutExpired:
                    pass
        except KeyboardInterrupt:
            stop_process(child)
            raise
        stop_process(child)
        return 130 if cancelled.is_set() else 124


def load() -> tuple[float, float, float] | None:
    return os.getloadavg() if hasattr(os, "getloadavg") else None


def test_counts(log: Path) -> dict[str, int]:
    counts = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if re.match(r"^(Tests\s+|=+\s*|\d+\s+(passed|failed|skipped)\b)", line):
            counts.update({label: int(number) for number, label in re.findall(r"(\d+) (passed|failed|skipped|deselected)\b", line)})
    return counts


def write_report(directory: Path, report: dict) -> None:
    pending = directory / "result.json.tmp"
    pending.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pending.replace(directory / "result.json")


def run_waves(
    run_step: Callable[[Step], int],
    finish_wave: Callable[[str, int], None],
    waves: tuple[Wave, ...],
    jobs: int,
    cancelled: Event,
) -> int:
    def run_wave(name: str, steps: tuple[Step, ...]) -> int:
        code = 0
        for step in steps:
            if cancelled.is_set():
                return 130
            code = run_step(step) or code
        finish_wave(name, code)
        return code

    (first, *remaining) = waves
    first_code = run_wave(*first)
    if jobs == 1:
        return max([first_code, *(run_wave(*wave) for wave in remaining)])

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_wave, *wave) for wave in remaining]
        try:
            return max([first_code, *(future.result() for future in futures)])
        except KeyboardInterrupt:
            cancelled.set()
            raise


def verify(sha: str, report_dir: Path, profile: str, jobs: int, queued_at: float) -> int:
    started_at = time.monotonic()
    workers = FAST_PYTEST_WORKERS if profile == "fast" else min(6, FAST_PYTEST_WORKERS)
    report: dict = {
        "run_id": report_dir.name, "family": "test",
        "sha": sha, "profile": profile, "status": "running", "load_start": load(),
        "queue_seconds": round(started_at - queued_at, 2),
        "pytest_workers": workers, "steps": {},
    }
    if profile == "waves":
        report.update(jobs=jobs, waves={})
    lock = Lock()
    cancelled = Event()
    snapshot = report_dir / "worktree"
    write_report(report_dir, report)
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
        build = ("build", [node, "node_modules/vite/bin/vite.js", "build"], "frontend", 240)
        vitest = ("vitest", [npm, "test"], "frontend", 240)
        pytest = ("pytest", [
            str(python), "-m", "pytest", "-o", "addopts=", "-q",
            "-n", str(workers), "--dist", "loadfile",
            "-m", "not heavy and not slow", "--durations", "15",
        ], "backend", 480)
        electron = ("electron", [node, "e2e/run.mjs", *terminal_args(), "--output", str(report_dir / "electron-artifacts")], "desktop", 240)

        def run(step: Step) -> int:
            name, command, folder, limit = step
            log = report_dir / f"{name}.log"
            started = time.monotonic()
            code = run_step(command, snapshot / folder, log, env, limit, cancelled)
            finished = time.monotonic()
            result = {
                "exit_code": code, "seconds": round(finished - started, 2), "log": log.name,
                "started_seconds": round(started - started_at, 2),
                "finished_seconds": round(finished - started_at, 2), "load": load(),
            }
            if name != "build":
                result.update(test_counts(log))
            with lock:
                if name == "build" and code == 0:
                    index = snapshot / "frontend" / "dist" / "index.html"
                    report["index_sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
                elif name != "build":
                    report.setdefault("first_test_result_seconds", result["finished_seconds"])
                report["steps"][name] = result
                write_report(report_dir, report)
                print(f"{name}: {code} · {log}", flush=True)
            return code

        def finish_wave(name: str, code: int) -> None:
            with lock:
                report["waves"][name] = {
                    "exit_code": code, "finished_seconds": round(time.monotonic() - started_at, 2),
                }
                write_report(report_dir, report)

        code = run(build)
        if code == 0 and profile == "waves":
            unit = [npm, "test", "--", "--maxWorkers=3", "--minWorkers=1"]
            waves = (
                ("terminal_logic", (("vitest-terminal", [*unit, TERMINAL_LOGIC], "frontend", 120),)),
                ("terminal_window", (electron,)),
                ("remaining_logic", (("vitest-remaining", [*unit, "--exclude", f"{TERMINAL_LOGIC}/**"], "frontend", 240), pytest)),
            )
            code = run_waves(run, finish_wave, waves, jobs, cancelled)
        elif code == 0:
            for step in (vitest, pytest, electron):
                if code := run(step):
                    break
        report.update(status="passed" if code == 0 else "failed", exit_code=code)
        return code
    except KeyboardInterrupt:
        report.update(status="cancelled", exit_code=130)
        return 130
    except Exception as error:
        report.update(status="error", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started_at, 2)
        report["load_finish"] = load()
        write_report(report_dir, report)
        if snapshot.exists():
            if WINDOWS:
                # Remove directory junctions themselves before Git walks the worktree.
                for name in DEPENDENCY_DIRS:
                    linked = snapshot / name
                    if linked.exists():
                        linked.rmdir()
            git("worktree", "remove", "--force", str(snapshot))


def queue_timeout(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds")
    return seconds


def queued_env(command: list[str], timeout: float) -> dict[str, str]:
    env = os.environ.copy()
    executable = Path(command[0]).stem.lower()
    if executable in {"pytest", "py.test"} or command[1:3] == ["-m", "pytest"]:
        # Pytest's built-in per-test watchdog also runs inside xdist workers.
        # Leave time for its stderr dump before the process group is stopped.
        trace_after = min(PYTEST_TRACE_TIMEOUT_S, timeout / 4)
        addopts = env.get("PYTEST_ADDOPTS", "")
        env["PYTEST_ADDOPTS"] = f"{addopts} -o faulthandler_timeout={trace_after:g}".strip()
    return env


def queue_command(command: list[str], timeout: float = QUEUE_TIMEOUT_S) -> int:
    print("Waiting for the machine test queue", flush=True)
    try:
        with machine_queue(LOCK):
            executable = shutil.which(command[0]) or command[0]
            child = subprocess.Popen(
                [executable, *command[1:]], env=queued_env(command, timeout), start_new_session=not WINDOWS,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0,
            )
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"Queued command timed out after {timeout:g}s. Stopping its process group.",
                      file=sys.stderr, flush=True)
                stop_process(child)
                return 124
            except KeyboardInterrupt:
                stop_process(child)
                raise
    except KeyboardInterrupt:
        return 130
    return code if code >= 0 else 128 - code


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, epilog="To queue another command, use %(prog)s queue [--timeout SECONDS] -- COMMAND [ARG ...].",
    )
    if sys.argv[1:2] == ["queue"]:
        queue_parser = argparse.ArgumentParser(prog=f"{parser.prog} queue")
        queue_parser.add_argument("--timeout", type=queue_timeout, default=QUEUE_TIMEOUT_S,
                                  help="per-run deadline in seconds after acquiring the lock (default: 2700)")
        tail = sys.argv[2:]
        split = tail.index("--") if "--" in tail else len(tail)
        args = queue_parser.parse_args(tail[:split])
        if not tail[split + 1:]:
            queue_parser.error("queue requires -- followed by a command")
        return queue_command(tail[split + 1:], args.timeout)
    parser.add_argument("profile", choices=["fast", "waves"])
    parser.add_argument("--ref", default="HEAD", help="commit to snapshot before waiting for the queue")
    parser.add_argument("--jobs", type=int, choices=[1, 2], default=1, help="run one or two groups at once for the waves pilot")
    args = parser.parse_args()
    if args.profile == "fast" and args.jobs != 1:
        parser.error("--jobs is only available for waves")
    sha = git("rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}")
    directory = Path(tempfile.mkdtemp(prefix=f"sp-verify-{sha[:8]}-"))
    queued_at = time.monotonic()
    write_report(directory, {"run_id": directory.name, "family": "test", "sha": sha, "profile": args.profile, "status": "queued"})
    print(f"{sha} · waiting for the machine test queue · {directory}", flush=True)
    with machine_queue():
        return verify(sha, directory, args.profile, args.jobs, queued_at)


if __name__ == "__main__":
    raise SystemExit(main())
