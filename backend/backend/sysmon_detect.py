"""What counts as unusual — the system monitor's detectors, with no I/O.

The sampler (sysmon.py) hands every reading to ``Detectors.observe`` and
every process scan to ``Detectors.observe_processes``. Each returns the
conditions that hold right now, as ``Signal``s keyed by what they are about
(``cpu.high``, ``leak:node:4121``). The sampler turns a key that starts
holding into an event, keeps its peak while it holds, and closes it when it
stops — so a ten-minute spike is one event, not a hundred and twenty.

Four kinds of rule:

- **limits** the operator set: CPU, memory, disk space, temperature, each
  held for a while before it counts (a compile hitting 100 % for five
  seconds is not news);
- **unusual for this machine**: a slow-moving baseline (mean and spread) of
  CPU, network and disk traffic, and a reading far outside it — how far is
  the sensitivity setting;
- **the connection**: no answer three times running, or answers far slower
  than usual;
- **trends**: a process whose memory keeps growing for the whole leak
  window (a straight, steady climb — not one jump), swap filling, a disk on
  course to be full within three days.

Pure: time is passed in, nothing is read from the machine. The tests drive
it with made-up readings.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

MB = 1024 * 1024

# Sensitivity → how many spreads (standard deviations) from the baseline a
# reading must be to count as unusual.
Z_LIMIT = {"low": 6.0, "normal": 4.5, "high": 3.5}

# Below these a reading is never unusual, whatever the baseline: an idle
# machine's network going from 2 KB/s to 40 KB/s is twenty spreads out and
# of no interest to anyone.
FLOORS = {"cpu": 40.0, "net_rx": 2 * MB, "net_tx": 2 * MB, "disk_read": 30 * MB, "disk_write": 30 * MB}
UNUSUAL_WORDS = {
    "cpu": ("CPU", "%"), "net_rx": ("download", "B/s"), "net_tx": ("upload", "B/s"),
    "disk_read": ("disk reads", "B/s"), "disk_write": ("disk writes", "B/s"),
}
# The baseline learns over about this long, and needs this many readings
# before it judges anything.
BASELINE_SECONDS = 1800.0
WARMUP_SAMPLES = 60


@dataclass
class Signal:
    """A condition that holds right now."""
    key: str
    kind: str            # cpu · memory · disk · network · temperature · leak · swap · unusual · battery
    severity: str        # info · warning · critical
    title: str
    detail: str
    value: float = 0.0   # the reading behind it — the event keeps the peak
    unit: str = ""
    metric: str = ""     # which series to draw beside it (cpu, mem_pct, ping_ms …)


@dataclass
class _Baseline:
    mean: float = 0.0
    var: float = 0.0
    n: int = 0

    def z(self, x: float) -> float:
        sd = math.sqrt(max(self.var, 1e-9))
        return (x - self.mean) / sd if self.n >= WARMUP_SAMPLES else 0.0

    def learn(self, x: float, alpha: float) -> None:
        if self.n == 0:
            self.mean, self.var = x, 0.0
        else:
            d = x - self.mean
            self.mean += alpha * d
            self.var = (1 - alpha) * (self.var + alpha * d * d)
        self.n += 1


@dataclass
class _Held:
    """A condition must hold this long before it is a signal."""
    since: float | None = None

    def hold(self, on: bool, now: float, seconds: float) -> bool:
        if not on:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        return now - self.since >= seconds


def fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares slope (per second) and r² of (t, y) points."""
    n = len(points)
    if n < 3:
        return 0.0, 0.0
    mt = sum(t for t, _ in points) / n
    my = sum(y for _, y in points) / n
    stt = sum((t - mt) ** 2 for t, _ in points)
    syy = sum((y - my) ** 2 for _, y in points)
    sty = sum((t - mt) * (y - my) for t, y in points)
    if stt <= 0 or syy <= 0:
        return 0.0, 0.0
    slope = sty / stt
    return slope, (sty * sty) / (stt * syy)


def human_bytes(b: float) -> str:
    b = float(b or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024 or unit == "TB":
            return f"{b:.0f} {unit}" if unit in ("B", "KB") else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


@dataclass
class Detectors:
    cfg: dict[str, Any] = field(default_factory=dict)
    _held: dict[str, _Held] = field(default_factory=dict)
    _base: dict[str, _Baseline] = field(default_factory=dict)
    _ping_fail: int = 0
    _ping_base: _Baseline = field(default_factory=_Baseline)
    _ping_slow: int = 0
    _swap: deque = field(default_factory=lambda: deque(maxlen=4000))
    _rss: dict[str, deque] = field(default_factory=dict)
    _disk_hist: dict[str, deque] = field(default_factory=dict)

    def _h(self, key: str) -> _Held:
        return self._held.setdefault(key, _Held())

    def c(self, key: str, default: Any) -> Any:
        v = self.cfg.get(f"monitor.{key}", default)
        try:
            return type(default)(v)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------ sample
    def observe(self, s: dict[str, Any], now: float, interval: float) -> list[Signal]:
        out: list[Signal] = []
        cpu = s.get("cpu")
        if cpu is not None:
            limit = self.c("cpu_alert_pct", 90)
            if self._h("cpu.high").hold(cpu >= limit, now, 120):
                out.append(Signal("cpu.high", "cpu", "warning", "CPU busy",
                                  f"CPU at or above {limit} % for more than 2 minutes.", cpu, "%", "cpu"))
        mem = s.get("mem_pct")
        if mem is not None:
            limit = self.c("memory_alert_pct", 90)
            if self._h("mem.high").hold(mem >= limit, now, 60):
                sev = "critical" if mem >= 97 else "warning"
                out.append(Signal("mem.high", "memory", sev, "Memory almost full",
                                  f"{mem:.0f} % of memory in use (alert at {limit} %).", mem, "%", "mem_pct"))
        # Swap filling fast: more than 512 MB in ten minutes.
        swap = s.get("swap_used")
        if swap is not None:
            self._swap.append((now, swap))
            old = next((v for t, v in self._swap if now - t <= 600), swap)
            if swap - old > 512 * MB:
                out.append(Signal("swap.growing", "swap", "warning", "Swapping to disk",
                                  f"Swap grew by {human_bytes(swap - old)} in 10 minutes: memory is short.",
                                  swap, "B", "swap_used"))
        for d in s.get("disks") or []:
            free_pct = 100.0 * (1 - d["used"] / d["total"]) if d.get("total") else 100.0
            limit = self.c("disk_alert_pct", 10)
            if free_pct < limit:
                sev = "critical" if free_pct < limit / 2 or d["total"] - d["used"] < 2 * 1024 * MB else "warning"
                out.append(Signal(f"disk.low:{d['mount']}", "disk", sev, f"Disk {d['mount']} almost full",
                                  f"{human_bytes(d['total'] - d['used'])} free ({free_pct:.1f} %).",
                                  free_pct, "% free", "disk_pct"))
        temp = s.get("temp_c")
        if temp is not None:
            limit = self.c("temp_alert_c", 90)
            if self._h("temp.high").hold(temp >= limit, now, 60):
                out.append(Signal("temp.high", "temperature", "warning", "Running hot",
                                  f"{temp:.0f} °C for more than a minute (alert at {limit} °C).", temp, "°C", "temp_c"))
        bat = s.get("battery")
        if bat is not None and not s.get("plugged") and bat <= 10:
            out.append(Signal("battery.low", "battery", "warning", "Battery low",
                              f"{bat:.0f} % left, not plugged in.", bat, "%", "battery"))
        out += self._unusual(s, now, interval)
        out += self._ping(s)
        return out

    def _unusual(self, s: dict[str, Any], now: float, interval: float) -> list[Signal]:
        out: list[Signal] = []
        limit = Z_LIMIT.get(str(self.cfg.get("monitor.sensitivity", "normal")), 4.5)
        alpha = min(0.5, max(interval, 1.0) / BASELINE_SECONDS)
        for metric, floor in FLOORS.items():
            x = s.get(metric)
            if x is None:
                continue
            b = self._base.setdefault(metric, _Baseline())
            z = b.z(x)
            odd = z >= limit and x >= floor
            # A long run of odd readings is learned slowly, so it stays odd
            # for a while instead of becoming the new normal at once.
            b.learn(x, alpha / 10 if odd else alpha)
            if self._h(f"unusual.{metric}").hold(odd, now, max(interval * 2, 10)):
                word, unit = UNUSUAL_WORDS[metric]
                shown = f"{x:.0f} %" if unit == "%" else f"{human_bytes(x)}/s"
                usual = f"{b.mean:.0f} %" if unit == "%" else f"{human_bytes(b.mean)}/s"
                out.append(Signal(f"unusual.{metric}", "unusual", "info", f"Unusual {word}",
                                  f"{word[0].upper() + word[1:]} at {shown}; usually about {usual}.", x, unit, metric))
        return out

    def _ping(self, s: dict[str, Any]) -> list[Signal]:
        if "ping_ok" not in s:
            return []
        out: list[Signal] = []
        if not s["ping_ok"]:
            self._ping_fail += 1
        else:
            self._ping_fail = 0
            ms = float(s.get("ping_ms") or 0)
            base = self._ping_base
            slow = base.n >= 20 and ms > max(base.mean * 3, base.mean + 80)
            base.learn(ms, 0.02 if slow else 0.1)
            self._ping_slow = self._ping_slow + 1 if slow else 0
            if self._ping_slow >= 3:
                out.append(Signal("net.slow", "network", "warning", "Slow connection",
                                  f"Answers take {ms:.0f} ms; usually about {base.mean:.0f} ms.", ms, "ms", "ping_ms"))
        if self._ping_fail >= 3:
            out.append(Signal("net.down", "network", "critical", "No connection",
                              f"{s.get('ping_host') or 'The ping host'} has not answered {self._ping_fail} times running.",
                              float(self._ping_fail), "tries", "ping_ms"))
        return out

    # --------------------------------------------------------------- processes
    def observe_processes(self, procs: Iterable[dict[str, Any]], now: float) -> list[Signal]:
        """Possible leaks: a process whose memory rose steadily for the whole window."""
        window = self.c("leak_window_minutes", 60) * 60.0
        per_hour = self.c("leak_mb_per_hour", 50) * MB
        seen: set[str] = set()
        out: list[Signal] = []
        for p in procs:
            if p.get("rss", 0) < 50 * MB:
                continue
            key = f"{p['name']}:{p['pid']}"
            seen.add(key)
            q = self._rss.setdefault(key, deque(maxlen=720))
            q.append((now, float(p["rss"])))
            while q and now - q[0][0] > window * 1.5:
                q.popleft()
            pts = [(t, y) for t, y in q if now - t <= window]
            if len(pts) < 8 or pts[-1][0] - pts[0][0] < window * 0.9:
                continue
            slope, r2 = fit(pts)
            grew = pts[-1][1] - pts[0][1]
            drops = sum(1 for (_, a), (_, b) in zip(pts, pts[1:]) if b < a * 0.99)
            if slope * 3600 >= per_hour and r2 >= 0.85 and grew >= 50 * MB and drops <= len(pts) // 5:
                label = p.get("label") or p["name"]
                out.append(Signal(f"leak:{key}", "leak", "warning", f"Possible memory leak: {label}",
                                  f"{label} (pid {p['pid']}) grew from {human_bytes(pts[0][1])} to "
                                  f"{human_bytes(pts[-1][1])} in {int((pts[-1][0] - pts[0][0]) / 60)} minutes, "
                                  f"steadily: +{slope * 3600 / MB:.0f} MB an hour.",
                                  pts[-1][1], "B", "rss"))
        for gone in set(self._rss) - seen:
            del self._rss[gone]
        return out

    # ------------------------------------------------------------------- disks
    def observe_disks(self, disks: Iterable[dict[str, Any]], now: float) -> list[Signal]:
        """A disk on course to be full within three days, from its last day of use."""
        out: list[Signal] = []
        for d in disks:
            q = self._disk_hist.setdefault(d["mount"], deque(maxlen=200))
            q.append((now, float(d["used"])))
            while q and now - q[0][0] > 86400:
                q.popleft()
            if len(q) < 6 or q[-1][0] - q[0][0] < 6 * 3600:
                continue
            slope, r2 = fit(list(q))
            if slope <= 0 or r2 < 0.7:
                continue
            left = (d["total"] - d["used"]) / slope
            if left < 3 * 86400:
                hours = left / 3600
                when = f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.1f} days"
                out.append(Signal(f"disk.filling:{d['mount']}", "disk", "warning", f"Disk {d['mount']} filling up",
                                  f"At the pace of the last day it is full in about {when} "
                                  f"(+{human_bytes(slope * 3600)} an hour).", hours, "hours", "disk_pct"))
        return out
