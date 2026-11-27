"""Write the CLI versions and model cost to the Actions job summary."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path


def summary_line(notes: dict, limit: float | None = None) -> str:
    versions = ", ".join(f"{tool} {version}" for tool, version in notes.get("cli_versions", {}).items()) or "unavailable"
    measured = notes.get("model_cost", {})
    dollars = measured.get("cost_usd")
    unpriced = measured.get("unpriced") or 0
    known = dollars is not None and (dollars > 0 or not unpriced)
    cost = f"${dollars:.4f} estimated at API prices" if known else "unavailable"
    if unpriced:
        cost += f" · {unpriced} unpriced tokens"
    line = f"CLI: {versions} · model cost: {cost}"
    if limit is not None:
        verdict = budget_passed(notes, limit)
        line += f" · estimated spend limit: ${limit:.2f} per job ({'pass' if verdict else 'fail'})"
    return line


def budget_passed(notes: dict, limit: float) -> bool:
    measured = notes.get("model_cost", {})
    dollars = measured.get("cost_usd")
    return (math.isfinite(limit) and limit > 0 and not measured.get("unpriced")
            and isinstance(dollars, (int, float)) and not isinstance(dollars, bool)
            and math.isfinite(dollars) and 0 <= dollars <= limit)


def failure_lines(report: dict) -> list[str]:
    return [f"FAIL [{check.get('failure_class') or 'unclassified'}] {check['stage']} / {check['name']}"
            for check in report.get("checks", ()) if not check["ok"] and not check.get("soft")]


if __name__ == "__main__":
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".sp/fresh-user/report.json")
    result = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    notes = result.get("notes", {})
    configured_limit = os.environ.get("SP_AGENT_COST_LIMIT_USD")
    limit = float(configured_limit) if configured_limit else None
    line = summary_line(notes, limit)
    lines = [line, *failure_lines(result)]
    print("\n".join(lines))
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")
    if limit is not None and not budget_passed(notes, limit):
        sys.exit(1)
