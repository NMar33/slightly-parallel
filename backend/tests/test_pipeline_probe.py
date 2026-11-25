"""Offline evidence and dispatch checks for the deliberate CI failure probe."""

import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ci"))
import pipeline_probe as pp

SHA = "c" * 40
RUN_ID = 199
PROBE = pp.Probe("ci-probe", SHA, "101")


def step(number, name, conclusion="success"):
    return {"number": number, "name": name, "status": "completed", "conclusion": conclusion}


def job(job_id, label):
    windows = label.casefold().startswith("windows")
    return {
        "id": job_id,
        "name": f"Runner ({label})",
        "labels": ["github-hosted", label],
        "run_id": RUN_ID,
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "failure",
        "steps": [
            step(1, "Set up job"),
            step(2, pp.START_STEP),
            step(3, pp.NATIVE_STEP, "failure"),
            step(4, pp.POWERSHELL_STEP, "failure" if windows else "skipped"),
            step(5, "Run normal tests", "skipped"),
            step(10, "Complete job"),
        ],
    }


def run_payload(workflow="windows.yml", **overrides):
    return {
        "id": RUN_ID,
        "head_branch": PROBE.branch,
        "head_sha": SHA,
        "event": "workflow_dispatch",
        "run_attempt": 1,
        "path": f".github/workflows/{workflow}@refs/heads/{PROBE.branch}",
        "display_title": f"Pipeline probe {PROBE.id} / {workflow}",
        "status": "completed",
        "conclusion": "failure",
        **overrides,
    }


def payload(jobs):
    return {"jobs": jobs, "total_count": len(jobs)}


def output(text):
    return "2026-11-25T08:03:19.4000210Z " + text + "\r\n"


def log(windows=False):
    contents = output(f"\x1b[36;1mecho '{pp.NATIVE}'\x1b[0m")
    contents += output(f"\x1b[36;1mecho '{pp.UNREACHABLE}'\x1b[0m")
    contents += output(pp.NATIVE) + output("##[error]Process completed with exit code 1.")
    if windows:
        contents += output(pp.POWERSHELL)
    return contents


def test_checks_each_runner_and_ignores_commands_written_to_the_log():
    jobs = [job(1, "ubuntu-latest"), job(2, "macos-15"), job(3, "WINDOWS-2025")]
    assert pp.check_jobs("terminal.yml", payload(jobs), SHA, RUN_ID) == jobs
    for row in jobs:
        pp.check_log(row, log(windows=row["id"] == 3))


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda rows: rows.pop(), "expected 3 jobs"),
        (lambda rows: rows[1].update(id=rows[0]["id"]), "duplicate job"),
        (lambda rows: rows[1].update(name=rows[0]["name"]), "duplicate job"),
        (lambda rows: rows[1].update(head_sha="b" * 40), "wrong run or SHA"),
        (lambda rows: rows[1].update(run_id=999), "wrong run or SHA"),
        (lambda rows: rows[1].update(conclusion="cancelled"), "expected job failure"),
        (lambda rows: rows[1].update(conclusion="success"), "expected job failure"),
        (lambda rows: rows[1].update(labels=["github-hosted"]), "runner OS label"),
        (lambda rows: rows[1].update(labels=["ubuntu-latest"]), "expected Linux, macOS, Windows counts"),
        (lambda rows: rows[1]["steps"][1].update(number=1), "duplicate step numbers"),
        (lambda rows: rows[1]["steps"][1].update(conclusion="failure"), "unexpected probe steps"),
        (lambda rows: rows[2]["steps"][3].update(conclusion="skipped"), "unexpected probe steps"),
        (lambda rows: rows[1]["steps"][2].update(conclusion="success"), "unexpected probe steps"),
        (lambda rows: rows[1]["steps"][3].update(conclusion="failure"), "duplicate probe step"),
        (lambda rows: rows[1]["steps"][4].update(number=0), "unexpected probe steps"),
        (lambda rows: rows[1]["steps"][4].update(conclusion="success"), "regular step ran"),
        (lambda rows: rows[1]["steps"][4].update(conclusion="failure"), "regular step ran"),
    ],
)
def test_job_evidence_rejects_bad_runs(mutate, reason):
    jobs = [job(1, "ubuntu-latest"), job(2, "macos-latest"), job(3, "windows-latest")]
    mutate(jobs)
    with pytest.raises(pp.ProbeError, match=reason):
        pp.check_jobs("terminal.yml", payload(jobs), SHA, RUN_ID)


@pytest.mark.parametrize(
    "contents",
    [
        output(f"\x1b[36;1mWrite-Output '{pp.NATIVE}'\x1b[0m"),
        log(),
        log(windows=True) + output(pp.UNREACHABLE),
        log(windows=True) + output(pp.NATIVE),
        output(pp.POWERSHELL) + log(),
    ],
)
def test_log_evidence_requires_the_actual_commands_to_hit_their_failure_paths(contents):
    with pytest.raises(pp.ProbeError, match="expected runtime evidence"):
        pp.check_log(job(1, "windows-latest"), contents)


class FakeGitHub:
    def __init__(self, dispatch_result, runs=()):
        self.dispatch_result = dispatch_result
        self.runs = list(runs)
        self.calls = []

    def json(self, path, data=None):
        self.calls.append((path, data))
        if path.startswith("workflows/windows.yml/runs?"):
            return {"total_count": len(self.runs), "workflow_runs": self.runs}
        if path == "workflows/windows.yml/dispatches":
            self.runs.append(run_payload())
            return self.dispatch_result
        if path == f"runs/{RUN_ID}":
            return self.runs[-1]
        if path == f"runs/{RUN_ID}/attempts/1/jobs?per_page=100":
            return payload([job(1, "windows-latest")])
        raise AssertionError(path)

    def request(self, path):
        assert path == "jobs/1/logs"
        return log(windows=True).encode()

    def wait(self, seconds):
        raise AssertionError("fixture did not finish immediately")


@pytest.fixture
def windows_workflow(monkeypatch):
    monkeypatch.setattr(pp, "WORKFLOWS", {"windows.yml": (0, 0, 1)})


@pytest.mark.parametrize("dispatch_result", [{"workflow_run_id": RUN_ID}, {}])
def test_dispatch_response_with_or_without_run_id(dispatch_result, windows_workflow):
    # Other workflow_dispatch runs on the same branch are ordinary background noise.
    old_run = run_payload(display_title="Pipeline probe 202 / windows.yml")
    api = FakeGitHub(dispatch_result, [old_run])
    pp.verify(api, PROBE)
    assert [data for _, data in api.calls if data is not None] == [
        {"ref": PROBE.branch, "inputs": {"expect_failure": True, "probe_id": PROBE.id}},
    ]


def test_existing_dispatch_rejected_before_sending_a_post(windows_workflow):
    api = FakeGitHub({}, [run_payload()])
    with pytest.raises(pp.ProbeError, match="already dispatched"):
        pp.verify(api, PROBE)
    assert all(data is None for _, data in api.calls)


def test_duplicate_dispatch_evidence_is_rejected(windows_workflow):
    api = FakeGitHub({}, [run_payload(), run_payload(id=RUN_ID + 1)])
    with pytest.raises(pp.ProbeError, match="duplicate runs"):
        pp.verify(api, PROBE)


@pytest.mark.parametrize(
    "changed",
    [
        {"head_branch": "other-branch"},
        {"head_sha": "b" * 40},
        {"event": "push"},
        {"run_attempt": 2},
        {"path": ".github/workflows/terminal.yml"},
        {"display_title": "Pipeline probe 1011 / windows.yml"},
    ],
)
def test_wrong_workflow_run_cannot_supply_evidence(changed):
    assert not PROBE.matches(run_payload(**changed), "windows.yml")


def test_ambiguous_dispatch_uses_title_lookup_instead_of_retrying_post(monkeypatch):
    calls = []

    def unreachable(request, *, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 503, "service unavailable", {}, None)

    monkeypatch.setattr(pp, "urlopen", unreachable)
    api = pp.GitHub("org/project", "dummy", float("inf"))
    assert api.json("workflows/windows.yml/dispatches", {"ref": PROBE.branch}) == {}
    assert len(calls) == 1
    assert calls[0].get_method() == "POST"


@pytest.mark.parametrize("workflow", pp.WORKFLOWS)
def test_production_jobs_accept_the_probe_and_isolate_normal_steps(workflow):
    import yaml

    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / workflow
    config = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    inputs = config["on"]["workflow_dispatch"]["inputs"]
    assert inputs["expect_failure"]["type"] == "boolean"
    assert inputs["expect_failure"]["default"] == "false"
    assert "Pipeline probe {0} /" in config["run-name"]
    assert config["defaults"]["run"]["shell"] == "bash"
    for job in config["jobs"].values():
        if "matrix" in job.get("strategy", {}):
            assert job["strategy"]["fail-fast"] == "false"
        assert all("secrets." not in str(value) or "!inputs.expect_failure" in str(value)
                   for value in job.get("env", {}).values())
        start, native, powershell, *production = job["steps"]
        assert [step["name"] for step in (start, native, powershell)] == [
            pp.START_STEP, pp.NATIVE_STEP, pp.POWERSHELL_STEP,
        ]
        assert all("inputs.expect_failure" in step["if"] for step in (start, native, powershell))
        assert pp.NATIVE in native["run"] and pp.UNREACHABLE in native["run"]
        assert pp.POWERSHELL in powershell["run"] and pp.UNREACHABLE in powershell["run"]
        assert powershell["shell"] == "pwsh" and "failure()" in powershell["if"]
        assert all("!inputs.expect_failure" in step["if"] for step in production)


def test_probe_registry_matches_the_exported_workflows():
    repo = Path(__file__).resolve().parents[2]
    workflow_dir = repo / ".github" / "workflows"
    exclusions = repo / "scripts" / "release-exclude.txt"
    excluded = set(exclusions.read_text(encoding="utf-8").splitlines()) if exclusions.is_file() else set()
    exported = {path.name for path in workflow_dir.glob("*.yml") if path.relative_to(repo).as_posix() not in excluded}
    assert set(pp.WORKFLOWS) == exported - {"pipeline-self-test.yml"}


@pytest.mark.parametrize("workflow,job_id", [("ci.yml", "codex"), ("weekly.yml", "codex-latest")])
def test_codex_checks_use_a_clean_profile_in_a_step_context(workflow, job_id):
    import yaml

    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
    job = config["jobs"][job_id]
    assert "CODEX_HOME" not in job["env"], "GitHub has no runner context in a job env"
    setup, rpc, server = job["steps"][-3:]
    assert "with an empty profile" in setup["name"]
    assert rpc["run"].endswith("--expect-signed-out") and server["run"].endswith("--expect-signed-out")
    for step in (setup, rpc, server):
        assert step["env"]["CODEX_HOME"] == "${{ runner.temp }}/sp-signed-out-codex"
