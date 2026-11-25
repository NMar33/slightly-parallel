from pathlib import Path
from runpy import run_path

import pytest


@pytest.mark.parametrize("bad_provider", [None, "anthropic", "openai"])
def test_core_gate_requires_both_provider_preflights(bad_provider):
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "ci" / "release_jobs.py"))
    sha = "a" * 40
    jobs = [
        {"name": name, "head_sha": sha, "conclusion": "success",
         "steps": [{"name": step, "conclusion": "success"} for step in steps]}
        for name, steps in module["required_jobs"]("agents.yml").items() if name not in ("L0 anthropic", "L0 openai")
    ]
    for provider in ("anthropic", "openai"):
        jobs.append({"name": f"L0 {provider}", "head_sha": sha, "conclusion": "success", "steps": [
            {"name": "Check provider access, authentication and model errors",
             "conclusion": "skipped" if provider == bad_provider else "success"},
        ]})
    problem = module["problem"]("agents.yml", {"jobs": jobs, "total_count": len(jobs)}, sha)
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
    jobs.extend({"name": f"Optional job {index}", "head_sha": sha, "conclusion": "success"} for index in range(30))
    issue = module["problem"]("ci.yml", {"jobs": jobs, "total_count": len(jobs)}, sha)
    assert issue == f"required job missing: {missing}"
