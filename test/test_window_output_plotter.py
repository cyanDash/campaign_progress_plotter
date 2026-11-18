"""Tests for window_output_plotter.py -- the cron entry point -- against a fake
SAM seam. Run with: pytest
"""

import pytest

import window_output_plotter as wop


class FakeSam:
    def __init__(self):
        self.queries = []

    def count(self, query):
        self.queries.append(query)
        return 10


def test_daily_plots_yesterdays_window_to_the_keepup_filename(tmp_path):
    sam = FakeSam()
    out = wop.main(["daily", "2026-11-16"], sam=sam, output_directory=tmp_path)
    assert out == f"{tmp_path}/sbnd_data_run3_keepup_daily.pdf"
    assert (tmp_path / "sbnd_data_run3_keepup_daily.pdf").stat().st_size > 0
    # 2026-11-15 00:00-03:00 Central is 06:00-09:00 UTC; input + 5 tiers.
    assert len(sam.queries) == 6
    assert "create_date >= '2026-11-15T06:00:00' and create_date < '2026-11-15T09:00:00'" in sam.queries[0]


def test_weekly_names_the_weekly_file(tmp_path):
    out = wop.main(["weekly", "2026-11-22"], sam=FakeSam(), output_directory=tmp_path)
    assert out.endswith("sbnd_data_run3_keepup_weekly.pdf")
    assert (tmp_path / "sbnd_data_run3_keepup_weekly.pdf").exists()


def test_exits_before_the_first_window_has_started(tmp_path):
    with pytest.raises(SystemExit, match="nothing to plot"):
        wop.main(["daily", "2026-11-15"], sam=FakeSam(), output_directory=tmp_path)
