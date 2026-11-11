"""Which open tasks a proposal is like (similarlib.py): the words, the
score, the threshold, and the labelled set measured on the operator's board."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend import similarlib
from backend.similarlib import THRESHOLD, rank, words

FIXTURE = Path(__file__).parent / "fixtures" / "similar_tasks.json"


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("задачи", "задачу"), ("задача", "задачами"), ("папками", "папка"), ("проектов", "проекты"),
    ("deploy", "deployed"), ("deploying", "deploys"), ("checked", "checking"), ("Windows", "windows"),
    ("ещё", "еще"), ("всё работает", "все работает"),
])
def test_forms_of_a_word_meet(a, b) -> None:
    assert words(a) == words(b)


def test_words_are_cut_to_the_prefix() -> None:
    assert words("international") == ["inter"] and words("переименование") == ["переи"]
    assert words("папка папку папками") == ["папк"] * 3
    assert similarlib.PREFIX == 5


@pytest.mark.parametrize("text", [
    "the and is of to in on at it a an be", "и в на что это как не для по", "a 1 2 3 2026 10%",
    "tk_8a88c687 cc-ca77654e 2c53ecd3 84920350", "", "   ",
])
def test_stop_words_ids_hashes_and_numbers_are_dropped(text) -> None:
    assert words(text) == []


def test_ids_inside_a_sentence_do_not_count() -> None:
    assert words("Close tk_8a88c687 after commit 2c53ecd3 on day 14") == ["close", "commi", "day"]


def test_letters_only_so_a_version_is_its_word() -> None:
    # fts5 → fts; snake_case splits into its words (searchlib kept it whole).
    assert words("fts5 task_done") == ["fts", "task", "done"]


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------


BOARD = [
    ("tk_a", "Kanban board crashes on unticking Unclassified"),
    ("tk_b", "Kanban board: drag a card between lanes"),
    ("tk_c", "Kanban board colours"),
    ("tk_d", "Timer durations go negative in the autumn DST hour"),
    # "kanban" and "board" are on most of a board of 34: common words.
    *[(f"tk_k{i}", f"Kanban board {w}") for i, w in enumerate(
        "fonts icons spacing filters search sorting sharing export import printing shortcuts tooltips "
        "badges avatars counters headers footers columns widths heights titles menus dialogs toasts "
        "loading paging scrolling zoom themes help".split())],
]


def test_the_same_text_scores_about_one() -> None:
    got = rank("Timer durations go negative in the autumn DST hour", BOARD)
    assert got[0][0] == "tk_d" and 0.6 <= got[0][1] <= 1.3   # longer than the average task: under 1


def test_a_rare_word_outweighs_a_common_one() -> None:
    # "kanban" and "board" are on 33 tasks, "unticking" on one.
    got = dict(rank("Kanban board unticking", BOARD, threshold=0.0))
    assert got["tk_a"] > 2 * max(got.get("tk_b", 0), got.get("tk_c", 0))


def test_common_words_alone_do_not_reach_the_threshold() -> None:
    assert rank("A new kanban board", BOARD) == []


def test_threshold_edges() -> None:
    score = dict(rank("negative timer", BOARD, threshold=0.0))["tk_d"]
    assert [x for x, _ in rank("negative timer", BOARD, threshold=score)] == ["tk_d"]
    assert rank("negative timer", BOARD, threshold=score + 0.01) == []
    assert THRESHOLD == 0.40


def test_at_most_three_best_first() -> None:
    board = [(f"tk_{i}", "deploy the site to staging") for i in range(6)]
    got = rank("deploy the site to staging", board)
    assert len(got) == 3 and [x for x, _ in got] == ["tk_0", "tk_1", "tk_2"]


def test_an_empty_board_and_an_empty_query() -> None:
    assert rank("anything at all", []) == []
    assert rank("the and of", BOARD) == []
    assert rank("", BOARD) == []


def test_a_board_of_one_task() -> None:
    assert rank("Timer goes negative at the DST hour", [BOARD[3]])[0][0] == "tk_d"


def test_on_a_small_board_a_copy_still_scores_high() -> None:
    """With two tasks every shared word looked common: a near copy scored
    0.24 until the rarity counted PRIOR_DOCS more documents."""
    board = [("dc_1", "The prompts page is a sortable table, one row per prompt"), ("dc_2", "Backups run nightly")]
    assert rank("The prompts page is a table whose row opens the whole prompt", board)[0][0] == "dc_1"


def test_russian_word_forms_find_the_task() -> None:
    board = [("tk_r", "Разобраться с папками проекта в integrations.csv"), ("tk_x", "Сайт подарков")]
    assert rank("Проверить папку проектов в integrations", board)[0][0] == "tk_r"


def test_another_language_does_not_meet() -> None:
    """The known limit: no translation. A Russian proposal of an English task is not found."""
    assert rank("Таймер уходит в минус при переводе часов", [BOARD[3]]) == []


def test_needs_no_sqlite_so_every_python_build_runs_it() -> None:
    """FTS5 is not in every Python's SQLite (Windows and macOS builds differ):
    the module imports neither sqlite3 nor duckdb itself."""
    tree = ast.parse(Path(similarlib.__file__).read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {str(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level}
    assert not imported & {"sqlite3", "duckdb", "apsw"}


# ---------------------------------------------------------------------------
# The labelled set from the operator's board (titles only)
# ---------------------------------------------------------------------------


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _board() -> list[tuple[str, str]]:
    return [(b["id"], b["title"]) for b in _fixture()["board"]]


def test_reworded_tasks_are_found() -> None:
    """28 of 30 when measured (2026-11-11); the two misses are Russian
    re-wordings of English tasks."""
    fx, board = _fixture(), _board()
    found = [p for p in fx["same"] if p["same_as"] in [i for i, _ in rank(f"{p['title']} {p['line']}", board)]]
    same_language = [p for p in fx["same"] if not (_cyrillic(p["title"]) and not _cyrillic(_title(board, p["same_as"])))]
    assert len(found) >= 27, [p["title"] for p in fx["same"] if p not in found]
    assert all(p in found for p in same_language[:25]), "an English re-wording was missed"


def test_unrelated_proposals_find_little() -> None:
    fx, board = _fixture(), _board()
    hits = [p["title"] for p in fx["different"] if rank(f"{p['title']} {p['line']}", board)]
    assert len(hits) <= 2, hits


def test_wrong_hits_are_few() -> None:
    fx, board = _fixture(), _board()
    wrong = sum(1 for p in fx["same"] for i, _ in rank(f"{p['title']} {p['line']}", board) if i != p["same_as"])
    wrong += sum(len(rank(f"{p['title']} {p['line']}", board)) for p in fx["different"])
    assert wrong <= 3


def test_real_pairs_filed_twice() -> None:
    """Of the pairs one project can find (same project, same language): at
    least 5 (6 when measured). A pair in another project never matches."""
    fx, board = _fixture(), _board()
    reachable = found = 0
    for p in fx["pairs"]:
        b = [x for x in board if x[0] != p["from"]]
        if p["same_project"] and not p["on_board"]:
            b.append((p["same_as"], p["title"]))
        hit = p["same_as"] in [i for i, _ in rank(p["proposal"], b)]
        if not p["same_project"]:
            assert not hit
            continue
        if p["language"] == "same":
            reachable += 1
            found += hit
    assert reachable == 9 and found >= 5


def test_the_fixture_holds_titles_only() -> None:
    fx = _fixture()
    assert set(fx) == {"note", "board", "same", "pairs", "different"}
    assert all(set(b) == {"id", "title"} for b in fx["board"])
    assert len(fx["board"]) >= 150 and len(fx["same"]) == 30 and len(fx["different"]) == 25


def _cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


def _title(board: list[tuple[str, str]], tid: str) -> str:
    return next(t for i, t in board if i == tid)
