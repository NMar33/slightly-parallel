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
