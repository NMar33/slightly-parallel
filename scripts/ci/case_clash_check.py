"""Fail when two tracked paths are one path on a case-insensitive disk.

macOS and Windows do not tell `Health.tsx` from `health.tsx`, and an import
names a module without its extension, so `./Health` and `./health` are one
file there when `Health.tsx` and `health.ts` sit side by side (tk_a9306fb1:
the type check failed on macOS and Windows only). Linux keeps them apart, so
nothing else notices. This lists every group of tracked paths that differ
only by case:

- whole paths (files and the folders above them);
- modules: names in one folder that are equal once the case and a code
  extension (.ts .tsx .js .py …) are dropped, unless they are spelled the
  same (`safety.test.ts` next to `safety.test.tsx` is fine). A folder counts
  as a module when it holds an index file or an __init__.py (`./health`
  then names it); a folder without one is only ever a step in a longer path,
  which a case-insensitive disk still finds.

    python scripts/ci/case_clash_check.py          # the repository it runs in
    python scripts/ci/case_clash_check.py a b ...  # these paths instead
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

CODE_EXTENSIONS = (".d.ts", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".py")


def _stem(name: str) -> str:
    lower = name.lower()
    for ext in CODE_EXTENSIONS:
        if lower.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)]
    return name


def clashes(paths: list[str]) -> list[list[str]]:
    """Groups of paths that are one on a case-insensitive disk, sorted."""
    entries: set[str] = set()
    for path in paths:
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            entries.add("/".join(parts[:i]))

    files = {p.strip("/") for p in paths}
    packages = set()
    for f in files:
        folder, _, name = f.rpartition("/")
        if name != _stem(name) and _stem(name) in ("index", "__init__"):
            packages.add(folder)

    by_path: dict[str, set[str]] = defaultdict(set)
    by_module: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        by_path[entry.lower()].add(entry)
        if entry not in files and entry not in packages:
            continue
        folder, _, name = entry.rpartition("/")
        stem = _stem(name)
        by_module[(folder + "/" + stem).lower()].add(entry)

    groups: set[tuple[str, ...]] = set()
    for same in by_path.values():
        if len(same) > 1:
            groups.add(tuple(sorted(same)))
    for same in by_module.values():
        spellings = {e.rpartition("/")[0] + "/" + _stem(e.rpartition("/")[2]) for e in same}
        if len(spellings) > 1:
            groups.add(tuple(sorted(same)))
    return [list(g) for g in sorted(groups)]


def tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def main(argv: list[str]) -> int:
    paths = argv or tracked(Path(__file__).resolve().parents[2])
    found = clashes(paths)
    if not found:
        print(f"case_clash_check: {len(paths)} paths, none differ only by case")
        return 0
    print("These paths are one path on macOS and Windows (they differ only by case); rename one of each group:")
    for group in found:
        print("  " + "  |  ".join(group))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
