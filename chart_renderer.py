"""Chart rendering -- the bar-chart layout (projected vs finished bars, target/
today/recovery reference lines, end-date annotation, legend) shared by both the
cumulative and daily campaign-progress plots.

Purely presentational: takes plain data and pre-formatted labels, doesn't know
about campaigns, SAM, or how a projection was computed.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np


def render_bar_chart(
    dates, projected_series, finished_series, *,
    finished_total, target, show_target_line,
    today_idx, today_label,
    recovery_idx, show_recovery_line, recovery_line_label,
    end_date_label, show_end_date_annotation,
    failed_files,
    title, ylabel, filename,
):
    """Render one projected-vs-finished bar chart and save it to `filename`.

    `finished_series`/`projected_series` are what's actually drawn as bars --
    cumulative totals for the cumulative chart, per-day diffs for the daily chart.
    `finished_total` is always the campaign's cumulative total so far, used for the
    "Finished Files" legend figure regardless of which series is being drawn.
    `failed_files` is the shortfall to draw as a red bar on the final day (0 for none).
    """
    x = np.arange(len(dates))
    bar_width = 0.4

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # Plot projected bars (orange) — left of center
    ax.bar(x - bar_width / 2, projected_series, width=bar_width, color='#FFA500', zorder=2)

    # Plot finished bars (green) — right of center
    ax.bar([x[i] + bar_width / 2 for i in range(len(finished_series))], finished_series, width=bar_width, color='#228B22', zorder=3)

    # Failed/Unfinished bar on the end date
    if failed_files:
        ax.bar([x[today_idx] + bar_width / 2], [failed_files], bottom=[finished_series[-1]], width=bar_width, color='red', zorder=3)

    handles = []

    # Target line (red dashed) -- only the cumulative chart has a fixed target to draw
    if show_target_line:
        ax.axhline(y=target, color='red', linestyle='--', linewidth=2, label='Target Files', zorder=4)
        handles.append(Line2D([0], [0], color='red', linestyle='--', linewidth=2, label=f'Target Files: ~ {target / 1000:.1f}K'))

    # Today's date vertical line (blue dashed)
    ax.axvline(x=today_idx, color='blue', linestyle='--', linewidth=2, label=today_label, zorder=4)
    handles.append(Line2D([0], [0], color='blue', linestyle='--', linewidth=2, label=today_label))

    # Recovery start date vertical line (purple dashed) -- suppressed once progress
    # hits the recovery-skip threshold, since there's no recovery portion to show
    if show_recovery_line:
        ax.axvline(x=recovery_idx, color='purple', linestyle='--', linewidth=2, label=recovery_line_label, zorder=4)
        handles.append(Line2D([0], [0], color='purple', linestyle='--', linewidth=2, label=recovery_line_label))

    # Annotation box with the predicted end date, once there's an actual end-date
    # prediction to show (recovery underway, or recovery skipped per policy)
    if show_end_date_annotation:
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
    ax.set_ylabel(ylabel, fontsize=14)
    ax.set_xlabel('Date', fontsize=14)
    ax.set_title(title, fontsize=18, fontweight='bold', pad=15)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
    ax.tick_params(axis='y', labelsize=11)

    # Legend — match the original order: Target, Today, Recovery, Projected, Finished, Failed
    handles.append(mpatches.Patch(color='#FFA500', label='Projected Finished Files'))
    handles.append(mpatches.Patch(color='#228B22', label=f'Finished Files: ~{finished_total / 1000:.1f}K'))
    if failed_files:
        handles.append(mpatches.Patch(color='red', label=f'Failed Files: ~{failed_files / 1000:.1f}K'))

    ax.legend(
        handles=handles,
        fontsize=12,
        loc='best',
        frameon=True,
        edgecolor='black'
    )
    plt.grid()
    plt.ylim(0, max(max(projected_series), max(finished_series)) * 1.1)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.savefig(filename, dpi=300)
    plt.tight_layout()
    plt.close()
