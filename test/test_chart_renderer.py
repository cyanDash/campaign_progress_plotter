"""Tests for the counting and coloring behind chart_renderer's worker
histograms, and that the 3x1 report renders. Run with: pytest
"""

from chart_renderer import stack_counts, status_colors, render_window_report
from window_jobs import latest_limits


def worker(exit_code, mem=8000, wall=3.0, kind="slice", sub="1", request=10240, limit=12.0):
    return {"node": "W", "exit": exit_code, "mem_mb": mem, "wall_h": wall, "starts": 1,
            "kind": kind, "submission_id": sub, "request_mb": request, "limit_h": limit}


def test_stack_counts_has_one_list_per_exit_code_in_order():
    workers = [worker(88, mem=8500), worker(0, mem=8100), worker(9, mem=50), worker(0, mem=8900),
               worker(None, mem=1500, wall=None), worker(88, mem=12000)]

    counts = stack_counts(workers, "mem_mb", 1000, 14)

    assert list(counts) == ["exit 0", "exit 9", "exit 88", "running"]
    assert counts["exit 0"][8] == 2 and counts["exit 88"][8] == 1 and counts["exit 88"][12] == 1
    assert counts["exit 9"][0] == 1 and counts["running"][1] == 1
    assert sum(sum(v) for v in counts.values()) == 6


def test_stack_counts_skips_workers_without_the_field_and_clamps_the_last_bin():
    counts = stack_counts([worker(0, wall=None), worker(0, wall=40.0), worker(0, wall=2.5)], "wall_h", 1, 13)

    assert sum(counts["exit 0"]) == 2 and counts["exit 0"][12] == 1 and counts["exit 0"][2] == 1


def test_status_colors_gives_each_exit_code_its_own_color():
    colors = status_colors([worker(0), worker(88), worker(9), worker(88), worker(None)])

    assert set(colors) == {"exit 0", "running", "exit 9", "exit 88"}
    assert len({colors["exit 9"], colors["exit 88"], colors["exit 0"], colors["running"]}) == 4


def test_latest_limits_come_from_the_newest_submission_of_the_kind():
    workers = [worker(0, sub="10", request=10240, limit=12.0), worker(0, sub="12", request=12288, limit=10.0),
               worker(0, sub="12", request=12288, limit=10.0), worker(0, kind="recovery", sub="11", request=16384)]

    assert latest_limits(workers, "slice") == (12288, 10.0)
    assert latest_limits(workers, "recovery") == (16384, 12.0)


def test_latest_limits_are_none_without_workers_of_the_kind():
    assert latest_limits([worker(0)], "recovery") == (None, None)
    assert latest_limits([worker(0, request=None, limit=None)], "slice") == (None, None)


def test_report_writes_a_pdf_with_workers_in_either_column_or_only_one(tmp_path):
    series = {"input": [10, 10], "reco1": [10, 9]}
    both = [worker(0), worker(88, mem=12000, wall=12.1), worker(None, wall=None),
            worker(0, kind="recovery", sub="2", request=16384), worker(9, kind="recovery", sub="2", mem=50, wall=0.1)]
    for name, workers in (("both", both), ("slice_only", both[:3])):
        out = tmp_path / f"{name}.pdf"

        render_window_report(["Sun 15 Nov", "Mon 16 Nov"], series, workers, title="t", filename=str(out))

        assert out.stat().st_size > 0


def test_limit_lines_are_named_in_the_legend_not_with_text(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    import chart_renderer

    seen = {}
    real_close = plt.close

    def keep(fig):
        seen["texts"] = [t.get_text() for ax in fig.axes for t in ax.texts]
        seen["legends"] = [[t.get_text() for t in ax.get_legend().get_texts()] for ax in fig.axes if ax.get_legend()]
        real_close(fig)
    monkeypatch.setattr(chart_renderer.plt, "close", keep)

    chart_renderer.render_window_report(["a"], {"input": [1], "reco1": [1]}, [worker(0)], title="t",
                                        filename=str(tmp_path / "x.pdf"))

    assert not any(text.startswith(("request", "limit")) for text in seen["texts"])
    legends = [sorted(names) for names in seen["legends"]]
    assert ["exit 0", "request 10.2 GB"] in legends and ["exit 0", "limit 12 h"] in legends
