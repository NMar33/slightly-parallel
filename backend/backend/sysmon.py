"""The system monitor: what this machine is doing, and what was unusual.

One background thread samples CPU, memory, disk, network, the connection,
temperature and battery every few seconds (settings ``monitor.*``), and every
process less often. What it keeps, in ``<data root>/monitor/monitor.sqlite``:

- **samples**, in three tiers — every sample for a few hours, minute
  averages and peaks for a week, 15-minute ones for months. Each tier is
  new-in, old-out: past its age a row is gone, and the tier above already
  holds its summary. A day of every sample at 5 s is ~17 000 rows; the whole
  file stays a few megabytes.
- **events** — anything unusual (sysmon_detect.py), one row per episode
  from its start to its end, with its peak and the processes and readings of
  the moment it began. Kept far longer than samples: they are what someone
  comes back to look for.
- **processes** — the heaviest few per scan, so an event or a leak can say
  who.

The monitor folder is left out of the file watcher and of backups: it is
this machine's record, written every few seconds, not project data.

Cost: a sample is a handful of /proc reads (~1 ms); a process scan ~60 ms
for 500 processes, every 30 s by default. The page shows what the monitor
itself costs.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from . import app_settings
from .sysmon_detect import Detectors, Signal

log = logging.getLogger("sp.sysmon")

FOLDER = "monitor"
DB_NAME = "monitor.sqlite"
TIERS = {0: 0, 1: 60, 2: 900}          # tier → bucket seconds (0 = every sample)
SPARK = 180                            # samples kept in memory for the top bar
GAP_SECONDS = 60                       # a pause longer than this is recorded (sleep, stopped server)
CLOSE_AFTER = 30                       # a condition gone this long ends its event

COLUMNS = (
    "cpu", "load1", "mem_used", "mem_total", "mem_pct", "swap_used", "swap_total",
    "disk_pct", "disk_free", "disk_read", "disk_write", "net_rx", "net_tx",
    "ping_ms", "ping_loss", "temp_c", "battery", "self_rss", "self_cpu",
)
# Kept as the bucket's maximum as well as its average: a spike of a few
# seconds (the server at 2.5 GB on a start) must survive the minute and
# quarter-hour tiers.
PEAKS = ("cpu", "mem_pct", "disk_read", "disk_write", "net_rx", "net_tx", "ping_ms", "temp_c", "self_rss")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS samples (
  tier INTEGER NOT NULL, ts REAL NOT NULL,
  {", ".join(f"{c} REAL" for c in COLUMNS)},
  {", ".join(f"{c}_max REAL" for c in PEAKS)},
  n INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS samples_tier_ts ON samples(tier, ts);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, kind TEXT, severity TEXT,
  title TEXT, detail TEXT, metric TEXT, unit TEXT,
  started REAL NOT NULL, ended REAL, peak REAL, context TEXT, seen INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_started ON events(started);
CREATE INDEX IF NOT EXISTS events_seen ON events(seen, severity);
CREATE TABLE IF NOT EXISTS processes (
  ts REAL NOT NULL, pid INTEGER, name TEXT, label TEXT, rss REAL, cpu REAL
);
CREATE INDEX IF NOT EXISTS processes_ts ON processes(ts);
CREATE TABLE IF NOT EXISTS disks (ts REAL NOT NULL, mount TEXT, used REAL, total REAL);
CREATE INDEX IF NOT EXISTS disks_ts ON disks(ts);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

# Mounts that are not disks a person thinks of. Linux: snaps, boot
# partitions, RAM. macOS: the sealed system volume's helpers (Preboot, VM,
# Update, the recovery volume) — they share one container with the data
# volume and repeat its free space. Windows: drives with nothing in them
# (an empty card reader, a DVD drive) and CD-ROMs.
_SKIP_FS = {"squashfs", "tmpfs", "devtmpfs", "overlay", "proc", "sysfs", "vfat", "efivarfs",
            "devfs", "autofs", "nullfs", "cdfs", "udf", ""}
_SKIP_MOUNTS = ("/snap", "/boot", "/run", "/sys", "/proc", "/dev", "/var/snap",
                "/System/Volumes/Preboot", "/System/Volumes/VM", "/System/Volumes/Update",
                "/System/Volumes/xarts", "/System/Volumes/iSCPreboot", "/System/Volumes/Hardware",
                "/Volumes/Recovery", "/private/var/vm")
# Processes that are not programs: Windows's idle counter reports every
# free core as its own CPU time.
_NOT_PROGRAMS = {"System Idle Process", "Idle"}


def real_disks(partitions: Any, usage: Any) -> list[dict[str, Any]]:
    """The disks a person means: one row per physical space, at least 1 GB.

    Two mounts with the same size and the same free space are one disk seen
    twice (macOS shows / and /System/Volumes/Data; Linux bind mounts); the
    first — the shorter mount path — names it."""
    out: list[dict[str, Any]] = []
    seen_dev: set[str] = set()
    seen_space: set[tuple[int, int]] = set()
    for part in sorted(partitions, key=lambda p: len(p.mountpoint)):
        opts = str(getattr(part, "opts", "") or "")
        if part.fstype in _SKIP_FS or part.mountpoint.startswith(_SKIP_MOUNTS) or "cdrom" in opts or part.device in seen_dev:
            continue
        try:
            u = usage(part.mountpoint)
        except (OSError, SystemError):      # an empty drive, a mount that went away, no permission
            continue
        if u.total < 1024 ** 3:
            continue
        space = (int(u.total), int(u.free) // (1024 ** 2))
        if space in seen_space:
            continue
        seen_dev.add(part.device)
        seen_space.add(space)
        out.append({"mount": part.mountpoint, "used": float(u.total - u.free), "total": float(u.total)})
    return out


def db_path(data_root: Path) -> Path:
    return Path(data_root) / FOLDER / DB_NAME


_READY: set[str] = set()


def _add_columns(con: sqlite3.Connection) -> None:
    """A record made before a reading or a peak was added gets its column:
    the table is created once, so a new name in COLUMNS or PEAKS is added here."""
    have = {r[1] for r in con.execute("PRAGMA table_info(samples)")}
    for name in (*COLUMNS, *(c + "_max" for c in PEAKS)):
        if name not in have:
            con.execute(f"ALTER TABLE samples ADD COLUMN {name} REAL")


def connect(data_root: Path) -> sqlite3.Connection:
    p = db_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # The schema and the journal mode once per file and process, not per
    # request: /api/monitor/now is asked every few seconds by every tab.
    if str(p) not in _READY:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        _add_columns(con)
        _READY.add(str(p))
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def connect_read(data_root: Path) -> sqlite3.Connection:
    """For the pages: the record if there is one, else an empty one in
    memory — a page asking must not create the file (a sandbox or a
    read-only data root stays as it was)."""
    if db_path(data_root).exists():
        return connect(data_root)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def settings(data_root: Path) -> dict[str, Any]:
    try:
        values = app_settings.load(Path(data_root))
    except Exception:  # noqa: BLE001 — a bad settings file must not stop the sampler
        values = app_settings.defaults()
    return {k: v for k, v in values.items() if k.startswith("monitor.")}


def _num(cfg: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(cfg.get(f"monitor.{key}", default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Reading the machine
# ---------------------------------------------------------------------------


class Reader:
    """Reads this machine. The rates need the previous reading, so it keeps it."""

    def __init__(self) -> None:
        import psutil
        self.ps = psutil
        self.me = psutil.Process(os.getpid())
        self.me.cpu_percent(None)
        psutil.cpu_percent(None)
        self._io: tuple[float, Any, Any] | None = None
        self._proc_times: dict[int, float] = {}
        self._proc_at = 0.0
        self._disks_at = 0.0
        self._disks: list[dict[str, Any]] = []
        self.ncpu = psutil.cpu_count() or 1
        self._temp_found = 0.0
        self._temp_files: list[Path] = []
        self._temp_slow: set[Path] = set()
        self._temp_last: dict[Path, float] = {}
        self._temp_slow_at = 0.0

    def disks(self, now: float) -> list[dict[str, Any]]:
        # Space changes slowly and statvfs on a network mount can hang: once a minute.
        if now - self._disks_at < 60 and self._disks:
            return self._disks
        try:
            out = real_disks(self.ps.disk_partitions(all=False), self.ps.disk_usage)
        except OSError:
            out = []
        self._disks, self._disks_at = out, now
        return out

    def temperature(self, now: float) -> float | None:
        """The hottest sensor. psutil reads every sensor file each time (~30 ms,
        most of it asking the NVMe drive). On Linux the files are found once
        an hour; a file slow to read (a drive) is read once a minute and its
        last value kept, the rest every sample."""
        if now - self._temp_found > 3600:
            self._temp_found = now
            self._temp_files, self._temp_slow = [], set()
            base = Path("/sys/class/hwmon")
            for f in sorted(base.glob("hwmon*/temp*_input")) if base.is_dir() else []:
                t = time.perf_counter()
                try:
                    self._temp_last[f] = int(f.read_text(encoding="utf-8")) / 1000
                except (OSError, ValueError):
                    continue
                self._temp_files.append(f)
                if time.perf_counter() - t > 0.002:
                    self._temp_slow.add(f)
            self._temp_slow_at = now
        if not self._temp_files:
            try:
                temps = self.ps.sensors_temperatures() or {}
                vals = [t.current for group in temps.values() for t in group if t.current and 0 < t.current < 150]
                return max(vals) if vals else None
            except (AttributeError, OSError):
                return None
        slow_due = now - self._temp_slow_at >= 60
        if slow_due:
            self._temp_slow_at = now
        for f in self._temp_files:
            if f in self._temp_slow and not slow_due:
                continue
            try:
                self._temp_last[f] = int(f.read_text(encoding="utf-8")) / 1000
            except (OSError, ValueError):
                self._temp_last.pop(f, None)
        vals = [v for v in self._temp_last.values() if 0 < v < 150]
        return max(vals) if vals else None

    def sample(self, now: float, cfg: dict[str, Any]) -> dict[str, Any]:
        ps = self.ps
        s: dict[str, Any] = {"ts": now}
        s["cpu"] = ps.cpu_percent(None)
        # os.getloadavg is Linux and macOS only; psutil emulates it on Windows.
        try:
            s["load1"] = float(ps.getloadavg()[0])
        except (AttributeError, OSError):
            pass
        vm = ps.virtual_memory()
        s.update(mem_used=float(vm.total - vm.available), mem_total=float(vm.total), mem_pct=float(vm.percent))
        sw = ps.swap_memory()
        s.update(swap_used=float(sw.used), swap_total=float(sw.total))
        # Either can be missing: Windows can have disk counters switched off
        # (diskperf), and a machine with no disk or no network answers None.
        io_disk = io_net = None
        if cfg.get("monitor.track_disk", True):
            try:
                io_disk = ps.disk_io_counters()
            except (RuntimeError, OSError):
                pass
        if cfg.get("monitor.track_network", True):
            try:
                io_net = ps.net_io_counters()
            except (RuntimeError, OSError):
                pass
        if self._io is not None:
            t0, d0, n0 = self._io
            dt = max(now - t0, 1e-3)
            if io_disk is not None and d0 is not None:
                s["disk_read"] = max(0.0, (io_disk.read_bytes - d0.read_bytes) / dt)
                s["disk_write"] = max(0.0, (io_disk.write_bytes - d0.write_bytes) / dt)
            if io_net is not None and n0 is not None:
                s["net_rx"] = max(0.0, (io_net.bytes_recv - n0.bytes_recv) / dt)
                s["net_tx"] = max(0.0, (io_net.bytes_sent - n0.bytes_sent) / dt)
        self._io = (now, io_disk, io_net)
        if cfg.get("monitor.track_disk", True):
            disks = self.disks(now)
            s["disks"] = disks
            if disks:
                s["disk_pct"] = max(100.0 * d["used"] / d["total"] for d in disks)
                s["disk_free"] = min(d["total"] - d["used"] for d in disks)
        if cfg.get("monitor.track_temperature", True):
            t = self.temperature(now)
            if t is not None:
                s["temp_c"] = t
            try:
                b = ps.sensors_battery()
                if b is not None:
                    s["battery"], s["plugged"] = float(b.percent), bool(b.power_plugged)
            except (AttributeError, OSError):
                pass
        with self.me.oneshot():
            s["self_rss"] = float(self.me.memory_info().rss)
            s["self_cpu"] = self.me.cpu_percent(None) / self.ncpu
        return s

    def processes(self, now: float) -> list[dict[str, Any]]:
        """Every process: memory, and CPU since the last scan (% of the whole machine)."""
        dt = now - self._proc_at if self._proc_at else 0.0
        out: list[dict[str, Any]] = []
        times: dict[int, float] = {}
        for p in self.ps.process_iter(["pid", "name", "memory_info", "cpu_times"]):
            info = p.info
            mi, ct = info.get("memory_info"), info.get("cpu_times")
            # macOS hides other users' processes (None here); Windows's idle
            # process is every free core, not a program.
            if mi is None or ct is None or info["pid"] == 0 or info.get("name") in _NOT_PROGRAMS:
                continue
            total = ct.user + ct.system
            times[info["pid"]] = total
            prev = self._proc_times.get(info["pid"])
            cpu = 100.0 * (total - prev) / dt / self.ncpu if prev is not None and dt > 0 else 0.0
            out.append({"pid": info["pid"], "name": program_name(info.get("name")), "rss": float(mi.rss), "cpu": max(0.0, cpu)})
        self._proc_times, self._proc_at = times, now
        # A readable name for the heavy ones: "node" says little, "node vite" says what.
        heavy = sorted(out, key=lambda x: -x["rss"])[:12] + sorted(out, key=lambda x: -x["cpu"])[:6]
        for p in heavy:
            if "label" in p:
                continue
            p["label"] = label_of(self.ps, p)
        return out

    @staticmethod
    def ping(host: str, timeout: float = 2.0) -> tuple[bool, float]:
        """Open a TCP connection and time it. No ICMP: that needs root."""
        name, _, port = host.rpartition(":")
        if not name:
            name, port = host, "443"
        t = time.perf_counter()
        try:
            with socket.create_connection((name, int(port or 443)), timeout=timeout):
                return True, (time.perf_counter() - t) * 1000
        except (OSError, ValueError):
            return False, (time.perf_counter() - t) * 1000


def program_name(name: str | None) -> str:
    """One name on every system: Windows's "node.exe" is "node"."""
    n = (name or "?").strip()
    return n[:-4] if n.lower().endswith(".exe") else n


_RUNTIMES = ("node", "python", "python3", "pythonw", "py", "java", "javaw", "bash", "sh", "zsh", "ruby",
             "deno", "bun", "powershell", "pwsh", "cmd", "dotnet")


def label_of(ps: Any, p: dict[str, Any]) -> str:
    name = p["name"]
    if p["pid"] == os.getpid():
        return "Slightly Parallel (this server)"
    if name.lower() in _RUNTIMES or name.startswith("python3."):
        try:
            args = [a for a in ps.Process(p["pid"]).cmdline()[1:] if not a.startswith("-")][:2]
            if args:
                return f"{name} {' '.join(Path(a).name for a in args)}"[:60]
        except Exception:  # noqa: BLE001 — the process may be gone or not ours
            pass
    return name


# ---------------------------------------------------------------------------
# The monitor
# ---------------------------------------------------------------------------


class Monitor:
    def __init__(self, data_root: Path, reader: Any = None) -> None:
        self.data_root = Path(data_root)
        self._reader = reader
        self.lock = threading.Lock()
        self.spark: deque[dict[str, Any]] = deque(maxlen=SPARK)
        self.latest: dict[str, Any] | None = None
        self.procs: list[dict[str, Any]] = []
        self.procs_at = 0.0
        self.ping: dict[str, Any] | None = None
        self.cfg = settings(self.data_root)
        self.detect = Detectors(self.cfg)
        self.open: dict[str, dict[str, Any]] = {}   # key → {id, last_seen, peak}
        self.cost_ms: deque[float] = deque(maxlen=60)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._con: sqlite3.Connection | None = None
        self._last_ping = 0.0
        self._last_disk_note = 0.0
        self._last_prune = 0.0
        self._last_rollup = 0.0
        self._last_ts: float | None = None
        self._filling: list[Signal] = []

    # -------------------------------------------------------------- plumbing
    @property
    def con(self) -> sqlite3.Connection:
        if self._con is None:
            self._con = connect(self.data_root)
            self._restore_open()
        return self._con

    @property
    def reader(self) -> Any:
        if self._reader is None:
            self._reader = Reader()
        return self._reader

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sysmon", daemon=True)
            self._thread.start()

    def stop(self, wait: float = 5.0) -> None:
        """Stop sampling, and wait for the thread to end: a monitor left
        running beside its replacement (a data root swap) kept its own
        connection and thread."""
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=wait)
            if self._thread.is_alive():
                log.warning("monitor thread did not stop in %.0f s", wait)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def interval(self) -> float:
        return max(1.0, _num(self.cfg, "interval_seconds", 5))

    def _run(self) -> None:
        try:
            self._loop()
        finally:
            con, self._con = self._con, None
            if con is not None:
                try:
                    con.close()
                except sqlite3.Error:
                    pass

    def _loop(self) -> None:
        cfg_at = 0.0
        while not self._stop.is_set():
            now = time.time()
            if now - cfg_at > 5:
                self.cfg = settings(self.data_root)
                self.detect.cfg = self.cfg
                cfg_at = now
            if not self.cfg.get("monitor.enabled", True):
                self._last_ts = None
                self._stop.wait(5)
                continue
            try:
                self.tick(now)
            except Exception:  # noqa: BLE001 — the monitor must outlive a bad reading
                log.exception("monitor tick failed")
            self._stop.wait(max(0.2, self.interval() - (time.time() - now)))

    # ------------------------------------------------------------------ tick
    def tick(self, now: float) -> dict[str, Any]:
        # CPU this thread spent, not wall time: waiting on the ping costs nothing.
        t0 = time.thread_time()
        cfg = self.cfg
        s = self.reader.sample(now, cfg)
        ping_every = _num(cfg, "ping_seconds", 10)
        if ping_every > 0 and now - self._last_ping >= ping_every:
            host = str(cfg.get("monitor.ping_host") or "1.1.1.1:443")
            ok, ms = self.reader.ping(host)
            s.update(ping_ok=ok, ping_ms=ms if ok else None, ping_loss=0.0 if ok else 1.0, ping_host=host)
            self._last_ping = now
            with self.lock:
                self.ping = {"ok": ok, "ms": round(ms, 1) if ok else None, "at": now, "host": host}
        elif self.ping and now - self.ping["at"] <= 3 * max(ping_every, 1):
            # Between two checks a sample carries the last one, so a chart
            # of the connection is a line and not a scatter of dots.
            s["ping_ms"] = self.ping["ms"]
        self._gap(now)
        signals = self.detect.observe(s, now, self.interval())
        proc_every = _num(cfg, "processes_seconds", 30)
        if proc_every > 0 and now - self.procs_at >= proc_every:
            procs = self.reader.processes(now)
            with self.lock:
                self.procs, self.procs_at = procs, now
            self._store_procs(now, procs)
            signals += self.detect.observe_processes(procs, now)
        # Disk space every 15 minutes: stored for the long view, and the
        # fill forecast re-judged; the forecast holds until the next look.
        if s.get("disks") and now - self._last_disk_note >= 900:
            self._last_disk_note = now
            self.con.executemany("INSERT INTO disks VALUES (?,?,?,?)",
                                 [(now, d["mount"], d["used"], d["total"]) for d in s["disks"]])
            self._filling = self.detect.observe_disks(s["disks"], now)
        signals += self._filling
        self._store_sample(s)
        self._events(signals, now, s)
        if now - self._last_rollup >= 30:
            self._rollup(now)
            self._last_rollup = now
        if now - self._last_prune >= 600:
            self.prune(now)
            self._last_prune = now
        self.con.commit()
        self.cost_ms.append((time.thread_time() - t0) * 1000)
        with self.lock:
            self.latest = s
            self.spark.append({k: s.get(k) for k in ("ts", "cpu", "mem_pct", "net_rx", "net_tx", "ping_ms", "disk_read", "disk_write", "temp_c")})
        self._last_ts = now
        return s

    def _gap(self, now: float) -> None:
        """A long pause between two samples: the machine slept, or the server was off."""
        last = self._last_ts
        if last is None:
            row = self.con.execute("SELECT MAX(ts) AS t FROM samples WHERE tier = 0").fetchone()
            last = row["t"] if row and row["t"] else None
            boot = str(int(self.reader.ps.boot_time())) if hasattr(self.reader, "ps") else ""
            was = self._meta("boot")
            if boot and was and was != boot:
                self._record(Signal("system.boot", "system", "info", "Computer restarted",
                                    "The computer started again.", 0, "", ""), float(boot), float(boot), {})
            if boot:
                self._meta("boot", boot)
        if last is not None and now - last > max(GAP_SECONDS, self.interval() * 6):
            mins = (now - last) / 60
            took = f"{mins:.0f} minutes" if mins < 120 else f"{mins / 60:.1f} hours"
            self._record(Signal("monitor.gap", "gap", "info", "No readings",
                                f"Nothing was read for {took}: the computer slept, or Slightly Parallel was not running.",
                                mins, "min", ""), last, now, {})

    # --------------------------------------------------------------- storing
    def _store_sample(self, s: dict[str, Any]) -> None:
        cols = ["tier", "ts", *COLUMNS]
        self.con.execute(f"INSERT INTO samples ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         [0, s["ts"], *[s.get(c) for c in COLUMNS]])

    def _store_procs(self, now: float, procs: list[dict[str, Any]]) -> None:
        top = {p["pid"]: p for p in sorted(procs, key=lambda x: -x["rss"])[:8]}
        top.update({p["pid"]: p for p in sorted(procs, key=lambda x: -x["cpu"])[:5] if p["cpu"] >= 1})
        self.con.executemany("INSERT INTO processes VALUES (?,?,?,?,?,?)",
                             [(now, p["pid"], p["name"], p.get("label") or p["name"], p["rss"], p["cpu"]) for p in top.values()])

    def _rollup(self, now: float) -> None:
        """Minute rows from samples, 15-minute rows from minute rows — complete buckets only."""
        # Averages of averages weigh each row by its readings (n), or a minute
        # with two readings would count as much as one with twelve.
        plain = ", ".join(f"AVG({c})" for c in COLUMNS)
        weighed = ", ".join(f"SUM({c} * n) / NULLIF(SUM(CASE WHEN {c} IS NULL THEN 0 ELSE n END), 0)" for c in COLUMNS)
        for tier, src, size in ((1, 0, 60), (2, 1, 900)):
            row = self.con.execute("SELECT MAX(ts) AS t FROM samples WHERE tier = ?", (tier,)).fetchone()
            after = row["t"] if row and row["t"] is not None else 0.0
            upto = (now // size) * size
            peak = ", ".join(f"MAX(COALESCE({c}_max, {c}))" for c in PEAKS) if src else ", ".join(f"MAX({c})" for c in PEAKS)
            self.con.execute(
                f"INSERT INTO samples (tier, ts, {', '.join(COLUMNS)}, {', '.join(c + '_max' for c in PEAKS)}, n) "
                f"SELECT ?, CAST(ts / ? AS INTEGER) * ?, {weighed if src else plain}, {peak}, SUM(n) FROM samples "
                f"WHERE tier = ? AND ts >= ? AND ts < ? GROUP BY CAST(ts / ? AS INTEGER)",
                (tier, size, size, src, after + size if after else 0.0, upto, size),
            )

    def prune(self, now: float) -> None:
        cfg = self.cfg
        keep = {0: _num(cfg, "keep_raw_hours", 6) * 3600, 1: _num(cfg, "keep_minutes_days", 7) * 86400,
                2: _num(cfg, "keep_quarters_days", 180) * 86400}
        for tier, age in keep.items():
            self.con.execute("DELETE FROM samples WHERE tier = ? AND ts < ?", (tier, now - age))
        self.con.execute("DELETE FROM processes WHERE ts < ?", (now - keep[1],))
        self.con.execute("DELETE FROM disks WHERE ts < ?", (now - keep[2],))
        events_age = _num(cfg, "keep_events_days", 730) * 86400
        self.con.execute("DELETE FROM events WHERE ended IS NOT NULL AND ended < ?", (now - events_age,))
        # A hard ceiling too: a machine in trouble for months must not grow the file without end.
        self.con.execute("DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY started DESC LIMIT -1 OFFSET 20000)")

    # ---------------------------------------------------------------- events
    def _meta(self, k: str, v: str | None = None) -> str | None:
        if v is None:
            row = self.con.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
            return row["v"] if row else None
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, v))
        return v

    def _restore_open(self) -> None:
        """Events left open by a stopped server stay open until their condition is seen again, or closes."""
        assert self._con is not None
        # Last seen at the last reading before the stop, not now: an event
        # closing later must not stretch over the hours the server was off.
        row = self._con.execute("SELECT MAX(ts) AS t FROM samples WHERE tier = 0").fetchone()
        last = float(row["t"]) if row and row["t"] else time.time()
        for r in self._con.execute("SELECT id, key, peak, started FROM events WHERE ended IS NULL"):
            self.open[r["key"]] = {"id": r["id"], "last": max(last, float(r["started"] or 0)), "peak": r["peak"], "started": r["started"]}

    def _context(self, s: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            procs = list(self.procs)
        pick = lambda key: [  # noqa: E731
            {"pid": p["pid"], "name": p.get("label") or p["name"], "rss": p["rss"], "cpu": round(p["cpu"], 1)}
            for p in sorted(procs, key=lambda x: -x[key])[:5]]
        reading = {k: s.get(k) for k in ("cpu", "mem_pct", "swap_used", "disk_pct", "net_rx", "net_tx", "ping_ms", "temp_c", "load1")}
        return {"reading": reading, "top_cpu": pick("cpu"), "top_memory": pick("rss")}

    def _record(self, sig: Signal, started: float, ended: float | None, context: dict[str, Any]) -> int:
        cur = self.con.execute(
            "INSERT INTO events (key, kind, severity, title, detail, metric, unit, started, ended, peak, context) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sig.key, sig.kind, sig.severity, sig.title, sig.detail, sig.metric, sig.unit, started, ended,
             sig.value, json.dumps(context)),
        )
        return int(cur.lastrowid or 0)

    def _events(self, signals: list[Signal], now: float, s: dict[str, Any]) -> None:
        active = {x.key: x for x in signals}
        for key, sig in active.items():
            cur = self.open.get(key)
            if cur is None:
                # The context names who: a scan up to 30 s old can miss the
                # process that started it, so a new event reads them now.
                if sig.kind not in ("gap", "system", "leak") and hasattr(self.reader, "processes") \
                        and now - self.procs_at > 2 and _num(self.cfg, "processes_seconds", 30) > 0:
                    fresh = self.reader.processes(now)
                    with self.lock:
                        self.procs, self.procs_at = fresh, now
                eid = self._record(sig, now, None, self._context(s))
                self.open[key] = {"id": eid, "last": now, "peak": sig.value, "started": now}
                log.info("monitor: %s — %s", sig.title, sig.detail)
                continue
            cur["last"] = now
            lower_is_worse = sig.unit in ("% free", "hours")
            if cur["peak"] is None or (sig.value < cur["peak"] if lower_is_worse else sig.value > cur["peak"]):
                cur["peak"] = sig.value
            self.con.execute("UPDATE events SET peak = ?, detail = ?, severity = CASE WHEN severity = 'critical' "
                             "THEN 'critical' ELSE ? END WHERE id = ?", (cur["peak"], sig.detail, sig.severity, cur["id"]))
        for key in [k for k in self.open if k not in active]:
            cur = self.open[key]
            # A leak is judged at each process scan, not each sample: give it
            # longer before calling it over.
            # The connection is judged at each ping: two pings without it, not 30 s,
            # or a minute's ping splits one outage into an event a minute.
            wait = (max(CLOSE_AFTER, 3 * _num(self.cfg, "processes_seconds", 30)) if key.startswith("leak:")
                    else max(CLOSE_AFTER, 2 * _num(self.cfg, "ping_seconds", 10)) if key.startswith("net.")
                    else CLOSE_AFTER)
            if now - cur["last"] >= wait:
                self.con.execute("UPDATE events SET ended = ? WHERE id = ?", (cur["last"], cur["id"]))
                del self.open[key]

    # --------------------------------------------------------------- reading
    def cost(self) -> dict[str, float]:
        ms = sum(self.cost_ms) / len(self.cost_ms) if self.cost_ms else 0.0
        return {"ms_per_sample": round(ms, 2), "cpu_pct": round(100 * ms / 1000 / self.interval(), 3)}


def os_name() -> str:
    """The system as its owner calls it: macOS 15.1, not Darwin 24.1."""
    system = platform.system()
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    if system == "Windows":
        return f"Windows {platform.release()}"
    return f"{system} {platform.release()}"


_HOST: tuple[float, dict[str, Any]] = (0.0, {})


def host_facts() -> dict[str, Any]:
    """The machine's name, system, CPUs and memory — asked every few seconds, read once a minute."""
    global _HOST
    if time.time() - _HOST[0] < 60 and _HOST[1]:
        return _HOST[1]
    _HOST = (time.time(), _host_facts())
    return _HOST[1]


def _host_facts() -> dict[str, Any]:
    try:
        import psutil
        boot = psutil.boot_time()
        cpus, logical = psutil.cpu_count(logical=False), psutil.cpu_count()
        mem = psutil.virtual_memory().total
    except Exception:  # noqa: BLE001
        boot, cpus, logical, mem = 0, 0, 0, 0
    return {"name": platform.node(), "os": os_name(), "cpus": cpus,
            "threads": logical, "memory": mem, "boot": boot, "python": platform.python_version()}
