#!/usr/bin/env python3
"""Show that a change of code changed nothing a reader sees: the same data,
the start's backfills, the same answers, the same files after (tk_d1d25a4d,
the no-change proof of the chat-folder resolver; kept for its next steps).

    python3 scripts/layout_proof.py run --source <data root> --commit <sha> --port 8191 --out <dir>
    python3 scripts/layout_proof.py run --source <data root> --repo <checkout> --port 8192 --out <dir>
    python3 scripts/layout_proof.py diff <out a> <out b>

The source must be a frozen snapshot: copy the live data root once
(``cp -a``), then point every run at that copy. Runs taken straight from a
live root see different data each time, and their diff shows the writes of
the agents in between, not the code.

``run``:
1. copies the source with ``cp -a`` into ``<out>/data`` (``<out>`` must not
   exist, nor lie inside the source: a copy is never reused). The source is
   only read. With ``--commit`` the code is a git worktree under ``<out>``,
   removed again (and ``git worktree prune``) when the run ends;
2. runs that code's start backfills (``server._backfill_from_logs``) in the
   foreground, twice; the second run must leave the copy's files as the first
   left them (path and sha256, ``*.lock`` left out);
3. starts that code's server on the copy at ``--port``, a sandbox
   (``SP_SANDBOX=1``) whose loop that types waiting messages into terminals is
   turned off, and checks ``/api/health`` names the copy;
4. dumps the answers a reader sees (``dump.json``) and the output of
   ``doctor.py`` and ``check_consistency.py``; the copy's path, the code's
   path and the port are replaced by placeholders, and what differs between
   two runs of the same code is evened out (found by diffing two such runs):
   a time stamp inside the run's own window (the backfills' and the server's
   writes, file times of what they wrote) reads ``<RUN-TIME>``, the fields
   in ``VOLATILE`` are left out, the server's memory line and the log lines
   in the scripts' output are dropped;
5. stops the server and records the copy's files (``tree-after.json``).

``diff`` compares two such folders: the dumps, the trees after the
backfills, and the trees after the server. A file whose sha256 differs after
the server is compared again with each run's own time stamps evened out the
same way; it counts only if it still differs. Exit code 1 when anything
differs.
A whole run takes the server's start plus a minute or two.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from backend import chatstore  # noqa: E402 — the proof's own listing of the copy
MAIN_VENV_PY = REPO / "backend" / ".venv" / "bin" / "python"
HEALTH_TIMEOUT_S = 180
HEALTH_POLL_INTERVAL_S = 0.5
REQUEST_TIMEOUT_S = 300
STOP_TIMEOUT_S = 20
SEARCH_WORDS = ("chatstore", "standup", "usage", "terminal", "task", "capture", "merkhet", "hook", "scan", "codex")
STANDUP_DAYS = 3

# Keys whose values differ between two runs of the same code on the same
# data (found by diffing two such runs): the age of the view, the run's own
# clock. Left out of every dump, at any depth.
VOLATILE = {
    "view_age_ms",   # the age of the view at the moment of asking
    "age_min",       # minutes from a moment to now: one run can be a minute later
}
MEMORY_RE = re.compile(r"\d+ MB now, peak \d+ MB, up [\d.]+ h")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?")
RUN_TIME = "<RUN-TIME>"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def tree(root: Path) -> dict[str, str]:
    """path → sha256 of every file under ``root`` (a symlink → its target),
    ``*.lock`` left out."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames) + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if name.endswith(".lock"):
                continue
            if p.is_symlink():
                out[rel] = "-> " + os.readlink(p)
                continue
            h = hashlib.sha256()
            try:
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
            except OSError as exc:
                out[rel] = f"unreadable: {exc}"
                continue
            out[rel] = h.hexdigest()
    return out


def tree_diff(a: dict[str, str], b: dict[str, str]) -> list[str]:
    out = [f"only in a: {k}" for k in sorted(a.keys() - b.keys())]
    out += [f"only in b: {k}" for k in sorted(b.keys() - a.keys())]
    out += [f"changed: {k}" for k in sorted(a.keys() & b.keys()) if a[k] != b[k]]
    return out


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The code under test
# ---------------------------------------------------------------------------

def checkout(commit: str, out: Path) -> Path:
    """A detached worktree of ``commit`` under ``out`` (the repository's own
    git; nothing of the current checkout changes)."""
    dest = out / "code"
    subprocess.run(["git", "-C", str(REPO), "worktree", "add", "--detach", str(dest), commit],
                   check=True, capture_output=True, text=True)
    return dest


def env_for(code: Path, copy: Path, port: int, out: Path) -> dict[str, str]:
    env = dict(os.environ)
    for k in ("SP_DATA_ROOT", "SCAN_DATA_ROOT", "DATA_ROOT", "SP_SMART_TIMER", "PYTHONPATH"):
        env.pop(k, None)
    env.update(SP_DATA_ROOT=str(copy), SP_SANDBOX="1", SP_LOG_FILE="0", SP_PORT=str(port), PORT=str(port),
               HOST="127.0.0.1", SP_BACKUP_ROOT=str(out / "backups"), TMPDIR=str(out / "tmp"),
               PYTHONPATH=str(code / "backend"), PYTHONDONTWRITEBYTECODE="1")
    return env


BACKFILL = """
import logging, sys
from pathlib import Path
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(name)s %(levelname)s %(message)s")
import backend
assert Path(backend.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve()), backend.__file__
from backend import server
server._backfill_from_logs(Path(sys.argv[1]))
"""

SERVE = """
import sys
from pathlib import Path
import backend
assert Path(backend.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve()), backend.__file__
from backend import msgdeliver, server
# The copy's waiting messages name the operator's real terminals: never typed.
msgdeliver.retry_waiting = lambda data_root: 0
import uvicorn
app = server.create_app(Path(sys.argv[1]), autoinstall_skills=False, run_monitor=False)
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[3]), log_config=None)
"""


# ---------------------------------------------------------------------------
# Asking the server
# ---------------------------------------------------------------------------

class Client:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.cookie = ""

    def _open(self, path: str) -> tuple[int, bytes, str]:
        headers = {"Sec-Fetch-Site": "same-origin"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
                if not self.cookie and r.headers.get("Set-Cookie"):
                    self.cookie = r.headers["Set-Cookie"].split(";", 1)[0]
                return r.status, r.read(), r.headers.get("Content-Type") or ""
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type") or ""

    def get(self, path: str) -> Any:
        status, body, ctype = self._open(path)
        text = body.decode("utf-8", "replace")
        if "json" in ctype:
            try:
                return {"status": status, "json": json.loads(text)}
            except ValueError:
                pass
        return {"status": status, "text": text}


def wait_health(client: Client, proc: subprocess.Popen, copy: Path) -> dict:
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"the server ended with {proc.returncode} before it answered")
        try:
            got = client.get("/api/health")
            if got["status"] == 200:
                root = got["json"]["data_root"]
                if Path(root).resolve() != copy.resolve():
                    raise SystemExit(f"the server serves {root}, not the copy {copy}")
                return got["json"]
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    raise SystemExit("the server did not answer /api/health")


def _in_run(stamp: float, window: tuple[float, float]) -> bool:
    return window[0] <= stamp <= window[1]


def _iso_in_run(text: str, window: tuple[float, float]) -> bool:
    try:
        return _in_run(datetime.fromisoformat(text).timestamp(), window)
    except ValueError:
        return False


def even_out(value: Any, window: tuple[float, float]) -> Any:
    """``value`` with the run's own clock taken out: VOLATILE keys left out,
    a time stamp inside ``window`` (epoch seconds, or an ISO string) made
    RUN_TIME, the server's memory line made a mark."""
    if isinstance(value, dict):
        # A plan limit's window: "in" is the time from now to its resets_at.
        skip = VOLATILE | ({"in"} if "resets_at" in value else set())
        return {k: even_out(v, window) for k, v in value.items() if k not in skip}
    if isinstance(value, list):
        return [even_out(v, window) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _in_run(float(value), window):
        return RUN_TIME
    if isinstance(value, str):
        if ISO_RE.fullmatch(value) and _iso_in_run(value, window):
            return RUN_TIME
        return MEMORY_RE.sub("<MEMORY>", value)
    return value


def even_out_text(text: str, window: tuple[float, float]) -> str:
    """A file's text with the run's ISO time stamps made RUN_TIME."""
    return ISO_RE.sub(lambda m: RUN_TIME if _iso_in_run(m.group(0), window) else m.group(0), text)


def no_log_lines(text: str) -> str:
    """The scripts' own output without the server's JSON log lines (each
    carries its moment and its duration)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith('{"ts": '))


def placeholders(text: str, swaps: list[tuple[str, str]]) -> str:
    for real, mark in swaps:
        text = text.replace(real, mark)
    return text


def dump(client: Client, copy: Path, checkup_cwd: str) -> dict[str, Any]:
    """Every answer a reader sees that reads chat folders."""
    out: dict[str, Any] = {}

    def ask(path: str) -> Any:
        got = client.get(path)
        out[path] = got
        return got

    q = urllib.parse.quote
    health = ask("/api/health")
    snapshot = ask("/api/snapshot")
    projects = sorted({str(p.get("code") or "") for p in (snapshot.get("json") or {}).get("projects") or []} - {""})
    if not projects:
        projects = sorted(p.name for p in (copy / "projects").iterdir() if p.is_dir())
    out["_projects"] = projects
    ask("/api/sessions?limit=5000")
    ask("/api/sessions?limit=5000&helpers=true")
    ask("/api/usage?project=all&range=today")
    ask("/api/usage?project=all&range=30d")
    ask("/api/timeline")
    ask("/api/heatmap")
    ask("/api/setup/info")
    ask("/api/capture/health")
    ask("/api/terminal/agents")
    ask(f"/api/checkup?cwd={q(checkup_cwd)}")
    for p in projects:
        ask(f"/api/project/{q(p)}")
        ask(f"/api/sessions?project={q(p)}&limit=5000")
        ask(f"/api/agents/profiles?project={q(p)}")
        ask(f"/api/usage?project={q(p)}&range=today")
        ask(f"/api/usage?project={q(p)}&range=30d")
        ask(f"/api/timeline?project={q(p)}")
        ask(f"/api/heatmap?project={q(p)}")
        ask(f"/api/calendar?project={q(p)}")
        ask(f"/api/timelapse?project={q(p)}")
        ask(f"/api/terminal/resumable?project={q(p)}")
        for days_ago in range(1, STANDUP_DAYS + 1):
            day = datetime.now() - timedelta(days=days_ago)
            ask(f"/api/standups/material?project={q(p)}&date={day:%y%m-%d}")
    for w in SEARCH_WORDS:
        ask(f"/api/search?q={q(w)}&limit=1000")
    # A few chats one by one: the usage of a chat, a Codex chat found by its
    # thread (whoami's crumb lookup).
    agents = sorted(a for _p, a, _f in chatstore.iter_chats(copy))
    for a in agents[:: max(1, len(agents) // 12)]:
        ask(f"/api/usage/chat/{q(a)}")
    codex = [f / "meta.json" for _p, a, f in chatstore.iter_chats(copy, has="meta.json") if a.startswith("codex-")]
    for meta in codex[:5]:
        try:
            thread = str(json.loads(meta.read_text(encoding="utf-8")).get("session_ref") or "")
        except (OSError, ValueError):
            continue
        if thread:
            ask(f"/api/whoami?cwd={q(checkup_cwd)}&thread={q(thread)}")
    del health
    return out


# ---------------------------------------------------------------------------
# run / diff
# ---------------------------------------------------------------------------

def remove_checkout(code: Path) -> None:
    """The worktree checkout() made, gone, and git's list of worktrees pruned."""
    subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(code)],
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(REPO), "worktree", "prune"], capture_output=True, text=True)


def run(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    source = Path(args.source).resolve()
    if out.is_relative_to(source):
        # The copy would copy itself, and the run would write into the source.
        raise SystemExit(f"{out} is inside the source {source}: put --out elsewhere")
    if out.exists():
        raise SystemExit(f"{out} exists: every run takes a fresh copy")
    out.mkdir(parents=True)
    (out / "tmp").mkdir()
    if args.repo:
        return _run(args, out, source, Path(args.repo).resolve())
    code = checkout(args.commit, out)
    try:
        return _run(args, out, source, code)
    finally:
        remove_checkout(code)


def _run(args: argparse.Namespace, out: Path, source: Path, code: Path) -> int:
    py = str(Path(args.python))
    sha = subprocess.run(["git", "-C", str(code), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(code), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    meta = {"source": str(source), "code": str(code), "sha": sha, "dirty": bool(dirty), "port": args.port,
            "started": datetime.now().isoformat(timespec="seconds")}
    write_json(out / "run.json", meta)
    began = time.time()
    print(f"[proof] code {code} at {sha[:8]}{' (dirty)' if dirty else ''}", flush=True)

    copy = out / "data"
    subprocess.run(["cp", "-a", str(source), str(copy)], check=True)
    print(f"[proof] copied {source} → {copy}", flush=True)
    env = env_for(code, copy, args.port, out)
    swaps = [(str(copy), "<ROOT>"), (str(code), "<CODE>"), (f":{args.port}", ":<PORT>"), (str(out), "<OUT>")]

    for n in (1, 2):
        t0 = time.monotonic()
        with open(out / f"backfill-{n}.log", "w", encoding="utf-8") as log:
            subprocess.run([py, "-c", BACKFILL, str(copy), str(code)], cwd=code / "backend", env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        write_json(out / f"tree-after-backfill-{n}.json", tree(copy))
        print(f"[proof] backfills run {n}: {time.monotonic() - t0:.0f} s", flush=True)
    again = tree_diff(json.loads((out / "tree-after-backfill-1.json").read_text(encoding="utf-8")),
                      json.loads((out / "tree-after-backfill-2.json").read_text(encoding="utf-8")))
    write_json(out / "backfill-rerun-diff.json", again)
    print(f"[proof] the second backfill changed {len(again)} file(s)", flush=True)

    log = open(out / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([py, "-c", SERVE, str(copy), str(code), str(args.port)], cwd=code / "backend", env=env,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        client = Client(args.port)
        wait_health(client, proc, copy)
        print("[proof] server up on the copy", flush=True)
        answers = dump(client, copy, args.checkup_cwd)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=STOP_TIMEOUT_S)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        log.close()
    window = (began, time.time() + 1)
    text = placeholders(json.dumps(even_out(answers, window), indent=1, sort_keys=True, ensure_ascii=False), swaps)
    (out / "dump.json").write_text(text + "\n", encoding="utf-8")
    bad = [k for k, v in answers.items() if isinstance(v, dict) and v.get("status", 200) >= 500]
    print(f"[proof] {len(answers)} answers dumped; 5xx: {bad or 'none'}", flush=True)

    for name, cmd in (("doctor", [py, str(code / "scripts" / "doctor.py"), "--root", str(copy), "--mvp-root", str(code),
                                  "--json", "--no-color"]),
                      ("check_consistency", [py, str(code / "scripts" / "check_consistency.py"), str(copy)])):
        got = subprocess.run(cmd, cwd=code / "backend", env=env, capture_output=True, text=True)
        (out / f"{name}.txt").write_text(
            placeholders(no_log_lines(f"exit {got.returncode}\n{got.stdout}\n{got.stderr}"), swaps), encoding="utf-8")
        print(f"[proof] {name}: exit {got.returncode}", flush=True)

    write_json(out / "tree-after.json", tree(copy))
    write_json(out / "run.json", {**meta, "window": [began, time.time() + 1]})
    print(f"[proof] done: {out}", flush=True)
    return 0


def _lines_diff(a: Path, b: Path) -> list[str]:
    """``diff -U2`` of two files (difflib takes minutes on a dump that differs much)."""
    got = subprocess.run(["diff", "-U2", str(a), str(b)], capture_output=True, text=True)
    return got.stdout.splitlines()


def diff(args: argparse.Namespace) -> int:
    a, b = Path(args.a), Path(args.b)
    found = 0
    for name in ("dump.json", "doctor.txt", "check_consistency.txt"):
        d = _lines_diff(a / name, b / name)
        found += bool(d)
        print(f"== {name}: {'no difference' if not d else f'{len(d)} diff lines'}")
        print("\n".join(d[: args.limit]))
    wa = tuple(json.loads((a / "run.json").read_text(encoding="utf-8"))["window"])
    wb = tuple(json.loads((b / "run.json").read_text(encoding="utf-8"))["window"])
    for name in ("tree-after-backfill-2.json", "tree-after.json"):
        d = tree_diff(json.loads((a / name).read_text(encoding="utf-8")), json.loads((b / name).read_text(encoding="utf-8")))
        clock = []
        # The copy as it is now is the copy after the server: a file is read
        # again only where it is still the version this tree recorded.
        ha, hb = (json.loads((x / name).read_text(encoding="utf-8")) for x in (a, b))
        na, nb = (json.loads((x / "tree-after.json").read_text(encoding="utf-8")) for x in (a, b))
        for line in [x for x in d if x.startswith("changed: ")]:
            rel = line.removeprefix("changed: ")
            if ha[rel] == na.get(rel) and hb[rel] == nb.get(rel):
                ta = (a / "data" / rel).read_text(encoding="utf-8", errors="replace")
                tb = (b / "data" / rel).read_text(encoding="utf-8", errors="replace")
                if even_out_text(ta, wa) == even_out_text(tb, wb):  # type: ignore[arg-type]
                    clock.append(rel)
                    d.remove(line)
        found += bool(d)
        print(f"== {name}: {'no difference' if not d else f'{len(d)} files differ'}"
              + (f" ({len(clock)} more differ only in the runs' own time stamps: {', '.join(clock)})" if clock else ""))
        print("\n".join(d[: args.limit]))
    for side in (a, b):
        again = json.loads((side / "backfill-rerun-diff.json").read_text(encoding="utf-8"))
        found += bool(again)
        print(f"== {side.name}: the second backfill changed {len(again)} file(s)")
        print("\n".join(again[: args.limit]))
    return 1 if found else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--source", required=True, help="the data root to copy (only read)")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--commit", help="a commit of this repository, checked out under --out")
    g.add_argument("--repo", help="a checkout to run as it is")
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--out", required=True, help="a folder that does not exist yet")
    r.add_argument("--python", default=str(MAIN_VENV_PY), help="the Python with the backend's packages")
    r.add_argument("--checkup-cwd", default=str(REPO), help="the folder /api/checkup and /api/whoami are asked about")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--limit", type=int, default=80, help="lines shown per part")
    args = p.parse_args()
    return run(args) if args.cmd == "run" else diff(args)


if __name__ == "__main__":
    sys.exit(main())
