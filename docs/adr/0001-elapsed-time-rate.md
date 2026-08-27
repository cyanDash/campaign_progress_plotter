# Rate is elapsed wall-clock time, not a day count

The progress rate used for projections used to divide by an integer day count,
explicitly excluding the first day and "today" because both are partial days —
production doesn't start exactly at midnight, and "today" isn't over yet.
Excluding them entirely threw away real data and made projections overly
pessimistic. We divide by true elapsed time (`now - campaign_start_dt`, in
fractional days) instead: partial days get their correct fractional weight
automatically, so nothing needs to be excluded. See `campaign_start_dt` in
[ADR-0002](0002-sam-derived-start-dates.md) for where the anchor comes from.
