# Fallback Pattern Audit - Session 248

**Status:** Active Audit - HIGH-RISK patterns identified and being fixed  
**Date:** 2026-07-18  
**Goal:** Eliminate silent fallbacks and secondary data sources that mask failures in trading decisions

---

## Critical Findings

### 1. **PHASE 8: Paper Mode Synthetic Technical Data (HIGH RISK)**

**File:** `algo/orchestrator/phase8_entry_execution.py`  
**Lines:** 766-874  
**Risk Level:** HIGH - Affects position sizing and stop-loss calculations  
**Severity:** Financial Impact - synthetic ATR can cause undersized positions

**Problem:**
```python
# Lines 866-874: In paper mode, when technical data missing, uses synthetic approximations
if close is None:
    close = entry_price_hint  # Fallback to entry price
if atr is None:
    atr = close * 0.02 if close else entry_price_hint * 0.02  # Synthetic 2% approximation
if sma_50 is None:
    sma_50 = close if close else entry_price_hint  # Fallback to entry price
```

**Why This Is Wrong:**
- ATR is used for stop-loss calculation: `stop_loss = min(sma_50 - atr, entry - 2*atr)`
- 2% synthetic ATR may be wildly incorrect (actual ATR could be 0.5% or 8%)
- Wrong stop-loss → wrong position sizing → wrong risk per trade
- Synthetic data creates false signal confidence in paper-mode backtests
- This ONLY affects paper mode, but paper mode feeds decisions into live trading

**Impact:**
- Position sizer receives wrong volatility input
- Stop losses may be placed too tight (premature exits) or too wide (excess risk)
- Dashboard and historical P&L metrics built on synthetic data

**Status:** NOT FIXED YET - This is Phase 8 graceful degradation that should fail-fast instead

---

### 2. **RECONCILIATION: SQL COALESCE Entry Price Fallback (HIGH RISK)**

**File:** `algo/infrastructure/reconciliation.py`  
**Lines:** 554-577 (query), 563 specifically  
**Risk Level:** HIGH - Affects P&L calculation accuracy  
**Severity:** Data Integrity - silently masks missing trade data

**Problem:**
```sql
-- Line 563: Falls back from actual trade entry price to position average
COALESCE(NULLIF(at.entry_price, 0), ap.avg_entry_price) as avg_entry_price
```

**Why This Is Wrong:**
- If `algo_trades.entry_price` is NULL/0, silently uses position average price
- Position average may be stale or accumulated from multiple older trades
- P&L calculation then uses wrong baseline price
- If entry_price is consistently NULL, this masks a data recording bug
- No audit trail showing which fallback branch was taken

**Impact:**
- P&L reporting shows wrong values
- Circuit breaker uses wrong cost basis for concentration calculations
- Drawdown detection may trigger incorrectly (using wrong P&L)
- If entry_price population breaks, won't be detected until manual audit

**Status:** PARTIALLY ADDRESSED - Has explicit comments but no audit logging

---

### 3. **DASHBOARD API: Signal Quality Score COALESCE (MEDIUM RISK)**

**File:** `lambda/api/routes/algo_handlers/dashboard.py`  
**Line:** 1539  
**Risk Level:** MEDIUM - Affects UI display ranking  
**Severity:** User-Facing - may hide low-quality signals

**Problem:**
```sql
-- Line 1539: Sorts by signal quality but defaults missing scores to 0
ORDER BY COALESCE(s.signal_quality_score, 0) DESC NULLS LAST
```

**Why This Is Wrong:**
- Signals with NULL quality_score treated as 0 (worst quality)
- Pushed to end of dashboard ranking
- If quality scorer is broken, signals disappear from view silently
- User has no indication that data is missing vs. low quality

**Impact:**
- Valid signals may be hidden if quality scoring fails
- Dashboard ranking appears complete even with scoring gaps
- No visibility into coverage gaps

**Status:** NEEDS MONITORING

---

### 4. **DASHBOARD API: RS Percentile Synthetic Default (MEDIUM RISK)**

**File:** `lambda/api/routes/algo_handlers/dashboard.py`  
**Line:** 1674  
**Risk Level:** MEDIUM - Affects signal filtering/ranking  
**Severity:** Data Quality - treats missing momentum data as median

**Problem:**
```sql
-- Line 1674: Defaults missing RS percentile to 50.0 (median)
COALESCE(fs.rs_percentile, 50.0) AS rs_percentile
```

**Why This Is Wrong:**
- Signals with missing RS data treated as 50th percentile momentum
- If momentum scorer breaks for a sector, all signals appear as average performers
- Dashboard doesn't show data is missing
- Filtering/ranking logic treats synthetic 50.0 as real data

**Impact:**
- Missing momentum data not visible
- Signal quality appears uniform when really it's broken for some universe subset
- Users may trade on signals that lack momentum confirmation

**Status:** NEEDS MONITORING

---

## Fix Strategy

### Phase 1: FAIL-FAST for Trading-Critical Data (Immediate)

**Phase 8 Paper Mode (HIGH):**
1. Remove synthetic approximations for technical data
2. Instead of `if atr is None: atr = close * 0.02`, raise with clear error
3. Let paper mode test reveal incomplete data dependencies
4. Maintains safety boundary: data_unavailable → phase result shows "degraded", trades skipped

**Reconciliation COALESCE (HIGH):**
1. Add explicit audit logging showing fallback path taken
2. Track frequency of NULL entry_price in production
3. If >= 5% NULL rate, alert DevOps (indicates data recorder bug)
4. Future: Consider separating trade-level vs. position-level entry price into different fields

### Phase 2: Monitoring & Transparency (Short-term)

**Dashboard COALESCE patterns:**
1. Add metric: "Signals with missing quality_score (NULL count)"
2. Add metric: "Positions with missing entry_price (COALESCE usage count)"
3. Alert if any metric exceeds threshold
4. Document in dashboard data coverage panel

### Phase 3: Long-term Cleanup

1. Phase 8 technical data: Make Phase 5 pre-computation mandatory (can't leave NULL)
2. Reconciliation: Add column for "entry_price_source" (trade|position) for audit trail
3. Dashboard: Add "data_completeness" field to signal display

---

## Patterns to Watch For (Prevention)

| Pattern | Where | Risk | Fix |
|---------|-------|------|-----|
| `a or b` | Config chains | Silent fallback | Explicit check + error |
| `a.get("key", default)` | Data access | Hidden missing | Use explicit checks |
| `COALESCE(a, b)` | SQL queries | Masked NULLs | Add audit logging |
| `try: ... except: continue` | Loops | Swallowed errors | Raise + track |
| Synthetic values | Missing data | False confidence | Use data_unavailable flag |

---

## Next Steps

1. **Immediate:** Fix Phase 8 paper mode (remove synthetic ATR)
2. **Short-term:** Add audit logging to reconciliation COALESCE
3. **Medium-term:** Add dashboard monitoring for NULL patterns
4. **Long-term:** Redesign data contracts to prevent NULLs for trading-critical fields
