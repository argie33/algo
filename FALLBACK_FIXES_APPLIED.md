# FALLBACK PATTERN FIXES - Session 442

## Summary
Systematic audit of finance app codebase to identify and eliminate fallback patterns that should be fail-fast. In finance, silent data degradation is worse than halting - incomplete data should fail loudly, not gracefully degrade.

## Key Principle
**FAIL-FAST OVER GRACEFUL DEGRADATION**: In a finance app, if required data is missing or incomplete, execution must halt immediately with clear error message. Never silently accept degraded data, use fallback sources, or mask missing critical fields.

---

## FIXES APPLIED (3 Critical Issues)

### 1. loaders/load_buy_sell_daily.py (Lines 162-178)
**Issue**: Fallback pattern for price data - if 90%+ coverage not found, fell back to "most recent date regardless of coverage"  
**Risk**: Generate trading signals with incomplete universe (missing 10%+ of tradeable symbols)  
**Fix**: Now FAILS immediately with clear error requiring 90%+ coverage minimum

### 2. loaders/load_buy_sell_daily.py (Lines 344-357)  
**Issue**: Accepted 90% coverage when no 3000+ symbol complete dataset found  
**Risk**: Session 248/250 found degraded data causes 99.5% filtering downstream  
**Fix**: Enforces strict 95% minimum (4750 of 5000 symbols), NO fallback mode

### 3. algo/orchestrator/phase9_reconciliation.py (Lines 129-144)
**Issue**: Fallback sequence trying 'equity' field then 'portfolio_value' if equity missing  
**Risk**: Masks broker API schema changes, uses wrong source of truth  
**Fix**: Requires explicit 'equity' field only, fails if missing (no fallback)

---

## VERIFIED PATTERNS (Already Correct - No Action)

✅ Phase 1: Data freshness - all fail-fast, strict config validation  
✅ Phase 4: Reconciliation - explicit field checking, audit trail enforcement  
✅ Phase 7: Signal generation - no fallback to computed scores, 95% universe requirement  
✅ Position sizer: Never fallback to $100k default, strict portfolio value checks  
✅ Weight optimizer: Explicit IC data validation, raises on incomplete data  

---

## Testing Status
✅ Phase 9 signal attribution tests: PASS (3/3)  
✅ Dashboard panel tests: PASS (19/19)  
✅ Signal tests: PASS  

## Governance Principle
In trading systems, incomplete data is worse than no data. Fail loud, fail early, prevent silent portfolio degradation.
