# Data Integrity Issues Found - Comprehensive Audit

**Date:** 2026-06-13  
**Status:** AUDIT COMPLETE - Issues identified for discussion  
**Total Issues Found:** Multiple categories

---

## CATEGORY 1: Lambda API Placeholder Calculations (HIGH PRIORITY)

### Issue L1: PnL Lists Using `or 0` Fallback

**Location:** `lambda/api/routes/algo.py:638-641`

```python
# PROBLEM: Converting None to 0, making missing P&L invisible
pnl_dollars = [float(t.get('profit_loss_dollars') or 0) for t in trades]
pnl_pcts = [float(t.get('profit_loss_pct') or 0) for t in trades]
holding_days = [float(t.get('holding_days') or 0) for t in trades if t.get('holding_days')]
```

**Impact:** 
- Missing P&L values silently converted to 0
- Sharpe ratio, Sortino, max drawdown calculations use fake 0s
- Metrics appear better than reality (0 losses treated as neutral, not missing data)

**Same pattern in:**
- Line 692: Portfolio snapshot values (equity curve calculation)
- Line 712: Equity curve vals
- Line 716-717: Return calculations

---

## CATEGORY 2: Missing Data Flags in API Responses (MEDIUM PRIORITY)

### Issue M15 Not Fully Resolved: Stale Alerts Not Returned

**Status:** According to `HIGH_MEDIUM_ISSUES.md` line 751-777, M15 lists functions that:
- Calculate `stale_alerts` internally
- **Do NOT return it to caller**
- Operator doesn't see stale data warnings

**Functions affected:**
1. fetch_market()
2. fetch_positions()
3. fetch_perf()
4. fetch_economic_pulse()
5. fetch_circuit_breaker()
6. fetch_risk_metrics()

**Example missing return:**
```python
def fetch_market(c):
    stale_alerts = []
    if spy_age > 1:
        stale_alerts.append(f"SPY {spy_age}d old")
    
    return {
        "pct": pct,
        # Missing: "stale_alerts": stale_alerts  ← NOT RETURNED
    }
```

---

## CATEGORY 3: Price Fallback Issues (MEDIUM PRIORITY)

### Issue M4 & M18: Fallback Prices Not Flagged in Display

**Status:** According to `HIGH_MEDIUM_ISSUES.md:483-497` and `834-852`

**Problem:** 
- Flag `_missing_price` exists in code (algo_position_monitor.py:322)
- Flag is **NOT displayed** in dashboard UI
- Operator sees current_price but doesn't know it's entry_price fallback
- P&L calculations use days-old data without warning

**Example pattern:**
```python
# Flag is set (algo/algo_position_monitor.py:322):
'price_is_fallback': price_metadata.get('is_fallback', False),

# But dashboard doesn't display it (tools/dashboard/panels.py)
price_display = f"${price:.2f}"  # No warning shown
```

**Impact:**
- P&L shown as current but actually using entry_price from days ago
- Gap-up/gap-down losses not visible
- Risk assessment skewed by stale prices

---

## CATEGORY 4: Placeholder Data Returns (MEDIUM PRIORITY)

### Issue: Lambda API Returning `_is_placeholder` Markers

**Status:** Marker set but display handling incomplete

**Examples in webapp/lambda/routes/algo.js:**
```javascript
return { _is_placeholder: true, _error: "...", items: [] };  // Lines 2877, 2895, 2923, etc.
```

**In webapp/lambda/routes/market.js:**
```javascript
// Many endpoints return placeholder flags when data unavailable
return { _is_placeholder: true, _error: 'No AAII sentiment data available', items: [] };
```

**Issue:** 
- Placeholder flag is set
- Display layer (dashboard, webapp) doesn't consistently show it
- Users may trust placeholder data as real

---

## CATEGORY 5: Inconsistent NULL Handling (MEDIUM PRIORITY)

### Issue M20: Inconsistent NULL Handling Across Codebase

**Status:** According to `HIGH_MEDIUM_ISSUES.md:877-893` - NOT FIXED

**Pattern variations found:**
```python
# Pattern 1: Truthiness check (treats empty list as false)
if data: ...

# Pattern 2: Length check (explicit)
if len(data) > 0: ...

# Pattern 3: None check (explicit)
if data is not None: ...

# Pattern 4: Mixed patterns
if not data or data.get("_error"): ...
```

**Problem:** Inconsistent behavior when data is:
- None (missing)
- Empty list []
- Empty dict {}
- 0 (for numeric)

---

## CATEGORY 6: Schema Validation Issues (HIGH PRIORITY)

### Issue H6: Schema Validation Missing Column Types

**Status:** According to `HIGH_MEDIUM_ISSUES.md:121-141` - NOT FIXED

**Location:** Validation functions check column existence, not types

**Example problem:**
```
If price column is TEXT instead of NUMERIC:
- Database allows TEXT
- Code tries float(price)  
- ValueError at runtime
- No pre-flight check caught it
```

**Impact:**
- Type mismatches not caught until runtime
- Queries fail with cryptic errors
- Data corruption undetected

---

## CATEGORY 7: Dashboard Architectural Issues (MEDIUM-HIGH PRIORITY)

### Issue C1-1 through C3-7: Dashboard as Calculation Engine

**Status:** According to `CALCULATION_ARCHITECTURE_ISSUES.md` - PHASE 1-2 COMPLETE, PHASE 3-5 PENDING

**What's Fixed (Phase 1-2):**
- ✅ Fallback calculations removed
- ✅ Hardcoded config removed
- ✅ Signal quality filtering moved to API

**What's NOT Fixed (Phases 3-5):**
- ❌ Pre-computed aggregations still missing
- ❌ Database constraints incomplete
- ❌ API response format inconsistencies

---

## CATEGORY 8: Test/Mock Data in Production (LOW PRIORITY)

### Issue: Potential Test Values in Code

**Status:** Per `SOLUTION_COMPLETENESS.md`, Phase 1 audit completed - NO hardcoded test values found

**What was verified:**
- ✅ No hardcoded test symbols
- ✅ No fake price values
- ✅ No mock account numbers
- ✅ All validation patterns are real (not test stubs)

**Conclusion:** This category is CLEAN.

---

## PRIORITY RANKING FOR DISCUSSION

### TIER 1 - INTEGRITY BREAKING (Fix immediately)
1. **L1:** Lambda API P&L using `or 0` fallback
   - **Why:** Makes missing P&L invisible; breaks metrics calculations
   - **Time:** 2-3 hours
   - **File:** `lambda/api/routes/algo.py` lines 638-641, 692, 712, 716-717

2. **H6:** Schema validation missing type checks
   - **Why:** Type errors not caught until runtime
   - **Time:** 4 hours
   - **File:** Database validation functions

### TIER 2 - DATA OPACITY (Fix soon)
3. **M15:** Stale alerts not returned from API
   - **Why:** Operator doesn't see when data is stale
   - **Time:** 1-2 hours
   - **Files:** 6 fetch functions in dashboard/Lambda API

4. **M4/M18:** Price fallback flags not displayed
   - **Why:** P&L shown as current but uses old entry_price
   - **Time:** 1-2 hours
   - **File:** `tools/dashboard/panels.py` (display)

5. **M20:** Inconsistent NULL handling
   - **Why:** Unpredictable behavior with missing/empty data
   - **Time:** 3-4 hours
   - **Files:** Across codebase

### TIER 3 - ARCHITECTURAL (Plan for refactor)
6. **C3-5:** Dashboard Pre-computed Aggregations
   - **Why:** Dashboard doing work that should be in API
   - **Time:** Full sprint
   - **Scope:** Create new tables, loaders, API endpoints

---

## SUMMARY

### What's Working ✅
- Financial data validation is strong
- Database constraints in place
- Fail-closed design for critical failures
- Comprehensive logging at critical points
- Transaction safety with SAVEPOINT

### What's Broken ❌
- Lambda API silently converts None → 0 in P&L calculations
- Stale data alerts calculated but not returned
- Price fallback flags exist but not displayed
- Schema validation incomplete (type checking missing)
- NULL handling inconsistent across codebase

### Data Integrity Risk
**MEDIUM** - Financial calculations use placeholder 0s which skew metrics, but database constraints prevent storing invalid trades.

---

## Next Steps for Discussion

1. **Confirm priorities** - Which TIER 1 issues are most urgent?
2. **Scope the fixes** - For each issue, define:
   - Exact code locations
   - How to test the fix
   - Where to add validation
3. **Define success criteria** - What does "fixed" look like for each?

