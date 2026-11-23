"""Verify that a successful GitHub run actually exercised the release matrix."""

from __future__ import annotations

import json
import sys

SYSTEMS = ("ubuntu-latest", "macos-latest", "windows-latest")
TOOLS = ("claude-code", "codex", "opencode")
AGENTS_SMOKE = "An agent from clone to its work on the pages (smoke, pinned)"


def required_jobs(workflow: str) -> dict[str, tuple[str, ...]]:
    if workflow == "agents.yml":
        return {f"{tool} ({os})": (AGENTS_SMOKE,) for tool in TOOLS for os in SYSTEMS}
    if workflow == "machine.yml":
        return {f"Machine full ({os})": ("The kit, Windows" if os.startswith("windows") else "The kit, Linux and macOS",)
                for os in SYSTEMS}
    if workflow == "terminal.yml":
        return {
            "Terminal window (ubuntu-latest)": (
                "End to end, Linux: an X11 window under Xvfb (no GPU there)",
                "End to end, Linux: no display at all (Chromium's headless Ozone, as on a laptop with SP_E2E_HEADLESS=1)",
                "End to end, Linux, plain terminals (no tmux, what Windows has): restore skips, named",
            ),
            "Terminal window (macos-latest)": ("End to end, macOS",),
            "Terminal window (windows-latest)": ("End to end, Windows",),
        }
    if workflow == "weekly.yml":
        return {f"{name} ({os})": (step,) for os in SYSTEMS for name, step in {
            "Heavy tests": "The heavy tests (-rs: a skipped test is named)",
            "Property tests, deep": "3 000 examples each (SP_HYPOTHESIS=deep); a failure prints the example to replay",
            "Newest Codex": "One read of the limits from the newest program",
            "Real Claude Code latest against a stub model": (
                "One turn: the hooks record it, the MCP server writes a decision (scripts/ci/stub_model.py; no tokens)"),
        }.items()}
    if workflow == "ci.yml":
        return {f"Real Codex ({os})": ("One read of the limits from the real program",) for os in SYSTEMS}
    raise ValueError(f"unknown workflow: {workflow}")


def problem(workflow: str, payload: dict, sha: str) -> str:
    jobs = payload["jobs"]
    if len(jobs) != payload["total_count"]:
        return "GitHub did not return the complete job list"
    by_name = {job["name"]: job for job in jobs}
    if len(by_name) != len(jobs):
        return "duplicate job names"
    if workflow == "ci.yml" and len(jobs) < 28:
        return f"required CI matrix is incomplete: {len(jobs)} jobs, expected at least 28"
    for name, steps in required_jobs(workflow).items():
        job = by_name.get(name)
        if job is None:
            return f"required job missing: {name}"
        checks = {row["name"]: row.get("conclusion") for row in job.get("steps", [])}
        for step in steps:
            if checks.get(step) != "success":
                return f"required step did not pass: {name} / {step} ({checks.get(step, 'missing')})"
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
