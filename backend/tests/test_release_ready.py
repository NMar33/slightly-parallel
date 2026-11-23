"""scripts/release-ready.sh: a release needs CI (ci.yml) and the Terminal
window (terminal.yml) green on their first attempt for the branch's head
commit. The terminal bench (terminal-bench.yml) never gates.

The publish folder is a real git repository with a "github" remote (a bare
one); gh is a stub that answers from files and logs what it was asked.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import git_env

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release-ready.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                                reason="a bash script, run on Linux and macOS")

GH = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_GH/calls"
if [[ $1 == run && $2 == list ]]; then
  while [[ $# -gt 0 ]]; do [[ $1 == --workflow ]] && wf=$2; shift; done
  cat "$FAKE_GH/$wf" 2>/dev/null
  exit 0
fi
if [[ $1 == api ]]; then
  if [[ $* == *'/attempts/1/jobs?'* ]]; then
    path=${*: -1}
    path=${path%/attempts*}
    cat "$FAKE_GH/jobs_${path##*/}"
    exit $?
  fi
  id=${2##*/}
  cat "$FAKE_GH/attempt_$id" 2>/dev/null || echo 1
  exit 0
fi
exit 1
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=git_env(), check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    publish = tmp_path / "publish"
    publish.mkdir()
    _git(publish, "init", "-q", "-b", "master")
    (publish / "a").write_text("a")
    _git(publish, "add", "a")
    _git(publish, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a")
    _git(publish, "branch", "ci-windows")
    _git(publish, "remote", "add", "github", str(remote))
    _git(publish, "push", "-q", "github", "ci-windows")
    fake = tmp_path / "gh"
    fake.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(GH)
    (bin_dir / "gh").chmod(0o755)
    sha = _git(publish, "rev-parse", "HEAD")
    required_jobs = runpy.run_path(str(SCRIPT.parent / "ci" / "release_jobs.py"))["required_jobs"]

    def run(**workflows: str) -> subprocess.CompletedProcess:
        for name, line in workflows.items():
            filename = name.replace("_", "-").replace("-yml", ".yml")
            (fake / filename).write_text(line + "\n")
            if filename == "terminal-bench.yml":
                continue
            path = fake / f"jobs_{line.split()[0]}"
            if not path.exists():
                matrix = required_jobs(filename)
                if filename == "ci.yml":
                    matrix.update({f"CI job {i}": () for i in range(28 - len(matrix))})
                path.write_text(json.dumps({"total_count": len(matrix), "jobs": [
                    {"name": job, "head_sha": sha, "conclusion": "success",
                     "steps": [{"name": step, "conclusion": "success"} for step in steps]}
                    for job, steps in matrix.items()
                ]}))
        env = {**git_env(), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_GH": str(fake), "SP_PUBLISH": str(publish), "SP_PUBLISH_REPO": "o/r"}
        return subprocess.run(["bash", str(SCRIPT), "ci-windows", "v9.9.9"], env=env,
                              capture_output=True, text=True, timeout=60)

    run.fake = fake  # type: ignore[attr-defined]
    return run


def test_both_green_prints_the_release_commands(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success",
              weekly_yml="33 completed success", agents_yml="44 completed success", machine_yml="55 completed success")
    assert r.returncode == 0, r.stderr
    assert "CI run 11 passed" in r.stdout and "Machine full run 55 passed" in r.stdout
    assert "git tag -a v9.9.9" in r.stdout


def test_release_selects_full_workflow_profiles_for_the_candidate(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success",
              weekly_yml="33 completed success", agents_yml="44 completed success", machine_yml="55 completed success")
    assert r.returncode == 0, r.stderr
    rows = (world.fake / "calls").read_text(encoding="utf-8").splitlines()
    for workflow, profile in (("ci.yml", "CI (full)"), ("agents.yml", "Agents (core, pinned)"),
                              ("machine.yml", "Machine (full)")):
        invocation = next(line for line in rows if line.startswith("run list") and f"--workflow {workflow} " in line)
        assert f'.displayTitle == "{profile}"' in invocation
        assert "--commit " in invocation


def test_a_red_window_stops_the_release(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed failure")
    assert r.returncode == 1
    assert "Terminal window run 22" in r.stderr and "ended: failure" in r.stderr
    assert "git tag" not in r.stdout


def test_no_window_run_says_how_to_start_one(world) -> None:
    r = world(ci_yml="11 completed success")
    assert r.returncode == 1
    assert "no Terminal window run for" in r.stderr
    assert "gh workflow run terminal.yml --repo o/r --ref ci-windows" in r.stderr


def test_no_ci_run_says_so_and_not_still_null(world) -> None:
    r = world(terminal_yml="22 completed success")
    assert r.returncode == 1
    assert "no CI run for" in r.stderr and "null" not in r.stderr


def test_a_window_green_only_on_a_rerun_does_not_count(world) -> None:
    (world.fake / "attempt_22").write_text("2\n")
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success")
    assert r.returncode == 1
    assert "Terminal window run 22" in r.stderr and "attempt 2" in r.stderr


def test_a_candidate_without_an_agents_run_cannot_release(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success",
              weekly_yml="33 completed success", machine_yml="55 completed success")
    assert r.returncode == 1
    assert "no Agents run for" in r.stderr
    assert "git tag" not in r.stdout


def test_the_bench_never_gates(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success",
              weekly_yml="33 completed success", agents_yml="44 completed success", machine_yml="55 completed success",
              terminal_bench_yml="33 completed failure")
    assert r.returncode == 0, r.stderr
    assert "terminal-bench.yml" not in (world.fake / "calls").read_text()


@pytest.mark.parametrize("variant", ["one tool", "no key", "smoke instead of core", "different SHA"])
def test_green_workflow_with_incomplete_agents_evidence_is_blocked(world, variant) -> None:
    expected = dict(ci_yml="11 completed success", terminal_yml="22 completed success",
                    weekly_yml="33 completed success", agents_yml="44 completed success", machine_yml="55 completed success")
    assert world(**expected).returncode == 0
    agents_file = world.fake / "jobs_44"
    page = json.loads(agents_file.read_text())
    if variant == "one tool":
        page["jobs"] = page["jobs"][:3]
        page["total_count"] = 3
    elif variant == "no key":
        page["jobs"][0]["steps"][0]["conclusion"] = "skipped"
    elif variant == "smoke instead of core":
        page["jobs"][0]["steps"][0]["name"] = "An agent from clone to its work on the pages (smoke, pinned)"
    else:
        page["jobs"][0]["head_sha"] = "a" * 40
    agents_file.write_text(json.dumps(page))
    r = world(**expected)
    assert r.returncode == 1
    assert "Agents run 44" in r.stderr
    assert "git tag" not in r.stdout
