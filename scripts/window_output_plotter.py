"""Grouped-bar plot of input vs output file counts per split window, for a
campaign run with poms_auto_submit's [split] window. Run after `source setup.sh`.

    window_output_plotter.py daily   [YYYY-MM-DD]   yesterday's window
    window_output_plotter.py weekly  [YYYY-MM-DD]   the last 7 windows

The optional date replaces today (Central) as the run date.
"""

import sys
from datetime import date, datetime, timedelta

import samweb_fetcher
from split_windows import recent_window_bounds, collect_window_counts, CENTRAL
from chart_renderer import render_window_chart

#####################################################################
# Must match the campaign's ini ([split] first_start/step/window).
first_start = "2026-11-15 00:00"  # Central
step = timedelta(days=1)
window = timedelta(hours=3)
input_dataset = "run3_raw_data_ongoing"
campaign = "Auto_POMS_SBND2026A_Gen2_Run3_BeamLight"
version = "v10_14_02_08"
tiers = ["reco1", "larcvreco1", "histreco2", "flatcaf", "caf"]

output_directory = "/exp/sbnd/app/users/sbndpro/mcp/SBND2026A/srcs/sbnutil/keepups/sbnd/data_run3/plots"
#####################################################################

mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
count = {"daily": 1, "weekly": 7}[mode]
today = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.now(CENTRAL).date()

bounds = recent_window_bounds(today, first_start, step, window, count)
if not bounds:
    sys.exit(f"No window has started before {today}; nothing to plot.")
definitions = [f"data_SBND2026A_{campaign}_{version}_{t}_sbnd" for t in tiers]

rows = collect_window_counts(samweb_fetcher, input_dataset, definitions, bounds)
series = {"input": rows["input"], **{t: rows[d] for t, d in zip(tiers, definitions)}}

labels = [s.astimezone(CENTRAL).strftime("%a %d %b") for s, _ in bounds]
hours = int(window.total_seconds() // 3600)
start_local = bounds[0][0].astimezone(CENTRAL).strftime("%H:%M")
end_local = bounds[0][1].astimezone(CENTRAL).strftime("%H:%M")
filename = f"{output_directory}/sbnd_data_run3_keepup_{mode}.pdf"
render_window_chart(
    labels, series,
    title=f"Input vs output files per split window ({start_local}-{end_local} Central, {hours}h window, step {step.days}d)",
    filename=filename,
)
print(series)
print(filename)
