# Loader Brittleness Root Cause Fixes - COMPLETE

**Session**: 87 (2026-08-13)
**Status**: ✅ ALL CRITICAL ROOT CAUSES FIXED
**Previous Work**: Session 86 identified 4 critical bugs; Session 87 completed the final fix

---

## The Problem (Every Monday)

```
Monday 9 AM:  Phase 1 queries data_loader_status
              Finds 20+ stale tables and 5+ stuck RUNNING loaders
              Cannot proceed → Orchestrator halts
              No fresh data for trading

Monday 10 AM: Manual backfilling begins (patchwork)
              Operators manually run loaders
              Skip dependencies → silent stale data
              No fix to root cause, just temporary relief
```

---

## Root Causes Identified & Fixed

### ROOT CAUSE #1: Dependency Enforcement Completely Broken ✅ FIXED

**Issue**: LOADER_DEPENDENCIES dict used wrong names, so no dependencies were ever enforced

**Fix Applied**: Commit 5aff47fd2 (Session 86)
- Changed `LOADER_DEPENDENCIES["buy_sell_daily"]` → `LOADER_DEPENDENCIES["buy_sell"]`
- Changed `LOADER_DEPENDENCIES["stock_scores"]` → `LOADER_DEPENDENCIES["scores"]`
- All dependency checks now work correctly

**Impact**: `buy_sell` cannot run unless `prices` + `technical` complete first

---

### ROOT CAUSE #2: analyst_sentiment_analysis Hangs 5+ Hours ✅ FIXED

**Issue**: Second yfinance API call (analyst_price_targets) had no timeout handling

**Fix Applied**: Commit 3483d50c6 (Session 86)
- Added try/except RuntimeError around analyst_price_targets fetch
- If it times out, proceed with None values (legitimate for many stocks)
- Loader now completes even if yfinance times out

**Impact**: analyst_sentiment no longer hangs indefinitely

---

### ROOT CAUSE #3: buy_sell_daily Hangs on GROUP BY Queries ✅ FIXED

**Issue**: Large GROUP BY queries on price_daily/technical_data_daily lacked statement timeouts
- Query could wait indefinitely under table contention
- No per-statement timeout enforcement

**Fix Applied**: Commit 7b70e7193 (Session 86)
- Changed DatabaseContext from `"read"` to `"read", timeout=120`
- Added `SET statement_timeout = '120 seconds'` before queries
- Group BY queries now abort after 120s instead of hanging forever

**Impact**: buy_sell_daily has safety barrier for hung queries

---

### ROOT CAUSE #4: Loader Timeouts Completely Ignored in Production ⚠️ CRITICAL, NOW FIXED

**Issue**: Terraform and Python code used DIFFERENT env var names for timeouts:
- Terraform set `LOADER_TIMEOUT` (seconds): 300-5400s depending on loader
- Python code read `LOADER_TIMEOUT_MINUTES` (never set by Terraform)
- Result: All loaders got 120-minute default instead of intended 5-90 minutes

**Examples of Impact**:
- analyst_sentiment: intended 20 min, got 120 min
- buy_sell_daily: intended 40 min, got 120 min
- financial_statements: intended 90 min, got 120 min

**Fix Applied**: Commit 73436c388 (Session 87) - THIS MORNING
- Changed `loaders/runner.py` to read `LOADER_TIMEOUT` (what Terraform sets)
- Changed `scripts/local_loader_scheduler.py` to set `LOADER_TIMEOUT` for child processes
- Changed `algo/config/__init__.py` to read `LOADER_TIMEOUT`
- Updated unit tests to verify LOADER_TIMEOUT in seconds

**Impact**: All loaders now respect per-loader timeout configuration from Terraform

---

## Supporting Fixes (Complementary)

- **Phase 1 Stale Detection** (commit 51a7c5c9a): Detects stuck RUNNING loaders and marks FAILED
- **Dependency Validation** (commit 10dffa9d1): Validates all dependencies before running loaders
- **Cascade Prevention** (commit 12ecb61d6): Skips loaders with 3+ consecutive failures
- **Dashboard Tracking** (commit b66510240): Real-time loader status monitoring

---

## Expected Impact on Monday Reliability

### Before (Today's Behavior)
```
Monday 9 AM:  [BROKEN] Dependencies not enforced
              [BROKEN] analyst_sentiment hangs 5+ hours  
              [BROKEN] buy_sell_daily GROUP BY hangs
              [BROKEN] Loaders ignore timeout config
              → Orchestrator halts, no trading
```

### After (With All 4 Fixes)
```
Monday 9 AM:  ✅ Dependencies enforced
              ✅ analyst_sentiment times out cleanly at 20 min
              ✅ buy_sell_daily GROUP BY times out at 2 min (safe)
              ✅ All loaders respect per-loader timeouts
              
              Result: Loaders complete or fail cleanly
                      Phase 1 retries failed loaders
                      Orchestrator proceeds with fresh data
                      
Monday 3 PM:  Trading proceeds normally
```

### Expected Outcome
**Monday staleness incidents**: ~0 (from current "tons of stale tables")

Even if one loader fails:
1. Phase 1 detects failure
2. Failsafe retry automatically re-runs it
3. Orchestrator continues with best-available data
4. No manual backfilling needed

---

## Verification Checklist

✅ All 4 critical fixes committed
✅ Pre-commit hooks pass (ruff, mypy, pylint)
✅ Unit tests pass (12000 test timeout seconds verified)
✅ Type checking passes (mypy strict mode)
✅ No regression in other systems

---

## Remaining Work (Optional Improvements)

### Optimization: yfinance parallelism=2 (High Impact)
- **Current**: LOADER_PARALLELISM=1 (takes 6+ hours for analyst pipeline)
- **Target**: LOADER_PARALLELISM=2 (target 2-3 hours, 50-67% speedup)
- **Plan**: Test on analyst_sentiment + analyst_upgrades first
- **Risk**: Could trigger HTTP 429 rate limit errors
- **Status**: Investigation complete, test harness ready, not yet run

### Monitoring & Alerting (Nice-to-Have)
- Dashboard alerts for "loader timeout changed"
- Slack notifications for "loader stuck RUNNING >30 min"
- Automatic circuit breaker state logging

---

## For Next Session

1. Run `python scripts/test_yfinance_parallelism_optimization.py` to test parallelism=2
2. Monitor production loaders for 1-2 weeks to verify fixes hold
3. If parallelism test succeeds, gradually roll out to production (analyst_sentiment first, then analyst_upgrades)
4. Consider extracting loader timeout config to a single source of truth (DynamoDB or S3)

---

## Summary

**Goal**: Fix root causes of Monday brittleness (tons of stale tables, stuck loaders)
**Status**: ✅ COMPLETE

All 4 critical root causes have been identified and fixed:
1. ✅ Dependency enforcement broken (FIXED Session 86)
2. ✅ Timeout handling broken (FIXED Session 86)  
3. ✅ Statement timeouts missing (FIXED Session 86)
4. ✅ Environment variable mismatch (FIXED Session 87)

**Next step**: Verify fixes in production for 2-3 weeks, then test yfinance parallelism optimization
