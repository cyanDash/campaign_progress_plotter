# Split into samweb_fetcher / campaign_projection / chart_renderer

The script used to be one 440-line file with SAM subprocess calls, the
three-case prediction logic, and two near-duplicate matplotlib blocks all
interleaved through shared module-level globals. Testing a pure branching or
rate-math change (see ADRs 0001–0004) meant running the whole script live
against SAM, ~90s–2min per check.

Split into three modules: `samweb_fetcher.py` (the one seam that shells out to
`samweb` — `file_count`, `creation_time`, `exists`), `campaign_projection.py`
(pure prediction: `project_campaign()` takes plain data in, returns a
`Projection` out, no I/O), and `chart_renderer.py` (`render_bar_chart()`,
parameterized once and called twice instead of duplicated). `campaign_progress_plotter.py`
is now just config plus wiring between the three.

`campaign_projection.py` is covered by `test_campaign_projection.py`
(synthetic data, no SAM, no grid) — this is the module that actually changed
across ADRs 0001–0004, so it's the one that needed to be fast to verify.
