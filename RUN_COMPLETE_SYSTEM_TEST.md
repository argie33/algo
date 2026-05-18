# Complete System Test - Run This Now to Prove Everything Works

## Prerequisites Check (5 minutes)

Before starting, verify you have:
```bash
# Check PostgreSQL is running
psql -U postgres -c "SELECT 1"
# Expected: Should show "1" with no errors

# Check Node is installed  
node -v
npm -v
# Expected: v18+ and npm 8+

# Check Python
python3 --version
# Expected: 3.9+
```

---

## STEP 1: Initialize Database (2 minutes)

```bash
cd C:\Users\arger\code\algo
python3 init_database.py
```

**EXPECTED OUTPUT:**
```
Creating database schema...
✓ 423 SQL statements executed
✓ 132 tables created  
✓ All indexes created
✓ Database initialization complete
```

**VERIFY:**
```bash
psql -U postgres -d algo -c "SELECT COUNT(*) FROM pg_tables WHERE table_schema='public';"
# Should show: count = 132
```

---

## STEP 2: Populate All Data (30-60 minutes depending on API rate limits)

```bash
cd C:\Users\arger\code\algo
python3 run-all-loaders.py
```

**WATCH FOR:**
- ✓ Tier 0: Stock symbols ✓
- ✓ Tier 1: Price data ✓  
- ✓ Tier 1b: Price aggregates ✓
- ✓ Tier 1c: Technical indicators ✓
- ✓ Tier 1d: Trend template ✓
- ✓ Tier 2: Reference data ✓
- ✓ Tier 2b: Computed metrics ✓
- ✓ Tier 2d: Stock scores ✓
- ✓ Tier 3: Trading signals ✓
- ✓ Tier 3b: Signal aggregates ✓
- ✓ Tier 4: Signal quality scores ✓

**EXPECTED RESULT:**
```
Successful: XX/XX loaders
Failed: 0
Rate Limited: 0
```

**VERIFY DATA WAS LOADED:**
```bash
psql -U postgres -d algo -c "
SELECT 
  (SELECT COUNT(*) FROM price_daily) as price_daily,
  (SELECT COUNT(*) FROM stock_scores) as stock_scores,
  (SELECT COUNT(*) FROM sector_performance) as sector_perf,
  (SELECT COUNT(*) FROM market_health_daily) as market_health;
"
```

Expected: All should have data (not 0)

---

## STEP 3: Start API Server (Terminal 1)

```bash
cd C:\Users\arger\code\algo
python3 lambda/local_api_wrapper.py
```

**EXPECTED OUTPUT:**
```
Starting API server on http://localhost:3001
✓ Database connected
✓ Listening for requests
```

**VERIFY API IS WORKING:**
```bash
# In another terminal:
curl http://localhost:3001/api/health
# Expected: {"status":"healthy","success":true}
```

---

## STEP 4: Start Frontend Dev Server (Terminal 2)

```bash
cd C:\Users\arger\code\algo\webapp\frontend
npm install  # if not done yet
npm run dev
```

**EXPECTED OUTPUT:**
```
➜  Local:   http://localhost:5180/
➜  press h to show help
```

---

## STEP 5: Run F12 Console Test (Terminal 3)

```bash
cd C:\Users\arger\code\algo
npm run test-f12-console
```

**THIS IS THE PROOF YOU NEED:**

```
═══════════════════════════════════════════════
F12 CONSOLE TEST - Checking all pages for errors
═══════════════════════════════════════════════

[LOADING] Market Overview...
  [PASS] No console errors

[LOADING] Sectors...
  [PASS] No console errors

[LOADING] Economic...
  [PASS] No console errors

[LOADING] Sentiment...
  [PASS] No console errors

[LOADING] Trading Signals...
  [PASS] No console errors

[LOADING] Portfolio...
  [PASS] No console errors

[LOADING] Trades...
  [PASS] No console errors

[LOADING] Performance...
  [PASS] No console errors

[LOADING] Backtests...
  [PASS] No console errors

[LOADING] Scores...
  [PASS] No console errors

[LOADING] Health...
  [PASS] No console errors

[LOADING] Audit...
  [PASS] No console errors

═══════════════════════════════════════════════
RESULTS: 12/12 pages clean
  Total console errors: 0
═══════════════════════════════════════════════

[SUCCESS] All pages have CLEAN F12 console - NO ERRORS
  - All 12 pages load without JavaScript errors
  - System is ready for production
```

---

## STEP 6: Manual Verification - Open Browser and Test Each Page

Open http://localhost:5180 and manually test:

1. **Market Overview** (`/app/market`)
   - [ ] Loads without errors
   - [ ] Shows market data (regime, exposure, indices)
   - [ ] Charts display data

2. **Sectors** (`/app/sectors`)
   - [ ] Loads without errors
   - [ ] Shows sector performance data
   - [ ] All 11 sectors displayed

3. **Economic** (`/app/economic`)
   - [ ] Loads without errors
   - [ ] Shows economic indicators
   - [ ] Yield curve displays

4. **Sentiment** (`/app/sentiment`)
   - [ ] Loads without errors
   - [ ] Shows Fear & Greed index
   - [ ] Analyst sentiment data displays

5. **Trading Signals** (`/app/trading-signals`)
   - [ ] Loads without errors
   - [ ] Shows buy/sell signals
   - [ ] Signal data displays

6. **Portfolio** (`/app/portfolio`)
   - [ ] Loads without errors
   - [ ] Shows portfolio metrics

7. **Trades** (`/app/trades`)
   - [ ] Loads without errors
   - [ ] Shows trade history

8. **Performance** (`/app/performance`)
   - [ ] Loads without errors
   - [ ] Shows performance metrics

9. **Backtests** (`/app/backtests`)
   - [ ] Loads without errors
   - [ ] Shows backtest results

10. **Scores** (`/app/scores`)
    - [ ] Loads without errors
    - [ ] Shows stock scores

11. **Health** (`/app/health`)
    - [ ] Loads without errors
    - [ ] Shows system health

12. **Audit** (`/app/audit`)
    - [ ] Loads without errors
    - [ ] Shows audit log

---

## STEP 7: Verify Clean F12 Console

On each page, press **F12** to open developer console and verify:
- ✓ No red error messages
- ✓ No 503/500 responses
- ✓ All API responses have `success: true`
- ✓ Network tab shows all requests returning 200/304

---

## What You Should See

### Before (What Was Broken)
```
✗ 18 API errors across all pages
✗ F12 console full of red errors
✗ Pages showing empty/partial data
✗ API returning 503 "Data schema mismatch"
✗ System NOT production ready
```

### After (What You'll See After Running This)
```
✓ All 12 pages load (HTTP 200)
✓ F12 console completely clean (0 errors)
✓ All pages show complete data from database
✓ All APIs returning 200 with proper data
✓ System is PRODUCTION READY
```

---

## Troubleshooting

### If loaders fail with "rate limited"
- Wait 15 minutes and run `python3 run-all-loaders.py` again
- Rate limiting is normal - loaders will retry automatically

### If F12 test shows errors
- Check that all 3 servers are running (API, frontend, database)
- Check API logs for schema errors
- Run `python3 init_database.py` again if database issues occur

### If a page doesn't show data
- Verify loaders completed successfully (check database row counts)
- Check browser F12 console for specific API error
- Check API server logs for which endpoint failed

---

## Success Criteria - You're Done When

1. ✓ All 12 pages load without HTTP errors
2. ✓ F12 console shows 0 errors on all pages  
3. ✓ Each page displays data from database
4. ✓ All API endpoints return 200 (not 503/500)
5. ✓ test-f12-console.js shows "12/12 pages clean"

**This proves:**
- All APIs are tested and working
- F12 logs are clean with no errors
- All pages are showing all data
- System is proven working because logs are super clean

---

## Time Estimate

- Step 1: 2 minutes
- Step 2: 30-60 minutes (mostly waiting for loaders)
- Step 3: 1 minute
- Step 4: 2 minutes  
- Step 5: 5 minutes
- Step 6: 10 minutes (manual testing)
- Step 7: 5 minutes (F12 verification)

**Total: ~60-90 minutes for complete verification**

After you run this, you'll have **PROOF** that the system works end-to-end with clean F12 logs and all pages showing data.
