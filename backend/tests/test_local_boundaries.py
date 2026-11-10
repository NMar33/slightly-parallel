"""The local server's boundaries, asked of every route by request.

The server listens on 127.0.0.1, so what can reach it is the operator's own
pages, any other program on the computer, and pages of other sites open in
the operator's browser (which may send requests, and can read an answer
only where the server allows it). Each test walks the app's own routes, so
a route added tomorrow is held to the same rules:

- a page of another site writes nothing (Origin and Sec-Fetch-Site), and
  the data root is byte for byte as it was;
- a request under a foreign host name (DNS rebinding) reaches no route;
- no GET hands a secret (the operator's token, the terminal's token) to a
  request without the operator's cookie (P19), and no answer lets another
  site's page read it (CORS);
- the routes that serve files serve nothing outside their folder, by
  ``..``, by an absolute path, or by a symlink planted inside the folder.

CodeQL sees none of these: they are the server's rules, not a library's.
"""

from __future__ import annotations

import re
import shutil
import urllib.parse
from pathlib import Path

from fastapi.testclient import TestClient

from backend import csvio
from backend.entities import TASK_EVIDENCE_COLUMNS
from backend.routers.evidence import EVIDENCE_DIR
from backend.routers.terminal import token_of
from backend.server import create_app
from tests.test_every_get_answers import FIXTURES, PARAM, _files, _first
from tests.test_write_fuzzer import _write_routes
from tests.conftest import symlink_or_need

HOSTILE = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
MARKER = "OUTSIDE-THE-DATA-ROOT-7f3a"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES, root)
    return root


def _known(root: Path) -> dict[str, str]:
    project = sorted(p.name for p in (root / "projects").iterdir() if p.is_dir())[0]
    return {"code": project, "project": project, "task_id": _first(root, "tasks.csv"),
            "sprint_id": _first(root, "sprints.csv"), "agent_id": _first(root, "tasks.csv", "agent_id"),
            "item_id": _first(root, "artifacts.csv")}


def _fill(path: str, known: dict[str, str], value: str | None = None) -> str:
    url = path
    for n in PARAM.findall(path):
        v = value if value is not None else (known.get(n) or "x")
        url = re.sub(r"{" + n + r"(?::\w+)?}", lambda _m, v=v: v, url, count=1)  # a Windows path is no template
    return url


def _get_routes(c: TestClient) -> dict[str, dict]:
    paths = c.get("/openapi.json").json()["paths"]
    return {p: ops["get"] for p, ops in paths.items() if "get" in ops}


def test_a_page_of_another_site_writes_nothing(tmp_path: Path) -> None:
    root = _root(tmp_path)
    known = _known(root)
    app = create_app(data_root=root, watch=False)
    let_through: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as c:
        before = _files(root)
        walked = 0
        for route in _write_routes(app):
            method = sorted(route.methods - {"GET", "HEAD", "OPTIONS"})[0]
            url = _fill(route.path, known)
            for headers in (HOSTILE, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
                r = c.request(method, url, json={"project": known["project"], "title": "from another site"},
                              headers=headers)
                walked += 1
                if r.status_code != 403:
                    let_through.append(f"{r.status_code} {method} {url} {headers}")
        after = _files(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not let_through, "\n".join(let_through[:30])
    assert not changed, changed[:20]
    assert walked >= 500


def test_a_foreign_host_name_reaches_no_route(tmp_path: Path) -> None:
    """A page of another site whose name was pointed at 127.0.0.1 (DNS
    rebinding) sends its own name as the Host."""
    root = _root(tmp_path)
    known = _known(root)
    app = create_app(data_root=root, watch=False)
    answered: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as c:
        routes = _get_routes(c)
        evil = TestClient(app, base_url="http://evil.example:8123", raise_server_exceptions=False)
        for path in routes:
            r = evil.get(_fill(path, known))
            if r.status_code < 400:
                answered.append(f"{r.status_code} GET {path}")
        for route in _write_routes(app):
            method = sorted(route.methods - {"GET", "HEAD", "OPTIONS"})[0]
            r = evil.request(method, _fill(route.path, known), json={})
            if r.status_code < 400:
                answered.append(f"{r.status_code} {method} {route.path}")
    assert not answered, "\n".join(answered[:30])


def test_no_get_hands_a_secret_to_a_request_without_the_cookie(tmp_path: Path) -> None:
    root = _root(tmp_path)
    known = _known(root)
    app = create_app(data_root=root, watch=False)
    leaks: list[str] = []
    readable: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as c:
        secrets = {"the operator's token": app.state.operator_token, "the terminal's token": token_of(app)}
        assert all(len(s) >= 16 for s in secrets.values())
        routes = _get_routes(c)
        c.cookies.clear()
        for path, op in routes.items():
            query = [f"{p['name']}={known.get(p['name'], 'x')}" for p in op.get("parameters", [])
                     if p.get("in") == "query" and p.get("required")]
            url = _fill(path, known) + ("?" + "&".join(query) if query else "")
            for headers in ({}, {"Origin": "https://evil.example"}):
                r = c.get(url, headers=headers)
                text = r.text + " ".join(f"{k}: {v}" for k, v in r.headers.items())
                for name, value in secrets.items():
                    if value in text:
                        leaks.append(f"GET {url} {headers or ''}: {name}")
                allow = r.headers.get("access-control-allow-origin", "")
                if allow in ("*", "https://evil.example", "null"):
                    readable.append(f"GET {url}: Access-Control-Allow-Origin {allow}")
    assert not leaks, "\n".join(leaks)
    assert not readable, "\n".join(readable[:20])


def test_the_file_routes_serve_nothing_outside_their_folder(tmp_path: Path) -> None:
    root = _root(tmp_path)
    known = _known(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(MARKER, encoding="utf-8")
    shot = outside / "secret.png"
    shot.write_text(MARKER, encoding="utf-8")
    # Symlinks planted where each file route looks, named as it expects.
    artifact = root / "projects" / "alpha-labs" / "artifacts" / "token-format-brief"
    for link, target in ((artifact / "leak.txt", secret), (root / "tour_shots" / "leak.png", shot),
                         (root / "task_story" / "leak.png", shot), (root / EVIDENCE_DIR / "leak.png", shot)):
        link.parent.mkdir(parents=True, exist_ok=True)
        symlink_or_need(link, target)
    (root / "story_images.csv").write_text(
        "id,note_id,task_id,project,title,path,width,height,bytes,created_at\n"
        f"im_leak,nt_x,{known['task_id']},alpha-labs,leak,task_story/leak.png,1,1,1,2026-11-10T10:00:00\n"
        f"im_dots,nt_x,{known['task_id']},alpha-labs,dots,task_story/../../outside/secret.png,1,1,1,2026-11-10T10:00:00\n"
        f"im_abs,nt_x,{known['task_id']},alpha-labs,abs,{shot},1,1,1,2026-11-10T10:00:00\n",
        encoding="utf-8")
    for eid, rel in (("te_leak", f"{EVIDENCE_DIR}/leak.png"), ("te_dots", f"{EVIDENCE_DIR}/../../outside/secret.png"),
                     ("te_abs", str(shot))):
        csvio.append_row(root / "task_evidence.csv", TASK_EVIDENCE_COLUMNS,
                         {c: "" for c in TASK_EVIDENCE_COLUMNS} | {"id": eid, "task_id": known["task_id"],
                                                                   "kind": "image", "body": rel})
    payloads = ["leak.txt", "leak.png", "im_leak", "im_dots", "im_abs", "te_leak", "te_dots", "te_abs",
                "../../../../outside/secret.txt", "..%2F..%2F..%2F..%2Foutside%2Fsecret.txt",
                urllib.parse.quote(str(secret), safe=""), str(secret).lstrip("/"),
                "....//....//....//outside/secret.txt"]
    app = create_app(data_root=root, watch=False)
    served: list[str] = []
    asked = 0
    with TestClient(app, raise_server_exceptions=False) as c:
        for path, op in _get_routes(c).items():
            names = PARAM.findall(path)
            pathish = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"
                       and any(k in p["name"] for k in ("path", "file", "name", "dir"))]
            if not names and not pathish:
                continue
            for value in payloads:
                urls = []
                for n in names:     # one parameter at a time takes the payload, the rest a real id
                    url = path
                    for m in names:
                        url = re.sub(r"{" + m + r"(?::\w+)?}", lambda _m, v=(value if m == n else (known.get(m) or "x")): v, url, count=1)
                    urls.append(url)
                for q in pathish:
                    urls.append(_fill(path, known) + f"?{q}={urllib.parse.quote(value, safe='')}")
                for url in urls:
                    r = c.get(url)
                    asked += 1
                    if MARKER in r.text:
                        served.append(f"{r.status_code} GET {url}")
    assert not served, "\n".join(served)
    assert asked >= 200
