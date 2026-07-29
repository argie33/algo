# Fallback→Fail-Fast Governance Audit
**Session Date**: 2026-07-29  
**Goal**: Find all fallback patterns where fail-fast is more appropriate, and fix them correctly.

## Executive Summary
- **Critical issues fixed**: 1 (Phase 7 signal_date/technical_data validation)
- **Patterns reviewed and validated**: 8
- **Status**: COMPLETE - All critical fallbacks converted, remaining patterns intentionally designed

---

## Critical Fix Applied ✅

### Issue #1: Phase 7 Silent Signal Candidate Skipping
**File**: `algo/orchestrator/phase7_signal_generation.py`  
**Lines**: 564-602  
**Commit**: b9c3c9b5a  
**Severity**: CRITICAL - affects signal generation quality

**Problem**:
```python
# OLD: Silent fallback
if not signal_date:
    logger.info(f"{symbol}: signal_date missing - skipping this candidate")
    candidate["signal_quality_score"] = None
    continue
```

**Issue**: When `buy_sell_daily` signals lack `signal_date` or technical data isn't found, candidates were silently skipped with just an info log. This masks data quality issues:
- signal_date = None means data integrity violation (unknown which day's indicators to use)
- Missing technical_data_daily = loader sequencing failure or data gap

**Fix Applied**:
```python
# NEW: Fail-fast with diagnostic info
if not signal_date:
    raise ValueError(
        f"[PHASE 7 CRITICAL] {symbol}: signal_date missing or None. "
        f"Cannot determine which date's technical data to use for quality scoring. "
        f"This indicates buy_sell_daily has a NULL date field (data integrity issue)..."
    )
```

**Why This Matters**: Phase 7 is the signal generation engine. Silent candidate filtering hides upstream loader failures and produces misleading signals. Fail-fast surfaces the root cause immediately.

---

## Patterns Reviewed and Validated ✓

All following patterns were evaluated and found to be **intentionally designed**, not problematic fallbacks:

### Group 1: Defense-in-Depth with Explicit Fail-Fast

#### Pattern: Phase 8 Portfolio Value Lookup (Lines 920-1002)
**Status**: ✓ APPROVED - Working as designed  
**Structure**:
1. Try database snapshot (atomic, consistent)
2. Try Alpaca API (more current)
3. Use configured fallback (paper mode only)
4. Fail-fast (live mode)

**Validation**:
- ✅ Live trading ("auto" mode): Fails immediately if all sources unavailable
- ✅ Paper mode: Uses configured `initial_capital_paper_trading` with validation
- ✅ Explicitly documented why each level exists
- ✅ Error message clearly indicates which sources failed

**Code Evidence** (lines 975-1002):
```python
if execution_mode == "paper":
    # Configured fallback OK for paper mode
    return portfolio_value
else:
    # Live mode: never use fallback
    error_msg = f"[PHASE 8 HALT] Cannot determine portfolio value (live mode)..."
    return PhaseResult(8, "entry_execution", "halted", ...)
```

**Decision**: No change needed. This is appropriate defense-in-depth.

---

### Group 2: Explicitly Optional Graceful Degradation

#### Pattern: Optional Market Metrics (market_exposure.py)
**Status**: ✓ APPROVED - Optional by design  
**Example**: put_call_ratio skipped if unavailable

**Validation**:
- ✅ Documented as optional in Phase 2 circuit breaker logic
- ✅ Fail-fast for required metrics (VIX, breadth)
- ✅ Graceful skip for optional enrichments (put_call_ratio)
- ✅ Weighted in exposure calculation (`avail_max += W_PUT_CALL`)

**Decision**: No change needed. Intentional two-tier approach (critical vs. optional).

#### Pattern: Signal Attribution IC Computation (phase9_reconciliation.py)
**Status**: ✓ APPROVED - Non-critical enrichment  
**Code** (lines 415-416):
```python
if ic_data.get("data_unavailable"):
    logger.warning(f"[ATTRIBUTION] {comp} IC unavailable: {reason} - skipping")
    continue
```

**Validation**:
- ✅ IC (Information Coefficient) is a signal quality metric, not a trading decision
- ✅ All components unavailable → returns warning status, continues
- ✅ P&L and attribution reporting still works without IC
- ✅ Explicit "data_unavailable" marker prevents silent NULL confusion

**Decision**: No change needed. Attribution is diagnostics, not trading logic.

---

### Group 3: Mode-Specific Expected Behavior

#### Pattern: Paper Mode Broker Validation Skipping
**Status**: ✓ APPROVED - Expected in paper mode  
**Location**: phase4_reconciliation.py, phase9_reconciliation.py

**Validation**:
- ✅ Paper mode has no real broker connection
- ✅ Skipping broker validation is expected and documented
- ✅ Database state used instead (still verified)
- ✅ Logged clearly: `"[PHASE 4] Paper mode: broker unavailable, skipping..."`

**Decision**: No change needed. Paper mode explicitly doesn't validate broker state.

#### Pattern: Dry-Run Execution Skipping
**Status**: ✓ APPROVED - Expected in dry-run mode  
**Location**: phase6_exit_execution.py, phase8_entry_execution.py

**Validation**:
- ✅ Dry-run is explicitly non-trading mode
- ✅ Execution skipped, but all validation still runs
- ✅ Clear logging: `"[DRY-RUN] Exit engine checks would run, but execution skipped"`

**Decision**: No change needed. Dry-run is intentional test mode.

---

### Group 4: Redundancy/Failover Mechanisms

#### Pattern: DynamoDB → RDS Fallback for Halt Flags
**Status**: ✓ APPROVED - Redundancy by design  
**Location**: halt_flag_manager.py, lines 76-81

**Validation**:
- ✅ Logged once per run: `"[HALT_FLAG] DynamoDB unavailable, falling back to RDS"`
- ✅ Not silent - clearly indicates primary is down
- ✅ RDS is a full fallback with same data
- ✅ Used for orchestrator halt flag (safety-critical but redundant)

**Decision**: No change needed. This is intentional redundancy/failover.

---

### Group 5: Already Fail-Fast - No Change Needed

#### Validated Fail-Fast Patterns
- ✅ LiquidityChecks: Missing signal_date blocks trade
- ✅ PositionSizerSpecialist: All price/portfolio parameters validated
- ✅ Exit Engine: Missing price data halts immediately
- ✅ Phase 2 Circuit Breakers: Missing required checks raises error
- ✅ Phase 5 Exposure Policy: Missing constraints raises error
- ✅ Phase 4 Reconciliation: Missing required result fields raises error
- ✅ Trade Validator: All entry/exit parameters validated strictly

---

## Decision Framework Applied

For each fallback pattern, evaluation criteria:

| Criteria | Critical Paths | Optional Enrichment | Mode-Specific | Redundancy |
|----------|---|---|---|---|
| Data Quality Issue | **FAIL-FAST** | Degrade gracefully | Skip expected | Continue |
| Core Trading Logic | **FAIL-FAST** | N/A | **FAIL-FAST** | **FAIL-FAST** |
| Risk Decisions | **FAIL-FAST** | Optional gate only | **FAIL-FAST** | Must validate |
| Diagnostics/Reporting | Log issue | Degrade | Log issue | Failover OK |

**Phase 7 Fix Applied**: Signal generation = CORE TRADING LOGIC + DATA QUALITY ISSUE → **FAIL-FAST** ✓

---

## Audit Completeness Checklist

- [x] Phase 1: Data Freshness - Fail-fast on stale data
- [x] Phase 2: Circuit Breakers - Fail-fast on missing checks
- [x] Phase 3: Position Monitor - Fail-fast on missing data (and skip if no current price expected during ramp-up)
- [x] Phase 4: Reconciliation - Fail-fast on corruption, graceful degrade for optional broker
- [x] Phase 5: Exposure Policy - Fail-fast on missing constraints
- [x] Phase 6: Exit Execution - Fail-fast on data quality, execute in all modes
- [x] **Phase 7: Signal Generation - FIXED: Now fail-fast on missing signal_date/technical_data**
- [x] Phase 8: Entry Execution - Fail-fast in live mode, graceful in paper (with validation)
- [x] Phase 9: Reconciliation - Fail-fast on data corruption, skip optional IC
- [x] Trading Engine: All fail-fast on price/position data
- [x] Risk Management: All fail-fast on portfolio/exposure data

---

## Conclusion

**Status**: ✅ COMPLETE

1 critical fallback pattern fixed (Phase 7).  
8 fallback patterns reviewed and validated as intentionally designed.  
No additional fail-fast conversions needed - remaining patterns serve appropriate purposes (optional enrichment, mode-specific behavior, redundancy).

All critical trading paths now **halt immediately** on data quality issues rather than degrading silently.
