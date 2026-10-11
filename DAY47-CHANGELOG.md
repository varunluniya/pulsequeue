# Day 47 changelog — PulseQueue

## Finding

`service.py`'s `learn()` re-pulled and re-grouped every decision+outcome
pair into per-ESI stats on every call, with no timestamp filter — the same
full-rescan pattern found across the portfolio (Guide 5's Mistake 5),
adapted here to a per-ESI-bucketed aggregation rather than a single total.

## Changes

- `gen4/memory.py`, `gen4/feedback.py` — pulled in unchanged from the
  LendFair reference fix (byte-identical kernel across the shared `gen4/`
  architecture): `fact_history` table + `add_fact()` history fix,
  `decisions(outcome_since=...)`, the `outcome_ts` bug fix in `_select()`,
  the `(system, ts DESC)` index, and the `new_rows_since` /
  `mark_processed` / `accumulate` / `incremental_calibration` primitives.

- `service.py`
  - `learn()` rewritten: pulls only outcomes since the last watermark via
    `new_rows_since()` (`LEARN_KEY = "pulsequeue_learn"`,
    `LEARN_GRACE_DAYS = 1` — PulseQueue's outcome lag is near-instant per
    `seed.py`, so a 1-day grace window is generous), groups the new rows by
    ESI level, and merges flagged/true-positive/missed-upgrade counts into
    per-ESI running totals via `accumulate()` instead of re-deriving them
    from the full history every call. Precision and missed-upgrade-rate
    thresholds for growth-rate proposals are now read from the accumulated
    totals.

- `tests/test_incremental_learning.py` — new test proving `learn()`
  accumulates per-ESI flagged counts correctly across repeated calls
  without double-counting, and picks up new decisions on a later call.

## Verification

- `pytest -q` → 24/24 passed (23 original + 1 new).
- `run_evals.py` → GATE PASS, 100%/100%, unchanged.
- `seed.py --reset` → per-ESI flag performance and pending growth-rate
  proposals (`['growth:esi2', 'growth:esi3', 'growth:esi4']`) match the
  pre-fix structure exactly.

No behavioral change in any observable output.
