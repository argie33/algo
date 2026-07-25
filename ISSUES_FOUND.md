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

**Critical Issues to Fix:**
1. ✅ Type error in risk calculation (FIXED)
2. ⚠️ Duplicate position entry still being attempted despite detection (INVESTIGATING)
3. ⚠️ Signal quality scores lock contention (NEEDS FIX)

**Next Steps:**
1. Test the type error fix
2. Add detailed logging to duplicate detection to trace where validation fails
3. Review lock management in signal_quality_scores loader
4. Rerun orchestrator after fixes to verify corrections
