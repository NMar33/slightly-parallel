"""Every write route answers a body of the wrong shape with a refusal, never a 500.

P16 in docs/audit/patterns.md: `relations: 5`, `add: 5`, `item_ids: 5`,
`tasks: true` were 500s (a loop over an int). A fuzzer found those four once
and was not kept; this one is. It walks the app's own routes, so a route
added tomorrow is walked with no one remembering to:

- the field names a route reads are taken from its handler's source, and
  from the source of the functions it hands the body to (one level down);
- a base body gives every name a plain value (a real project, task or
  sprint where the name says so);
- then each field in turn is sent as an int, a bool, null, a list, an
  object, a string, a float and a huge number.

A 2xx, 4xx is an answer; a 5xx (or an exception) is a bug. A 4xx must also
change no file of the data root, and must not list the value it refused
among the allowed ones (tests/refusals.py; the agent's tags list was refused
with ag_followup named as allowed). Each enum field is also sent its own
allowed value inside a list, the shape that refusal came from. The run starts in
a folder of its own, so a route that writes relative to the server's working
folder (P01) shows up as a file there and fails too.

Heavy (about 15 000 requests): CI runs it on Linux on every push, and on the
three systems weekly (.github/workflows/weekly.yml).
"""

from __future__ import annotations

import inspect
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.entities import ENTITIES
from backend.server import create_app, operator_cookie
from backend.vocab import ENUM_FIELDS
from tests.refusals import changed, contradicts, snapshot
from tests.test_every_get_answers import FIXTURES, PARAM, _first, _ids_in

pytestmark = pytest.mark.heavy

# Routes left out, each for what it reaches outside the data root.
SKIP = {
    "/api/backup/reveal": "opens the system's file manager",
    "/api/sessions/{session_id}/open": "opens a terminal or an editor on the computer",
    "/api/usage/limits/refresh": "starts the real Codex program",
    "/api/tour/capture": "starts a browser",
    "/api/setup/delete-data": "deletes the data root the rest of the walk runs on (tested in test_setup.py)",
    "/api/setup/data-root": "moves the server to another data root (tested in test_data_root_switch.py)",
    "/api/skills/usage/backfill": "reads every Claude Code transcript in the home folder; takes no body",
}
SKIP_PREFIX = {
    "/api/terminal/": "starts tmux and a shell",
}

VALUES: list[Any] = [5, True, None, [1, "x"], {"a": 1}, "x", 1.5, 10**30]
NAMES = re.compile(r"""\b\w+\s*(?:\.get\(|\[)\s*["'](\w+)["']""")
CALLS = re.compile(r"\b((?:\w+\.)?\w+)\(([^()]*\b(?:body|raw|payload|data|fields)\b[^()]*)\)")


def _write_routes(app) -> list[Any]:
    out: list[Any] = []

    def walk(routes):
        for r in routes:
            if hasattr(r, "endpoint") and hasattr(r, "methods"):
                if r.methods - {"GET", "HEAD", "OPTIONS"}:
                    out.append(r)
            elif hasattr(r, "original_router"):
                walk(r.original_router.routes)
            elif hasattr(r, "routes"):
                walk(r.routes)

    walk(app.routes)
    return sorted(out, key=lambda r: r.path)


def _source(fn: Any) -> str:
    try:
        return inspect.getsource(inspect.unwrap(fn))
    except (OSError, TypeError):
        return ""


def _names_of(endpoint: Any) -> list[str]:
    """The keys a handler reads from its body, and those of the functions it
    passes the body to."""
    src = _source(endpoint)
    names = set(NAMES.findall(src))
    scope = getattr(inspect.unwrap(endpoint), "__globals__", {})
    for callee, _args in CALLS.findall(src):
        head, _, tail = callee.partition(".")
        fn = scope.get(head)
        if tail and fn is not None:
            fn = getattr(fn, tail, None)
        if callable(fn) and (getattr(fn, "__module__", None) or "").startswith("backend"):
            names |= set(NAMES.findall(_source(fn)))
    return sorted(names)


def _columns_of(path: str) -> set[str]:
    """A lens route (/api/<lens>, /api/<lens>/{item_id}/update) takes its
    entity's columns: the generic handler names none of them."""
    parts = path.removeprefix("/api/").split("/")
    if not (len(parts) == 1 or (len(parts) == 3 and parts[1] == "{item_id}" and parts[2] == "update")):
        return set()
    seg = parts[0]
    out: set[str] = set()
    for e in ENTITIES.values():
        if e.csv.removesuffix(".csv").replace("_", "-") == seg:
            out |= set(e.columns)
    return out


# Routes that take away what the others are about run last.
LAST = re.compile(r"/(delete|remove|off|archive|uninstall|clear|unmark|forget)$")


def _id_for(c: TestClient, path: str, name: str, known: dict[str, str], seen: dict[str, str]) -> str:
    """A real id for a path's parameter: a known one, else the first id the
    list above it answers (GET /api/boards for /api/boards/{board_id}/…)."""
    if name in known:
        return known[name]
    base = path.split("/{" + name)[0]
    if base not in seen:
        r = c.get(base)
        found = _ids_in(r.json()) if r.status_code == 200 and "json" in r.headers.get("content-type", "") else None
        seen[base] = found or "x"
    return seen[base]


# Files a refused request may change: the server's own log.
QUIET = ("logs/",)


def _enums(name: str) -> list[set[str]]:
    return [vals for fields in ENUM_FIELDS.values() for f, vals in fields.items() if f == name and vals]


def _detail(r) -> str:
    try:
        got = r.json()
    except ValueError:
        return r.text
    return str(got.get("detail", "")) if isinstance(got, dict) else str(got)


def _plain(name: str, known: dict[str, str]) -> Any:
    if name in known:
        return known[name]
    if name.endswith("_ids") or name in ("ids", "tags", "items", "tasks", "relations"):
        return []
    if name.endswith(("_date", "date", "day")):
        return "2609-01"
    return "x"


@pytest.fixture()
def fuzz_client(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    cwd = tmp_path / "server-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    app = create_app(data_root=root, watch=False)
    with TestClient(app, raise_server_exceptions=False) as c:
        # The operator's own page: the operator-only routes are walked too.
        name, value = operator_cookie(app)
        c.cookies.set(name, value)
        yield c, root, cwd


def test_no_write_route_answers_a_wrong_shape_with_a_server_error(fuzz_client) -> None:
    c, root, cwd = fuzz_client
    project = sorted(p.name for p in (root / "projects").iterdir() if p.is_dir())[0]
    known = {
        "code": project, "project": project,
        "task_id": _first(root, "tasks.csv"), "sprint_id": _first(root, "sprints.csv"),
        "agent_id": _first(root, "tasks.csv", "agent_id"),
    }
    failures: list[str] = []
    refused_writes: list[str] = []
    contradictions: list[str] = []
    sent = walked = 0
    seen: dict[str, str] = {}
    routes = sorted(_write_routes(c.app), key=lambda r: bool(LAST.search(r.path)))
    for route in routes:
        if route.path in SKIP or any(route.path.startswith(p) for p in SKIP_PREFIX):
            continue
        url = route.path
        for n in PARAM.findall(route.path):
            url = re.sub(r"{" + n + r"(?::\w+)?}", _id_for(c, route.path, n, known, seen), url, count=1)
        method = sorted(route.methods - {"GET", "HEAD", "OPTIONS"})[0]
        names = sorted(set(_names_of(route.endpoint)) | _columns_of(route.path))
        base = {n: _plain(n, known) for n in names}
        # A handler that reads no field is asked once with an object and
        # once without; the shapes go to the fields of those that read some.
        bodies: list[Any] = [base, [], 5, "x", None] if names else [base, 5]
        bodies += [{**base, n: v} for n in names for v in VALUES]
        # An allowed value in a list: the shape that was refused as "unknown".
        bodies += [{**base, n: [sorted(allowed)[0]]} for n in names for allowed in _enums(n)]
        walked += 1
        for body in bodies:
            before = snapshot(root, skip=QUIET)
            r = c.request(method, url, json=body)
            sent += 1
            if r.status_code >= 500:
                failures.append(f"{r.status_code} {method} {url} {str(body)[:200]}: {r.text[:160]}")
                continue
            if 400 <= r.status_code < 500:
                moved = changed(before, snapshot(root, skip=QUIET))
                if moved:
                    refused_writes.append(f"{r.status_code} {method} {url} {str(body)[:120]} changed {moved[:3]}")
                detail = _detail(r)
                for n, v in (body.items() if isinstance(body, dict) else []):
                    if who := contradicts(detail, v):
                        contradictions.append(f"{method} {url} {n}={v!r}: {detail[:200]} ({who})")
    stray = sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*"))
    assert not failures, f"{len(failures)} server errors:\n" + "\n".join(failures[:60])
    assert not contradictions, f"{len(contradictions)} refusals list the refused value as allowed:\n" + "\n".join(contradictions[:40])
    assert not refused_writes, f"{len(refused_writes)} refused writes changed files:\n" + "\n".join(refused_writes[:40])
    assert not stray, f"written relative to the server's working folder: {stray[:20]}"
    assert walked >= 170, f"only {walked} write routes walked"
    assert sent >= 5_000, f"only {sent} requests sent"
