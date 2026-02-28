# 🚨 Data Loader Issues Report
**Date**: Feb 28, 2026 ~10:12 UTC
**Status**: 7 Critical Issues Found

---

## 🔴 CRITICAL ISSUES

### Issue #1: loadannualbalancesheet.py - Missing DB Config
**Severity**: 🔴 CRITICAL
**Error**: `KeyError: 'dbname'`
**File**: `/home/arger/algo/loadannualbalancesheet.py` line 314
**Root Cause**: Database config dictionary is missing 'dbname' key

**Log**:
```
Traceback (most recent call last):
  File "/home/arger/algo/loadannualbalancesheet.py", line 314, in <module>
    dbname=cfg["dbname"]
           ~~~^^^^^^^^^^
KeyError: 'dbname'
```

**Fix Required**: Check database config parsing

---

### Issue #2: loadecondata.py - Missing fredapi Module
**Severity**: 🔴 CRITICAL
**Error**: `ModuleNotFoundError: No module named 'fredapi'`
**File**: `/home/arger/algo/loadecondata.py` line 14
**Root Cause**: FRED API module not installed

**Log**:
```
Traceback (most recent call last):
  File "/home/arger/algo/loadecondata.py", line 14, in <module>
    from fredapi import Fred
ModuleNotFoundError: No module named 'fredapi'
```

**Fix Required**: Install fredapi module

---

### Issue #3: loadfeargreed.py - Event Loop Closed
**Severity**: 🔴 CRITICAL
**Error**: `RuntimeError: Event loop is closed`
**File**: `/home/arger/algo/loadfeargreed.py`
**Root Cause**: Asyncio event loop not properly managed

**Fix Required**: Fix async event loop handling

---

### Issue #4: loadnews.py - Duplicate Key Constraint
**Severity**: 🔴 CRITICAL
**Error**: `ON CONFLICT DO UPDATE command cannot affect row a second time`
**File**: `/home/arger/algo/loadnews.py`
**Root Cause**: Multiple rows with same news being inserted, triggering duplicate constraint multiple times

**Affected Symbols**: KRNT, KRNY, KRO, KROS, KRRO, KRT, KRUS, KRYS...

**Log**:
```
ERROR - Failed to process news for KRUS: ON CONFLICT DO UPDATE command cannot affect row a second time
HINT: Ensure that no rows proposed for insertion within the same command have duplicate constrained values.
```

**Fix Required**: Deduplicate news data before INSERT...ON CONFLICT

---

### Issue #5: loadsectors.py - Missing Column 'trailing_pe'
**Severity**: 🔴 CRITICAL
**Error**: `column "trailing_pe" of relation "sector_ranking" does not exist`
**File**: `/home/arger/algo/loadsectors.py` line 296
**Root Cause**: sector_ranking table schema doesn't match INSERT query

**Log**:
```
ERROR - Error populating sector_ranking: column "trailing_pe" of relation "sector_ranking" does not exist
LINE 2: ...ame, date_recorded, current_rank, momentum_score, trailing_p...
                                                             ^
```

**Fix Required**: Fix SQL INSERT query to match schema

---

### Issue #6: Rate Limiting Issues
**Severity**: 🟠 HIGH
**Affected Loaders**:
- `loadanalystsentiment.py` - Too Many Requests (rate limited)
- `loadanalystupgradedowngrade.py` - Too Many Requests (rate limited)
- `loaddailycompanydata.py` - Too Many Requests (rate limited)

**Example**:
```
WARNING - Failed to fetch analyst data for GPGI: Too Many Requests. Rate limited.
WARNING - All fetch attempts failed for AAUC: Too Many Requests. Rate limited.
```

**Fix Required**: Add exponential backoff + longer delays between requests

---

### Issue #7: Missing Data from yfinance
**Severity**: 🟠 HIGH
**Affected Loaders**:
- `loadannualincomestatement.py` - Some symbols return empty data
- `loadannualcashflow.py` - Some symbols return empty data
- `loadsecfilings.py` - Timeouts getting CIK for certain symbols

**Example**:
```
WARNING - income_stmt returned empty data for GIL
WARNING - No income statement data returned by any method for GIL
WARNING - Timeout getting CIK for AUGO
```

**Root Cause**: API availability issues (expected for some symbols)

---

## 📊 Summary

| Issue | Severity | Status | Files Affected |
|-------|----------|--------|-----------------|
| DB Config Missing | 🔴 CRITICAL | 🔧 NEEDS FIX | loadannualbalancesheet.py |
| fredapi Module | 🔴 CRITICAL | 🔧 NEEDS FIX | loadecondata.py |
| Event Loop Closed | 🔴 CRITICAL | 🔧 NEEDS FIX | loadfeargreed.py |
| Duplicate Keys | 🔴 CRITICAL | 🔧 NEEDS FIX | loadnews.py |
| Schema Mismatch | 🔴 CRITICAL | 🔧 NEEDS FIX | loadsectors.py |
| Rate Limiting | 🟠 HIGH | ⚠️ KNOWN | Multiple loaders |
| Missing Data | 🟠 HIGH | ⚠️ KNOWN | Multiple loaders |

---

## ✅ What's Working

- ✅ loadstockscores.py - 4,996 stocks (100%)
- ✅ loadmarket.py - Market data loaded
- ✅ loadeconomicdata-retry.py - 4 calendar events
- ✅ loadpricedaily.py - 22.2M+ price records
- ✅ loadbuysell_etf_daily.py - ETF signals loading
- ✅ loadfactormetrics.py - Metrics processing
- ✅ loadearningshistory.py - Earnings loaded
- ✅ loadearningsrevisions.py - Revisions loaded

---

## 🔧 Recommended Fixes (Priority Order)

### Priority 1 (Blocking):
1. Fix loadannualbalancesheet.py DB config
2. Install fredapi module
3. Fix loadnews.py duplicate constraint
4. Fix loadsectors.py schema mismatch

### Priority 2 (Important):
5. Fix loadfeargreed.py event loop
6. Add better rate limit handling
7. Document symbols without yfinance data

---

## 🚀 Next Steps

1. Run `python3 -m pip install fredapi` to install missing module
2. Review and fix each loader's database config parsing
3. Fix SQL schema issues in loadsectors.py
4. Deduplicate news data in loadnews.py
5. Rerun all loaders with fixes applied

---

**Status**: Ready for fixes
**Estimated Fix Time**: 30-45 minutes for all critical issues
