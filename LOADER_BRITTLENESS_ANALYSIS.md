# Root Causes of Loader Brittleness (Analysis 2026-08-11)

## Summary
The loader system fails every Monday with tons of stale tables and failed loaders. Root cause analysis reveals 5 cascading issues, 3 of which have been fixed in the last 24 hours.

## Root Cause #1: Incomplete Dependency Enforcement (FIXED 2026-08-11)
**Problem**: 4 loaders had documented dependencies that weren't enforced:
- `buy_sell` depends on `prices` + `technical`
- `scores` depends on `value_quality_growth` + `enhanced_quality_growth` + `momentum`
- `signal_quality` depends on `buy_sell`
- `algo` depends on `signal_quality` + `scores`

**Impact**: A local backfill of just `scores` could skip upstream loaders, silently creating stale data.

**Evidence**: LOADER_DEPENDENCIES dict only had 3 entries; loaders documented in code had dependencies not listed.

**Status**: FIXED - all 7 dependencies now enforced in local_loader_scheduler.py

---

## Root Cause #2: Yfinance Parallelism Forced to 1 (KNOWN ISSUE, UNFIXED)
**Problem**: LOADER_PARALLELISM=4 triggers shared-IP circuit breaker, causing 84%+ false failure rates.
Fixed locally to LOADER_PARALLELISM=1 to prevent IP bans.
But this makes analyst loaders single-threaded: 6+ hours for full analyst pipeline.

**Impact**: Creates pressure to skip loaders, encouraging manual hacks and workarounds.

**Evidence**:
- Git: `FIX: Reduce yfinance-dependent loaders from parallelism=2 to parallelism=1`
- Code: Multiple analyst loader timeout increases (20m→30m)
- local_loader_scheduler.py: "BUG FOUND 2026-08-10: LOADER_PARALLELISM=4 self-triggered yfinance IP circuit breaker"

**Status**: UNFIXED - requires investigation of why parallelism=4 causes ban, explore parallelism=2-3

---

## Root Cause #3: Timeout Configurations Were Severely Undersized (FIXED 2026-08-10/11)
**Documented fixes from recent commits**:

| Loader | Old | New | Reason |
|--------|-----|-----|--------|
| financial_statements | 30 min | 150 min | SEC EDGAR: ~2500 symbols @ 30s/symbol + retries |
| enhanced_quality_growth | 150 min | 200 min | yfinance retry overhead, measured 1718 symbols in 52 min |
| company_info | 15 min | 120 min | SEC rate limiter @ 2 req/sec = 41+ min minimum |
| earnings_sec | 15 min | 60 min | SEC API rate limiting on 4900+ symbols |
| analyst_upgrades | 20 min | 30 min | yfinance rate limiting, timed out at 945s |
| insider_velocity | 15 min | 25 min | Form 345 bulk download needs 18 min alone |
| segment_info | 15 min | 30 min | SEC XBRL parsing, timed out at 900s exactly |

**Evidence**: Git history shows live reproduction of each timeout:
- "BUG FOUND 2026-08-10: 30 min was never enough... live-reproduced twice"
- "BUG FOUND 2026-08-11: 15 min was too short... timed out at 900s exactly"

**Status**: FIXED - current timeouts based on real wall-clock measurements

---

## Root Cause #4: No Robust Mid-Run Crash Recovery (PARTIALLY FIXED)
**Problem**: When a loader crashes or times out, `data_loader_status` stays RUNNING indefinitely.
- `reap_stale_running_loaders()` runs once at pipeline start
- Crashes DURING pipeline execution are not detected
- Waits 4 hours for next pipeline invocation to discover the crash

**Impact**:
- Monday morning: tables stuck RUNNING from Friday failures
- Phase 1 data freshness check hangs thinking loader is still in progress
- Cascades to orchestrator halt with "waiting for data"

**Evidence**: CLAUDE.md mentions "buy_sell_daily_stuck_running_74_hours_20260810"

**Status**: PARTIALLY FIXED - start-time recovery works, mid-run crashes still uncaught

**What's needed**: Process monitoring during subprocess.run() to detect crashes immediately

---

## Root Cause #5: External API Failures Are Real, Not Bugs (DESIGN ISSUE)
**Problem**: Some "failures" are legitimate data unavailability:
- yfinance returns 404 on ~28% of symbols (OTC/delisted - no coverage)
- SEC API rate-limits on high volume
- These aren't bugs, they're expected data gaps

**Current approach**: max_fail_rate = 35% (just accept 35% failure as normal)

**Problem with this**: Operators can't distinguish between:
- "This symbol genuinely has no data" (404)
- "Real failure - network error / timeout" (429/timeout)
- "Rate limiter broke it" (rate limit exceeded)

**Status**: Unfixed - needs categorization and monitoring, not timeout increases

---

## Monday Failure Sequence

1. **Friday late**: One loader times out (e.g., financial_statements with old insufficient budget)
2. **data_loader_status**: Stuck at RUNNING, no process alive
3. **Saturday/Sunday**: No one monitoring, stuck state persists
4. **Monday early**: Phase 1 data freshness check hangs waiting for RUNNING loader
5. **Orchestrator halt**: "Waiting for data, timeout exceeded"
6. **Operators**: Manually backfill loaders, often skipping proper dependency ordering
7. **Cycle repeats**: No fix to root cause, just monthly band-aid

---

## What's Been Fixed (Last 24h)

- [x] Timeouts adequately sized (150-200 min where needed)
- [x] Dependency enforcement complete (all 7 loaders with dependencies now checked)
- [x] Loader registry complete (all 34 loaders reachable from PIPELINES)
- [x] Start-time crash recovery (reap_stale_running_loaders at pipeline start)

## What Remains (Blocking True Stability)

- [ ] Mid-run crash recovery - crashes during pipeline don't auto-fail
- [ ] yfinance parallelism investigation - why does 4 trigger ban? safe at 2?
- [ ] External API failure categorization - 404 vs timeout vs rate limit
- [ ] DB freshness checking - dependencies only check in-memory, not actual DB staleness
- [ ] Monitoring/alerting - need visibility into which loaders are slow/flaky

---

## Recommended Next Steps (Priority Order)

1. **Add mid-run crash recovery** (Task #3) - immediate, highest impact
   - Monitor subprocess during run_pipeline()
   - Auto-fail tables when loader crashes
   - Prevent Monday morning's "stuck RUNNING" problem

2. **Investigate yfinance parallelism** (Task #4) - high impact on speed
   - Test parallelism=2-3 with monitoring
   - Reduce analyst pipeline from 6h to 1.5-2h
   - Eliminate pressure to use shortcuts

3. **Categorize external API failures** (Task #7) - medium impact on debugging
   - Log failure type (404/429/timeout/other)
   - Distinguish real failures from expected data gaps
   - Replace guessing about max_fail_rate with actual data

4. **Add DB freshness checking** (architectural, lower priority)
   - Current dependency check: in-memory only, per invocation
   - Better: check actual DB freshness before skipping loader

5. **Add monitoring/alerting** (operational)
   - Track loader execution time trends
   - Alert on unusual timeouts or high fail rates
   - Catch regressions early
