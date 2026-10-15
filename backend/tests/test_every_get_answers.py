"""Every page the dashboard reads answers — on real-shaped data, and on nonsense.

Three read endpoints answered 500 on the operator's data for days before
anyone opened them (the sprints deck, a sprint's dossier, the prompt-runs
list). This calls every GET route the app serves against a copy of the demo
data root: a path id is filled with a real id where one exists, and with a
nonsense one where not. A 404 or a 422 is an answer; a 500 is a bug.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PARAM = re.compile(r"{(\w+)(?::\w+)?}")


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


def test_every_get_route_answers_without_a_server_error(tmp_path: Path) -> None:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    project = sorted(p.name for p in (root / "projects").iterdir() if p.is_dir())[0]
    known = {
        "code": project, "project": project,
        "task_id": _first(root, "tasks.csv"), "sprint_id": _first(root, "sprints.csv"),
        "agent_id": _first(root, "tasks.csv", "agent_id"),
    }
    failures: list[str] = []
    called = with_ids = 0
    with TestClient(create_app(data_root=root, watch=False), raise_server_exceptions=False) as c:
        routes = c.get("/openapi.json").json()["paths"]
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
            with_ids += bool(names) and r.status_code == 200
            if r.status_code >= 500:
                failures.append(f"{r.status_code} {url}: {r.text[:160]}")
            elif not names and r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                found = _ids_in(r.json())
                if found:
                    list_ids[path] = found
    assert not failures, "\n".join(failures)
    assert called >= 150, f"only {called} routes were called"
    assert with_ids >= 20, f"only {with_ids} detail routes found a real id"
