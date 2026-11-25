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
        return {
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
    if workflow == "ci.yml" and len(jobs) != 40:
        return f"required CI matrix is incomplete: {len(jobs)} jobs, expected 40"
    required = required_jobs(workflow)
    if workflow != "ci.yml" and len(jobs) != len(required):
        return f"{workflow}: expected {len(required)} jobs, got {len(jobs)}"
    for name, steps in required.items():
        job = by_name.get(name)
        if job is None:
            return f"required job missing: {name}"
        for step in steps:
            matches = [row.get("conclusion") for row in job.get("steps", []) if row["name"] == step]
            if matches != ["success"]:
                return f"required step did not pass exactly once: {name} / {step} ({matches or 'missing'})"
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
