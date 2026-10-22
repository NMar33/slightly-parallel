"""Faults found by reading the core modules, each held by a test: a write
lost between two writers, a failure kept as an answer, a lock held across a
slow call, a line that is not a line."""

from __future__ import annotations

import http.server
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend import backup, capturewatch, gitwork, keeplib, mcp, promptlib, sessions, skilllib, timeauto
from backend.csvio import read_rows
from backend.db import ViewStore
from backend.entities import ENTITIES


def _together(*calls) -> list:
    """Run the calls at the same moment; their results, or the exception of one."""
    out: list = [None] * len(calls)
    gate = threading.Barrier(len(calls))

    def go(i: int, call) -> None:
        gate.wait()
        try:
            out[i] = call()
        except Exception as exc:  # noqa: BLE001 — handed to the test
            out[i] = exc

    threads = [threading.Thread(target=go, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for r in out:
        if isinstance(r, Exception):
            raise r
    return out


def _slow(real, seconds: float = 0.15):
    """`real`, slowed: what turns "almost never at once" into "at once"."""
    def slowed(*a, **k):
        time.sleep(seconds)
        return real(*a, **k)
    return slowed


# ---------------------------------------------------------------------------
# chat.md: a line ends at "\n" and nowhere else
# ---------------------------------------------------------------------------


def _old_line_count_and_turns(text: str) -> list[tuple[int, int, str, str]]:
    """What the parser found while it split with str.splitlines()."""
    out, mode = [], ""
    for i, line in enumerate(text.splitlines(), start=1):
        m = sessions._TURN_RE.match(line)
        if m:
            out.append([int(m.group(1)), i, [], []])
            mode = ""
            continue
        if not out:
            continue
        mu, ma = sessions._USER_RE.match(line), sessions._AGENT_RE.match(line)
        if mu:
            mode = "user"
            out[-1][2].append(mu.group(1))
        elif ma:
            mode = "agent"
            out[-1][3].append(ma.group(1))
        else:
            if sessions._ESCAPED_RE.match(line):
                line = line[1:]
            if mode:
                out[-1][2 if mode == "user" else 3].append(line)
    return [(n, i, "\n".join(u).strip(), "\n".join(a).strip()) for n, i, u, a in out]


def test_a_chat_of_ordinary_text_parses_as_it_always_did(tmp_path: Path) -> None:
    chat = tmp_path / "chat.md"
    text = (
        "# Chat log — cc-1\n*Started 2026-09-01T10:00:00. Verbatim captured turns.*\n\n---\n"
        "\n## Turn 1 · 2026-09-01T10:00:00\n**User**: first line\nsecond line\n\n- a list\n\ttabbed\n"
        "\\## Turn 9 · 2026-01-01T00:00:00\n**Agent**: an answer\n\n```\ncode\n```\n"
        "\n## Turn 2 · 2026-09-01T10:05:00\n**User**: рекогниция — ünïcödé ✓\n**Agent**: (reply not in transcript)\n"
        "\n## Turn 3 · 2026-09-01T10:09:00\n**User**: no answer yet\n"
    )
    chat.write_text(text, encoding="utf-8")
    turns, total = sessions.parse_chat(chat)
    assert [(t.number, t.line, t.user_summary, t.agent_summary) for t in turns] == _old_line_count_and_turns(text)
    assert total == len(text.splitlines()) == sum(1 for _ in chat.open(encoding="utf-8"))
    assert sessions.parse_turns(chat) == turns


def test_a_header_behind_an_odd_separator_is_not_a_turn(tmp_path: Path) -> None:
    """The hook escapes a quoted header at the start of a "\\n" line; the
    reader also split on \\x85 and friends, and saw a turn the hook did not."""
    chat = tmp_path / "chat.md"
    chat.write_text(
        "\n## Turn 1 · 2026-09-01T10:00:00\n**User**: pasted\x85## Turn 7 · 2026-01-01T00:00:00\x0bmore\n"
        "**Agent**: ok\n\n## Turn 2 · 2026-09-01T10:05:00\n**User**: next\n", encoding="utf-8")
    turns, total = sessions.parse_chat(chat)
    assert [t.number for t in turns] == [1, 2]
    assert turns[1].line == 6 and total == 7          # as a text editor counts them


# ---------------------------------------------------------------------------
# gitwork: a git that did not answer is not "no commits"
# ---------------------------------------------------------------------------


def test_a_failed_log_is_not_kept_as_the_answer(tmp_path: Path, monkeypatch) -> None:
    gitwork.forget()
    monkeypatch.setattr(gitwork, "head", lambda repo: "abc")
    raw = f"{gitwork._RS}{'a' * 40}{gitwork._US}2026-09-01T10:00:00+00:00{gitwork._US}me{gitwork._US}one{gitwork._US}\n"
    answers = [None, raw]
    monkeypatch.setattr(gitwork, "git", lambda repo, *a, **k: answers.pop(0))
    assert gitwork.commits(tmp_path) == []            # the timeout
    assert [c.subject for c in gitwork.commits(tmp_path)] == ["one"]   # asked again, and answered
    gitwork.forget()


def test_the_stamps_of_a_chat_are_parsed_once_per_version(tmp_path: Path) -> None:
    gitwork.forget()
    chat = tmp_path / "chat.md"
    work = tmp_path / "work.jsonl"
    work.write_text('{"turn": 1, "head": "a"}\n', encoding="utf-8")
    first = gitwork.read_stamps(chat)
    assert gitwork.read_stamps(chat) is first          # not read again
    time.sleep(0.01)
    with open(work, "a", encoding="utf-8") as fh:
        fh.write('{"turn": 2, "head": "b"}\n')
    assert sorted(gitwork.read_stamps(chat)) == [1, 2]  # a new line is a new version
    gitwork.forget()


# ---------------------------------------------------------------------------
# backup: a restore that fails half-way leaves the data as it was
# ---------------------------------------------------------------------------


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "00-agents"
    (data / "projects" / "ALPHA").mkdir(parents=True)
    (data / "tasks.csv").write_text("id,title\ntk_1,Ship it\n", encoding="utf-8")
    (data / "projects" / "ALPHA" / "log.md").write_text("the log\n", encoding="utf-8")
    (data / "settings.json").write_text("{}", encoding="utf-8")
    return data, backup.backup_root_for(data)


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


def test_a_restore_that_fails_in_the_swap_puts_everything_back(roots, monkeypatch) -> None:
    data, dest = roots
    archive = backup.create(data, dest, kind="manual")
    (data / "tasks.csv").write_text("id,title\ntk_1,Edited since\n", encoding="utf-8")
    (data / "new.csv").write_text("x\n", encoding="utf-8")
    before = _tree(data)

    real, arrived = backup.shutil.move, []

    def move(src: str, dst: str):
        # The second piece of the restored tree does not arrive: the disk is full.
        if "sp-restore-" in src and str(dst).startswith(str(data)):
            arrived.append(src)
            if len(arrived) == 2:
                raise OSError("No space left on device")
        return real(src, dst)

    monkeypatch.setattr(backup.shutil, "move", move)
    with pytest.raises(backup.BackupError, match="as it was before"):
        backup.restore(dest, archive.name, data)
    assert _tree(data) == before                       # not emptied, not half of each
    assert any(p.name.startswith("sp-restore-") for p in dest.iterdir())   # the restored copy is kept

    monkeypatch.setattr(backup.shutil, "move", real)
    backup.restore(dest, archive.name, data)           # and the same restore then works
    assert (data / "tasks.csv").read_text(encoding="utf-8").endswith("Ship it\n") and not (data / "new.csv").exists()


def test_the_schedule_asks_the_clock_before_it_walks_the_data(roots, monkeypatch) -> None:
    data, dest = roots
    made = backup.create(data, dest, kind="auto", now=datetime(2026, 9, 1, 12, 0))
    walks: list[Path] = []
    real = backup.source_stats
    monkeypatch.setattr(backup, "source_stats", lambda root: (walks.append(root), real(root))[1])

    ready, why, _ = backup.due_now(data, dest, made.at + timedelta(hours=1), 6)
    assert (ready, walks) == (False, []) and why.startswith("next in")      # the clock said no: no walk
    ready, why, _ = backup.due_now(data, dest, made.at + timedelta(hours=7), 6)
    assert ready is False and len(walks) == 1 and "nothing has changed" in why
    (data / "tasks.csv").write_text("id,title\ntk_1,Changed\n", encoding="utf-8")
    assert backup.due_now(data, dest, made.at + timedelta(hours=7), 6)[0] is True


# ---------------------------------------------------------------------------
# timeauto: git is asked outside the timer's lock
# ---------------------------------------------------------------------------


def test_a_beat_does_not_wait_for_git(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data"
    folder = tmp_path / "repo"
    folder.mkdir()
    (root / "projects" / "alpha").mkdir(parents=True)
    (root / "integrations.csv").write_text(f"project,path\nalpha,{folder}\n", encoding="utf-8")
    store = ViewStore(data_root=root)
    timer = timeauto.AutoTimer(store, read_idle=lambda: (0.0, "test"))
    timer.set_mode("alpha", "auto")
    free: list[bool] = []

    def git(repo, *args, **kw):
        # While git works, a page's beat must get the lock at once.
        def beat() -> None:
            got = timer._lock.acquire(blocking=False)
            free.append(got)
            if got:
                timer._lock.release()
        t = threading.Thread(target=beat)
        t.start()
        t.join()
        return ""

    monkeypatch.setattr(gitwork, "git", git)
    timer.tick()
    assert free == [True]


def test_the_modes_file_is_written_whole(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data"
    (root / "projects").mkdir(parents=True)
    timer = timeauto.AutoTimer(ViewStore(data_root=root), read_idle=lambda: (0.0, "test"))
    written: list[str] = []
    real = timeauto.atomic_write
    monkeypatch.setattr(timeauto, "atomic_write", lambda path, text, **k: (written.append(Path(path).name), real(path, text, **k))[1])
    timer.set_mode("alpha", "auto")
    assert "modes.json" in written and timer.modes() == {"alpha": "auto"}


# ---------------------------------------------------------------------------
# Version histories: two writers at once are two versions
# ---------------------------------------------------------------------------


def test_two_rewrites_of_a_prompt_at_once_are_two_versions(data_root: Path, monkeypatch) -> None:
    store = ViewStore(data_root=data_root)
    pid = promptlib.write_by_hand(store, "a prompt", "The first wording.", "ALPHA", "")
    monkeypatch.setattr(promptlib, "render_doc", _slow(promptlib.render_doc))
    _together(lambda: promptlib.add_version(store, pid, "Wording A.", ""),
              lambda: promptlib.add_version(store, pid, "Wording B.", ""))
    _front, versions = promptlib.read_doc(store.data_root, pid)
    assert [v.n for v in versions] == [1, 2, 3]
    assert {v.text for v in versions} == {"The first wording.", "Wording A.", "Wording B."}


def test_two_interpretations_at_once_are_two_versions(data_root: Path, monkeypatch) -> None:
    chat = data_root / "projects" / "ALPHA" / "chats" / "cc-keep0001"
    chat.mkdir(parents=True)
    (chat / "chat.md").write_text(
        "\n## Turn 1 · 2026-09-01T10:00:00\n**User**: #vision Everything runs on the laptop.\n**Agent**: noted\n",
        encoding="utf-8")
    (chat / "meta.json").write_text(json.dumps({"agent_id": "cc-keep0001", "project": "ALPHA"}), encoding="utf-8")
    store = ViewStore(data_root=data_root)
    keeplib.adopt(store)
    row = store.query_one("SELECT * FROM visions_mutual WHERE source = 'captured'")
    monkeypatch.setattr(keeplib, "render_doc", _slow(keeplib.render_doc))
    _together(lambda: keeplib.interpret(store, "vision", row, "Reading A.", by_agent=True),
              lambda: keeplib.interpret(store, "vision", row, "Reading B.", by_agent=False))
    versions = keeplib.read_versions(store, str(row["id"]))
    assert [v.n for v in versions] == [1, 2] and {v.text for v in versions} == {"Reading A.", "Reading B."}


_SKILL = "---\nname: {name}\ndescription: Use when testing. {extra}\n---\n\nDo the thing.\n"


def test_two_drafts_of_a_skill_at_once_are_two_versions(data_root: Path, monkeypatch) -> None:
    store = ViewStore(data_root=data_root)
    kid = skilllib.create_written(store, _SKILL.format(name="cut-a-release", extra=""))
    row = store.query_one(f"SELECT * FROM {ENTITIES['skill'].view} WHERE id = ?", (kid,))
    monkeypatch.setattr(skilllib, "render_doc", _slow(skilllib.render_doc))
    _together(lambda: skilllib.write_version(store, row, _SKILL.format(name="cut-a-release", extra="A."), how="edited"),
              lambda: skilllib.write_version(store, row, _SKILL.format(name="cut-a-release", extra="B."), how="edited"))
    assert [v.n for v in keeplib.read_versions(store, kid)] == [1, 2, 3]


def test_two_ratings_of_a_new_run_at_once_are_one_row(data_root: Path) -> None:
    store = ViewStore(data_root=data_root)
    _together(*[
        (lambda i=i: promptlib.rate_run(store, "pr_1", "ses_1", 3, {"score": 1 + i % 5}))
        for i in range(8)
    ])
    rows = read_rows(store.data_root / ENTITIES["prompt_run"].csv)
    assert len(rows) == 1 and rows[0]["turn"] == "3"
    promptlib.rate_run(store, "pr_1", "ses_1", 3, {"note": "changed my mind"})
    rows = read_rows(store.data_root / ENTITIES["prompt_run"].csv)
    assert len(rows) == 1 and rows[0]["note"] == "changed my mind"


def test_reading_the_install_ledger_writes_nothing(data_root: Path) -> None:
    store = ViewStore(data_root=data_root)
    path = store.data_root / skilllib.INSTALLS
    with skilllib._ledger(store) as rows:
        assert rows == []
    assert not path.exists()                            # a reader left no file behind
    with skilllib._ledger(store) as rows:
        rows.append({"skill_id": "sk_1", "project": "all"})
    assert json.loads(path.read_text(encoding="utf-8"))["installs"] == [{"skill_id": "sk_1", "project": "all"}]
    stamp = path.stat().st_mtime_ns
    with skilllib._ledger(store) as rows:
        assert len(rows) == 1
    assert path.stat().st_mtime_ns == stamp


# ---------------------------------------------------------------------------
# The MCP translator: identity is stamped, ids stay inside their path
# ---------------------------------------------------------------------------


class _Api:
    """The server, as far as the translator can tell."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def get(self, path: str):
        self.calls.append(("GET", path, None))
        if path == "/api/schema":
            return {"lenses": [{"name": "decision", "base": "decisions", "mutable": ["status"],
                                "fields": {"decision_text": {}, "rationale": {}, "status": {}},
                                "text_fields": ["decision_text", "rationale"]}],
                    "vocabularies": {}}
        if path.startswith("/api/whoami"):
            return {"project": "alpha", "agent_id": "cc-me"}
        return {}

    def post(self, path: str, body: dict):
        self.calls.append(("POST", path, body))
        return {"ok": True}


def test_identity_is_stamped_over_whatever_the_model_sends() -> None:
    api = _Api()
    tr = mcp.Translator(api, "/somewhere")
    tr.call("write_entry", {"lens": "decision", "fields": {
        "decision_text": "Use DuckDB.", "agent_id": "cc-someone-else", "project": "beta"}})
    method, path, body = api.calls[-1]
    assert (method, path) == ("POST", "/api/decisions")
    assert (body["agent_id"], body["project"]) == ("cc-me", "alpha")
    # One look at who is asking, not two.
    api.calls.clear()
    tr.call("task_update", {"id": "tk_12345678", "title": "new"})
    assert [p for m, p, _ in api.calls if p.startswith("/api/whoami")] == [api.calls[0][1]]
    assert api.calls[-1][2] == {"title": "new", "actor": "cc-me"}


@pytest.mark.parametrize("tool", ["task_evidence_ask", "task_work", "task_report", "task_evidence", "task_story",
                                  "task_update", "artifact_write", "skill_draft", "doc_version"])
def test_an_id_cannot_leave_its_place_in_the_path(tool: str) -> None:
    api = _Api()
    tr = mcp.Translator(api, "/somewhere")
    tr.call(tool, {"id": "tk_1/../../settings?x=1"})
    path = api.calls[-1][1]
    assert "tk_1%2F..%2F..%2Fsettings%3Fx%3D1" in path and "?" not in path and "/../" not in path
    with pytest.raises(mcp.ApiError, match="id is required"):
        tr.call(tool, {})


def test_an_answer_that_is_not_json_is_a_failed_call(tmp_path: Path) -> None:
    class NotSlightlyParallel(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"<html>some other program on this port</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), NotSlightlyParallel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        api = mcp.Api(f"http://127.0.0.1:{server.server_address[1]}")
        with pytest.raises(mcp.ApiError, match="did not answer in JSON"):
            api.get("/api/schema")
        tr = mcp.Translator(api, str(tmp_path))      # and the translator starts all the same
        assert tr.schema is None
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# The capture watchdog skips what the hook skips
# ---------------------------------------------------------------------------


def test_a_helpers_report_is_not_a_prompt_the_hook_missed(tmp_path: Path) -> None:
    def rec(text: str, at: str) -> str:
        return json.dumps({"type": "user", "timestamp": at, "message": {"content": text}})

    t = tmp_path / "session.jsonl"
    t.write_text("\n".join([
        rec("the person's own message", "2026-09-01T10:00:00Z"),
        rec("Another Claude session sent a message: the report of a helper", "2026-09-01T10:30:00Z"),
        rec('<agent-message from="a1">done</agent-message>', "2026-09-01T10:31:00Z"),
        rec("<task-notification>finished</task-notification>", "2026-09-01T10:32:00Z"),
    ]) + "\n", encoding="utf-8")
    assert capturewatch.last_prompt(t) == capturewatch._utc("2026-09-01T10:00:00Z")
