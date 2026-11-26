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
PTY_CLOSE_TIMEOUT_S = 3

_ANSI = re.compile(r"\x1b\[[0-9;?<>=]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|[\x00-\x08\x0e-\x1f]")
DOWN, ENTER = "\x1b[B", "\r"
_CURSOR_MODE = re.compile(r"\x1b\[\?1([hl])")
_CURSOR_ARROWS = {"\x1b[A": "\x1bOA", DOWN: "\x1bOB"}
KITTY_KEYBOARD_QUERY = "\x1b[?u"
ROWS, COLS = 45, 160
SCREEN_HISTORY_CHARS = 1600
#: What a full-screen program asks its terminal before it draws, and what a
#: terminal answers: the cursor, the colours, its kind, its keyboard. Left
#: unanswered, Codex waits; tmux and real terminals answer on their own.
_REPLIES = {"\x1b[6n": "\x1b[1;1R", "\x1b]10;?": "\x1b]10;rgb:ffff/ffff/ffff\x1b\\",
            "\x1b]11;?": "\x1b]11;rgb:0000/0000/0000\x1b\\", "\x1b[c": "\x1b[?1;2c", KITTY_KEYBOARD_QUERY: "\x1b[?0u"}


class TerminalTrace:
    def __init__(self, path: Path, columns: int = COLS):
        import pyte

        self.path = path
        self.frame = pyte.Screen(columns, ROWS)
        self.stream = pyte.Stream(self.frame)

    def feed(self, text: str) -> None:
        self.stream.feed(text)

    @property
    def rendered(self) -> str:
        return "\n".join(row.rstrip() for row in self.frame.display).strip("\n")

    def save(self, label: str) -> None:
        with self.path.open("a", encoding="utf-8") as log:
            log.write(f"\n--- {label} ---\n{redact_diagnostics(self.rendered)}\n")


def _opencode_composer(frame: str) -> str:
    from wcwidth import wcwidth, wcswidth

    lines = frame.splitlines()
    for index in range(len(lines) - 1, 1, -1):
        border = re.fullmatch(r"( *)╹▀{4,}(?: {2,}\S.*)?", lines[index])
        if border:
            break
    else:
        return ""
    # Input rows and the mode/model row have the same left border.
    prefix = border[1] + "┃"
    status = lines[index - 1]
    if not status.startswith(prefix):
        return ""
    # OpenCode starts the right pane at the same column on each row.
    # The status row leaves an aligned gap before its workspace label.
    status_body = status[len(prefix):].lstrip()
    gap = re.search(r" {4,}(?=\S)", status_body)
    width = wcswidth(status[:len(status) - len(status_body) + gap.end()]) if gap else 0
    rows = []
    for line in reversed(lines[:index - 1]):
        if not line.startswith(prefix):
            break
        if width:
            columns = 0
            for offset, char in enumerate(line):
                columns += max(0, wcwidth(char))
                if columns > width:
                    line = line[:offset]
                    break
        rows.append(line[len(prefix):])
    return "\n".join(reversed(rows))


def _claude_paste_marker(frame: str) -> str:
    lines = frame.splitlines()
    dividers = [index for index, line in enumerate(lines) if re.fullmatch(r" *─{8,} *", line)]
    if len(dividers) < 2:
        return ""
    top, bottom = dividers[-2:]
    composer = "\n".join(lines[top + 1:bottom]).strip()
    match = re.fullmatch(r"[❯>]\s*\[Pasted text #(\d+)(?: \+\d+ lines?)?\]", composer)
    return match[1] if match else ""


class Screen:
    """One program on a pseudo-terminal: what it shows so far, and keys to send."""

    def __init__(self, args: list[str], cwd: Path, env: dict[str, str], *, trace: Path | None = None,
                 reply_to_kitty_query: bool = True, columns: int = COLS):
        self.text = ""
        self.history = ""
        self.exited = False
        self.application_cursor = False
        self.reply_to_kitty_query = reply_to_kitty_query
        self._cursor_tail = ""
        self.trace = TerminalTrace(trace, columns) if trace is not None else None
        self._decode = codecs.getincrementaldecoder("utf-8")(errors="replace")
        if WINDOWS:
            from winpty import PtyProcess  # type: ignore[import-not-found]
            import threading
            self.proc = PtyProcess.spawn([shutil.which(args[0]) or args[0], *args[1:]], cwd=str(cwd), env=env,
                                         dimensions=(ROWS, columns))
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
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, columns, 0, 0))
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
            if asked not in got:
                continue
            # ConPTY handles OSC color queries. Injecting our own OSC into
            # its input writes the response as text in the CLI composer.
            if WINDOWS and asked.startswith("\x1b]"):
                continue
            # A late Kitty reply can insert a literal 'u' into Claude's
            # composer. Use its legacy keyboard fallback in this PTY.
            if asked == KITTY_KEYBOARD_QUERY and not self.reply_to_kitty_query:
                continue
            self._write(said)

    def wait_for(self, words: str, seconds: float, *, tool: str = "") -> bool:
        """Until the screen shows these words. A full-screen program moves the
        cursor between words instead of writing spaces: they are compared without."""
        end = time.monotonic() + seconds
        want = re.sub(r"\s", "", words)
        while time.monotonic() < end:
            self.read()
            frame = self.rendered
            if tool == "opencode":
                if want == re.sub(r"\s", "", _opencode_composer(frame)):
                    return True
            elif want in re.sub(r"\s", "", frame):
                return True
            elif tool == "claude-code" and len(words) > COLS:
                marker = _claude_paste_marker(frame)
                if marker and marker != self._paste_before_input:
                    # Claude elides long pastes. The caller still requires
                    # the captured turn to contain the exact original text.
                    return True
            time.sleep(SCREEN_POLL_INTERVAL_S)
        return False

    def send(self, keys: str) -> None:
        self.save_frame("before input")
        self._paste_before_input = _claude_paste_marker(self.rendered) if len(keys) > COLS else ""
        self.history = (self.history + "\n" + self.text.rstrip())[-SCREEN_HISTORY_CHARS:]
        self.text = ""  # what comes after this key
        self._write(_CURSOR_ARROWS.get(keys, keys) if self.application_cursor else keys)

    def _write(self, keys: str) -> None:
        if WINDOWS:
            self.proc.write(keys)
        else:
            remaining = memoryview(keys.encode())
            while remaining:
                remaining = remaining[os.write(self.fd, remaining):]

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


def codex_pty_args(binary: str = "codex") -> list[str]:
    # The background server would outlive the disposable folder. Windows CI
    # chooses the normal non-admin sandbox before the first-run setup prompt.
    args = [binary, "--no-daemon", "-c", "check_for_update_on_startup=false"]
    if WINDOWS:
        args += ["-c", 'windows.sandbox="unelevated"']
    return args


def trust_codex(folder: Path, env: dict[str, str], home: Path, seconds: float = 60) -> tuple[bool, str]:
    """Open Codex in the folder, trust the folder and its hooks on Codex's own
    screen, and check that Codex saved the hooks' trust. Answers (done, what
    the screen showed last)."""
    from agents import tools
    from interactive import _ready

    screen = Screen(codex_pty_args(), folder, env)
    try:
        ready = _ready(screen, tools()["codex"], seconds, [], home / ".codex" / "config.toml")
        return ready, screen.rendered[-600:]
    finally:
        screen.close()
