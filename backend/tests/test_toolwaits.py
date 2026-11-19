import json
import sqlite3
from datetime import datetime, timedelta

from backend import toolwaits as tw


NOW = datetime(2026, 11, 18, 14)


def record(sec, item, codex=False):
    data = (
        {"type": "response_item", "payload": item}
        if codex
        else {"message": {"content": [item]}}
    )
    return (
        json.dumps(dict(data, timestamp=(NOW + timedelta(seconds=sec)).isoformat()))
        + "\n"
    )


def start(sec, key, name="Bash", **args):
    return record(sec, {"type": "tool_use", "name": name, "id": key, "input": args})


def end(sec, key, content="done"):
    return record(sec, {"type": "tool_result", "tool_use_id": key, "content": content})


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(tw.SCHEMA)
    return db


def test_parallel_restart_partial_and_replay(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        start(0, "a", command="pytest secret")
        + start(10, "b", command="git status")
        + "broken\n"
        + end(40, "a")
        + end(50, "b").rstrip()
    )
    dbfile = tmp_path / "waits.sqlite"
    db = connect(dbfile)
    tw.advance(db, path, "p", "agent")
    db.close()
    with path.open("a") as f:
        f.write("\n" + start(0, "a", command="pytest") + end(40, "a"))
    db = connect(dbfile)
    tw.advance(db, path, "p", "agent")
    tw.advance(db, path, "p", "agent")
    report = tw.snapshot(db, NOW)
    assert {r[3]: r[4] for r in report["daily"]} == {
        "tests": 10,
        "mixed": 30,
        "git": 10,
    }
    assert "secret" not in str(list(db.iterdump()))
    db.close()


def test_background_poll_and_operator(tmp_path, monkeypatch):
    path = tmp_path / "session"
    path.write_text(
        start(0, "launch", command="pytest", run_in_background=True)
        + end(1, "launch", "Command running in the background with ID: abc")
        + start(99, "poll", "TaskOutput", task_id="abc")
        + end(139, "poll")
        + start(140, "ask", "AskUserQuestion")
        + end(500, "ask")
    )
    db = connect(":memory:")
    tw.advance(db, path, "p", "a")
    folder = tmp_path / ".usage"
    folder.mkdir()
    (folder / "tool-waits.json").write_text(json.dumps(tw.snapshot(db, NOW)))
    monkeypatch.setenv("SP_TOOL_WAITS", "1")
    summary = tw.summary(tmp_path, "p", 1, NOW)
    assert (
        summary["seconds"],
        summary["jobs"],
        summary["blocked"],
        summary["immediate"],
    ) == (40, 1, 1, 1)
    assert summary["p90"] == 40
    assert tw.summary(tmp_path, "other", 1, NOW)["seconds"] == 0
    monkeypatch.delenv("SP_TOOL_WAITS")
    assert tw.summary(tmp_path, "p", 1, NOW) is None


def test_codex_buffered_clock_is_separate(tmp_path):
    src = tmp_path / "rollout"
    src.write_text(
        record(
            0,
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "a",
                "input": 'await tools.exec_command({cmd:"pytest"})',
            },
            True,
        )
        + record(
            0.001,
            {
                "type": "custom_tool_call_output",
                "call_id": "a",
                "output": [
                    {
                        "type": "input_text",
                        "text": "Script completed\nWall time 40.0 seconds\nOutput:\n",
                    }
                ],
            },
            True,
        )
    )
    db = connect(":memory:")
    tw.advance(db, src, "p", "agent")
    report = tw.snapshot(db, NOW)
    assert report["daily"] == []
    assert report["clock"] == [["p", "2026-11-18", 1]]


def test_poll_timeout_leaves_job_open(tmp_path):
    path = tmp_path / "poll"
    path.write_text(
        start(0, "launch", command="pytest")
        + end(1, "launch", "Command running in the background with ID: abc")
        + start(2, "poll", "TaskOutput", task_id="abc")
        + end(33, "poll", "<retrieval_status>timeout</retrieval_status>")
    )
    db = connect(":memory:")
    tw.advance(db, path, "project", "agent")
    assert tw.snapshot(db, NOW)["jobs"][0][2:] == [None, False, True]


def test_collector_publishes_and_stops_without_server_hooks(tmp_path):
    import time

    collector = tw.Collector(tmp_path)
    collector.start()
    try:
        path = tmp_path / ".usage/tool-waits.json"
        deadline = time.monotonic() + 15
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert json.loads(path.read_text())["daily"] == []
    finally:
        collector.stop()
    assert not collector.process.is_alive()
