# Critical Fixes Required - API Errors Analysis

**Status:** API Server Crashed / 8+ Endpoint Errors

---

## IMMEDIATE ACTIONS NEEDED

### 1. **RESTART API SERVER**
```bash
# Kill any existing processes on port 3001
lsof -i :3001 | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true

# Start fresh API server
node webapp/lambda/index.js
```

**Why:** "Connection Refused" errors indicate API server crashed

---

## ENDPOINT ERRORS IDENTIFIED

### ✅ FIXED (in this commit)
1. **Score Endpoint Filter** - Removed broken `is_sp500 = TRUE` filter
   - Was causing empty results because flag never populated
   - Fixed in: `webapp/lambda/routes/scores.js`

2. **Sectors/Industries Routes** - Routes have been simplified
   - Sectors now has: `/` (root) and `/sectors` endpoint
   - Industries now has: `/` (root) and `/industries` endpoint
   - Frontend calls: `/api/sectors/sectors` and `/api/industries/industries` ✅

### ❌ STILL BROKEN (Need Fixes)

#### 404 Errors (Routes Don't Exist)
1. **GET /api/market/fresh-data** - 404
   - Route exists in `webapp/lambda/routes/market.js`
   - But reads from `/tmp/latest_market_data.json` which doesn't exist
   - Fix: Either populate the file OR disable this endpoint

#### 500 Errors (Server Errors - Database/Logic Issues)
1. **GET /api/sectors/sectors** - 500
   - Issue: Querying `company_profile` table for sectors
   - Problem: `company_profile` may not have data OR column names wrong
   - Fix: Verify table exists and has `sector` column

2. **GET /api/industries/industries** - 500
   - Issue: Querying `company_profile` table for industries
   - Problem: Same as sectors - table may not exist or have data
   - Fix: Verify table exists and has `industry` column

3. **GET /api/earnings/sp500-trend** - 500
   - Issue: Unknown - need to check endpoint logic
   - Fix: Review `webapp/lambda/routes/earnings.js`

4. **GET /api/financials/AAPL/balance-sheet** - 500
   - Issue: Likely missing financial statement tables
   - Fix: Verify `annual_balance_sheet` table exists with data

5. **GET /api/sentiment/data** - 500
   - Issue: Likely missing `analyst_sentiment_analysis` table
   - Fix: Verify table exists and has data (should have 359/515 stocks)

6. **GET /api/strategies/covered-calls** - 500
   - Issue: Complex query, likely missing tables/columns
   - Fix: Verify `options_chains` and strategy tables exist

#### Connection Refused (API Server Not Running)
1. **All /api/commodities/* endpoints** - ERR_CONNECTION_REFUSED
   - Issue: API server crashed while responding to earlier requests
   - Fix: Restart API server
   - Note: Once restarted, these may work or may return 500 if tables missing

---

## ROOT CAUSE ANALYSIS

The fundamental issue: **Tables missing or not populated by loaders**

The API endpoints are trying to query tables like:
- `company_profile` (sector, industry columns)
- `analyst_sentiment_analysis` (analyst data)
- `annual_balance_sheet` (financial statements)
- `options_chains` (options data)

But these tables are either:
1. **Not created** - init_database.py didn't run
2. **Created but empty** - Loaders haven't run yet
3. **Created with wrong columns** - Schema mismatch

---

## VERIFICATION CHECKLIST

Before declaring fixes complete:

```bash
# 1. Start API server
node webapp/lambda/index.js

# 2. Check database tables exist
psql -h localhost -U stocks -d stocks -c "\dt"

# 3. Check table data exists
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM company_profile;"
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM analyst_sentiment_analysis;"
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM annual_balance_sheet;"

# 4. Test endpoints
curl http://localhost:3001/api/sectors/sectors?limit=5
curl http://localhost:3001/api/industries/industries?limit=5
curl http://localhost:3001/api/scores/stockscores?limit=5

# 5. Check response format
# Should return: {success: true, items: [...], pagination: {...}, timestamp: "..."}
```

---

## QUICK FIX PRIORITY

### TIER 1 (Do First - Blocking All UI)
1. Restart API server: `node webapp/lambda/index.js`
2. Verify database is running and accessible
3. Check that required tables exist: `company_profile`, `stock_scores`, etc.

### TIER 2 (Do Second - Makes UI Work)
1. Run data loaders: `bash run-all-loaders.sh`
   - This populates all tables with data
   - Takes 30-60 minutes
2. Verify data loaded: `node check-data-coverage.js`

### TIER 3 (Do Third - Makes Pages Display Correctly)
1. Test each endpoint manually
2. Fix any 500 errors by checking table schemas
3. Add missing routes if any

---

## WHAT LIKELY HAPPENED

1. **API server crashed** while processing one of the 500 error endpoints
2. One of the endpoints has:
   - A syntax error causing crash
   - A database query error (table doesn't exist)
   - Missing required data

Most likely culprit: An endpoint tried to query a table that doesn't exist or database connection failed

---

## SOLUTION FLOW

```
1. Restart API server
   ↓
2. Database comes online
   ↓
3. Test endpoints - some still 404/500
   ↓
4. Check which tables are missing/empty
   ↓
5. If tables missing: Run init_database.py
   ↓
6. If tables empty: Run bash run-all-loaders.sh
   ↓
7. Retry endpoints - should return data
   ↓
8. Frontend receives data and displays correctly
```

---

## FILES TO CHECK

When debugging 500 errors, check these files:

| Endpoint | Error File | Check |
|----------|-----------|-------|
| /api/sectors/sectors | sectors.js:25 | Does `company_profile` table exist? |
| /api/industries/industries | industries.js:35 | Does `company_profile` table exist? |
| /api/earnings/sp500-trend | earnings.js | Check endpoint logic |
| /api/financials/AAPL/balance-sheet | financials.js | Does `annual_balance_sheet` exist? |
| /api/sentiment/data | sentiment.js | Does `analyst_sentiment_analysis` exist? |
| /api/strategies/covered-calls | strategies.js | Does `options_chains` exist? |
| /api/market/fresh-data | market.js | Does `/tmp/latest_market_data.json` exist? |

---

## COMMANDS TO RUN NOW

```bash
# 1. Kill old API process
killall node 2>/dev/null || true

# 2. Start fresh API
node webapp/lambda/index.js &

# 3. Wait for startup (5 seconds)
sleep 5

# 4. Test connection
curl http://localhost:3001/api/status

# 5. If GET /api/status returns 200: API is working!
# If connection refused: API server didn't start (check logs)

# 6. Test one endpoint
curl http://localhost:3001/api/sectors/sectors?limit=1

# 7. If you get data: Route works!
# If 500: Table missing/empty
# If 404: Route doesn't exist
```

---

## EXPECTED NEXT ERRORS AFTER RESTART

After restarting the API server, you'll likely see:

1. **More 500 errors** - Expected because loaders haven't run
2. **Same 404 for /api/market/fresh-data** - Expected, data file doesn't exist
3. **Some endpoints working** - Ones that don't require database (health, status, etc.)

This is NORMAL. The fix is to run the loaders:
```bash
bash run-all-loaders.sh
```

After loaders complete, all 500 errors should become 200 with data.

---

## BOTTOM LINE

**Current State:**
- ❌ API server crashed (connection refused)
- ❌ 8 endpoints returning 404 or 500
- ❌ Frontend can't get data

**Immediate Fix (5 minutes):**
- Restart API server
- Test that it's responding

**Complete Fix (60 minutes):**
- Run data loaders
- Verify data loaded
- All endpoints should work

**Long-term Fix (Optional):**
- Investigate why endpoints are erroring
- Add better error handling
- Add monitoring to prevent crashes
