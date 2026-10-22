"""Tests for backend.date_utils.

Contract note: identical inputs/outputs must be produced by the TypeScript
mirror in frontend/src/utils/dateUtils.ts. Any change here MUST have a
matching change in dateUtils.test.ts.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.date_utils import (
    InvalidYYMMDD,
    days_ago,
    format_yymm_dd,
    format_yymmdd,
    parse_iso_local,
    parse_yymm_dd,
    parse_yymmdd,
    relative_time,
    today_yymm_dd,
)


# ---------------------------------------------------------------------------
# parse_yymm_dd
# ---------------------------------------------------------------------------


class TestParseYYMMDD:
    def test_basic(self):
        assert parse_yymm_dd("2608-06") == date(2026, 8, 6)

    def test_earliest_and_latest_year(self):
        assert parse_yymm_dd("0001-01") == date(2000, 1, 1)
        assert parse_yymm_dd("9912-31") == date(2099, 12, 31)

    def test_leap_day(self):
        assert parse_yymm_dd("2402-29") == date(2024, 2, 29)  # 2024 is leap

    def test_non_leap_feb_29_rejected(self):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd("2302-29")

    def test_month_zero_rejected(self):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd("2600-01")

    def test_month_thirteen_rejected(self):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd("2613-01")

    def test_feb_30_rejected(self):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd("2602-30")

    def test_day_zero_rejected(self):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd("2608-00")

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "26-08-06",
            "260806",
            "2608-6",
            "2608-006",
            "26/08/06",
            "not-a-date",
            "2026-08-06",  # 5-digit prefix ambiguous with ISO — reject
        ],
    )
    def test_bad_shapes_rejected(self, bad):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd(bad)

    @pytest.mark.parametrize("bad", [None, 20260806, 3.14, [], {}])
    def test_non_string_rejected(self, bad):
        with pytest.raises(InvalidYYMMDD):
            parse_yymm_dd(bad)

    def test_iso_local_prefix_accepted(self):
        assert parse_yymm_dd("2608-06T14:30:00") == date(2026, 8, 6)
        assert parse_yymm_dd("2608-06T14:30:00+03:00") == date(2026, 8, 6)
        assert parse_yymm_dd("2608-06 14:30:00") == date(2026, 8, 6)


# ---------------------------------------------------------------------------
# format_yymm_dd
# ---------------------------------------------------------------------------


class TestFormatYYMMDD:
    def test_basic(self):
        assert format_yymm_dd(date(2026, 8, 6)) == "2608-06"

    def test_datetime_input(self):
        assert format_yymm_dd(datetime(2026, 8, 6, 14, 30)) == "2608-06"

    def test_pad_single_digits(self):
        assert format_yymm_dd(date(2001, 1, 2)) == "0101-02"

    def test_none_returns_empty(self):
        assert format_yymm_dd(None) == ""

    def test_year_out_of_range(self):
        with pytest.raises(ValueError):
            format_yymm_dd(date(1999, 1, 1))
        with pytest.raises(ValueError):
            format_yymm_dd(date(2100, 1, 1))

    def test_round_trip(self):
        for d in [date(2001, 1, 1), date(2026, 8, 6), date(2099, 12, 31)]:
            assert parse_yymm_dd(format_yymm_dd(d)) == d


# ---------------------------------------------------------------------------
# days_ago
# ---------------------------------------------------------------------------


class TestDaysAgo:
    def test_today_is_zero(self):
        assert days_ago("2608-06", today=date(2026, 8, 6)) == 0

    def test_past(self):
        assert days_ago("2608-01", today=date(2026, 8, 6)) == 5

    def test_future_negative(self):
        assert days_ago("2608-10", today=date(2026, 8, 6)) == -4

    def test_accepts_date(self):
        assert days_ago(date(2026, 8, 1), today=date(2026, 8, 6)) == 5

    def test_accepts_datetime(self):
        assert days_ago(datetime(2026, 8, 1, 12), today=date(2026, 8, 6)) == 5

    def test_accepts_iso_local(self):
        assert days_ago("2608-01T14:30:00", today=date(2026, 8, 6)) == 5


# ---------------------------------------------------------------------------
# parse_iso_local
# ---------------------------------------------------------------------------


class TestParseISOLocal:
    def test_full_timestamp(self):
        assert parse_iso_local("2608-06T14:30:00") == datetime(2026, 8, 6, 14, 30, 0)

    def test_with_tz_stripped(self):
        assert parse_iso_local("2608-06T14:30:00+03:00") == datetime(
            2026, 8, 6, 14, 30, 0
        )
        assert parse_iso_local("2608-06T14:30:00Z") == datetime(2026, 8, 6, 14, 30, 0)

    def test_with_microseconds(self):
        assert parse_iso_local("2608-06T14:30:00.123456") == datetime(
            2026, 8, 6, 14, 30, 0, 123456
        )

    def test_hh_mm_only(self):
        assert parse_iso_local("2608-06T14:30") == datetime(2026, 8, 6, 14, 30, 0)

    def test_date_only(self):
        assert parse_iso_local("2608-06") == datetime(2026, 8, 6, 0, 0, 0)

    def test_space_separator(self):
        assert parse_iso_local("2608-06 14:30:00") == datetime(2026, 8, 6, 14, 30, 0)


# ---------------------------------------------------------------------------
# relative_time
# ---------------------------------------------------------------------------


class TestRelativeTime:
    NOW = datetime(2026, 8, 6, 12, 0, 0)

    def test_just_now(self):
        assert relative_time(datetime(2026, 8, 6, 11, 59, 30), now=self.NOW) == "just now"

    def test_seconds_bucket_1m(self):
        # 60s ago falls into <90s bucket → "1m ago"
        assert relative_time(datetime(2026, 8, 6, 11, 59, 0), now=self.NOW) == "1m ago"

    def test_minutes(self):
        assert relative_time(datetime(2026, 8, 6, 11, 30, 0), now=self.NOW) == "30m ago"

    def test_hours(self):
        assert relative_time(datetime(2026, 8, 6, 9, 0, 0), now=self.NOW) == "3h ago"

    def test_days(self):
        assert relative_time(datetime(2026, 8, 3, 12, 0, 0), now=self.NOW) == "3d ago"

    def test_weeks(self):
        assert relative_time(datetime(2026, 7, 16, 12, 0, 0), now=self.NOW) == "3w ago"

    def test_months(self):
        assert relative_time(datetime(2026, 5, 1, 12, 0, 0), now=self.NOW) == "3mo ago"

    def test_years(self):
        assert relative_time(datetime(2023, 8, 6, 12, 0, 0), now=self.NOW) == "3y ago"

    def test_future(self):
        assert (
            relative_time(datetime(2026, 8, 9, 12, 0, 0), now=self.NOW) == "in 3d"
        )

    def test_string_input(self):
        assert relative_time("2608-03", now=self.NOW) == "3d ago"

    def test_iso_string_input(self):
        assert (
            relative_time("2608-06T09:00:00", now=self.NOW) == "3h ago"
        )


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_parse_yymmdd_returns_none_on_bad_input(self):
        assert parse_yymmdd("") is None
        assert parse_yymmdd(None) is None
        assert parse_yymmdd("garbage") is None

    def test_parse_yymmdd_returns_date_on_good(self):
        assert parse_yymmdd("2608-06") == date(2026, 8, 6)

    def test_format_yymmdd_matches_canonical(self):
        assert format_yymmdd(date(2026, 8, 6)) == "2608-06"
        assert format_yymmdd(None) == ""


# ---------------------------------------------------------------------------
# today_yymm_dd
# ---------------------------------------------------------------------------


def test_today_yymm_dd():
    result = today_yymm_dd()
    # matches the format regex
    assert len(result) == 7
    assert result[4] == "-"
    parse_yymm_dd(result)  # round-trip parseable


# ---------------------------------------------------------------------------
# Performance smoke — parse must be fast (heatmap hot path)
# ---------------------------------------------------------------------------


def test_parse_hot_path_smoke():
    """~10k parses complete in well under 100ms; the bound is wide for a
    loaded CI runner."""
    import time

    dates = ["2608-06", "2607-01", "2601-15", "2412-31"] * 2500  # 10k
    t0 = time.perf_counter()
    for s in dates:
        parse_yymm_dd(s)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"10k parses took {elapsed:.3f}s"
