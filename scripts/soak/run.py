#!/usr/bin/env python3
r"""The soak test: a release candidate under steady work for hours.

    backend/.venv/bin/python scripts/soak/run.py              # 24 hours (Windows: backend\.venv\Scripts\python.exe)
    backend/.venv/bin/python scripts/soak/run.py --hours 0.5  # a short run, to try it

Everything happens in one folder of its own (a copy of the demo data, a
home folder, a free port): the operator's server and data are never touched.
Simulated agents write tasks through the API and chat messages through the
capture hook, in three projects; pages are read as a browser would. Every
30 minutes a backup; every 2 hours a restart (every second one a kill);
every 6 hours the latest backup is restored into a folder of its own and
checked. A ledger kept outside the server holds every acknowledged write.

Every minute: the server's memory, threads and open files, read latency,
errors. At the end, report.md says each threshold and whether it held:
nothing acknowledged lost, every restore complete, memory after warm-up
not growing, reads fast, no server errors.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
PY = BACKEND / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
HOOK = REPO / "scripts" / "hooks" / "claude-code-capture.py"
PROJECTS = ("alpha-labs", "beta-corp", "pdr-framework-dev")
READS = ("/api/snapshot", "/api/tasks?project=alpha-labs", "/api/standups/day?project=alpha-labs",
         "/api/agents/profiles", "/api/health")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Soak:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data, self.home, self.backups = root / "data", root / "home", root / "backups"
        shutil.copytree(REPO / "fixtures", self.data)
        self.home.mkdir()
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.cookie = ""
        self.lock = threading.Lock()
        self.ledger = open(root / "ledger.jsonl", "a", encoding="utf-8")
        self.samples = open(root / "samples.tsv", "a", encoding="utf-8")
        self.samples.write("t\trss_mb\tthreads\tfiles\tread_p50_ms\tread_p95_ms\twrites\terrors\n")
        self.reads: list[float] = []
        self.writes = 0
        self.errors: list[str] = []
        self.restores: list[str] = []
        self.stop = threading.Event()

    # ------------------------------------------------------------ the server

    def start(self) -> None:
        env = {**os.environ, "SP_DATA_ROOT": str(self.data), "SP_PORT": str(self.port), "SP_EXAMPLES": "0",
               "SP_LOG_DIR": str(self.root / "logs"), "SP_BACKUP_ROOT": str(self.backups),
               "HOME": str(self.home), "USERPROFILE": str(self.home), "MALLOC_ARENA_MAX": "2"}
        log = open(self.root / "server.log", "a", encoding="utf-8")
        self.proc = subprocess.Popen([str(PY), "-m", "backend.server"], cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
        for _ in range(240):
            try:
                req = urllib.request.Request(self.url + "/api/health", headers={"Sec-Fetch-Site": "same-origin"})
                with urllib.request.urlopen(req, timeout=3) as r:
                    self.cookie = (r.headers.get("Set-Cookie") or "").split(";", 1)[0] or self.cookie
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("the server did not start")

    def halt(self, kill: bool = False) -> None:
        if self.proc is None:
            return
        self.proc.kill() if kill else self.proc.terminate()
        try:
            self.proc.wait(60)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None

    def post(self, path: str, body: dict, timeout: float = 60) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": self.cookie})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def acked(self, kind: str, what: str, project: str) -> None:
        with self.lock:
            self.ledger.write(json.dumps({"t": time.time(), "kind": kind, "what": what, "project": project}) + "\n")
            self.ledger.flush()
            self.writes += 1

    # ------------------------------------------------------------ the agents

    def agent(self, n: int) -> None:
        rng = random.Random(n)
        session = f"50a{n:05d}-0000-4000-8000-{n:012d}"
        folder = self.root / f"work-{n}"
        folder.mkdir(exist_ok=True)
        project = PROJECTS[n % len(PROJECTS)]
        i = 0
        while not self.stop.is_set():
            i += 1
            try:
                if rng.random() < 0.5:
                    title = f"soak {n}-{i}"
                    self.post("/api/tasks", {"project": project, "title": title, "status": "todo", "actor": "operator"})
                    self.acked("task", title, project)
                else:
                    text = f"soak message {n}-{i}"
                    ok = all(subprocess.run(
                        [str(PY), str(HOOK), "--project", project, "--data-root", str(self.data)],
                        input=json.dumps({"session_id": session, "cwd": str(folder), **payload}),
                        capture_output=True, text=True, encoding="utf-8", timeout=60).returncode == 0
                        for payload in ({"hook_event_name": "UserPromptSubmit", "prompt": text},
                                        {"hook_event_name": "Stop", "last_assistant_message": f"answer {i}"}))
                    if ok:
                        self.acked("message", text, project)
            except OSError:
                pass                      # a restart in progress: not acknowledged, not counted
            self.stop.wait(rng.uniform(2, 8))

    def reader(self) -> None:
        while not self.stop.is_set():
            for path in READS:
                t0 = time.perf_counter()
                try:
                    with urllib.request.urlopen(self.url + path, timeout=60) as r:
                        r.read()
                    with self.lock:
                        self.reads.append((time.perf_counter() - t0) * 1000)
                except urllib.error.HTTPError as exc:
                    if exc.code >= 500:
                        self.errors.append(f"{time.strftime('%H:%M')} {path} → {exc.code}")
                except OSError:
                    pass
            self.stop.wait(5)

    # ------------------------------------------------------------ measure

    def sample(self, t0: float) -> None:
        try:
            import psutil
        except ImportError:
            psutil = None
        rss = threads = files = 0.0
        if psutil and self.proc:
            try:
                p = psutil.Process(self.proc.pid)
                rss = p.memory_info().rss / 1e6
                threads = p.num_threads()
                files = p.num_handles() if hasattr(p, "num_handles") else p.num_fds()
            except psutil.Error:
                pass
        with self.lock:
            reads, self.reads = self.reads, []
            writes, self.writes = self.writes, 0
        p50 = statistics.median(reads) if reads else 0
        p95 = sorted(reads)[int(len(reads) * 0.95) - 1] if len(reads) > 1 else p50
        self.samples.write(f"{(time.time() - t0) / 3600:.3f}\t{rss:.0f}\t{threads:.0f}\t{files:.0f}\t{p50:.0f}\t{p95:.0f}\t{writes}\t{len(self.errors)}\n")
        self.samples.flush()

    def ledger_rows(self, until: float | None = None) -> list[dict]:
        with open(self.root / "ledger.jsonl", encoding="utf-8") as fh:
            return [r for r in map(json.loads, fh) if until is None or r["t"] < until]

    def check(self, root: Path, until: float | None = None) -> list[str]:
        """What the ledger holds that ``root`` does not."""
        with open(root / "tasks.csv", encoding="utf-8", newline="") as fh:
            titles = {r.get("title") for r in csv.DictReader(fh)}
        chats = "".join(p.read_text(encoding="utf-8", errors="replace") for p in root.glob("projects/*/chats/cc-50a*/chat.md"))
        return [r["what"] for r in self.ledger_rows(until)
                if (r["kind"] == "task" and r["what"] not in titles) or (r["kind"] == "message" and r["what"] not in chats)]

    def restore_check(self) -> None:
        sys.path.insert(0, str(BACKEND))
        from backend import backup
        archives = backup.list_archives(self.backups)
        if not archives:
            return
        latest = max(archives, key=lambda a: a.at)
        target = self.root / f"restored-{len(self.restores)}"
        target.mkdir()
        try:
            backup.restore(self.backups, latest.name, target)
            lost = self.check(target, until=latest.at.timestamp() - 5)
            self.restores.append(f"{latest.name}: {'complete' if not lost else f'{len(lost)} missing, e.g. {lost[:3]}'}")
        except Exception as exc:  # noqa: BLE001 — a failed restore is a finding
            self.restores.append(f"{latest.name}: restore failed: {exc}")
        finally:
            shutil.rmtree(target, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--agents", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="keep the folder at the end")
    args = ap.parse_args()
    root = Path(tempfile.mkdtemp(prefix="sp-soak-")).resolve()
    print(f"soak in {root} for {args.hours} h", flush=True)
    s = Soak(root)
    s.start()
    workers = [threading.Thread(target=s.agent, args=(i,), daemon=True) for i in range(args.agents)]
    workers.append(threading.Thread(target=s.reader, daemon=True))
    for w in workers:
        w.start()
    t0 = time.time()
    end = t0 + args.hours * 3600
    every = {"backup": 1800.0, "restart": 7200.0, "restore": 21600.0}
    scale = min(1.0, args.hours / 24)           # a short run does each at least once
    every = {k: max(120.0, v * scale) for k, v in every.items()}
    due = {k: t0 + v for k, v in every.items()}
    restarts = 0
    try:
        while time.time() < end:
            s.sample(t0)
            now = time.time()
            if now >= due["backup"]:
                try:
                    s.post("/api/backup/run", {"kind": "auto", "label": "soak"}, 600)
                except OSError as exc:
                    s.errors.append(f"backup: {exc}")
                due["backup"] = now + every["backup"]
            if now >= due["restore"]:
                s.restore_check()
                due["restore"] = now + every["restore"]
            if now >= due["restart"]:
                restarts += 1
                s.halt(kill=restarts % 2 == 0)
                s.start()
                due["restart"] = now + every["restart"]
            time.sleep(60 if args.hours >= 1 else 15)
    finally:
        s.stop.set()
        for w in workers:
            w.join(90)
        s.restore_check()
        s.halt()
    return report(s, root, args, restarts)


def report(s: Soak, root: Path, args: argparse.Namespace, restarts: int) -> int:
    rows = [ln.split("\t") for ln in (root / "samples.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    rss = [float(r[1]) for r in rows if float(r[1]) > 0]
    p95 = [float(r[5]) for r in rows if float(r[5]) > 0]
    warm = rss[len(rss) // 6:] or rss                       # after the first sixth
    first, last = (statistics.median(warm[: max(1, len(warm) // 4)]), statistics.median(warm[-max(1, len(warm) // 4):])) if warm else (0, 0)
    lost = s.check(s.data)
    acked = len(s.ledger_rows())
    checks = [
        ("nothing acknowledged is lost", not lost, f"{acked} writes acknowledged, {len(lost)} missing" + (f": {lost[:3]}" if lost else "")),
        ("every restore is complete", bool(s.restores) and all("complete" in r for r in s.restores), "; ".join(s.restores) or "no restore ran"),
        ("memory after warm-up does not grow by more than 15 %", not warm or last <= first * 1.15 + 20, f"{first:.0f} MB → {last:.0f} MB, peak {max(rss, default=0):.0f} MB"),
        ("reads: p95 under 2 s", not p95 or statistics.median(p95) < 2000, f"median of the minutes' p95: {statistics.median(p95) if p95 else 0:.0f} ms, worst {max(p95, default=0):.0f} ms"),
        ("no server error", not s.errors, f"{len(s.errors)}: {s.errors[:5]}" if s.errors else "none"),
    ]
    text = [f"# Soak report\n\n{args.hours} h, {args.agents} agents, {restarts} restarts, folder {root}\n",
            "| Check | Held | Evidence |", "|---|---|---|"]
    text += [f"| {name} | {'yes' if ok else '**no**'} | {ev} |" for name, ok, ev in checks]
    text.append("\nEvery minute's numbers: samples.tsv (hours, RSS MB, threads, open files, read p50/p95 ms, writes, errors).")
    (root / "report.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text), flush=True)
    if not args.keep and all(ok for _, ok, _ in checks):
        for name in ("data", "home", "backups"):
            shutil.rmtree(root / name, ignore_errors=True)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
