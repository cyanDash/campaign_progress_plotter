"""
Name: campaign_progress_plotter.py
Description: Bar Graph Plotter for Production Campaign Updates.
This script calls samweb-client to fetch the number of files in a given dataset created before a target date,
and uses that information to plot the progress of the campaign. The campaign end date predicted from the observed 
daily rate of progress. If the recovery campaign hasn't started yet, the script
predicts the recovery campaign's start date instead of an end date; once a recovery_start_date is supplied,
it predicts the end date using the rate of progress since recovery began.

Before running the script, setup sam_web_client and python from cvmfs.

Creator: Max Dubnowski
Updater: Sayan Kr Das
Last updated: August 19th, 2026"""

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from datetime import date, timedelta
import subprocess

#####################################################################
# Ideally (doing a lot of heavy working here) this is the only block that needs to be edited.
# Unless of course you want to tweak how the plots look.
#####################################################################
# Campaign Information:
campaign_type = 'mc' # 'data' or 'mc'.
target = 249946 # If running an MC campaign, enter the number of files you want to process, for data campaigns this will the size of the input dataset so will be redefined later in the code.
input_dataset = r"aurora_SBND2026A_gen2_BNBLight_DevSample_prodgenie_corsika_proton_rockbox0p1_sbnd_CV_v10_14_02_03_reco1_sbnd" # Input dataset for data campaigns. Ignored if MC campaign is run.
output_dataset = r"mc_SBND2026A_prodgenie_corsika_proton_rockbox0p1_sbnd_PDS_detvar_Sample3_v10_14_02_0602_flatcaf_sbnd" # This dataset's progress is being plotted in the graph. crucial element.

start_date = date(2026, 8, 15) # Start date of the campaign
recovery_start_date = None # True date the recovery campaign started. Leave as None if recovery hasn't started yet -- the script will then predict when it will start instead of predicting an end date.
today_date = date(2026, 8, 23)
output_directory = "/exp/sbnd/app/users/sdas1/slides/sbnd_production/Update on PDS Detvar 3 Campaign/plots" # Directory where the plots will be saved.
#####################################################################


def format_date(d):
    """Format date as '6-May'. Tkes datetime.date object and returns a string."""
    return f"{d.day}-{d.strftime('%b')}"

def get_date_range(start, end):
    """Return list of formatted date labels from start..end inclusive.

    Works across month and year boundaries.
    """
    if start > end:
        return []
    days = (end - start).days
    return [format_date(start + timedelta(days=i)) for i in range(days + 1)]



def files_from_dataset(dataset, target_date):
    """Return the number of files in the dataset created before the target date. Make sure
    your environment is set up and samweb-client is active."""
    command = f"samweb list-files 'defname:{dataset} and create_date < {target_date}' --summary"
    try:
        result = subprocess.check_output(command, shell = True, executable = "/bin/bash", stderr = subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while fetching files from dataset {dataset}: {e.output}. \n Make sure your environment is set up and samweb-client is active.")
        return None
    finally:
        number_of_files = int(result.splitlines()[0].decode('utf-8').split('\t')[1])
        return number_of_files


# Target files for data campaigns
if campaign_type == 'data':
    target = files_from_dataset(input_dataset, start_date+timedelta(days=1))
    # print(f"Target number of files from dataset {input_dataset} created before {format_date(end_date)}: {target}")

# Whether the recovery campaign's start date was actually known (vs. left for us to predict)
recovery_confirmed = recovery_start_date is not None

# Today's date index, relative to the campaign start (the date axis isn't known yet -- it
# depends on the end date we're about to predict)
today_idx = (today_date - start_date).days

# Finished (green) values - estimated from the chart (values in the future date should be None)

# finished = [
#     333, 1862, 3464, 4945, 7005, 11354, 16259, 19587, 23092, 26390, 29561, 35020, 37050, 38212
# ]

# Number of files that have been finished till today_date (inclusive)
finished = [files_from_dataset(output_dataset, start_date + timedelta(days=i+1)) for i in range(today_idx + 1)]
# print(finished)

# Calculate the most recent average rate. Today's count is a partial day (today hasn't
# finished yet), so it's excluded. Similar logic for the first day. Otherwise it drags
# the average rate down and the projections look overly pessimistic.
# Rate is based on data from the second through yesterday instead.
yesterday_idx = today_idx - 1
if yesterday_idx >= 0:
    current_avg_rate = (finished[yesterday_idx] - finished[0]) / yesterday_idx
else:
    # No complete day yet (campaign started today) -- fall back to today's partial count.
    current_avg_rate = finished[today_idx] / (today_idx + 1)

MAX_PROJECTION_DAYS = 3650 # Safety cap so a stalled/zero rate can't loop forever

if not recovery_confirmed:
    # Case 1: Recovery has not started yet.
    # Each day, calculate average rate up to that day and project forward until the target
    # is reached at the current rate -- that's our estimate of when recovery will kick in.
    projected = [finished[0]]
    i = 1
    while projected[-1] < target and i <= MAX_PROJECTION_DAYS:
        if i < today_idx:
            # Use the actual average rate up to this day (today is excluded -- see above)
            avg_rate = (finished[i] - finished[0]) / i
        else:
            # Use the most recent average rate for today and future days
            avg_rate = current_avg_rate
        if avg_rate <= 0:
            print("Warning: progress rate is zero or negative, cannot predict recovery start date.")
            break
        projected.append(projected[-1] + avg_rate)
        i += 1
    projected[-1] = min(projected[-1], target)

    recovery_idx = len(projected) - 1
    recovery_start_date = start_date + timedelta(days=recovery_idx)
    end_date = recovery_start_date

    dates = get_date_range(start_date, end_date)
else:
    # Case 2: Recovery has already started -- predict the campaign end date from the rate
    # of progress since recovery began.
    assert recovery_start_date <= today_date, "recovery_start_date must be on or before today_date"
    recovery_idx = (recovery_start_date - start_date).days
    recovery_target = target - finished[recovery_idx - 1]

    # Same exclusion as above: today's count is partial, so the recovery-phase rate is
    # measured through yesterday only.
    days_since_recovery = yesterday_idx - (recovery_idx - 1)
    if days_since_recovery > 0:
        recovery_rate = (finished[yesterday_idx] - finished[recovery_idx - 1]) / days_since_recovery
    else:
        recovery_rate = current_avg_rate
    if recovery_rate <= 0:
        recovery_rate = current_avg_rate

    post_recovery_days = max(1, math.ceil(recovery_target / recovery_rate)) if recovery_rate > 0 else 1
    end_date = start_date + timedelta(days=recovery_idx - 1) + timedelta(days=post_recovery_days)

    dates = get_date_range(start_date, end_date)

    # Projected (orange) values
    projected = [0] * len(dates)
    projected[0] = finished[0]

    # Calculate average rate until recovery start date
    for i in range(1, recovery_idx):
        if i <= today_idx:
            avg_rate = (finished[i] - finished[0]) / i
        else:
            avg_rate = current_avg_rate
        projected[i] = projected[i - 1] + avg_rate

    # From recovery start date onwards, use post-recovery ramp
    start_val = projected[recovery_idx - 1]
    recovery_target_amount = target - start_val
    for j in range(post_recovery_days):
        idx = recovery_idx + j
        if idx < len(dates):
            projected[idx] = start_val + recovery_target_amount * (j + 1) / post_recovery_days

# Today's date is capped at the (now predicted) campaign end date to avoid out-of-range indices
today_date = min(today_date, end_date)
today_idx = (today_date - start_date).days

# Labels for the purple recovery line / end-date annotation, distinguishing a confirmed
# recovery start date from one this script predicted.
recovery_line_label = f"Recovery Start: {format_date(recovery_start_date)}" if recovery_confirmed else f"Predicted Recovery Start: {format_date(recovery_start_date)}"
end_date_label = f"Predicted End Date: {format_date(end_date)}"

# print("Dates:", dates)
# print("Projected:", projected)
# print("Finished:", finished)


# Plot the cumulative bar graph

x = np.arange(len(dates))
bar_width = 0.4

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor('white')
ax.set_facecolor('white')

# Plot projected bars (orange) — left of center
ax.bar(x - bar_width / 2, projected, width=bar_width, color='#FFA500', zorder=2)

# Plot finished bars (green) — right of center
ax.bar([x[i] + bar_width / 2 for i in range(len(finished))], finished, width=bar_width, color='#228B22', zorder=3)

# Failed/Unfinished bars on the end date
if today_date == end_date and target > finished[-1]:
    failed_jobs = target - finished[-1]
    ax.bar([x[today_idx] + bar_width / 2], [failed_jobs], bottom=[finished[-1]], width=bar_width, color='red', zorder=3)

# Target line (red dashed)
ax.axhline(y=target, color='red', linestyle='--', linewidth=2, label=f'Target Files', zorder=4)

# Today's date vertical line (blue dashed)
if today_idx is not None:
    ax.axvline(x=today_idx, color='blue', linestyle='--', linewidth=2, label=f"Today's Date: {format_date(today_date)}", zorder=4)

# Recovery start date vertical line (purple dashed)
ax.axvline(x=recovery_idx, color='purple', linestyle='--', linewidth=2, label=recovery_line_label, zorder=4)

# Annotation box with the predicted end date, once recovery is underway and an end date
# can actually be predicted
if recovery_confirmed:
    ax.annotate(
        end_date_label,
        xy=(0.98, 0.98), xycoords='axes fraction', ha='right', va='top',
        fontsize=13,
        bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='black', linewidth=1.5),
        zorder=5
    )

# Axes formatting
ax.set_xticks(x)
ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=12)
ax.set_ylabel('Cumulative Files', fontsize=14)
ax.set_xlabel('Date', fontsize=14)
ax.set_title('Cumulative Files Over Time', fontsize=18, fontweight='bold', pad=15)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
ax.tick_params(axis='y', labelsize=11)

# Legend — match the original order: Target, Today, Projected, Finished
projected_patch = mpatches.Patch(color='#FFA500', label='Projected Finished Files')
finished_patch = mpatches.Patch(color='#228B22', label=f'Finished Files: ~{finished[-1] / 1000:.1f}K')

# Use Line2D for the dashed lines in legend
from matplotlib.lines import Line2D
target_line = Line2D([0], [0], color='red', linestyle='--', linewidth=2, label=f'Target Files: ~ {target / 1000:.1f}K')
today_line = Line2D([0], [0], color='blue', linestyle='--', linewidth=2, label=f"Today's Date: {format_date(today_date)}")
recovery_line = Line2D([0], [0], color='purple', linestyle='--', linewidth=2, label=recovery_line_label)
handles = [target_line, today_line, recovery_line, projected_patch, finished_patch]
if today_date == end_date and target > finished[-1]:
    failed_patch = mpatches.Patch(color='red', label=f'Failed Files: ~{(target - finished[-1]) / 1000:.1f}K')
    handles.append(failed_patch)

ax.legend(
    handles=handles,
    fontsize=12,
    loc='best',
    frameon=True,
    edgecolor='black'
)
plt.grid()
plt.ylim(0, max(max(projected), max(finished)) * 1.1)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.savefig(f'{output_directory}/campaign_progress_till_{format_date(today_date)}_cumulative.png', dpi=300)
plt.tight_layout()
plt.close()



# Plot the Daily report bar graph

# Compute finished_per_day
finished_per_day = [finished[i] - finished[i-1] if i > 0 else finished[i] for i in range(len(finished))]
projected_per_day = [projected[i] - projected[i-1] if i > 0 else projected[i] for i in range(len(projected))]

x = np.arange(len(dates))
bar_width = 0.4

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor('white')
ax.set_facecolor('white')

# Plot projected bars (orange) — left of center
ax.bar(x - bar_width / 2, projected_per_day, width=bar_width, color='#FFA500', label='Projected Daily Files', zorder=2)

# Plot finished bars (green) — right of center
ax.bar([x[i] + bar_width / 2 for i in range(len(finished_per_day))], finished_per_day, width=bar_width, color='#228B22', zorder=3)

# Failed/Unfinished bars on the end date
if today_date == end_date and target > finished[-1]:
    failed_jobs = target - finished[-1]
    ax.bar([x[today_idx] + bar_width / 2], [failed_jobs], bottom=[finished_per_day[-1]], width=bar_width, color='red', zorder=3)

# Today's date vertical line (blue dashed)
ax.axvline(x=today_idx, color='blue', linestyle='--', linewidth=2, label=f"Today's Date: {format_date(today_date)}", zorder=4)

# Recovery start date vertical line (purple dashed)
ax.axvline(x=recovery_idx, color='purple', linestyle='--', linewidth=2, label=recovery_line_label, zorder=4)

# Annotation box with the predicted end date, once recovery is underway and an end date
# can actually be predicted
if recovery_confirmed:
    ax.annotate(
        end_date_label,
        xy=(0.98, 0.98), xycoords='axes fraction', ha='right', va='top',
        fontsize=13,
        bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor='black', linewidth=1.5),
        zorder=5
    )

# Axes formatting
ax.set_xticks(x)
ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=12)
ax.set_ylabel('Daily Files', fontsize=14)
ax.set_xlabel('Date', fontsize=14)
ax.set_title('Finished Files Per Day', fontsize=18, fontweight='bold', pad=15)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
ax.tick_params(axis='y', labelsize=11)

# Legend — match the original order: Target, Today, Projected, Finished
projected_patch = mpatches.Patch(color='#FFA500', label='Projected Finished Files')
finished_patch = mpatches.Patch(color='#228B22', label=f'Finished Files: ~{finished[-1] / 1000:.1f}K')

handles = [recovery_line, today_line, projected_patch, finished_patch]
if today_date == end_date and target > finished[-1]:
    failed_patch = mpatches.Patch(color='red', label=f'Failed Files: ~{(target - finished[-1]) / 1000:.1f}K')
    handles.append(failed_patch)

ax.legend(
    handles=handles,
    fontsize=12,
    loc='best',
    frameon=True,
    edgecolor='black'
)
plt.grid()
plt.ylim(0, max(max(projected_per_day), max(finished_per_day)) * 1.1)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.savefig(f'{output_directory}/campaign_progress_till_{format_date(today_date)}_daily.png', dpi=300)
plt.tight_layout()
plt.close()
