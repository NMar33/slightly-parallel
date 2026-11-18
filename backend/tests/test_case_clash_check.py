"""scripts/ci/case_clash_check.py: paths that are one path on macOS and Windows."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("case_clash_check", ROOT / "scripts" / "ci" / "case_clash_check.py")
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def test_a_component_beside_its_model_of_the_same_name_clashes() -> None:
    # tk_a9306fb1: `./Health` and `./health` were one file on macOS and Windows.
    assert check.clashes(["a/health/Health.tsx", "a/health/health.ts", "a/health/index.ts"]) == [
        ["a/health/Health.tsx", "a/health/health.ts"]
    ]


def test_whole_paths_and_folders_that_differ_only_by_case_clash() -> None:
    assert check.clashes(["README.md", "readme.md"]) == [["README.md", "readme.md"]]
    assert check.clashes(["src/Foo/a.txt", "src/foo/b.txt"]) == [["src/Foo", "src/foo"]]


def test_a_folder_with_an_index_is_a_module() -> None:
    assert check.clashes(["src/DayBook.tsx", "src/daybook/index.ts"]) == [["src/DayBook.tsx", "src/daybook"]]
    assert check.clashes(["pkg/Util.py", "pkg/util/__init__.py"]) == [["pkg/Util.py", "pkg/util"]]


def test_same_spelling_or_no_index_is_fine() -> None:
    assert check.clashes(["a/safety.test.ts", "a/safety.test.tsx"]) == []
    assert check.clashes(["src/DayBook.tsx", "src/daybook/DayEntry.tsx"]) == []
    assert check.clashes(["a/healthModel.ts", "a/Health.tsx", "a/Health.png"]) == []


def test_this_repository_has_no_clash() -> None:
    assert check.clashes(check.tracked(ROOT)) == []
