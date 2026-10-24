"""Search over everything Slightly Parallel has, not three kinds of it.

``/api/search`` answered from three hand-written blocks — tasks, decisions
and agents — each matching a few CSV columns. A word read on a scan, a
standup, a problem, a skill or in a chat returned nothing, which is why
search did not work: what you are looking for is usually in the text of an
entry, and the text lives in a Markdown detail file the old search never
opened.

One index instead. Every entity in the registry, every scan, every agent,
and every captured **turn** of every chat — not the transcript as one blob,
because "who said it, and when" is most of what a person wants back. Each
is a row of `kind, id, title, project, date` and the text to match: the
row's own words plus its detail document. It is
small — on a working install a few megabytes — so it is built in memory and
kept until the store changes (``ViewStore.view_mtime``, which already moves
when a CSV, a detail folder or a snapshot changes; chats get their own
stamp, being outside it).

Matching is plain: the query, folded to lower case, as a substring. A hit
in the title outranks a hit in the body, and newer outranks older. The
snippet is the line the match sits on, trimmed around it, so the page can
show why a row came back.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .date_utils import format_yymm_dd
from .db import ViewStore
from .docs_md import read_detail
from .entities import ENTITIES
from . import repomap
from .viewrows import rows_or_empty

log = logging.getLogger("sp.search")

SNIPPET = 160
BODY_MAX = 20_000          # per entry: a long chat is matched, not stored whole
MAX_PER_KIND = 5_000
MIN_AGE = 15.0                  # seconds before a changed store is read again

# Columns worth matching on, beyond the headline: whatever a person might
# remember typing. A column an entity does not have is skipped.
TEXT_COLUMNS = (
    "title", "l1", "name", "description", "summary", "decision_text", "rationale",
    "note", "notes", "tags", "status", "kind", "type", "path", "surface", "body",
    "agent_id", "assignee", "lane", "scope", "for_date",
)


@dataclass
class Row:
    kind: str
    id: str
    title: str
    project: str
    date: str
    text: str                       # already lower case
    raw: str = ""                   # the same text, as written, for snippets
    meta: dict[str, Any] = field(default_factory=dict)   # who, when, where inside
    # A turn's title is its chat's name, shared by every turn of that chat: it
    # is context, not content. Matching on it made every turn of a chat named
    # "evidence-and-language" a title hit whose snippet was that name.
    by_title: bool = True


@dataclass
class Hit:
    kind: str
    id: str
    title: str
    project: str
    date: str
    snippet: str
    where: str                      # "title" or "text"
    count: int = 1                  # times the word occurs in this row
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "id": self.id, "title": self.title,
            "project": self.project, "date": self.date,
            "snippet": self.snippet, "where": self.where, "count": self.count,
            **self.meta,
        }


@dataclass
class Index:
    rows: list[Row] = field(default_factory=list)
    built_at: float = 0.0
    stamp: tuple[float, float] = (0.0, 0.0)
    # Counted once with the index, for the page that has no query yet.
    shape: dict[str, Any] = field(default_factory=dict)
    # How many rows each word appears in, so a word beside another can be
    # judged against how common it is everywhere.
    word_rows: dict[str, int] = field(default_factory=dict)


_cache: dict[str, Index] = {}
_build_lock = threading.Lock()


def _day(iso: str) -> str:
    """'2026-08-20T21:04:27' → '2608-20', the shape every other row uses."""
    try:
        return format_yymm_dd(datetime.fromisoformat(iso.replace("Z", "+00:00")).date())
    except (ValueError, TypeError):
        return ""


def _clip(text: str) -> str:
    return text[:BODY_MAX]


def _detail_text(store: ViewStore, md_ref: str) -> str:
    if not md_ref:
        return ""
    l2, l3, l4 = read_detail(store.data_root, md_ref)
    return " ".join([l2, " ".join(l3 or []), l4]).strip()


def _row_words(r: dict[str, Any], columns: Iterable[str]) -> str:
    return " ".join(str(r.get(c) or "") for c in columns if r.get(c))


def _chats_stamp(root: Path) -> float:
    latest = 0.0
    chats = root / "projects"
    if not chats.is_dir():
        return latest
    for chat in chats.glob("*/chats/*/chat.md"):
        try:
            latest = max(latest, chat.stat().st_mtime)
        except OSError:
            pass
    return latest


def build(store: ViewStore) -> Index:
    """Every searchable thing, once. Cheap enough to hold in memory."""
    rows: list[Row] = []

    def add(kind: str, rid: str, title: str, project: str, date: str, *parts: str,
            meta: dict[str, Any] | None = None, by_title: bool = True) -> None:
        if not rid:
            return
        raw = " ".join(p for p in parts if p).strip()
        # The id is matched too: an id pasted from a chat, a commit message or
        # another page is the most exact query a person can type.
        words = (rid + " " + title + " " + raw) if by_title else (rid + " " + raw)
        rows.append(Row(kind, rid, title, project, date, words.lower(), raw, meta or {}, by_title))

    for name, ent in ENTITIES.items():
        # A view may be absent (no file yet). Any other failure is logged
        # and costs this kind only: the rest stays searchable.
        try:
            got = rows_or_empty(store, f"SELECT * FROM {ent.view}")
        except Exception:
            log.exception("search index: %s skipped", ent.view)
            continue
        columns = [c for c in TEXT_COLUMNS if c in ent.columns or c in ent.view_extras]
        for r in got[:MAX_PER_KIND]:
            title = str(r.get(ent.headline_field) or r.get("title") or r.get("name") or "")
            add(name, str(r.get("id") or ""), title, str(r.get("project") or ""),
                str(r.get("created_date") or ""),
                _row_words(r, columns), _clip(_detail_text(store, str(r.get("md_ref") or ""))))

    for r in rows_or_empty(store, "SELECT * FROM scans"):
        add("scan", str(r.get("id") or ""), str(r.get("l1") or ""), str(r.get("project") or ""),
            str(r.get("created_date") or ""), str(r.get("scope") or ""),
            _clip(_detail_text(store, str(r.get("md_ref") or ""))))

    for a in store.agents():
        # Dates are YYMM-DD everywhere; an agent's stamp is an ISO instant, so
        # it is converted, not sliced — a month in another shape sorts last.
        add("agent", str(a.get("agent_id") or ""), str(a.get("agent_name") or a.get("agent_id") or ""),
            str(a.get("project") or ""), _day(str(a.get("last_active") or "")),
            str(a.get("l1_headline") or ""), " ".join(str(t) for t in (a.get("tags") or [])),
            str(a.get("chat_title") or ""))

    # The map of each program: one row per part, so a module, a path or a
    # service is found by its own name. The map lives in versions outside the
    # CSV ledgers, so nothing else would reach it.
    for project in {str(p.code) for p in store.projects}:
        try:
            current = repomap.current(store, project)
        except Exception:  # noqa: BLE001 — one damaged map must not end the search
            log.exception("search: the map of %s could not be read", project)
            current = None
        if not current:
            continue
        for r in current["map"].get("rows") or []:
            add("part", f"{project}:{r.get('kind')}:{r.get('name')}", str(r.get("name") or ""),
                project, str(current.get("at") or "")[:10].replace("-", "")[2:6] or "",
                str(r.get("kind") or ""), str(r.get("what") or ""), str(r.get("where") or ""),
                str(r.get("note") or ""),
                meta={"map_kind": str(r.get("kind") or ""), "where_path": str(r.get("where") or "")})

    # Every captured turn, one row: a word said in a chat is found with the
    # person who said it, the minute, and the session it belongs to. The
    # turns are already parsed into the sessions table, so this costs nothing.
    names = {str(a.get("agent_id") or ""): a for a in store.agents()}
    for ses in store.query("SELECT * FROM sessions"):
        try:
            turns = json.loads(str(ses.get("turns_json") or "[]"))
        except ValueError:
            continue
        agent = names.get(str(ses.get("agent_id") or ""), {})
        chat = str(agent.get("chat_title") or agent.get("agent_name") or ses.get("agent_id") or "")
        for t in turns:
            n = int(t.get("n") or 0)
            for role in ("user", "agent"):
                said = str(t.get(role) or "").strip()
                if not said:
                    continue
                add("turn", f"{ses.get('agent_id')}#{n}.{role}", chat,
                    str(ses.get("project") or ""), str(ses.get("created_date") or ""),
                    _clip(said),
                    meta={"role": role, "turn": n, "at": str(t.get("at") or ""),
                          "session_id": str(ses.get("id") or ""),
                          "agent_id": str(ses.get("agent_id") or "")},
                    by_title=False)

    in_rows: Counter[str] = Counter()
    for r in rows:
        in_rows.update(set(_words(r.raw)))
    return Index(rows=rows, built_at=time.time(),
                 stamp=(store.view_mtime, _chats_stamp(store.data_root)),
                 shape=_shape(rows), word_rows=dict(in_rows))


def index(store: ViewStore) -> Index:
    """The index, rebuilt when the store or a chat has changed — but not more
    often than ``MIN_AGE``.

    The chat being typed into right now moves its file on every turn, so a
    strict stamp rebuilt the whole index on every request while someone was
    working: half a second each, for a page that answers in milliseconds. The
    floor means a word said in the last few seconds can be missed by that
    much, which is the right trade for a record of what already happened.
    """
    key = str(store.data_root)
    stamp = (store.view_mtime, _chats_stamp(store.data_root))
    hit = _cache.get(key)
    if hit is not None and (hit.stamp == stamp or time.time() - hit.built_at < MIN_AGE):
        return hit
    # One build at a time: the page asks for the list and the overview
    # together, and each used to read every document and turn for itself.
    with _build_lock:
        hit = _cache.get(key)
        if hit is not None and (hit.stamp == stamp or time.time() - hit.built_at < MIN_AGE):
            return hit
        hit = build(store)
        _cache[key] = hit
        return hit


def forget() -> None:
    _cache.clear()


def _snippet(raw: str, needle: str) -> str:
    where = raw.lower().find(needle)
    if where < 0:
        return raw[:SNIPPET].strip()
    start = max(0, where - SNIPPET // 3)
    piece = raw[start:start + SNIPPET].strip()
    return ("… " if start else "") + " ".join(piece.split()) + ("…" if start + SNIPPET < len(raw) else "")


def search(store: ViewStore, query: str, kinds: set[str] | None = None, limit: int = 0) -> list[Hit]:
    """Every hit, title matches first and newest first inside that.

    ``limit`` 0 means all of them: the caller counts the kinds over the whole
    set and shows as many as its page can hold.
    """
    needle = (query or "").strip().lower()
    if not needle:
        return []
    found: list[tuple[int, str, Hit]] = []
    for row in index(store).rows:
        if kinds and row.kind not in kinds:
            continue
        in_title = row.by_title and needle in row.title.lower()
        if not in_title and needle not in row.text:
            continue
        found.append((
            0 if in_title else 1, row.date,
            Hit(row.kind, row.id, row.title, row.project, row.date,
                _snippet(row.raw if not in_title else row.title, needle),
                "title" if in_title else "text",
                row.text.count(needle), row.meta),
        ))
    found.sort(key=lambda f: (f[0], _reverse(f[1])))
    hits = [h for _, _, h in found]
    return hits[:limit] if limit else hits


def _reverse(date: str) -> str:
    """Sort newest first without a second key: invert each digit."""
    return "".join(chr(ord("9") - (ord(c) - ord("0"))) if c.isdigit() else c for c in date)


def counts(hits: list[Hit]) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in hits:
        out[h.kind] = out.get(h.kind, 0) + 1
    return out


# ---------------------------------------------------------------------------
# What is in there, before anyone types
# ---------------------------------------------------------------------------
#
# A search page with no query is a blank page. Everything a person might want
# to see there — the words that come up most, how much was said on each day,
# how long a turn runs, which chats carry the weight — is already in the
# index, so it is counted once when the index is built and handed over whole.
# Counting the words is the only heavy part (about 1.3 million of them on a
# working install), and it happens on the same rebuild the index already pays
# for. For one word, the same shape is counted over the rows that match it —
# a few hundred at most — which is fast enough to do on the request.

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{2,}|[a-z]+_[a-z0-9_]+")
TOP_WORDS = 240
LENGTH_BUCKETS = (0, 10, 25, 50, 100, 200, 400, 800, 1600)

# Words that say nothing about a project. English only: the product's own
# output is English, and a word a person types is theirs to judge.
STOP = frozenset("""
the and that for with this from have has had not are was were you your they them their there here
what when where which who whom why how all any both each few more most other some such only own same
than too very can will just don should now its it's about into over under again further then once
out off above below between through during before after because while against among upon
one two three four five six seven eight nine ten first second next last also like get got make made
say said says see saw seen use used using want wants need needs know knows think thought
but not nor yes no okay ok well still yet even ever never always sure thing things way ways
""".split())


def _words(text: str) -> list[str]:
    return [w for w in (m.group(0).lower() for m in WORD_RE.finditer(text))
            if w not in STOP and not w.isdigit()]


def _bucket(n: int) -> str:
    for low, high in zip(LENGTH_BUCKETS, LENGTH_BUCKETS[1:]):
        if n < high:
            return f"{low}–{high}"
    return f"{LENGTH_BUCKETS[-1]}+"


def _shape(rows: list[Row], words: Counter[str] | None = None) -> dict[str, Any]:
    """The picture of a set of rows: kinds, days, turn lengths, who, words."""
    kinds: Counter[str] = Counter()
    days: Counter[str] = Counter()
    lengths: Counter[str] = Counter()
    chats: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    projects: Counter[str] = Counter()
    said_words = 0
    if words is None:
        words = Counter()
        count_words = True
    else:
        count_words = False
    for r in rows:
        kinds[r.kind] += 1
        if r.date:
            days[r.date] += 1
        projects[r.project or "(none)"] += 1
        if r.kind == "turn":
            n = len(r.raw.split())
            said_words += n
            lengths[_bucket(n)] += 1
            chats[r.title or str(r.meta.get("agent_id") or "")] += 1
            roles[str(r.meta.get("role") or "")] += 1
        if count_words:
            words.update(_words(r.raw))
    return {
        "rows": len(rows),
        "kinds": kinds.most_common(),
        "days": sorted(days.items()),
        "projects": projects.most_common(),
        "turn_lengths": [{"bucket": _bucket(low), "n": lengths[_bucket(low)]}
                         for low in LENGTH_BUCKETS[:-1]] + [{"bucket": f"{LENGTH_BUCKETS[-1]}+",
                                                             "n": lengths[f"{LENGTH_BUCKETS[-1]}+"]}],
        "words_said": said_words,
        "chats": chats.most_common(12),
        "roles": roles.most_common(),
        "words": [{"word": w, "n": n} for w, n in words.most_common(TOP_WORDS)],
    }


def overview(store: ViewStore, query: str = "", kinds: set[str] | None = None) -> dict[str, Any]:
    """What is in the index, as a whole or for one word.

    With no word: the shape of everything, counted when the index was built.
    With a word: the same shape over the rows that match it, and the words
    that keep it company — the ones that occur far more often beside it than
    they do anywhere else.
    """
    idx = index(store)
    if not query.strip():
        return {"query": "", **idx.shape}

    rows = [r for r in idx.rows if (not kinds or r.kind in kinds) and query.strip().lower() in r.text]
    near: Counter[str] = Counter()
    for r in rows:
        near.update(set(_words(r.raw)))
    shape = _shape(rows, near)
    # A word that is everywhere tells you nothing: rank by how much more often
    # it sits beside this word than in the index at large.
    everywhere = idx.word_rows or {}
    total = max(1, len(idx.rows))
    here = max(1, len(rows))
    lift = []
    for w, n in near.items():
        if n < 2 or w == query.strip().lower():
            continue
        base = (everywhere.get(w, 0) or 1) / total
        lift.append({"word": w, "n": n, "lift": round((n / here) / base, 1)})
    # The word breaks a tie: the words come out of a set, whose order
    # changes with every start of the server.
    lift.sort(key=lambda x: (-x["lift"], -x["n"], x["word"]))
    shape["near"] = lift[:60]
    return {"query": query.strip(), **shape}
