"""Many capture hooks at once, as processes, and what the page then shows.

Claude Code runs one hook process per event, and an operator runs several
chats side by side, in more than one project. Each of those processes
writes the chat's files under its own lock while the server watches the
folder and rebuilds. This runs a real server on a copy of the demo data and
six chats at once (two projects), each a series of prompt and answer
events, with the hazards real sessions bring:

- the same prompt event delivered twice (a retried hook, an interrupt and a
  resend): one turn, not two;
- the same answer event delivered twice: the second has no open turn and
  is dropped;
- a hook process killed while it runs (the operator closes the terminal):
  nothing it leaves breaks the chat, and the next turn is recorded.

Then the server is asked, as the page asks: every acknowledged prompt is a
turn of its own chat exactly once, in its own project, with its own answer,
and no chat holds another's words.

Heavy (some 150 hook processes): CI runs it on Linux on every push and
on the three systems weekly (.github/workflows/weekly.yml).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.server import FIXTURES
from tests.test_backup_under_load import HOOK, Server

CHATS = [  # (session id, project): six chats, two projects, distinct agent ids
    (f"{n:x}{n:x}c0ffee-0000-4000-8000-00000000{n:04x}", "alpha-labs" if n % 2 else "beta-corp")
    for n in range(10, 16)
]
TURNS = 8

pytestmark = pytest.mark.heavy


def _agent(session: str) -> str:
    return f"cc-{session[:8]}"


def _event(root: Path, folder: Path, session: str, project: str, payload: dict, *, kill_after: float = 0.0) -> bool:
    """One hook process; with ``kill_after`` it is killed that many seconds
    in, as a closed terminal would."""
    out = subprocess.DEVNULL if kill_after else subprocess.PIPE
    proc = subprocess.Popen([sys.executable, str(HOOK), "--project", project, "--data-root", str(root)],
                            stdin=subprocess.PIPE, stdout=out, stderr=out)
    data = json.dumps({"session_id": session, "cwd": str(folder), **payload}).encode()
    if kill_after:
        assert proc.stdin is not None
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except OSError:
            pass
        time.sleep(kill_after)
        proc.kill()
        proc.wait()
        return False
    proc.communicate(data, timeout=60)
    return proc.returncode == 0


def _chat(root: Path, folder: Path, session: str, project: str, kill_at: int) -> list[tuple[str, str]]:
    """One chat's turns; the acknowledged (prompt, answer) pairs."""
    acked: list[tuple[str, str]] = []
    for n in range(TURNS):
        prompt, answer = f"prompt {session[:8]} {n}", f"answer {session[:8]} {n}"
        if n == kill_at:
            # A prompt whose hook is killed early, before or while it writes:
            # not acknowledged, so not required; it must break nothing.
            _event(root, folder, session, project, {"hook_event_name": "UserPromptSubmit",
                                                    "prompt": f"killed {session[:8]} {n}"}, kill_after=0.05 + 0.03 * n)
            _event(root, folder, session, project, {"hook_event_name": "Stop",
                                                    "last_assistant_message": f"killed answer {session[:8]} {n}"})
            continue
        event = {"hook_event_name": "UserPromptSubmit", "prompt": prompt}
        if n % 3 == 1:
            # The prompt delivered twice at the same moment (a retried hook):
            # two processes race for one turn.
            with ThreadPoolExecutor(2) as two:
                both = [two.submit(_event, root, folder, session, project, event) for _ in range(2)]
                ok = all(f.result() for f in both)
        else:
            ok = _event(root, folder, session, project, event)
        if n % 3 == 0 and n:   # the prompt again, after a moment, before the answer: one turn
            ok = _event(root, folder, session, project, event) and ok
        ok = _event(root, folder, session, project, {"hook_event_name": "Stop", "last_assistant_message": answer}) and ok
        if n % 3 == 2:   # the answer again, after the turn closed: dropped
            ok = _event(root, folder, session, project, {"hook_event_name": "Stop", "last_assistant_message": answer}) and ok
        if ok:
            acked.append((prompt, answer))
    return acked


def _get(server: Server, path: str) -> dict:
    req = urllib.request.Request(server.url + path, headers={"Cookie": server.cookie})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _turns_of(server: Server, project: str, agent: str) -> list[dict]:
    q = urllib.parse.urlencode({"project": project, "agent_id": agent})
    got = _get(server, f"/api/sessions?{q}")
    ids = [s["id"] for s in (got.get("sessions") if isinstance(got, dict) else got) or []]
    if not ids:
        return []
    turns = _get(server, "/api/sessions/turns?ids=" + urllib.parse.quote(",".join(ids)))["turns"]
    return [t for sid in ids for t in turns.get(sid, [])]


def test_six_chats_at_once_each_turn_once_in_its_own_chat(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    folders = {}
    for session, _project in CHATS:
        folders[session] = tmp_path / "work" / session[:8]
        folders[session].mkdir(parents=True)
    server = Server(root, tmp_path)
    try:
        with ThreadPoolExecutor(len(CHATS)) as pool:
            futures = {s: pool.submit(_chat, root, folders[s], s, p, kill_at=3 + i % 3)
                       for i, (s, p) in enumerate(CHATS)}
            acked = {s: f.result(timeout=600) for s, f in futures.items()}
        assert all(len(a) == TURNS - 1 for a in acked.values()), {s[:8]: len(a) for s, a in acked.items()}

        # The page reads what the watcher has rebuilt: wait for every chat's
        # turns to be in (a condition, with a deadline only for a hang).
        deadline = time.monotonic() + 120
        seen: dict[str, list[dict]] = {}
        while True:
            seen = {s: _turns_of(server, p, _agent(s)) for s, p in CHATS}
            texts = {s: " ".join(str(t.get("user") or "") for t in ts) for s, ts in seen.items()}
            if all(all(pr in texts[s] for pr, _a in acked[s]) for s, _p in CHATS) or time.monotonic() > deadline:
                break
            time.sleep(0.5)
    finally:
        server.stop()

    problems: list[str] = []
    for session, project in CHATS:
        users = [str(t.get("user") or "") for t in seen[session]]
        agents = [str(t.get("agent") or "") for t in seen[session]]
        for prompt, answer in acked[session]:
            n = sum(u.strip() == prompt for u in users)
            if n != 1:
                problems.append(f"{project}/{_agent(session)}: {prompt!r} is {n} turns")
                continue
            got = agents[next(i for i, u in enumerate(users) if u.strip() == prompt)]
            if got.strip() != answer:
                problems.append(f"{project}/{_agent(session)}: {prompt!r} answered {got[:80]!r}")
        for other, _p in CHATS:
            if other != session and any(other[:8] in u or other[:8] in a for u, a in zip(users, agents)):
                problems.append(f"{project}/{_agent(session)} holds words of {_agent(other)}")
        doubled = [a for a in agents if a.strip() and agents.count(a) > 1]
        if doubled:
            problems.append(f"{project}/{_agent(session)}: answers twice: {sorted(set(doubled))[:3]}")
        # The chat's files read whole: every line of the turn log is JSON.
        folder = root / "projects" / project / "chats" / _agent(session)
        for name in ("turns.jsonl", "work.jsonl"):
            f = folder / name
            if f.is_file():
                for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
                    try:
                        json.loads(line)
                    except ValueError:
                        problems.append(f"{folder.name}/{name} line {i + 1} is not JSON: {line[:80]!r}")
        if not (root / "projects" / project / "chats" / _agent(session)).is_dir():
            problems.append(f"{_agent(session)} has no folder in {project}")
    assert not problems, "\n".join(problems[:40])
    assert os.environ.get("SP_DATA_ROOT") != str(root)
