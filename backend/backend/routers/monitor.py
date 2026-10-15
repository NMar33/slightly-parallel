"""The system monitor's pages (sysmon.py).

- ``GET /api/monitor/now`` — the latest reading, the last few minutes for
  the top bar's small charts, the events still going on, the connection,
  and what the monitor itself costs. Cheap: read from memory.
- ``GET /api/monitor/series?range=1h`` (or ``from``/``to``) — every
  measure over a span, about 400 points whatever the span, from the finest
  tier that still holds it. Each point is an average; ``*_max`` the peak.
- ``GET /api/monitor/events`` — what was unusual, newest first, filtered;
  with ``days``: per day, how many and the worst.
- ``GET /api/monitor/events/{id}`` — one event with the readings and
  processes of its moment.
- ``GET /api/monitor/processes`` — the heaviest processes now.
- ``GET /api/monitor/storage`` — how much the record holds.
- ``POST /api/monitor/events/{id}/seen`` · ``POST /api/monitor/events/seen``
  · ``POST /api/monitor/clear`` — the operator's.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path as PathParam, Query, Request

from .. import sysmon
from ..db import ViewStore
from .deps import get_store, not_found, operator_only

router = APIRouter()

RANGES = {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000,
          "90d": 7776000, "1y": 31536000}
TARGET_POINTS = 400
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _mon(request: Request) -> sysmon.Monitor | None:
    return getattr(request.app.state, "monitor", None)


def _con(store: ViewStore):
    return sysmon.connect_read(store.data_root)


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    if "context" in d:
        try:
            d["context"] = json.loads(d["context"] or "{}")
        except ValueError:
            d["context"] = {}
    return d


@router.get("/api/monitor/now")
def monitor_now(request: Request, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    cfg = sysmon.settings(store.data_root)
    mon = _mon(request)
    out: dict[str, Any] = {
        "enabled": bool(cfg.get("monitor.enabled", True)),
        "running": bool(mon and mon.running),
        "interval": float(cfg.get("monitor.interval_seconds") or 5),
        "topbar": cfg.get("monitor.topbar", "sparks"),
        "host": sysmon.host_facts(),
    }
    if mon is not None and mon.latest is not None:
        with mon.lock:
            latest = {k: v for k, v in mon.latest.items() if k != "disks"}
            latest["disks"] = mon.latest.get("disks") or []
            spark = list(mon.spark)
            ping = dict(mon.ping) if mon.ping else None
        out.update(ts=latest.get("ts"), sample=latest, spark=spark, ping=ping, cost=mon.cost())
    else:
        con = _con(store)
        try:
            r = con.execute("SELECT * FROM samples WHERE tier = 0 ORDER BY ts DESC LIMIT 1").fetchone()
        finally:
            con.close()
        out.update(ts=r["ts"] if r else None, sample=dict(r) if r else None, spark=[], ping=None, cost=None)
    con = _con(store)
    try:
        out["open"] = [_row(r) for r in con.execute(
            "SELECT id, key, kind, severity, title, detail, started, peak, unit FROM events "
            "WHERE ended IS NULL ORDER BY started DESC")]
        day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        out["today"] = {r["severity"]: r["n"] for r in con.execute(
            "SELECT severity, COUNT(*) AS n FROM events WHERE started >= ? AND kind != 'gap' GROUP BY severity", (day0,))}
        out["unseen"] = con.execute(
            "SELECT COUNT(*) AS n FROM events WHERE seen = 0 AND severity != 'info'").fetchone()["n"]
    finally:
        con.close()
    return out


@router.get("/api/monitor/series")
def monitor_series(
    range: str = Query("1h"),
    from_: float | None = Query(None, alias="from"),
    to: float | None = Query(None),
    store: ViewStore = Depends(get_store),
) -> dict[str, Any]:
    now = time.time()
    if from_ is not None:
        start, end = float(from_), float(to or now)
    else:
        if range not in RANGES:
            raise HTTPException(status_code=422, detail=f"range is one of {', '.join(RANGES)}")
        start, end = now - RANGES[range], now
    if end <= start:
        raise HTTPException(status_code=422, detail="to must be after from")
    span = end - start
    cfg = sysmon.settings(store.data_root)
    raw_age = float(cfg.get("monitor.keep_raw_hours") or 6) * 3600
    minute_age = float(cfg.get("monitor.keep_minutes_days") or 7) * 86400
    # The finest tier that still holds the start of the span.
    tier = 0 if now - start <= raw_age else 1 if now - start <= minute_age else 2
    bucket = max(float(sysmon.TIERS[tier] or 1), span / TARGET_POINTS)
    avgs = ", ".join(f"AVG({c}) AS {c}" for c in sysmon.COLUMNS)
    peaks = ", ".join(f"MAX(COALESCE({c}_max, {c})) AS {c}_max" for c in sysmon.PEAKS)
    con = _con(store)
    try:
        rows = con.execute(
            f"SELECT MIN(ts) AS t, {avgs}, {peaks} FROM samples WHERE tier = ? AND ts >= ? AND ts <= ? "
            f"GROUP BY CAST(ts / ? AS INTEGER) ORDER BY t",
            (tier, start, end, bucket),
        ).fetchall()
        events = [_row(r) for r in con.execute(
            "SELECT id, key, kind, severity, title, started, ended, metric FROM events "
            "WHERE started <= ? AND COALESCE(ended, ?) >= ? ORDER BY started", (end, now, start))]
    finally:
        con.close()
    keys = ["t", *sysmon.COLUMNS, *(c + "_max" for c in sysmon.PEAKS)]
    cols: dict[str, list[Any]] = {k: [] for k in keys}
    for r in rows:
        for k in keys:
            v = r[k]
            cols[k].append(round(v, 3) if isinstance(v, float) else v)
    # Where the record has a hole longer than three points: drawn as a gap.
    gaps = [[a, b] for a, b in zip(cols["t"], cols["t"][1:]) if b - a > max(bucket * 3, sysmon.GAP_SECONDS)]
    return {"from": start, "to": end, "tier": tier, "bucket": bucket, "points": len(rows),
            "series": cols, "gaps": gaps, "events": events}


def _day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


@router.get("/api/monitor/events")
def monitor_events(
    since: float | None = Query(None),
    until: float | None = Query(None),
    severity: str = Query(""),
    kind: str = Query(""),
    q: str = Query(""),
    limit: int = Query(300, ge=1, le=5000),
    days: int = Query(0, ge=0, le=3650),
    store: ViewStore = Depends(get_store),
) -> dict[str, Any]:
    where, params = ["1=1"], []
    if since is not None:
        where.append("COALESCE(ended, 1e12) >= ?")
        params.append(since)
    if until is not None:
        where.append("started <= ?")
        params.append(until)
    if severity:
        sev = [s for s in severity.split(",") if s in SEVERITY_RANK]
        where.append(f"severity IN ({','.join('?' * len(sev))})")
        params += sev
    if kind:
        ks = kind.split(",")
        where.append(f"kind IN ({','.join('?' * len(ks))})")
        params += ks
    if q.strip():
        where.append("(title LIKE ? OR detail LIKE ?)")
        params += [f"%{q.strip()}%"] * 2
    con = _con(store)
    try:
        rows = [_row(r) for r in con.execute(
            f"SELECT id, key, kind, severity, title, detail, metric, unit, started, ended, peak, seen FROM events "
            f"WHERE {' AND '.join(where)} ORDER BY started DESC LIMIT ?", (*params, limit))]
        out: dict[str, Any] = {"events": rows, "total": len(rows)}
        if days:
            first = time.time() - days * 86400
            per: dict[str, dict[str, Any]] = {}
            for r in con.execute("SELECT started, severity, kind FROM events WHERE started >= ? AND kind != 'gap'", (first,)):
                d = per.setdefault(_day_of(r["started"]), {"n": 0, "worst": "info"})
                d["n"] += 1
                if SEVERITY_RANK.get(r["severity"], 0) > SEVERITY_RANK[d["worst"]]:
                    d["worst"] = r["severity"]
            out["days"] = per
            # Days the monitor was reading at all, so an empty day reads as calm, not as missing.
            out["watched"] = sorted({_day_of(r["t"] * 900) for r in con.execute(
                "SELECT DISTINCT CAST(ts / 900 AS INTEGER) AS t FROM samples WHERE ts >= ?", (first,))})
    finally:
        con.close()
    return out


# An id SQLite cannot hold is refused as a bad request, not a 500.
_EVENT_ID = PathParam(..., ge=0, le=2**63 - 1)


@router.get("/api/monitor/events/{event_id}")
def monitor_event(event_id: int = _EVENT_ID, store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    con = _con(store)
    try:
        r = con.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if r is None:
            raise not_found("event", str(event_id))
        ev = _row(r)
        end = ev["ended"] or time.time()
        # A long event spans thousands of scans: thirty of them, evenly spread,
        # tell the story (a week-long leak was 260 000 rows).
        scans = [r["ts"] for r in con.execute(
            "SELECT DISTINCT ts FROM processes WHERE ts BETWEEN ? AND ? ORDER BY ts", (ev["started"] - 600, end + 60))]
        if len(scans) > 30:
            step = (len(scans) - 1) / 29
            scans = [scans[round(i * step)] for i in range(30)]
        procs = [dict(p) for p in con.execute(
            f"SELECT ts, pid, name, label, rss, cpu FROM processes WHERE ts IN ({','.join('?' * len(scans))}) ORDER BY ts",
            scans)] if scans else []
    finally:
        con.close()
    return {"event": ev, "processes": procs}


@router.get("/api/monitor/processes")
def monitor_processes(
    request: Request,
    sort: str = Query("rss"),
    limit: int = Query(15, ge=1, le=100),
    store: ViewStore = Depends(get_store),
) -> dict[str, Any]:
    key = "cpu" if sort == "cpu" else "rss"
    mon = _mon(request)
    if mon is not None and mon.procs:
        with mon.lock:
            procs, at = list(mon.procs), mon.procs_at
        top = sorted(procs, key=lambda p: -p[key])[:limit]
        # Programs, not processes: a browser is thirty processes and one thing to a person.
        by_name: dict[str, dict[str, Any]] = {}
        for p in procs:
            g = by_name.setdefault(p["name"], {"name": p["name"], "rss": 0.0, "cpu": 0.0, "n": 0})
            g["rss"] += p["rss"]
            g["cpu"] += p["cpu"]
            g["n"] += 1
        groups = sorted(by_name.values(), key=lambda g: -g[key])[:limit]
        return {"at": at, "count": len(procs), "processes": [
            {"pid": p["pid"], "name": p.get("label") or p["name"], "rss": p["rss"], "cpu": round(p["cpu"], 2)} for p in top],
            "programs": [{**g, "cpu": round(g["cpu"], 2)} for g in groups]}
    con = _con(store)
    try:
        last = con.execute("SELECT MAX(ts) AS t FROM processes").fetchone()["t"]
        rows = [dict(r) for r in con.execute(
            f"SELECT pid, label AS name, rss, cpu FROM processes WHERE ts = ? ORDER BY {key} DESC LIMIT ?", (last, limit))] if last else []
    finally:
        con.close()
    return {"at": last, "count": len(rows), "processes": rows, "programs": []}


@router.get("/api/monitor/storage")
def monitor_storage(store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    path = sysmon.db_path(store.data_root)
    size = sum(os.path.getsize(p) for p in (path, path.with_name(path.name + "-wal")) if p.exists())
    con = _con(store)
    try:
        tiers = {r["tier"]: {"rows": r["n"], "oldest": r["o"]} for r in con.execute(
            "SELECT tier, COUNT(*) AS n, MIN(ts) AS o FROM samples GROUP BY tier")}
        ev = con.execute("SELECT COUNT(*) AS n, MIN(started) AS o FROM events").fetchone()
    finally:
        con.close()
    return {"file": str(path), "bytes": size, "tiers": tiers, "events": {"rows": ev["n"], "oldest": ev["o"]}}


@router.post("/api/monitor/events/{event_id}/seen")
def monitor_event_seen(event_id: int = _EVENT_ID, body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "Marking a monitor event seen")
    con = _con(store)
    try:
        n = con.execute("UPDATE events SET seen = 1 WHERE id = ?", (event_id,)).rowcount
        con.commit()
    finally:
        con.close()
    return {"seen": n}


@router.post("/api/monitor/events/seen")
def monitor_events_seen(body: dict = Body(default={}), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    operator_only(body, "Marking monitor events seen")
    con = _con(store)
    try:
        n = con.execute("UPDATE events SET seen = 1 WHERE seen = 0").rowcount
        con.commit()
    finally:
        con.close()
    return {"seen": n}


@router.post("/api/monitor/clear")
def monitor_clear(body: dict = Body(...), store: ViewStore = Depends(get_store)) -> dict[str, Any]:
    """``{what: samples | events | all}`` — delete the record. Settings stay."""
    operator_only(body, "Deleting the monitor's record")
    what = str(body.get("what") or "")
    if what not in ("samples", "events", "all"):
        raise HTTPException(status_code=422, detail="what must be samples, events or all")
    con = _con(store)
    try:
        if what in ("samples", "all"):
            for t in ("samples", "processes", "disks"):
                con.execute(f"DELETE FROM {t}")
        if what in ("events", "all"):
            con.execute("DELETE FROM events WHERE ended IS NOT NULL")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    return {"cleared": what}
