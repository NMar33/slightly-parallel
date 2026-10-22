"""The server and the capture hook killed in the middle of their writes.

A process killed at a random moment (``kill -9``, TerminateProcess on
Windows) stands in for a crash. After each kill: everything acknowledged
before it is there, every file reads (the data check finds nothing
damaged), an interrupted backup is not offered as a restore point, and the
next write works. A ledger kept outside the server says what to look for.
This is a killed process, not a power cut: the operating system still
writes what it was given. SP_CRASH_SEED picks other moments to kill at.
"""

from __future__ import annotations

import csv
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import backup
from backend.server import FIXTURES, create_app
from backend.sessions import parse_turns

from tests.test_backup_under_load import HOOK, Server

SESSION = "c4a50000-0000-4000-8000-0000000c4a50"


def _titles(root: Path) -> set[str]:
    with open(root / "tasks.csv", encoding="utf-8", newline="") as fh:
        return {str(r.get("title")) for r in csv.DictReader(fh)}


def _damaged(root: Path) -> list[dict]:
    with TestClient(create_app(data_root=root, watch=False, run_monitor=False, autoinstall_skills=False)) as c:
        return [i for i in c.get("/api/doctor").json().get("issues", []) if i.get("severity") == "error"]


def test_the_server_killed_mid_write_and_mid_backup_loses_nothing_acknowledged(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    rng = random.Random(int(os.environ.get("SP_CRASH_SEED", "7")))
    acked: list[str] = []
    for round_ in range(4):
        server = Server(root, tmp_path)
        stop = threading.Event()

        def write() -> None:
            n = 0
            while not stop.is_set():
                title = f"crash {round_}-{n}"
                try:
                    server.post("/api/tasks", {"project": "alpha-labs", "title": title, "status": "todo", "actor": "operator"}, 10)
                    acked.append(title)
                except OSError:
                    return                # the server is gone: unacknowledged, not counted
                n += 1

        def back_up() -> None:
            try:
                server.post("/api/backup/run", {"label": f"round {round_}"}, 60)
            except OSError:
                pass

        writers = [threading.Thread(target=write) for _ in range(2)] + [threading.Thread(target=back_up)]
        for w in writers:
            w.start()
        time.sleep(rng.uniform(0.3, 2.0))
        server.proc.kill()                # no clean exit: a crash
        server.proc.wait()
        server.log.close()
        stop.set()
        for w in writers:
            w.join(30)

        titles = _titles(root)
        lost = [t for t in acked if t not in titles]
        assert not lost, f"round {round_}: {len(lost)} acknowledged tasks lost: {lost[:5]}"
        damaged = _damaged(root)
        assert not damaged, f"round {round_}: {damaged[:3]}"
        # An interrupted archive is a .part file: never listed as a backup, and
        # every listed one verifies.
        for archive in backup.list_archives(tmp_path / "backups"):
            assert backup.verify(tmp_path / "backups", archive.name)["ok"], archive.name
    assert len(acked) >= 10, f"too little was written to test anything: {len(acked)}"

    # It starts again and takes a write.
    server = Server(root, tmp_path)
    try:
        server.post("/api/tasks", {"project": "alpha-labs", "title": "after the crashes", "status": "todo", "actor": "operator"})
    finally:
        server.stop()
    assert "after the crashes" in _titles(root)


def test_the_hook_killed_mid_write_leaves_a_chat_that_reads_and_records_the_next_turn(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    folder = tmp_path / "work"
    folder.mkdir()
    rng = random.Random(int(os.environ.get("SP_CRASH_SEED", "11")))

    def hook(payload: dict, kill_after: float | None = None) -> bool:
        proc = subprocess.Popen([sys.executable, str(HOOK), "--project", "alpha-labs", "--data-root", str(root)],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"session_id": SESSION, "cwd": str(folder), **payload}))
        proc.stdin.close()
        if kill_after is not None:
            time.sleep(kill_after)
            proc.kill()
        return proc.wait(60) == 0 and kill_after is None

    done: list[str] = []
    for n in range(12):
        text = f"turn {n}"
        kill = rng.uniform(0.0, 0.25) if n % 3 == 1 else None
        if hook({"hook_event_name": "UserPromptSubmit", "prompt": text}, kill) and \
                hook({"hook_event_name": "Stop", "last_assistant_message": f"answer {n}"}):
            done.append(text)
    chat = next((root / "projects" / "alpha-labs" / "chats").glob(f"cc-{SESSION[:8]}*/chat.md"))
    turns = parse_turns(chat)                 # reads, whatever was cut
    body = chat.read_text(encoding="utf-8")
    missing = [t for t in done if t not in body]
    assert not missing, missing
    assert turns and not _damaged(root)
    assert hook({"hook_event_name": "UserPromptSubmit", "prompt": "after the kills"})
    assert "after the kills" in chat.read_text(encoding="utf-8")


def test_a_second_server_on_the_same_data_folder_is_refused(tmp_path: Path) -> None:
    """Two servers on one folder would each rebuild, back up and time the
    same files. The second says why it stops; the first goes on."""
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    first = Server(root, tmp_path)
    try:
        other = tmp_path / "other"
        other.mkdir()
        try:
            Server(root, other)
            raise AssertionError("a second server started on the same data folder")
        except RuntimeError:
            pass
        assert "another Slightly Parallel server is using the data folder" in (other / "server.log").read_text(encoding="utf-8")
        first.post("/api/tasks", {"project": "alpha-labs", "title": "the first goes on", "status": "todo", "actor": "operator"})
    finally:
        first.stop()
    again = Server(root, tmp_path)            # the lock went with the process
    again.stop()
