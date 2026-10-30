"""split_windows -- per-window input/output file counts for a campaign run with
poms_auto_submit's [split] window.

Windows are given in Central time (as in the ini) and queried in UTC (SAM's
create_date). Counting goes through any object with `count(query)`, i.e.
samweb_fetcher or a test fake.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")


def window_bounds(first_start, step, window, n):
    """Return n (start, end) UTC datetime pairs: `first_start` is a Central
    'YYYY-MM-DD HH:MM' string, each window starts `step` after the last."""
    start = datetime.strptime(first_start, "%Y-%m-%d %H:%M").replace(tzinfo=CENTRAL)
    bounds = []
    for i in range(n):
        s = start.replace(tzinfo=None) + i * step
        s = s.replace(tzinfo=CENTRAL)
        bounds.append((s.astimezone(timezone.utc), (s + window).astimezone(timezone.utc)))
    return bounds


def _stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def input_query(dataset, start, end):
    return f"defname:{dataset} and create_date >= '{_stamp(start)}' and create_date < '{_stamp(end)}'"


def output_query(definition, in_query):
    return f"defname:{definition} and ischildof:({in_query})"


def collect_window_counts(sam, input_dataset, output_definitions, bounds):
    """Return {'input': [...], <definition>: [...]} with one count per window."""
    rows = {"input": [], **{d: [] for d in output_definitions}}
    for start, end in bounds:
        iq = input_query(input_dataset, start, end)
        rows["input"].append(sam.count(iq))
        for d in output_definitions:
            rows[d].append(sam.count(output_query(d, iq)))
    return rows
