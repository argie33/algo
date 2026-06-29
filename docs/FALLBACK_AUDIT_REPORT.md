# Fallback Elimination Audit Report
**Date**: 2026-06-29  
**Status**: CRITICAL FIXES COMPLETE | HIGH-SEVERITY FIXES IN PROGRESS  
**Scope**: Comprehensive audit of silent fallbacks across algo, loaders, signals, and risk modules

---

## Executive Summary

Comprehensive codebase audit identified **13 major fallback anti-patterns** that were silently degrading financial decision accuracy. Signal generation, risk calculations, and position sizing were all operating on incomplete or fake data without explicit markers.

**CRITICAL Issues**: 3 fixed ✅  
**HIGH Issues**: 10 identified, requires individual mitigation  
**MEDIUM Issues**: 3 identified, inconsistency/context loss  

---

## CRITICAL SEVERITY - FIXED ✅

### 1. signal_momentum.py: Silent False Returns on Missing Market Data

**Issue**: Pivot breakout and pocket pivot patterns returned `False` when critical volume/price data was missing, making it impossible to distinguish "pattern didn't fire" from "data missing."

**Lines**: 39-45, 201-213, 260-285, 327  
**Commit**: d69beab9b (Remove silent fallbacks and improve logging)

**Fixes Applied**:
- `td_sequential()`: Changed `return {count: 0}` → `raise ValueError` when < 14 bars
- `pivot_breakout()`: Changed `return {breakout: False}` → `raise ValueError` when pivot/volume missing
- `pocket_pivot()`: Changed `return {pivot: False}` → `raise ValueError` when price/volume missing

**Impact**: Position entries no longer occur on degraded technical signals; missing data now triggers audit alerts.

---

### 2. market_factor_calculator.py: Silent (0.0, 0.0) Returns for Missing Market Risk Factors

**Issue**: When market factors (VIX, breadth, credit spreads) returned None, `_wt_pts()` silently returned `(0.0, 0.0)`, removing them from exposure calculation.

**Lines**: 26-43  
**Commit**: d69beab9b

**Fix Applied**:
- `_wt_pts()`: Changed `return (0.0, 0.0)` → `raise ValueError` when factor score is None

**Impact**: Missing risk factors now block position sizing instead of silently reweighting remaining factors. Prevents portfolio oversizing when market data is incomplete.

---

### 3. attribution.py: Fake Zero IC Values Mask Insufficient Sample Sizes

**Issue**: IC calculation returned `{ic_value: 0, ic_pvalue: 1.0}` when < 10 closed trades, identical to "component has zero predictive power."

**Lines**: 95-97, 177-178, 242-245  
**Commit**: d69beab9b

**Fixes Applied**:
- `compute_ic()`: Changed `ic_value: 0` → `data_unavailable: True, reason: "insufficient_trades"`
- `compute_ic_by_regime()`: Changed default fallback to "caution" → `continue` (skip trades with missing regime data)

**Impact**: Dashboard no longer shows false signal degradation; analytics can distinguish "no data" from "weak signal."

---

## HIGH SEVERITY - IDENTIFIED & REQUIRING MITIGATION

### 4. notifications.py: Silent Empty List on Database Failure ⚠️

**File**: `algo/reporting/notifications.py:49`  
**Issue**: Returns `[]` on database error, making it impossible to distinguish "no recent events" from "database failed."

**Status**: Fix applied in current session (not yet committed)  
**Mitigation**: Raise `RuntimeError` on database failures to propagate errors explicitly.

---

### 5-7. Loaders with Silent Empty Lists ⚠️

**Files**:
- `loaders/load_trend_criteria_data.py:140`
- `loaders/price_transformer.py:319`
- `loaders/load_market_constituents.py:397`

**Issue**: Return `[]` when data unavailable, callers can't distinguish "no data" from "empty result."

**Status**: Partially mitigated (load_trend_criteria_data has wrapper checks; others need explicit markers)  
**Mitigation**: Return `[{"symbol": sym, "data_unavailable": True, "reason": "..."}]` instead of `[]`.

---

### 8. signal_patterns.py: Ambiguous None for Volume Dryup ⚠️

**File**: `algo/signals/signal_patterns.py:117`  
**Issue**: Sets `volume_dryup: None` when < 50 bars, ambiguous in return dict.

**Status**: Fix applied in current session (not yet committed)  
**Mitigation**: Return explicit `volume_dryup_unavailable: True` flag when data insufficient.

---

### 9. load_swing_trader_scores.py: Silent Zero on Empty Batch ⚠️

**File**: `loaders/load_swing_trader_scores.py:410-411`  
**Issue**: Returns `0` (success code) when DataFrame is empty, hiding upstream compute failures.

**Status**: Fix applied in current session (not yet committed)  
**Mitigation**: Raise `ValueError` if DataFrame empty before insert.

---

### 10. load_stock_scores.py: Silent None Returns ⚠️

**File**: `loaders/load_stock_scores.py:113-118`  
**Issue**: Returns None from compute function; wrapper handles it but intermediate None values can leak.

**Status**: Identified  
**Mitigation**: Ensure all compute functions return explicit data_unavailable markers instead of None.

---

### 11. load_market_health_daily.py: Inconsistent Logging ⚠️

**File**: `loaders/load_market_health_daily.py:66-72`  
**Issue**: Some failures log and return codes; others raise exceptions. Inconsistent error handling.

**Status**: Identified  
**Mitigation**: Standardize on exception-raising for all critical failures.

---

### 12. load_market_constituents.py: Russell 2000 Optional Enrichment ⚠️

**File**: `loaders/load_market_constituents.py:393-397`  
**Issue**: Returns empty list for optional enrichment; wrapper handles gracefully but pattern is fragile.

**Status**: Identified  
**Mitigation**: Document "optional enrichment" vs "critical data" in all loaders.

---

### 13. sector_rotation.py: Exception Masking ⚠️

**File**: `algo/signals/sector_rotation.py:101-102`  
**Issue**: All exceptions caught and re-raised generically, losing specificity.

**Status**: Identified  
**Mitigation**: Preserve exception context with `from e`; add data quality context to error messages.

---

## MEDIUM SEVERITY - IDENTIFIED

### Field Name Inconsistency

**Issue**: Different loaders use inconsistent data_unavailable field names:
- Some: `data_unavailable: True`
- Some: `data_completeness: False`
- Some: implicit empty list

**Impact**: Downstream validation expecting standard markers fails.

**Mitigation**: Standardize on `data_unavailable: True, reason: "<reason_string>"` across all loaders.

---

### Exception Masking & Context Loss

Multiple modules catch and re-raise exceptions without preserving data quality context.

**Mitigation**: Always use `from e` to preserve chain; add context about what data was expected.

---

## Governance & Prevention

**Enforced Patterns** (from `steering/GOVERNANCE.md`):

1. **Fail-Fast on Critical Data**: Missing critical financial data raises, never silently defaults
2. **Explicit Unavailability Markers**: Optional data returns `data_unavailable: True, reason: "..."` not None/empty
3. **No Secondary Fallbacks**: Never silently fall back to alternate data sources or synthetic values
4. **Logged Visibility**: Data quality issues logged at WARNING/ERROR (not DEBUG) for ops visibility

**Pre-Commit Validation**:
- ✅ mypy strict type checking (catches None returns)
- ✅ Custom validators for data_unavailable markers
- ✅ Grep patterns for ".get(" with empty defaults (still catching legacy patterns)

---

## Next Steps

**Immediate (This Session)**:
1. ✅ Identify all 13 fallback patterns (complete)
2. ✅ Fix CRITICAL severity issues (complete)
3. 🔄 Fix HIGH severity issues in signal paths (in progress)
4. 📋 Standardize data_unavailable field naming

**Follow-Up (Next Sprint)**:
1. Audit all loaders for silent empty list returns
2. Standardize exception handling across all signal modules
3. Add data quality context to error messages
4. Extend pre-commit validators for field name consistency

---

## Testing & Verification

All fixes validated with:
- ✅ mypy strict (type safety)
- ✅ Pre-commit hooks (lint, format)
- ✅ Integration tests for fail-fast behavior

Recommended manual verification:
- [ ] Run with missing market health data
- [ ] Run with stale technical indicators  
- [ ] Run with incomplete SEC financials
- [ ] Monitor logs for "data_unavailable" markers
- [ ] Verify position sizing rejects on missing factors

---

## References

- **Steering**: `steering/GOVERNANCE.md` (fail-fast design, credential handling, logging discipline)
- **Operations**: `steering/OPERATIONS.md` (CI/CD procedures, troubleshooting)
- **Recent Commits**:
  - d69beab9b: Remove silent fallbacks and improve logging
  - fbece3466: Remove silent defaults for critical financial data

---

**Auditor**: Claude Code (Haiku 4.5)  
**Completion**: 2026-06-29 02:30 UTC  
**Next Review**: After high-severity fixes are applied
