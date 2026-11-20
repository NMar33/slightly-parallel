"""scripts/release-ready.sh: a release needs CI (ci.yml) and the Terminal
window (terminal.yml) green on their first attempt for the branch's head
commit. The terminal bench (terminal-bench.yml) never gates.

The publish folder is a real git repository with a "github" remote (a bare
one); gh is a stub that answers from files and logs what it was asked.
"""

from __future__ import annotations

import os
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

    def run(**workflows: str) -> subprocess.CompletedProcess:
        for name, line in workflows.items():
            (fake / name.replace("_", "-").replace("-yml", ".yml")).write_text(line + "\n")
        env = {**git_env(), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_GH": str(fake), "SP_PUBLISH": str(publish), "SP_PUBLISH_REPO": "o/r"}
        return subprocess.run(["bash", str(SCRIPT), "ci-windows", "v9.9.9"], env=env,
                              capture_output=True, text=True, timeout=60)

    run.fake = fake  # type: ignore[attr-defined]
    return run


def test_both_green_prints_the_release_commands(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success")
    assert r.returncode == 0, r.stderr
    assert "CI run 11 and Terminal window run 22 passed" in r.stdout
    assert "git tag -a v9.9.9" in r.stdout


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


def test_the_bench_never_gates(world) -> None:
    r = world(ci_yml="11 completed success", terminal_yml="22 completed success",
              terminal_bench_yml="33 completed failure")
    assert r.returncode == 0, r.stderr
    assert "terminal-bench.yml" not in (world.fake / "calls").read_text()
