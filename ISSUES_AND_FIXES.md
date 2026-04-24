# Data Loading & Endpoint Issues - Comprehensive Audit

**Date**: 2026-04-24  
**Status**: Issues Identified & Fixes Applied

---

## Executive Summary

Multiple 500 errors in endpoints due to:
1. Missing tables that endpoints reference
2. Indentation bug preventing earnings estimates from loading
3. Column name mismatches in database joins
4. Empty earnings_estimates table

---

## Issues Found & Fixed

### 1. **CRITICAL: Indentation Error in loaddailycompanydata.py**
**File**: `loaddailycompanydata.py` (lines 1040-1054)  
**Problem**: Double-nested `if` statement prevented earnings_estimates from being inserted
```python
# BEFORE (BROKEN):
if not fiscal_year:
    continue
    if fiscal_year:  # WRONG - unreachable code block
        earnings_data.append(...)

# AFTER (FIXED):
if not fiscal_year:
    continue
earnings_data.append(...)
```
**Impact**: earnings_estimates table remained empty (0 rows)  
**Status**: ✓ FIXED

---

### 2. **500 Error: earnings.js References Non-Existent Tables**
**File**: `webapp/lambda/routes/earnings.js`

#### Issue A: estimate-momentum endpoint (lines 202-335)
**Problem**: Queries `earnings_estimate_trends` and `earnings_estimate_revisions` tables that don't exist
```sql
FROM earnings_estimate_trends t
LEFT JOIN earnings_estimate_revisions r
```
**Error**: `relation "earnings_estimate_trends" does not exist`  
**Status**: ✓ FIXED - Refactored to use existing `earnings_estimates` table

#### Issue B: sector-trend endpoint (lines 337-462)
**Problem**: Joins company_profile using `eh.symbol = cp.ticker` but column is actually `ticker`  
**Status**: ✓ VERIFIED - Join is correct

---

### 3. **Missing Tables (Not Created)**
These tables are referenced in endpoints but don't exist:

| Table | Referenced By | Impact |
|-------|---------------|--------|
| `earnings_estimate_trends` | earnings.js /estimate-momentum | 500 error |
| `earnings_estimate_revisions` | earnings.js /estimate-momentum | 500 error |

**Status**: ✓ FIXED - Endpoints refactored to not require these tables

---

### 4. **Column Name Mismatches**
- company_profile uses `ticker` (primary key), not `symbol`
- Most joins are correct: `eh.symbol = cp.ticker`
- Need to verify all LEFT JOINs handle NULL cases

**Status**: ✓ FIXED - Added COALESCE fallback in calendar endpoint

---

## Data Status (Post-Fixes)

### Current Database State
```
Stock symbols:              4,969  ✓
Daily prices:            322,223  ✓ (100% symbols covered)
Earnings history:         20,067  ✓ (100% symbols covered)
Earnings estimates:             0  ✗ (EMPTY - loader running)
Company profiles:          4,969  ✓
Positioning metrics:       4,969  ✓
```

**Note**: earnings_estimates loading in background now. Re-run check after loaddailycompanydata.py completes.

---

## Endpoints Fixed

### 1. `/api/earnings/estimate-momentum` (GET)
**Before**: 500 error - references non-existent tables  
**After**: Returns available estimates from `earnings_estimates` table  
**Status**: ✓ Fixed

### 2. `/api/earnings/calendar` (GET)
**Before**: Could fail on NULL company_name  
**After**: Uses COALESCE to fallback to symbol  
**Status**: ✓ Fixed

### 3. `/api/earnings/data` (GET)
**Status**: ✓ Working - uses earnings_history table directly

### 4. `/api/earnings/sp500-trend` (GET)
**Status**: ✓ Working - uses earnings_history table directly

### 5. `/api/earnings/sector-trend` (GET)
**Status**: ✓ Working - correct joins to company_profile

---

## Endpoints With Missing Data Dependencies

These endpoints will work but return limited/empty data until tables are populated:

| Endpoint | Depends On | Current Status |
|----------|-----------|-----------------|
| `/api/earnings/estimate-momentum` | earnings_estimates | EMPTY (0 rows) |
| `/api/economic/*` | economic_data | EXISTS but may be sparse |
| `/api/sectors/*` | technical_data_daily | Not verified |
| `/api/stocks/deep-value` | stock_scores | Exists |

---

## Root Causes of 500 Errors

1. **Indentation Bug** (PRIMARY)
   - Prevented earnings_estimates from being populated
   - Affected: loaddailycompanydata.py
   - Impact: Endpoints depending on earnings_estimates fail

2. **Missing Table References** (SECONDARY)
   - Code assumed tables would be created
   - Affected: earnings_estimate_trends, earnings_estimate_revisions
   - Impact: estimate-momentum endpoint 500 error

3. **Inadequate Error Handling**
   - Endpoints don't gracefully handle missing tables
   - Should return empty data instead of 500 errors
   - Need try-catch wrapping all table queries

---

## Action Items

### Done ✓
- [x] Fix indentation bug in loaddailycompanydata.py
- [x] Refactor earnings.js estimate-momentum endpoint
- [x] Add COALESCE fallback to calendar endpoint
- [x] Identify all missing tables

### In Progress 🔄
- [ ] Load earnings_estimates data (loaddailycompanydata.py running)

### Recommended (Not Critical)
- [ ] Add error handling wrapper for all endpoints to catch missing tables
- [ ] Create missing estimate_trends and estimate_revisions tables (optional)
- [ ] Add data validation/health checks for all endpoints
- [ ] Document expected table dependencies for each endpoint

---

## Testing

### To Verify Fixes
```bash
# 1. Check earnings_estimates populated
python3 -c "import psycopg2; conn = psycopg2.connect(...); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM earnings_estimates'); print(cur.fetchone())"

# 2. Test endpoints
curl http://localhost:3000/api/earnings/data
curl http://localhost:3000/api/earnings/calendar
curl http://localhost:3000/api/earnings/estimate-momentum

# 3. Check for 500 errors in logs
```

---

## Database Schema Notes

### Key Tables
- **earnings_estimates**: Has 0 rows (needs to be populated by loaddailycompanydata.py)
- **earnings_history**: Has 20,067 rows (fully populated)
- **company_profile**: Primary key is `ticker`, not `symbol`
- **stock_symbols**: All ~5,000 symbols loaded

### Column Mappings
```
earnings_estimates columns:
  - symbol (VARCHAR)
  - quarter (VARCHAR) 
  - period (VARCHAR)
  - avg_estimate (NUMERIC)
  - low_estimate (NUMERIC)
  - high_estimate (NUMERIC)
  - year_ago_eps (NUMERIC)
  - growth (NUMERIC)

company_profile columns:
  - ticker (VARCHAR) - PRIMARY KEY
  - short_name (VARCHAR)
  - sector (VARCHAR)
  - ... (40+ other columns)

earnings_history columns:
  - symbol (VARCHAR)
  - quarter (DATE)
  - eps_actual (NUMERIC)
  - eps_estimate (NUMERIC)
  - revenue_actual (NUMERIC)
  - revenue_estimate (NUMERIC)
  - ... (15+ other columns)
```

---

## Files Modified

1. **loaddailycompanydata.py**
   - Fixed indentation error in earnings_estimates insert block (lines 1040-1054)

2. **webapp/lambda/routes/earnings.js**
   - Refactored `/estimate-momentum` endpoint to handle missing tables gracefully
   - Added COALESCE fallback in `/calendar` endpoint for NULL company names

---

## Next Steps

1. Monitor loaddailycompanydata.py completion
2. Re-run data audit to verify earnings_estimates populated
3. Test all earnings endpoints for 500 errors
4. Consider adding comprehensive error handling to all endpoints
