"""scripts/release.sh: what counts as "not committed" before a release tree is made."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git")


def _unsaved(repo: Path) -> list[str]:
    text = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    fn = re.search(r"^unsaved\(\) \{.*?^\}", text, re.S | re.M)
    assert fn, "release.sh has no unsaved()"
    out = subprocess.run(["bash", "-c", fn.group(0) + "\nunsaved"], cwd=repo, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


def test_only_what_a_release_would_lose_stops_it(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "release-exclude.txt").write_text("# left out\nbrand/\nnotes/\nsecret.txt\n")
    (tmp_path / "src" / "a").write_text("x\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "first")
    assert _unsaved(tmp_path) == []

    # A new file in a folder no release carries changes nothing, a space in its name or not.
    (tmp_path / "brand" / "video ideas").mkdir(parents=True)
    (tmp_path / "brand" / "video ideas" / "post.md").write_text("y\n")
    (tmp_path / "secret.txt").write_text("s\n")
    assert _unsaved(tmp_path) == []

    # A new file anywhere else would be left out of the release: named.
    (tmp_path / "src" / "new").write_text("z\n")
    assert _unsaved(tmp_path) == ["?? src/new"]
    (tmp_path / "src" / "new").unlink()

    # A name that only starts like a left-out folder is not in it.
    (tmp_path / "brandx").write_text("q\n")
    assert _unsaved(tmp_path) == ["?? brandx"]
    (tmp_path / "brandx").unlink()

    # A change to a tracked file is named, in a left-out folder too: it was committed there once.
    (tmp_path / "src" / "a").write_text("changed\n")
    assert _unsaved(tmp_path) == [" M src/a"]


def test_the_demo_servers_token_is_never_a_change() -> None:
    """A server started on fixtures/ writes the operator's token there: a secret, ignored."""
    out = subprocess.run(["git", "check-ignore", "-q", "fixtures/operator.token"], cwd=ROOT)
    assert out.returncode == 0
