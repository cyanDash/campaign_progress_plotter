# Campaign and recovery start dates come from SAM, not manual config

`start_date` and `recovery_start_date` used to be hand-typed config, which
drifted from reality and had to be updated by hand every run. We derive them
instead: `start_date` from the output dataset definition's SAM creation
timestamp (`samweb describe-definition`'s `Creation Date`), and
`recovery_start_date` from whether a `{input_dataset}_{campaign}_recovery_campaign`
dataset definition exists in SAM, using its creation timestamp if so. This
also gives an *exact* timestamp (not a hand-typed date defaulted to midnight),
which [ADR-0001](0001-elapsed-time-rate.md)'s rate calculation depends on.

Trade-off: this makes the script depend on a specific SAM dataset-naming
convention (`{input_dataset}_{campaign}_recovery_campaign`) that isn't
enforced anywhere — if a campaign's recovery dataset doesn't follow it, the
script will silently treat recovery as not-yet-started. See
[ADR-0003](0003-recovery-skip-overrides-existence.md) for why dataset
existence isn't trusted as proof recovery actually ran, even when found.
