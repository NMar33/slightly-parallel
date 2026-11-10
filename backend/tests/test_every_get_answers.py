"""Every page the dashboard reads answers — on real-shaped data, and on nonsense.

Three read endpoints answered 500 on the operator's data for days before
anyone opened them (the sprints deck, a sprint's dossier, the prompt-runs
list). This calls every GET route the app serves against a copy of the demo
data root: a path id is filled with a real id where one exists, and with a
nonsense one where not. A 404 or a 422 is an answer; a 500 is a bug.

The same walk is a read: it must leave the data root as it found it (P10,
P17 in docs/audit/patterns.md). Every file is hashed after the app has
started and again after the walk; a file changed, added or removed outside
WRITTEN_BY_READS fails, with the route that did it.
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PARAM = re.compile(r"{(\w+)(?::\w+)?}")


# Files a GET may write, each for a reason someone chose. A new one is a
# finding: a read that writes (P10) or a failed read written back (P17).
WRITTEN_BY_READS = {
    # P10, accepted: the task list adopts #now and #done cards and keeps
    # where it got to (nowlib, donelib).
    "now.json": "the #now adoption's state",
    "done.json": "the #done adoption's state",
    # Kept by the Usage page for the Stop hook and for the next visit
    # (docs/logging.md).
    ".usage/units.json": "what one dollar takes of the limit, read by the hook",
    ".usage/insights.json": "today's feed of insights",
}


def _files(root: Path) -> dict[str, str]:
    """Every file under the data root and its hash; lock files left out
    (a read takes a lock, which leaves its empty file)."""
    out = {}
    for p in root.rglob("*"):
        if p.is_file() and not p.name.endswith(".lock"):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _changed(before: dict[str, str], after: dict[str, str], allowed: dict[str, str]) -> list[str]:
    return sorted(k for k in before.keys() | after.keys()
                  if before.get(k) != after.get(k) and k not in allowed)


def _first(root: Path, name: str, col: str = "id") -> str:
    try:
        with open(root / name, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get(col):
                    return row[col]
    except OSError:
        pass
    return "x"


def _ids_in(payload) -> str | None:
    """The first `id` anywhere in a list answer."""
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and v[0].get("id"):
                return str(v[0]["id"])
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return str(payload[0].get("id") or "") or None
    return None


def _walk(root: Path, allowed: dict[str, str]) -> tuple[list[str], list[str], int, int]:
    """Call every GET route on the data root: (server errors, files a call
    changed outside ``allowed``, routes called, detail routes that found a
    real id)."""
    project = sorted(p.name for p in (root / "projects").iterdir() if p.is_dir())[0]
    known = {
        "code": project, "project": project,
        "task_id": _first(root, "tasks.csv"), "sprint_id": _first(root, "sprints.csv"),
        "agent_id": _first(root, "tasks.csv", "agent_id"),
    }
    failures: list[str] = []
    wrote: list[str] = []
    called = with_ids = 0
    with TestClient(create_app(data_root=root, watch=False), raise_server_exceptions=False) as c:
        routes = c.get("/openapi.json").json()["paths"]
        files = _files(root)
        list_ids: dict[str, str] = {}
        # Lists first: they give the ids the detail routes are asked about.
        for path, ops in sorted(routes.items(), key=lambda kv: "{" in kv[0]):
            get = ops.get("get")
            if not get:
                continue
            query = []
            for p in get.get("parameters", []):
                if p.get("in") == "query" and p.get("required"):
                    n = p["name"]
                    query.append(f"{n}={known.get(n) or ('2609-01' if 'date' in n or n in ('day', 'for_date') else '2026-09' if n == 'month' else 'x')}")
            names = PARAM.findall(path)
            url = path
            for n in names:
                base = path.split("/{")[0]
                value = known.get(n) or (list_ids.get(base) if n == "item_id" else None) or "x"
                url = re.sub(r"{" + n + r"(?::\w+)?}", value, url, count=1)
            url += ("?" + "&".join(query)) if query else ""
            r = c.get(url)
            called += 1
            now = _files(root)
            wrote += [f"GET {url} wrote {name}" for name in _changed(files, now, allowed)]
            files = now
            with_ids += bool(names) and r.status_code == 200
            if r.status_code >= 500:
                failures.append(f"{r.status_code} {url}: {r.text[:160]}")
            elif not names and r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                found = _ids_in(r.json())
                if found:
                    list_ids[path] = found
    return failures, wrote, called, with_ids


def test_every_get_route_answers_without_a_server_error_and_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    failures, wrote, called, with_ids = _walk(root, WRITTEN_BY_READS)
    assert not failures, "\n".join(failures)
    assert not wrote, "\n".join(wrote)
    assert called >= 150, f"only {called} routes were called"
    assert with_ids >= 20, f"only {with_ids} detail routes found a real id"


# Not UTF-8 and not JSON: what a disk error, a cut write or a hand edit leaves.
CORRUPT = b"\xff\xfe{ cut here"


def test_a_read_never_writes_over_a_file_it_could_not_read(tmp_path: Path) -> None:
    """P17: a file that cannot be read was taken as empty and written back,
    losing what it held. Every JSON file a read may touch is made unreadable
    (the ones reads write included); the walk must answer, and leave each
    of them byte for byte as it was."""
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    spoilt = [root / n for n in ("now.json", "done.json", "boards.json", "examples.json",
                                 "skill_installs.json", ".usage/units.json", ".usage/insights.json")]
    spoilt += sorted((root / "projects").glob("*/chats/*/meta.json"))
    for f in spoilt:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(CORRUPT)
    # units.json holds nothing of its own: the page works it out again from
    # the usage logs on each build, so writing it whole over a bad copy
    # repairs it. Every other file here holds state a write back would lose.
    names = {f.relative_to(root).as_posix() for f in spoilt} - {".usage/units.json"}
    # Every other file a read writes may still change; these may not.
    failures, wrote, _called, _ids = _walk(root, {k: v for k, v in WRITTEN_BY_READS.items() if k not in names})
    assert not failures, "\n".join(failures)
    over = [w for w in wrote if w.rsplit(" wrote ", 1)[1] in names]
    assert not over, "\n".join(over)
    left = sorted(n for n in names if not (root / n).is_file() or (root / n).read_bytes() != CORRUPT)
    assert not left, f"changed or removed: {left}"
