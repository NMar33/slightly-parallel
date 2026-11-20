"""Keep a per-area budget for hard-coded settings and exact cross-file copies."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path("scripts/ci/refactoring_budget.json")
AREAS = ("backend", "scripts", "frontend/src", "desktop")
SOURCE_SUFFIXES = {".py", ".js", ".cjs", ".mjs", ".ts", ".tsx"}
EXCLUDED = {"test", "tests", "e2e", "__tests__", "fixtures"}
DETECTOR_VERSION = 3
POLICY_NAME = re.compile(
    r"(?:^|_)(?:timeout|delay|interval|retries|tries|limit|threshold|port|size)(?:_|$)", re.IGNORECASE,
)
POSITIONAL_TIMER_ARG = {"sleep": 0, "wait": 0, "wait_for": 1, "Timer": 0}
SETTING_NAME = re.compile(
    r"_(?:NS|US|MS|S|SEC|SECS|SECONDS|MINUTES|HOURS|DAYS|BYTES|KB|MB|GB|PX|CHARS)$"
    r"|(?:^|_)(?:MAX|MIN|COUNT|ATTEMPTS|TRIES|RETRIES|LIMIT|PORT|WORKERS|ROWS|ITEMS|ENTRIES|STEPS)(?:_|$)",
    re.IGNORECASE,
)
DUPLICATE_LINES = 6
MIN_LINE_CHARS = 14
MIN_DUPLICATE_CHARS = 150


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8")


def sources() -> dict[str, list[str]]:
    paths = git("ls-files", "-z", "--", *AREAS).split("\0")
    return {
        area: [
            path for path in paths if path.startswith(area + "/")
            and Path(path).suffix in SOURCE_SUFFIXES
            and not EXCLUDED.intersection(Path(path).parts)
            and not re.search(r"\.(?:spec|test)\.", path)
        ]
        for area in AREAS
    }


def number(node: ast.AST | None) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value not in (0, 1)


def unnamed_setting_target(target: ast.AST) -> bool:
    if not isinstance(target, ast.Name) or not POLICY_NAME.search(target.id):
        return False
    return not (target.id.isupper() and SETTING_NAME.search(target.id))


def python_count(path: str, source: str) -> int:
    nodes = list(ast.walk(ast.parse(source, filename=path)))
    unnamed: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Assign) and number(node.value):
            unnamed.update(t.id for t in node.targets if isinstance(t, ast.Name) and not SETTING_NAME.search(t.id))
        elif (
            isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            and number(node.value) and not SETTING_NAME.search(node.target.id)
        ):
            unnamed.add(node.target.id)

    def candidates():
        for node in nodes:
            if isinstance(node, ast.keyword) and node.arg and POLICY_NAME.search(node.arg):
                yield node.value
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                positional = [*args.posonlyargs, *args.args]
                defaults = zip(positional[len(positional) - len(args.defaults):], args.defaults)
                for arg, default in [*defaults, *zip(args.kwonlyargs, args.kw_defaults)]:
                    if POLICY_NAME.search(arg.arg):
                        yield default
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
                position = POSITIONAL_TIMER_ARG.get(name)
                if position is not None and len(node.args) > position:
                    yield node.args[position]
                elif name == "range":
                    yield from node.args
                elif name == "getattr" and len(node.args) == 3:
                    key = node.args[1]
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) and POLICY_NAME.search(key.value):
                        yield node.args[2]
            elif (
                isinstance(node, ast.Assign) and any(unnamed_setting_target(t) for t in node.targets)
                or isinstance(node, ast.AnnAssign) and unnamed_setting_target(node.target)
            ):
                yield node.value

    return sum(number(node) or isinstance(node, ast.Name) and node.id in unnamed for node in candidates())


def duplicate_windows(texts: dict[str, str]) -> int:
    seen: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for path, text in texts.items():
        lines = [" ".join(line.split()) for line in text.splitlines()
                 if len(line.strip()) >= MIN_LINE_CHARS and not line.lstrip().startswith(("#", "//", "/*", "*", "<!--"))]
        for index in range(len(lines) - DUPLICATE_LINES + 1):
            window = tuple(lines[index:index + DUPLICATE_LINES])
            if sum(map(len, window)) >= MIN_DUPLICATE_CHARS:
                seen[window].add(path)
    return sum(len(paths) > 1 for paths in seen.values())


def measure() -> dict[str, dict[str, int]]:
    groups = sources()
    js_files = [p for paths in groups.values() for p in paths if not p.endswith(".py")]
    js_counts = json.loads(subprocess.check_output(
        ["node", "scripts/ci/refactoring_budget_ts.cjs"], cwd=ROOT,
        input=json.dumps(js_files), encoding="utf-8",
    ))
    out = {}
    for area, paths in groups.items():
        texts = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
        out[area] = {
            "numeric_settings": sum(
                python_count(p, text) if p.endswith(".py") else js_counts[p] for p, text in texts.items()
            ),
            "duplicate_windows": duplicate_windows(texts),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="record the current per-area counts")
    parser.add_argument("--base", default="HEAD^", help="compare budgets with this available Git revision")
    args = parser.parse_args()
    current = measure()
    path = ROOT / BASELINE
    if args.record:
        path.write_text(json.dumps({"_version": DETECTOR_VERSION, **current}, indent=2) + "\n", encoding="utf-8")
    budget = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(current, indent=2))
    base = args.base if args.base.strip("0") else "HEAD^"
    old_entry = git("ls-tree", base, "--", BASELINE.as_posix())
    previous = json.loads(git("show", f"{base}:{BASELINE.as_posix()}")) if old_entry else budget
    previous_version = previous.get("_version", 1)
    errors = []
    if budget.get("_version", 1) != DETECTOR_VERSION or not DETECTOR_VERSION - 1 <= previous_version <= DETECTOR_VERSION:
        errors.append(f"invalid budget version: previous {previous_version}, expected {DETECTOR_VERSION}")
    for area in AREAS:
        for metric, actual in current[area].items():
            cap = budget[area][metric]
            if previous_version == DETECTOR_VERSION and cap > previous[area][metric]:
                errors.append(f"{area} {metric}: budget rose from {previous[area][metric]} to {cap}")
            if actual != cap:
                instruction = "lower the recorded budget" if actual < cap else "remove the added occurrences"
                errors.append(f"{area} {metric}: found {actual}, budget {cap}; {instruction}")
    if errors:
        print("\n".join(errors))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
