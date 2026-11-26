"""The identity-protection matrix (tk_0b8a32d2): every agent write path ×
every identity field × where the agent puts it.

The paths are not listed by hand: the MCP rows are server._WRITE_TOOLS, and
each needs a WALK entry below (a new write tool without one fails here); the
HTTP rows are the requests those tools really post, replayed as an agent's
own body, and every pattern of server._MCP_WRITE_PATHS plus the lens create
and update must be among them.

Each cell sends one write with one forged identity field, top-level or in a
nested object the tool carries, through the real translator into the real
gated server, then reads the data folder: the forged value stored is
«PASSED THROUGH», a refusal that wrote nothing is «refused», a write that
did not store it is «stamped over» (through the MCP) or «dropped» (plain
HTTP). The matrix is never filled in by hand; with IDENTITY_MATRIX_OUT set
it is written there as JSON. The assertions hold every cell to the one
decision table, mcp_args.IDENTITY.

Known hole, pinned (tk_fd75ce20): the mark that says «this came through the
MCP» is a header anyone on this computer can send. A request that carries it
is trusted for the identity in its body: a lens create's created_date and
created_time, and the agent_id of another chat Slightly Parallel has
recorded, are stored as sent, whether agents.mcp_only is on or off. That is
the same-machine trust the server states (server.py, AgentsViaMcp); the
«known hole» rows show it and must not change silently.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pytest

from backend import keeplib, mcp
from backend import server as _server
from tests.conftest import git_env, git_repo, make_chat
from tests.test_membership_tools import A, PAGE, world  # noqa: F401 — the fixture

pytestmark = pytest.mark.strict_membership

B = "cc-bbbb2222"
FORGED = {
    "agent_id": "cc-forged999", "actor": "cc-forged998", "from": "cc-forged997", "from_agent": "cc-forged996",
    "agent": "cc-forged995", "created_by": "cc-forged994", "session": "FORGEDSESSION1", "session_id": "FORGEDSESSION2",
    "created_date": "0101-01", "created_time": "04:44", "project": "GAMMA",
}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and not p.name.endswith(".lock")
            and "logs/" not in p.relative_to(root).as_posix()}


def _stored(root: Path, before: dict[str, str], value: str) -> tuple[bool, bool]:
    """(something was written, the value is in what was written)."""
    after = _files(root)
    touched = [k for k, h in after.items() if before.get(k) != h]
    found = False
    for rel in touched:
        try:
            if value in (root / rel).read_text(encoding="utf-8", errors="replace"):
                found = True
        except OSError:
            continue
    return bool(touched), found


class _Api(mcp.Api):
    """The translator's client into the test app. In capture mode it records
    the request and sends nothing (the HTTP rows replay it)."""

    class Captured(Exception):
        pass

    def __init__(self, client) -> None:
        super().__init__("http://testserver")
        self.client = client
        self.calls: list[tuple[str, str, dict | None]] = []
        self.capture = False

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        if self.capture and method != "GET":
            self.calls.append((method, path, body))
            raise _Api.Captured()
        self.calls.append((method, path, body))
        r = self.client.request(method, path, json=body, headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        if r.status_code >= 400:
            raise mcp.ApiError(f"{r.status_code}: {r.json().get('detail', '')}")
        return r.json()


class Ctx:
    def __init__(self, tr: mcp.Translator, c, root: Path, tmp: Path) -> None:
        self.tr, self.c, self.root, self.tmp = tr, c, root, tmp
        self.turns: list[str] = ["work"]
        self.ids: dict[str, str] = {}
        self.png = tmp / "shot.png"
        self.png.write_bytes(PNG)
        self.txt = tmp / "report.txt"
        self.txt.write_text("p95 180 ms\n", encoding="utf-8")

    def say(self, text: str) -> int:
        """The operator's next message in chat A; its turn number."""
        self.turns.append(text)
        start = datetime.now() - timedelta(minutes=len(self.turns) + 1)
        make_chat(self.root, "ALPHA", A, [((start + timedelta(minutes=i)).isoformat(timespec="seconds"), t, "ok")
                                          for i, t in enumerate(self.turns)])
        store = self.c.app.state.store
        store.rebuild()
        keeplib.adopt(store)
        return len(self.turns)

    def call(self, tool: str, args: dict) -> Any:
        return self.tr.call(tool, args)

    def task(self, title: str) -> str:
        got = self.call("write_entry", {"lens": "task", "fields": {"title": title, "tags": "ag_idea"}})
        return got["metadata"]["id"]

    def from_b(self, text: str) -> None:
        r = self.c.post("/api/messages", json={"agent_id": B, "to": A, "text": text},
                        headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
        assert r.status_code == 201, r.text


def _find_id(obj: Any, prefix: str) -> str:
    """The first id with ``prefix`` in an answer, however it nests it."""
    if isinstance(obj, dict):
        if str(obj.get("id") or "").startswith(prefix):
            return str(obj["id"])
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            if (got := _find_id(v, prefix)):
                return got
    return ""


def _seed(ctx: Ctx) -> None:
    c, root = ctx.c, ctx.root
    make_chat(root, "ALPHA", B, [("2026-11-20T10:00:00", "hello", "ok")])
    (root / "done.json").write_text('{"since": "2000-01-01T00:00:00"}', encoding="utf-8")
    c.app.state.store.rebuild()
    # Level 3: the chat may move a task to another of its projects.
    assert c.post(f"/api/agents/{A}/membership", json={"op": "level", "value": 3}).status_code == 200
    ids = ctx.ids
    ids["task"] = c.post("/api/tasks", json={"project": "ALPHA", "title": "Seed task", "status": "doing",
                                             "agent_id": "operator", "created_date": "2611-20",
                                             "created_time": "10:00"}).json()["metadata"]["id"]
    ids["doc"] = c.post("/api/docs", json={"project": "ALPHA", "kind": "post",
                                           "title": "Seed doc"}).json()["doc"]["id"]
    ids["decision"] = ctx.call("write_entry", {"lens": "decision", "fields": {"decision": "seed decision",
                                                                              "why": "x"}})["metadata"]["id"]
    ids["note"] = _find_id(ctx.call("note_write", {"text": "# Seed note\n\nbody", "kind": "context"}), "nt_")
    ids["core"] = _find_id(ctx.call("core_new", {"name": "seed core", "type": "feature", "text": "kept"}), "cr_")
    t = ctx.say("#vision the app stays on one laptop")
    ids["vision"] = keeplib.keep_id("vision", "ALPHA", A, t)
    t = ctx.say("#skill keep a changelog of every release")
    ids["skill"] = keeplib.keep_id("skill", "ALPHA", A, t)
    t = ctx.say("#artifact the calculator dataset")
    ids["artifact"] = keeplib.keep_id("artifact", "ALPHA", A, t)
    t = ctx.say("#publish The calculator now subtracts.")
    ids["card"] = keeplib.keep_id("publish", "ALPHA", A, t)
    t = ctx.say("#entrypoint the install film")
    ids["entrypoint"] = keeplib.keep_id("entrypoint", "ALPHA", A, t)
    ctx.call("entrypoint_ask", {"id": ids["entrypoint"], "name": "the install film"})
    ctx.say("1")
    ctx.call("entrypoint_answer", {"number": 1})
    ids["way"] = _find_id(ctx.call("entrypoint_way", {"id": ids["entrypoint"], "way": {
        "name": "seed way", "kind": "page", "url": "http://127.0.0.1:8130/"}}), "ew_")
    r = c.post("/api/carries", json={"chat_agent": A, "turn": 1, "side": "reply", "level": "brief"})
    assert r.status_code < 400, r.text
    r = c.post(f"/api/tasks/{ids['task']}/story-requests", json={"type": "release", "brief": "Write the release."})
    assert r.status_code == 201, r.text
    ids["story"] = _find_id(r.json(), "sr_")
    # A repository for the project, with a commit no Task: line names.
    repo = Path(str((root / "integrations.csv").read_text(encoding="utf-8").splitlines()[1]).split(",", 1)[1])
    git_repo(repo)
    ids["repo"] = str(repo)


def _commit(ctx: Ctx, n: int) -> str:
    repo = Path(ctx.ids["repo"])
    (repo / f"f{n}.py").write_text(f"x = {n}\n", encoding="utf-8")
    env = git_env()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", f"Change {n}"], cwd=repo, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


# Each write tool: its valid call (n keeps each one new) and the nested
# objects that call carries, as paths to a dict inside the arguments.
Walk = tuple[Callable[[Ctx, int], dict[str, Any]], tuple[tuple[Any, ...], ...]]


def _undo_propose(ctx: Ctx, n: int) -> dict:
    tid = ctx.task(f"Undo me {n}")
    ctx.say(f"#undo the task undo me {n}")
    return {"ids": [tid]}


def _undo_apply(ctx: Ctx, n: int) -> dict:
    ctx.call("undo_propose", _undo_propose(ctx, n))
    ctx.say("#undo-yes")
    return {}


def _undo_restore(ctx: Ctx, n: int) -> dict:
    args = _undo_propose(ctx, n)
    ctx.call("undo_propose", args)
    ctx.say("#undo-yes")
    ctx.call("undo_apply", {})
    return {"id": args["ids"][0]}


def _task_done(ctx: Ctx, n: int) -> dict:
    # A task of its own each time: #done closes it, and the offer follows.
    r = ctx.c.post("/api/tasks", json={"project": "ALPHA", "title": f"Make step {n} work", "status": "doing",
                                       "agent_id": "operator", "created_date": "2611-20", "created_time": "10:00"})
    ctx.say(f"{r.json()['metadata']['id']} step {n}: make it work")
    ctx.say("#done")
    ctx.call("task_done", {})
    # Words of their own each time: a proposal like an earlier one is dropped.
    w = hashlib.sha256(str(n).encode()).hexdigest()
    return {"proposals": [{"title": f"Check {w[:6]} with {w[6:12]}", "line": f"{w[12:18]} ran on Linux only"}]}


def _next_tasks(ctx: Ctx, n: int) -> dict:
    ctx.call("task_done", _task_done(ctx, n))
    ctx.say("1")
    return {"numbers": [1]}


def _core_off(ctx: Ctx, n: int) -> dict:
    got = ctx.call("core_new", {"name": f"core to switch off {n}", "type": "feature", "text": "x"})
    return {"id": _find_id(got, "cr_")}


def _task_move(ctx: Ctx, n: int) -> dict:
    return {"id": ctx.task(f"Move me {n}"), "to": "BETA"}


def _messages(ctx: Ctx, n: int) -> dict:
    ctx.from_b(f"read me {n}")
    return {}


def _shot(ctx: Ctx, n: int) -> dict:
    shot = ctx.tmp / f"shot{n}.png"
    shot.write_bytes(PNG + str(n).encode())
    return {"id": ctx.ids["entrypoint"], "way_id": ctx.ids["way"], "path": str(shot), "caption": f"s{n}"}


def _artifact(ctx: Ctx, n: int) -> dict:
    folder = ctx.root / "projects" / "ALPHA" / "artifacts" / f"calc-data-{n}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "cases.csv").write_text(f"a,b\n{n},{n}\n", encoding="utf-8")
    return {"id": ctx.ids["artifact"], "name": f"calc-data-{n}", "kind": "dataset",
            "description": f"The calculator's cases, {n}."}


def _story(ctx: Ctx, n: int) -> dict:
    """A request of its own each time: a fulfilled one takes nothing more."""
    r = ctx.c.post(f"/api/tasks/{ctx.ids['task']}/story-requests", json={"type": "release", "brief": f"Write it, {n}."})
    assert r.status_code == 201, r.text
    return {"id": ctx.ids["task"], "request_id": _find_id(r.json(), "sr_"),
            "body": f"# Release {n}\n\nThe calculator subtracts. ![chart](image:1)",
            "images": [{"title": f"chart {n}", "data_base64": base64.b64encode(PNG).decode()}]}


def _picture(ctx: Ctx, n: int) -> str:
    p = ctx.tmp / f"pic{n}.png"
    p.write_bytes(PNG + str(n).encode())
    return str(p)


WALK: dict[str, Walk] = {
    "write_entry": (lambda x, n: {"lens": "decision", "fields": {"decision": f"chose sqlite {n}", "why": "small"}},
                    (("fields",),)),
    "update_entry": (lambda x, n: {"lens": "decision", "id": x.ids["decision"], "changes": {"why": f"because {n}"}},
                     (("changes",),)),
    "task_update": (lambda x, n: {"id": x.ids["task"], "comment": f"A note on the seed, {n}."}, ()),
    "task_report": (lambda x, n: {"id": x.ids["task"], "summary": f"Done, step {n}."}, ()),
    "task_evidence": (lambda x, n: {"id": x.ids["task"], "items": [{"kind": "text", "title": f"t{n}", "body": "b"}]},
                      (("items", 0),)),
    "task_story": (_story, (("images", 0),)),
    "task_move": (_task_move, ()),
    "interpret": (lambda x, n: {"lens": "vision", "id": x.ids["vision"], "text": f"## What\nOne laptop, {n}.\n"}, ()),
    "skill_draft": (lambda x, n: {"id": x.ids["skill"], "skill_md": f"---\nname: changelog\ndescription: keep a "
                                  f"changelog {n}\n---\n\nWrite the entry.\n",
                                  "files": {"notes.md": f"step {n}\n"}}, ()),
    "artifact_write": (_artifact, ()),
    "doc_version": (lambda x, n: {"id": x.ids["doc"], "body": f"# Seed doc\n\nDraft {n}.", "note": f"v{n}"}, ()),
    "architecture_page": (lambda x, n: {"text": PAGE + f"\n- step {n}\n", "note": f"v{n}"}, ()),
    "map_write": (lambda x, n: {"map": {"template": "tool", "rows": [
        {"kind": "module", "name": f"calc{n}", "what": "the calculator", "where": "calc.py", "evidence": "computed"}]},
        "note": f"v{n}"}, (("map",), ("map", "rows", 0))),
    "standup_postpone": (lambda x, n: {"date": f"2611-{(n % 27) + 1:02d}", "hours": 4}, ()),
    "undo_propose": (_undo_propose, ()),
    "undo_apply": (_undo_apply, ()),
    "undo_restore": (_undo_restore, ()),
    "task_commits": (lambda x, n: {"id": x.ids["task"], "shas": [_commit(x, n)]}, ()),
    "task_done": (_task_done, (("proposals", 0),)),
    "next_tasks": (_next_tasks, ()),
    "core_new": (lambda x, n: {"name": f"core {n}", "type": "feature", "text": f"keep {n} in view"}, ()),
    "core_note": (lambda x, n: {"id": x.ids["core"], "text": f"note {n}", "comment": "c"}, ()),
    "core_attach": (lambda x, n: {"id": x.ids["core"], "task_id": x.task(f"Attach me {n}"), "note": f"n{n}"}, ()),
    "core_off": (_core_off, ()),
    "publish_attach": (lambda x, n: {"id": x.ids["card"], "links": [{"title": f"l{n}", "url": f"https://example.org/{n}"}]},
                       (("links", 0),)),
    "publish_write": (lambda x, n: {"id": x.ids["card"], "context": f"ctx {n}",
                                    "links": [{"title": f"l{n}", "url": f"https://example.org/w{n}"}],
                                    "images": [{"path": _picture(x, n), "title": f"p{n}"}],
                                    "files": [{"path": str(x.txt), "title": f"report {n}"}]},
                      (("links", 0), ("images", 0), ("files", 0))),
    "usage_prices_write": (lambda x, n: {"models": {f"claude-x{n}": {"input": 1, "write_5m": 1, "write_1h": 1,
                                                                     "read": 1, "output": 1}},
                                         "sources": ["https://example.com/prices"], "note": f"v{n}"},
                           (("models", "claude-x{n}"),)),
    "entrypoint_stop": (lambda x, n: {"id": x.ids["entrypoint"], "text": f"stopped at step {n}"}, ()),
    "entrypoint_way": (lambda x, n: {"id": x.ids["entrypoint"], "way": {"name": f"way {n}", "kind": "page",
                                                                        "url": f"http://127.0.0.1:{8200 + n}/"}},
                       (("way",),)),
    "entrypoint_shot": (_shot, ()),
    "entrypoint_ask": (lambda x, n: (x.say(f"#entrypoint the topic {n}") and
                                     {"id": keeplib.keep_id("entrypoint", "ALPHA", A, len(x.turns)),
                                      "name": f"the topic {n}"}), ()),
    "entrypoint_answer": (lambda x, n: (x.call("entrypoint_ask", WALK["entrypoint_ask"][0](x, n)) and x.say("1")
                                        and {"number": 1}), ()),
    "task_topic": (lambda x, n: {"id": x.task(f"Topic me {n}"), "topic": x.ids["entrypoint"]}, ()),
    "carry_brief": (lambda x, n: {"message": f"{A}#1/reply", "text": f"The brief, {n}."}, ()),
    "note_write": (lambda x, n: {"text": f"# Note {n}\n\nbody {n}", "kind": "context",
                                 "images": [{"path": _picture(x, n), "caption": f"c{n}"}]}, (("images", 0),)),
    "note_image": (lambda x, n: {"id": x.ids["note"], "path": _picture(x, n), "caption": f"c{n}"}, ()),
    "message": (lambda x, n: {"to": B, "text": f"hello {n}"}, ()),
    "messages": (_messages, ()),
}


def _with(args: dict, where: tuple[Any, ...], field: str, value: str, n: int) -> dict:
    """args with field=value at the dict ``where`` points to (top-level for ())."""
    out = json.loads(json.dumps(args))
    target = out
    for step in where:
        step = step.replace("{n}", str(n)) if isinstance(step, str) else step
        target = target[step]
    target[field] = value
    return out


def _cell(ctx: Ctx, tool: str, args: dict, value: str) -> str:
    tr, root = ctx.tr, ctx.root
    before = _files(root)
    calls = len(tr.api.calls)
    try:
        tr.call(tool, args)
    except mcp.ApiError as exc:
        wrote, found = _stored(root, before, value)
        if found:
            return "PASSED THROUGH"
        posted = any(m != "GET" for m, *_ in tr.api.calls[calls:])
        return f"refused ({'server' if posted else 'translator'})" + (" but wrote" if wrote else "") + f": {str(exc)[:90]}"
    wrote, found = _stored(root, before, value)
    if found:
        return "PASSED THROUGH"
    return "stamped over" if wrote else "no write"


def _mcp_rows(ctx: Ctx) -> tuple[dict[str, dict[str, str]], list[tuple[str, str, dict]]]:
    """The MCP rows, and each tool's valid request as it was posted."""
    missing = sorted(set(_server._WRITE_TOOLS) - set(WALK))
    assert not missing, f"write tools with no walk: {missing}"
    matrix: dict[str, dict[str, str]] = {}
    posted: list[tuple[str, str, dict]] = []
    n = 0
    for tool in _server._WRITE_TOOLS:
        make, nested = WALK[tool]
        n += 1
        args = make(ctx, n)
        before = _files(ctx.root)
        calls = len(ctx.tr.api.calls)
        ctx.tr.call(tool, args)          # the valid call writes: the fixture is right
        assert _stored(ctx.root, before, "\0")[0], f"{tool}: the valid call wrote nothing"
        posted += [(tool, p, b or {}) for m, p, b in ctx.tr.api.calls[calls:] if m != "GET"]
        row: dict[str, str] = {}
        for where in ((), *nested):
            label = "top" if not where else ".".join(str(s) for s in where).replace("{n}", "N")
            for field, value in FORGED.items():
                n += 1
                row[f"{field}@{label}"] = _cell(ctx, tool, _with(make(ctx, n), where, field, value, n), value)
        matrix[tool] = row
    return matrix, posted


def _route(path: str) -> str:
    return re.sub(r"/(tk|dc|cr|pu|ep|nt|vs|sk|ar|dc|sr|doc|msg)_[0-9a-zA-Z_-]+", r"/{\1}", path)


def _http_rows(ctx: Ctx, posted: list[tuple[str, str, dict]], monkeypatch) -> dict[str, dict[str, str]]:
    """agents.mcp_only off: each route the tools post to, with the agent's own
    body (the tool's next valid request, captured) and one forged field."""
    monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self: False)
    from fastapi.testclient import TestClient
    agent = TestClient(ctx.c.app)
    agent.cookies.clear()
    api = ctx.tr.api
    assert isinstance(api, _Api)
    out: dict[str, dict[str, str]] = {}
    n = 5000
    for tool in _server._WRITE_TOOLS:
        make, _nested = WALK[tool]
        row: dict[str, str] = {}
        route = ""
        for field, value in FORGED.items():
            n += 1
            args = make(ctx, n)
            api.capture = True
            at = len(api.calls)
            try:
                ctx.tr.call(tool, args)
            except _Api.Captured:
                pass
            finally:
                api.capture = False
            method, path, body = api.calls[at]
            route = f"{method} {_route(path.split('?')[0])}"
            before = _files(ctx.root)
            # An agent's own request: no operator cookie, no MCP mark.
            r = agent.request(method, path, json={**(body or {}), field: value})
            wrote, found = _stored(ctx.root, before, value)
            if found:
                row[f"{field}@body"] = "PASSED THROUGH"
            elif r.status_code >= 400:
                row[f"{field}@body"] = f"refused ({r.status_code}): {str(r.json().get('detail', ''))[:80]}"
            else:
                row[f"{field}@body"] = "dropped" if wrote else "no write"
        out[f"{route} ({tool})"] = row
    return out


def _known_hole(ctx: Ctx, monkeypatch) -> dict[str, dict[str, str]]:
    """The header that marks a request as the MCP's, sent by hand, with
    agents.mcp_only on and off (tk_fd75ce20)."""
    out: dict[str, dict[str, str]] = {}
    for on in (True, False):
        monkeypatch.setattr(_server.AgentsViaMcp, "_enforced", lambda self, on=on: on)
        row = {}
        for label, body, value in (
            ("created_date@body", {"created_date": "0101-01", "created_time": "10:00"}, "0101-01"),
            ("created_time@body", {"created_date": "2611-20", "created_time": "04:44"}, "04:44"),
            ("agent_id=another recorded chat@body", {"agent_id": B, "created_date": "2611-20",
                                                     "created_time": "10:00"}, B),
        ):
            before = _files(ctx.root)
            r = ctx.c.post("/api/decisions", json={"project": "ALPHA", "agent_id": A,
                                                   "decision_text": f"by hand {label} {on}", **body},
                           headers={mcp.VIA_HEADER: mcp.VIA_VALUE})
            wrote, found = _stored(ctx.root, before, f"by hand {label} {on}")
            stored_value = found and _stored(ctx.root, before, value)[1]
            row[label] = ("PASSED THROUGH" if stored_value else f"refused ({r.status_code})" if r.status_code >= 400
                          else "dropped")
        out[f"POST /api/decisions with the MCP header, mcp_only {'on' if on else 'off'}"] = row
    return out


def test_the_identity_matrix(world, monkeypatch, tmp_path) -> None:  # noqa: F811
    _tr, c, root = world
    tr = mcp.Translator(_Api(c), cwd=_tr.cwd)
    ctx = Ctx(tr, c, root, tmp_path)
    _seed(ctx)
    mcp_rows, posted = _mcp_rows(ctx)
    http_rows = _http_rows(ctx, posted, monkeypatch)
    hole = _known_hole(ctx, monkeypatch)
    matrix = {"mcp": mcp_rows, "http (mcp_only off)": http_rows, "known hole": hole}
    out = os.environ.get("IDENTITY_MATRIX_OUT")
    if out:
        Path(out).write_text(json.dumps(matrix, indent=1, ensure_ascii=False), encoding="utf-8")

    from backend import mcp_args

    # Every route the MCP may write to was walked, the lens create and update among them.
    walked = {p.split("?")[0] for _t, p, _b in posted}
    for pattern in _server._MCP_WRITE_PATHS:
        if pattern in (r"/api/standups/(claim|postpone)",):
            assert any(re.fullmatch(pattern, p) for p in walked), pattern
            continue
        assert any(re.fullmatch(pattern, p) for p in walked), f"no walk posts to {pattern}"
    assert "/api/decisions" in walked and f"/api/decisions/{ctx.ids['decision']}/update" in walked

    # Every tool, top-level: a stamped name dies in the translator, before any request.
    for tool in sorted(mcp_args.TOOL_ARGS):
        for field in sorted(mcp_args.STAMPED):
            calls = len(tr.api.calls)
            with pytest.raises(mcp.ApiError, match=f"^{field} is stamped by Slightly Parallel; leave it out"):
                tr.call(tool, {field: FORGED[field]})
            assert not [m for m, *_ in tr.api.calls[calls:] if m != "GET"], (tool, field)

    # MCP: every cell as the table says. Nothing forged is stored.
    for tool, row in mcp_rows.items():
        for key, got in row.items():
            field = key.split("@")[0]
            assert got != "PASSED THROUGH", (tool, key)
            assert mcp_args.IDENTITY[field] == "refuse"
            if field == "project" and key.endswith("@top") and tool in mcp_args.PROJECT_TOOLS:
                # A real argument there: a project the chat is not in is the gate's refusal.
                assert got.startswith("refused (server)") and "not a member of GAMMA" in got, (tool, key, got)
            else:
                assert got.startswith("refused (translator)"), (tool, key, got)

    # Plain HTTP: the body is the agent's own claim. Nothing forged is stored,
    # except a create's created_date/created_time (there the body is the stamp).
    for route, row in http_rows.items():
        for key, got in row.items():
            field = key.split("@")[0]
            if route.startswith("POST /api/decisions ") and field in ("created_date", "created_time"):
                assert got == "PASSED THROUGH", (route, key, got)
            else:
                assert got != "PASSED THROUGH", (route, key, got)
    # The known hole, pinned: it must not change without this test changing.
    for row in hole.values():
        assert set(row.values()) == {"PASSED THROUGH"}, hole
