"""Which open tasks, or which decisions, a new one is like.

An agent that offers next tasks after #done, or logs a decision, should
know whether the board already holds the same thing. Reading the board
costs it tens of thousands of tokens (156 open tasks on the operator's
largest project), so the server compares instead and answers a few ids.

The comparison is word overlap weighted by rarity (BM25), over one
project's open tasks:

- **words** — lower case, ``ё`` as ``е``; ids (``tk_8a88c687``,
  ``cc-ca77654e``) and commit hashes are taken out first; then runs of
  letters, so a number never counts; stop words in English and Russian
  dropped; a Russian word loses its ending, then each word is cut to its
  first ``PREFIX`` letters, so the forms of a word meet
  (``папка``/``папку``/``папками``, ``deploy``/``deployed``).
  ``searchlib._words`` is not used: its pattern is Latin letters only and
  keeps ``snake_case`` whole; its stop list is.
- **a task's text** — its title and the first ``LINE_WORDS`` words of the
  first line of its description. The whole line added noise: on the
  operator's board many first lines are the operator's raw message.
- **the score** — BM25 divided by the summed rarity of the proposal's
  words: how much of the proposal's weight the task covers. The same text
  scores near 1 (above it for a task shorter than the board's average,
  below for a longer one) whatever the size of the board, so one threshold
  holds for a board of 3 tasks and of 300.

Pure Python, not SQLite FTS5: the corpus is one project's open tasks, a
few milliseconds of work, and it needs no question about which SQLite a
Python build on Windows or macOS carries (FTS5's tokenizers would not cut
Russian words either).

Measured on the operator's data on 2026-11-11 (docs/next-tasks.md; the
labelled set is tests/fixtures/similar_tasks.json): at 0.40, 28 of 28
re-worded tasks in the same language found, 6 of 9 real pairs filed twice,
2 of 25 unrelated proposals with a hit (both related, not the same).
Another language does not meet: a Russian proposal never finds an English
task.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

from .db import ViewStore
from .docs_md import resolve_under
from .entities import is_done
from .searchlib import STOP as _SEARCH_STOP
from .turns import description_of, parse_task_doc

PREFIX = 5
LINE_WORDS = 12
THRESHOLD = 0.40
TASKS_MAX = 3
DECISIONS_MAX = 1
K1 = 1.2
PRIOR_DOCS = 20
B = 0.75

# Function words searchlib's list (built for the search page's word cloud)
# leaves in, and the Russian ones: the operator writes in both.
_MORE_EN = """
a an is be been being am do does did to of in on at by as or if so it i we me my our us he she his her
him would could may might must shall into onto per via vs etc eg ie let lets s t re ll ve d m isn aren wasn weren
doesn didn won wouldn cannot can't
"""
_RU = """
и в во не что он на я с со как а то все всё она так его но да ты к у же вы за бы по только ее её мне было вот от
меня еще ещё нет о об из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам
ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз
тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее неё
сейчас были куда зачем всех никогда можно при наконец два другой хоть после над больше тот через эти нас про всего
них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда
конечно всю между это эта ок окей нужно нужен нужна пусть который которая которые которое также
"""
STOP = frozenset(_SEARCH_STOP) | frozenset(_MORE_EN.split()) | frozenset(_RU.split())

_ID_RE = re.compile(r"\b[a-z]{2}[_-][0-9a-f]{6,}\b")
_HASH_RE = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
_LETTERS_RE = re.compile(r"[^\W\d_]+")


# Russian endings, longest first: a short word changes in its last letters
# (папка, папку), which a cut to five letters alone leaves apart.
_RU_ENDINGS = tuple(sorted("""
ами ями ого его ому ему ыми ими ых их ах ях ам ям ов ев ей ой ий ый ая яя ое ее ую юю ом ем
ы и а я у ю о е ь й""".split(), key=len, reverse=True))
_CYRILLIC_RE = re.compile(r"[а-я]")


def _stem(w: str) -> str:
    if _CYRILLIC_RE.match(w):
        for end in _RU_ENDINGS:
            if w.endswith(end) and len(w) - len(end) >= 3:
                w = w[:-len(end)]
                break
    return w[:PREFIX]


def words(text: str) -> list[str]:
    """The words of a text as the comparison sees them, in order."""
    low = str(text or "").lower().replace("ё", "е")
    low = _HASH_RE.sub(" ", _ID_RE.sub(" ", low))
    return [_stem(w) for w in _LETTERS_RE.findall(low) if len(w) >= 2 and w not in STOP]


def _first_line(text: str) -> str:
    line = next((ln.strip() for ln in str(text or "").splitlines() if ln.strip()), "")
    return " ".join(line.split()[:LINE_WORDS])


def rank(query: str, docs: Iterable[tuple[str, str]], *, limit: int = TASKS_MAX,
         threshold: float = THRESHOLD) -> list[tuple[str, float]]:
    """``(id, score)`` of the documents most like ``query``, best first: at
    most ``limit``, each at least ``threshold``. Ties keep the documents' order."""
    corpus = [(did, words(text)) for did, text in docs]
    q = list(dict.fromkeys(words(query)))
    if not corpus or not q:
        return []
    n = len(corpus)
    avg = sum(len(ws) for _, ws in corpus) / n or 1.0
    df: Counter[str] = Counter()
    for _, ws in corpus:
        df.update(set(ws))

    def idf(w: str) -> float:
        # PRIOR_DOCS more documents that hold none of the words: on a board
        # of two tasks every shared word was "common" and a copy scored 0.24.
        return math.log(1 + (n + PRIOR_DOCS - df[w] + 0.5) / (df[w] + 0.5))

    weight = sum(idf(w) for w in q)
    scored: list[tuple[float, int, str]] = []
    for i, (did, ws) in enumerate(corpus):
        tf = Counter(ws)
        s = 0.0
        for w in q:
            f = tf.get(w, 0)
            if f:
                s += idf(w) * f * (K1 + 1) / (f + K1 * (1 - B + B * len(ws) / avg))
        # Rounded before the comparison: the score shown is the one judged.
        score = round(s / weight, 2) if weight else 0.0
        if score >= threshold:
            scored.append((score, i, did))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(did, score) for score, _, did in scored[:limit]]


def _open(row: dict[str, Any]) -> bool:
    return not is_done(row.get("status")) and not str(row.get("archived_at") or "").strip()


def open_tasks(store: ViewStore, project: str) -> list[dict[str, Any]]:
    """The project's open tasks: not done, not archived, this project only."""
    if not str(project or "").strip():
        return []
    rows = store.query(
        "SELECT id, title, status, archived_at, md_ref FROM tasks_mutual WHERE project = ?", (project,))
    return [r for r in rows if _open(r)]


def _task_text(store: ViewStore, row: dict[str, Any]) -> str:
    title = str(row.get("title") or "")
    path = resolve_under(store.data_root, str(row.get("md_ref") or "")) if row.get("md_ref") else None
    if path is None or not path.is_file():
        return title
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return title     # compared by its title alone; nothing is written from this read
    return f"{title} {_first_line(description_of(parse_task_doc(text)))}".strip()


def similar_tasks(store: ViewStore, project: str, title: str, line: str = "",
                  tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Up to three open tasks of ``project`` like the proposal, best first:
    ``{id, title, status, score}``. ``tasks`` reuses one read of the board
    for several proposals."""
    rows = open_tasks(store, project) if tasks is None else tasks
    by_id = {str(r["id"]): r for r in rows}
    texts = [(str(r["id"]), str(r.get("_text") or _task_text(store, r))) for r in rows]
    return [{"id": tid, "title": str(by_id[tid].get("title") or ""),
             "status": str(by_id[tid].get("status") or ""), "score": score}
            for tid, score in rank(f"{title} {line}", texts)]


def board_for(store: ViewStore, project: str) -> list[dict[str, Any]]:
    """The open tasks with their compared text read once."""
    rows = open_tasks(store, project)
    return [{**r, "_text": _task_text(store, r)} for r in rows]


def similar_decisions(store: ViewStore, project: str, text: str, exclude: str = "") -> list[dict[str, Any]]:
    """The decision of ``project`` most like ``text`` (at most one), not ``exclude``:
    ``{id, decision, created, score}``."""
    if not str(project or "").strip():
        return []
    rows = [r for r in store.query(
        "SELECT id, decision_text, created_date FROM decisions_mutual WHERE project = ?",
        (project,)) if str(r.get("id") or "") != exclude]
    by_id = {str(r["id"]): r for r in rows}
    return [{"id": did, "decision": str(by_id[did].get("decision_text") or ""),
             "created": str(by_id[did].get("created_date") or ""), "score": score}
            for did, score in rank(text, [(str(r["id"]), str(r.get("decision_text") or "")) for r in rows],
                                   limit=DECISIONS_MAX)]
