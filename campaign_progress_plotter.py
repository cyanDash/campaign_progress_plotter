"""Bar graph plotter for production campaign updates. See docs/adr/ for the
reasoning behind the rate/date/threshold decisions below.
"""

from datetime import datetime, timezone, timedelta

import samweb_fetcher
from campaign_projection import project_campaign, recovery_skipped, format_date
from chart_renderer import render_bar_chart

#####################################################################
# Campaign Information:
campaign_type = 'mc' # 'data' or 'mc'.
target = 249946 # If running an MC campaign, enter the number of files you want to process, for data campaigns this will the size of the input dataset so will be redefined later in the code.
campaign = "SBND2026A_gen2_PDS_DetVar_Sample3" # Must match input_dataset + "_" + campaign + "_recovery_campaign".
input_dataset = r"aurora_SBND2026A_gen2_BNBLight_DevSample_prodgenie_corsika_proton_rockbox0p1_sbnd_CV_v10_14_02_03_reco1_sbnd"
output_dataset = r"mc_SBND2026A_prodgenie_corsika_proton_rockbox0p1_sbnd_PDS_detvar_Sample3_v10_14_02_0602_flatcaf_sbnd"

output_directory = "/exp/sbnd/app/users/sdas1/slides/sbnd_production/Update on PDS Detvar 3 Campaign/plots"
#####################################################################


now = datetime.now(timezone.utc)
today_date = now.date()
timestamp = now.strftime("%Y%m%d_%H%M%S")

campaign_start_dt = samweb_fetcher.creation_time(output_dataset)
start_date = campaign_start_dt.date()

recovery_dataset = f"{input_dataset}_{campaign}_recovery_campaign"
if samweb_fetcher.exists(recovery_dataset):
    recovery_start_dt = samweb_fetcher.creation_time(recovery_dataset)
    recovery_start_date = recovery_start_dt.date()
else:
    recovery_start_dt = None
    recovery_start_date = None

if campaign_type == 'data':
    target = samweb_fetcher.file_count(input_dataset, start_date + timedelta(days=1))

today_idx = (today_date - start_date).days

finished = []
for i in range(today_idx + 1):
    finished.append(samweb_fetcher.file_count(output_dataset, start_date + timedelta(days=i + 1)))
    if recovery_skipped(finished[-1], target):
        break
if len(finished) - 1 < today_idx:
    today_idx = len(finished) - 1
    today_date = start_date + timedelta(days=today_idx)

projection = project_campaign(
    finished, target, start_date, today_idx, today_date, now,
    campaign_start_dt, recovery_start_date, recovery_start_dt,
)

finished_total = finished[projection.today_idx]
today_label = f"Today's Date: {format_date(projection.today_date)}"

finished_per_day = [finished[i] - finished[i - 1] if i > 0 else finished[i] for i in range(len(finished))]
projected_per_day = [projection.projected[i] - projection.projected[i - 1] if i > 0 else projection.projected[i] for i in range(len(projection.projected))]

render_bar_chart(
    projection.dates, projection.projected, finished,
    finished_total=finished_total, target=target, show_target_line=True,
    today_idx=projection.today_idx, today_label=today_label,
    recovery_idx=projection.recovery_idx, show_recovery_line=projection.show_recovery_line,
    recovery_line_label=projection.recovery_line_label,
    end_date_label=projection.end_date_label, show_end_date_annotation=projection.show_end_date_annotation,
    failed_files=projection.failed_files,
    title='Cumulative Files Over Time', ylabel='Cumulative Files',
    filename=f'{output_directory}/{campaign}_{timestamp}_cumulative.png',
)

render_bar_chart(
    projection.dates, projected_per_day, finished_per_day,
    finished_total=finished_total, target=target, show_target_line=False,
    today_idx=projection.today_idx, today_label=today_label,
    recovery_idx=projection.recovery_idx, show_recovery_line=projection.show_recovery_line,
    recovery_line_label=projection.recovery_line_label,
    end_date_label=projection.end_date_label, show_end_date_annotation=projection.show_end_date_annotation,
    failed_files=projection.failed_files,
    title='Finished Files Per Day', ylabel='Daily Files',
    filename=f'{output_directory}/{campaign}_{timestamp}_daily.png',
)
