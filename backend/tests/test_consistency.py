"""The parts add up to the whole (scripts/check_consistency.py), on the demo
data and on the golden usage root, and the folder checked is never written.
By hand, the same script runs on the operator's folder (docs/testing.md case 4:
the split's parts once came to 443% of a total of 402% on real data)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.refusals import snapshot

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_consistency", REPO / "scripts" / "check_consistency.py")
assert _spec and _spec.loader
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


# The golden root's own moment, and the boundaries before it: a day's and a
# month's last second and first, and the night the clocks go back (in the
# zones the CI runs: UTC, Los Angeles, Kolkata).
@pytest.mark.parametrize("folder,now", [("fixtures", ""), ("testdata/usage/root", "2026-11-01T14:48:00"),
                                        ("testdata/usage/root", "2026-10-31T23:59:59"),
                                        ("testdata/usage/root", "2026-11-01T00:00:00"),
                                        ("testdata/usage/root", "2026-11-01T01:30:00")])
def test_the_parts_add_up_and_the_folder_is_not_written(folder, now, monkeypatch) -> None:
    if now:
        monkeypatch.setenv("SP_NOW", now)
    src = REPO / folder
    before = snapshot(src)
    lines: list[str] = []
    failed = cc.check(src, out=lines.append)
    assert not failed, "\n".join(lines)
    assert snapshot(src) == before
    if now == "2026-11-01T14:48:00":
        assert any("usage 7d:" in ln and " 0 chats" not in ln for ln in lines), lines


def test_a_total_that_is_not_the_sum_of_its_chats_fails(monkeypatch) -> None:
    from backend import usagelib
    real = usagelib.summary

    def off_by_one(*a, **k):
        got = real(*a, **k)
        got["totals"]["new_output"] = (got["totals"].get("new_output") or 0) + 1
        return got
    monkeypatch.setattr(usagelib, "summary", off_by_one)
    monkeypatch.setenv("SP_NOW", "2026-11-01T14:48:00")
    failed = cc.check(REPO / "testdata/usage/root", out=lambda s: None)
    assert any("new_output" in f for f in failed), failed
