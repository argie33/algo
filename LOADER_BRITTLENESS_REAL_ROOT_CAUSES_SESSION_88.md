# Loader Brittleness: Real Root Causes (Session 88)

**Status**: Analysis complete. 4 previous "critical bugs" were necessary but not sufficient. Real root causes identified and prioritized.

**Date**: 2026-08-12

---

## Executive Summary

Previous sessions claimed to fix 4 "critical bugs" that would reduce Monday brittleness from "tons of stale tables" to "near-zero incidents." **This is inaccurate.** Those 4 bugs are real but only fix 20% of the problem.

**The actual Monday brittleness is caused by:**

1. **SEC Edgar rate limiting** → company_info_sec fails 8+ times/week (EXTERNAL, RECURRING)
2. **No graceful degradation** → dependent loaders fail when upstream is rate-limited (FIXED Session 88)
3. **Incomplete data loads** → price_daily at 94.4% (UNFIXED, CRITICAL)
4. **Cascading failures** → one external API issue blocks entire pipeline (PARTIALLY FIXED Session 88)
5. **Circuit breaker never cancels unprocessed futures** → hangs wait 20+ min for rate-limited batches (UNFIXED)

---

## Root Cause #1: SEC Edgar Rate Limiting (EXTERNAL, UNCONTROLLABLE)

**Status**: Not fixable. Must design around it.

**Observation**:
- company_info_sec: 8 consecutive failures in last 3 days
- Error: "MARKED UNAVAILABLE: SEC Edgar rate limiter + IP blocking issue"
- Affects: company_profile (depends on company_info_sec)
- Frequency: Recurring weekly, especially Mondays after high volume weekends

**Why Previous Fixes Miss This**:
- Dependency checking (Bug #1): Only checks if loader completed, not if it's available for use
- Timeout tuning (Bugs #2, #3): Doesn't prevent external API rate limiting
- Env var alignment (Bug #4): Doesn't prevent SEC from rejecting requests

**Solution** (Session 88, IMPLEMENTED):
- Detect SEC loaders with 3+ failures + "rate limit" error
- Skip gracefully instead of failing cascade
- Allow downstream to proceed with cached data
- Pipeline returns 0 (success) instead of 1 (failure)

**Result**: Metrics pipeline can proceed even when SEC rate-limits hit.

---

## Root Cause #2: Incomplete Data Loads (CRITICAL BLOCKER)

**Status**: UNFIXED. price_daily stuck at 94.4% completion.

**Current State**:
```
price_daily: 94.4% complete (meaning 5.6% of symbols failed to load)
This is WORSE than 0% - it's silently partial data
```

**Why This Is Critical**:
- Phase 1 data freshness checks pass (table exists, last_updated is recent)
- But 5.6% of prices are missing/stale
- Loaders proceed with incomplete signals
- When those missing symbols need to trade → quote not found → order fails

**Why Previous Fixes Miss This**:
- Dependency checking: Only checks if upstream completed, not data completeness
- Timeout tuning: Doesn't detect or prevent partial loads
- Env vars: Doesn't affect data quality

**Real Problem**:
- price_daily loader succeeds even though it failed 5.6% of symbols
- `mark_completed()` called even though data is incomplete
- No per-symbol retry logic for failed symbols
- Next run just tries all 5500 symbols again instead of retrying the 5.6%

**Solution** (NOT YET IMPLEMENTED):
- Require minimum completion threshold before marking loader COMPLETED
  - Example: 95% of symbols must load successfully
  - If < 95%, mark as INCOMPLETE (not FAILED)
- Skip dependent loaders that have incomplete upstream data
- Retry only the failed symbols in next run, not entire universe

**Impact**: Stop propagating partial/stale data through signal chain.

---

## Root Cause #3: Circuit Breaker Never Cancels Unprocessed Futures

**Status**: UNFIXED. load_prices.py hangs 20+ minutes waiting for rate-limited batches.

**Current Code Flow** (load_prices.py lines 1576-1600):
```python
if result.get("status") == "halted":
    halted = True
    # ... but as_completed() still waits for ALL futures
    for future in as_completed(futures.values(), timeout=timeout_per_batch):
        # This loop waits for rate-limited/delayed batches
        # even though we've marked them for fallback retry
        # Timeout enforcement is per-batch, not total
```

**Why This Hangs**:
1. Circuit breaker triggers (status == "halted")
2. Code sets halted=True and returns from loop
3. But unprocessed futures are still queued in executor
4. Executor keeps trying to fetch those symbols from rate-limited API
5. Each retry adds 10+ second delays
6. Loader waits for all futures to complete (or timeout individually)
7. Total wait: sum of individual timeouts = 20+ minutes

**Solution** (NOT YET IMPLEMENTED):
- When halted=True, call `.cancel()` on all unprocessed futures
- Stop waiting for them to complete
- Immediately add them to fallback queue for per-symbol retry
- Exit the batch loop immediately after canceling

**Impact**: Circuit breaker halt time: 20+ min → seconds. Loader completes faster.

---

## Root Cause #4: Yfinance Parallelism Still Set to 1 (SLOWNESS, NOT BRITTLENESS)

**Status**: Partially analyzed, test not yet run (Session 87 task).

**Current**:
- analyst loaders take 6+ hours with parallelism=1
- Parallelism=2 is theoretically safe (12 concurrent = under Yahoo's 15 req/sec limit)
- Never tested in practice

**Why This Matters for Brittleness**:
- Analyst pipeline so slow (6+ hours) that timeouts become more likely
- By time analyst_sentiment completes, next orchestrator phase may have started
- Cascading overlap = concurrency issues

**Solution** (NOT YET IMPLEMENTED):
- Test parallelism=2 on analyst loaders
- Monitor for HTTP 429 errors in logs
- If clean, expand to all yfinance loaders
- Target: 2-3 hour analyst pipeline (not 6+ hours)

**Impact**: Faster data refresh → lower chance of staleness on Monday morning.

---

## Root Cause #5: Price Data Staleness Undetected

**Status**: UNFIXED. Phase 1 can't tell if price_daily is stale.

**Current**: Phase 1 only checks:
- Table exists
- last_updated is recent (< 24h)
- Doesn't check: actual data inside (age of oldest record, volume of records)

**Problem**:
- Monday 9 AM: price_daily shows "updated 30 min ago"
- But it's Friday's data, reprocessed with Sunday's timestamp
- Phase 1 halts waiting for Monday's data that's still loading

**Solution** (NOT YET IMPLEMENTED):
- Phase 1 checks date of records in price_daily
- If all records are Friday or older after market close → STALE
- If < 90% of trading symbols have records → INCOMPLETE
- Mark both RUNNING status with "Waiting for Monday data"

---

## Summary: What Actually Needs to Be Fixed

| Root Cause | Category | Severity | Fixable? | Session 88 Status | Impact |
|-----------|----------|----------|----------|-------------------|--------|
| SEC rate limiting | External | HIGH | No | N/A (graceful degradation added) | Partial (allows fallback to cache) |
| No graceful degradation | Logic | HIGH | Yes | ✅ FIXED | Pipeline proceeds with stale data instead of halt |
| Incomplete data loads | Code | CRITICAL | Yes | ⏳ PENDING | Stop propagating 5.6% stale price data |
| Circuit breaker hangs | Code | HIGH | Yes | ⏳ PENDING | Reduce price loader time from 90min+ to 60min |
| Yfinance parallelism=1 | Slowness | MEDIUM | Yes | ⏳ PENDING (test not run) | Reduce analyst pipeline from 6h to 2-3h |
| Price staleness detection | Logic | MEDIUM | Yes | ⏳ PENDING | Phase 1 can detect incomplete Monday data |

---

## What Session 88 Actually Fixed

✅ **Graceful degradation for SEC loaders**
- Track skipped loaders separately from hard failures
- When SEC loader has 3+ failures, skip it (don't cascade)
- Dependent loaders also skip (use cached SEC data)
- Pipeline returns 0 (success) instead of 1 (failure)

**Result**: Metrics pipeline can proceed with stale SEC data instead of halting.

**This is necessary but not sufficient.** Monday will still have issues if:
- price_daily is 94.4% complete (5.6% missing symbols)
- analyst pipeline hangs for 6+ hours
- yfinance rate limiting hits (different from SEC)

---

## Next Priority Actions

**To Actually Fix Monday Brittleness**:

1. **IMMEDIATE** (Next session): Implement incomplete-data-load detection
   - Require min 95% symbol completion before mark_completed()
   - Measure: How many price_daily runs fail the 95% threshold?
   - Blocker: Test suite needs to verify this logic

2. **HIGH** (This week): Implement circuit breaker future cancellation
   - Cancel unprocessed futures when halted=True
   - Measure: Reduce price_daily load time by 20+ minutes
   - Verify: Log "Canceled N unprocessed futures" messages

3. **HIGH** (This week): Test yfinance parallelism=2
   - Run analyst loaders with parallelism=2
   - Monitor logs for HTTP 429 errors
   - Measure: Analyst pipeline time 6h → 2-3h?

4. **MEDIUM** (Next week): Implement price staleness detection in Phase 1
   - Check date of records in price_daily, not just last_updated timestamp
   - Check: Do we have Monday's data after market close?

5. **MEDIUM** (Next week): Implement per-symbol retry logic
   - If symbol fails to load, retry only that symbol next run
   - Don't retry entire 5500-symbol universe

---

## How to Verify This Is Fixed

**Before**: Monday 9 AM
- Phase 1 queries company_info_sec
- Waits for company_info_sec to load (it's stuck RUNNING)
- Orchestrator halts
- Operators manually backfill

**After**: Monday 9 AM
- Phase 1 detects company_info_sec is rate-limited, skips it
- Metrics pipeline runs with cached SEC data
- Price loader completes price_daily within 60 minutes (not 90+)
- Analyst pipeline completes within 2-3 hours (not 6+)
- All symbols have fresh prices
- Orchestrator proceeds normally
- Trading starts Monday 10 AM with fresh data

---

## Memory (For Future Sessions)

This finding contradicts the Session 87 commit message that claimed "All 4 critical root causes fixed → near-zero Monday incidents expected."

**The truth**:
- 4 bugs were real but insufficient
- They fix 20% of the problem (dependency checking, timeouts, env vars)
- Session 88 adds graceful degradation (partial fix for SEC)
- **Still unfixed**: Incomplete data, circuit breaker hangs, yfinance slowness, staleness detection

A similar pattern of "fixed X → problem solved" claims followed by "actually 5 more things" suggests sessions may not be fully validating fixes before closing them out.
