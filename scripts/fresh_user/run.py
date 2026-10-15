#!/usr/bin/env python3
"""The fresh-user test: Slightly Parallel from `git clone` to an agent at work.

    python3 scripts/fresh_user/run.py                       # everything, Claude Code on sonnet
    python3 scripts/fresh_user/run.py --no-agent            # the stages that cost nothing
    python3 scripts/fresh_user/run.py --scenario core       # seven messages instead of eighteen
    python3 scripts/fresh_user/run.py --agent-runs 3        # the chat three times: how steady is it
    python3 scripts/fresh_user/run.py --tools claude-code,codex,opencode
    python3 scripts/fresh_user/run.py --keep                # leave the folder to look at

Everything happens in one temporary folder: a home that has never seen
Slightly Parallel, a clone of this repository's last commit, a data folder and
sample projects. The server runs on a free port. Nothing of yours is read
or written, except: the agent stages copy the tool's login file into the
temporary home so the agent can answer, and delete it at the end.

See scripts/fresh_user/README.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario  # noqa: E402
import stages  # noqa: E402
from agents import tools  # noqa: E402
from common import REPO, Report, Space, free_port, http  # noqa: E402

FREE = ["install", "pages", "setup", "wiring", "terminal", "failures", "disconnect", "restart", "background", "dev", "volume", "upgrade"]
PAID = ["agent", "parallel"]
ALL = ["install", "pages", "setup", "wiring", "agent", "parallel", "terminal", "failures", "disconnect", "restart", "background", "dev", "volume", "upgrade"]
OUT = REPO / ".sp" / "fresh-user"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Test Slightly Parallel the way a new user meets it.")
    ap.add_argument("--stages", default=",".join(ALL), help=f"comma-separated, from: {', '.join(ALL)} (install and setup always run)")
    ap.add_argument("--no-agent", action="store_true", help=f"leave out the stages that start a real agent ({', '.join(PAID)})")
    ap.add_argument("--tools", default="claude-code", help="agent tools: claude-code, codex, opencode")
    ap.add_argument("--model", default="sonnet", help="sonnet, haiku or opus; or a model name passed to the tool as is")
    ap.add_argument("--scenario", default="full", choices=sorted(scenario.SCENARIOS), help="core: 7 messages; full: the standup and every command")
    ap.add_argument("--agent-runs", type=int, default=1, help="run the agent chat this many times, each in a new project")
    ap.add_argument("--source", default=str(REPO), help="the repository folder to clone")
    ap.add_argument("--upgrade-from", default="", help="the commit an upgrade starts from (default: the newest v* tag, else 5 commits back)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder (logins are removed either way)")
    ap.add_argument("--boot-seconds", type=int, default=1200, help="how long the first start may take")
    ap.add_argument("--turn-seconds", type=int, default=900, help="how long one agent turn may take")
    args = ap.parse_args(argv)

    wanted = [x.strip() for x in args.stages.split(",") if x.strip()]
    names = [x.strip() for x in args.tools.split(",") if x.strip()]
    known = tools()
    bad_names = [x for x in wanted if x not in ALL] + [n for n in names if n not in known]
    if bad_names:
        ap.error(f"unknown stage or tool: {bad_names}")
    if args.no_agent:
        wanted = [x for x in wanted if x not in PAID]
    on = lambda stage: stage in wanted  # noqa: E731

    space = Space(Path(tempfile.mkdtemp(prefix="sp-fresh-")), free_port())
    report = Report()
    code, second = "calc", "notes"
    shots = space.root / "screens"
    started = time.time()
    print(f"fresh-user test in {space.root} on port {space.port}", flush=True)
    proc = None
    states: list[scenario.State] = []
    try:
        print("\ninstall", flush=True)
        proc = stages.install(space, report, Path(args.source), args.boot_seconds)
        if proc is None:
            return finish(space, report, args, started, shots)
        print("\nreadme", flush=True)
        stages.readme(space, report)
        stages.screens(space, report, "1-first-start", ["/", "/setup", "/kanban", "/guide"], shots)
        if on("pages"):
            print("\npages", flush=True)
            stages.pages(space, report)

        print("\nsetup", flush=True)
        stages.setup(space, report, code, names)
        second_folder = stages.second_project(space, report, second)
        stages.screens(space, report, "2-after-setup", ["/setup", "/", f"/project/{code}", f"/project/{code}#tasks", "/time"], shots)
        if report.failed():
            return finish(space, report, args, started, shots, proc)

        if on("wiring"):
            print("\nwiring", flush=True)
            stages.wiring(space, report, code)
        if on("agent") and not report.failed():
            if args.scenario == "full":
                stages.yesterday(space, report, code)
            for n in names:
                for i in range(args.agent_runs):
                    this, folder = code, space.sample
                    if i > 0:
                        # A run after the first gets its own project, set up the same way.
                        this = f"{code}{i + 1}"
                        folder = space.root / this
                        shutil.copytree(space.sample, folder, ignore=shutil.ignore_patterns(".git", "*.txt", "test_*", "AGENTS.md", "CLAUDE.md", ".claude", ".mcp.json", "__pycache__", ".pytest_cache"))
                        (folder / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
                        stages.sh(["git", "init", "-q"], folder, space.env())
                        stages.sh(["git", "config", "user.name", "Fresh User"], folder, space.env())
                        stages.sh(["git", "config", "user.email", "fresh@example.com"], folder, space.env())
                        stages.sh(["git", "add", "-A"], folder, space.env())
                        stages.sh(["git", "commit", "-qm", "first commit"], folder, space.env())
                        http(space.url + "/api/setup/integrate", {"project_code": this, "project_dir": str(folder)})
                    print(f"\nagent · {n} · {args.model} · {args.scenario}" + (f" · run {i + 1} of {args.agent_runs}" if args.agent_runs > 1 else ""), flush=True)
                    plan = args.scenario if i == 0 else ("core" if args.scenario == "full" else args.scenario)
                    stage = "" if i == 0 else f"agent:{n}:run{i + 1}"
                    st = scenario.run(space, report, this, folder, tools()[n], args.model, Path.home(), args.turn_seconds, plan, stage)
                    if st:
                        states.append(st)
            if states:
                st = states[0]
                stages.screens(space, report, "3-after-agent", [
                    "/", f"/project/{code}", f"/project/{code}#tasks", f"/project/{code}#activity", f"/agent/{st.agent}",
                    "/kanban", "/chats", "/scans", "/standups", "/decisions", "/rules", "/visions", "/problems",
                    "/skills", "/artifacts", "/architecture", "/files", "/stats", "/important", "/time",
                ], shots)
        if on("parallel") and not report.failed():
            print(f"\nparallel · {names[0]}", flush=True)
            scenario.parallel(space, report, (code, space.sample), (second, second_folder), names[0], args.model, Path.home(), args.turn_seconds)
        if on("terminal"):
            print("\nterminal", flush=True)
            st = states[0] if states else None
            stages.terminal(space, report, code, st.agent if st else "cc-f0e1d2c3",
                            st.tool.session if st else "f0e1d2c3-0000-4000-8000-000000000001", st.task if st else "")
        if on("failures"):
            print("\nfailures", flush=True)
            stages.failures(space, report, running_port=proc is not None)
        if on("disconnect"):
            print("\ndisconnect", flush=True)
            stages.disconnect(space, report, second)
        if on("restart"):
            print("\nrestart", flush=True)
            proc = stages.restart(space, report, proc, [code])
        if on("background"):
            print("\nbackground", flush=True)
            stages.background(space, report, proc)
            proc = None
        if on("dev"):
            print("\ndev", flush=True)
            stages.stop(proc)
            proc = None
            stages.dev(space, report, code)
        if on("volume"):
            print("\nvolume", flush=True)
            stages.stop(proc)
            proc = None
            stages.volume(space, report)
        if on("upgrade"):
            print("\nupgrade", flush=True)
            stages.stop(proc)
            proc = None
            base = args.upgrade_from
            if not base:
                # The newest release tag that is not HEAD itself, else five commits back.
                head = stages.sh(["git", "rev-parse", "HEAD"], Path(args.source)).stdout.strip()
                tags = stages.sh(["git", "tag", "--list", "v*", "--sort=-creatordate"], Path(args.source)).stdout.split()
                behind = [t for t in tags if stages.sh(["git", "rev-parse", t + "^{commit}"], Path(args.source)).stdout.strip() != head]
                base = behind[0] if behind else "HEAD~5"
            if stages.sh(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"], Path(args.source)).returncode == 0:
                stages.upgrade(space, report, Path(args.source), base, args.boot_seconds)
            else:
                # A fresh repository, or a shallow clone: nothing earlier to install first.
                report.add("upgrade", f"no earlier commit to upgrade from: {base} is not in the history", False, soft=True)
    finally:
        stages.stop(proc)
        stages.sh(["./sp.sh", "down"], space.clone, space.env()) if (space.clone / "sp.sh").is_file() else None
    return finish(space, report, args, started, shots)


def finish(space: Space, report: Report, args: argparse.Namespace, started: float, shots: Path, proc=None) -> int:
    stages.stop(proc)
    OUT.mkdir(parents=True, exist_ok=True)
    if shots.is_dir():
        shutil.rmtree(OUT / "screens", ignore_errors=True)
        shutil.copytree(shots, OUT / "screens")
    report.notes["seconds"] = round(time.time() - started)
    report.notes["folder"] = str(space.root) if args.keep else "removed"
    report.write(OUT / "report.json")
    stages.cleanup(space, args.keep)

    bad = report.failed()
    soft = [c for c in report.checks if not c.ok and c.soft]
    by_stage: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for c in report.checks:
        by_stage[c.stage.split(":run")[0]][0 if c.ok else (2 if c.soft else 1)] += 1
    print("\nstage                      passed  failed  soft", flush=True)
    for stage, (ok, failed, softn) in by_stage.items():
        print(f"  {stage:<24} {ok:>6}  {failed:>6}  {softn:>4}", flush=True)
    if args.agent_runs > 1:
        # The same check across the runs: which ones hold every time.
        seen: dict[str, list[bool]] = defaultdict(list)
        for c in report.checks:
            if c.stage.startswith("agent:"):
                seen[c.name.split(": the agent answered")[0]].append(c.ok)
        shaky = {k: v for k, v in seen.items() if not all(v)}
        print(f"\nacross {args.agent_runs} runs: {len(seen) - len(shaky)} checks held every time, {len(shaky)} did not", flush=True)
        for k, v in shaky.items():
            print(f"  {sum(v)}/{len(v)}  {k}", flush=True)
        report.notes["shaky"] = {k: f"{sum(v)}/{len(v)}" for k, v in shaky.items()}
        report.write(OUT / "report.json")
    print(f"\n{len(report.checks) - len(bad) - len(soft)} passed, {len(bad)} failed, {len(soft)} soft · {report.notes['seconds']} s"
          f"\nreport: {OUT / 'report.json'} · pictures: {OUT / 'screens'}", flush=True)
    for c in bad:
        print(f"  FAIL {c.stage}: {c.name}\n      {c.detail}", flush=True)
    for c in soft:
        print(f"  soft {c.stage}: {c.name}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
