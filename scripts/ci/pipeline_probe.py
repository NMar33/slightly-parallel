"""Prove that deliberate job failures make every production workflow fail."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Counts per Linux, macOS and Windows. A missing OS fails even if an extra job
# on another OS keeps the workflow's total unchanged.
WORKFLOWS = {
    "ci.yml": (21, 10, 9),
    "terminal.yml": (1, 1, 1),
    "weekly.yml": (4, 4, 4),
    "agents.yml": (6, 3, 3),
    "machine.yml": (1, 1, 1),
    "user-profiles.yml": (1, 1, 2),
    "terminal-bench.yml": (1, 1, 1),
}
START_STEP = "Pipeline probe starts"
NATIVE_STEP = "Pipeline probe rejects a failed native command"
POWERSHELL_STEP = "Pipeline probe rejects a failed PowerShell command"
NATIVE = "SP_PIPELINE_NATIVE_FAILURE"
POWERSHELL = "SP_PIPELINE_POWERSHELL_FAILURE"
UNREACHABLE = "SP_PIPELINE_UNREACHABLE"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOG_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z\s+")
SYSTEM_STEP = {"Set up job", "Complete job"}


class ProbeError(Exception):
    """Evidence is missing or does not prove the intended failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


@dataclass(frozen=True)
class Probe:
    branch: str
    sha: str
    id: str

    def matches(self, run: dict, workflow: str) -> bool:
        return (
            run.get("head_branch") == self.branch
            and run.get("head_sha") == self.sha
            and run.get("event") == "workflow_dispatch"
            and run.get("run_attempt") == 1
            and run.get("path", "").split("@", maxsplit=1)[0] == f".github/workflows/{workflow}"
            and run.get("display_title", "").startswith(f"Pipeline probe {self.id} / ")
        )


def runner_os(job: dict) -> str:
    labels = {label.casefold().split("-", maxsplit=1)[0] for label in job.get("labels", ())}
    systems = labels & {"windows", "linux", "macos"}
    if "ubuntu" in labels:
        systems.add("linux")
    require(len(systems) == 1, f"{job['name']}: missing or ambiguous runner OS label")
    return systems.pop()


def check_jobs(workflow: str, payload: dict, sha: str, run_id: int) -> list[dict]:
    jobs = payload["jobs"]
    expected_os = WORKFLOWS[workflow]
    expected_count = sum(expected_os)
    require(
        payload["total_count"] == len(jobs) == expected_count,
        f"{workflow}: expected {expected_count} jobs, found {len(jobs)} of {payload['total_count']}",
    )
    require(
        len({job["id"] for job in jobs}) == len({job["name"] for job in jobs}) == expected_count,
        f"{workflow}: duplicate job IDs or names",
    )
    systems = Counter()
    for job in jobs:
        name = f"{workflow} / {job['name']}"
        require(job.get("head_sha") == sha and job.get("run_id") == run_id, f"{name}: wrong run or SHA")
        require(
            job.get("status") == "completed" and job.get("conclusion") == "failure",
            f"{name}: expected job failure, got {job.get('status')}/{job.get('conclusion')}",
        )
        system = runner_os(job)
        systems[system] += 1
        expected = [(START_STEP, "success"), (NATIVE_STEP, "failure")]
        if system == "windows":
            expected.append((POWERSHELL_STEP, "failure"))
        steps = sorted(job["steps"], key=lambda step: step["number"])
        numbered_steps = [step["number"] for step in steps]
        require(len(set(numbered_steps)) == len(steps), f"{name}: duplicate step numbers")
        evidence = []
        for step in steps:
            step_name = step["name"]
            conclusion = step.get("conclusion")
            require(step.get("status") == "completed", f"{name}: incomplete step {step_name}")
            if step_name in SYSTEM_STEP:
                require(conclusion == "success", f"{name}: failed runner bookkeeping ({step_name})")
            else:
                evidence.append((step_name, conclusion))
        if system != "windows" and evidence[2:3] == [(POWERSHELL_STEP, "skipped")]:
            expected.append((POWERSHELL_STEP, "skipped"))
        first_steps = evidence[:len(expected)]
        require(first_steps == expected, f"{name}: unexpected probe steps or conclusions {first_steps!r}")
        for step_name, conclusion in evidence[len(expected):]:
            require(step_name not in {START_STEP, NATIVE_STEP, POWERSHELL_STEP}, f"{name}: duplicate probe step ({step_name})")
            require(conclusion == "skipped", f"{name}: regular step ran ({step_name})")
    actual_os = tuple(systems[system] for system in ("linux", "macos", "windows"))
    require(actual_os == expected_os, f"{workflow}: expected Linux, macOS, Windows counts {expected_os}, got {actual_os}")
    return jobs


def check_log(job: dict, log: str) -> None:
    markers = {NATIVE, POWERSHELL, UNREACHABLE}
    output = []
    for line in log.splitlines():
        line = LOG_TIMESTAMP.sub("", ANSI.sub("", line)).strip()
        if line in markers:
            output.append(line)
    expected = [NATIVE, POWERSHELL] if runner_os(job) == "windows" else [NATIVE]
    require(output == expected, f"{job['name']}: expected runtime evidence {expected}, got {output}")


class GitHub:
    def __init__(self, repository: str, token: str, deadline: float):
        require(bool(re.fullmatch(r"[\w.-]+/[\w.-]+", repository)), "invalid GITHUB_REPOSITORY")
        self.base = f"https://api.github.com/repos/{repository}/actions/"
        self.token = token
        self.deadline = deadline

    def time_left(self) -> float:
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "pipeline probe exceeded its 30-minute deadline")
        return remaining

    def wait(self, seconds: float) -> None:
        time.sleep(min(seconds, self.time_left()))

    def request(self, path: str, data: dict | None = None) -> bytes | None:
        request = Request(
            self.base + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "slightly-parallel-pipeline-probe",
                "X-GitHub-Api-Version": "2026-03-10",
            },
            data=None if data is None else json.dumps(data).encode(),
        )
        # Job logs redirect to a signed URL. Keep the API credential on the initial request.
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        while True:
            try:
                with urlopen(request, timeout=min(20, self.time_left())) as response:
                    return response.read()
            except HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise ProbeError(f"GitHub returned HTTP {exc.code} for {path}") from None
            except (URLError, TimeoutError, OSError):
                pass
            if data is not None:
                # The API may have queued the run before the response was lost.
                # Resolve it by its unique title instead of dispatching again.
                return None
            self.wait(5)

    def json(self, path: str, data: dict | None = None) -> dict:
        body = self.request(path, data)
        return json.loads(body) if body else {}


def workflow_run(api: GitHub, probe: Probe, workflow: str) -> dict | None:
    query = urlencode({
        "branch": probe.branch,
        "head_sha": probe.sha,
        "event": "workflow_dispatch",
        "per_page": 100,
    })
    path = f"workflows/{workflow}/runs?{query}"
    matching_runs = []
    for page in range(1, 11):
        payload = api.json(f"{path}&page={page}")
        matching_runs.extend(run for run in payload["workflow_runs"] if probe.matches(run, workflow))
        if payload["total_count"] <= 100 * page:
            require(len(matching_runs) <= 1, f"{workflow}: duplicate runs for probe {probe.id}")
            return matching_runs[0] if matching_runs else None
    raise ProbeError(f"{workflow}: cannot inspect all runs for probe {probe.id}")


def verify(api: GitHub, probe: Probe) -> None:
    run_ids = {}
    # Resolve all existing runs before making a dispatch, so a repeated controller
    # invocation does not partly start a new matrix with the same probe ID.
    for workflow in WORKFLOWS:
        existing = workflow_run(api, probe, workflow)
        require(existing is None, f"{workflow}: probe {probe.id} already dispatched, use a fresh workflow run")
    for workflow in WORKFLOWS:
        result = api.json(
            f"workflows/{workflow}/dispatches",
            {"ref": probe.branch, "inputs": {"expect_failure": True, "probe_id": probe.id}},
        )
        run_ids[workflow] = result.get("workflow_run_id")
    while run_ids:
        for workflow, dispatched_id in list(run_ids.items()):
            if dispatched_id is not None:
                run = api.json(f"runs/{dispatched_id}")
                require(probe.matches(run, workflow), f"{workflow}: dispatch returned an unrelated run")
            else:
                run = workflow_run(api, probe, workflow)
            if run is None or run.get("status") != "completed":
                continue
            run_id = run["id"]
            require(
                run.get("conclusion") == "failure",
                f"{workflow}: run {run_id} concluded {run.get('conclusion')}, expected failure",
            )
            listed = workflow_run(api, probe, workflow)
            if listed is None:
                continue
            require(listed["id"] == run_id, f"{workflow}: listed probe run does not match dispatch")
            jobs = check_jobs(workflow, api.json(f"runs/{run_id}/attempts/1/jobs?per_page=100"), probe.sha, run_id)
            for job in jobs:
                log = api.request(f"jobs/{job['id']}/logs")
                require(bool(log), f"{workflow} / {job['name']}: GitHub did not return job logs")
                check_log(job, log.decode("utf-8", errors="replace"))
            print(f"{workflow}: {len(jobs)} failures proved (run {run_id})", flush=True)
            del run_ids[workflow]
        if run_ids:
            api.wait(10)


def main() -> None:
    try:
        require(os.environ.get("GITHUB_RUN_ATTEMPT", "1") == "1", "start a fresh workflow run for a new probe ID")
        probe = Probe(os.environ["GITHUB_REF_NAME"], os.environ["GITHUB_SHA"], os.environ["GITHUB_RUN_ID"])
        require(bool(re.fullmatch(r"[0-9a-f]{40}", probe.sha)), "invalid GITHUB_SHA")
        require(bool(re.fullmatch(r"[1-9][0-9]*", probe.id)), "invalid GITHUB_RUN_ID")
        api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"], time.monotonic() + 30 * 60)
        verify(api, probe)
    except (ProbeError, KeyError, TypeError, ValueError) as exc:
        sys.exit(f"Pipeline probe failed: {exc}")


if __name__ == "__main__":
    main()
