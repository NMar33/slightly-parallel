"""Verify that a successful GitHub run actually exercised the release matrix."""

from __future__ import annotations

import json
import sys

SYSTEMS = ("ubuntu-latest", "macos-latest", "windows-latest")
TOOLS = ("claude-code", "codex", "opencode")
AGENTS_CORE = "An agent from clone to its work on the pages (core, pinned)"
AGENTS_PREFLIGHT = "Check provider access, authentication and model errors"
OFFLINE_CORE = "Run full Codex core through the guarded MCP on a local stub"
INTERACTIVE_STUB = "Capture a real PTY turn, task, decision, rule and done on a local stub"
HEADLESS_OPENCODE = "Save the headless OpenCode reply before the process exits"
MACHINE_COST = "Report CLI version and model cost"
CODEX_LIMITS = ("Codex limits RPC rejects a signed-out account",
                "The real server reports the signed-out Codex limits response")


def required_jobs(workflow: str) -> dict[str, tuple[str, ...]]:
    if workflow == "agents.yml":
        return {
            "L0 CLI versions": ("Record the CLI package versions",),
            **{f"L0 {provider}": (AGENTS_PREFLIGHT,) for provider in ("anthropic", "openai")},
            **{f"{tool} ({os})": (AGENTS_CORE,) for tool in TOOLS for os in SYSTEMS},
        }
    if workflow == "machine.yml":
        return {f"Machine full ({os})": ("The kit, Windows" if os.startswith("windows") else "The kit, Linux and macOS", MACHINE_COST)
                for os in SYSTEMS}
    if workflow == "pipeline-self-test.yml":
        return {"Verify pipeline failure propagation": ("Require every native probe to fail and prove why",)}
    if workflow == "user-profiles.yml":
        return {
            "Dashboard without Node (ubuntu-latest)": (
                "Run the shipped dashboard and native agent CLIs in a container with no Node",
            ),
            **{f"Dashboard without Node ({os})": ("Run the shipped dashboard with Node removed from PATH",)
               for os in SYSTEMS[1:]},
            "Windows redirected Cyrillic home (PowerShell)": (
                "Redirect the user and temporary folders to Cyrillic paths", "Record Windows profile coverage",
            ),
        }
    if workflow == "terminal.yml":
        return {
            "Terminal window (ubuntu-latest)": (
                "End to end, Linux: an X11 window under Xvfb (no GPU there)",
                "End to end, Linux: no display at all (Chromium's headless Ozone, as on a laptop with SP_E2E_HEADLESS=1)",
                "End to end, Linux, plain terminals (no tmux, what Windows has): restore skips, named",
            ),
            "Terminal window (macos-latest)": ("End to end, macOS",),
            "Terminal window (windows-latest)": (
                "Windows: the ConPTY and the terminal's routes (pywinpty, from requirements.lock)",
                "End to end, Windows",
            ),
        }
    if workflow == "weekly.yml":
        return {f"{name} ({os})": steps for os in SYSTEMS for name, steps in {
            "Heavy tests": ("The heavy tests (-rs: a skipped test is named)",),
            "Property tests, deep": ("3 000 examples each (SP_HYPOTHESIS=deep); a failure prints the example to replay",),
            "Newest Codex": CODEX_LIMITS,
            "Real Claude Code latest against a stub model": (
                "One turn: the hooks record it, the MCP server writes a decision (scripts/ci/stub_model.py; no tokens)",),
        }.items()}
    if workflow == "ci.yml":
        backend_steps = (
            "Run tests (-rs: a skipped test is named, never silent)",
            "Only the skips expected on this system (scripts/ci/check_skips.py: a new skip fails, named)",
        )
        frontend_steps = ("Build (typecheck-gated)", "Unit tests")
        zones = ("America/Los_Angeles", "Asia/Kolkata")
        clocks = ("2026-11-30T23:59:58", "2026-12-31T23:59:58", "2026-11-01T01:59:58")
        return {
            **{f"Backend ({os}, Python 3.12)": backend_steps for os in SYSTEMS},
            **{f"Backend (ubuntu-latest, Python {version})": backend_steps for version in ("3.11", "3.13", "3.14")},
            **{f"Backend (TZ={zone})": (f"Run tests in {zone} (-rs: a skipped test is named)",
                                       "Only the skips expected on this system") for zone in zones},
            **{f"Backend (clock at {clock})": (f"The date-heavy tests at {clock}, Los Angeles time",
                                              "Check that the clock suite actually ran") for clock in clocks},
            "Dependency audit": ("Python (the versions users get)", "npm (what ships; high and critical fail, moderate is listed)"),
            "Frontend (Node 20)": frontend_steps,
            "Frontend (Node 22)": (*frontend_steps, "Unit tests with the clock behind UTC (a day's edge, a date read as UTC)"),
            "End to end (Playwright)": ("Happy path against the demo data",),
            "End to end (Playwright, macOS)": ("Every page and the flows",),
            **{f"Fresh user ({os})": ("From clone to a working setup",) for os in SYSTEMS},
            **{f"Launcher ({os})": ("Healthy", "Nothing left serving",
                                    "Start at login and the shortcut, for real (the runner's own login entry, its shortcut, then off)")
               for os in SYSTEMS},
            **{f"Real Claude Code 2.1.312 and Codex 0.167.0 against stub models ({os})": (
                "One turn: the hooks record it, the MCP server writes a decision (scripts/ci/stub_model.py; no tokens)",
                "codex exec against a stub of the Responses API: recorded as a helper of the chat in its environment, "
                "with its effort (scripts/ci/stub_responses.py; no tokens, no key)",
            ) for os in SYSTEMS},
            **{f"Real Codex ({os})": CODEX_LIMITS for os in SYSTEMS},
            **{f"Interactive agent ({tool}, {os})": (INTERACTIVE_STUB,) for tool in TOOLS for os in SYSTEMS},
            **{f"Interactive agent (opencode, {os})": (INTERACTIVE_STUB, HEADLESS_OPENCODE) for os in SYSTEMS},
            **{f"Interactive agent (codex, {os})": (INTERACTIVE_STUB, OFFLINE_CORE) for os in SYSTEMS},
            **{f"Interactive agent (claude-code, {os}, trust dialog)": (INTERACTIVE_STUB,) for os in SYSTEMS},
        }
    raise ValueError(f"unknown workflow: {workflow}")


def problem(workflow: str, payload: dict, sha: str) -> str:
    jobs = payload["jobs"]
    if len(jobs) != payload["total_count"]:
        return "GitHub did not return the complete job list"
    by_name = {job["name"]: job for job in jobs}
    if len(by_name) != len(jobs):
        return "duplicate job names"
    required = required_jobs(workflow)
    for name, steps in required.items():
        job = by_name.get(name)
        if job is None:
            return f"required job missing: {name}"
        for step in steps:
            matches = [row.get("conclusion") for row in job.get("steps", []) if row["name"] == step]
            if len(matches) > 1:
                return f"duplicate required step: {name} / {step}"
            if matches != ["success"]:
                conclusion = matches[0] if matches else "missing"
                return f"required step did not pass: {name} / {step} ({conclusion})"
    if len(jobs) != len(required):
        return f"{workflow}: expected {len(required)} jobs, got {len(jobs)}"
    for name, job in by_name.items():
        if job.get("head_sha") != sha:
            return f"job ran on a different SHA: {name}"
        if job.get("conclusion") != "success":
            return f"job did not pass: {name} ({job.get('conclusion')})"
    return ""


if __name__ == "__main__":
    try:
        issue = problem(sys.argv[1], json.load(sys.stdin), sys.argv[2])
    except (ValueError, KeyError, TypeError) as exc:
        issue = f"cannot verify job evidence: {exc}"
    if issue:
        sys.exit(issue)
