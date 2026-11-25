"""Chart rendering -- the bar-chart layout (projected vs finished bars, target/
today/recovery reference lines, end-date annotation, legend) shared by both the
cumulative and daily campaign-progress plots.

Purely presentational: takes plain data and pre-formatted labels, doesn't know
about campaigns, SAM, or how a projection was computed.
"""

import matplotlib
matplotlib.use("Agg")  # file output only; a set DISPLAY (ssh -X) must not pick an X backend
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np

from window_jobs import latest_limits


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


WINDOW_COLORS = ['#9a9a96', '#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']
# Worker status colors: exit 0, running, then one per non-zero exit code.
OK_COLOR = '#2f7fa8'
RUNNING_COLOR = '#b5a23a'
FAIL_COLORS = ['#d9622b', '#a61c3c', '#7b4fb0', '#8c6d31', '#d55e9c', '#3d3d3d']
LIMIT_COLOR = '#8a5cc7'
# Exit codes seen on the grid keep one color from report to report.
KNOWN_EXIT_COLORS = {9: '#d9622b', 88: '#a61c3c'}


def status_label(worker):
    """'running', or 'exit <code>'."""
    return 'running' if worker['exit'] is None else f"exit {worker['exit']}"


def status_colors(workers):
    """{label: color} for every status among `workers`, the same in every
    histogram of one report: exit 0 blue, running yellow, each non-zero exit
    code its own color: KNOWN_EXIT_COLORS, else the spare FAIL_COLORS."""
    codes = sorted({w['exit'] for w in workers if w['exit'] not in (None, 0)})
    colors = {'exit 0': OK_COLOR, 'running': RUNNING_COLOR}
    spare = [c for c in FAIL_COLORS if c not in KNOWN_EXIT_COLORS.values()]
    for code in codes:
        colors[f'exit {code}'] = KNOWN_EXIT_COLORS.get(code) or spare[len(colors) % len(spare)]
    return colors


def _draw_window_bars(ax, labels, series):
    """Grouped bars, one group per split window, on `ax`.

    `series` is an ordered {name: [count per window]} whose first entry is the
    input; every other series gets a red "missing n" under a group when its
    count falls short of the input (the worst shortfall is shown).
    """
    names = list(series)
    n = len(names)
    w = 0.13 if n > 2 else 0.3
    x = np.arange(len(labels))
    top = max(1, max(max(v) for v in series.values()))
    crowded = len(labels) > 10  # a month of windows: rotate the dates, shrink the numbers

    for i, name in enumerate(names):
        pos = x + (i - (n - 1) / 2) * (w + 0.01)
        ax.bar(pos, series[name], w, label=name, color=WINDOW_COLORS[i % len(WINDOW_COLORS)], zorder=3)
        for p, v in zip(pos, series[name]):
            ax.text(p, v + top * 0.01, str(v), ha='center', va='bottom', fontsize=5 if crowded else 7, rotation=90 if crowded else 0)
    inputs = series[names[0]]
    for xi, j in zip(x, range(len(labels))):
        missing = inputs[j] - min(series[k][j] for k in names[1:])
        if missing:
            ax.annotate(f'missing {missing}', xy=(xi, 0), xycoords=('data', 'axes fraction'), xytext=(0, -74 if crowded else -30),
                        textcoords='offset points', ha='center', fontsize=8, color='#c0392b')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8 if crowded else 9, rotation=90 if crowded else 0)
    ax.set_ylabel('files')
    ax.set_ylim(0, top * 1.5)
    ax.grid(axis='y', color='#e3e2de', zorder=0)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.legend(ncol=n, frameon=False, fontsize=8, loc='upper left', bbox_to_anchor=(0, 1.0))


def render_window_chart(labels, series, *, title, filename):
    """Render grouped bars, one group per split window, and save to `filename`."""
    crowded = len(labels) > 10
    fig, ax = plt.subplots(figsize=(max(10, 0.5 * len(labels)), 5.8), dpi=200)
    _draw_window_bars(ax, labels, series)
    ax.set_title(title, fontsize=11)
    fig.subplots_adjust(bottom=0.31 if crowded else 0.17)
    fig.savefig(filename)
    plt.close(fig)


def stack_counts(workers, field, bin_width, n_bins):
    """Per-bin counts of `workers[field]`, one list of length n_bins per status
    label: 'exit 0' first, then the non-zero exit codes in order, 'running'
    last, only for statuses that occur. A worker without the field is skipped;
    a value past the last bin goes in the last one."""
    counts = {}
    for w in workers:
        value = w.get(field)
        if value is None:
            continue
        bins = counts.setdefault(status_label(w), [0] * n_bins)
        bins[min(n_bins - 1, int(value // bin_width))] += 1

    def order(label):
        return (-1, 0) if label == 'exit 0' else ((2, 0) if label == 'running' else (1, int(label.split()[1])))
    return {label: counts[label] for label in sorted(counts, key=order)}


def _draw_histogram(ax, workers, colors, field, bin_width, n_bins, to_axis_unit, xlabel, title,
                    limit=None, limit_label=''):
    """Stacked histogram of `workers[field]` on `ax`. `limit`, in the field's
    unit, draws a dashed vertical line named `limit_label` in the legend."""
    ax.set_title(title, fontsize=10, loc='left', pad=20)
    x = np.arange(n_bins)
    ax.set_xlim(-0.7, n_bins - 0.3)
    ax.set_xticks(x[::2])
    ax.set_xticklabels([f'{to_axis_unit(i * bin_width):g}' for i in range(n_bins)][::2], fontsize=8)
    ax.set_xlabel(xlabel)
    if not workers:
        ax.text(0.5, 0.5, 'no workers', transform=ax.transAxes, ha='center', va='center', color='#8a8a85')
        ax.set_yticks([])
        for s in ('top', 'right', 'left'):
            ax.spines[s].set_visible(False)
        return
    bottom = np.zeros(n_bins)
    for label, values in stack_counts(workers, field, bin_width, n_bins).items():
        ax.bar(x, values, 0.85, bottom=bottom, color=colors[label], label=label, zorder=3)
        bottom += np.array(values)
    for xi, total in zip(x, bottom):
        if total:
            ax.text(xi, total + 0.1, str(int(total)), ha='center', va='bottom', fontsize=7)
    ax.set_ylim(0, max(1, bottom.max()) * 1.15)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_ylabel('workers')
    ax.grid(axis='y', color='#e3e2de', zorder=0)
    ax.set_axisbelow(True)
    if limit is not None:
        ax.axvline(limit / bin_width - 0.5, color=LIMIT_COLOR, linestyle='--', linewidth=1.5, zorder=4,
                   label=limit_label)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=7.5, loc='lower right', bbox_to_anchor=(1, 1.0), ncol=6)


def render_window_report(labels, series, workers, *, title, filename):
    """The window bar chart on top, then peak-memory (1 GB bins) and wall-time
    (1 h bins) histograms of `workers`: the original run on the left, the
    recovery on the right, colored by exit code. `workers` is a list of
    condor_fetcher.workers() dicts, each tagged with its Submission's `kind`
    ('slice' or 'recovery') and `submission_id`. The dashed memory request and
    wall-time limit are those of the newest Submission of each kind."""
    colors = status_colors(workers)
    columns = [('Original run', [w for w in workers if w.get('kind', 'slice') == 'slice'], 'slice'),
               ('Recovery', [w for w in workers if w.get('kind') == 'recovery'], 'recovery')]
    fig = plt.figure(figsize=(12, 13), dpi=150)
    grid = fig.add_gridspec(3, 2, height_ratios=[1.3, 1, 1], hspace=0.5, wspace=0.18, bottom=0.06, top=0.96)
    bars = fig.add_subplot(grid[0, :])
    _draw_window_bars(bars, labels, series)
    bars.set_title(title, fontsize=11)

    top_mem = max([w['mem_mb'] or 0 for w in workers] + [w.get('request_mb') or 0 for w in workers] + [0])
    top_wall = max([w['wall_h'] or 0 for w in workers] + [0])
    mem_bins = max(17, int(top_mem // 1000) + 2)
    wall_bins = max(13, int(top_wall) + 2)
    for col, (name, group, kind) in enumerate(columns):
        request, limit_h = latest_limits(workers, kind)
        mem = fig.add_subplot(grid[1, col])
        _draw_histogram(mem, group, colors, 'mem_mb', 1000, mem_bins, lambda v: v / 1000, 'peak memory (GB)',
                        f'{name}: peak memory ({len(group)} workers)', limit=request,
                        limit_label=f'request {request / 1000:.1f} GB' if request else '')
        wall = fig.add_subplot(grid[2, col])
        _draw_histogram(wall, group, colors, 'wall_h', 1, wall_bins, lambda v: v, 'wall time (h)',
                        f'{name}: wall time', limit=limit_h, limit_label=f'limit {limit_h:g} h' if limit_h else '')
    fig.savefig(filename)
    plt.close(fig)
