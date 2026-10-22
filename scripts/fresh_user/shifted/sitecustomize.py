"""Moves the clock of one Python process by FRESH_SHIFT_SECONDS.

The fresh-user test puts this folder on PYTHONPATH when it runs Slightly Parallel's
capture hook for "yesterday's chat", so the next day's first message meets
a day with messages and no standup. Nothing else loads it.
"""

import datetime as _dt
import os
import time

_shift = float(os.environ.get("FRESH_SHIFT_SECONDS") or 0)

if _shift:
    _time, _localtime, _strftime = time.time, time.localtime, time.strftime
    time.time = lambda: _time() + _shift
    time.localtime = lambda secs=None: _localtime(time.time() if secs is None else secs)
    time.strftime = lambda fmt, t=None: _strftime(fmt, time.localtime() if t is None else t)

    class datetime(_dt.datetime):  # noqa: N801 — stands in for the real class
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(time.time(), tz)

        @classmethod
        def today(cls):
            return cls.now()

    class date(_dt.date):  # noqa: N801
        @classmethod
        def today(cls):
            return _dt.datetime.now().date()

    _dt.datetime = datetime
    _dt.date = date
