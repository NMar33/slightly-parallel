"""Keep native command failures visible in GitHub Actions."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


MATRIX_LABEL = re.compile(r"\$\{\{\s*matrix\.(\w+)\s*\}\}")
ACTION_EXPRESSION = re.compile(r"\$\{\{[^}\n]*\}\}")
WIN32_LABEL = re.compile(r"\bwin32\b")
BENCHMARK_EXCEPTION = "${{ !inputs.expect_failure }}"
MASKED_FAILURE = re.compile(r"\|\|\s*(?:true\b|:(?=[\s;}]|$))|(?:^|[;{]|\|\|)\s*exit\s+0\b", re.I)
BASH_OVERRIDE = re.compile(r"(?:^|[;{])\s*(?:!\s|set\s+\+(?:[a-z]*e[a-z]*\b|o\s+(?:errexit|pipefail)\b))")
PWSH_PREFERENCE = r"(?:ErrorActionPreference|PSNativeCommandUseErrorActionPreference)"
PWSH_OVERRIDE = re.compile(
    rf"\$\{{?(?:(?:global|local|script|private|variable):)*{PWSH_PREFERENCE}\}}?\s*(?:[-+*/%]?=|\+\+|--)"
    rf"|(?:^|[;{{])\s*(?:(?:Set|New|Clear|Remove)-(?:Variable|Item)|sv|nv|clv|rv)\s+[^;\n]*\b{PWSH_PREFERENCE}\b"
    r"|\$PSDefaultParameterValues\s*\[\s*['\"][^'\"]*:ErrorAction['\"]\s*\]\s*="
    r"|\s-(?:ErrorAction|ea)(?:\s+|:)\s*['\"]?(?:SilentlyContinue|Ignore|Continue)\b",
    re.I,
)
PWSH_GUARDS = {"$erroractionpreference = 'stop'", "$psnativecommanduseerroractionpreference = $true"}


def runs_on_windows(job: dict) -> bool:
    runner = job.get("runs-on", "")
    if isinstance(runner, str) and (reference := MATRIX_LABEL.fullmatch(runner)):
        axis = reference[1]
        matrix = job.get("strategy", {}).get("matrix", {})
        if isinstance(matrix, dict) and isinstance(matrix.get(axis), list):
            runner = [*matrix[axis], *(row.get(axis, "") for row in matrix.get("include", []))]
    labels = str(runner).lower()
    return "windows" in labels or "${{" in labels or WIN32_LABEL.search(labels) is not None


def default_shell(block: dict) -> str:
    return block.get("defaults", {}).get("run", {}).get("shell", "")


def unsafe_steps(workflow: dict, *, workflow_name: str = "") -> list[str]:
    problems = []
    for name, job in workflow.get("jobs", {}).items():
        on_windows = runs_on_windows(job)
        continue_on_error = job.get("continue-on-error", False)
        benchmark = workflow_name == "terminal-bench.yml" and name == "bench"
        if continue_on_error is not False and not (benchmark and continue_on_error == BENCHMARK_EXCEPTION):
            problems.append(f"{name}: continue-on-error can hide a required job failure")
        if job.get("uses", "").startswith("./"):
            problems.append(f"{name}: review local reusable workflows before using them")
        inherited = default_shell(job) or default_shell(workflow)
        for index, step in enumerate(job.get("steps", []), 1):
            label = f"{name} / {step.get('name', index)}"
            if step.get("continue-on-error", False) is not False:
                problems.append(f"{label}: continue-on-error can hide a required step failure")
            if step.get("uses", "").startswith("./"):
                problems.append(f"{label}: review local actions before using them")
            if "run" not in step:
                continue
            shell = step.get("shell") or inherited
            if shell == "python":
                continue
            lines = [
                line.strip() for line in step["run"].splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if shell == "pwsh":
                if {line.lower() for line in lines[:2]} != PWSH_GUARDS:
                    problems.append(f"{label}: start pwsh with both native failure guards")
                    continue
                overrides = PWSH_OVERRIDE
                lines = lines[2:]
            elif shell == "bash" or (not shell and not on_windows):
                overrides = BASH_OVERRIDE
            else:
                problems.append(f"{label}: use bash, python or guarded pwsh")
                continue
            commands = (ACTION_EXPRESSION.sub("", line) for line in lines)
            if any(overrides.search(line) or MASKED_FAILURE.search(line) for line in commands):
                problems.append(f"{label}: shell code overrides fail-fast or masks command failures")
    return problems


def check(directory: Path) -> list[str]:
    return [f"{path.name}: {problem}"
            for path in sorted(directory.iterdir()) if path.suffix in {".yml", ".yaml"}
            for problem in unsafe_steps(yaml.safe_load(path.read_text(encoding="utf-8")), workflow_name=path.name)]


if __name__ == "__main__":
    issues = check(Path(sys.argv[1]))
    if issues:
        sys.exit("\n".join(issues))
    print("Workflow steps preserve native command failures.")
