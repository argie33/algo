# Critical Issues Found in Recent Runs

## Status
Date: 2026-07-25
Logs Analyzed: orch_final_verification.log, orch_verification_run.log

## Issues Identified

### 1. **FIXED** - Type Error in Phase 8 Risk Calculation
**Severity:** CRITICAL  
**File:** `algo/orchestrator/phase8_entry_execution.py:85`  
**Issue:** `unsupported operand type(s) for /: 'decimal.Decimal' and 'float'`  
**Root Cause:** Mixed Decimal and float types in division operation  
**Fix Applied:** Added explicit float conversion before arithmetic (commit pending)

```python
# BEFORE (line 85):
current_risk_pct = (total_risk_dollars / portfolio_value * 100.0)

# AFTER:
total_risk_dollars_f = float(total_risk_dollars)
portfolio_value_f = float(portfolio_value)
current_risk_pct = (total_risk_dollars_f / portfolio_value_f * 100.0)
```

### 2. **NEEDS INVESTIGATION** - Duplicate Position Detection Not Preventing Entry
**Severity:** CRITICAL  
**File:** `algo/trading/executor_entry_handler.py` + `check_handler_strategies.py`  
**Issue:** 
- Log shows: `WARNING:algo.trading.trade_validator:DUPLICATE SIGNAL: SEIC|99.32|89.13|2026-07-24`
- But trade still attempted: `INFO:algo.trading.executor:[ENTRY] SEIC: PAPER mode - creating LOCAL order TRD-49916EA91E`
- Database constraint violation: `duplicate key value violates unique constraint "algo_trades_symbol_open_positions_idx"`

**Root Cause:** 
- Duplicate detection is working (warning is logged)
- But validation is not blocking the trade
- Possible race condition between validation and insertion
- OR the validation result is not being properly checked before insertion

**Investigation Needed:**
- Check if `_validate_entry_conditions` is properly returning False when duplicate detected
- Verify FingerprintCheckHandler.process() is being called and returning correct values
- Check for race conditions in concurrent validation checks

### 3. **ISSUE** - Signal Quality Scores Lock Contention  
**Severity:** HIGH  
**File:** `Phase 7 signal generation`  
**Issue:**
- Lock acquisition failing after 3 retries: "signal_quality_scores lock will expire in 7200s"
- Results in 0 symbols getting quality scores recomputed
- But phase 7 continues with fallback (uses 100 signals from buy_sell_daily)

**Root Cause:**
- Stale lock from previous run not being released
- Lock timeout set to 7200s (2 hours) is too long
- Multiple orchestrator runs trying to acquire same lock

**Fix Needed:**
- Check for orphaned locks in database
- Reduce lock timeout or implement lock cleanup
- Add early detection of stale locks

### 4. **WARNING** - Phase 8 Pending Orders Guard  
**Severity:** MEDIUM (Expected behavior)  
**File:** `Phase 8`  
**Issue:** `[PHASE 8 PENDING ORDERS GUARD] Blocking Phase 8: 2 positions created in last 10 min`  
**Status:** Working as designed - guard correctly blocking entries when recent orders may still be filling
**Action:** None - this is correct behavior

## Summary

**Issues Fixed:**
1. ✅ Type error in Phase 8 risk calculation - Commit 8c8bcc0bd
   - Added explicit float() conversion before Decimal/float division
   
2. ✅ Signal quality scores lock contention - Commit b2b3c2432
   - Reduced lock timeout from 7200s to 600s in LOCAL_MODE
   - Faster recovery from crashed loaders during development
   - Production mode keeps 7200s for slow loaders

**Issues Requiring Further Investigation:**
3. ⚠️ **CRITICAL** - Duplicate position detection not blocking entry (NEEDS INVESTIGATION)
   - Symptom: DUPLICATE SIGNAL warning logged but trade still attempted
   - Root cause: Unknown - validation logic appears correct but not functioning
   - Debug logging added to trace validation flow on next run
   - Status: Awaiting retest when market opens (Monday 2026-07-29)
   - Commits: 8c8bcc0bd (added debug logging)

**Next Steps:**
1. Wait for market to open (Monday 2026-07-29)
2. Rerun orchestrator to generate fresh logs with debug logging
3. Analyze logs to identify why duplicate detection fails to block entry
4. Fix duplicate detection bug
5. Verify all 9 phases complete successfully

**Testing Plan:**
- Monday morning: Run orchestrator with new debug logging
- Check logs for FingerprintCheckHandler output
- Trace validation loop to see all check results
- Fix identified issues
- Retest until all phases pass cleanly
