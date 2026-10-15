#!/usr/bin/env python3
"""
pdr_doctor — the "keep the wheels on" health check for the Slightly Parallel dashboard.

Runs a battery of read-only checks against the agents data root
(default: SP_DATA_ROOT / SCAN_DATA_ROOT env, falling back to the repo's
``fixtures/`` demo data) and the local build environment,
then prints a friendly report.

Exit codes:
    0  — everything is healthy (WARN-level findings allowed)
    1  — at least one ERROR-level finding (dashboard likely broken)
    2  — the doctor itself couldn't run (path missing, permissions, …)

Usage:
    ./pdr_doctor.py                     # default agents root
    ./pdr_doctor.py --root /some/path   # override
    ./pdr_doctor.py --json              # machine-readable output

Design notes:
    • Never writes. Ever. Read-only, like the dashboard.
    • Every check has a suggested fix (`hint`) — no "something's wrong, good luck".
    • Cyrillic-safe (all IO is utf-8).
    • YYMM-DD aware — flags any date that doesn't parse.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import socket
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Defaults + constants
# ---------------------------------------------------------------------------

DEFAULT_AGENTS_ROOT = Path(
    os.environ.get("SP_DATA_ROOT")
    or os.environ.get("SCAN_DATA_ROOT")
    or os.environ.get("DATA_ROOT")
    or Path(__file__).resolve().parents[1] / "fixtures"
).expanduser()
# The repository this script sits in — it used to be hard-coded to a sibling
# folder named "mvp" that no longer exists, so every run warned about a venv
# in a tree nobody has.
DEFAULT_MVP_ROOT    = Path(__file__).resolve().parents[1]

# Columns we require to exist (subset — extra columns are fine).
GOALS_REQUIRED = {
    "id", "goal_text", "created_date", "agent_id", "status",
}
DECISIONS_REQUIRED = {
    "id", "decision_text", "agent_id",
}
ACTIVITY_REQUIRED_ANY = [
    # Real fixtures use one of these date column names; either is acceptable.
    {"date", "duration_min", "agent_id"},
    {"created_date", "duration_min", "agent_id"},
]

YYMMDD_RE = re.compile(r"^\d{4}-\d{2}$")  # e.g. 2608-06

DASHBOARD_PORT = 8123

# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------

Severity = str  # "OK" | "WARN" | "ERROR"


@dataclass
class Finding:
    check:    str
    severity: Severity
    message:  str
    hint:     str = ""
    where:    str = ""

    def as_line(self, use_color: bool = True) -> str:
        colors = {
            "OK":    "\033[32m",   # green
            "WARN":  "\033[33m",   # yellow
            "ERROR": "\033[31m",   # red
        }
        reset = "\033[0m"
        tag = f"[{self.severity:>5}]"
        if use_color:
            tag = f"{colors.get(self.severity, '')}{tag}{reset}"
        line = f"{tag} {self.check}: {self.message}"
        if self.where:
            line += f"\n         at: {self.where}"
        if self.hint and self.severity != "OK":
            line += f"\n         fix: {self.hint}"
        return line


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, *f: Finding) -> None:
        self.findings.extend(f)

    def worst(self) -> Severity:
        levels = {"OK": 0, "WARN": 1, "ERROR": 2}
        return max((f.severity for f in self.findings), key=lambda s: levels.get(s, 0), default="OK")

    def exit_code(self) -> int:
        return 1 if self.worst() == "ERROR" else 0


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_agents_root(root: Path) -> Iterable[Finding]:
    if not root.exists():
        yield Finding(
            "agents-root", "ERROR",
            f"agents root does not exist: {root}",
            hint="create the directory or pass --root <path>",
            where=str(root),
        )
        return
    if not root.is_dir():
        yield Finding("agents-root", "ERROR", f"path is not a directory: {root}", where=str(root))
        return
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        yield Finding(
            "agents-root", "ERROR",
            "no `projects/` subdirectory under agents root",
            hint=f"expected {projects_dir}",
            where=str(root),
        )
        return
    yield Finding("agents-root", "OK", f"found {root}")


def _iter_projects(root: Path) -> list[Path]:
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted([p for p in projects_dir.iterdir() if p.is_dir() and not p.name.startswith(".")])


def check_projects_present(root: Path) -> Iterable[Finding]:
    projects = _iter_projects(root)
    if not projects:
        yield Finding(
            "projects", "ERROR",
            "no project directories found under projects/",
            hint="start an agent — the dashboard populates from what's on disk",
            where=str(root / "projects"),
        )
        return
    yield Finding("projects", "OK", f"{len(projects)} project(s): {', '.join(p.name for p in projects)}")


def _read_csv_header(path: Path) -> set[str] | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            first = next(reader, None)
            if first is None:
                return set()
            return {c.strip() for c in first}
    except Exception:
        return None


def check_csv_schemas(root: Path) -> Iterable[Finding]:
    for project in _iter_projects(root):
        # goals.csv — retired. The product no longer writes goals, so its
        # absence is the normal state and says nothing; only a goals.csv that
        # is there and malformed is worth a word.
        goals = project / "goals.csv"
        if goals.exists():
            header = _read_csv_header(goals)
            if header is None:
                yield Finding("goals.csv", "ERROR", f"cannot read {goals}", hint="check file encoding is utf-8", where=str(goals))
            else:
                missing = GOALS_REQUIRED - header
                if missing:
                    yield Finding(
                        "goals.csv", "ERROR",
                        f"{project.name}: missing columns: {sorted(missing)}",
                        hint=f"expected superset of: {sorted(GOALS_REQUIRED)}",
                        where=str(goals),
                    )
                else:
                    yield Finding("goals.csv", "OK", f"{project.name}: schema ok ({len(header)} cols)")

        # decisions.csv
        decisions = project / "decisions.csv"
        if not decisions.exists():
            yield Finding(
                "decisions.csv", "WARN",
                f"missing in project {project.name}",
                hint="agents write this when they log decisions via the Slightly Parallel API",
                where=str(decisions),
            )
        else:
            header = _read_csv_header(decisions)
            if header is None:
                yield Finding("decisions.csv", "ERROR", f"cannot read {decisions}", hint="check utf-8", where=str(decisions))
            else:
                missing = DECISIONS_REQUIRED - header
                if missing:
                    yield Finding("decisions.csv", "ERROR",
                                  f"{project.name}: missing columns: {sorted(missing)}",
                                  hint=f"expected superset of: {sorted(DECISIONS_REQUIRED)}",
                                  where=str(decisions))
                else:
                    yield Finding("decisions.csv", "OK", f"{project.name}: schema ok ({len(header)} cols)")

        # activity_log.csv — accept either of two schema shapes
        activity = project / "activity_log.csv"
        if not activity.exists():
            yield Finding("activity_log.csv", "WARN",
                          f"missing in project {project.name}",
                          hint="populated by the capture hooks",
                          where=str(activity))
        else:
            header = _read_csv_header(activity)
            if header is None:
                yield Finding("activity_log.csv", "ERROR", f"cannot read {activity}", where=str(activity))
            elif not any(req.issubset(header) for req in ACTIVITY_REQUIRED_ANY):
                yield Finding(
                    "activity_log.csv", "ERROR",
                    f"{project.name}: header {sorted(header)} matches none of the expected shapes",
                    hint=f"expected superset of one of: {[sorted(r) for r in ACTIVITY_REQUIRED_ANY]}",
                    where=str(activity),
                )
            else:
                yield Finding("activity_log.csv", "OK", f"{project.name}: schema ok ({len(header)} cols)")


def check_meta_json(root: Path) -> Iterable[Finding]:
    total = 0
    bad = 0
    for project in _iter_projects(root):
        chats_dir = project / "chats"
        if not chats_dir.is_dir():
            continue
        for meta in chats_dir.rglob("meta.json"):
            total += 1
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("root is not an object")
            except Exception as e:
                bad += 1
                yield Finding(
                    "meta.json", "ERROR",
                    f"cannot parse: {e}",
                    hint="restore from backup, or delete if the agent is dead",
                    where=str(meta),
                )
    if total == 0:
        yield Finding("meta.json", "WARN",
                      "no meta.json files found under any project's chats/",
                      hint="agents create these on first activity — expected if MVP is fresh")
    elif bad == 0:
        yield Finding("meta.json", "OK", f"{total} meta.json file(s) parse cleanly")


def check_yymm_dates(root: Path) -> Iterable[Finding]:
    """Sample-check that date columns look like YYMM-DD (the Slightly Parallel date convention)."""
    bad_examples: list[tuple[Path, str, str]] = []
    checked = 0
    # The root ledgers the product writes today, plus the per-project
    # overlays that older data roots still carry.
    paths = [root / n for n in (
        "tasks.csv", "task_events.csv", "scans.csv", "standups.csv",
        "decisions.csv", "problems.csv", "rules.csv", "visions.csv",
        "skills.csv", "artifacts.csv", "architecture.csv", "files.csv",
        "sprints.csv",
    )]
    for project in _iter_projects(root):
        paths += [project / n for n in
                  ("goals.csv", "decisions.csv", "activity_log.csv")]
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for col in ("created_date", "date", "retro_date"):
                        val = (row.get(col) or "").strip()
                        if not val:
                            continue
                        checked += 1
                        if not YYMMDD_RE.match(val):
                            bad_examples.append((path, col, val))
                            if len(bad_examples) >= 5:
                                break
                    if len(bad_examples) >= 5:
                        break
        except Exception:
            pass
    if checked == 0:
        yield Finding("dates", "WARN", "no dated rows to sample")
        return
    if bad_examples:
        preview = "; ".join(f"{p.name}:{c}={v!r}" for p, c, v in bad_examples[:3])
        yield Finding(
            "dates", "ERROR",
            f"{len(bad_examples)}+ row(s) do not match YYMM-DD (e.g. {preview})",
            hint="dates must be YYMM-DD (e.g. 2608-06). Fix in the CSV or the agent that wrote it.",
        )
    else:
        yield Finding("dates", "OK", f"{checked} date value(s) sampled, all YYMM-DD")


def check_mvp_layout(mvp_root: Path) -> Iterable[Finding]:
    if not mvp_root.exists():
        yield Finding("mvp-root", "WARN",
                      f"MVP root not found: {mvp_root}",
                      hint="skipping venv / node_modules checks")
        return
    yield Finding("mvp-root", "OK", str(mvp_root))

    venv = mvp_root / "backend" / ".venv"
    if venv.is_dir():
        yield Finding("venv", "OK", f"found at {venv}")
    else:
        yield Finding("venv", "WARN",
                      "no .venv/ — backend can't run until it's created",
                      hint=f"cd {mvp_root}/backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt",
                      where=str(venv))

    frontend = mvp_root / "frontend"
    if frontend.is_dir():
        node_modules = frontend / "node_modules"
        if node_modules.is_dir():
            yield Finding("node_modules", "OK", "installed")
        else:
            yield Finding("node_modules", "WARN",
                          "frontend deps not installed",
                          hint=f"cd {frontend} && npm install",
                          where=str(node_modules))
    else:
        yield Finding("frontend", "WARN", "no frontend/ directory", where=str(frontend))


def check_binaries() -> Iterable[Finding]:
    for exe, hint in [
        ("python3", "install Python 3.11+"),
        ("node",    "install Node 20+ (nvm recommended)"),
        ("npm",     "ships with Node"),
    ]:
        if shutil.which(exe):
            yield Finding(f"bin:{exe}", "OK", f"found at {shutil.which(exe)}")
        else:
            yield Finding(f"bin:{exe}", "ERROR", f"{exe} not on PATH", hint=hint)


def check_port_free(port: int = DASHBOARD_PORT) -> Iterable[Finding]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        yield Finding(f"port:{port}", "OK", "free")
    except OSError:
        yield Finding(
            f"port:{port}", "WARN",
            f"port {port} is in use",
            hint=f"if it's already the dashboard, fine; otherwise: `lsof -i :{port}` to see who",
        )
    finally:
        s.close()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def run(root: Path, mvp_root: Path) -> Report:
    r = Report()
    r.add(*list(check_agents_root(root)))
    if r.worst() != "ERROR":
        r.add(*list(check_projects_present(root)))
        r.add(*list(check_csv_schemas(root)))
        r.add(*list(check_meta_json(root)))
        r.add(*list(check_yymm_dates(root)))
    r.add(*list(check_mvp_layout(mvp_root)))
    r.add(*list(check_binaries()))
    r.add(*list(check_port_free(DASHBOARD_PORT)))
    return r


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pdr_doctor",
        description="Health check for the Slightly Parallel agents dashboard.",
    )
    p.add_argument("--root", type=Path, default=DEFAULT_AGENTS_ROOT,
                   help=f"path to agents root (default: {DEFAULT_AGENTS_ROOT})")
    p.add_argument("--mvp-root", type=Path, default=DEFAULT_MVP_ROOT,
                   help=f"path to dashboard MVP (default: {DEFAULT_MVP_ROOT})")
    p.add_argument("--json", action="store_true", help="emit JSON instead of pretty text")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors in text output")
    args = p.parse_args(argv)

    try:
        report = run(args.root.expanduser().resolve(), args.mvp_root.expanduser().resolve())
    except Exception as e:
        # Something we didn't anticipate — exit 2 so callers can tell "doctor
        # itself is broken" from "dashboard has issues".
        print(f"pdr_doctor failed: {e}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "worst": report.worst(),
            "findings": [asdict(f) for f in report.findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        use_color = sys.stdout.isatty() and not args.no_color and not os.environ.get("NO_COLOR")
        counts = {"OK": 0, "WARN": 0, "ERROR": 0}
        for f in report.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
            print(f.as_line(use_color=use_color))
        print()
        print(f"summary: {counts.get('OK', 0)} ok · "
              f"{counts.get('WARN', 0)} warn · {counts.get('ERROR', 0)} error")
        print(f"verdict: {'healthy' if report.worst() != 'ERROR' else 'needs attention'}")

    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
