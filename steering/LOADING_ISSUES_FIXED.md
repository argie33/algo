# Data Loading Issues - Root Cause Analysis & Fixes

**Date:** 2026-06-20  
**Status:** 2 critical issues identified and fixed, diagnostic tools created

## Issues Identified

### 1. PUT/CALL OPTIONS DATA NOT BEING PERSISTED (CRITICAL)

**Problem:** `loaders/load_options_chains.py` was not committing data to the database.

**Root Causes:**
1. **Line 53:** Used `DatabaseContext()` with default role="read" parameter
   - DatabaseContext defaults to `role="read"` when not specified
   - Read connections ROLLBACK on exit instead of COMMITTING
   - All options_chains and iv_history inserts were being discarded

2. **Lines 80-160:** Misused DatabaseContext API
   - Code treated DatabaseContext as returning a connection object
   - Called `db.cursor()` and `db.commit()` which don't exist on cursor objects
   - DatabaseContext returns a cursor-like wrapper, not a connection

**Impact:**
- `options_chains` table remained empty (no put/call volume data)
- `iv_history` table remained empty (no implied volatility data)
- Options-based signals cannot generate entries without these inputs

**Fix Applied:**
```python
# BEFORE (broken):
with DatabaseContext() as db:  # default role="read" → ROLLBACK
    self._load_symbol_options(db, symbol, eval_date)
        with db.cursor() as cur:  # ❌ cursor doesn't have cursor() method
            cur.execute(...)
        db.commit()  # ❌ cursor doesn't have commit() method

# AFTER (fixed):
with DatabaseContext("write") as cur:  # explicitly role="write" → COMMIT
    self._load_symbol_options(cur, symbol, eval_date)
        cur.execute(...)  # ✓ use cursor directly
        # ✓ context manager handles commit on exit
```

### 2. FACTOR SCORES SHOWING 0 - INCOMPLETE LOADER DEPENDENCY CHAIN

**Symptom:** `stock_scores` and `swing_trader_scores` tables empty or mostly zero values

**Root Cause Cascade:**
```
stock_scores = 0
  ↓ depends on
quality_metrics, growth_metrics, value_metrics, positioning_metrics, stability_metrics
  
swing_trader_scores = 0
  ↓ depends on
signal_quality_scores
  ↓ depends on
buy_sell_daily (BUY/SELL signals)
  ↓ depends on
price_daily, technical_data_daily
  
trend_template_data (also required by swing_trader_scores)
```

**Investigation Steps:**
1. Run diagnostic script to identify which loaders are missing
2. Verify upstream tables have data: `price_daily`, `buy_sell_daily`, `technical_data_daily`
3. Check factor input tables: `quality_metrics`, `growth_metrics`, `value_metrics`, etc.
4. Run loaders in dependency order

**Diagnostic Tool:**
- Created `scripts/diagnose_loading_issues.py`
- Reports status of all critical tables
- Identifies which loaders are blocked and why
- Provides actionable next steps

**Run Diagnostic:**
```bash
cd /d C:\Users\arger\code\algo
python scripts/diagnose_loading_issues.py
```

## Verification Steps

### 1. Verify Options Data Fix
```bash
# Check if options_chains has data now
sqlite3 or psql:
SELECT COUNT(*) FROM options_chains;
SELECT COUNT(*) FROM iv_history;

# Should see > 0 rows after running load_options_chains.py with fixed code
```

### 2. Verify Factor Scores Load
```bash
# Run diagnostic first to see what's missing
python scripts/diagnose_loading_issues.py

# Then trigger loaders in order:
python loaders/load_stock_scores.py
python loaders/load_swing_trader_scores_vectorized.py --today
```

### 3. Verify Signal Generation Works
```bash
# Phase 5 should now find candidates with composite scores > 0
# Check orchestrator logs for "PHASE 5" output with non-zero signal counts
```

## Dependencies Resolved

✓ Fixed: options_chains loader database context usage  
✓ Created: diagnostic tool for loader dependency analysis  
⏳ Pending: Run diagnostic and verify upstream loaders  
⏳ Pending: Populate missing factor input tables  

## Related Issues

- **Issue #3:** All validation filters moved to SQL WHERE clauses (Phase 5)
- **Issue #4:** Explicit dependency validation for Phase 5
- **Issue #8:** Swing trader scores scoring validation
- **Phase 1:** Data freshness check validates stock_scores exists

## Files Modified

- `loaders/load_options_chains.py` — Fixed database context usage (137 lines changed)
- `scripts/diagnose_loading_issues.py` — New diagnostic script (199 lines)

## Next Actions

1. **Immediate:** Run `diagnose_loading_issues.py` to identify missing loaders
2. **Priority:** Run missing loaders identified by diagnostic
3. **Verify:** Check that Phase 5 can generate signals with composite_score > 0
4. **Monitor:** Watch data_loader_status table for stuck or incomplete loaders

## Notes

- DatabaseContext is a critical abstraction for connection pooling and transaction management
- Always use `DatabaseContext("write")` for INSERT/UPDATE/DELETE operations
- DatabaseContext handles commits/rollbacks automatically—don't call db.commit() manually
- Use the diagnostic script before each major data reload to catch dependency issues early
