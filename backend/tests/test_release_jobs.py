from pathlib import Path
from runpy import run_path

import pytest


@pytest.mark.parametrize("workflow", ["agents.yml", "machine.yml"])
@pytest.mark.parametrize("bad_provider", [None, "anthropic", "openai/codex", "openai/opencode"])
def test_release_gate_requires_each_provider_preflight(workflow, bad_provider):
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    sha = "a" * 40
    jobs = [
        {"name": name, "head_sha": sha, "conclusion": "success",
         "steps": [{"name": step, "conclusion": "success"} for step in steps]}
        for name, steps in module["required_jobs"](workflow).items() if not name.endswith(" key")
    ]
    for provider in ("anthropic", "openai/codex", "openai/opencode"):
        jobs.append({"name": f"L0 {provider} key", "head_sha": sha, "conclusion": "success", "steps": [
            {"name": "Check provider access, authentication and model errors",
             "conclusion": "skipped" if provider == bad_provider else "success"},
        ]})
    problem = module["problem"](workflow, {"jobs": jobs, "total_count": len(jobs)}, sha)
    if bad_provider is None:
        assert not problem
    else:
        assert f"required step did not pass: L0 {bad_provider}" in problem


@pytest.mark.parametrize("missing", [
    "Interactive agent (opencode, windows-latest)",
    "Interactive agent (claude-code, ubuntu-latest, trust dialog)",
    "Interactive agent (claude-code, macos-latest, trust dialog)",
    "Interactive agent (claude-code, windows-latest, trust dialog)",
])
def test_full_ci_cannot_release_with_a_missing_interactive_stub_job(missing):
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    sha = "b" * 40
    jobs = [
        {"name": name, "head_sha": sha, "conclusion": "success",
         "steps": [{"name": step, "conclusion": "success"} for step in steps]}
        for name, steps in module["required_jobs"]("ci.yml").items() if name != missing
    ]
    issue = module["problem"]("ci.yml", {"jobs": jobs, "total_count": len(jobs)}, sha)
    assert issue == f"required job missing: {missing}"


@pytest.mark.parametrize("os", ["macos-latest", "windows-latest"])
def test_full_ci_requires_the_offline_codex_core_on_all_systems(os):
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    sha = "c" * 40
    job_name = f"Interactive agent (codex, {os})"
    step_name = module["OFFLINE_CORE"]
    jobs = [
        {"name": name, "head_sha": sha, "conclusion": "success", "steps": [
            {"name": step, "conclusion": "success"} for step in steps if name != job_name or step != step_name
        ]}
        for name, steps in module["required_jobs"]("ci.yml").items()
    ]
    issue = module["problem"]("ci.yml", {"jobs": jobs, "total_count": len(jobs)}, sha)
    assert issue == f"required step did not pass: {job_name} / {step_name} (missing)"


def test_pipeline_proof_rejects_a_duplicate_named_step():
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    workflow = "pipeline-self-test.yml"
    name, (step,) = next(iter(module["required_jobs"](workflow).items()))
    sha = "d" * 40
    payload = {"total_count": 1, "jobs": [
        {"name": name, "head_sha": sha, "conclusion": "success",
         "steps": [{"name": step, "conclusion": "failure"}, {"name": step, "conclusion": "success"}]},
    ]}
    assert module["problem"](workflow, payload, sha) == f"duplicate required step: {name} / {step}"


@pytest.mark.parametrize(("name", "step"), [
    ("Backend (windows-latest, Python 3.12)", "Run tests (-rs: a skipped test is named, never silent)"),
    ("Backend (TZ=Asia/Kolkata)", "Only the skips expected on this system"),
    ("Backend (clock at 2026-11-30T23:59:58)", "Check that the clock suite actually ran"),
    ("Frontend (Node 22)", "Unit tests"),
    ("Fresh user (windows-latest)", "From clone to a working setup"),
    ("End to end (Playwright, macOS)", "Every page and the flows"),
    ("Launcher (ubuntu-latest)", "Nothing left serving"),
    ("Dependency audit", "Python (the versions users get)"),
])
def test_full_ci_rejects_a_green_job_when_its_test_step_was_skipped(name, step):
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    sha = "e" * 40
    required = module["required_jobs"]("ci.yml")
    jobs = [
        {"name": job, "head_sha": sha, "conclusion": "success",
         "steps": [{"name": action, "conclusion": "skipped" if (job, action) == (name, step) else "success"}
                   for action in steps]}
        for job, steps in required.items()
    ]
    assert module["problem"]("ci.yml", {"jobs": jobs, "total_count": len(jobs)}, sha) == (
        f"required step did not pass: {name} / {step} (skipped)"
    )
