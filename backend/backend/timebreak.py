"""A break the operator takes on purpose (tk_810245f2, tk_caf2b06a).

«Перерыв» in the terminal window's health label starts one; «Готово» ends
it. While it lasts the operator's time stands still:

- the smart timer's open auto spans close now, and the tick opens none for
  a held project, whatever beats arrive (``held``, read by
  ``AutoTimer._working``);
- every running manual timer is paused, stamped with the break's start.

On «Готово» the manual timers this break paused resume, each only if it is
still paused at that same moment (one stopped, resumed or paused again by
hand meanwhile is left as it is). Auto spans open again on the next beat.

``project`` narrows a break to one project; empty (the default) holds all
of them: on a break nobody works on anything.

The state lives in ``timer/break.json`` beside the smart timer's own, so a
restart keeps a break under way. Today's breaks are kept there too, with
the note written on «Готово».
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import clocktime
from .csvio import DamagedFile
from .file_safety import atomic_write

log = logging.getLogger("sp.timebreak")

FILE = "break.json"
#: Breaks kept in the file, newest last.
KEEP = 200
NOTE_MAX = 500

_iso = clocktime.iso
_parse = clocktime.parse


def _state(timer: Any) -> dict[str, Any]:
    """The break state, read once per timer and kept on it."""
    got = getattr(timer, "_break_state", None)
    if got is None:
        try:
            got = timer._read(FILE)
        except DamagedFile as exc:
            log.warning("%s", exc)
            got = {}
        got.setdefault("on", None)
        got.setdefault("log", [])
        timer._break_state = got
    return got


def _write(timer: Any) -> None:
    timer.folder.mkdir(parents=True, exist_ok=True)
    atomic_write(timer.folder / FILE, json.dumps(_state(timer), indent=1))


def held(timer: Any, project: str) -> bool:
    """True while a break holds `project`: the smart timer counts nothing for it."""
    on = _state(timer).get("on")
    if not on:
        return False
    scope = str(on.get("project") or "")
    return not scope or scope == project


def status(timer: Any) -> dict[str, Any]:
    """Whether a break is under way, since when, what it paused, and today's breaks."""
    with timer._lock:
        st = _state(timer)
        on = st.get("on")
        now = clocktime.at(timer.clock())
        today = now.date().isoformat()
        breaks = [b for b in st.get("log") or [] if str(b.get("from") or "")[:10] == today]
        out: dict[str, Any] = {"on": bool(on), "today": breaks}
        if on:
            since = _parse(str(on.get("since") or "")) or now
            out.update({
                "since": on.get("since"), "project": on.get("project") or "",
                "note": on.get("note") or "", "paused": sorted(on.get("paused") or {}),
                "closed": list(on.get("closed") or []),
                "sec": max(0, int((now - since).total_seconds())),
            })
        return out


def start(timer: Any, project: str = "", note: str = "") -> dict[str, Any]:
    """Begin a break: close the auto spans, pause the running manual timers.
    A break already under way is kept as it is."""
    from .timelib import _patch
    with timer._lock:
        st = _state(timer)
        if st.get("on"):
            return status(timer)
        now = clocktime.at(timer.clock())
        at = _iso(now)
        closed = []
        for p in list(timer.spans):
            if not project or p == project:
                closed.append(timer.spans[p].entry_id)
                timer._close(p, now)
        paused: dict[str, str] = {}
        for r in timer._running_manual(project):
            rid = str(r["id"])
            if str(r.get("paused_at") or "") or rid in timer.paused:
                continue   # paused already, by hand or by the away rule
            _patch(timer.store, rid, {"paused_at": at})
            paused[rid] = at
        st["on"] = {"since": at, "project": project, "note": note[:NOTE_MAX], "paused": paused, "closed": closed}
        timer._save()
        _write(timer)
        return status(timer)


def finish(timer: Any, note: str = "") -> dict[str, Any]:
    """End the break: resume the manual timers it paused (only those still
    paused at its start), keep it in today's breaks with its note."""
    from .timelib import time_resume_row
    with timer._lock:
        st = _state(timer)
        on = st.get("on")
        if not on:
            return status(timer)
        now = clocktime.at(timer.clock())
        resumed = []
        for rid, at in (on.get("paused") or {}).items():
            rows = timer._rows(rid)
            if not rows or str(rows[0].get("ended_at") or "") or str(rows[0].get("paused_at") or "") != at:
                continue   # stopped, resumed or paused again by hand meanwhile
            time_resume_row(timer.store, rows[0], now)
            resumed.append(rid)
        since = _parse(str(on.get("since") or "")) or now
        text = (note or str(on.get("note") or "")).strip()[:NOTE_MAX]
        entry = {"from": on.get("since"), "to": _iso(now), "sec": max(0, int((now - since).total_seconds())),
                 "project": on.get("project") or "", "note": text, "resumed": resumed}
        st["on"] = None
        st["log"] = [*(st.get("log") or []), entry][-KEEP:]
        _write(timer)
        out = status(timer)
        out["ended"] = entry
        return out
