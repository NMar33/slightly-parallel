"""scripts/layout_proof.py, the no-change proof on a copy of the data
(tk_d1d25a4d): what it refuses, and what it leaves behind."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "layout_proof.py"


def _proof():
    spec = importlib.util.spec_from_file_location("sp_layout_proof", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sp_layout_proof"] = mod
    spec.loader.exec_module(mod)
    return mod


def _args(source: Path, out: Path, **kw) -> argparse.Namespace:
    base = dict(source=str(source), out=str(out), commit="HEAD", repo=None, port=1, python=sys.executable,
                checkup_cwd=str(source))
    return argparse.Namespace(**{**base, **kw})


def test_an_out_inside_the_source_is_refused(tmp_path: Path) -> None:
    proof = _proof()
    source = tmp_path / "data"
    (source / "projects").mkdir(parents=True)
    before = sorted(p.relative_to(source) for p in source.rglob("*"))
    for out in (source / "proof", source / "projects" / "x" / "proof", source):
        with pytest.raises(SystemExit, match="inside the source"):
            # --repo, not --commit: no checkout is made even if the refusal is missing
            proof.run(_args(source, out, commit=None, repo=str(tmp_path / "nowhere")))
    assert sorted(p.relative_to(source) for p in source.rglob("*")) == before   # nothing made in it


def test_the_checkout_is_removed_after_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run with --commit removes its worktree and prunes, even when a later
    step fails."""
    proof = _proof()
    source = tmp_path / "data"
    source.mkdir()
    calls: list[list[str]] = []
    real = subprocess.run

    def fake(cmd, *a, **kw):
        calls.append([str(c) for c in cmd])
        if cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            Path(cmd[cmd.index("--detach") + 1]).mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "git" and "worktree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "cp":
            raise subprocess.CalledProcessError(1, cmd)     # a step after the checkout fails
        return real(cmd, *a, **kw)

    monkeypatch.setattr(proof.subprocess, "run", fake)
    with pytest.raises(subprocess.CalledProcessError):
        proof.run(_args(source, tmp_path / "out"))
    worktree = [c for c in calls if c[0] == "git" and "worktree" in c]
    code = str(tmp_path / "out" / "code")
    assert [c[c.index("worktree") + 1:] for c in worktree] == [
        ["add", "--detach", code, "HEAD"], ["remove", "--force", code], ["prune"]]
