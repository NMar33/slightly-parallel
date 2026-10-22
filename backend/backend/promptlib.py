"""The prompt library — what the operator wrote, kept and watched change.

A prompt is not something an agent should be asked to report. The operator
already typed it, and capture already stored it verbatim; asking the agent to
also write it down adds a second, worse copy that can disagree with the first.
So the library harvests: put ``#prompt`` anywhere in a message and that
message joins the library, named by ``#prompt(a name)`` or by its first line.
It works on chat logs captured months ago, because the source is the log.

Three things the library is for, in the order they matter:

1. **Keeping it.** The prompt that worked is a real asset and it currently
   lives in scrollback. Harvesting costs the operator four characters.
2. **Watching it change.** A prompt is rewritten far more often than it is
   written. Every rewrite is a version with a note saying why, so the
   question "what did I change, and did it help?" has an answer with a diff
   attached. Version 1 is always the captured original and is never edited.
3. **Knowing whether it is used.** Reuse is counted by *equality* on a
   normalised fingerprint of the message — a prompt pasted again is
   byte-identical once whitespace is collapsed. Nothing here is fuzzy: a
   library that reports reuse which did not happen is worse than one that
   reports none.

The row lives in ``prompts.csv``; the versions live in one markdown document
per prompt, which is the whole edit history in a file a person can read.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import frontmatter, limits
from .csvio import append_row, rewrite_rows
from .db import ViewStore
from .entities import ENTITIES
from .file_safety import acquire_flock, atomic_write, lock_path
from .sessions import _TASK_ID_RE, fingerprint, prompt_title

# "## Version 2 · 2609-07 16:40 · edited"
VERSION_HEAD_RE = re.compile(
    r"^##\s+Version\s+(\d+)\s+·\s+(\d{4}-\d{2}(?:\s+\d{2}:\d{2})?)"
    r"(?:\s+·\s+([a-z]+))?[ \t]*$",
    re.MULTILINE,
)

HOWS = ("captured", "written", "edited")
STATUSES = ("active", "archived")


@dataclass
class Version:
    """One state of a prompt, and why it stopped being the current one."""

    n: int
    at: str                 # YYMM-DD HH:MM
    how: str                # captured · written · edited
    note: str               # why this rewrite — the evolution record
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n, "at": self.at, "how": self.how,
            "note": self.note, "text": self.text,
            "chars": len(self.text), "words": len(self.text.split()),
            "print": fingerprint(self.text),
        }


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(the block including both fences, the rest) — ``render_doc`` joins
    them back, so the newline after the closing fence may sit on either
    side of the cut."""
    return frontmatter.block(text)


def parse_doc(text: str) -> tuple[str, list[Version]]:
    """(frontmatter, versions) — oldest first. A doc with no headings is v1.

    A prompt document that predates the format, or one a person wrote by
    hand, is read as a single captured version rather than refused. Losing
    the operator's text to a parse error is the one outcome worth ruling out.
    """
    front, body = _split_frontmatter(text or "")
    heads = list(VERSION_HEAD_RE.finditer(body))
    if not heads:
        stripped = body.strip()
        return front, ([Version(1, "", "captured", "", stripped)] if stripped else [])

    versions: list[Version] = []
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        chunk = body[start:end].strip("\n")
        note = ""
        lines = chunk.split("\n")
        # A blockquote immediately under the heading is the note for the
        # rewrite; everything after it is the prompt.
        while lines and lines[0].startswith(">"):
            note = (note + " " + lines.pop(0).lstrip("> ").strip()).strip()
            while lines and not lines[0].strip():
                lines.pop(0)
        versions.append(Version(
            n=int(m.group(1)), at=m.group(2), how=(m.group(3) or "edited"),
            note=note, text="\n".join(lines).strip(),
        ))
    versions.sort(key=lambda v: v.n)
    return front, versions


def render_doc(front: str, versions: list[Version]) -> str:
    out = [front.rstrip("\n"), ""] if front else []
    for v in versions:
        out.append(f"## Version {v.n} · {v.at} · {v.how}")
        if v.note:
            out.append(f"> {v.note}")
        out.append("")
        out.append(v.text)
        out.append("")
    return "\n".join(out).strip() + "\n"


def doc_ref(prompt_id: str) -> str:
    return f"prompt_details/{prompt_id}.md"


def read_doc(root: Path, prompt_id: str) -> tuple[str, list[Version]]:
    path = root / doc_ref(prompt_id)
    try:
        return parse_doc(path.read_text(encoding="utf-8"))
    except OSError:
        return "", []


def write_doc(root: Path, prompt_id: str, front: str, versions: list[Version]) -> None:
    path = root / doc_ref(prompt_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, render_doc(front, versions))


# ---------------------------------------------------------------------------
# Harvesting
# ---------------------------------------------------------------------------


def source_id(project: str, agent_id: str, session_id: str, turn: int) -> str:
    """Identity is the turn it came from, never the text.

    So editing a prompt does not mint a second one, and re-harvesting the
    same chat log forever produces the same row.
    """
    seed = f"{project}|{agent_id}|{session_id}|{turn}"
    prefix = ENTITIES["prompt"].id_prefix
    return prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]


def _stamp(at_ts: str) -> tuple[str, str]:
    """ISO → (YYMM-DD, HH:MM), Slightly Parallel's own date shape."""
    try:
        d = datetime.fromisoformat(at_ts)
    except ValueError:
        return "", ""
    return f"{d.year % 100:02d}{d.month:02d}-{d.day:02d}", d.strftime("%H:%M")


# Adoption rides every list read, and two reads can land in the same
# instant — the page's poll and a second tab. Check-then-append is not
# atomic across them, and the same turn was once adopted twice. One lock,
# and the check reads the file rather than a view that has not rebuilt yet.
_adopt_lock = threading.Lock()


def adopt(store: ViewStore) -> list[str]:
    """Bring every ``#prompt`` in the chat logs into the library.

    Idempotent, and safe to run on every read: a mark whose row already
    exists is skipped, and the id comes from the turn, so nothing is ever
    adopted twice. Returns the ids added.
    """
    with _adopt_lock:
        return _adopt_locked(store)


def _adopt_locked(store: ViewStore) -> list[str]:
    from .csvio import read_rows
    ent = ENTITIES["prompt"]
    marks = store.query(
        "SELECT project, agent_id, session_id, turn, at_ts, title, body "
        "FROM prompt_marks ORDER BY at_ts"
    )
    if not marks:
        return []
    known = {str(r["id"]) for r in store.query("SELECT id FROM prompts_mutual")}
    known |= {str(r.get("id") or "") for r in read_rows(store.data_root / ent.csv)}
    added: list[str] = []
    for m in marks:
        pid = source_id(str(m["project"]), str(m["agent_id"]),
                        str(m["session_id"]), int(m["turn"] or 0))
        if pid in known:
            continue
        date, time = _stamp(str(m["at_ts"]))
        body = str(m["body"] or "").strip()
        if not body:
            continue
        write_doc(store.data_root, pid, f"---\nid: {pid}\n---\n",
                  [Version(1, f"{date} {time}", "captured", "", body)])
        append_row(store.data_root / ent.csv, ent.columns, {
            "id": pid, "created_date": date, "created_time": time,
            "project": str(m["project"]), "agent_id": str(m["agent_id"]),
            "title": str(m["title"] or "")[:limits.MAX_TITLE], "tags": "", "status": "active",
            "source": "captured", "session_id": str(m["session_id"]),
            "source_turn": int(m["turn"] or 0), "versions_n": 1, "marks": "{}",
            "md_ref": doc_ref(pid),
        })
        known.add(pid)
        added.append(pid)
    if added:
        store.rebuild()
    return added


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


def add_version(
    store: ViewStore, prompt_id: str, text: str, note: str, *,
    how: str = "edited", now: datetime | None = None,
) -> list[Version]:
    """Append a rewrite. The captured original is never overwritten.

    A rewrite identical to the current text is not a version — the history
    is meant to answer "what changed", and a no-op entry in it is a lie.
    """
    body = (text or "").strip()
    if not body:
        raise ValueError("a prompt version cannot be empty")
    doc = store.data_root / doc_ref(prompt_id)
    doc.parent.mkdir(parents=True, exist_ok=True)
    # Read, number and write under one lock: two rewrites at the same moment
    # were both version n+1, and one of them was lost.
    with acquire_flock(lock_path(doc)):
        front, versions = read_doc(store.data_root, prompt_id)
        if versions and versions[-1].text.strip() == body:
            return versions
        at = now or datetime.now()
        versions.append(Version(
            n=(versions[-1].n + 1 if versions else 1),
            at=f"{at.year % 100:02d}{at.month:02d}-{at.day:02d} {at:%H:%M}",
            how=how if how in HOWS else "edited",
            note=(note or "").strip()[:400],
            text=body,
        ))
        write_doc(store.data_root, prompt_id, front, versions)
    set_fields(store, prompt_id, {"versions_n": len(versions)})
    return versions


def set_fields(
    store: ViewStore, prompt_id: str, fields: dict[str, Any], marks: dict[str, Any] | None = None,
) -> None:
    """Update one row of prompts.csv in place, under the file's own lock.

    ``marks`` are changes merged into the row's marks as the file holds
    them: merged into a copy read from the view, a mark posted a moment
    earlier was lost."""
    ent = ENTITIES["prompt"]
    values = {k: str(v) for k, v in fields.items()}

    def mutate(rows: list[dict[str, str]]) -> bool:
        touched = False
        for r in rows:
            if r.get("id") != prompt_id:
                continue
            want = dict(values)
            if marks is not None:
                want["marks"] = json.dumps(merge_marks(parse_marks(r.get("marks")), marks))
            if any(r.get(k) != v for k, v in want.items()):
                r.update(want)
                touched = True
        return touched

    if rewrite_rows(store.data_root / ent.csv, ent.columns, mutate):
        store.rebuild()


def write_by_hand(
    store: ViewStore, title: str, text: str, project: str, tags: str,
    now: datetime | None = None, source: str = "written",
) -> str:
    """A prompt typed straight into the library rather than tagged in chat.

    Same row, same document, same versioning — only ``source`` differs, so
    the library never has to explain two kinds of prompt.
    """
    ent = ENTITIES["prompt"]
    at = now or datetime.now()
    date = f"{at.year % 100:02d}{at.month:02d}-{at.day:02d}"
    time = at.strftime("%H:%M")
    body = text.strip()
    head = title.strip() or next(
        (ln.strip() for ln in body.splitlines() if ln.strip()), "untitled prompt"
    )
    seed = f"{source}|{project}|{date}|{time}|{head}"
    pid = ent.id_prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]
    if store.query_one("SELECT id FROM prompts_mutual WHERE id = ?", (pid,)) is not None:
        return pid
    write_doc(store.data_root, pid, f"---\nid: {pid}\n---\n",
              [Version(1, f"{date} {time}", "written", "", body)])
    append_row(store.data_root / ent.csv, ent.columns, {
        "id": pid, "created_date": date, "created_time": time,
        "project": project, "agent_id": "operator", "title": head[:limits.MAX_TITLE],
        "tags": tags.strip()[:limits.MAX_TITLE], "status": "active", "source": source,
        "marks": "{}",
        "session_id": "", "source_turn": 0, "versions_n": 1,
        "archived_at": "", "md_ref": doc_ref(pid),
    })
    store.rebuild()
    return pid


# ---------------------------------------------------------------------------
# What a prompt is worth
# ---------------------------------------------------------------------------


def metrics(store: ViewStore, versions: list[Version]) -> dict[str, Any]:
    """Where this prompt was actually sent, and what came out of it.

    Two counts, because they answer different questions. ``exact`` is the
    number of turns whose text matched a version byte for byte once
    whitespace is collapsed. ``uses`` is the number of turns in the same
    *cluster* — the near-duplicates, the sends where one opening line was
    swapped before pasting.

    Only the second one is true to how a prompt is really re-sent. Over 563
    captured turns, 7 of the 187 substantial ones had an exact twin, while
    the operator's most-repeated prompt went out nine times with a different
    first sentence each time. Counting equality alone would have reported
    that prompt as used once — the page confidently wrong about the single
    thing it exists to measure.
    """
    prints = sorted({fingerprint(v.text) for v in versions if v.text})
    empty = {"uses": 0, "reuses": 0, "exact": 0, "sessions": 0, "turns": 0,
             "minutes": 0, "projects": [], "tasks": [], "last_used": "",
             "first_used": "", "by_version": {}, "clustered": False, "by_day": {}}
    if not prints:
        return empty

    ph = ",".join("?" * len(prints))
    seeds = store.query(
        f"SELECT print, cluster FROM turn_prints WHERE print IN ({ph})",
        tuple(prints),
    )
    if not seeds:
        return empty

    clusters = sorted({str(s["cluster"]) for s in seeds if s["cluster"]})
    if clusters:
        ch = ",".join("?" * len(clusters))
        hits = store.query(
            f"SELECT print, project, session_id, turn, at_ts FROM turn_prints "
            f"WHERE cluster IN ({ch}) ORDER BY at_ts",
            tuple(clusters),
        )
    else:
        hits = store.query(
            f"SELECT print, project, session_id, turn, at_ts FROM turn_prints "
            f"WHERE print IN ({ph}) ORDER BY at_ts",
            tuple(prints),
        )

    exact = sum(1 for h in hits if str(h["print"]) in set(prints))
    by_day: dict[str, int] = {}
    for h in hits:
        d = str(h["at_ts"])[:10]
        if len(d) == 10:
            key = f"{d[2:4]}{d[5:7]}-{d[8:10]}"   # Slightly Parallel's YYMM-DD
            by_day[key] = by_day.get(key, 0) + 1
    by_print: dict[str, int] = {}
    for h in hits:
        by_print[str(h["print"])] = by_print.get(str(h["print"]), 0) + 1
    sessions = sorted({str(h["session_id"]) for h in hits})
    projects = sorted({str(h["project"]) for h in hits if h["project"]})

    sh = ",".join("?" * len(sessions))
    runs = store.query(
        f"SELECT id, turns_n, duration_min, agent_min, helper_min FROM sessions WHERE id IN ({sh})",
        tuple(sessions),
    )
    tasks = store.query(
        f"SELECT DISTINCT task_id FROM task_mentions WHERE session_id IN ({sh})",
        tuple(sessions),
    )
    first = str(hits[0]["at_ts"])
    return {
        "uses": len(hits),
        # Sends after the first. A prompt filed from a message it was sent in
        # starts at one use, and calling that "sent once" invites reading the
        # act of filing as evidence of reuse. This is the number that is not
        # true by construction.
        "reuses": max(0, len(hits) - 1),
        "first_used": first,
        "exact": exact,
        "sessions": len(sessions),
        "turns": sum(int(r["turns_n"] or 0) for r in runs),
        # The agents' working minutes on the runs; the sessions' wall clock beside.
        "minutes": sum(int(r["agent_min"] or 0) for r in runs),
        "session_minutes": sum(int(r["duration_min"] or 0) for r in runs),
        "helper_minutes": sum(int(r["helper_min"] or 0) for r in runs),
        "projects": projects,
        "tasks": sorted(str(t["task_id"]) for t in tasks),
        "last_used": str(hits[-1]["at_ts"]),
        # Which wording was the one sent — the answer to "did the rewrite
        # ever get used, and did anything change when it did".
        "by_version": {
            str(v.n): by_print.get(fingerprint(v.text), 0) for v in versions
        },
        "clustered": len(hits) > exact,
        # Sends per day, Slightly Parallel dates — the rhythm of one prompt, and summed
        # across the library, of prompting itself.
        "by_day": by_day,
    }


# ---------------------------------------------------------------------------
# Marks — the numbers the operator keeps, beside the ones that are derived
# ---------------------------------------------------------------------------

# The derived metrics say what happened; a mark says what the operator
# concluded. "worked: yes", "cost: high", "rating: 4" — the names are theirs
# and are never validated against a list, because the useful ones are the
# ones nobody thought of in advance. Stored as compact JSON in one column so
# adding a mark is not a migration.
MAX_MARKS = 12
MAX_MARK_LEN = 60


def parse_marks(raw: Any) -> dict[str, str]:
    try:
        data = json.loads(str(raw or "") or "{}")
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k)[:MAX_MARK_LEN]: str(v)[:MAX_MARK_LEN] for k, v in data.items()}


def merge_marks(current: dict[str, str], changes: dict[str, Any]) -> dict[str, str]:
    """A null value deletes the mark; anything else sets it."""
    out = dict(current)
    for k, v in changes.items():
        name = str(k).strip()[:MAX_MARK_LEN]
        if not name:
            continue
        if v is None or str(v).strip() == "":
            out.pop(name, None)
        else:
            out[name] = str(v).strip()[:MAX_MARK_LEN]
    return dict(list(out.items())[:MAX_MARKS])


def mark_names(store: ViewStore) -> list[str]:
    """Every mark name in use, commonest first — the library's own vocabulary.

    So the second prompt the operator marks is offered the word they used on
    the first, and the names converge into columns instead of scattering.
    """
    seen: dict[str, int] = {}
    for r in store.query("SELECT marks FROM prompts_mutual"):
        for name in parse_marks(r.get("marks")):
            seen[name] = seen.get(name, 0) + 1
    return [n for n, _ in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))]


# ---------------------------------------------------------------------------
# Where it was sent — the conversations behind the count
# ---------------------------------------------------------------------------


def sends(store: ViewStore, versions: list[Version]) -> list[dict[str, Any]]:
    """Every send of this prompt, newest first, each pointing at its session.

    The count on the card is an assertion; this is the evidence for it. A
    number the operator cannot open is a number they have to take on trust,
    and this feature is asking for a lot of trust already.
    """
    prints = sorted({fingerprint(v.text) for v in versions if v.text})
    if not prints:
        return []
    ph = ",".join("?" * len(prints))
    seeds = store.query(
        f"SELECT cluster FROM turn_prints WHERE print IN ({ph})", tuple(prints)
    )
    clusters = sorted({str(s["cluster"]) for s in seeds if s["cluster"]})
    if clusters:
        ch = ",".join("?" * len(clusters))
        rows = store.query(
            f"SELECT print, project, agent_id, session_id, turn, at_ts, words, head, body "
            f"FROM turn_prints WHERE cluster IN ({ch}) ORDER BY at_ts DESC",
            tuple(clusters),
        )
    else:
        rows = store.query(
            f"SELECT print, project, agent_id, session_id, turn, at_ts, words, head, body "
            f"FROM turn_prints WHERE print IN ({ph}) ORDER BY at_ts DESC",
            tuple(prints),
        )
    exact = set(prints)
    by_print = {fingerprint(v.text): v.n for v in versions if v.text}
    return [{
        "at": str(r["at_ts"]),
        "project": str(r["project"] or ""),
        "agent_id": str(r["agent_id"] or ""),
        "session_id": str(r["session_id"] or ""),
        "turn": int(r["turn"] or 0),
        "words": int(r["words"] or 0),
        "head": str(r["head"] or ""),
        "body": str(r["body"] or ""),
        # Which version this send was, when it was one of them exactly.
        "version": by_print.get(str(r["print"])),
        "exact": str(r["print"]) in exact,
    } for r in rows]


# ---------------------------------------------------------------------------
# What the operator has been sending without ever filing it
# ---------------------------------------------------------------------------

# Below this a repetition is a mood, not a habit. Three sends surfaced a
# recurring complaint ("I see a very bad problem…") beside a real prompt sent
# nine times; four keeps the prompt and drops the grumble.
CANDIDATE_SENDS = 4
CANDIDATE_WORDS = 25


def candidates(store: ViewStore, limit: int = 12) -> list[dict[str, Any]]:
    """Messages sent again and again that are not in the library yet.

    The tag is a door the operator has to remember to walk through *before*
    knowing the message mattered — and a prompt usually earns its place on
    the fourth send, not the first. This is the other door, and it needs
    nothing from anybody: the clustering already knows what has been sent
    repeatedly, so the library can open with "you have sent this nine times
    since 22 August — keep it?" rather than waiting to be fed.
    """
    known = {
        fingerprint(v.text)
        for r in store.query("SELECT id FROM prompts_mutual")
        for v in read_doc(store.data_root, str(r["id"]))[1]
    }
    rows = store.query(
        "SELECT cluster, count(*) n, min(at_ts) first_at, max(at_ts) last_at, "
        "max(words) words, count(DISTINCT project) projects "
        "FROM turn_prints WHERE cluster <> '' GROUP BY cluster "
        "HAVING count(*) >= ? ORDER BY n DESC, last_at DESC",
        (CANDIDATE_SENDS,),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        members = store.query(
            "SELECT print, body, project, at_ts, words FROM turn_prints "
            "WHERE cluster = ? ORDER BY at_ts DESC",
            (str(r["cluster"]),),
        )
        if not members or any(str(m["print"]) in known for m in members):
            continue          # already filed, under one wording or another
        newest = members[0]
        if int(newest["words"] or 0) < CANDIDATE_WORDS:
            continue
        out.append({
            "cluster": str(r["cluster"]),
            "sends": int(r["n"]),
            "first_at": str(r["first_at"]),
            "last_at": str(r["last_at"]),
            "projects": sorted({str(m["project"]) for m in members if m["project"]}),
            "words": int(newest["words"] or 0),
            "text": str(newest["body"] or ""),
            "title": prompt_title("", str(newest["body"] or "")),
            # How much the wording moves between sends: all the same text, or
            # a body with one line swapped each time.
            "wordings": len({str(m["print"]) for m in members}),
        })
        if len(out) >= limit:
            break
    return out


def adopt_candidate(store: ViewStore, cluster_key: str) -> str:
    """File a repeated message as a prompt, keeping every send behind it."""
    members = store.query(
        "SELECT body, project, at_ts, words FROM turn_prints "
        "WHERE cluster = ? ORDER BY at_ts DESC",
        (cluster_key,),
    )
    if not members:
        raise ValueError(f"no such cluster: {cluster_key}")
    newest = members[0]
    body = str(newest["body"] or "").strip()
    if not body:
        raise ValueError("that cluster has no text")
    return write_by_hand(
        store, prompt_title("", body), body,
        str(newest["project"] or ""), "", source="repeated",
    )


# ---------------------------------------------------------------------------
# Runs — a send, judged, with the facts of what followed it
# ---------------------------------------------------------------------------

# The operator's four ratings of a run. Ordinal, few steps, his words. There
# is deliberately no composite: "3 of 5 runs one-shot, 1 regression" says
# more than 7.4, and a number nobody can decompose is a number nobody trusts.
SCALES: dict[str, tuple[str, ...]] = {
    "task_success": ("below", "average", "better", "one-shot"),
    "regression": ("none", "some", "serious"),
    "intervention": ("none", "little", "lot"),
}
SCORE_MIN, SCORE_MAX = 1, 10
MAX_NOTE = limits.MAX_NOTE

# What "produced" counts: the entries an agent can post during a run. Each
# is a (view, label). Counted by agent within the session's clock window.
PRODUCED: tuple[tuple[str, str], ...] = (
    ("scans_mutual", "scans"), ("decisions_mutual", "decisions"),
    ("files_mutual", "files"), ("problems_mutual", "problems"),
    ("rules_mutual", "rules"), ("visions_mutual", "visions"),
    ("entrypoints_mutual", "entrypoints"),
    ("architecture_mutual", "architecture"), ("task_evidence_mutual", "evidence"),
)


def run_key(prompt_id: str, session_id: str, turn: int) -> str:
    seed = f"{prompt_id}|{session_id}|{turn}"
    return ENTITIES["prompt_run"].id_prefix + hashlib.sha256(seed.encode()).hexdigest()[:8]


def clean_rating(body: dict[str, Any]) -> dict[str, Any]:
    """Validate the four ratings and the note. Unknown steps are refused,
    absent fields are left alone, an explicit null clears one."""
    out: dict[str, Any] = {}
    for name, steps in SCALES.items():
        if name not in body:
            continue
        v = body[name]
        if v is None or v == "":
            out[name] = ""
            continue
        if str(v) not in steps:
            raise ValueError(f"{name} must be one of: {', '.join(steps)}")
        out[name] = str(v)
    if "score" in body:
        v = body["score"]
        if v is None or v == "":
            out["score"] = ""
        else:
            try:
                n = int(v)
            except (TypeError, ValueError) as exc:
                raise ValueError("score must be a whole number") from exc
            if not SCORE_MIN <= n <= SCORE_MAX:
                raise ValueError(f"score must be {SCORE_MIN}–{SCORE_MAX}")
            out["score"] = n
    if "note" in body:
        out["note"] = str(body["note"] or "").strip()[:MAX_NOTE]
    return out


def rate_run(
    store: ViewStore, prompt_id: str, session_id: str, turn: int,
    body: dict[str, Any], now: datetime | None = None,
) -> dict[str, Any]:
    """Upsert the operator's judgement of one run."""
    ent = ENTITIES["prompt_run"]
    fields = clean_rating(body)
    if not fields:
        raise ValueError("nothing to rate")
    rid = run_key(prompt_id, session_id, turn)
    at = (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
    path = store.data_root / ent.csv
    values = {k: str(v) for k, v in fields.items()}
    values["rated_at"] = at

    def mutate(rows: list[dict[str, str]]) -> bool:
        for r in rows:
            if r.get("id") == rid:
                r.update(values)
                return True
        # The first judgement of this run. Added in the same rewrite, under
        # the same lock: looked for and then appended in two steps, two
        # ratings at once were two rows.
        rows.append({
            "id": rid, "prompt_id": prompt_id, "session_id": session_id,
            "turn": str(turn), "rated_at": at,
            "task_success": "", "regression": "", "intervention": "",
            "score": "", "note": "", **values,
        })
        return True

    rewrite_rows(path, ent.columns, mutate)
    store.rebuild()
    return ratings_for(store, prompt_id).get((session_id, turn), {})


def ratings_for(store: ViewStore, prompt_id: str) -> dict[tuple[str, int], dict[str, Any]]:
    rows = store.query(
        "SELECT * FROM prompt_runs_mutual WHERE prompt_id = ?", (prompt_id,)
    )
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:
        score = r.get("score")
        out[(str(r["session_id"]), int(r["turn"] or 0))] = {
            "task_success": str(r.get("task_success") or ""),
            "regression": str(r.get("regression") or ""),
            "intervention": str(r.get("intervention") or ""),
            "score": int(score) if score not in (None, "") else None,
            "note": str(r.get("note") or ""),
            "rated_at": str(r.get("rated_at") or ""),
        }
    return out


def _session_turns(store: ViewStore, session_id: str) -> tuple[dict[str, Any] | None, list[dict]]:
    row = store.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if row is None:
        return None, []
    try:
        turns = json.loads(row.get("turns_json") or "[]")
    except ValueError:
        turns = []
    return row, turns


def _iso_end(session: dict[str, Any], send_at: str) -> str:
    """The session's end as an ISO stamp, on the send's own date."""
    return f"{send_at[:10]}T{str(session.get('end_time') or '23:59')}:59"


def facts_for(store: ViewStore, send: dict[str, Any]) -> dict[str, Any]:
    """What followed one send — recomputed from the log, never stored.

    Plain facts for the operator to read *while* rating, not a rating: turns
    the session ran after this send, how many of them were the operator
    stepping back in, what the agent posted, and whether a task the send
    named changed status before the session ended. Scenarios differ too much
    for any of these to be scored on its own — a one-turn session is a prompt
    that landed or a prompt that was abandoned, and only the operator knows.
    """
    session, turns = _session_turns(store, str(send["session_id"]))
    empty = {"turns_after": 0, "follow_ups": 0, "minutes": 0, "reply_words": 0,
             "produced": {}, "task_moved": [], "session_turns": 0}
    if session is None:
        return empty
    n = int(send["turn"])
    after = [t for t in turns if int(t.get("n") or 0) > n]
    mine = next((t for t in turns if int(t.get("n") or 0) == n), None)

    # From the posts cache — one read per store version, not eight scans per send.
    from . import produced as _produced
    produced = _produced.count_in(
        store, str(session.get("agent_id") or ""), str(session.get("created_date") or ""),
        str(send["at"])[11:16], str(session.get("end_time") or "23:59"),
    )

    moved: list[dict[str, str]] = []
    text = str(send.get("body") or send.get("head") or "")
    ids = sorted({m.group(1) for m in _TASK_ID_RE.finditer(text)})
    if ids:
        ph = ",".join("?" * len(ids))
        events = store.query(
            f"SELECT task_id, old_value, new_value FROM task_events_mutual "
            f"WHERE field = 'status' AND task_id IN ({ph}) "
            f"AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
            (*ids, str(send["at"]), _iso_end(session, str(send["at"]))),
        )
        moved = [{"task_id": str(e["task_id"]), "from": str(e["old_value"] or ""),
                  "to": str(e["new_value"] or "")} for e in events]

    return {
        "turns_after": len(after),
        "follow_ups": sum(1 for t in after if str(t.get("user") or "").strip()),
        "minutes": int(session.get("agent_min") or 0),
        "session_minutes": int(session.get("duration_min") or 0),
        "reply_words": len(str((mine or {}).get("agent") or "").split()),
        "produced": produced,
        "task_moved": moved,
        "session_turns": len(turns),
    }


def rollup(sends: list[dict[str, Any]], versions: list[Version]) -> dict[str, Any]:
    """Per version: how its runs were judged, as counts — never an average
    of an ordinal. Plus the medians of the plain facts, for context."""
    out: dict[str, Any] = {}
    by_version: dict[int | None, list[dict[str, Any]]] = {}
    for s in sends:
        by_version.setdefault(s.get("version"), []).append(s)
    for v in versions:
        runs = by_version.get(v.n, [])
        rated = [r["rating"] for r in runs if r.get("rating")]
        dist = {
            name: {step: sum(1 for r in rated if r.get(name) == step) for step in steps}
            for name, steps in SCALES.items()
        }
        scores = sorted(r["score"] for r in rated if r.get("score") is not None)
        fu = sorted(r["facts"]["follow_ups"] for r in runs if r.get("facts"))
        out[str(v.n)] = {
            "sends": len(runs),
            "rated": len(rated),
            "dist": dist,
            "score_median": scores[len(scores) // 2] if scores else None,
            "follow_ups_median": fu[len(fu) // 2] if fu else None,
        }
    reworded = by_version.get(None, [])
    if reworded:
        out["reworded"] = {"sends": len(reworded), "rated": sum(1 for r in reworded if r.get("rating"))}
    return out


# ---------------------------------------------------------------------------
# A version, judged
# ---------------------------------------------------------------------------

# The operator rewrites, sends, judges — one judgement per wording is how he
# thinks about it, and a wording is rarely sent twice unchanged. So the
# version carries the rating, on the same four scales, stored as a run row
# whose session is the literal "version" and whose turn is the version
# number. One table, one validator, no second schema to keep honest.
VERSION_SESSION = "version"


def rate_version(
    store: ViewStore, prompt_id: str, n: int, body: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    return rate_run(store, prompt_id, VERSION_SESSION, n, body, now=now)


def version_ratings(store: ViewStore, prompt_id: str) -> dict[int, dict[str, Any]]:
    return {
        turn: r for (sid, turn), r in ratings_for(store, prompt_id).items()
        if sid == VERSION_SESSION
    }


# ---------------------------------------------------------------------------
# Every send of every prompt — so any chat can say "this was a prompt"
# ---------------------------------------------------------------------------


def all_marks(store: ViewStore) -> dict[str, dict[str, dict[str, Any]]]:
    """session_id → turn → {prompt_id, title, version, exact, rating}.

    Read once per store version and kept on the store, so a reader that is
    not scoped to any prompt can still tag the turns that were one — the
    way from a chat to the prompt, not only from the prompt to its chats.
    """
    version = float(getattr(store, "view_mtime", 0.0) or 0.0)
    cached = getattr(store, "_prompt_marks_cache", None)
    if cached is not None and cached[0] == version:
        return cached[1]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in store.query("SELECT id, title FROM prompts_mutual WHERE status = 'active'"):
        pid = str(row["id"])
        _, versions = read_doc(store.data_root, pid)
        if not versions:
            continue
        ratings = version_ratings(store, pid)
        for send in sends(store, versions):
            r = ratings.get(int(send["version"])) if send.get("version") else None
            out.setdefault(str(send["session_id"]), {})[str(send["turn"])] = {
                "prompt_id": pid, "title": str(row.get("title") or ""),
                "version": send.get("version"), "exact": bool(send.get("exact")),
                "rating": ({"task_success": r.get("task_success") or "", "score": r.get("score")}
                           if r else None),
            }
    store._prompt_marks_cache = (version, out)  # type: ignore[attr-defined]
    return out
