# Production Readiness & Quality Audit - Comprehensive Plan
**Date:** 2026-05-08  
**Status:** Phase 2 (Resource Leak Fixes In Progress)  
**Risk Level:** MEDIUM (Robustness issues, not correctness)

---

## WHAT WE'VE ACCOMPLISHED

### ✓ Phase 1 Complete: Critical Imports Fixed
- [x] utils/greeks_calculator.py: `import numpy as np`
- [x] algo_governance.py: `import numpy as np, json`
- [x] algo_performance.py: `import numpy as np, json`
- [x] tests/backtest/test_backtest_regression.py: `import json`
- **Result:** All import errors resolved; greeks tests 30/30 PASS

### ✓ Phase 2 In Progress: Critical Path Resource Leaks Fixed
Fixed 4 phase-critical signal methods with try-finally cleanup:
- [x] algo_signals.py: minervini_trend_template (✓ tested)
- [x] algo_signals.py: weinstein_stage (✓ tested)
- [x] algo_signals.py: base_detection (✓ tested)
- [x] algo_signals.py: stage2_phase (✓ tested)
- **Result:** All 4 signal methods tested and working

### ✓ End-to-End Verification (from 2026-05-07)
- [x] All 7 orchestrator phases functional
- [x] 50+ trades synced to Alpaca
- [x] Signal filtering working correctly
- [x] Exit engine executing properly
- **Result:** System is logically correct; 0 trades is correct for market conditions

---

## REMAINING QUALITY ISSUES (Priority Order)

### TIER 1: Phase-Critical (Must Fix Before Deployment)

#### 1. Connection Leaks in Supporting Modules
**Severity:** HIGH (causes connection exhaustion under load)

| Module | Method | Issue | Status |
|--------|--------|-------|--------|
| algo_position_monitor.py | __init__, check_sector_concentration | Missing try-finally | NEEDS FIX |
| algo_trade_executor.py | execute_trade, execute_exit, cancel_trade | Verify protection | NEEDS REVIEW |
| algo_advanced_filters.py | general | 1 unprotected connection | NEEDS FIX |
| algo_backtest.py | general | 1 unprotected connection | NEEDS FIX |
| algo_data_patrol.py | scan | 1 unprotected connection | NEEDS FIX |
| algo_data_remediation.py | general | 1 unprotected connection | NEEDS FIX |
| algo_filter_pipeline.py | execute | 1 unprotected connection | NEEDS FIX |
| algo_governance.py | general | 1 unprotected connection | NEEDS FIX |
| algo_market_events.py | general | 1 unprotected connection | NEEDS FIX |
| algo_market_exposure.py | general | 1 unprotected connection | NEEDS FIX |
| algo_model_governance.py | general | 1 unprotected connection | NEEDS FIX |
| algo_orchestrator.py | Multiple | Mostly protected ✓ | VERIFIED |
| algo_position_monitor.py | review_positions | 1 unprotected | NEEDS FIX |
| algo_risk_and_concentration.py | general | 1 unprotected | NEEDS FIX |
| algo_tca.py | general | 1 unprotected | NEEDS FIX |
| algo_var.py | general | Protected ✓ | VERIFIED |
| algo_wfo.py | general | 1 unprotected | NEEDS FIX |
| backtest.py | general | 1 unprotected | NEEDS FIX |

**Total Remaining:** ~17 modules need fixes

#### 2. Unprotected Connections in Data Loaders
**Severity:** MEDIUM (but runs frequently in background)

| Module | Status |
|--------|--------|
| loadpricedaily.py | NEEDS FIX |
| loadmultisource_ohlcv.py | NEEDS FIX |
| lib/performance.py | NEEDS FIX |
| FULL_BUILD_VERIFICATION.py | NEEDS FIX (3 instances) |

#### 3. Signal Methods Still Missing Cleanup (10 remaining)
**Severity:** MEDIUM (not in main path, but used in analysis)

All in algo_signals.py:
- [ ] td_sequential
- [ ] vcp_detection
- [ ] classify_base_type
- [ ] base_type_stop
- [ ] three_weeks_tight
- [ ] high_tight_flag
- [ ] power_trend
- [ ] distribution_days
- [ ] mansfield_rs
- [ ] pivot_breakout

### TIER 2: Exception-Masking Returns (75+ instances)

**Severity:** MEDIUM (hides errors, makes debugging harder)

Pattern: `return` statements in `finally:` blocks that swallow exceptions.

**Example:**
```python
try:
    # ... operation ...
except Exception as e:
    print(f"Error: {e}")
finally:
    return result  # ← masks exception, returns anyway
```

**Files with this pattern:**
- algo_backtest.py:472
- algo_data_freshness.py:131
- algo_governance.py:246
- algo_model_governance.py:302
- algo_orchestrator.py:1116
- [70+ more locations]

**Fix:** Remove `return` from finally blocks; do cleanup before returning.

### TIER 3: Data Quality Issues

#### 1. Stage 2 Price Data Gap
**Status:** Identified but not critical  
**Symbols:** BRK.B, LEN.B, WSO.B  
**Impact:** Won't affect today's trading, but blocks future Stage 2 entries  
**Fix:** Review and expand loader watchlist for large-cap support

#### 2. Missing 50-Day SMA Data
**Status:** TBD  
**Impact:** Unknown—need to verify technical_data_daily is fully populated

---

## IMPLEMENTATION PLAN

### Phase 3: Fix All Tier 1 Connection Leaks (Today)
**Effort:** ~1 hour per module group  
**Steps:**
1. Fix algo_position_monitor.py (2 instances)
2. Fix algo_trade_executor.py (verify 3 methods)
3. Fix algo_advanced_filters.py, algo_governance.py, algo_market_events.py (small modules, 5 min each)
4. Fix remaining supporting modules (algo_backtest.py, algo_wfo.py, algo_tca.py, etc.)
5. **Test:** Run signal methods + position monitor + trade executor

### Phase 4: Fix Tier 2 Data Loaders (Parallel)
**Effort:** ~30 min  
**Steps:**
1. Fix loadpricedaily.py
2. Fix loadmultisource_ohlcv.py
3. Fix lib/performance.py
4. Fix FULL_BUILD_VERIFICATION.py
5. **Test:** Verify data loader runs without connection errors

### Phase 5: Fix Remaining Signal Methods (Optional but recommended)
**Effort:** ~30 min  
**Steps:**
1. Add try-finally to remaining 10 methods in algo_signals.py
2. Test all signal methods comprehensively
3. **Result:** 100% signal method protection

### Phase 6: Address Exception-Masking Returns (Longer term)
**Effort:** ~2-3 hours  
**Impact:** Improved debugging visibility  
**Steps:**
1. Identify all 75+ locations (script-assisted)
2. Refactor to remove finally-block returns
3. Test each change

### Phase 7: Data Quality Fixes (Low priority, ongoing)
**Effort:** ~1 hour  
**Steps:**
1. Review get_active_symbols() for Stage 2 coverage
2. Verify technical_data_daily is fully backfilled
3. Add watchdog for data gaps

---

## RISK ASSESSMENT

### Current Risks
1. **Connection Exhaustion** (HIGH): System works fine in single runs but may fail under sustained load or concurrent runs. 
   - **Mitigation:** Fix Tier 1 leaks today.
2. **Hidden Errors** (MEDIUM): Exception-masking returns hide real failures.
   - **Mitigation:** Add connection pool monitoring and logs.
3. **Data Gaps** (LOW): Stage 2 loader coverage incomplete.
   - **Mitigation:** Monitor and backfill as needed.

### What's NOT Broken
- ✓ Core algorithm logic (verified end-to-end)
- ✓ Trade execution & Alpaca sync
- ✓ Risk metrics & circuit breakers
- ✓ Exit engine & position management
- ✓ Signal generation & filtering

---

## TESTING CHECKLIST

### Before Deployment
- [ ] Run full orchestrator 5 times in succession (tests connection leaks)
- [ ] Check database connection count before/after
- [ ] Run pytest full suite (greeks, backtest, unit tests)
- [ ] Verify no "too many connections" errors in logs
- [ ] Test signal methods on 50 random symbols
- [ ] Verify loaders complete without errors

### Monitoring Setup (Recommended)
```
- Alert if postgres connections > 80% of pool
- Alert if exceptions with "connection" or "timeout"
- Monitor orchestrator run duration (should be < 30s)
- Track phase execution times
```

---

## SUMMARY & NEXT STEPS

**Status:** System is functionally correct but has robustness issues.

**Priority Order:**
1. **Today:** Fix all Tier 1 connection leaks (critical path modules) ← YOU ARE HERE
2. **Today:** Run full pipeline verification
3. **Tomorrow:** Fix Tier 2 loaders + remaining signal methods
4. **This week:** Address exception-masking returns
5. **Ongoing:** Monitor data quality gaps

**Deliverables:**
- [x] Quality audit document (QUALITY_AUDIT_2026_05_08.md)
- [x] Production readiness plan (THIS FILE)
- [ ] All Tier 1 fixes complete
- [ ] Full pipeline verification report
- [ ] Monitoring setup documentation

**Confidence Level:**
- **Before Tier 1 fixes:** 60% (works, but risky under load)
- **After Tier 1 fixes:** 85% (robust, good error handling)
- **After Tier 2 fixes:** 90% (complete resource cleanup)
- **After Tier 3 fixes:** 95% (no hidden errors, full visibility)

