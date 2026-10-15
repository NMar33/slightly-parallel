"""Timelapse source — everything one film needs, in one read.

The board replays: a card is born at its created stamp, carries the
``old_value`` of its first status event as the status it was born with,
and every later status event moves it. Sessions come from the derived
time axis (turn logs), so the river underneath the board is real wall
clock, not agent-claimed work.

Read-only and derived. Nothing here writes; the film is a view of the
log, and a frame is a pure function of this payload and a timestamp.
"""

from __future__ import annotations

import itertools
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from ..db import ViewStore
from ..gitwork import SAFE_GIT
from .deps import PROJECT_CODE_RE, etag_for, get_store, json_response, maybe_304, not_found

router = APIRouter()

# Events that move a card on the presentation board. `lane` and `assignee`
# change a card's colour and column-of-origin but never its position in
# the film, so the film keeps the card's final lane and animates status.
MOVE_FIELDS = ("status",)

# Events that are worth a held beat rather than a movement.
MARK_FIELDS = {
    "agent_report": "report",
    "agent_done_at": "handed over",
    "done_in_chat": "#done in the chat",
    "evidence": "evidence",
}


def _project_cwd(data_root: Path, project: str) -> str:
    """Where the project's agents actually worked.

    Capture already records it: every chat session's ``meta.json`` carries the
    ``cwd`` the tool was started in. The most common one is the codebase, so
    the film can ask git about it without the operator registering anything.
    """
    chats = data_root / "projects" / project / "chats"
    if not chats.is_dir():
        return ""
    seen: Counter[str] = Counter()
    for meta in chats.glob("*/meta.json"):
        try:
            cwd = str(json.loads(meta.read_text(encoding="utf-8")).get("cwd") or "")
        except (OSError, ValueError):
            continue
        if cwd:
            seen[cwd] += 1
    for cwd, _ in seen.most_common():
        if Path(cwd).is_dir():
            return cwd
    return ""


# Where a path belongs, for the churn bands. First match wins, so the more
# specific prefixes come first.
AREAS: tuple[tuple[str, str], ...] = (
    ("backend/tests", "tests"),
    ("frontend/src/test", "tests"),
    ("backend", "backend"),
    ("frontend", "frontend"),
    ("docs", "docs"),
    ("articles", "docs"),
    ("prompts", "docs"),
    ("scripts", "tooling"),
    ("templates", "tooling"),
    ("fixtures", "tooling"),
)
AREA_ORDER = ("frontend", "backend", "tests", "docs", "tooling", "other")

# A graph has to stay legible and has to travel: the busiest files carry the
# structure, and the long tail is noise in both senses.
GRAPH_NODES = 130
GRAPH_EDGES = 420

# Anything bigger is a vendored lockfile or a generated blob, not work.
BIG_COMMIT = 20_000


def _area(path: str) -> str:
    for prefix, area in AREAS:
        if path.startswith(prefix):
            return area
    return "other"


def _git_log(cwd: str, since: str, until: str) -> list[str] | None:
    """`git log --numstat`, or nothing at all. Never raises."""
    if not cwd or not (Path(cwd) / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", *SAFE_GIT, "log", f"--since={since}", f"--until={until}",
             "--numstat", "--date=format:%Y-%m-%dT%H:%M:%S",
             "--pretty=format:C%H\t%ad"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.splitlines() if out.returncode == 0 else None


def _git_detail(lines: list[str]) -> dict[str, Any]:
    """Commits on the film's clock, and the graph the repository draws itself.

    Two files changed in the same commit are related — not because anyone said
    so, but because the work kept touching them together. Over 247 commits that
    co-change count is a real structure, and it is one nobody had to maintain.
    """
    commits: list[dict[str, Any]] = []
    churn: Counter[str] = Counter()
    born: dict[str, str] = {}
    pairs: Counter[tuple[str, str]] = Counter()
    tie_born: dict[tuple[str, str], str] = {}

    at = ""
    touched: list[str] = []
    add = dele = 0

    def close() -> None:
        nonlocal at, touched, add, dele
        if at and touched:
            uniq = sorted(set(touched))
            commits.append({
                "at": at, "add": add, "del": dele, "files": len(uniq),
                "areas": dict(Counter(_area(f) for f in uniq)),
                "touched": uniq[:48],
            })
            if len(uniq) <= 12:
                # A sweeping rename relates everything to everything; only a
                # commit small enough to be about one thing says anything.
                combos = list(itertools.combinations(uniq, 2))
                pairs.update(combos)
                for pair in combos:
                    tie_born[pair] = at
        at, touched, add, dele = "", [], 0, 0

    for line in lines:
        if line.startswith("C"):
            close()
            parts = line[1:].split("\t")
            at = parts[1] if len(parts) > 1 else ""
            continue
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        a, d, name = cols
        if not a.isdigit() or not d.isdigit():
            continue
        n = int(a) + int(d)
        if n > BIG_COMMIT:
            continue
        add += int(a)
        dele += int(d)
        touched.append(name)
        churn[name] += n
        # git log runs newest first, so the last stamp seen for a file is the
        # earliest one: that is when it appeared.
        born[name] = at
    close()

    keep = [f for f, _ in churn.most_common(GRAPH_NODES)]
    index = {f: i for i, f in enumerate(keep)}

    # A tie is born the first time two files move together, so the graph can
    # assemble itself instead of arriving whole.
    edges: list[list[Any]] = []
    for (a_path, b_path), w in pairs.most_common():
        if a_path not in index or b_path not in index:
            continue
        edges.append([index[a_path], index[b_path], w, tie_born.get((a_path, b_path), "")])
        if len(edges) >= GRAPH_EDGES:
            break

    # The folders those files live in, as a tree. A codebase graph that
    # ignores its own directories is an abstract blob; hung off the tree it
    # looks like the repository people actually work in.
    dirs: dict[str, int] = {}
    dir_rows: list[dict[str, Any]] = []

    def dir_index(path: str) -> int:
        if path in dirs:
            return dirs[path]
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        pi = dir_index(parent) if parent else -1
        dirs[path] = len(dir_rows)
        dir_rows.append({
            "path": path,
            "name": path.rsplit("/", 1)[-1] or path,
            "parent": pi,
            "depth": path.count("/"),
        })
        return dirs[path]

    nodes = []
    for f in keep:
        folder = f.rsplit("/", 1)[0] if "/" in f else ""
        nodes.append({
            "name": f.rsplit("/", 1)[-1],
            "path": f,
            "dir": dir_index(folder) if folder else -1,
            "area": _area(f),
            "churn": churn[f],
            "born": born.get(f, ""),
        })

    commits.sort(key=lambda c: c["at"])
    return {
        "commits": commits,
        "areas": [a for a in AREA_ORDER if any(a in c["areas"] for c in commits)],
        "graph": {"nodes": nodes, "edges": edges, "dirs": dir_rows},
    }


def _git_stats(detail: dict[str, Any], lines: list[str]) -> dict[str, Any]:
    """The film's git totals. Files are counted from the log itself: each
    commit's ``touched`` list is cut at 48 for the page, and a total read
    off those lists came out short after any large commit."""
    commits = detail["commits"]
    if not commits:
        return {}
    files: set[str] = set()
    for line in lines:
        cols = line.split("\t")
        if not line.startswith("C") and len(cols) == 3 and cols[0].isdigit() and cols[1].isdigit() \
                and int(cols[0]) + int(cols[1]) <= BIG_COMMIT:
            files.add(cols[2])
    return {
        "commits": len(commits),
        "lines_add": sum(c["add"] for c in commits),
        "lines_del": sum(c["del"] for c in commits),
        "files": len(files),
    }


def _born(created_date: str, created_time: str) -> str:
    """`2608-14` + `15:32` → an ISO stamp. Slightly Parallel dates are YYMM-DD."""
    d = (created_date or "").strip()
    t = (created_time or "").strip() or "00:00"
    if len(d) < 7:
        return ""
    try:
        stamp = datetime(
            2000 + int(d[0:2]), int(d[2:4]), int(d[5:7]),
            int(t[0:2]), int(t[3:5]),
        )
    except ValueError:
        return ""
    return stamp.isoformat(timespec="seconds")


@router.get("/api/timelapse")
def timelapse_source(
    request: Request,
    project: str = Query(...),
    store: ViewStore = Depends(get_store),
) -> Response:
    """One project's whole life as film source: cards, moves, river, marks."""
    # The code becomes a folder name below: a code, never a path.
    if not PROJECT_CODE_RE.match(project):
        raise not_found("project", project)
    etag = etag_for(f"timelapse:{project}", store)
    if (r := maybe_304(request, etag)) is not None:
        return r

    rows = store.query(
        "SELECT id, title, lane, assignee, status, tags, sprint_id, created_date, "
        "created_time, archived_at, agent_done_at, evidence_required "
        "FROM tasks_mutual WHERE project = ? ORDER BY created_date, created_time",
        (project,),
    )
    cards: dict[str, dict[str, Any]] = {}
    for r_ in rows:
        born = _born(str(r_.get("created_date") or ""), str(r_.get("created_time") or ""))
        if not born:
            continue
        cards[str(r_["id"])] = {
            "id": str(r_["id"]),
            "title": str(r_.get("title") or ""),
            "lane": str(r_.get("lane") or r_.get("assignee") or ""),
            "born": born,
            "status0": str(r_.get("status") or "unclassified"),
            "moves": [],
            "assignee": str(r_.get("assignee") or ""),
            "tags": str(r_.get("tags") or ""),
            "sprint": str(r_.get("sprint_id") or ""),
            "archived_at": str(r_.get("archived_at") or ""),
            "evidence": str(r_.get("evidence_required") or "") == "yes",
        }

    marks: list[dict[str, Any]] = []
    if cards:
        ph = ",".join("?" * len(cards))
        events = store.query(
            "SELECT task_id, timestamp, actor, field, old_value, new_value "
            f"FROM task_events_mutual WHERE task_id IN ({ph}) ORDER BY timestamp ASC",
            tuple(cards),
        )
        seen_status: set[str] = set()
        for e in events:
            tid = str(e.get("task_id") or "")
            card = cards.get(tid)
            if card is None:
                continue
            field = str(e.get("field") or "")
            at = str(e.get("timestamp") or "")
            if field in MOVE_FIELDS:
                if tid not in seen_status:
                    # The status it was born with is what the first move left.
                    card["status0"] = str(e.get("old_value") or "unclassified")
                    seen_status.add(tid)
                card["moves"].append({"at": at, "status": str(e.get("new_value") or "")})
            elif field in MARK_FIELDS:
                marks.append({
                    "at": at,
                    "kind": MARK_FIELDS[field],
                    "task_id": tid,
                    "actor": str(e.get("actor") or ""),
                })

    river = store.query(
        "SELECT id, agent_id, created_date, start_time, end_time, duration_min, "
        "turns_n, l1 FROM sessions WHERE project = ? ORDER BY created_date, start_time",
        (project,),
    )
    sessions = []
    for s in river:
        start = _born(str(s.get("created_date") or ""), str(s.get("start_time") or ""))
        end = _born(str(s.get("created_date") or ""), str(s.get("end_time") or ""))
        if not start:
            continue
        sessions.append({
            "id": str(s.get("id") or ""),
            "agent_id": str(s.get("agent_id") or ""),
            "start": start,
            "end": end or start,
            "turns_n": int(s.get("turns_n") or 0),
            "l1": str(s.get("l1") or ""),
        })

    stamps = [c["born"] for c in cards.values()]
    stamps += [m["at"] for c in cards.values() for m in c["moves"]]
    stamps += [s["end"] for s in sessions]
    span = {"start": min(stamps), "end": max(stamps)} if stamps else {"start": "", "end": ""}

    turns = sum(s["turns_n"] for s in sessions)
    stats: dict[str, Any] = {"turns": turns}
    detail: dict[str, Any] = {}
    if span["start"]:
        lines = _git_log(_project_cwd(store.data_root, project), span["start"], span["end"])
        if lines:
            detail = _git_detail(lines)
            stats |= _git_stats(detail, lines)

    return json_response({
        "project": project,
        "span": span,
        "cards": list(cards.values()),
        "sessions": sessions,
        "marks": marks,
        "stats": stats,
        # `null`, not `{}`: a project with no repository has no git section,
        # and an empty object is a shape the reader has to remember to check
        # the inside of.
        "git": detail or None,
    }, etag)
