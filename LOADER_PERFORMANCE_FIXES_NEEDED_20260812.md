# Loader Performance Issues - What Must Be Fixed

**Status**: ROOT CAUSE IDENTIFIED  
**Priority**: CRITICAL - Blocks daily signal generation  
**Updated**: 2026-08-12 02:00

---

## The Real Problem (Not Backfills)

The loaders aren't failing due to data quality or missing dependencies. They're **timing out due to performance issues**:

### buy_sell_daily: 17-Minute Execution Time
- **Expected**: ~2-3 minutes to generate signals for 4,000 symbols
- **Actual**: 17 minutes (1,033 seconds) before timeout/failure
- **Impact**: Data stays 1+ days stale; Phase 7 uses outdated signals

**Root Cause**: Signal generation algorithm is too slow
- Options: Database query too expensive, algorithm O(n²) or worse, no caching

**Fix Required**: Profile and optimize BuySignalGenerator
1. Add query timing logs to _prepare_batch_context() and signal generation
2. Check if GROUP BY price_daily query uses proper indexes (appears OK based on schema)
3. Check if signal algorithm does N+1 queries per symbol
4. Consider caching technical indicator calculations
5. Profile Python execution time vs database time

---

### company_info_sec: 7 Consecutive Failures
- **Blocker**: SEC Edgar API rate limiter (2 req/sec) on 4,900 symbols
- **Math**: 4,900 symbols ÷ 2 req/sec = 2,450s minimum (41 minutes)
- **Previous timeout**: 15 minutes (impossible)
- **Increased timeout**: 120 minutes (still fails - 7 consecutive failures)

**Issues**:
1. Even with 120-min timeout, still failing
2. May be hitting IP-level rate limiting after too many requests
3. Possible SEC API unavailability or network issues
4. Could be inter-symbol pacing delay too aggressive

**Fix Required**: Network diagnostics + API investigation
1. Check if SEC API is rejecting requests after N calls
2. Verify network connectivity to SEC Edgar API
3. Consider implementing exponential backoff with jitter
4. Add per-request timeout with retry logic
5. Fallback: Mark table as data_unavailable if SEC API consistently unavailable

---

### technical_data_daily: Quick Failure (114 seconds)
- **Symptoms**: Runs for 2 minutes then fails
- **No error message** in database (data_loader_status.error_message is empty)

**This is a separate bug**: Loader crashes but doesn't record error

**Fix Required**: Error message tracking
1. Ensure all loader exceptions are logged to data_loader_status.error_message
2. Add try/except at loader entry point to capture stderr
3. Run with stderr capture to see actual error

---

## What We've Already Fixed

1. ✅ **Identified backfill pattern** (data manually inserted without running loaders)
2. ✅ **Created recovery script** (fix_loader_status_drift.py)
3. ✅ **Reset stuck loaders** (insider_transaction_velocity, technical_data_daily)
4. ✅ **Documented root causes** (LOADER_STATUS_AUDIT_20260812.md)

## What Still Needs Fixing

| Loader | Issue Type | Severity | Status |
|--------|-----------|----------|--------|
| **buy_sell_daily** | Performance (17 min execution) | CRITICAL | Needs profiling + optimization |
| **company_info_sec** | API rate limiting + too many failures | CRITICAL | Needs network diagnostics |
| **technical_data_daily** | Unknown (no error logged) | HIGH | Needs error message tracking |
| **company_profile** | Unknown | MEDIUM | Needs profiling |
| **sec_valuations** | Likely API timeout | MEDIUM | Needs retry logic |

---

## Action Plan

### Immediate (Today)
1. **buy_sell_daily profiling**:
   - Add timing logs: query time + signal generation time
   - Identify if bottleneck is database or Python
   - Run with smaller universe (1,000 symbols) to estimate scaling

2. **Error logging**:
   - Add stderr capture to technical_data_daily runs
   - Run it directly to see the actual error

### Short-term (This Week)
1. **buy_sell_daily optimization**:
   - Based on profiling: optimize database queries OR algorithm
   - Consider caching pre-computed values
   - Test with production parallelism setting

2. **company_info_sec investigation**:
   - Test SEC API connectivity directly
   - Check if IP-level blocking is occurring
   - Verify network routing to SEC

### Medium-term
1. Implement error logging for all loaders
2. Add performance monitoring/alerts
3. Parallelize where possible (respect API rate limits)

---

## Key Principle

**These are PERFORMANCE/RELIABILITY issues, not DATA QUALITY issues.**

Backfilling won't help - it just masks the real problem. The next time buy_sell_daily times out, we'll have fresh backfilled data but the underlying issue remains unsolved.

**Permanent fix requires**:
1. Understanding WHY it's slow
2. Fixing the root cause
3. Monitoring to prevent regression

---

## Success Criteria

- [ ] buy_sell_daily completes in <3 minutes
- [ ] company_info_sec succeeds within 120-minute timeout (or is marked data_unavailable)
- [ ] technical_data_daily reports actual error message on failure
- [ ] All loaders log complete execution times + error messages
- [ ] No manual backfills - all data comes from actual loader execution
