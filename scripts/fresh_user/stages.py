"""The stages of the fresh-user test, in the order a new user meets them:

install   clone the repository and start it the way the README says
pages     every page of the app opens, the example project among the projects
setup     the Setup page: a data folder, then a project, in the browser
wiring    what Setup wrote works with no agent: the hook captures a
          message, the MCP server starts, lists its tools and writes
agent     a real agent in the project: messages and # commands, each
          checked through the API (scenario.py)
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from common import REPO, WINDOWS, Report, Space, eventually, get, http, rows, wait_for

FRONTEND = REPO / "frontend"
#: npx is npx.cmd on Windows, which a program list does not find by its bare name.
NPX = shutil.which("npx") or "npx"
#: The server and everything it starts in a group of its own, for stop().
SPAWN: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}


def run_sh(*args: str) -> list[str]:
    """The README's start: ./run.sh on Linux and macOS, `sp run` on Windows."""
    return ["cmd", "/c", "sp.cmd", "run", *args] if WINDOWS else ["./run.sh", *args]


def sp_sh(*args: str) -> list[str]:
    """The launcher: ./sp.sh on Linux and macOS, sp.cmd on Windows."""
    return ["cmd", "/c", "sp.cmd", *args] if WINDOWS else ["./sp.sh", *args]


def venv_python(clone: Path) -> Path:
    return clone / "backend" / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def sh(args: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


# ------------------------------------------------------------------ the README

def readme(space: Space, report: Report) -> None:
    """The README's own words against the clone: what it names exists."""
    import re
    s = "readme"
    root = space.clone
    text = (root / "README.md").read_text(encoding="utf-8")
    code = "\n".join(re.findall(r"```(?:bash)?\n(.*?)```", text, re.S))

    links = [m for m in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text) if "://" not in m]
    gone = [m for m in links if not (root / m).exists()]
    report.add(s, f"every file the README links to exists ({len(links)})", not gone, ", ".join(gone))

    scripts = sorted(set(re.findall(r"(?m)^\s*(\./[\w./-]+)", code)))
    bad = [x for x in scripts if not (root / x).is_file() or not os.access(root / x, os.X_OK)]
    report.add(s, f"every script it tells you to run is there and can be run ({', '.join(scripts)})", bool(scripts) and not bad, ", ".join(bad))

    launcher = (root / "sp.py").read_text(encoding="utf-8")
    known = set(re.findall(r'"([a-z_]+)": cmd_', launcher))
    used = set(re.findall(r"(?m)^\s*\./sp\.sh (\w+)", code)) | set(re.findall(r"`sp (\w+)", text))
    report.add(s, f"every launcher command it names exists ({', '.join(sorted(used))})", bool(used) and used <= known, f"unknown: {sorted(used - known)}")

    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    npm_used = set(re.findall(r"npm run ([\w:-]+)", code)) | ({"test"} if re.search(r"npm test", code) else set())
    report.add(s, f"every npm script it names exists ({', '.join(sorted(npm_used))})", npm_used <= set(package), f"unknown: {sorted(npm_used - set(package))}")

    shipped = {p.name for p in (root / "templates" / "skills").iterdir() if p.is_dir()}
    # The skills are listed in docs/integration.md; the README links to it.
    text = text + (root / "docs" / "integration.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", text)) & (shipped | {w for w in re.findall(r"`([a-z]+(?:-[a-z]+)+)`", text) if w.split("-")[0] in ("make", "keep", "map", "update", "daily", "log", "write", "task", "finish", "sp")})
    report.add(s, "the skills it lists are the skills shipped", named == shipped, f"README only: {sorted(named - shipped)}; shipped only: {sorted(shipped - named)}")

    sources = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in [root / "sp.py", root / "frontend" / "vite.config.ts", *(root / "backend" / "backend").glob("*.py")])
    variables = set(re.findall(r"`((?:SP|SCAN|VITE)_[A-Z_]+|HOST|PORT)`", text))
    unread = sorted(v for v in variables if v not in sources)
    report.add(s, f"every setting it names is read by the code ({len(variables)})", not unread, ", ".join(unread))

    report.add(s, "it says what you need before the first command", bool(re.search(r"Python 3\.11\+", text)) and bool(re.search(r"Node 20\+", text))
               and text.index("Python 3.11+") < text.index("git clone"), "Python 3.11+ is not named before `git clone`, or Node 20+ nowhere")
    report.add(s, "the launcher asks for the same versions", "Python 3.11+" in launcher and "Node 20+" in launcher)


# ------------------------------------------------------------------ install

def install(space: Space, report: Report, source: Path, boot_seconds: int) -> subprocess.Popen | None:
    """A fresh clone, started with ./run.sh --prod in a home that has never
    seen Slightly Parallel. Returns the server process, or None when it did not start."""
    s = "install"
    dirty = sh(["git", "status", "--porcelain"], source).stdout.strip()
    if dirty:
        report.notes["uncommitted"] = "the working tree has uncommitted changes; the clone tests the last commit only"
        print("  note: uncommitted changes are not in the clone", flush=True)
    space.home.mkdir(parents=True)
    cloned = sh(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(space.clone)], space.root)
    if not report.add(s, "git clone", cloned.returncode == 0, cloned.stderr.strip()[-300:]):
        return None
    report.notes["commit"] = sh(["git", "rev-parse", "--short", "HEAD"], space.clone).stdout.strip()
    # A file that names a folder of the machine it was committed on is wrong on every other machine.
    mine = sh(["git", "grep", "-l", "-F", str(Path.home()), "--", ".", ":!*.test.*", ":!*/tests/*", ":!articles"], space.clone).stdout.split()
    report.add(s, "no committed file names a folder of this machine", not mine, f"{Path.home()} is in: {', '.join(mine)}")
    report.add(s, "the clone has no leftovers of a previous install",
               not (space.clone / "backend" / ".venv").exists() and not (space.clone / "frontend" / "node_modules").exists()
               and not (space.clone / ".env").exists())

    log = open(space.root / "server.log", "w", encoding="utf-8")
    start = time.time()
    proc = subprocess.Popen(run_sh("--prod"), cwd=space.clone, env=space.env(), stdout=log,
                            stderr=subprocess.STDOUT, **SPAWN)
    up = wait_for(space, "/api/health", boot_seconds, alive=lambda: proc.poll() is None)
    took = round(time.time() - start)
    report.notes["boot_seconds"] = took
    # On a failure the build's own error sits above the launcher's traceback: keep enough of the log to see it.
    tail = (space.root / "server.log").read_text(encoding="utf-8", errors="replace")[-4000:]
    if not report.add(s, f"./run.sh --prod answers on its port ({took} s)", up, tail):
        stop(proc)
        return None
    health = get(space, "/api/health")
    report.add(s, "the server is healthy", health.get("ok") is True and not health.get("load_errors"), json.dumps(health)[:300])
    # A new install keeps its data outside the clone, and plays the example
    # project into it in the background.
    report.add(s, "it starts in a new data folder, outside the clone", Path(str(health.get("data_root", ""))).name == ".slightly-parallel", str(health.get("data_root")))
    page = http(space.url + "/")
    report.add(s, "the built app is served at /", isinstance(page, str) and 'id="root"' in page and "/assets/" in page, str(page)[:200])
    t0 = time.time()
    state: dict = {}
    while time.time() - t0 < 300:
        state = get(space, "/api/example")
        if not state.get("building"):
            break
        time.sleep(3)
    report.notes["example_seconds"] = round(time.time() - t0)
    report.add(s, f"the example project is played ({report.notes['example_seconds']} s)",
               state.get("present") is True and not state.get("error"), json.dumps(state)[:300])
    snap = get(space, "/api/snapshot")
    report.add(s, "the example project is in the app", state.get("project") in {p.get("code") for p in rows(snap, "projects")})
    standups = rows(get(space, f"/api/standups?project={state.get('project')}&limit=200"), "standups")
    newest = max((str(r.get("for_date") or r.get("created_date") or "") for r in standups), default="")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%y%m-%d")
    before = (datetime.now() - timedelta(days=3)).strftime("%y%m-%d")
    report.add(s, "its newest standup is from the last days, not from the month it was written in",
               before <= newest <= yesterday, f"newest {newest}, yesterday {yesterday}")
    return proc


def start(space: Space, args: list[str], log_name: str, extra: dict[str, str] | None = None) -> subprocess.Popen:
    log = open(space.root / log_name, "w", encoding="utf-8")
    return subprocess.Popen(args, cwd=space.clone, env={**space.env(), **(extra or {})}, stdout=log,
                            stderr=subprocess.STDOUT, **SPAWN)


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if WINDOWS:
        # No process groups to signal: end the tree under the started process.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# ----------------------------------------------------- the browser (Playwright)

def playwright(space: Space, report: Report, stage: str, name: str, args: list[str], extra: dict[str, str] | None = None) -> bool:
    """Run browser tests from this repository against the server under test.
    The browser belongs to whoever runs the test, so it keeps the real home."""
    if not (FRONTEND / "node_modules" / "@playwright").is_dir():
        return report.add(stage, name, False, "Playwright is not installed here: cd frontend && npm install && npx playwright install chromium")
    env = {**os.environ, "SP_E2E_URL": space.url, **(extra or {})}
    p = sh([NPX, "playwright", "test", *args, "--reporter=line"], FRONTEND, env, timeout=1200)
    out = (p.stdout + p.stderr).strip()
    spec = next((a for a in reversed(args) if a.endswith(".ts")), "run").split("/")[-1].removesuffix(".spec.ts")
    (space.root / f"playwright-{stage.replace(':', '-')}-{spec}.log").write_text(out, encoding="utf-8")
    last = [line for line in out.splitlines() if line.strip()][-12:]
    return report.add(stage, name, p.returncode == 0, "\n      ".join(last))


def pages(space: Space, report: Report) -> None:
    playwright(space, report, "pages", "every page opens without a crash", ["tests/e2e/every-page.spec.ts"])


# -------------------------------------------------------------------- setup

def make_sample(space: Space) -> None:
    """The user's own project: a small git repository."""
    space.sample.mkdir(parents=True, exist_ok=True)
    (space.sample / "README.md").write_text("# calc\n\nA small calculator module.\n", encoding="utf-8")
    (space.sample / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    env = space.env()
    sh(["git", "init", "-q"], space.sample, env)
    # The identity is the repository's own: an agent's commits need one.
    sh(["git", "config", "user.name", "Fresh User"], space.sample, env)
    sh(["git", "config", "user.email", "fresh@example.com"], space.sample, env)
    sh(["git", "add", "-A"], space.sample, env)
    sh(["git", "commit", "-qm", "first commit"], space.sample, env)


def setup(space: Space, report: Report, code: str, tool_names: list[str]) -> None:
    s = "setup"
    space.data.mkdir(parents=True, exist_ok=True)
    make_sample(space)
    playwright(space, report, s, "the Setup page: data folder, then the project", ["--config", "playwright.fresh.config.ts", "setup.spec.ts"], {
        "FRESH_DATA": str(space.data), "FRESH_PROJECT": str(space.sample), "FRESH_CODE": code,
        "FRESH_TOOLS": ",".join(tool_names),
        # Playing the example into a second folder is slower on Windows (many small files).
        "FRESH_EXAMPLE_SECONDS": "900" if WINDOWS else "240",
    })
    started = report.notes.get("example_seconds")
    report.notes["example_in_new_folder"] = get(space, "/api/example")
    if started is not None:
        report.notes["example_seconds_first"] = started
    health = get(space, "/api/health")
    report.add(s, "the server reads the new data folder", health.get("data_root") == str(space.data), str(health.get("data_root")))
    envfile = space.clone / ".env"
    saved = envfile.read_text(encoding="utf-8") if envfile.is_file() else ""
    report.add(s, "the data folder is remembered in .env", "SP_DATA_ROOT=" in saved and str(space.data) in saved, saved[:200])
    info = get(space, "/api/setup/info")
    mine = [i for i in info.get("integrations", []) if i.get("project") == code]
    report.add(s, "Setup lists the project as integrated, with hooks",
               bool(mine) and mine[0].get("status") == "fresh" and mine[0].get("hooks") is True, json.dumps(mine)[:300])
    report.add(s, "the project is in the app", any(p.get("code") == code for p in rows(get(space, "/api/snapshot"), "projects")))

    agents_md = (space.sample / "AGENTS.md").read_text(encoding="utf-8") if (space.sample / "AGENTS.md").is_file() else ""
    report.add(s, "AGENTS.md has the Slightly Parallel section", "slightly-parallel:begin" in agents_md and f"`{code}`" in agents_md)
    report.add(s, "the contract it points at exists", Path(info.get("contract_path", "/nonexistent")).is_file() and str(info.get("contract_path")) in agents_md)
    report.add(s, "AGENTS.md names this server", space.url in agents_md, f"expected {space.url}")
    claude_md = space.sample / "CLAUDE.md"
    report.add(s, "CLAUDE.md imports AGENTS.md", claude_md.is_file() and "@AGENTS.md" in claude_md.read_text(encoding="utf-8"))
    report.add(s, "the README's first line still stands", (space.sample / "README.md").read_text(encoding="utf-8").startswith("# calc"))
    skills = sorted(p.name for p in (space.home / ".claude" / "skills").glob("*") if p.is_dir()) if (space.home / ".claude" / "skills").is_dir() else []
    report.notes["skills_in_home"] = skills
    report.add(s, "the built-in skills are in the home folder", "make-a-scan" in skills and "write-a-task" in skills, f"found {skills}")
    installs = rows(json.loads((space.data / "skill_installs.json").read_text(encoding="utf-8")) if (space.data / "skill_installs.json").is_file() else {}, "installs")
    report.add(s, "the new data folder knows where they are installed", any(i.get("path") == str(space.home) for i in installs), json.dumps(installs)[:200])
    changed = sh(["git", "status", "--porcelain"], space.clone).stdout.strip()
    report.add(s, "installing and setting up changed no file of the repository", not changed, changed[:400])


# ------------------------------------------------------------------- wiring

def hook_command(space: Space, folder: Path | None = None) -> str:
    cfg = json.loads(((folder or space.sample) / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    return cfg["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]


def fire_hook(space: Space, event: dict, days_ago: int = 0, folder: Path | None = None) -> subprocess.CompletedProcess:
    """Run the capture hook as the tool would. `days_ago` moves that one
    process's clock back (shifted/sitecustomize.py)."""
    env = space.env()
    if days_ago:
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent / "shifted")
        env["FRESH_SHIFT_SECONDS"] = str(-86400 * days_ago)
    return subprocess.run(hook_command(space, folder), shell=True, cwd=folder or space.sample, env=env,
                          input=json.dumps(event), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)


YESTERDAY_SESSION = "0a1b2c3d-0000-4000-8000-000000000002"


def yesterday(space: Space, report: Report, code: str) -> bool:
    """A chat that happened yesterday, so today's first message owes a standup."""
    turns = [
        ("Set up the repository: one module, calc.py, with add(a, b).", "calc.py is in place with add(a, b), and the first commit is made."),
        ("Should add accept floats as well as integers?", "Yes: add works on any numbers, so it stays as written. No change was needed."),
        ("Write down in the README what the module is.", "The README now says: a small calculator module."),
    ]
    for asked, answered in turns:
        fire_hook(space, {"hook_event_name": "UserPromptSubmit", "session_id": YESTERDAY_SESSION, "cwd": str(space.sample), "prompt": asked}, days_ago=1)
        fire_hook(space, {"hook_event_name": "Stop", "session_id": YESTERDAY_SESSION, "cwd": str(space.sample), "last_assistant_message": answered}, days_ago=1)
    chat = space.data / "projects" / code / "chats" / f"cc-{YESTERDAY_SESSION[:8]}" / "chat.md"
    text = chat.read_text(encoding="utf-8") if chat.is_file() else ""
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    return report.add("wiring", "a chat dated yesterday is captured (for the standup)", text.count(f"· {day}T") >= 3, text[:300])


def mcp_call(space: Space, messages: list[dict]) -> list[dict]:
    """Start the MCP server the way a tool does (from .mcp.json, in the
    project folder), send the requests, return the answers."""
    entry = json.loads((space.sample / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["slightly-parallel"]
    env = {**space.env(), **entry.get("env", {})}
    text = "".join(json.dumps(m) + "\n" for m in messages)
    p = subprocess.run([entry["command"], *entry["args"]], cwd=space.sample, env=env, input=text,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    out = [json.loads(line) for line in p.stdout.splitlines() if line.strip().startswith("{")]
    if not out and p.stderr:
        raise RuntimeError(p.stderr.strip()[-400:])
    return out


def wiring(space: Space, report: Report, code: str) -> None:
    s = "wiring"
    session = "f0e1d2c3-0000-4000-8000-000000000001"
    agent = f"cc-{session[:8]}"
    try:
        command = hook_command(space)
    except (OSError, KeyError, ValueError) as exc:
        report.add(s, "the hook is in .claude/settings.local.json", False, str(exc))
        return
    parts = [p.strip('"') for p in shlex.split(command, posix=not WINDOWS)]
    script = next((part for part in parts if part.endswith("claude-code-capture.py")), "")
    report.add(s, "the hook script is inside the clone", script.startswith(str(space.clone)) and Path(script).is_file(), script)

    def fire(event: dict) -> subprocess.CompletedProcess:
        return fire_hook(space, event)

    asked = "Wiring check: please read calc.py."
    first = fire({"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": str(space.sample), "prompt": asked})
    report.add(s, "the hook runs on a message", first.returncode == 0, (first.stderr or first.stdout)[-300:])
    report.add(s, "it tells the agent its project and id", f"project {code}" in first.stdout and agent in first.stdout, first.stdout[:300])
    chat = space.data / "projects" / code / "chats" / agent / "chat.md"
    report.add(s, "the message is in the chat file", chat.is_file() and asked in chat.read_text(encoding="utf-8"), str(chat))
    fire({"hook_event_name": "Stop", "session_id": session, "cwd": str(space.sample),
          "last_assistant_message": "calc.py has one function, add."})
    report.add(s, "the reply is in the chat file", chat.is_file() and "one function, add" in chat.read_text(encoding="utf-8"))
    shown = eventually(lambda: any(a.get("agent_id") == agent for a in rows(get(space, f"/api/project/{code}"), "agents")))
    report.add(s, "the app shows the chat as an agent", shown, json.dumps(get(space, f"/api/project/{code}"))[:300])

    try:
        answers = mcp_call(space, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fresh-user", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "write_entry", "arguments": {
                "lens": "decision", "fields": {"decision": "The wiring check writes one decision.", "why": "To prove an entry reaches the ledger.", "weight": "minor"}}}},
        ])
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        report.add(s, "the MCP server starts from .mcp.json", False, str(exc))
        return
    by_id = {a.get("id"): a for a in answers}
    report.add(s, "the MCP server starts from .mcp.json", 1 in by_id and "result" in by_id[1], json.dumps(answers)[:300])
    names = [t.get("name") for t in by_id.get(2, {}).get("result", {}).get("tools", [])]
    report.add(s, "it offers its tools", {"write_entry", "task_report", "task_done", "interpret"} <= set(names), f"{len(names)} tools: {names[:8]}")
    wrote = by_id.get(3, {}).get("result", {})
    said = " ".join(c.get("text", "") for c in wrote.get("content", []))
    report.add(s, "write_entry writes a decision", wrote.get("isError") is False, said[:400])
    decisions = rows(get(space, f"/api/decisions?project={code}"), "decisions")
    report.add(s, "the decision is in the ledger, stamped with the agent",
               any(d.get("agent_id") == agent and "wiring check" in str(d.get("decision_text", "")).lower() for d in decisions),
               json.dumps(decisions)[:300])
    direct = None
    try:
        http(space.url + "/api/decisions", {"project": code, "agent_id": agent, "decision_text": "Written around MCP."})
        direct = "accepted"
    except Exception as exc:  # the refusal is the pass
        direct = str(exc)
    report.add(s, "a write that names an agent and skips MCP is refused", direct != "accepted", str(direct)[:200])


# ----------------------------------------------------------------- terminal

def terminal(space: Space, report: Report, code: str, agent: str, session: str, task: str) -> None:
    """Resume and Start, in Slightly Parallel's own terminal. The command is typed and
    left waiting for Enter, so no agent is started and nothing is spent."""
    s = "terminal"
    if not shutil.which("tmux"):
        report.notes[s] = "skipped: tmux is not installed"
        print("  skipped: tmux is not installed", flush=True)
        return
    try:
        http(space.url + "/api/settings", {"values": {"terminal.enabled": True, "terminal.launch": "type"}})
    except Exception as exc:
        report.add(s, "the terminal can be switched on in Settings", False, str(exc))
        return
    state = get(space, "/api/terminal/state")
    report.add(s, "the terminal is on, kept in tmux", state.get("enabled") is True and bool(state.get("tmux")), json.dumps(state)[:200])

    def opened(body: dict) -> dict:
        try:
            return http(space.url + "/api/terminal/sessions", body).get("session", {})
        except Exception as exc:
            return {"error": str(exc)}

    def screen(sid: str) -> str:
        try:
            got = http(space.url + f"/api/terminal/sessions/{sid}/capture", {})
            return str(got.get("text") or got.get("lines") or got)
        except Exception as exc:
            return str(exc)

    shell = opened({"kind": "shell", "project": code})
    if report.add(s, "a shell opens in the project's folder", shell.get("cwd") == str(space.sample), json.dumps(shell)[:300]):
        http(space.url + f"/api/terminal/sessions/{shell['id']}/type", {"text": "echo fresh-$((6*7))", "enter": True})
        seen = eventually(lambda: "fresh-42" in screen(shell["id"]), 10)
        report.add(s, "a command typed in it runs, and its output can be copied", bool(seen), screen(shell["id"])[-300:])

    if agent:
        resume = opened({"kind": "resume", "agent": agent})
        report.add(s, "Resume opens where the chat started", resume.get("cwd") == str(space.sample), json.dumps(resume)[:300])
        report.add(s, "Resume uses the chat's own tool and session", session in str(resume.get("command", "")), str(resume.get("command")))
        if resume.get("id"):
            seen = eventually(lambda: session[:13] in screen(resume["id"]), 10)
            report.add(s, "the resume command is typed into the terminal", bool(seen), screen(resume["id"])[-300:])
            again = opened({"kind": "resume", "agent": agent})
            report.add(s, "a second Resume reuses the terminal", again.get("id") == resume.get("id"))
    if task:
        st = opened({"kind": "start", "project": code, "task_id": task})
        cmd = str(st.get("command", ""))
        report.add(s, "Start on a task opens an agent with the task as its first message",
                   task in cmd and cmd.startswith("claude") and st.get("cwd") == str(space.sample), json.dumps(st)[:300])
    listing = rows(get(space, "/api/terminal/sessions"), "sessions")
    for row in listing:
        try:
            http(space.url + f"/api/terminal/sessions/{row['id']}/close", {})
        except Exception:
            pass
    left = eventually(lambda: not [r for r in rows(get(space, "/api/terminal/sessions"), "sessions") if r.get("state") != "ended"], 10)
    report.add(s, "closing the terminals leaves none running", bool(left))


# ------------------------------------------------- the second project, and leaving

def second_project(space: Space, report: Report, code: str) -> Path:
    """A second project, integrated through the API the page calls, with a
    note of what its folder held before."""
    folder = space.root / code
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notes.md").write_text("# notes\n\nA folder of notes.\n", encoding="utf-8")
    env = space.env()
    sh(["git", "init", "-q"], folder, env)
    sh(["git", "config", "user.name", "Fresh User"], folder, env)
    sh(["git", "config", "user.email", "fresh@example.com"], folder, env)
    sh(["git", "add", "-A"], folder, env)
    sh(["git", "commit", "-qm", "first commit"], folder, env)
    try:
        http(space.url + "/api/setup/integrate", {"project_code": code, "project_dir": str(folder)})
        ok = (folder / "AGENTS.md").is_file() and (folder / ".mcp.json").is_file()
    except Exception as exc:
        ok = False
        print(f"      {exc}", flush=True)
    report.add("setup", f"a second project ({code}) is integrated", ok)
    return folder


def disconnect(space: Space, report: Report, code: str) -> None:
    """Setup's Disconnect: the folder is as it was before Setup, the data stays."""
    s = "disconnect"
    folder = space.root / code
    playwright(space, report, s, "the Setup page: Disconnect the project", ["--config", "playwright.fresh.config.ts", "disconnect.spec.ts"], {"FRESH_CODE": code})
    info = get(space, "/api/setup/info")
    report.add(s, "Setup no longer lists it", not any(i.get("project") == code for i in info.get("integrations", [])))
    # Nothing Setup wrote is left; what the user or an agent made since stays.
    wrote = ("AGENTS.md", "CLAUDE.md", ".claude", ".mcp.json", ".codex", ".opencode", "opencode.json")
    left = [name for name in wrote if (folder / name).exists()]
    report.add(s, "nothing Setup wrote is left in its folder", not left, ", ".join(left))
    report.add(s, "the files that were there are untouched", (folder / "notes.md").read_text(encoding="utf-8").startswith("# notes"))
    report.add(s, "its data is kept", (space.data / "projects" / code).is_dir())


# ---------------------------------------------------- stopping and starting again

def restart(space: Space, report: Report, proc: subprocess.Popen | None, codes: list[str]) -> subprocess.Popen | None:
    """Stop the server and start it the same way: everything is still there."""
    s = "restart"
    before = get(space, "/api/health")
    stop(proc)
    time.sleep(1)
    start_at = time.time()
    proc = start(space, run_sh("--prod"), "server-2.log")
    up = wait_for(space, "/api/health", 600, alive=lambda: proc.poll() is None)
    took = round(time.time() - start_at)
    report.notes["second_boot_seconds"] = took
    if not report.add(s, f"./run.sh --prod starts again ({took} s)", up, (space.root / "server-2.log").read_text(encoding="utf-8", errors="replace")[-500:]):
        return None
    after = get(space, "/api/health")
    report.add(s, "it opens the data folder Setup chose, not the first one", after.get("data_root") == str(space.data), str(after.get("data_root")))
    report.add(s, "the projects and the agents are all there",
               after.get("projects") == before.get("projects") and after.get("agents") == before.get("agents"),
               f"before {before.get('projects')}/{before.get('agents')}, after {after.get('projects')}/{after.get('agents')}")
    have = {p.get("code") for p in rows(get(space, "/api/snapshot"), "projects")}
    report.add(s, "each project is still in the app", set(codes) <= have, f"{sorted(have)}")
    report.add(s, "the second start changed no file of the repository", not sh(["git", "status", "--porcelain"], space.clone).stdout.strip())
    return proc


def background(space: Space, report: Report, proc: subprocess.Popen | None) -> None:
    """`sp up`, `status`, `down`: the way to keep it running. Leaves the server stopped."""
    s = "background"
    stop(proc)
    time.sleep(1)
    env = space.env()
    up = sh(sp_sh("up"), space.clone, env, timeout=900)
    report.add(s, "sp up starts it and says healthy", up.returncode == 0 and "healthy" in up.stdout, (up.stdout + up.stderr)[-400:])
    status = sh(sp_sh("status"), space.clone, env)
    report.add(s, "sp status says running and healthy", status.returncode == 0 and "running" in status.stdout and "healthy" in status.stdout, status.stdout[-300:])
    report.add(s, "the app answers", wait_for(space, "/api/health", 5))
    again = sh(sp_sh("up"), space.clone, env)
    report.add(s, "a second sp up refuses, and says why", again.returncode != 0 and "already running" in (again.stdout + again.stderr), (again.stdout + again.stderr)[-300:])
    down = sh(sp_sh("down"), space.clone, env)
    report.add(s, "sp down stops it", down.returncode == 0 and "stopped" in down.stdout, (down.stdout + down.stderr)[-300:])
    report.add(s, "nothing answers on the port afterwards", not wait_for(space, "/api/health", 3))
    status = sh(sp_sh("status"), space.clone, env)
    report.add(s, "sp status fails when nothing runs", status.returncode != 0, status.stdout[-200:])


def dev(space: Space, report: Report, code: str) -> None:
    """`./run.sh` with no flag: the backend and the hot-reload UI. Expects the port free; leaves it free."""
    from common import free_port
    s = "dev"
    vite = free_port()
    proc = start(space, run_sh(), "server-dev.log", {"VITE_PORT": str(vite)})
    try:
        up = wait_for(space, "/api/health", 600, alive=lambda: proc.poll() is None)
        if not report.add(s, "./run.sh starts the backend", up, (space.root / "server-dev.log").read_text(encoding="utf-8", errors="replace")[-500:]):
            return
        page = ""
        for _ in range(60):
            try:
                page = str(http(f"http://127.0.0.1:{vite}/", timeout=3))
                break
            except Exception:
                time.sleep(1)
        report.add(s, "the hot-reload UI answers on its port", "/@vite/client" in page or "/src/main" in page, page[:200] or "no answer")
        playwright(space, report, s, "the app works through the hot-reload UI", ["--config", "playwright.fresh.config.ts", "dev.spec.ts"],
                   {"SP_E2E_URL": f"http://127.0.0.1:{vite}", "FRESH_CODE": code})
    finally:
        stop(proc)
        time.sleep(1)


# ------------------------------------------------------------ when things are wrong

def path_without(space: Space, *missing: str) -> str:
    """A PATH that has everything this machine has, except the named programs."""
    if WINDOWS:
        # Links need rights a user may not have: leave out every folder that holds one of them.
        exts = [e.lower() for e in os.environ.get("PATHEXT", ".EXE;.CMD;.BAT").split(";") if e] + [""]
        return os.pathsep.join(f for f in os.environ.get("PATH", "").split(os.pathsep)
                               if f and not any((Path(f) / (m + e)).is_file() for m in missing for e in exts))
    shim = space.root / ("path-without-" + "-".join(missing))
    if not shim.is_dir():
        shim.mkdir()
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                target, link = Path(folder) / name, shim / name
                if name in missing or link.exists() or link.is_symlink() or not os.access(target, os.X_OK) or target.is_dir():
                    continue
                try:
                    link.symlink_to(target)
                except OSError:
                    pass
    return str(shim)


def failures(space: Space, report: Report, running_port: bool) -> None:
    """What a new user can get wrong, or lack: each must end in words that
    say what to do, not in a stack trace or a silent wrong state."""
    from common import free_port
    import urllib.error
    s = "failures"
    env = space.env()

    def launcher(extra: dict[str, str], *args: str) -> tuple[int, str, float]:
        start_at = time.time()
        try:
            p = sh(run_sh(*args), space.clone, {**env, **extra}, timeout=90)
            return p.returncode, (p.stdout + p.stderr).strip(), time.time() - start_at
        except subprocess.TimeoutExpired as exc:
            return -1, f"still running after 90 s: {str(exc.stdout or '')[-200:]}", 90.0

    def plain(code: int, out: str, took: float, *words: str) -> tuple[bool, str]:
        ok = code not in (0, -1) and took < 30 and all(w in out for w in words) and "Traceback" not in out
        return ok, f"exit {code} after {round(took)} s: {out[-400:]}"

    if running_port:
        report.add(s, "a start on a port in use says so, with the way out", *plain(*launcher({}, "--prod"), "already in use", "SP_PORT"))
    other = str(free_port())
    no_node = {"PATH": path_without(space, "node", "npm", "npx", "corepack"), "SP_PORT": other, "PORT": other}
    if (space.clone / "frontend" / "dist" / "index.html").is_file():
        # A release ships the UI built: a start with no Node serves it.
        log = open(space.root / "server-no-node.log", "w", encoding="utf-8")
        proc = subprocess.Popen(run_sh("--prod"), cwd=space.clone, env={**env, **no_node}, stdout=log, stderr=subprocess.STDOUT, **SPAWN)
        up = wait_for(Space(space.root, int(other)), "/api/health", 60, alive=lambda: proc.poll() is None)
        stop(proc)
        out = (space.root / "server-no-node.log").read_text(encoding="utf-8", errors="replace")
        report.add(s, "a start with no Node serves the UI the release ships", up and "frontend/dist" in out.replace("\\", "/"), out[-400:])
    else:
        report.add(s, "a start with no Node says to install it", *plain(*launcher(no_node, "--prod"), "not found", "Node"))

    # A second server of the same clone, on a machine with no tmux, with a
    # data folder and a project whose names have spaces and non-Latin letters.
    odd_data = space.root / "данные и пробел"
    odd_project = space.root / "мой проект (2)"
    odd_data.mkdir(exist_ok=True)
    odd_project.mkdir(exist_ok=True)
    (odd_project / "заметки.md").write_text("# заметки\n", encoding="utf-8")
    port = free_port()
    second = Space(space.root, port)
    saved_env = (space.clone / ".env").read_text(encoding="utf-8") if (space.clone / ".env").is_file() else None
    py = venv_python(space.clone)
    log = open(space.root / "server-odd.log", "w", encoding="utf-8")
    proc = subprocess.Popen([str(py), "-m", "backend.server"], cwd=space.clone / "backend", stdout=log, stderr=subprocess.STDOUT,
                            **SPAWN,
                            env={**env, "PATH": path_without(space, "tmux"), "SP_PORT": str(port), "PORT": str(port),
                                 "HOST": "127.0.0.1", "SP_DATA_ROOT": str(odd_data)})
    try:
        up = wait_for(second, "/api/health", 60, alive=lambda: proc.poll() is None)
        if not report.add(s, "the server starts on a data folder with spaces and non-Latin letters", up,
                          (space.root / "server-odd.log").read_text(encoding="utf-8", errors="replace")[-400:]):
            return

        def refused(path: str, body: dict) -> tuple[bool, str]:
            """True when the server said no, in words."""
            try:
                got = http(second.url + path, body)
                return False, f"accepted: {json.dumps(got)[:200]}"
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", "replace")
                return 400 <= exc.code < 500 and len(text) > 20, f"{exc.code}: {text[:200]}"

        # Without tmux the terminal still works, and says what it is.
        http(second.url + "/api/settings", {"values": {"terminal.enabled": True}})
        state = get(second, "/api/terminal/state")
        report.add(s, "with no tmux the terminal says so", state.get("enabled") is True and not state.get("tmux"), json.dumps(state)[:200])
        try:
            shell = http(second.url + "/api/terminal/sessions", {"kind": "shell"}).get("session", {})
        except Exception as exc:
            shell = {"error": str(exc)}
        report.add(s, "and still opens a shell", shell.get("backend") == "plain", json.dumps(shell)[:200])

        # Setup, given wrong things.
        report.add(s, "Setup refuses a project folder that does not exist", *refused("/api/setup/integrate", {"project_code": "x", "project_dir": str(space.root / "nowhere")}))
        report.add(s, "Setup refuses a relative folder", *refused("/api/setup/integrate", {"project_code": "x", "project_dir": "some/folder"}))
        report.add(s, "Setup refuses a file given as the folder", *refused("/api/setup/integrate", {"project_code": "x", "project_dir": str(odd_project / "заметки.md")}))
        report.add(s, "Setup refuses a project code with spaces or capitals", *refused("/api/setup/integrate", {"project_code": "My App", "project_dir": str(odd_project)}))
        report.add(s, "Setup refuses a data folder that does not exist", *refused("/api/setup/data-root", {"path": str(space.root / "no-such-data")}))
        if WINDOWS:
            # A folder's mode does not stop a write on Windows; this one is checked on Linux and macOS.
            report.notes["unwritable_data_folder"] = "not checked on Windows"
        else:
            locked = space.root / "locked"
            locked.mkdir(exist_ok=True)
            locked.chmod(0o555)
            report.add(s, "Setup refuses a data folder it cannot write to", *refused("/api/setup/data-root", {"path": str(locked)}))
            locked.chmod(0o755)

        # The odd names, all the way through: integrate, the hook, the MCP server.
        try:
            http(second.url + "/api/setup/integrate", {"project_code": "odd", "project_dir": str(odd_project)})
            integrated = True
        except Exception as exc:
            integrated = False
            print(f"      {exc}", flush=True)
        if report.add(s, "a project in a folder with spaces and non-Latin letters is integrated", integrated):
            session = "0dd00000-0000-4000-8000-000000000003"
            asked = "Проверка: прочитай заметки."
            fired = fire_hook(space, {"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": str(odd_project), "prompt": asked}, folder=odd_project)
            chat = odd_data / "projects" / "odd" / "chats" / f"cc-{session[:8]}" / "chat.md"
            report.add(s, "its hook captures a message in another alphabet", fired.returncode == 0 and chat.is_file() and asked in chat.read_text(encoding="utf-8"),
                       (fired.stderr or fired.stdout)[-300:])
            try:
                entry = json.loads((odd_project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["slightly-parallel"]
                text = "".join(json.dumps(m) + "\n" for m in [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fresh-user", "version": "1"}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "write_entry", "arguments": {
                        "lens": "decision", "fields": {"decision": "Заметки остаются в одном файле.", "why": "Проверка записи.", "weight": "minor"}}}},
                ])
                p = subprocess.run([entry["command"], *entry["args"]], cwd=odd_project, env={**env, **entry.get("env", {})}, input=text,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                wrote = '"isError": false' in p.stdout or '"isError":false' in p.stdout
                detail = (p.stdout + p.stderr)[-300:]
            except Exception as exc:
                wrote, detail = False, str(exc)
            report.add(s, "its MCP server writes an entry in another alphabet", wrote, detail)
            got = rows(get(second, "/api/decisions?project=odd"), "decisions")
            report.add(s, "the entry reads back as written", any("Заметки остаются" in str(d.get("decision_text")) for d in got), json.dumps(got, ensure_ascii=False)[:200])
    finally:
        stop(proc)
        # The second server shares the clone: put its .env back as Setup left it.
        if saved_env is not None:
            (space.clone / ".env").write_text(saved_env, encoding="utf-8")


# ------------------------------------------------------------------- volume

def volume(space: Space, report: Report, tasks_n: int = 400, turns_n: int = 1500) -> None:
    """A month of work on three projects (the demo builder), then one very
    long chat and hundreds of tasks on top: the pages still open, the server
    still answers quickly, and a write does not get slower as the data grows."""
    from common import free_port
    s = "volume"
    env = space.env()
    py = venv_python(space.clone)
    target = space.root / "month"
    # The demo builder is a developer's tool: it needs the development packages.
    dev = sh([str(py), "-m", "pip", "install", "-q", "-r", str(space.clone / "backend" / "requirements-dev.txt")], space.clone, env, timeout=900)
    if not report.add(s, "the development packages install in the fresh environment", dev.returncode == 0, (dev.stdout + dev.stderr)[-400:]):
        return
    start_at = time.time()
    built = sh([str(py), str(space.clone / "scripts" / "demo" / "build_demo.py"), str(target), "--force"], space.clone, env, timeout=1800)
    if not report.add(s, f"a month of work is built ({round(time.time() - start_at)} s)", built.returncode == 0, (built.stdout + built.stderr)[-400:]):
        return
    data = target / "data"

    # One chat far longer than any in the month, written by the capture hook's own code.
    long_session = "10ng0000-0000-4000-8000-000000000004"
    writer = (
        "import sys; sys.path.insert(0, sys.argv[1]);\n"
        "from capture import TurnCapture\n"
        "cap = TurnCapture(sys.argv[2], 'shopfront', 'cc-' + sys.argv[3][:8])\n"
        "cap.note_origin('claude-code', sys.argv[3], sys.argv[4])\n"
        "for i in range(int(sys.argv[5])):\n"
        "    cap.full_turn(f'Step {i}: look at the order list again and say what changed. ' + 'detail ' * 40,\n"
        "                  f'Step {i}: the order list has a new column. ' + 'explanation ' * 120)\n"
    )
    wrote = sh([str(py), "-c", writer, str(space.clone / "scripts" / "hooks"), str(data), long_session,
                str(target / "repos" / "shopfront"), str(turns_n)], space.clone, env, timeout=900)
    chat = data / "projects" / "shopfront" / "chats" / f"cc-{long_session[:8]}" / "chat.md"
    size = chat.stat().st_size if chat.is_file() else 0
    report.add(s, f"a chat of {turns_n} turns is captured ({size // 1024} KB)", wrote.returncode == 0 and size > 500_000, (wrote.stderr or wrote.stdout)[-400:])

    port = free_port()
    big = Space(space.root, port)
    log = open(space.root / "server-volume.log", "w", encoding="utf-8")
    start_at = time.time()
    proc = subprocess.Popen([str(py), "-m", "backend.server"], cwd=space.clone / "backend", stdout=log, stderr=subprocess.STDOUT,
                            **SPAWN,
                            env={**env, "SP_PORT": str(port), "PORT": str(port), "HOST": "127.0.0.1",
                                 "SP_DATA_ROOT": str(data), "SP_SANDBOX": "1"})
    try:
        up = wait_for(big, "/api/health", 120, alive=lambda: proc.poll() is None)
        took = time.time() - start_at
        report.notes["volume_start_seconds"] = round(took, 1)
        if not report.add(s, f"the server starts on it ({took:.1f} s)", up and took < 30,
                          (space.root / "server-volume.log").read_text(encoding="utf-8", errors="replace")[-400:]):
            return

        # Hundreds of tasks through the API: the last writes are as quick as the first.
        times: list[float] = []
        for i in range(tasks_n):
            t0 = time.time()
            http(big.url + "/api/tasks", {"project": "shopfront", "title": f"Volume task {i}: check order {i}", "status": "todo", "actor": "operator"})
            times.append(time.time() - t0)
        first, last = sum(times[:30]) / 30, sum(times[-30:]) / 30
        report.notes["volume_task_write_ms"] = {"first_30": round(first * 1000), "last_30": round(last * 1000)}
        report.add(s, f"{tasks_n} tasks are written (a write: {first * 1000:.0f} ms at first, {last * 1000:.0f} ms at the end)", True)
        report.add(s, "a write stays under a second", last < 1.0, f"{last * 1000:.0f} ms")
        report.add(s, "a write does not get three times slower as the tasks grow", last < max(0.15, first * 3), f"{first * 1000:.0f} ms → {last * 1000:.0f} ms", soft=True)

        health = get(big, "/api/health")
        report.notes["volume"] = {"projects": health.get("projects"), "agents": health.get("agents"), "tasks": tasks_n + 75, "long_chat_kb": size // 1024}
        agent = f"cc-{long_session[:8]}"
        reads = {
            "the overview": "/api/snapshot",
            "the board's tasks": "/api/tasks?project=shopfront&limit=2000",
            "the project": "/api/project/shopfront",
            "the long chat": f"/api/chat/{agent}",
            "the long chat's agent": f"/api/agent/{agent}",
            "the statistics": "/api/stats/tasks",
            "the search": "/api/search?q=order",
            "the calendar": "/api/calendar?project=shopfront&from=2026-09-01&to=2026-09-30",
            "the time entries": "/api/time-entries?limit=5000",
        }
        slow: dict[str, int] = {}
        for name, path in reads.items():
            best = 99.0
            failed = ""
            for _ in range(3):
                t0 = time.time()
                try:
                    http(big.url + path, timeout=60)
                except Exception as exc:
                    failed = str(exc)
                best = min(best, time.time() - t0)
            slow[name] = round(best * 1000)
            report.add(s, f"{name} answers in {best * 1000:.0f} ms", not failed and best < 2.0, failed or f"{best * 1000:.0f} ms")
        report.notes["volume_read_ms"] = slow

        playwright(big, report, s, "every page opens on a month of data", ["tests/e2e/every-page.spec.ts"])
        playwright(big, report, s, "the heavy pages show their content in time", ["--config", "playwright.fresh.config.ts", "volume.spec.ts"],
                   {"FRESH_AGENT": agent, "FRESH_CODE": "shopfront"})
    finally:
        stop(proc)


# ------------------------------------------------------------------ upgrade

def upgrade(space: Space, report: Report, source: Path, base: str, boot_seconds: int) -> None:
    """Someone installed an earlier commit and used it; now they `git pull`.
    Their data, their project and their chat are all still there."""
    from common import free_port
    s = "upgrade"
    old = Space(space.root / "upgrade", free_port())
    old.root.mkdir()
    old.home.mkdir()
    env = {**old.env(), "HOME": str(space.home)}
    sh(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(old.clone)], old.root)
    head = sh(["git", "rev-parse", "--short", "HEAD"], old.clone).stdout.strip()
    back = sh(["git", "reset", "--hard", "--quiet", base], old.clone)
    was = sh(["git", "rev-parse", "--short", "HEAD"], old.clone).stdout.strip()
    behind = sh(["git", "rev-list", "--count", f"HEAD..origin/{sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], old.clone).stdout.strip()}"], old.clone).stdout.strip()
    if not report.add(s, f"an earlier commit is installed ({was}, {behind} commits behind {head})", back.returncode == 0 and was != head, back.stderr[-300:]):
        return
    report.notes["upgrade"] = f"{was} → {head}"

    def boot(log_name: str) -> subprocess.Popen | None:
        log = open(old.root / log_name, "w", encoding="utf-8")
        proc = subprocess.Popen(run_sh("--prod"), cwd=old.clone, env=env, stdout=log, stderr=subprocess.STDOUT, **SPAWN)
        if wait_for(old, "/api/health", boot_seconds, alive=lambda: proc.poll() is None):
            return proc
        stop(proc)
        return None

    proc = boot("server-old.log")
    if not report.add(s, "the earlier commit starts", proc is not None, (old.root / "server-old.log").read_text(encoding="utf-8", errors="replace")[-400:]):
        return
    try:
        old.data.mkdir()
        old.sample.mkdir()
        (old.sample / "app.py").write_text("print('hello')\n", encoding="utf-8")
        http(old.url + "/api/setup/data-root", {"path": str(old.data)})
        http(old.url + "/api/setup/integrate", {"project_code": "kept", "project_dir": str(old.sample)})
        session = "0ead0000-0000-4000-8000-000000000005"
        fire_hook(old, {"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": str(old.sample), "prompt": "Before the upgrade: say hello."}, folder=old.sample)
        fire_hook(old, {"hook_event_name": "Stop", "session_id": session, "cwd": str(old.sample), "last_assistant_message": "Hello, before the upgrade."}, folder=old.sample)
        task = http(old.url + "/api/tasks", {"project": "kept", "title": "A task made before the upgrade", "status": "todo", "actor": "operator"})
        before = eventually(lambda: get(old, "/api/health") if get(old, "/api/health").get("agents") else None, 20) or get(old, "/api/health")
        report.add(s, "it is set up and used: a project, a chat, a task", before.get("agents", 0) >= 1 and bool(task), json.dumps(before)[:200])
    finally:
        stop(proc)
        time.sleep(1)

    dirty = sh(["git", "status", "--porcelain"], old.clone).stdout.strip()
    report.add(s, "using it changed no file of the repository", not dirty, dirty[:300])
    pulled = sh(["git", "pull", "--ff-only", "--quiet"], old.clone, env)
    now = sh(["git", "rev-parse", "--short", "HEAD"], old.clone).stdout.strip()
    if not report.add(s, f"git pull brings the newest commit ({now})", pulled.returncode == 0 and now == head, (pulled.stdout + pulled.stderr)[-400:]):
        return

    proc = boot("server-new.log")
    if not report.add(s, "the new commit starts on the old install", proc is not None, (old.root / "server-new.log").read_text(encoding="utf-8", errors="replace")[-600:]):
        return
    try:
        after = get(old, "/api/health")
        report.add(s, "it opens the same data folder", after.get("data_root") == str(old.data), str(after.get("data_root")))
        report.add(s, "the project and the chat are there", after.get("projects") == before.get("projects") and after.get("agents") == before.get("agents"),
                   f"before {before.get('projects')}/{before.get('agents')}, after {after.get('projects')}/{after.get('agents')}")
        tasks = rows(get(old, "/api/tasks?project=kept"), "tasks")
        report.add(s, "the task is there", any("before the upgrade" in str(t.get("title")) for t in tasks))
        chat = old.data / "projects" / "kept" / "chats" / f"cc-{session[:8]}" / "chat.md"
        report.add(s, "the chat reads as it was", chat.is_file() and "Hello, before the upgrade." in chat.read_text(encoding="utf-8"))
        info = get(old, "/api/setup/info")
        mine = [i for i in info.get("integrations", []) if i.get("project") == "kept"]
        report.add(s, "the project is still integrated; Setup says whether its files need a refresh",
                   bool(mine) and mine[0].get("status") in ("fresh", "stale"), json.dumps(mine)[:200])
        fired = fire_hook(old, {"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": str(old.sample), "prompt": "After the upgrade: still here."}, folder=old.sample)
        report.add(s, "the old project's hook still captures", fired.returncode == 0 and "After the upgrade" in chat.read_text(encoding="utf-8"), (fired.stderr or fired.stdout)[-300:])
        playwright(old, report, s, "every page opens after the upgrade", ["tests/e2e/every-page.spec.ts"])
    finally:
        stop(proc)


def screens(space: Space, report: Report, moment: str, routes: list[str], out: Path) -> None:
    """Pictures of what a person sees at this moment, for a human to look at."""
    out.mkdir(parents=True, exist_ok=True)
    playwright(space, report, "screens", f"pictures: {moment} ({len(routes)} pages)", ["--config", "playwright.fresh.config.ts", "screens.spec.ts"],
               {"FRESH_SHOTS": str(out), "FRESH_MOMENT": moment, "FRESH_ROUTES": "\n".join(routes)})


def cleanup(space: Space, keep: bool) -> None:
    """Logins first, always; the rest unless the run asked to keep it."""
    for rel in (".claude/.credentials.json", ".codex/auth.json", ".local/share/opencode/auth.json"):
        try:
            (space.home / rel).unlink()
        except OSError:
            pass
    if not keep:
        shutil.rmtree(space.root, ignore_errors=True)
