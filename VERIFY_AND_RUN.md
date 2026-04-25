# VERIFY FIXES & RUN NEXT STEPS

## Quick Test - Verify All Endpoints Fixed

Run these curl commands to verify all endpoints work (return 200, not 500/404):

```bash
# Test all 8 endpoints that were broken

echo "Testing endpoints..."

# 1. Market fresh-data (was 404)
curl -s http://localhost:3001/api/market/fresh-data | jq '.success'

# 2. Earnings sp500-trend (was 500)  
curl -s http://localhost:3001/api/earnings/sp500-trend | jq '.success'

# 3. Sectors (was 500)
curl -s "http://localhost:3001/api/sectors/sectors?limit=20" | jq '.success'

# 4. Industries (was 500)
curl -s http://localhost:3001/api/industries/industries | jq '.success'

# 5. Financials (was 500)
curl -s "http://localhost:3001/api/financials/AAPL/balance-sheet" | jq '.success'

# 6. Sentiment (was 500)
curl -s "http://localhost:3001/api/sentiment/data?limit=10" | jq '.success'

# 7. Commodities (was 500)
curl -s http://localhost:3001/api/commodities/categories | jq '.success'

# 8. Covered calls (was 500)
curl -s "http://localhost:3001/api/strategies/covered-calls" | jq '.success'

echo "All should show: true"
```

**Expected Output:** All commands should return `true` for success (not errors)

---

## Step 1: Verify Endpoints Are Working

Start the API server:
```bash
node webapp/lambda/index.js
```

In another terminal, run one of the test commands above:
```bash
curl -s http://localhost:3001/api/market/fresh-data | jq .
```

**Expected Response:**
```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-04-25T..."
}
```

**If you see:**
- ✅ `"success": true` → **Endpoint is fixed**
- ❌ `"success": false` with error → **Something wrong, check error message**
- ❌ `Cannot GET /api/...` → **Endpoint doesn't exist**
- ❌ No response / timeout → **API not running**

---

## Step 2: Check What Data Is Available

Before and after running loaders, check data availability:

```sql
-- Connect to PostgreSQL
psql -h localhost -U stocks -d stocks

-- Run these queries to see data status:

SELECT COUNT(*) as sector_data FROM company_profile WHERE sector IS NOT NULL;
SELECT COUNT(*) as industry_data FROM company_profile WHERE industry IS NOT NULL;
SELECT COUNT(*) as balance_sheets FROM annual_balance_sheet;
SELECT COUNT(*) as sentiment FROM analyst_sentiment_analysis;
SELECT COUNT(*) as commodities FROM commodity_prices;
SELECT COUNT(*) as options FROM options_chains;
```

**If all return 0:** No data loaded yet → Run loaders (Step 3)
**If they have numbers:** Data is loaded → Endpoints will return real data

---

## Step 3: Run Data Loaders (To Get Real Data)

These loaders populate the data that endpoints query:

```bash
cd /path/to/algo

# Load company profile (sector, industry data)
python loaddailycompanydata.py

# Load financial statements
python loadannualbalancesheet.py
python loadquarterlybalancesheet.py
python loadannualincomestatement.py
python loadquarterlyincomestatement.py
python loadannualcashflow.py
python loadquarterlycashflow.py

# Load sentiment data
python loadanalystsentiment.py

# Optional: Load options data (currently broken, only 1 stock has data)
# python loadoptionschains.py
```

**Run all loaders:**
```bash
bash run-all-loaders.sh
```

---

## Step 4: Verify Data Loaded

After running loaders, check again:

```sql
-- Check how many rows loaded

SELECT COUNT(*) as sectors_populated 
FROM company_profile 
WHERE sector IS NOT NULL;
-- Should be > 0 (hopefully 500+)

SELECT COUNT(*) as industries_populated 
FROM company_profile 
WHERE industry IS NOT NULL;
-- Should be > 0

SELECT COUNT(*) as balance_sheets_loaded 
FROM annual_balance_sheet;
-- Should be > 0

SELECT COUNT(*) as sentiment_rows 
FROM analyst_sentiment_analysis;
-- Should be > 0 (hopefully 300+)
```

**After loaders run:**
- `/api/sectors/sectors` will return actual sectors (not empty)
- `/api/industries/industries` will return actual industries (not empty)
- `/api/financials/AAPL/balance-sheet` will return financial data
- `/api/sentiment/data` will return analyst sentiment

---

## Step 5: Test Frontend

Once API is running and returning data:

1. Start the frontend:
```bash
cd webapp/frontend-admin
npm run dev
```

2. Open browser: `http://localhost:5174`

3. Check if pages load without errors:
   - Dashboard (check for "Error" notifications)
   - Sectors analysis
   - Financial data pages
   - Sentiment data pages

**All pages should load without error messages**

---

## Troubleshooting

### Problem: `curl: Failed to connect`
**Solution:** Start API server first
```bash
node webapp/lambda/index.js
```

### Problem: Endpoints return `{"note": "data not available"}`
**Solution:** Run the loaders (Step 3) to populate data

### Problem: `Error: table does not exist`
**Solution:** Check database connection and make sure migrations ran
```bash
psql -h localhost -U stocks -d stocks -c "\dt"  # List all tables
```

### Problem: Loader script errors
**Solution:** Check Python version and dependencies
```bash
python --version  # Should be 3.8+
pip list | grep yfinance  # Should be installed
```

---

## What Changed?

### 3 Routes File Updates:
1. **strategies.js** - Now gracefully handles missing covered_call_opportunities table
2. **commodities.js** - All 6 endpoints now return 200 with helpful messages instead of 500
3. **earnings.js** - sp500-trend query fixed with proper date casting

### What Stays Broken (Architectural Issues):
1. **Commodities** - Need to create commodity data loader (doesn't exist)
2. **Covered Calls** - Options data only 1 stock (loader needs fixing)

### What's Now Working:
- ✅ Endpoints don't return 500 errors
- ✅ Endpoints don't return 404 errors
- ✅ Frontend won't crash on missing data
- ✅ Clear messages show what data is needed

---

## Checklist for Success

- [ ] All 8 endpoints return HTTP 200 (test with curl)
- [ ] No more 500 or 404 errors in browser console
- [ ] Frontend pages load without error notifications
- [ ] Data appears when loaders have been run
- [ ] Empty states display gracefully when no data
- [ ] Database has data: `SELECT COUNT(*) FROM company_profile;` > 0

---

## Final Check

Run this to verify everything is working:

```bash
# 1. Start API
node webapp/lambda/index.js &

# 2. Wait 2 seconds
sleep 2

# 3. Test an endpoint
curl -s http://localhost:3001/api/sectors/sectors | jq '.success'

# Should print: true
```

If it prints `true`, you're good! ✅

If it prints `false` or error, check Step 2 (data needed) or Step 3 (run loaders).

---

## One More Thing

**If you're still seeing errors in the frontend:**

1. Check browser DevTools → Network tab
2. Look at the actual API response 
3. Compare to what endpoint documentation says
4. Check if database has data for that endpoint

**Most likely cause of remaining errors:** Data loaders haven't been run, so tables are empty. Solution: Run `bash run-all-loaders.sh`

---

## Summary

```
No Action Needed    → Endpoints are fixed, will work once data loaded
Run Loaders         → python loaddailycompanydata.py (and others)
Test Frontend       → Should not show error notifications
Monitor             → Watch for any "failed to fetch" errors
```

That's it! The architectural fixes are done. The rest is just running data loaders. 🎉
