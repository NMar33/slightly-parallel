"""Answer a tool's own screen, as a person at the keyboard would.

Codex runs a project's hooks only once the user has trusted the folder and
the hooks, on its interactive screen. The test does that step the same way:
it starts `codex` in a pseudo-terminal, waits for each question and presses
the key. Linux and macOS use the standard library's pty; Windows uses its
pseudo-console through pywinpty (pip install pywinpty==3.1.0).
"""

from __future__ import annotations

import codecs
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from common import WINDOWS, redact_diagnostics

SCREEN_POLL_INTERVAL_S = 0.3
KEY_PRESS_SETTLE_S = 0.5
CODEX_PROMPT_TIMEOUT_S = 30
PTY_CLOSE_TIMEOUT_S = 3

_ANSI = re.compile(r"\x1b\[[0-9;?<>=]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|[\x00-\x08\x0e-\x1f]")
DOWN, ENTER = "\x1b[B", "\r"
_CURSOR_MODE = re.compile(r"\x1b\[\?1([hl])")
_CURSOR_ARROWS = {"\x1b[A": "\x1bOA", DOWN: "\x1bOB"}
ROWS, COLS = 45, 160
SCREEN_HISTORY_CHARS = 1600
#: What a full-screen program asks its terminal before it draws, and what a
#: terminal answers: the cursor, the colours, its kind, its keyboard. Left
#: unanswered, Codex waits; tmux and real terminals answer on their own.
_REPLIES = {"\x1b[6n": "\x1b[1;1R", "\x1b]10;?": "\x1b]10;rgb:ffff/ffff/ffff\x1b\\",
            "\x1b]11;?": "\x1b]11;rgb:0000/0000/0000\x1b\\", "\x1b[c": "\x1b[?1;2c", "\x1b[?u": "\x1b[?0u"}


class TerminalTrace:
    def __init__(self, path: Path):
        import pyte

        self.path = path
        self.frame = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.frame)

    def feed(self, text: str) -> None:
        self.stream.feed(text)

    @property
    def rendered(self) -> str:
        return "\n".join(row.rstrip() for row in self.frame.display).strip("\n")

    def save(self, label: str) -> None:
        with self.path.open("a", encoding="utf-8") as log:
            log.write(f"\n--- {label} ---\n{redact_diagnostics(self.rendered)}\n")


class Screen:
    """One program on a pseudo-terminal: what it shows so far, and keys to send."""

    def __init__(self, args: list[str], cwd: Path, env: dict[str, str], *, trace: Path | None = None):
        self.text = ""
        self.history = ""
        self.exited = False
        self.application_cursor = False
        self._cursor_tail = ""
        self.trace = TerminalTrace(trace) if trace is not None else None
        self._decode = codecs.getincrementaldecoder("utf-8")(errors="replace")
        if WINDOWS:
            from winpty import PtyProcess  # type: ignore[import-not-found]
            import threading
            self.proc = PtyProcess.spawn([shutil.which(args[0]) or args[0], *args[1:]], cwd=str(cwd), env=env,
                                         dimensions=(ROWS, COLS))
            self.fd = None
            # pywinpty's read blocks until there is output: a thread reads, so
            # every wait keeps its time limit when the program shows nothing.
            self._buf: list[str] = []
            self._lock = threading.Lock()

            def pump() -> None:
                while True:
                    try:
                        got = self.proc.read(4096)
                    except Exception:  # noqa: BLE001 — closed: the program ended
                        self.exited = True
                        return
                    if got:
                        with self._lock:
                            self._buf.append(got)
            threading.Thread(target=pump, daemon=True).start()
        else:
            import pty
            import fcntl
            import struct
            import termios
            pid, fd = pty.fork()
            if pid == 0:  # the child: the program, in the folder
                os.chdir(cwd)
                os.execvpe(args[0], args, {**env, "TERM": "xterm-256color"})
            # A new pseudo-terminal is 0 by 0: a full-screen program draws nothing in it.
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
            self.pid, self.fd = pid, fd

    def read(self) -> None:
        if WINDOWS:
            with self._lock:
                got, self._buf = "".join(self._buf), []
            if got:
                self._receive(got)
            return
        import select
        end = time.monotonic() + SCREEN_POLL_INTERVAL_S
        while (remaining := end - time.monotonic()) > 0 and select.select([self.fd], [], [], remaining)[0]:
            try:
                got = os.read(self.fd, 65536)
            except OSError:
                self.exited = True
                return
            if not got:
                self.exited = True
                return
            self._receive(self._decode.decode(got))

    def _receive(self, text: str) -> None:
        controls = self._cursor_tail + text
        if modes := _CURSOR_MODE.findall(controls):
            self.application_cursor = modes[-1] == "h"
        self._cursor_tail = controls[-4:]
        self._answer(text)
        if self.trace is not None:
            self.trace.feed(text)
        self.text += _ANSI.sub("", text)

    @property
    def rendered(self) -> str:
        return self.trace.rendered if self.trace is not None else self.text

    def save_frame(self, label: str) -> None:
        if self.trace is not None:
            self.trace.save(label)

    def _answer(self, got: str) -> None:
        for asked, said in _REPLIES.items():
            # ConPTY handles OSC color queries. Injecting our own OSC into
            # its input writes the response as text in the CLI composer.
            if WINDOWS and asked.startswith("\x1b]"):
                continue
            if asked in got:
                self._write(said)

    def wait_for(self, words: str, seconds: float) -> bool:
        """Until the screen shows these words. A full-screen program moves the
        cursor between words instead of writing spaces: they are compared without."""
        end = time.time() + seconds
        want = re.sub(r"\s", "", words)
        while time.time() < end:
            self.read()
            if want in re.sub(r"\s", "", self.text):
                return True
            time.sleep(SCREEN_POLL_INTERVAL_S)
        return False

    def send(self, keys: str) -> None:
        self.save_frame("before input")
        self.history = (self.history + "\n" + self.text.rstrip())[-SCREEN_HISTORY_CHARS:]
        self.text = ""  # what comes after this key
        self._write(_CURSOR_ARROWS.get(keys, keys) if self.application_cursor else keys)
        time.sleep(KEY_PRESS_SETTLE_S)

    def _write(self, keys: str) -> None:
        if WINDOWS:
            self.proc.write(keys)
        else:
            os.write(self.fd, keys.encode())

    def close(self) -> None:
        if WINDOWS:
            self._close_windows()
            return
        if self.fd is None:
            return
        import signal

        def leader_running() -> bool:
            try:
                return os.waitpid(self.pid, os.WNOHANG)[0] == 0
            except ChildProcessError:
                return False

        def group_running() -> bool:
            try:
                os.killpg(self.pid, 0)
                return True
            except ProcessLookupError:
                return False

        try:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.pid, sig)
                except ProcessLookupError:
                    # close() can run before the child has entered its PTY session.
                    if leader_running():
                        os.kill(self.pid, sig)
                deadline = time.monotonic() + PTY_CLOSE_TIMEOUT_S
                while leader_running() or group_running():
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(SCREEN_POLL_INTERVAL_S)
                else:
                    break
        except (ChildProcessError, OSError):
            pass
        finally:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def _close_windows(self) -> None:
        import psutil

        command = ["taskkill", "/PID", str(self.proc.pid), "/T"]

        def taskkill(args: list[str]) -> None:
            try:
                subprocess.run(args, capture_output=True, timeout=PTY_CLOSE_TIMEOUT_S)
            except (OSError, subprocess.TimeoutExpired):
                pass

        running = []
        try:
            root = psutil.Process(self.proc.pid)
        except psutil.NoSuchProcess:
            root = None
        else:
            try:
                running = root.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            running.append(root)
        if running:
            taskkill(command)
            _, running = psutil.wait_procs(running, timeout=PTY_CLOSE_TIMEOUT_S)
        if running:
            if root in running:
                taskkill([*command, "/F"])
            # Retain process identities from before the gentle stop. Children
            # can survive an exited parent, so taskkill /T alone can miss them.
            for process in running:
                try:
                    process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            _, running = psutil.wait_procs(running, timeout=PTY_CLOSE_TIMEOUT_S)
        try:
            self.proc.close(force=bool(running))
        except OSError:
            pass


def trust_codex(folder: Path, env: dict[str, str], home: Path, seconds: float = 60) -> tuple[bool, str]:
    """Open Codex in the folder, trust the folder and its hooks on Codex's own
    screen, and check that Codex saved the hooks' trust. Answers (done, what
    the screen showed last)."""
    # --no-daemon: Codex's background server would outlive the test's folder.
    screen = Screen(["codex", "--no-daemon"], folder, env)
    try:
        if screen.wait_for("Trust this folder", seconds):
            screen.send(ENTER)
        # The choice's own words: a heading's letter can be lost in the drawing ("Hooks eed review", macOS).
        if not screen.wait_for("Trust all and continue", seconds):
            return False, screen.text[-600:]
        screen.send(DOWN)            # "Trust all and continue", the second choice
        screen.send(ENTER)
        screen.wait_for("Ask Codex", CODEX_PROMPT_TIMEOUT_S)
    finally:
        screen.close()
    try:
        saved = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        saved = ""
    return "trusted_hash" in saved, saved[-600:]
