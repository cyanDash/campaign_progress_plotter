"""Grouped-bar plot of input vs output file counts per split window, for a
campaign run with poms_auto_submit's [split] window. Run after `source setup.sh`.
"""

import sys
from datetime import datetime, timedelta, timezone

import samweb_fetcher
from split_windows import window_bounds, collect_window_counts, CENTRAL
from chart_renderer import render_window_chart

#####################################################################
# Must match the campaign's ini ([split] first_start/step/window).
first_start = "2026-10-25 04:00"  # Central
step = timedelta(days=1)
window = timedelta(hours=3)
input_dataset = "run3_raw_data_ongoing"
campaign = "Auto_POMS_SBND2026A_Gen2_Run3_BeamLight"
version = "v10_14_02_08"
tiers = ["reco1", "larcvreco1", "histreco2", "flatcaf", "caf"]

output_directory = "plots"
#####################################################################

n_windows = int(sys.argv[1]) if len(sys.argv) > 1 else 5
bounds = window_bounds(first_start, step, window, n_windows)
definitions = [f"data_SBND2026A_{campaign}_{version}_{t}_sbnd" for t in tiers]

rows = collect_window_counts(samweb_fetcher, input_dataset, definitions, bounds)
series = {"input": rows["input"], **{t: rows[d] for t, d in zip(tiers, definitions)}}

labels = [s.astimezone(CENTRAL).strftime("%a %d %b") for s, _ in bounds]
hours = int(window.total_seconds() // 3600)
start_local = bounds[0][0].astimezone(CENTRAL).strftime("%H:%M")
end_local = bounds[0][1].astimezone(CENTRAL).strftime("%H:%M")
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
filename = f"{output_directory}/{campaign}_{timestamp}_windows.png"
render_window_chart(
    labels, series,
    title=f"Input vs output files per split window ({start_local}-{end_local} Central, {hours}h window, step {step.days}d)",
    filename=filename,
)
print(series)
print(filename)
