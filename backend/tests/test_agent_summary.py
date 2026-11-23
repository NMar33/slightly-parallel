from pathlib import Path
from runpy import run_path


def test_a_run_with_only_unpriced_usage_does_not_report_zero_cost() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_summary.py"
    summary_line = run_path(str(script))["summary_line"]
    line = summary_line({"cli_versions": {"opencode": "1.19.3"}, "model_cost": {"cost_usd": 0, "unpriced": 165260}})
    assert "opencode 1.19.3" in line
    assert "model cost: unavailable" in line and "165260 unpriced tokens" in line
    assert "$0.0000" not in line
