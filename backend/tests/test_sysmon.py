"""The system monitor: detectors on made-up readings, the store on a fake machine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend import sysmon
from backend.server import create_app
from backend.sysmon_detect import MB, Detectors, fit

GB = 1024 * MB


def _signals(det: Detectors, readings: list[dict[str, Any]], step: float = 5.0) -> list[set[str]]:
    return [{x.key for x in det.observe(r, 1000.0 + i * step, step)} for i, r in enumerate(readings)]


# ------------------------------------------------------------------ detectors


def test_fit_finds_a_straight_line() -> None:
    slope, r2 = fit([(t, 3 * t + 1) for t in range(10)])
    assert abs(slope - 3) < 1e-9 and r2 > 0.999


def test_cpu_must_stay_high_for_two_minutes() -> None:
    det = Detectors({"monitor.cpu_alert_pct": 90})
    seen = _signals(det, [{"cpu": 99.0}] * 30)            # 150 s at 5 s
    assert "cpu.high" not in seen[20] and "cpu.high" in seen[25]
    assert "cpu.high" not in _signals(det, [{"cpu": 10.0}])[0]


def test_disk_low_names_the_disk() -> None:
    det = Detectors({"monitor.disk_alert_pct": 10})
    got = det.observe({"disks": [{"mount": "/", "used": 95 * GB, "total": 100 * GB}]}, 0, 5)
    assert [x.key for x in got] == ["disk.low:/"] and got[0].severity == "warning"


def test_unusual_only_after_learning_and_above_the_floor() -> None:
    det = Detectors({"monitor.sensitivity": "normal"})
    calm = [{"net_rx": 100_000.0 + (i % 7) * 5_000} for i in range(80)]
    assert not any(_signals(det, calm)[-1])
    spike = _signals(det, [{"net_rx": 60.0 * MB}] * 4)
    assert "unusual.net_rx" in spike[-1]
    # An idle machine going from tiny to small is not news.
    det2 = Detectors()
    _signals(det2, [{"net_rx": 1000.0}] * 80)
    assert not any(_signals(det2, [{"net_rx": 500_000.0}] * 4)[-1])


def test_no_connection_after_three_failures() -> None:
    det = Detectors()
    seen = _signals(det, [{"ping_ok": False}] * 3)
    assert "net.down" not in seen[1] and "net.down" in seen[2]
    assert "net.down" not in _signals(det, [{"ping_ok": True, "ping_ms": 20.0}])[0]


def test_a_steady_climb_is_a_leak_and_a_jump_is_not() -> None:
    det = Detectors({"monitor.leak_mb_per_hour": 50, "monitor.leak_window_minutes": 60})
    t0, got = 0.0, []
    for i in range(0, 70):                         # a minute apart, +3 MB a minute = 180 MB/h
        got = det.observe_processes([{"pid": 7, "name": "node", "rss": 200 * MB + i * 3 * MB}], t0 + i * 60)
    assert [x.key for x in got] == ["leak:node:7"]
    det2 = Detectors({"monitor.leak_mb_per_hour": 50, "monitor.leak_window_minutes": 60})
    for i in range(0, 70):                         # flat, then one jump: a tab opened, not a leak
        got = det2.observe_processes([{"pid": 8, "name": "firefox", "rss": (300 if i < 35 else 600) * MB}], t0 + i * 60)
    assert got == []


def test_a_disk_filling_fast_is_forecast() -> None:
    det = Detectors()
    got = []
    for i in range(30):                            # 15-minute notes, +2 GB each, 20 GB left at the end
        got = det.observe_disks([{"mount": "/", "used": (20 + 2 * i) * GB, "total": 98 * GB}], i * 900)
    assert got and got[0].key == "disk.filling:/"


# ---------------------------------------------------------------- the monitor


class FakeReader:
    """A machine that says what the test wants."""

    def __init__(self) -> None:
        self.cpu, self.ping_ok, self.procs = 5.0, True, []

    def sample(self, now: float, cfg: dict[str, Any]) -> dict[str, Any]:
        return {"ts": now, "cpu": self.cpu, "mem_used": 4 * GB, "mem_total": 16 * GB, "mem_pct": 25.0,
                "swap_used": 0.0, "net_rx": 1000.0, "net_tx": 500.0,
                "disks": [{"mount": "/", "used": 40 * GB, "total": 100 * GB}], "disk_pct": 40.0}

    def ping(self, host: str) -> tuple[bool, float]:
        return self.ping_ok, 12.0

    def processes(self, now: float) -> list[dict[str, Any]]:
        return self.procs


def _monitor(root: Path, **cfg: Any) -> tuple[sysmon.Monitor, FakeReader]:
    fake = FakeReader()
    m = sysmon.Monitor(root, reader=fake)
    m.cfg = {"monitor.enabled": True, "monitor.interval_seconds": "5", "monitor.ping_seconds": "5",
             "monitor.processes_seconds": "30", **cfg}
    m.detect.cfg = m.cfg
    return m, fake


def test_an_episode_is_one_event_from_start_to_end(tmp_path: Path) -> None:
    m, fake = _monitor(tmp_path)
    t = 1_000_000.0
    for i in range(10):
        m.tick(t + i * 5)
    fake.ping_ok = False
    for i in range(10, 20):
        m.tick(t + i * 5)
    fake.ping_ok = True
    for i in range(20, 40):
        m.tick(t + i * 5)
    rows = [dict(r) for r in m.con.execute("SELECT key, started, ended FROM events WHERE key = 'net.down'")]
    assert len(rows) == 1 and rows[0]["ended"] is not None
    ctx = m.con.execute("SELECT context FROM events").fetchone()["context"]
    assert '"reading"' in ctx


def test_samples_roll_up_into_minutes_and_old_ones_go(tmp_path: Path) -> None:
    m, _ = _monitor(tmp_path, **{"monitor.keep_raw_hours": 1})
    t = 1_000_020.0
    for i in range(0, 60 * 12 * 2, 1):                 # two hours at 5 s ≈ 1440 samples
        m.tick(t + i * 5)
    tiers = dict(m.con.execute("SELECT tier, COUNT(*) FROM samples GROUP BY tier").fetchall())
    assert 110 <= tiers[1] <= 121                       # a row per complete minute
    m.prune(t + 1440 * 5)
    oldest = m.con.execute("SELECT MIN(ts) FROM samples WHERE tier = 0").fetchone()[0]
    assert oldest >= t + 1440 * 5 - 3600


def test_a_long_pause_is_recorded(tmp_path: Path) -> None:
    m, _ = _monitor(tmp_path)
    m.tick(2_000_000.0)
    m.tick(2_000_005.0)
    m.tick(2_003_600.0)                                 # an hour later: the laptop slept
    got = m.con.execute("SELECT kind, title FROM events").fetchall()
    assert [tuple(r) for r in got] == [("gap", "No readings")]


def test_the_pages_read_the_record(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        m, fake = _monitor(root)
        c.app.state.monitor = m
        import time
        now = time.time()
        fake.ping_ok = False
        for i in range(6):
            m.tick(now - 30 + i * 5)
        now_ = c.get("/api/monitor/now").json()
        assert now_["sample"]["cpu"] == 5.0 and now_["open"][0]["key"] == "net.down"
        assert len(now_["spark"]) == 6 and now_["unseen"] == 1
        series = c.get("/api/monitor/series?range=15m").json()
        assert series["tier"] == 0 and series["points"] == 6 and len(series["events"]) == 1
        ev = c.get("/api/monitor/events?days=7").json()
        assert ev["total"] == 1 and list(ev["days"].values())[0]["worst"] == "critical"
        eid = ev["events"][0]["id"]
        assert c.get(f"/api/monitor/events/{eid}").json()["event"]["title"] == "No connection"
        assert c.post(f"/api/monitor/events/{eid}/seen", json={}).json()["seen"] == 1
        assert c.post("/api/monitor/clear", json={"what": "nope"}).status_code == 422
        assert c.post("/api/monitor/clear", json={"what": "samples", "actor": "cc-x"}).status_code == 422
        assert c.get("/api/monitor/storage").json()["tiers"]["0"]["rows"] == 6
        assert c.get("/api/monitor/series?range=5y").status_code == 422


# ------------------------------------------------------ other operating systems

from collections import namedtuple  # noqa: E402

Part = namedtuple("Part", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")


def test_macos_system_volumes_count_once() -> None:
    parts = [
        Part("/dev/disk3s1s1", "/", "apfs", "ro,local"),
        Part("/dev/disk3s6", "/System/Volumes/VM", "apfs", "rw"),
        Part("/dev/disk3s2", "/System/Volumes/Preboot", "apfs", "rw"),
        Part("/dev/disk3s5", "/System/Volumes/Data", "apfs", "rw"),
        Part("/dev/disk5s1", "/Volumes/Backup", "apfs", "rw"),
    ]
    one_container = Usage(500 * GB, 420 * GB, 80 * GB, 84.0)
    usage = {"/": one_container, "/System/Volumes/Data": Usage(500 * GB, 300 * GB, 80 * GB, 60.0),
             "/Volumes/Backup": Usage(2000 * GB, 100 * GB, 1900 * GB, 5.0)}
    got = sysmon.real_disks(parts, lambda m: usage.get(m, one_container))
    assert [d["mount"] for d in got] == ["/", "/Volumes/Backup"]
    assert got[0]["total"] - got[0]["used"] == 80 * GB   # free space is what counts, as the system reports it


def test_windows_drives_skip_the_empty_and_the_dvd() -> None:
    parts = [
        Part("C:\\", "C:\\", "NTFS", "rw,fixed"),
        Part("D:\\", "D:\\", "", "cdrom"),
        Part("E:\\", "E:\\", "FAT32", "rw,removable"),
        Part("F:\\", "F:\\", "exFAT", "rw,removable"),
    ]

    def usage(m: str) -> Usage:
        if m == "E:\\":
            raise PermissionError("the device is not ready")
        return Usage(1000 * GB, 400 * GB, 600 * GB, 40.0) if m == "C:\\" else Usage(64 * GB, 1 * GB, 63 * GB, 2.0)

    assert [d["mount"] for d in sysmon.real_disks(parts, usage)] == ["C:\\", "F:\\"]


def test_program_names_are_the_same_everywhere() -> None:
    assert sysmon.program_name("node.exe") == "node"
    assert sysmon.program_name("Code.EXE") == "Code"
    assert sysmon.program_name("firefox") == "firefox"
    assert sysmon.program_name(None) == "?"


def test_hidden_and_idle_processes_are_left_out() -> None:
    PI = namedtuple("PI", "info")
    Mem = namedtuple("Mem", "rss")
    Times = namedtuple("Times", "user system")

    class FakePs:
        @staticmethod
        def process_iter(attrs):  # noqa: ARG004
            return [
                PI({"pid": 0, "name": "System Idle Process", "memory_info": Mem(0), "cpu_times": Times(9e6, 0)}),
                PI({"pid": 4, "name": "WindowsTerminal.exe", "memory_info": Mem(90 * MB), "cpu_times": Times(3, 1)}),
                PI({"pid": 9, "name": "loginwindow", "memory_info": None, "cpu_times": None}),   # macOS: not ours
            ]

    r = sysmon.Reader.__new__(sysmon.Reader)
    r.ps, r.ncpu, r._proc_times, r._proc_at = FakePs, 8, {}, 0.0
    got = r.processes(100.0)
    assert [(p["pid"], p["name"]) for p in got] == [(4, "WindowsTerminal")]


def test_one_outage_is_one_event_with_a_slow_ping(tmp_path: Path) -> None:
    m, fake = _monitor(tmp_path, **{"monitor.ping_seconds": "60"})
    t = 3_000_000.0
    fake.ping_ok = False
    for i in range(0, 60 * 5, 5):                      # five minutes down, pinged once a minute
        m.tick(t + i)
    n = m.con.execute("SELECT COUNT(*) FROM events WHERE key = 'net.down'").fetchone()[0]
    assert n == 1


def test_an_event_left_open_by_a_stop_ends_at_the_last_reading(tmp_path: Path) -> None:
    m, fake = _monitor(tmp_path)
    t = 4_000_000.0
    fake.ping_ok = False
    for i in range(0, 60, 5):
        m.tick(t + i)
    m.con.commit()
    m2, fake2 = _monitor(tmp_path)                     # the server comes back an hour later
    fake2.ping_ok = True
    for i in range(0, 120, 5):
        m2.tick(t + 3600 + i)
    ended = m2.con.execute("SELECT ended FROM events WHERE key = 'net.down'").fetchone()[0]
    assert ended is not None and ended < t + 120


def test_a_record_from_before_the_server_memory_peak_gets_its_column_and_keeps_spikes(tmp_path) -> None:
    """The server's memory is kept with its peak per bucket, so a start-up
    spike survives the minute tier; a record made before has the column added."""
    import sqlite3
    from backend import sysmon
    db = sysmon.db_path(tmp_path)
    db.parent.mkdir(parents=True)
    old = sqlite3.connect(db)
    old.execute("CREATE TABLE samples (tier INTEGER NOT NULL, ts REAL NOT NULL, cpu REAL, self_rss REAL, n INTEGER DEFAULT 1)")
    old.commit(); old.close()
    sysmon._READY.discard(str(db))
    con = sysmon.connect(tmp_path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    assert {"self_rss_max", "mem_pct", "cpu_max"} <= cols
    con.execute("DELETE FROM samples")
    for i, rss in enumerate((200e6, 2500e6, 210e6)):          # one spike within a minute
        con.execute("INSERT INTO samples (tier, ts, self_rss) VALUES (0, ?, ?)", (60.0 + i * 5, rss))
    m = sysmon.Monitor.__new__(sysmon.Monitor)
    m._con = con
    m._rollup(200.0)
    row = con.execute("SELECT self_rss, self_rss_max FROM samples WHERE tier = 1").fetchone()
    assert row["self_rss_max"] == 2500e6 and row["self_rss"] < 1000e6
