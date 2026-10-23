"""The agent stage: one chat with a real agent in the sample project.

Each step is a message a person would type, and checks of what the product
holds afterwards, read through the API and the files. The checks are about
structure — an entry exists, on the right project, by the right agent, with
its required parts — never about wording: an agent may say it differently
and still be right. A check marked soft is reported and does not fail.

Two scenarios: `core` (seven messages: a request, #task, #decision, #rule,
the work, #scan, #done) and `full` (the day's standup first, then every
command the contract has).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from agents import Tool, give_login, model_for, tools
from common import Report, Space, eventually, get, http, rows
from stages import YESTERDAY_SESSION, playwright, sh

WIRING_AGENTS = ("cc-f0e1d2c3", f"cc-{YESTERDAY_SESSION[:8]}")


class State:
    """What the chat has produced so far, for the later steps to refer to."""

    def __init__(self, code: str, folder: Path, tool: Tool) -> None:
        self.code, self.folder, self.tool = code, folder, tool
        self.agent = ""
        self.task = ""
        self.problem = ""
        self.said: list[str] = []      # the agent's replies, in order
        self.helper = ""               # how the standup and map helpers must run (helper_settings)
        self.standup_owed = True       # no standup for yesterday when the chat began


Checker = Callable[[Space, Report, str, State], None]


def listed(space: Space, path: str, key: str, st: State, mine: bool = True) -> list[dict]:
    sep = "&" if "?" in path else "?"
    got = rows(get(space, f"{path}{sep}project={st.code}&limit=200"), key)
    got = [r for r in got if str(r.get("project") or st.code) == st.code]
    return [r for r in got if r.get("agent_id") == st.agent] if mine else got


def detail(space: Space, row: dict) -> str:
    """The body of an entry's own file, under its header."""
    path = space.data / str(row.get("md_ref") or "")
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[-1] if row.get("md_ref") and path.is_file() else ""


def find_agent(space: Space, report: Report, s: str, st: State) -> None:
    if st.agent:
        return
    def read() -> list[dict]:
        got = rows(get(space, f"/api/project/{st.code}"), "agents")
        return [a for a in got if str(a.get("agent_id", "")).startswith(st.tool.id_prefix)
                and a.get("agent_id") not in WIRING_AGENTS and a.get("session_ref") == st.tool.session]
    mine = eventually(read)
    if report.add(s, "the chat is captured as an agent", bool(mine), "no agent with this session"):
        st.agent = str(mine[0]["agent_id"])
        report.add(s, "the agent records where it runs", mine[0].get("cwd") == str(st.folder), json.dumps({k: mine[0].get(k) for k in ("cwd", "session_ref", "tool")}))


# ------------------------------------------------------------------ checks

def after_hello(space: Space, report: Report, s: str, st: State) -> None:
    find_agent(space, report, s, st)
    report.add(s, "the agent asks about yesterday's standup before other work", "standup" in st.said[-1].lower(), st.said[-1][:300], soft=True)


def helper_settings(tool: Tool, model: str) -> tuple[dict, str]:
    """The helper model Settings give this tool, and how its helper must then
    run, as Tool.helpers says it. Claude Code keeps the default (opus, not
    the chat's model); Codex and OpenCode are given one, to see it used."""
    if tool.name == "codex":
        name = model or "gpt-6-luna"
        return {"standup.model_codex": name, "map.model_codex": name}, name
    if tool.name == "opencode":
        name = model if "/" in model else "openai/gpt-6-luna"
        return {"standup.model_opencode": name, "map.model_opencode": name}, f"sp-{{job}}:{name}"
    return {}, "opus"


def yesterdays_standup(space: Space, st: State) -> list[dict]:
    day = time.strftime("%y%m-%d", time.localtime(time.time() - 86400))
    return [r for r in listed(space, "/api/standups", "standups", st, mine=False) if str(r.get("for_date") or "") == day]


def helper_ran(space: Space, report: Report, s: str, st: State, job: str) -> None:
    if job == "standup" and not st.standup_owed:
        # An earlier tool's chat in the same run wrote it: nothing was asked.
        report.notes[f"{s} standup helper"] = "not checked: yesterday's standup was written before this chat"
        return
    want = st.helper.replace("{job}", job)
    got = st.tool.helpers(space)
    report.add(s, f"the {job} helper runs as Settings say ({want})", bool(got) and got[-1] == want, f"helpers started: {got}")


def after_standup(space: Space, report: Report, s: str, st: State) -> None:
    helper_ran(space, report, s, st, "standup")
    got = eventually(lambda: yesterdays_standup(space, st), 30)
    if report.add(s, "yesterday's standup is written", bool(got), json.dumps(listed(space, "/api/standups", "standups", st, mine=False))[:300]):
        report.add(s, "it has a summary line", bool(str(got[0].get("l1") or got[0].get("summary") or "").strip()), json.dumps(got[0])[:300], soft=True)
        text = (get(space, f"/api/standups/{got[0]['id']}") or {}).get("text") or {}
        report.add(s, "it tells the day: a story, and what moved", bool(str(text.get("story") or "").strip()) and bool(text.get("movement")),
                   json.dumps(text)[:300])


def after_edit(space: Space, report: Report, s: str, st: State) -> None:
    find_agent(space, report, s, st)
    chat = space.data / "projects" / st.code / "chats" / st.agent / "chat.md"
    text = chat.read_text(encoding="utf-8") if chat.is_file() else ""
    report.add(s, "the chat file has your message and the reply", "sub(a, b)" in text and text.count("\n") > 6, str(chat))
    report.add(s, "the agent edited the file", "def sub" in (st.folder / "calc.py").read_text(encoding="utf-8"))


def after_task(space: Space, report: Report, s: str, st: State) -> None:
    tasks = listed(space, "/api/tasks", "tasks", st, mine=False)
    mine = [t for t in tasks if "test" in str(t.get("title", "")).lower()]
    if report.add(s, "#task put a task on the board", bool(mine), json.dumps(tasks)[:300]):
        st.task = str(mine[0]["id"])
        report.add(s, "it is in the agent column", str(mine[0].get("status")) == "agent", str(mine[0].get("status")))
        report.add(s, "it is written by this agent", st.agent in json.dumps(mine[0]), json.dumps(mine[0])[:300], soft=True)


def after_task_any(space: Space, report: Report, s: str, st: State) -> None:
    """#task in the site scenario: a card in the agent column (the #now task stays st.task)."""
    tasks = listed(space, "/api/tasks", "tasks", st, mine=False)
    report.add(s, "#task put a task in the agent column", any(str(t.get("status")) == "agent" for t in tasks), json.dumps(tasks)[:300])


def after_decision(space: Space, report: Report, s: str, st: State) -> None:
    got = listed(space, "/api/decisions", "decisions", st)
    if report.add(s, "#decision logged a decision", bool(got)):
        report.add(s, "it names pytest", "pytest" in json.dumps(got).lower(), soft=True)
        report.add(s, "it has a weight", any(str(d.get("weight") or "") in ("minor", "normal", "major") for d in got), json.dumps(got)[:300], soft=True)


def kept(lens: str, key: str, words: str) -> Checker:
    """A tagged message is kept by the server; the agent writes what it means."""
    def check(space: Space, report: Report, s: str, st: State) -> None:
        got = [r for r in listed(space, f"/api/{key}", key, st) if words in json.dumps(r).lower() or words in detail(space, r).lower()]
        if report.add(s, f"#{lens} kept the message", bool(got), json.dumps(listed(space, f'/api/{key}', key, st, mine=False))[:300]):
            body = detail(space, got[0])
            report.add(s, "the agent wrote what it means", "## L2" in body and len(body) > 150, body[:300], soft=True)
            if lens == "problem":
                st.problem = str(got[0]["id"])
    return check


def after_work(space: Space, report: Report, s: str, st: State) -> None:
    tests = st.folder / "test_calc.py"
    report.add(s, "the agent wrote the tests", tests.is_file() and "def test" in tests.read_text(encoding="utf-8"))
    log = sh(["git", "log", "--oneline"], st.folder, space.env()).stdout.strip().splitlines()
    report.add(s, "the agent committed", len(log) >= 2, "\n".join(log))


def after_evidence(space: Space, report: Report, s: str, st: State) -> None:
    got = get(space, f"/api/tasks/evidence/summary?project={st.code}")
    n = (got.get("evidence") or {}).get(st.task)
    report.add(s, "#evidence attached evidence to the task", bool(n), json.dumps(got)[:300])


def after_important(space: Space, report: Report, s: str, st: State) -> None:
    got = get(space, f"/api/marks?project={st.code}")
    blob = json.dumps(got)
    report.add(s, "#important starred the message", bool(rows(got, "marks")) or st.agent in blob, blob[:300])


def after_scan(space: Space, report: Report, s: str, st: State) -> None:
    report.add(s, "#scan wrote a scan", bool(listed(space, "/api/scans", "scans", st)))
    report.add(s, "the scan's files are recorded", bool(listed(space, "/api/files", "files", st, mine=False)), soft=True)


def after_architecture(space: Space, report: Report, s: str, st: State) -> None:
    form = listed(space, "/api/architecture", "architecture", st, mine=False)
    report.add(s, "#architecture filled the form for the scan", bool(form), soft=True)
    page = get(space, f"/api/architecture/page?project={st.code}")
    report.add(s, "the architecture page has a version", bool(page.get("page") or page.get("versions") or page.get("version")), json.dumps(page)[:300], soft=True)


def after_map_asked(space: Space, report: Report, s: str, st: State) -> None:
    text = st.said[-1].lower()
    report.add(s, "#map asks before it starts: now, or later", "later" in text or "now" in text, st.said[-1][:300], soft=True)


def after_map(space: Space, report: Report, s: str, st: State) -> None:
    helper_ran(space, report, s, st, "map")
    def read() -> list[dict]:
        # The answer holds the version, and the version holds the map.
        version = get(space, f"/api/map?project={st.code}").get("map") or {}
        return (version.get("map") or {}).get("rows") or version.get("rows") or []
    got = eventually(read, 30)
    doc = get(space, f"/api/map?project={st.code}")
    if report.add(s, "the map of the program is written", bool(got), json.dumps(doc)[:300]):
        kinds = {str(r.get("kind")) for r in got}
        report.add(s, "it has rows of several kinds, each with where it is", len(kinds) >= 3 and all(r.get("where") or r.get("name") == "none" for r in got),
                   f"kinds: {sorted(kinds)}", soft=True)
        report.add(s, "calc.py is on it", "calc.py" in json.dumps(got), soft=True)


def after_artifact(space: Space, report: Report, s: str, st: State) -> None:
    got = listed(space, "/api/artifacts", "artifacts", st, mine=False)
    report.add(s, "#artifact made an artifact", bool(got), json.dumps(got)[:300])


def after_skill(space: Space, report: Report, s: str, st: State) -> None:
    got = [r for r in rows(get(space, "/api/skills?limit=200"), "skills") if r.get("agent_id") == st.agent or str(r.get("source")) not in ("builtin", "demo")]
    report.add(s, "#skill drafted a skill", bool(got), json.dumps([r.get("name") for r in rows(get(space, '/api/skills?limit=200'), 'skills')])[:300])


def after_solved(space: Space, report: Report, s: str, st: State) -> None:
    got = {str(r.get("id")): r for r in listed(space, "/api/problems", "problems", st, mine=False)}
    state = str(got.get(st.problem, {}).get("status") or "")
    report.add(s, "#problem solved closed the problem", state in ("solved", "resolved", "closed", "done"), f"{st.problem}: {state}")


def after_help(space: Space, report: Report, s: str, st: State) -> None:
    text = st.said[-1]
    report.add(s, "#help lists the commands", all(c in text for c in ("#scan", "#task", "#decision", "#done")), text[:300])


def after_sp(space: Space, report: Report, s: str, st: State) -> None:
    """#sp: the agent asked the server (the MCP tool checkup), and answered
    with what it found — not from its own idea of the setup."""
    asked = eventually(lambda: any(str(r.get("path", "")).startswith("/api/checkup")
                                   for r in rows(get(space, "/api/logs?level=INFO&limit=2000"), "records")), 10)
    report.add(s, "#sp called the checkup", bool(asked))
    text = st.said[-1].lower()
    report.add(s, "#sp answered with what it found", any(w in text for w in ("recorded", "check", "concern", "fine", "ok")),
               st.said[-1][:300], soft=True)


def site_ask(st: "State") -> str:
    """Each tool builds in a folder of its own: the agents run one after
    another in one project, and the second found the first one's page done,
    changed nothing, and had nothing to scan."""
    # The folder is made here: OpenCode escapes the spaces of a path in a
    # shell command and then takes its own project folder for an outside one,
    # refusing `mkdir` with no one to ask (the test's paths have a space).
    (st.folder / site_dir(st)).mkdir(exist_ok=True)
    return (f"#now build a small notes page in the folder {site_dir(st)} (it exists, empty): index.html and notes.js — add a note, "
            "list the notes, delete one, kept in localStorage — and notes.test.js with node:test tests for the "
            "functions that change the list. Run the tests with `node --test` in that folder, then commit.")


def site_dir(st: "State") -> str:
    return f"notes-{st.tool.name}"


def after_site_now(space: Space, report: Report, s: str, st: State) -> None:
    """#now: the card is in doing, with the operator's message as its text."""
    find_agent(space, report, s, st)          # the later checks read this agent's own entries
    tasks = listed(space, "/api/tasks", "tasks", st, mine=False)
    now = [t for t in tasks if str(t.get("status")) == "doing"]
    if report.add(s, "#now put the task in doing", bool(now), json.dumps(tasks)[:300]):
        st.task = str(now[0]["id"])
        full = get(space, f"/api/tasks/{st.task}")
        text = json.dumps(full)
        report.add(s, "its text is the operator's message", "notes page" in text and "localStorage" in text, text[:300])
        # The server writes the card when the agent ended the turn without it.
        events = json.dumps(get(space, f"/api/tasks/{st.task}/events"))
        report.add(s, "the agent wrote the #now card itself", "the server did" not in events,
                   "the server wrote it: the agent ended the turn without one", soft=True)
    files = [st.folder / site_dir(st) / n for n in ("index.html", "notes.js", "notes.test.js")]
    report.add(s, "the agent built the page and its tests", all(f.is_file() for f in files),
               ", ".join(f.name for f in files if not f.is_file()) or "all there")
    log = sh(["git", "log", "--oneline"], st.folder, space.env()).stdout.strip().splitlines()
    report.add(s, "the agent committed", len(log) >= 2, "\n".join(log), soft=True)


def after_site_tests(space: Space, report: Report, s: str, st: State) -> None:
    ran = sh(["node", "--test"], st.folder / site_dir(st), space.env())
    report.add(s, "the page's tests pass", ran.returncode == 0, (ran.stdout + ran.stderr)[-400:])


def after_done(space: Space, report: Report, s: str, st: State) -> None:
    tasks = {str(t.get("id")): t for t in listed(space, "/api/tasks", "tasks", st, mine=False)}
    t = eventually(lambda: str({str(x.get("id")): x for x in listed(space, "/api/tasks", "tasks", st, mine=False)}.get(st.task, {}).get("status")) == "done", 10)
    report.add(s, "#done moved the task to done", bool(t), f"{st.task}: {tasks.get(st.task, {}).get('status')}")
    stats = [r for r in rows(get(space, "/api/stats/tasks"), "tasks") if str(r.get("id")) == st.task]
    report.add(s, "the finished task has its stretch of the chat", bool(stats), soft=True)


# ------------------------------------------------------------------- steps

Step = tuple[str, Callable[[State], str], Checker]

EDIT: Step = ("a plain request", lambda st: "Add a function sub(a, b) to calc.py that returns a - b. Do not commit yet.", after_edit)
TASK: Step = ("#task", lambda st: "#task write unit tests for calc.py", after_task)
DECISION: Step = ("#decision", lambda st: "We will use pytest, not unittest. #decision", after_decision)
RULE: Step = ("#rule", lambda st: "#rule calc.py must stay a single file with no dependencies outside the standard library", kept("rule", "rules", "single file"))
WORK: Step = ("the work", lambda st: "Write the tests now in test_calc.py, as pytest-style functions, and commit everything.", after_work)
SCAN: Step = ("#scan", lambda st: "#scan", after_scan)
DONE: Step = ("#done", lambda st: f"#done {st.task}".strip(), after_done)
SP: Step = ("#sp", lambda st: "#sp", after_sp)

CORE: list[Step] = [EDIT, TASK, DECISION, RULE, WORK, SCAN, SP, DONE]

FULL: list[Step] = [
    ("hello", lambda st: "Hello. What is in this project?", after_hello),
    ("the standup answer", lambda st: "2", after_standup),
    EDIT, TASK, DECISION, RULE,
    ("#vision", lambda st: "#vision one day calc should also work from the command line, like `python calc.py add 2 3`", kept("vision", "visions", "command line")),
    ("#problem", lambda st: "#problem sub(a, b) is not documented anywhere, so nobody knows the order of its arguments", kept("problem", "problems", "documented")),
    WORK,
    ("#evidence", lambda st: f"#evidence {st.task}".strip(), after_evidence),
    ("#important", lambda st: "The tests must run before every commit. #important", after_important),
    SCAN,
    ("#architecture", lambda st: "#architecture — and skip the map of the program, later", after_architecture),
    ("#map", lambda st: "#map", after_map_asked),
    ("the map answer", lambda st: "Now.", after_map),
    ("#artifact", lambda st: "#artifact a one-page cheat sheet of calc.py's functions, as a document", after_artifact),
    ("#skill", lambda st: "#skill how we add a function to calc.py: write it, test it with pytest, commit", after_skill),
    ("#problem solved", lambda st: f"Add a docstring to sub that says it returns a minus b, and commit. #problem solved {st.problem}".strip(), after_solved),
    ("#help", lambda st: "#help", after_help),
    SP,
    DONE,
]

# A real piece of work, as on a new machine: a small page built with #now,
# a task for later, the tests run and fixed, a scan, #sp, #done.
SITE: list[Step] = [
    ("#now: build the page", site_ask, after_site_now),
    ("#task", lambda st: "#task add a search box over the notes, later", after_task_any),
    ("the tests", lambda st: "Run the tests again, fix anything that fails, and commit.", after_site_tests),
    SCAN,
    SP,
    DONE,
]

SCENARIOS = {"core": CORE, "full": FULL, "site": SITE}


# --------------------------------------------------------------------- run

def chat(space: Space, report: Report, s: str, st: State, plan: list[Step], model: str, env: dict[str, str], turn_seconds: int) -> float:
    """Say each step and check after it. Returns what the chat cost."""
    cost = 0.0
    for i, (name, message, check) in enumerate(plan):
        text = message(st)
        print(f"  [{st.code}] > {text}", flush=True)
        turn = st.tool.say(text, model_for(st.tool.name, model), space, env, turn_seconds, st.folder)
        cost = max(cost, turn.cost_usd)
        st.said.append(turn.text)
        (space.root / f"{st.code}-{st.tool.name}-turn-{i + 1:02d}.txt").write_text(f"> {text}\n\n{turn.text}\n\n{turn.error}\n", encoding="utf-8")
        if not report.add(s, f"{name}: the agent answered ({round(turn.seconds)} s)", turn.ok, turn.error or turn.text[-300:]):
            break
        check(space, report, s, st)
    return cost


def run(space: Space, report: Report, code: str, folder: Path, tool: Tool, model: str, real_home: Path,
        turn_seconds: int, scenario: str = "full", stage: str = "") -> State | None:
    s = stage or f"agent:{tool.name}"
    if not tool.installed():
        print(f"  skipped: {tool.binary} is not installed", flush=True)
        report.notes[s] = "skipped: not installed"
        return None
    env = space.env()
    login = give_login(tool, real_home, space, env)
    if not report.add(s, f"a login for {tool.name} ({login or 'none found'})", bool(login),
                      f"log in to {tool.binary} first, or set one of {', '.join(tool.login_env)}"):
        return None
    if tool.name == "codex":
        # As a person does once: trust the folder and its hooks on Codex's own screen.
        from screen import trust_codex
        try:
            done, shown = trust_codex(folder, env, space.home)
        except Exception as exc:  # noqa: BLE001 — no pseudo-terminal here: the run goes on with the bypass
            done, shown = False, f"{type(exc).__name__}: {exc}"
        tool.hooks_trusted = report.add(s, "the folder and its hooks are trusted on Codex's own screen", done, shown)
    st = State(code, folder, tool)
    values, st.helper = helper_settings(tool, model_for(tool.name, model))
    if values:
        http(space.url + "/api/settings", {"values": values})
    st.standup_owed = not yesterdays_standup(space, st)
    cost = chat(space, report, s, st, SCENARIOS[scenario], model, env, turn_seconds)
    report.notes[f"{s} cost_usd"] = round(cost, 2)
    # The pages check looks for what core and full make (a rule, a decision);
    # the site scenario makes neither, and its checks read the API instead.
    if st.agent and not stage and scenario != "site":
        playwright(space, report, s, "the pages show what the agent did",
                   ["--config", "playwright.fresh.config.ts", "after-agent.spec.ts"],
                   {"FRESH_CODE": code, "FRESH_AGENT": st.agent, "FRESH_TASK": st.task,
                    "FRESH_SAID": SCENARIOS[scenario][0][1](st)[:40]})
    return st


def parallel(space: Space, report: Report, first: tuple[str, Path], second: tuple[str, Path], tool_name: str,
             model: str, real_home: Path, turn_seconds: int) -> None:
    """Agents at the same time: one in each of two projects, then two in one folder."""
    s = "parallel"
    if not tools()[tool_name].installed():
        report.notes[s] = "skipped: the tool is not installed"
        return
    env = space.env()
    if not give_login(tools()[tool_name], real_home, space, env):
        return

    def side(code: str, folder: Path, word: str) -> State:
        st = State(code, folder, tools()[tool_name])
        plan: list[Step] = [
            ("a request", lambda _st: f"Create a file {word}.txt that holds the single word {word}. Do not commit.", lambda *a: None),
            ("#decision", lambda _st: f"We name such files after their content, so this one is {word}.txt. #decision", lambda *a: None),
        ]
        chat(space, report, f"{s}:{code}:{word}", st, plan, model, env, turn_seconds)
        return st

    def together(jobs: list[tuple[str, Path, str]]) -> list[State]:
        out: list[State | None] = [None] * len(jobs)
        def work(i: int) -> None:
            out[i] = side(*jobs[i])
        threads = [threading.Thread(target=work, args=(i,)) for i in range(len(jobs))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return [x for x in out if x is not None]

    def verdict(states: list[State], what: str, soft: bool) -> None:
        for st in states:
            word = st.said and next((w for w in ("alpha", "beta", "gamma", "delta") if (st.folder / f"{w}.txt").is_file() and w in st.said[0].lower() + st.said[-1].lower()), "") or ""
            agents = eventually(lambda: [a for a in rows(get(space, f"/api/project/{st.code}"), "agents") if a.get("session_ref") == st.tool.session])
            if not report.add(s, f"{what}: the chat in {st.code} ({st.tool.session[:8]}) is captured under its project", bool(agents)):
                continue
            st.agent = str(agents[0]["agent_id"])
            mine = [d for d in rows(get(space, f"/api/decisions?project={st.code}&limit=200"), "decisions") if d.get("agent_id") == st.agent]
            report.add(s, f"{what}: its decision is stamped with its own agent", bool(mine),
                       f"{st.agent} ({word}) has no decision; decisions: " + json.dumps([[d.get('agent_id'), str(d.get('decision_text'))[:40]] for d in rows(get(space, f'/api/decisions?project={st.code}&limit=200'), 'decisions')])[:400], soft=soft)

    print("  two projects at once", flush=True)
    verdict(together([(first[0], first[1], "alpha"), (second[0], second[1], "beta")]), "two projects", soft=False)
    print("  two agents in one folder", flush=True)
    # Two chats in one folder: each one's MCP server must find its own chat
    # (by the tool process it shares with that chat's hook), not the newest.
    verdict(together([(first[0], first[1], "gamma"), (first[0], first[1], "delta")]), "one folder", soft=False)
