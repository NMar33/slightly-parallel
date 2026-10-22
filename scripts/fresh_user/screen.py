"""Answer a tool's own screen, as a person at the keyboard would.

Codex runs a project's hooks only once the user has trusted the folder and
the hooks, on its interactive screen. The test does that step the same way:
it starts `codex` in a pseudo-terminal, waits for each question and presses
the key. Linux and macOS use the standard library's pty; Windows uses its
pseudo-console through pywinpty (pip install pywinpty).
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

from common import WINDOWS

_ANSI = re.compile(r"\x1b\[[0-9;?<>=]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|[\x00-\x08\x0e-\x1f]")
DOWN, ENTER = "\x1b[B", "\r"
ROWS, COLS = 45, 160
#: What a full-screen program asks its terminal before it draws, and what a
#: terminal answers: the cursor, the colours, its kind, its keyboard. Left
#: unanswered, Codex waits; tmux and real terminals answer on their own.
_REPLIES = {"\x1b[6n": "\x1b[1;1R", "\x1b]10;?": "\x1b]10;rgb:ffff/ffff/ffff\x1b\\",
            "\x1b]11;?": "\x1b]11;rgb:0000/0000/0000\x1b\\", "\x1b[c": "\x1b[?1;2c", "\x1b[?u": "\x1b[?0u"}


class Screen:
    """One program on a pseudo-terminal: what it shows so far, and keys to send."""

    def __init__(self, args: list[str], cwd: Path, env: dict[str, str]):
        self.text = ""
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
                self._answer(got)
                self.text += _ANSI.sub("", got)
            return
        import select
        while select.select([self.fd], [], [], 0.2)[0]:
            try:
                got = os.read(self.fd, 65536)
            except OSError:
                return
            if not got:
                return
            text = got.decode("utf-8", "replace")
            self._answer(text)
            self.text += _ANSI.sub("", text)

    def _answer(self, got: str) -> None:
        for asked, said in _REPLIES.items():
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
            time.sleep(0.3)
        return False

    def send(self, keys: str) -> None:
        self.text = ""  # what comes after this key
        self._write(keys)
        time.sleep(0.5)

    def _write(self, keys: str) -> None:
        if WINDOWS:
            self.proc.write(keys)
        else:
            os.write(self.fd, keys.encode())

    def close(self) -> None:
        if WINDOWS:
            try:
                self.proc.terminate(force=True)
            except Exception:  # noqa: BLE001 — gone already
                pass
            return
        import signal
        try:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
        except (ProcessLookupError, ChildProcessError, OSError):
            pass
        try:
            os.close(self.fd)
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
        screen.wait_for("Ask Codex", 30)
    finally:
        screen.close()
    try:
        saved = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        saved = ""
    return "trusted_hash" in saved, saved[-600:]
