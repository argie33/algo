# API Endpoints - Broken & Missing
## April 25, 2026

---

## CRITICAL STATUS

API Server: ✅ **RUNNING** on port 3001  
Database: ✅ **CONNECTED** with 25+ tables populated

But: ❌ **Multiple endpoints broken or missing**

---

## BROKEN ENDPOINTS (500 errors)

### 1. `/api/sectors/sectors` - Returns generic "Request failed"
**File**: `webapp/lambda/routes/sectors.js`  
**Status**: 500 error, likely query issue  
**Fix**: Check and fix the SELECT query in sectors endpoint

### 2. `/api/industries/industries` - Returns generic "Request failed"  
**File**: `webapp/lambda/routes/industries.js`  
**Status**: 500 error, likely query issue  
**Fix**: Check and fix the SELECT query

### 3. `/api/earnings/sp500-trend` - `invalid input syntax for type interval: "1 quarter"`
**File**: `webapp/lambda/routes/earnings.js` (line 159+)  
**Status**: SQL syntax error in interval clause  
**Issue**: Somewhere "INTERVAL '1 quarter'" is being used (invalid PostgreSQL syntax)  
**Fix**: Change to `INTERVAL '3 months'` or `INTERVAL '91 days'`

### 4. `/api/financials/{symbol}/balance-sheet` - Returns empty data array
**File**: `webapp/lambda/routes/financials.js`  
**Status**: Query works but returns no rows  
**Issue**: `annual_balance_sheet` table exists but may be empty (only 64 rows vs expected 4,969)  
**Fix**: Check if data actually loaded, or adjust query

### 5. `/api/sentiment/data` - Returns 500 error
**File**: `webapp/lambda/routes/sentiment.js`  
**Status**: 500 error - likely missing table or column  
**Fix**: Verify `analyst_sentiment_analysis` table has required columns

### 6. `/api/strategies/covered-calls` - Returns 500 error
**File**: `webapp/lambda/routes/strategies.js`  
**Status**: 500 error - depends on options data which is mostly empty  
**Fix**: Either populate options data or return placeholder for missing data

---

## MISSING ENDPOINTS (404 errors)

### 1. `/api/market/fresh-data`
**Frontend expects**: Market data summary with fresh statistics  
**Actual**: Endpoint doesn't exist OR returns 404  
**File**: `webapp/lambda/routes/market.js`  
**Fix**: Check if route is properly mounted, or return empty/placeholder

---

## CONNECTION REFUSED ENDPOINTS

These return `net::ERR_CONNECTION_REFUSED` - API server is unreachable:

```
/api/commodities/categories
/api/commodities/prices
/api/commodities/market-summary
/api/commodities/correlations
/api/commodities/cot/{symbol}
/api/commodities/seasonality/{symbol}
```

**Status**: Either:
1. Endpoint not registered in main index.js
2. Database table doesn't exist
3. Query is crashing

**File**: `webapp/lambda/routes/commodities.js`  
**Fix**: Check if commodities routes are mounted in `webapp/lambda/index.js`

---

## DATA AVAILABILITY ISSUES

Even when endpoints work, they return empty data:

| Table | Records | Expected | Coverage | Issue |
|-------|---------|----------|----------|-------|
| company_profile | 367 | 4,969 | 7.4% | Loader only ran on 367 stocks |
| key_metrics | 924 | 4,969 | 18.6% | Partial load |
| annual_balance_sheet | -1 | 4,969 | ERROR | Table query failing |
| financial_data | Very low | 4,969 | <10% | Financial statements missing |
| earnings_estimates | 1,348 | 4,969 | 27% | Loader incomplete |
| options_chains | 1 | 500+ | 0.2% | Loader failed |
| calendar_events | 0 | 4,969 | 0% | Table not populated |
| stock_news | 0 | ? | 0% | Table not populated |

---

## QUICK FIXES

### Fix 1: Check if all routes are mounted in index.js
```bash
grep "use.*api/" webapp/lambda/index.js | wc -l
```

Should show all route files are registered. If commodities, strategies, etc. are missing, add them.

### Fix 2: Fix SQL interval syntax
Search earnings.js for any `INTERVAL '1 quarter'` and replace with `INTERVAL '3 months'`

### Fix 3: Add defensive error handling
All endpoints should return JSON with error message, not generic "Request failed"

### Fix 4: Return placeholder data for missing features
Instead of 500 error, return 200 with message "Data not yet available"

---

## SYSTEMATIC FIX PROCESS

1. **Start API server**:
   ```bash
   node webapp/lambda/index.js
   ```

2. **Test each endpoint** with curl
3. **Check console logs** for error messages
4. **Fix one at a time**:
   - Read the route file
   - Find the failing query
   - Test the query directly
   - Fix it
   - Restart API server
   - Test endpoint again

5. **For data issues**, either:
   - Run missing loaders
   - Or mark data as "Not yet available"

---

## ENDPOINTS STATUS MATRIX

| Endpoint | Status | Issue | Fix |
|----------|--------|-------|-----|
| /api/health | ✅ WORKS | - | - |
| /api/stocks | ✅ WORKS | - | - |
| /api/scores/stockscores | ✅ WORKS | - | - |
| /api/technicals | ✅ WORKS | - | - |
| /api/signals/stocks | ✅ WORKS | - | - |
| /api/earnings/info | ✅ WORKS | - | - |
| /api/sectors/sectors | ❌ 500 | Generic error | Fix query |
| /api/industries/industries | ❌ 500 | Generic error | Fix query |
| /api/earnings/sp500-trend | ❌ 500 | Interval syntax | Replace "1 quarter" |
| /api/financials/*/balance-sheet | ⚠️ Empty | No data | Load financial data |
| /api/sentiment/data | ❌ 500 | Unknown | Check table |
| /api/strategies/covered-calls | ❌ 500 | Options missing | Return placeholder |
| /api/market/fresh-data | ❌ 404 | Not found | Check mount |
| /api/commodities/* | ❌ 404 | Not found | Check mount |

---

## NEXT ACTIONS

**Immediate (30 min)**:
1. Check which routes are mounted in index.js
2. Add missing mounts
3. Restart API server

**Short-term (1 hour)**:
1. Fix SQL syntax errors in each failing endpoint
2. Add error logging so we see what's failing
3. Test each endpoint

**Medium-term (during loader run)**:
1. Run remaining loaders to populate missing data
2. Re-test endpoints with real data

---

Generated: 2026-04-25  
API Server Status: Running but broken endpoints exist
