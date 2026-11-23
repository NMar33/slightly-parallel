from pathlib import Path
from runpy import run_path

import pytest


def test_a_run_with_only_unpriced_usage_does_not_report_zero_cost() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_summary.py"
    summary_line = run_path(str(script))["summary_line"]
    line = summary_line({"cli_versions": {"opencode": "1.19.3"}, "model_cost": {"cost_usd": 0, "unpriced": 165260}})
    assert "opencode 1.19.3" in line
    assert "model cost: unavailable" in line and "165260 unpriced tokens" in line
    assert "$0.0000" not in line



@pytest.mark.parametrize(("usage", "ok"), [
    ({"cost_usd": 0.04, "unpriced": 0}, True),
    ({"cost_usd": 0.11, "unpriced": 0}, False),
    ({"cost_usd": 0.04, "unpriced": 12}, False),
    ({}, False),
])
def test_summary_reports_a_cost_limit_and_fails_closed(usage, ok):
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_summary.py"
    module = run_path(str(script))
    notes = {"model_cost": usage}
    assert module["budget_passed"](notes, 0.10) is ok
    verdict = "pass" if ok else "fail"
    assert f"estimated spend limit: $0.10 per job ({verdict})" in module["summary_line"](notes, 0.10)
