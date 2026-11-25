"""Keep native command failures visible in GitHub Actions on Windows."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


MATRIX_LABEL = re.compile(r"\$\{\{\s*matrix\.(\w+)\s*\}\}")


def runs_on_windows(job: dict) -> bool:
    runner = job.get("runs-on", "")
    if isinstance(runner, str) and (reference := MATRIX_LABEL.fullmatch(runner)):
        axis = reference[1]
        matrix = job.get("strategy", {}).get("matrix", {})
        if isinstance(matrix, dict) and isinstance(matrix.get(axis), list):
            runner = [*matrix[axis], *(row.get(axis, "") for row in matrix.get("include", []))]
    labels = str(runner).lower()
    return "windows" in labels or "${{" in labels


def default_shell(block: dict) -> str:
    return block.get("defaults", {}).get("run", {}).get("shell", "")


def unsafe_steps(workflow: dict) -> list[str]:
    problems = []
    for name, job in workflow.get("jobs", {}).items():
        if not runs_on_windows(job):
            continue
        inherited = default_shell(job) or default_shell(workflow)
        for index, step in enumerate(job.get("steps", []), 1):
            if "run" not in step:
                continue
            shell = step.get("shell") or inherited
            if shell in {"bash", "python"}:
                continue
            if shell == "pwsh":
                lines = [line.strip().lower() for line in step["run"].splitlines()
                         if line.strip() and not line.lstrip().startswith("#")]
                guards = {"$erroractionpreference = 'stop'", "$psnativecommanduseerroractionpreference = $true"}
                if set(lines[:2]) == guards:
                    continue
            problems.append(f"{name} / {step.get('name', index)}: use bash, python or guarded pwsh")
    return problems


def check(directory: Path) -> list[str]:
    return [f"{path.name}: {problem}"
            for path in sorted(directory.iterdir()) if path.suffix in {".yml", ".yaml"}
            for problem in unsafe_steps(yaml.safe_load(path.read_text(encoding="utf-8")))]


if __name__ == "__main__":
    issues = check(Path(sys.argv[1]))
    if issues:
        sys.exit("\n".join(issues))
    print("Windows workflow steps preserve native command failures.")
