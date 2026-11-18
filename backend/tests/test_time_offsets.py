"""Time entries and the smart timer keep their moments with the UTC offset
(tk_3a363c87): lengths across the hours the clocks change are real time,
old rows (naive local times) still read, and the migration gives the
stored rows their offset once, with a copy first, never losing a row.

The zone is America/Los_Angeles: the clocks went back at 2:00 on
2026-11-01 (01:00–02:00 came twice) and forward at 2:00 on 2026-03-08
(02:00–03:00 never came)."""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend import timeauto
from backend.csvio import DamagedFile, read_rows
from backend.entities import ENTITIES
from backend.server import create_app
from backend.timelib import decorate, elapsed_seconds, migrate_offsets

ENT = ENTITIES["time_entry"]
HEADER = ",".join(ENT.columns)


@pytest.fixture()
def la(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("Windows: a process cannot set its own time zone (no time.tzset)")
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture()
def backups(tmp_path: Path, monkeypatch) -> Path:
    out = tmp_path / "backups"
    monkeypatch.setenv("SP_BACKUP_ROOT", str(out))
    return out


def _utc(*a: int) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


def _when(stored: str) -> datetime:
    got = datetime.fromisoformat(stored)
    assert got.tzinfo is not None, f"{stored} has no offset"
    return got


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now
        self.idle: float | None = 0.0

    def __call__(self) -> float:
        return self.now

    def reading(self):
        return self.idle, "test"


def _app(root: Path, clock=None):
    (root / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    app = create_app(data_root=root, watch=False)
    if clock is not None:
        app.state.timer = timeauto.AutoTimer(app.state.store, read_idle=clock.reading, clock=clock)
    return app


# ------------------------------------------------------------------ the timer


def test_an_auto_span_across_the_spring_forward_hour_is_its_real_length(la, tmp_path: Path, backups) -> None:
    start = _utc(2026, 3, 8, 9, 50)               # 01:50 PST; at 02:00 the clock reads 03:00
    clock = Clock(start)
    app = _app(tmp_path / "data", clock)
    timer = app.state.timer
    with TestClient(app) as c:
        c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
        for s in range(0, 20 * 60 + 1, 20):       # twenty minutes of beats
            clock.now = start + s
            c.post("/api/time/auto/beat", json={"project": "alpha", "source": "window"})
            timer.tick()
        clock.now = start + 20 * 60 + 200          # past the grace: closed at the last beat
        timer.tick()
        [row] = c.get("/api/time-entries").json()["time_entries"]
    began, ended = _when(row["started_at"]), _when(row["ended_at"])
    assert row["started_at"].endswith("-08:00") and row["ended_at"].endswith("-07:00")
    assert (began.hour, ended.hour) == (1, 3)      # 01:50 PST to 03:10 PDT on the wall
    assert ended - began == timedelta(minutes=20) and row["duration_min"] == 20


def test_an_auto_span_in_the_hour_that_comes_twice_is_kept_and_positive(la, tmp_path: Path, backups) -> None:
    start = _utc(2026, 11, 1, 8, 50)               # 01:50 PDT; at 02:00 the clock reads 01:00 again
    clock = Clock(start)
    app = _app(tmp_path / "data", clock)
    timer = app.state.timer
    with TestClient(app) as c:
        c.post("/api/time/auto/mode", json={"project": "alpha", "mode": "auto"})
        for s in range(0, 20 * 60 + 1, 20):
            clock.now = start + s
            timer.beat("alpha", "tk_dst", "terminal")
            timer.tick()
        clock.now = start + 20 * 60 + 200
        timer.tick()
        [row] = c.get("/api/time-entries").json()["time_entries"]
    assert row["started_at"].endswith("01:50:00-07:00") and row["ended_at"].endswith("01:10:00-08:00")
    assert row["duration_min"] == 20 and row["task_id"] == "tk_dst"


def test_away_in_the_hour_that_comes_twice_is_a_positive_gap(la, tmp_path: Path, backups) -> None:
    import time_machine
    idle: list[float | None] = [0.0]
    # A ZoneInfo destination: time_machine keeps the zone (a UTC one would make the run UTC).
    with time_machine.travel(datetime(2026, 11, 1, 1, 50, tzinfo=ZoneInfo("America/Los_Angeles")), tick=False) as tr:
        app = _app(tmp_path / "data")
        app.state.timer = timeauto.AutoTimer(app.state.store, read_idle=lambda: (idle[0], "test"), clock=lambda: time.time())
        timer = app.state.timer
        with TestClient(app) as c:
            entry = c.post("/api/time/start", json={"project": "alpha"}).json()   # 01:50 PDT
            assert entry["started_at"].endswith("-07:00")
            tr.shift(timedelta(minutes=12))          # 01:02 PST, nobody here since 01:50:30 PDT
            idle[0] = 11.5 * 60
            timer.tick()
            row = c.get(f"/api/time-entries/{entry['id']}").json()["metadata"]
            assert _when(row["paused_at"]) == _when(entry["started_at"]) + timedelta(seconds=30)
            tr.shift(timedelta(minutes=23))          # 01:25 PST, back
            idle[0] = 5
            timer.tick()
            [notice] = c.get("/api/time/auto").json()["away"]
            assert 34 * 60 <= notice["sec"] <= 35 * 60 and not notice["long"]
            stopped = c.post(f"/api/time/{entry['id']}/stop", json={}).json()
    # 35 minutes on the clock, 34.5 of them away: half a minute counted, rounded.
    assert stopped["duration_min"] in (0, 1) and stopped["paused_total_sec"] >= 34 * 60


def test_an_old_naive_row_still_reads_as_local_time_without_the_migration(la) -> None:
    row = {"started_at": "2026-11-01T00:30:00", "ended_at": "2026-11-01T01:30:00", "paused_total_sec": "0",
           "duration_min": "60", "share_pct": "100"}
    assert elapsed_seconds(row) == 3600
    running = {"started_at": "2026-11-01T00:30:00", "ended_at": "", "paused_at": "", "paused_total_sec": "0", "share_pct": "50"}
    # A caller's naive "now" (the calendar's) is local time as well.
    got = decorate(running, datetime(2026, 11, 1, 1, 30))
    assert got["elapsed_sec"] == 3600 and got["attributed_sec"] == 1800


def test_times_typed_by_hand_are_kept_with_their_offset(la, tmp_path: Path, backups) -> None:
    app = _app(tmp_path / "data")
    with TestClient(app) as c:
        made = c.post("/api/time-entries", json={
            "project": "alpha", "agent_id": "operator", "created_date": "2611-01", "created_time": "00:30",
            "started_at": "2026-11-01T00:30:00", "ended_at": "2026-11-01T01:30:00", "duration_min": 60,
            "paused_total_sec": 0, "share_pct": 100,
        })
        assert made.status_code == 201, made.text
        eid = made.json()["metadata"]["id"]
        row = c.get(f"/api/time-entries/{eid}").json()["metadata"]
        assert row["started_at"] == "2026-11-01T00:30:00-07:00" and row["ended_at"] == "2026-11-01T01:30:00-07:00"
        c.post(f"/api/time-entries/{eid}/update", json={"ended_at": "2026-11-01T01:20:00", "note": "fixed"})
        row = c.get(f"/api/time-entries/{eid}").json()["metadata"]
        assert row["ended_at"] == "2026-11-01T01:20:00-07:00" and row["started_at"] == "2026-11-01T00:30:00-07:00"


# ------------------------------------------------------------------ the migration

# The shape of the operator's time_entries.csv (2611-18): its header, naive
# local times, notes with commas, quotes and a line break, a running and a
# paused row, an auto row, a row in the hour that came twice whose end reads
# before its start, and one already written with offsets.
REAL_SHAPED = [
    HEADER,
    "tm_58758436,2608-16,00:37,merkhet,operator,2026-08-16T00:37:03,2026-08-16T00:37:10,,0,30,100,,,lll,"
    "time_entry_details/260816-0037__merkhet__operator.md,,",
    "tm_47182473,2608-17,11:29,merkhet,operator,2026-08-17T11:29:15,2026-08-17T14:21:13,,8620,28,100,,,,"
    "time_entry_details/260817-1129__merkhet__operator.md,,",
    'tm_a1b2c3d4,2610-02,09:00,alpha,operator,2026-10-02T09:00:00,2026-10-02T10:15:00,,0,75,10,,sp_x,'
    '"design, then ""review""\nand a second line",,tk_one,',
    "tm_dst00001,2611-01,01:40,alpha,operator,2026-11-01T01:40:00,2026-11-01T01:10:00,,0,30,100,,,,,,",
    "tm_run00001,2611-18,09:00,alpha,operator,2026-11-18T09:00:00,,,0,0,100,,,,,,",
    "tm_pau00001,2611-18,08:00,alpha,operator,2026-11-18T08:00:00,,2026-11-18T08:40:00,120,0,100,,,,,,",
    "tm_aut00001,2611-18,10:00,alpha,operator,2026-11-18T10:00:00,2026-11-18T10:20:00,,0,20,90,,,,,tk_two,auto",
    "tm_new00001,2611-18,11:00,alpha,operator,2026-11-18T11:00:00-08:00,2026-11-18T11:30:00-08:00,,0,30,100,,,,,,",
]


def _write(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ENT.csv
    path.write_text("\n".join(REAL_SHAPED) + "\n", encoding="utf-8")
    return path


def test_the_migration_gives_every_moment_its_offset_and_keeps_every_row(la, tmp_path: Path, backups) -> None:
    path = _write(tmp_path / "data")
    before_bytes = path.read_bytes()
    before = read_rows(path)
    got = migrate_offsets(tmp_path / "data")
    after = read_rows(path)
    assert got["changed"] == 7 and got["rows"] == 8
    assert [r["id"] for r in after] == [r["id"] for r in before]
    for b, a in zip(before, after):
        for col in ENT.columns:
            if col in ("started_at", "ended_at", "paused_at"):
                if b[col]:
                    assert _when(a[col]).replace(tzinfo=None) == datetime.fromisoformat(b[col]).replace(tzinfo=None)
                else:
                    assert a[col] == ""
            else:
                assert a[col] == b[col], (b["id"], col)
    by = {r["id"]: r for r in after}
    assert by["tm_58758436"]["started_at"] == "2026-08-16T00:37:03-07:00"
    assert by["tm_pau00001"]["paused_at"] == "2026-11-18T08:40:00-08:00"
    # The hour that came twice: the end before the start is the second 01:10.
    assert by["tm_dst00001"]["started_at"].endswith("-07:00") and by["tm_dst00001"]["ended_at"].endswith("-08:00")
    assert elapsed_seconds(by["tm_dst00001"]) == 30 * 60
    assert by["tm_new00001"]["started_at"] == "2026-11-18T11:00:00-08:00"
    # The copy first, byte for byte, in the backup folder beside the data root.
    copy = Path(got["backup"])
    assert copy.parent.parent == backups and copy.parent.name.startswith("time-offsets-migration-")
    assert copy.read_bytes() == before_bytes


def test_the_migration_is_idempotent(la, tmp_path: Path, backups) -> None:
    path = _write(tmp_path / "data")
    migrate_offsets(tmp_path / "data")
    once = path.read_bytes()
    again = migrate_offsets(tmp_path / "data")
    assert again["changed"] == 0 and again["backup"] == ""
    assert path.read_bytes() == once
    assert len(list(backups.iterdir())) == 1


def test_no_file_or_nothing_naive_writes_nothing(la, tmp_path: Path, backups) -> None:
    root = tmp_path / "data"
    root.mkdir()
    assert migrate_offsets(root)["changed"] == 0
    path = root / ENT.csv
    path.write_text(HEADER + "\n" + REAL_SHAPED[-1] + "\n", encoding="utf-8")
    stamp = path.stat().st_mtime_ns
    assert migrate_offsets(root)["changed"] == 0
    assert path.stat().st_mtime_ns == stamp and not backups.exists()


def test_a_damaged_file_is_left_as_it_was(la, tmp_path: Path, backups) -> None:
    root = tmp_path / "data"
    root.mkdir()
    path = root / ENT.csv
    path.write_text(HEADER + "\n" + REAL_SHAPED[1] + "\n" + 'tm_bad,2611-18,09:00,alpha,operator,2026-11-18T09:00:00,,,0,0,100,,,"open\n'
                    + REAL_SHAPED[2] + "\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(DamagedFile):
        migrate_offsets(root)
    assert path.read_bytes() == before


def test_the_server_runs_the_migration_on_start_and_says_so(la, tmp_path: Path, backups, caplog) -> None:
    path = _write(tmp_path / "data")
    with caplog.at_level(logging.INFO, logger="sp.server"):
        app = _app(tmp_path / "data")
    assert any("time entries migrated: 7 of 8 rows" in r.getMessage() for r in caplog.records)
    with TestClient(app) as c:
        rows = c.get("/api/time-entries").json()["time_entries"]
    assert len(rows) == 8
    assert all(_when(r["started_at"]) for r in rows)
    with open(path, encoding="utf-8", newline="") as fh:
        assert sum(1 for _ in csv.DictReader(fh)) == 8
