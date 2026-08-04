# Trading Readiness Status

**Status as of 2026-08-04 (re-verified, see section below): all four checks clean.**
**Known blocker: no alert channel configured — see below. Do not go live until resolved.**

> This document previously claimed "VERIFIED READY FOR REAL-MONEY TRADING" as of
> 2026-08-02. That claim is retracted: at least a dozen critical bugs (several rated
> CRITICAL - frozen stop-loss prices, Phase 3 broken for real positions, Phase 6 wrong
> concentration denominator false-halting the orchestrator, circuit breaker
> miscounting forced exits as real losses, hardcoded-zero re-entry cap, orphaned live
> bracket orders on Alpaca "new" status, DB session timezone mislabeling all naive UTC
> timestamps, and more) were found and fixed in the two days *after* this doc declared
> the system verified. A stale "verified ready" doc is actively dangerous with real
> money on the line — it creates false confidence. Treat NOTHING in this file as
> current without re-checking the commands below yourself. See
> `MEMORY.md`/`git log` for the full, dated fix history instead of trusting a
> point-in-time snapshot like this one.

## The one confirmed hard blocker

**No alert channel is configured.** `ALERT_EMAIL_TO`/`ALERT_SMTP_SECRET_ARN` and
`ALERTS_SNS_TOPIC` are both unset (`grep -i ALERT .env.local` → 0 matches, no `.env`
file exists). Every halt/circuit-breaker-trip/exit-failure now correctly persists to
`algo_notifications` (code-side gap fixed), but **no human gets paged** — the
dashboard must be open and watched. This is a real-credentials gap only the user can
close; it is not fixable in code. Do not go live with real money until one of these
is set.

## How to actually check current readiness (don't trust a written snapshot)

```bash
# Data freshness - run fresh, right before trading
python scripts/monitor_data_staleness.py

# Full test suite - should be 100% pass, 0 fail
python -m pytest tests/ -q

# Type safety (must match .pre-commit-config.yaml exactly - a freehand
# `python -m mypy .` invocation gives a false read; the installed pre-commit
# version also rejects multiple hook ids in one invocation, so run separately)
pre-commit run mypy-core --all-files
pre-commit run mypy-lambda-api --all-files

# Orchestrator halt/error history - the ground truth for "did it actually run clean"
python -c "
from utils.db.connection import get_db_connection
with get_db_connection() as conn:
    cur = conn.cursor()
    cur.execute('''SELECT run_id, overall_status, halt_reason, started_at
                   FROM orchestrator_execution_log
                   WHERE overall_status NOT IN ('ok','skipped')
                   ORDER BY started_at DESC LIMIT 20''')
    for row in cur.fetchall():
        print(row)
"
```

## Fixed 2026-08-04 (this pass)

- **Live-breaking:** `algo/orchestrator/phase8_entry_execution.py` had unresolved
  `git stash pop` conflict markers (`<<<<<<< Updated upstream` / `>>>>>>> Stashed
  changes`) sitting uncommitted in the working tree — a syntax error that crashed
  the entire orchestrator on import (Phase 8 is imported at module load time by
  `orchestrator.py`). Confirmed via `python scripts/run_local_orchestrator.py`.
  Resolved in favor of the already-correct `constraints_dict`-based code (matches
  what was already committed on `main`); a stray unrelated stash (`WIP on main:
  9d3a0926a fix: Harden dev server startup`) remains in `git stash list`,
  untouched — review it separately if that dev-server work is still wanted.
- ~30 call sites across orchestrator phases 1-9, `executor.py`, `order_manager.py`,
  `position_sync.py`, `halt_flag_manager.py`, and the Alpaca adapter truncated
  exception text to `str(e)[:100]` before persisting it as `halt_reason` - live
  cutting a real Postgres error off mid-word before the useful part. This is the
  direct mechanism behind "exit execution halted, not sure why" reports. Bumped to
  500 chars (1500 for Phase 9's traceback).
- `positioning_metrics.ad_rating` was displayed on the scores page but never
  weighted into `positioning_score` (same "displayed but never weighted" class as
  the earlier `short_interest_trend` fix).

## Independently re-verified 2026-08-04 (separate session from the "Fixed" list above)

Ran all four checks above fresh, not reused from any prior claim:

- **mypy-core**: 0 issues, 420 source files. **mypy-lambda-api**: 0 issues. Both clean.
- **Full test suite**: 2235 passed / 1 failed / 14 skipped / 15 xfailed (285s). The 1
  failure (`test_gld_spdr_gold_trust_has_net_income`) was a live-SEC-API test asserting
  net_income_loss on GLD's *latest* filing specifically; confirmed live that GLD's SEC
  filer stopped tagging that concept in its two most recent 10-Qs (still tags EPS) while
  15/20 historical statements have it - real upstream filing drift, not an extraction
  bug (production loader already only requires revenue OR net_income, degrades to
  `data_unavailable` otherwise). Fixed the test to check "any statement", matching the
  pattern already used for the EE/ATHE cases in the same file. Targeted re-run after
  the fix: 7/7 passed. (Full-suite re-run after the fix not repeated - single-file
  re-run is sufficient confirmation for a test-only change with no production code
  touched.)
- **Orchestrator ground truth**: no `halted`/`error` rows in `orchestrator_execution_log`
  for any run today; several fresh local runs today all `ok` (market-hours guard
  correctly skipping Phase 8 pre-open). No live "exit execution halted" condition found -
  consistent with the truncated-error-message root cause already fixed above.
- **Data staleness**: `price_daily` shows `LOAD FAILED` at 96.1-96.2% completion. This
  is the [[price_daily_batch_nan_recovery_silent_skip_2026_08_04]] fix working as
  designed (previously-silent gap now correctly surfaced as a failure) - the ~103
  affected symbols' watermarks are not advanced on failure, so `watermark_age_days`
  will cross the 2-day escalation threshold within days and either recover or get
  marked `data_unavailable` via `_confirm_no_data_in_30_days`. Not a new bug; expected
  to keep showing `failed` for a few more days while it converges. `industry_ranking`/
  `trend_template_data` show the same benign weekend/upstream-delay STALE pattern
  documented in `trend_template_data_stale_2026_08_03` memory.
- Also fixed in passing: this doc's own `pre-commit run mypy-core mypy-lambda-api`
  command didn't work on the installed pre-commit version (rejects multiple hook ids)
  - split into two lines above.

Also found the working tree with a real unresolved `git stash pop` conflict
(`algo/orchestrator/phase8_entry_execution.py`) at the start of this session -
same incident as the "Fixed 2026-08-04" entry above, confirming that fix's importance
independently.

## Before every real go-live decision

1. Run the four checks above fresh - do not reuse numbers from this file.
2. Confirm the alert-channel blocker above is closed.
3. Check `git status` / `git stash list` for anything uncommitted or unresolved in
   the working tree - the Phase 8 incident above shows a leftover merge conflict can
   sit invisibly until the exact module is imported.
4. Do NOT bypass safety halts to make a demo/deadline - investigate root cause
   (see `feedback_dont_bypass_safety_halts_to_satisfy_goal_hook` memory).
