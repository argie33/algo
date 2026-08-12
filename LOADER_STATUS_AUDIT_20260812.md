# Loader Status Drift Audit - 2026-08-12

**Status**: ACTIVE INVESTIGATION  
**Created**: 2026-08-12 01:30  
**Last Updated**: 2026-08-12 01:45

---

## Executive Summary

The orchestrator is experiencing **loader status drift** - tables have fresh data but are marked PENDING/FAILED in the status table, causing Phase 1 to halt or loaders to not run. This is NOT a data freshness problem; it's a bookkeeping problem that prevents real loaders from executing.

**Finding**: This week's "tons of stale tables" issue was NOT due to missing runs - it was due to backfills being applied without proper loader execution. Now that we've identified and are resetting the status, we need to actually RUN these loaders to fix the root causes, not backfill more data.

---

## Affected Loaders (6 Critical)

### 1. ❌ PENDING with 3+ Failures → MANUAL INVESTIGATION REQUIRED

| Loader | Status | Failures | Last Data | Issue |
|--------|--------|----------|-----------|-------|
| **company_info_sec** | PENDING | 3 | None | SEC rate limiter (2 req/sec) × 4,940 symbols = 41+ min minimum; timeout was 15 min |

**Action**: Requires investigation into why this keeps failing. Likely data quality or external API issues.

---

### 2. ⚠️ FAILED with 1-2 Failures → CAN RETRY

| Loader | Status | Failures | Last Data | Root Cause |
|--------|--------|----------|-----------|-----------|
| **buy_sell_daily** | FAILED | 1 | 08-10 (1d old) | Unknown - needs actual execution to diagnose |
| **quality_metrics** | FAILED | 1 | None (reset) | Depends on value_quality_growth; not yet executed |
| **growth_metrics** | FAILED | 1 | None (reset) | Depends on value_quality_growth; not yet executed |
| **sec_valuations** | FAILED | 2 | None (reset) | Timeout/external API issue; was 30 min timeout, increased to 90 min |
| **company_profile** | FAILED | 2 | 08-09 (2d old) | Unknown - needs actual execution to diagnose |

**Status**: Script reset these from PENDING → FAILED so they can retry on next pipeline run.

---

## Root Cause Analysis

### The Backfill Problem
This week, when loaders failed or got stuck, the response was to manually load data via SQL:
```sql
-- Instead of running the loader, data was inserted directly:
INSERT INTO growth_metrics (...) VALUES (...);
INSERT INTO quality_metrics (...) VALUES (...);
```

**Result**: Tables have fresh data, but `data_loader_status` was never updated to COMPLETED, leaving them marked PENDING. Phase 1 saw PENDING status and either:
- Halted (treating PENDING as "not ready")
- Allowed dependent loaders to run on stale upstream data (causing cascading failures)

### Why Loaders Failed

1. **SEC Rate Limiter**: company_info_sec and sec_valuations hit SEC Edgar API limits
   - 2 req/sec rate limiter on 4,900 symbols = 41+ min minimum
   - Timeouts were inadequate (15-30 min)
   - **Fix deployed**: Increased to 120 min for company_info, 90 min for sec_valuations

2. **Yfinance Throttling**: Analyst loaders (analyst_sentiment, analyst_upgrades)
   - Parallelism=4 triggered shared-IP circuit breaker (84%+ failures)
   - **Fix deployed**: Forced parallelism=1 locally

3. **Unknown Failures**: buy_sell_daily, company_profile, quality_metrics
   - Never executed or failed with undiagnosed errors
   - Need actual run to see stderr/traceback

---

## Script Changes Made

### 1. fix_loader_status_drift.py (NEW)
Automatically:
- Detects RUNNING loaders stuck >30 minutes (crashed processes)
- Cleans stale lock files (>2 hours old)
- Resets PENDING loaders with <3 consecutive failures to FAILED (ready to retry)
- Validates dependencies before allowing retry

**Result**: 3 loaders reset from PENDING → FAILED:
- growth_metrics
- quality_metrics
- sec_valuations

Company_info_sec NOT reset (has 3 failures - needs manual investigation).

---

## Next Steps to Actually Fix Loaders

### 1. Understand Real Failures (Do NOT Backfill)
Run each failed loader in isolation to see the actual error:
```bash
# See the real error, not just "FAILED" status
timeout 120 python loaders/load_buy_sell_daily.py 2>&1 | tail -50
timeout 120 python loaders/load_company_profile.py 2>&1 | tail -50
timeout 120 python loaders/load_sec_valuations.py 2>&1 | tail -50
```

### 2. Fix Issues in Loader Code
Once errors are known:
- Patch data quality issues
- Add retry logic for transient failures
- Adjust timeouts for rate-limited APIs
- Add proper error messages to identify root cause

### 3. Clear Status and Retry
Only after code is fixed:
```bash
python scripts/fix_loader_status_drift.py  # Reset PENDING → FAILED
python scripts/local_loader_scheduler.py --now metrics  # Retry the pipeline
```

### 4. Monitor for Recurrence
After successful run:
- Verify data_loader_status shows COMPLETED (not PENDING)
- Check that data has today's date (not backfilled midnight)
- Monitor logs for warnings (watermark checks, coverage thresholds)

---

## What NOT to Do

❌ **DO NOT manually backfill data** without fixing the loader
- Creates silent data quality issues downstream (Phase 7 signals, Phase 8 execution)
- Prevents real bugs from being discovered
- Leads to "failed Monday" cascading failures

❌ **DO NOT just update status to COMPLETED** if you didn't run the loader
- Lies to Phase 1 validation
- Hides dependency freshness issues
- Enables signal generation on stale/incomplete upstream data

❌ **DO NOT skip Phase 1 dependency validation**
- It exists because buy_sell_daily was running on incomplete technical_data_daily (5 days stale)
- Signals were using stale price data → wrong positions → losses

---

## Loader Dependency Graph

```
prices, technical  
    ↓
buy_sell_daily
    ↓  
signal_quality  
    ↓  
algo_metrics_daily

financial_statements, valuations, analyst_earnings_estimates
    ↓
value_quality_growth
    ↓
enhanced_quality_growth
    ↓
stock_scores  
    ↓
algo_metrics_daily
```

All 7 dependencies are now enforced in `local_loader_scheduler.py`.

---

## Remaining Known Issues

1. **company_info_sec** (3 consecutive failures)
   - Needs investigation into why it keeps failing despite timeout increase
   - Candidates: SEC API unavailable, IP blocking, network issues

2. **Yfinance parallelism forced to 1**
   - Makes analyst pipeline run 6+ hours instead of 2-3 hours
   - Optimization study in progress, not yet implemented

3. **External API failure categorization**
   - Can't distinguish "data unavailable (404)" from "real failure (timeout)"
   - Current workaround: 35% max_fail_rate acceptance

---

## Success Criteria

- [ ] buy_sell_daily runs to COMPLETED (no backfill)
- [ ] quality_metrics runs to COMPLETED
- [ ] growth_metrics runs to COMPLETED  
- [ ] sec_valuations runs to COMPLETED
- [ ] company_info_sec investigated and fixed (or marked unavailable)
- [ ] All status transitions recorded in data_loader_status (no NULL execution_started/completed)
- [ ] Phase 1 validates all dependencies have fresh data before downstream loaders
- [ ] No more manual SQL backfills without running actual loaders

---

## Key Principle

**Status table is ground truth.** If you load data:
1. Run the actual loader (`python loaders/load_xxx.py`)
2. Let it mark its own status (execution_started, execution_completed, COMPLETED)
3. If loader fails, fix the loader code, not the data

Backfilling data bypasses all safety checks and creates technical debt for next time.
