"""The terminal log (termlog.py, routers/termlog.py, tk_f89e84c4): a page's
batch is kept per mode, refused whole when it is wrong, bounded; Full turns
itself back to Light; old files go; the day reads back for the Monitor; the
report holds no text anyone typed."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app_settings, termlog
from backend.server import create_app

SECRET = "hunter2-s3cr3t-paste"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def client(root: Path):
    termlog.REC.take()
    termlog.REC.drain_events()
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _row(t: float | None = None, **extra) -> dict:
    t = time.time() if t is None else t
    h = [0] * (len(termlog.EDGES) + 1)
    h[2] = 50          # 50 frames under 17 ms
    h[7] = 3           # 3 frames 50–75 ms
    h[11] = 1          # 1 frame 200–300 ms
    return {
        "t": int(t // 60 * 60), "page": "w1",
        "frames": {"scroll": {"h": h, "max": 240}},
        "terms": {"t-1": {"p": "alpha", "b": "tmux", "in": 4000, "out": 12, "keys": 10, "pastes": 1, "wheels": 30}},
        "errors": {"js": 0, "fetch": 1},
        "findings": [{"t": int(t * 1000), "kind": "scroll-stall", "sid": "t-1", "p": "alpha", "doing": "scroll", "n": 240}],
        **extra,
    }


def _light(root: Path) -> Path:
    return termlog.log_dir(root) / f"light-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def test_light_is_the_default_and_a_batch_is_one_line_a_row(client, root) -> None:
    assert client.get("/api/terminal/log/mode").json()["mode"] == "light"
    r = client.post("/api/terminal/log", json={"page": "w1", "rows": [_row()], "events": [[1, "key", "t-1", 1, None]]})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "light"
    lines = _light(root).read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["src"] == "page"
    # Light keeps no events.
    assert not list(termlog.log_dir(root).glob("full-*"))


def test_off_keeps_nothing(client, root) -> None:
    assert client.post("/api/terminal/log/mode", json={"mode": "off"}).json()["mode"] == "off"
    assert client.post("/api/terminal/log", json={"rows": [_row()]}).json()["kept"] == 0
    assert not _light(root).exists()


def test_full_keeps_the_events_and_turns_itself_back_to_light(client, root) -> None:
    m = client.post("/api/terminal/log/mode", json={"mode": "full", "hours": 1}).json()
    assert m["mode"] == "full" and m["full_until"] > time.time() + 3500
    r = client.post("/api/terminal/log", json={"page": "w1", "rows": [], "events": [[1, "key", "t-1", 1, None], [2, "frame", "", 16.6, None]]})
    assert r.json()["kept"] == 2
    full = list(termlog.log_dir(root).glob("full-*.jsonl"))
    assert len(full) == 1 and len(full[0].read_text().splitlines()) == 2
    # The hour is over: the mode reads Light at once, and the next batch writes it back.
    later = time.time() + 3700
    assert termlog.mode(root, later)["mode"] == "light"
    assert termlog.accept(root, {"rows": [_row(later)]}, later)["mode"] == "light"
    assert app_settings.load(root)["terminal.log"] == "light"


def test_full_switched_on_in_settings_gets_its_two_hours(client, root) -> None:
    app_settings.save(root, {"terminal.log": "full"})
    now = time.time()
    got = termlog.accept(root, {"rows": []}, now)
    assert got["mode"] == "full"
    assert abs(got["full_until"] - (now + 2 * 3600)) < 5


def test_a_wrong_batch_is_refused_and_writes_nothing(client, root) -> None:
    for bad in ({"rows": "x"}, {"rows": [{"no": "t"}]}, {"rows": [_row()] * 21}, {"events": [["t", "k"]]},
                {"rows": [_row()], "events": [[1]]}, [1, 2]):
        r = client.post("/api/terminal/log", json=bad)
        assert r.status_code == 422, (bad, r.text)
    assert not termlog.log_dir(root).exists() or not list(termlog.log_dir(root).iterdir())


def test_a_batch_over_its_size_is_refused(client, root) -> None:
    big = {"rows": [], "events": [[1, "key", "x" * 100, 1, 1]] * 30_000}
    r = client.post("/api/terminal/log", content=json.dumps(big), headers={"content-type": "application/json"})
    assert r.status_code in (413, 422)
    assert not _light(root).exists()


def test_long_strings_are_cut_and_unknown_keys_dropped(client, root) -> None:
    row = _row(extra_key="y", findings=[{"t": 1, "kind": "fetch", "what": "z" * 5000}])
    client.post("/api/terminal/log", json={"rows": [row]})
    got = json.loads(_light(root).read_text())
    assert "extra_key" not in got
    assert len(got["findings"][0]["what"]) == termlog.MAX_TEXT


def test_old_light_files_go_after_14_days_and_full_files_keep_their_cap(root, monkeypatch) -> None:
    d = termlog.log_dir(root)
    d.mkdir(parents=True)
    (d / "light-2000-01-01.jsonl").write_text("{}\n")
    keep = d / f"light-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    keep.write_text("{}\n")
    monkeypatch.setattr(termlog, "FULL_TOTAL_BYTES", 2500)
    for i in range(4):
        p = d / f"full-2026010{i}-000000.jsonl"
        p.write_text("x" * 1000)
        os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))
    termlog.housekeep(root)
    assert not (d / "light-2000-01-01.jsonl").exists()
    assert keep.exists()
    # The two newest fit under 2500 bytes; the older go.
    assert sorted(p.name for p in d.glob("full-*")) == ["full-20260102-000000.jsonl", "full-20260103-000000.jsonl"]


def test_full_files_rotate_at_their_size(root, monkeypatch) -> None:
    monkeypatch.setattr(termlog, "FULL_FILE_BYTES", 300)
    termlog.set_mode(root, "full")
    now = time.time()
    for i in range(5):
        termlog.accept(root, {"events": [[i, "frame", "", 16.0, None]] * 5}, now + i)
    assert len(list(termlog.log_dir(root).glob("full-*.jsonl"))) >= 2


def test_the_server_adds_its_own_minute_with_tmux_timeouts(client, root) -> None:
    termlog.REC.tmux_call("capture-pane", 2001, timed_out=True)
    termlog.REC.tmux_call("display-message", 4)
    with termlog.timed("write", "t-1", 10):
        pass
    client.post("/api/terminal/log", json={"rows": [_row()]})
    rows = [json.loads(x) for x in _light(root).read_text().splitlines()]
    server = [r for r in rows if r["src"] == "server"]
    assert len(server) == 1
    assert server[0]["tmux"]["capture-pane"]["timeouts"] == 1
    assert any(f["kind"] == "tmux-timeout" for f in server[0]["findings"])
    s = client.get("/api/terminal/log/summary").json()
    assert s["server"]["tmux"]["capture-pane"]["timeouts"] == 1
    assert s["by_kind"]["tmux-timeout"] == 1


def test_the_summary_reads_the_day_back(client, root) -> None:
    client.post("/api/terminal/log", json={"rows": [_row()]})
    s = client.get("/api/terminal/log/summary").json()
    assert s["totals"]["frames"] == 54
    assert s["totals"]["slow"] == 4          # 3 at 50–75 ms and 1 at 200–300 ms
    assert s["totals"]["stalls"] == 1
    assert s["totals"]["errors"] == 1
    assert s["totals"]["in"] == 4000
    assert s["totals"]["p50"] == 17
    assert s["totals"]["max"] == 240
    assert s["findings"][0]["kind"] == "scroll-stall"
    assert sum(h["frames"] for h in s["hours"]) == 54
    assert client.get("/api/terminal/log/summary?day=bad").status_code == 422


def test_reading_writes_nothing(client, root) -> None:
    app_settings.save(root, {"terminal.log": "full"})
    before = app_settings.load(root)
    client.get("/api/terminal/log/mode")
    client.get("/api/terminal/log/summary")
    client.get("/api/terminal/log/report")
    assert app_settings.load(root) == before
    assert not (termlog.log_dir(root) / "state.json").exists()


def test_the_report_is_a_file_with_versions_and_settings_and_no_text(client, root) -> None:
    termlog.set_mode(root, "full")
    client.post("/api/terminal/log", json={"page": "w1", "rows": [_row()], "events": [[time.time() * 1000, "paste", "t-1", 21, "native"]]})
    r = client.get("/api/terminal/log/report")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    got = r.json()
    assert got["versions"]["slightly_parallel"]
    assert got["system"]["os"]
    assert got["settings"]["terminal.log"] == "full"
    assert len(got["full_last_hour"]) == 1
    assert SECRET not in r.text


def test_mode_switch_is_the_operators_and_checked(client) -> None:
    assert client.post("/api/terminal/log/mode", json={"mode": "loud"}).status_code == 422
    assert client.post("/api/terminal/log/mode", json={"mode": "full", "hours": 99}).status_code == 422
    assert client.post("/api/terminal/log/mode", json={"mode": "full", "agent_id": "cc-abc"}).status_code >= 400
    assert client.get("/api/terminal/log/mode").json()["mode"] == "light"


def test_percentile_reads_the_bucket_edges() -> None:
    h = [0] * (len(termlog.EDGES) + 1)
    h[2] = 95
    h[-1] = 5
    assert termlog.percentile(h, 0.5) == 17
    assert termlog.percentile(h, 0.95) == 17
    assert termlog.percentile(h, 0.99, top=1500) == 1500


def test_a_tmux_call_that_times_out_is_counted(root, monkeypatch) -> None:
    import subprocess

    from backend import termlib

    termlog.REC.take()
    termlog.REC.mode = "light"

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("tmux", 2)

    monkeypatch.setattr(termlib.subprocess, "run", slow)
    monkeypatch.setattr(termlib, "tmux_argv", lambda root, *args: ["tmux", *args])
    with pytest.raises(termlib.TmuxError):
        termlib.tmux(root, "capture-pane", timeout=2)
    row = termlog.REC.take()
    assert row is not None and row["tmux"]["capture-pane"]["timeouts"] == 1
    assert row["findings"][0]["kind"] == "tmux-timeout"
