"""A backup taken while agents write, restored on a clean install.

A real server on a copy of the demo data; tasks are written through the API
and chat messages through the capture hook, from several threads, while
two backups run. The second backup is restored into an empty data folder.
A ledger kept outside the server says what to find there: every task and
message acknowledged before that backup started. The restored folder must
read without a damaged file, and take a new write.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import backup
from backend.server import FIXTURES, create_app

HOOK = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "claude-code-capture.py"
BACKEND = Path(__file__).resolve().parents[1]
SESSION = "10ad0000-0000-4000-8000-00000000b4c0"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, root: Path, tmp: Path) -> None:
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = {**os.environ, "SP_DATA_ROOT": str(root), "SP_PORT": str(self.port), "SP_SANDBOX": "1",
               "SP_EXAMPLES": "0", "SP_LOG_DIR": str(tmp / "logs"), "SP_BACKUP_ROOT": str(tmp / "backups")}
        self.log = open(tmp / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=BACKEND, env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(240):
            if self.proc.poll() is not None:
                raise RuntimeError("the server exited: " + (tmp / "server.log").read_text(encoding="utf-8")[-800:])
            try:
                req = urllib.request.Request(self.url + "/api/health", headers={"Sec-Fetch-Site": "same-origin"})
                with urllib.request.urlopen(req, timeout=2) as r:
                    self.cookie = (r.headers.get("Set-Cookie") or "").split(";", 1)[0]
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("the server did not answer")

    def post(self, path: str, body: dict, timeout: float = 120) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": self.cookie})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()


def _hook(root: Path, folder: Path, payload: dict) -> bool:
    proc = subprocess.run([sys.executable, str(HOOK), "--project", "alpha-labs", "--data-root", str(root)],
                          input=json.dumps({"session_id": SESSION, "cwd": str(folder), **payload}),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    return proc.returncode == 0


@pytest.mark.skipif(not hasattr(__import__("tarfile"), "data_filter"), reason="restore needs tarfile's data filter")
def test_a_backup_taken_while_agents_write_restores_everything_acknowledged_before_it(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    folder = tmp_path / "work"
    folder.mkdir()
    server = Server(root, tmp_path)
    acked: list[tuple[float, str, str]] = []          # (when acknowledged, kind, what)
    stop = threading.Event()
    failures: list[str] = []

    def tasks(lane: int) -> None:
        n = 0
        while not stop.is_set():
            title = f"load {lane}-{n}"
            try:
                server.post("/api/tasks", {"project": "alpha-labs", "title": title, "status": "todo", "actor": "operator"}, 30)
                acked.append((time.time(), "task", title))
            except OSError as exc:
                failures.append(f"{title}: {exc}")
            n += 1

    def messages() -> None:
        n = 0
        while not stop.is_set():
            text = f"load message {n}"
            if _hook(root, folder, {"hook_event_name": "UserPromptSubmit", "prompt": text}) and \
                    _hook(root, folder, {"hook_event_name": "Stop", "last_assistant_message": f"answer {n}"}):
                acked.append((time.time(), "message", text))
            n += 1

    writers = [threading.Thread(target=tasks, args=(i,)) for i in range(2)] + [threading.Thread(target=messages)]
    try:
        for w in writers:
            w.start()
        time.sleep(2)
        server.post("/api/backup/run", {"label": "under load, first"})
        time.sleep(1)
        started = time.time()
        made = server.post("/api/backup/run", {"label": "under load, second"})
        time.sleep(1)
    finally:
        stop.set()
        for w in writers:
            w.join(60)
        server.stop()
    assert not failures, failures[:3]
    name = made["archive"]["name"] if "archive" in made else made["name"]
    before = [a for a in acked if a[0] < started]
    assert sum(1 for a in before if a[1] == "task") >= 5 and any(a[1] == "message" for a in before), \
        f"too little written before the backup: {len(before)}"

    clean = tmp_path / "restored"
    clean.mkdir()
    backup.restore(tmp_path / "backups", name, clean)

    with open(clean / "tasks.csv", encoding="utf-8", newline="") as fh:
        titles = {r.get("title") for r in csv.DictReader(fh)}
    lost = [w for t, k, w in before if k == "task" and w not in titles]
    assert not lost, f"{len(lost)} acknowledged tasks are not in the backup: {lost[:5]}"
    chat = next((clean / "projects" / "alpha-labs" / "chats").glob(f"cc-{SESSION[:8]}*/chat.md"))
    text = chat.read_text(encoding="utf-8")
    gone = [w for t, k, w in before if k == "message" and w not in text]
    assert not gone, f"{len(gone)} acknowledged messages are not in the backup: {gone[:5]}"

    # The restored folder reads whole and takes a new write.
    with TestClient(create_app(data_root=clean, watch=False, run_monitor=False, autoinstall_skills=False),
                    base_url="http://127.0.0.1:8123") as c:
        doctor = c.get("/api/doctor").json()
        errors = [i for i in doctor.get("issues", []) if i.get("severity") == "error"]
        assert not errors, errors[:3]
        c.get("/api/health", headers={"Sec-Fetch-Site": "same-origin"})     # the page's cookie, kept by the client
        r = c.post("/api/tasks", json={"project": "alpha-labs", "title": "after the restore", "status": "todo", "actor": "operator"})
        assert r.status_code in (200, 201), r.text
