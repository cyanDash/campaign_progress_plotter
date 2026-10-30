"""Tests for split_windows.py -- window bounds (Central -> UTC) and per-window
input/output counting against a fake SAM seam. Run with: pytest
"""

from datetime import datetime, timedelta, timezone

from split_windows import window_bounds, collect_window_counts, input_query, output_query


def utc(y, m, d, hour=0):
    return datetime(y, m, d, hour, tzinfo=timezone.utc)


def test_window_bounds_cdt_to_utc():
    # 04:00 CDT is 09:00 UTC; step 1d, window 3h.
    bounds = window_bounds("2026-10-25 04:00", timedelta(days=1), timedelta(hours=3), 2)
    assert bounds == [
        (utc(2026, 10, 25, 9), utc(2026, 10, 25, 12)),
        (utc(2026, 10, 26, 9), utc(2026, 10, 26, 12)),
    ]


def test_window_bounds_follows_dst_change():
    # Clocks fall back 1 Nov 2026: 04:00 local is CDT (UTC-5) before, CST (UTC-6) after.
    bounds = window_bounds("2026-10-31 04:00", timedelta(days=1), timedelta(hours=3), 2)
    assert bounds[0][0] == utc(2026, 10, 31, 9)
    assert bounds[1][0] == utc(2026, 11, 1, 10)


def test_queries():
    iq = input_query("raw", utc(2026, 10, 25, 9), utc(2026, 10, 25, 12))
    assert iq == "defname:raw and create_date >= '2026-10-25T09:00:00' and create_date < '2026-10-25T12:00:00'"
    assert output_query("out", iq) == f"defname:out and ischildof:({iq})"


class FakeSam:
    def __init__(self, counts):
        self.counts = counts
        self.queries = []

    def count(self, query):
        self.queries.append(query)
        return self.counts[query]


def test_collect_window_counts():
    w = [(utc(2026, 10, 25, 9), utc(2026, 10, 25, 12))]
    iq = input_query("raw", *w[0])
    fake = FakeSam({iq: 10, output_query("reco1", iq): 9, output_query("caf", iq): 8})
    rows = collect_window_counts(fake, "raw", ["reco1", "caf"], w)
    assert rows == {"input": [10], "reco1": [9], "caf": [8]}


def test_recent_window_bounds_ends_yesterday():
    from datetime import date
    from split_windows import recent_window_bounds
    # Run on 28 Oct: the daily chunk is 27 Oct 04:00 CDT.
    bounds = recent_window_bounds(date(2026, 10, 28), "2026-10-25 04:00", timedelta(days=1), timedelta(hours=3), 1)
    assert bounds == [(utc(2026, 10, 27, 9), utc(2026, 10, 27, 12))]
    week = recent_window_bounds(date(2026, 10, 30), "2026-10-20 04:00", timedelta(days=1), timedelta(hours=3), 7)
    assert [b[0] for b in week] == [utc(2026, 10, d, 9) for d in range(23, 30)]


def test_recent_window_bounds_clamped_to_first_start():
    from datetime import date
    from split_windows import recent_window_bounds
    # Only 25-27 Oct exist when run on 28 Oct, so a 7-day request returns 3.
    bounds = recent_window_bounds(date(2026, 10, 28), "2026-10-25 04:00", timedelta(days=1), timedelta(hours=3), 7)
    assert [b[0] for b in bounds] == [utc(2026, 10, d, 9) for d in (25, 26, 27)]


def test_recent_window_bounds_before_first_window_is_empty():
    from datetime import date
    from split_windows import recent_window_bounds
    assert recent_window_bounds(date(2026, 10, 25), "2026-10-25 04:00", timedelta(days=1), timedelta(hours=3), 1) == []
