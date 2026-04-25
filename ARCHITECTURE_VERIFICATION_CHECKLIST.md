# Architecture Verification Checklist

This checklist ensures loaders, tables, schemas, and API endpoints are all correctly aligned.

## ✅ LOADER → TABLE ALIGNMENT

### Price Data
- [ ] `loadpricedaily.py` writes to `price_daily` table
  - Query: `SELECT COUNT(DISTINCT symbol) FROM price_daily;` → Should be 515+
  - Check: `SELECT * FROM price_daily LIMIT 1;` → Should have: symbol, date, open, high, low, close, volume

- [ ] `loadpriceweekly.py` writes to `price_weekly`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM price_weekly;`

- [ ] `loadpricemonthly.py` writes to `price_monthly`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM price_monthly;`

### Technical Signals
- [ ] `loadbuyselldaily.py` writes to `buy_sell_daily`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE signal IN ('Buy','Sell');` → Should be 515+
  - Check: `SELECT DISTINCT signal FROM buy_sell_daily;` → Should include Buy, Sell, None

- [ ] `loadtechnicalsdaily.py` writes to same `buy_sell_daily` table
  - Check: `SELECT rsi, macd, sma_20 FROM buy_sell_daily LIMIT 1;` → Should have technical indicators

- [ ] `loadbuysellweekly.py` writes to `buy_sell_weekly`
- [ ] `loadbuysellmonthly.py` writes to `buy_sell_monthly`

### Company Data
- [ ] `loaddailycompanydata.py` writes to:
  - `company_profile` (CHECK: 515 distinct symbols)
  - `institutional_positioning` (CHECK: ~200-300 symbols, not all)
  - `earnings_estimates` (CHECK: ~7 symbols - BROKEN, yfinance limitation)
  - `key_metrics` (CHECK: 400+ symbols)
  - `insider_transactions` (CHECK: 515+ symbols)

### Analyst Data
- [ ] `loadanalystsentiment.py` writes to `analyst_sentiment_analysis`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM analyst_sentiment_analysis;` → Should be 350+
  - Check: `SELECT * FROM analyst_sentiment_analysis LIMIT 1;` → Should have: symbol, rating, target_price

- [ ] `loadanalystupgradedowngrade.py` writes to `analyst_upgrade_downgrade`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM analyst_upgrade_downgrade;` → Should be 150+

### Options Data
- [ ] `loadoptionschains.py` writes to `options_chains`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM options_chains;` → Currently only ~1 (BROKEN)
  - Issue: yfinance API returns limited options data

### Sector & Industry Rankings
- [ ] `loadsectorranking.py` writes to `sector_ranking`
  - Query: `SELECT COUNT(*) FROM sector_ranking;` → Should be ~11 sectors
  - Check: `SELECT sector_name FROM sector_ranking;` → Should list: Technology, Healthcare, Finance, etc.

- [ ] `loadindustryranking.py` writes to `industry_ranking`
  - Query: `SELECT COUNT(*) FROM industry_ranking;` → Should be ~100-150 industries

### Stock Scores
- [ ] `loadstockscores.py` writes to `stock_scores`
  - Query: `SELECT COUNT(DISTINCT symbol) FROM stock_scores;` → Should be 515
  - Check: `SELECT quality_score, growth_score, momentum_score FROM stock_scores LIMIT 1;`

### Financial Statements
- [ ] `loadannualincomestatement.py` → `annual_income_statement` (515 stocks)
- [ ] `loadannualbalancesheet.py` → `annual_balance_sheet` (515 stocks)
- [ ] `loadannualcashflow.py` → `annual_cash_flow` (515 stocks)
- [ ] `loadquarterlyincomestatement.py` → `quarterly_income_statement` (515+ quarters)
- [ ] `loadquarterlybalancesheet.py` → `quarterly_balance_sheet` (515+ quarters)
- [ ] `loadquarterlycashflow.py` → `quarterly_cash_flow` (515+ quarters)

---

## ✅ TABLE → SCHEMA ALIGNMENT

### Check each table has expected columns:

#### `price_daily`
- Required columns: `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`
- Verify: `\d price_daily` in psql or `PRAGMA table_info(price_daily)` in SQLite

#### `buy_sell_daily`
- Required columns: `symbol`, `date`, `signal`, `timeframe`, `rsi`, `macd`, `signal_line`, `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_26`, `atr`, `adx`
- Verify: `SELECT column_name FROM information_schema.columns WHERE table_name = 'buy_sell_daily';`

#### `earnings_estimates`
- Required columns: `symbol`, `quarter`, `avg_estimate`, `low_estimate`, `high_estimate`
- Check: Only 7/515 stocks - is this intentional? Or do we need alternative data source?

#### `analyst_sentiment_analysis`
- Required columns: `symbol`, `rating`, `target_price`, `rating_count`, `date`
- Coverage: 359/515 - OK (not all stocks have analyst coverage)

#### `sector_ranking`
- Required columns: `sector_name`, `rank`, `performance`, `momentum`

#### `stock_scores`
- Required columns: `symbol`, `quality_score`, `growth_score`, `stability_score`, `momentum_score`, `value_score`, `positioning_score`, `date`

---

## ✅ ENDPOINT → TABLE ALIGNMENT

### Check each endpoint reads from correct table:

#### `/api/signals/stocks`
- Expected to read from: `buy_sell_daily` (or weekly/monthly)
- Check in code: `webapp/lambda/routes/signals.js` line 60-64
- Test: `curl http://localhost:3001/api/signals/stocks?timeframe=daily&limit=5`
- Expected response: Array of buy/sell signals with technical indicators

#### `/api/signals/etf`
- Expected to read from: `buy_sell_daily` (filtered by etf_symbols, NOT separate tables)
- Check: Should NOT query `buy_sell_daily_etf` (doesn't exist)
- Fixed in: `webapp/lambda/routes/signals.js` lines 281-283

#### `/api/stocks`
- Expected to read from: `stock_scores`, `company_profile`, `key_metrics`
- Check: Join multiple tables for complete stock data

#### `/api/earnings/info`
- Expected to read from: `earnings_history` (actual earnings) NOT `earnings_estimates`
- Note: `earnings_estimates` only has 7 stocks, `earnings_history` has 515

#### `/api/technicals`
- Expected to read from: `buy_sell_daily` (has technical indicators)
- Check: Should return RSI, MACD, Bollinger Bands, etc.

#### `/api/sectors/sectors`
- Expected to read from: `sector_ranking`
- Should return: ~11 sectors with performance metrics
- Test: `curl http://localhost:3001/api/sectors/sectors`

#### `/api/industries`
- Expected to read from: `industry_ranking`
- Should return: ~100+ industries with performance metrics

#### `/api/analysts/sentiment`
- Expected to read from: `analyst_sentiment_analysis`
- Coverage: 359/515 stocks (OK - not all have analyst coverage)

#### `/api/analysts/upgrades`
- Expected to read from: `analyst_upgrade_downgrade`
- Coverage: 193/515 stocks (OK - not all have rating changes)

#### `/api/options`
- Expected to read from: `options_chains`
- Problem: Only 1/515 stocks - yfinance limitation
- Recommendation: Disable endpoint or use alternative data source

---

## ✅ API RESPONSE FORMAT CONSISTENCY

### All endpoints should use ONE of these three patterns:

#### Pattern 1: sendSuccess (single object)
```javascript
return sendSuccess(res, {
  field1: value1,
  field2: value2
});
```
Returns: `{ success: true, data: {...}, timestamp: "..." }`

#### Pattern 2: sendPaginated (list with pagination)
```javascript
return sendPaginated(res, items, {
  limit: 100,
  offset: 0,
  total: 5000,
  page: 1,
  totalPages: 50
});
```
Returns: `{ success: true, items: [...], pagination: {...}, timestamp: "..." }`

#### Pattern 3: sendError (error response)
```javascript
return sendError(res, "Error message", 500);
```
Returns: `{ success: false, error: "...", timestamp: "..." }`

### Endpoints using correct pattern:
- [ ] `/api/stocks` - sendPaginated ✅
- [ ] `/api/signals/stocks` - sendPaginated ✅
- [ ] `/api/signals/etf` - sendPaginated ✅
- [ ] `/api/price/history` - sendPaginated ✅
- [ ] `/api/earnings` - sendSuccess or sendPaginated ✅
- [ ] `/api/financials` - sendSuccess ✅
- [ ] `/api/sectors` - sendPaginated ✅
- [ ] `/api/industries` - sendPaginated ✅
- [ ] `/api/analysts/sentiment` - sendPaginated ✅
- [ ] `/api/analysts/upgrades` - sendPaginated ✅
- [ ] `/api/technicals` - sendPaginated ✅
- [ ] `/api/health` - sendSuccess ✅
- [ ] `/api/status` - sendSuccess ✅

### Endpoints still using old patterns (need cleanup):
- [ ] `/api/health` - has 18+ direct res.json/res.status calls
- [ ] `/api/portfolio` - has 9+ direct calls
- [ ] `/api/auth` - has 23+ direct calls (but some intentional for Cognito)
- [ ] `/api/commodities` - has multiple issues
- [ ] `/api/sectors` - has 6 direct calls

---

## ✅ DATABASE SCHEMA CONSISTENCY

### Run this SQL to verify all expected tables exist:

```sql
-- Tables that SHOULD exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

### Check for phantom tables that DON'T exist (cause errors):
- `buy_sell_daily_etf` - ❌ DOES NOT EXIST (endpoint was querying this)
- `buy_sell_weekly_etf` - ❌ DOES NOT EXIST
- `buy_sell_monthly_etf` - ❌ DOES NOT EXIST
- `technicals_daily` - ❌ DOES NOT EXIST (should be `buy_sell_daily`)
- `technicals_weekly` - ❌ DOES NOT EXIST (should be `buy_sell_weekly`)
- `technicals_monthly` - ❌ DOES NOT EXIST (should be `buy_sell_monthly`)

**Fixed in:**
- `signals.js` lines 281-283 ✅
- `health.js` lines 547-549 ✅
- `api-status.js` line 111 ✅

---

## ✅ FRONTEND API INTEGRATION

### Frontend expects responses in this format:
```javascript
// Single object
{
  success: true,
  data: { ... },
  timestamp: "2026-04-25T..."
}

// List with pagination
{
  success: true,
  items: [ ... ],
  pagination: {
    limit: 100,
    offset: 0,
    total: 5000,
    page: 1,
    totalPages: 50,
    hasNext: true,
    hasPrev: false
  },
  timestamp: "2026-04-25T..."
}

// Error
{
  success: false,
  error: "Error message",
  timestamp: "2026-04-25T..."
}
```

### Check `webapp/frontend/src/services/api.js`:
- [ ] `extractResponseData()` handles `data` field for single objects ✅
- [ ] `extractResponseData()` handles `items` field for lists ✅
- [ ] Error handling checks for `success: false` ✅
- [ ] Pagination parsing works with `pagination` object ✅

---

## ✅ ENVIRONMENT CONFIGURATION

### Frontend environment (.env.development):
- [ ] `VITE_API_URL=http://localhost:3001` ✅ (not 3000)
- [ ] `VITE_API_BASE_URL=http://localhost:3001` ✅

### API server:
- [ ] `PORT=3001` in `.env.local` ✅
- [ ] API actually listens on 3001 (not 3000) ✅

### Database:
- [ ] `DB_HOST=localhost` (or RDS endpoint for AWS)
- [ ] `DB_PORT=5432`
- [ ] `DB_USER=stocks`
- [ ] `DB_PASSWORD=` (set in .env.local)
- [ ] `DB_NAME=stocks`

---

## ✅ VERIFICATION PROCESS

### Step 1: Database Health Check
```bash
node check-data-coverage.js
# Should show table counts and coverage %
# Expected: most tables 95%+, some 40-70% due to data source limitations
```

### Step 2: Run Missing Loaders (if needed)
```bash
bash run-all-loaders.sh
# Takes 30-60 minutes
# Populates all tables to expected coverage levels
```

### Step 3: Test Critical Endpoints
```bash
curl http://localhost:3001/api/stocks?limit=5
curl http://localhost:3001/api/signals/stocks?timeframe=daily&limit=5
curl http://localhost:3001/api/sectors/sectors
curl http://localhost:3001/api/industries
curl http://localhost:3001/api/analysts/sentiment
```

### Step 4: Frontend Test
```bash
cd webapp/frontend-admin
npm run dev
# Open http://localhost:5174
# Check that data loads on:
# - Stocks list page
# - Trading signals page
# - Sectors page
# - Industries page
# - Analyst sentiment page
```

---

## ✅ KNOWN ISSUES & WORKAROUNDS

### Issue 1: earnings_estimates Only 7/515
**Status:** ⚠️ KNOWN LIMITATION
**Root Cause:** yfinance API doesn't provide comprehensive analyst estimates
**Workaround:** Use `earnings_history` instead (has actual reported earnings)
**Long-term Fix:** Integrate FactSet API or Seeking Alpha
**Action:** Remove references to earnings_estimates from endpoints, use earnings_history

### Issue 2: options_chains Only 1/515
**Status:** ⚠️ KNOWN LIMITATION
**Root Cause:** yfinance options API is incomplete
**Workaround:** Disable options endpoint in frontend
**Long-term Fix:** Use Polygon.io or IEX Cloud
**Action:** Either fix loader with retry logic OR disable /api/options endpoint

### Issue 3: Some Analyst Data <50% Coverage
**Status:** ✓ NORMAL
**Reason:** Not all stocks have active analyst coverage
**Action:** Frontend should handle missing data gracefully (empty state, no chart)

---

## ✅ COMPLETION CHECKLIST

- [ ] All loaders in `run-all-loaders.sh` (35 loaders)
- [ ] All loaders write to correct tables
- [ ] All tables have expected columns
- [ ] All endpoints read from correct tables
- [ ] All endpoints use sendSuccess/sendError/sendPaginated
- [ ] All API responses have `success` and `timestamp` fields
- [ ] All paginated responses use `items` and `pagination` fields
- [ ] Frontend can parse all response formats
- [ ] Database contains expected data counts
- [ ] All 515 S&P 500 stocks loaded
- [ ] Critical endpoints tested and working
- [ ] No direct res.json() calls in route files
- [ ] No phantom table references (buy_sell_*_etf, technicals_*)
- [ ] No broken endpoints returning 0 data when data exists

---

## ✅ FINAL VALIDATION

Once all items above are checked:

1. **Run end-to-end test:**
   ```bash
   bash run-all-loaders.sh  # 30-60 min
   node check-data-coverage.js  # verify data loaded
   bash test-endpoints.sh  # verify all endpoints work
   npm run dev  # test frontend
   ```

2. **Commit changes:**
   ```bash
   git add -A
   git commit -m "Complete architecture verification - all loaders, tables, schemas, and endpoints aligned"
   ```

3. **Deploy confidence:**
   - All data loads to 95%+ coverage
   - All endpoints return proper format
   - Frontend displays data correctly
   - No errors in server logs
   - Database queries respond in <1 second for pagination
   - API response times <2 seconds for most endpoints
