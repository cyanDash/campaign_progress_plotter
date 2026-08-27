# "Today" freezes at the day progress crossed the skip threshold

The daily-count fetch loop (in `campaign_progress_plotter.py`) stops querying
SAM as soon as `recovery_skipped()` (see [ADR-0003](0003-recovery-skip-overrides-existence.md))
first becomes true, and treats that day — not the real current date — as
"today" for every downstream calculation (rates, bars, the predicted end
date).

Without this, running the script well after a campaign actually finished
(finished counts stay flat once done) pads the chart with meaningless flat
days out to the real "today", and dilutes the elapsed-time rate from
[ADR-0001](0001-elapsed-time-rate.md) since its denominator keeps growing
with no matching numerator. Freezing "today" at the crossing day also means
fewer SAM queries: the loop doesn't fetch days that don't affect anything.
