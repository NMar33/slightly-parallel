"""Write the CLI versions and model cost to the Actions job summary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def summary_line(notes: dict) -> str:
    versions = ", ".join(f"{tool} {version}" for tool, version in notes.get("cli_versions", {}).items()) or "unavailable"
    measured = notes.get("model_cost", {})
    dollars = measured.get("cost_usd")
    unpriced = measured.get("unpriced") or 0
    known = dollars is not None and (dollars > 0 or not unpriced)
    cost = f"${dollars:.4f} estimated at API prices" if known else "unavailable"
    if unpriced:
        cost += f" · {unpriced} unpriced tokens"
    return f"CLI: {versions} · model cost: {cost}"


if __name__ == "__main__":
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".sp/fresh-user/report.json")
    notes = json.loads(report.read_text(encoding="utf-8")).get("notes", {}) if report.is_file() else {}
    line = summary_line(notes)
    print(line)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(line + "\n")
