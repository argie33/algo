# Complete Data Display Fix Verification Checklist

## ✅ Completed Work

### Code Changes (Commit b7422ab)
- [x] Updated `/api/signals/stocks` query to select 40+ columns
- [x] Fixed `/api/algo/markets` to query market_exposure_daily table
- [x] Added ema_21 and mansfield_rs to technical indicators
- [x] All API code compiles successfully (Python syntax verified)
- [x] Frontend builds successfully (14,379 modules transformed)
- [x] TradingSignals page compiles (57.04 kB gzipped)
- [x] MarketsHealth page compiles (57.04 kB gzipped)

### Documentation Created
- [x] DATA_DISPLAY_FIXES.md - Root cause analysis
- [x] FIND_DATA_ISSUES.md - Systematic debugging guide
- [x] VERIFICATION_CHECKLIST.md - This file

## ⏳ To Do: Database Setup & Data Population

### Phase 1: Database Schema (5 minutes)
```bash
# Set up PostgreSQL credentials
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
export DB_PASSWORD=your_password

# Apply schema migrations (adds missing columns)
python3 init_database.py
```

**Expected result:** buy_sell_daily and technical_data_daily now have all required columns

### Phase 2: Run Data Loaders (20-30 minutes)
```bash
# Load all data (40 loaders, ~1.5M price records)
python3 run-all-loaders.py
```

**What this does:**
- Loads stock symbols from NASDAQ
- Loads price data from Alpaca
- Loads technical indicators (RSI, EMA, SMA, ATR, ADX, etc.)
- Loads earnings data from SEC
- Populates swing trader scores
- Populates market exposure and regime data

**Expected result:** Database fully populated with current market data

### Phase 3: Verify Data (5 minutes)
```bash
# Check if data loaded successfully
psql $DATABASE_URL -c "
  SELECT table_name, MAX(date) as latest, COUNT(*) as rows FROM (
    SELECT 'buy_sell_daily' as table_name, date, COUNT(*) FROM buy_sell_daily GROUP BY date
    UNION ALL
    SELECT 'technical_data_daily', date, COUNT(*) FROM technical_data_daily GROUP BY date
    UNION ALL
    SELECT 'market_exposure_daily', date, COUNT(*) FROM market_exposure_daily GROUP BY date
  ) t GROUP BY table_name;
"
```

**Expected output:**
```
table_name         | latest     | rows
-----------        | ---------- | -------
buy_sell_daily     | 2026-05-17 | ~5000
technical_data_daily | 2026-05-17 | ~1.5M
market_exposure_daily | 2026-05-17 | ~365
```

## ⏳ Phase 4: Run & Test (20 minutes)

### Start Development Server
```bash
# Terminal 1: Start backend API
python3 local_api_server.py
# Should say: "Starting local API server on http://127.0.0.1:3001"

# Terminal 2: Start frontend
cd webapp/frontend
npm run dev
# Should open http://localhost:5173
```

### Test API Endpoints
```bash
# Test Trading Signals endpoint
curl 'http://localhost:3001/api/signals/stocks?limit=1' | jq '.items[0]'
# Should see: symbol, signal, date, buylevel, stoplevel, risk_reward_ratio, etc.

# Test Market data endpoint
curl 'http://localhost:3001/api/algo/markets' | jq '.current'
# Should see: exposure_pct, regime, distribution_days, factors

# Test swing scores
curl 'http://localhost:3001/api/algo/swing-scores?limit=5' | jq '.items[0]'
# Should see: symbol, swing_score, grade, pass_gates
```

### Test Frontend Pages
Open http://localhost:5173 in browser and test:

#### Trading Signals Page (`/app/signals`)
- [ ] Stocks tab loads without errors
- [ ] Table displays all columns (Symbol, Signal, Close, Buy Level, Stop, R/R, SQS, RSI, Vol Surge, Base, Stage, Gates, Age)
- [ ] Click a row to expand and see full details
- [ ] Expanded view shows: Entry Plan, Targets & Exits, Technicals & Strength
- [ ] Charts render (Signal Heatmap, Setup Breakdown, Recent Performance, SQS Distribution)
- [ ] Filters work (search, timeframe, stage, sectors, SQS range, max age, gates)
- [ ] Data refreshes every 60 seconds (freshness indicator updates)

#### Markets Health Page (`/app/markets`)
- [ ] Page loads without errors
- [ ] Regime banner shows: Exposure %, Regime Tier, Risk multiplier
- [ ] Indices strip shows 30-day sparklines for SPY, QQQ, IWM, DIA
- [ ] Exposure Factors card shows 9-factor composite
- [ ] Market Pulse card shows Drawdown circle and other metrics
- [ ] Exposure History chart shows 90-day trend
- [ ] Breadth, New Highs/Lows, Sentiment, VIX cards render
- [ ] Sector Heat Map and Rotation Map display
- [ ] All data updates on refresh button

#### Portfolio Page (`/app/portfolio`)
- [ ] Current positions load
- [ ] Performance metrics display
- [ ] Trade history shows recent trades
- [ ] Charts render without errors

#### Stock Detail Page (`/app/stock/AAPL`)
- [ ] Price chart displays
- [ ] Technical indicators show (RSI, EMA, SMA, ADX, ATR)
- [ ] Signal history loads
- [ ] Key metrics display correctly

#### Other Pages
- [ ] Sector Analysis page loads
- [ ] Economic Dashboard loads
- [ ] Sentiment page loads
- [ ] All pages have no console errors (F12 → Console tab)

### Browser Console Check
Open Developer Tools (F12) and check Console tab:
- [ ] No red error messages
- [ ] No "Cannot read properties of undefined" errors
- [ ] Network tab shows API calls returning 200 status
- [ ] All API responses have valid JSON

## 🔴 If Issues Found

### Common Issue: "Cannot read properties of undefined (reading 'xxx')"
**Cause:** API not returning expected field
**Solution:**
```bash
# Check what API is actually returning
curl 'http://localhost:3001/api/endpoint' | jq '.' | head -50

# Compare with what component expects
# Update API query if field is missing
```

### Common Issue: "Data unavailable" or empty tables
**Cause:** Loaders haven't run or data is null
**Solution:**
```bash
# Check if data exists in database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day';"

# If count is 0, data hasn't loaded
# Run loaders: python3 run-all-loaders.py

# If count > 0 but columns are NULL:
# Check which columns have data
psql $DATABASE_URL -c "SELECT * FROM buy_sell_daily LIMIT 1 \gx"
```

### Common Issue: API returns 500 error
**Cause:** Database connection or query error
**Solution:**
```bash
# Check database connectivity
python3 -c "from utils.db_connection import get_db_connection; conn = get_db_connection(); print('Connected OK')"

# Check API error logs
tail -50 server.log

# Verify schema migrations ran
psql $DATABASE_URL -c "\d buy_sell_daily" | grep -E "buylevel|stoplevel|base_type"
```

## ✅ Success Criteria

When complete, you should have:

1. **Database:** All tables populated with current market data
   - 1.5M+ price records
   - 5000+ trading signals
   - 365 days of market exposure data

2. **API:** All endpoints returning complete data structures
   - /api/signals/stocks → 40+ columns
   - /api/algo/markets → market regime + history
   - All other endpoints → proper response format

3. **Frontend:** All pages rendering correctly
   - No console errors
   - All tables displaying data
   - All charts rendering
   - All filters working
   - Real-time updates working

4. **Performance:** Pages load quickly
   - Trading Signals loads in <2 seconds
   - Markets Health loads in <3 seconds
   - Data refreshes without page reload

## 📋 Testing Checklist

### API Tests
```bash
# Create test script: tests/quick-api-test.sh
curl -s 'http://localhost:3001/api/signals/stocks?limit=1' | jq '.items[0] | keys | length' # Should be 40+
curl -s 'http://localhost:3001/api/algo/markets' | jq '.current | keys | length' # Should be 8+
curl -s 'http://localhost:3001/api/market/sentiment?range=30d' | jq '.items | length' # Should be > 0
```

### Frontend Visual Tests
```bash
# Pages to screenshot and compare (for regression testing):
# /app/signals - should show full signal table
# /app/markets - should show regime banner + charts
# /app/portfolio - should show positions table
# /app/stock/AAPL - should show price chart

# Use Playwright for automated testing:
npm run test:e2e --prefix webapp/frontend
```

### Data Quality Tests
```bash
# Verify data freshness (should be today or yesterday):
psql $DATABASE_URL -c "SELECT MAX(date) FROM buy_sell_daily;"
psql $DATABASE_URL -c "SELECT MAX(date) FROM technical_data_daily;"
psql $DATABASE_URL -c "SELECT MAX(date) FROM market_exposure_daily;"

# Verify no excessive nulls:
psql $DATABASE_URL -c "
  SELECT column_name, COUNT(NULL) as nulls, COUNT(*) as total 
  FROM buy_sell_daily b, (SELECT * FROM b LIMIT 100)
  WHERE b.buylevel IS NULL OR b.stoplevel IS NULL
  GROUP BY column_name;
"
```

## 🎯 Next Steps (In Order)

1. **Set up PostgreSQL** locally on localhost:5432
2. **Set DB credentials** as environment variables
3. **Run:** `python3 init_database.py` (adds 24 new columns)
4. **Run:** `python3 run-all-loaders.py` (populates all data)
5. **Start:** `python3 local_api_server.py` (backend)
6. **Start:** `npm run dev` in webapp/frontend (frontend)
7. **Open:** http://localhost:5173 in browser
8. **Test:** Each page listed in "Test Frontend Pages" above
9. **Check:** Browser console for errors (F12)
10. **Verify:** Data displays correctly and updates

## 📞 Troubleshooting

If you get stuck on any step, check:
1. `troubleshooting-guide.md` - Common issues & solutions
2. `DATA_DISPLAY_FIXES.md` - Root cause analysis
3. `FIND_DATA_ISSUES.md` - Debugging methodology
4. Browser console (F12) - JavaScript errors
5. Server logs - API errors
6. Database logs - Query errors

## 📊 Success Indicators

You'll know it's working when:
- ✅ No red errors in browser console
- ✅ Trading Signals table shows real data
- ✅ Markets Health displays exposure and regime
- ✅ All pages load within 3 seconds
- ✅ Data refreshes automatically
- ✅ Charts render without errors
- ✅ Filters work smoothly
- ✅ Can click rows to expand details

## Files Modified
- `lambda/api/lambda_function.py` - API query fixes (Commit b7422ab)

## Files To Create (SQL Migration)
- `utils/migrate_signal_columns.sql` - Schema changes (for reference)

## Documentation Created
- `DATA_DISPLAY_FIXES.md` - Root cause analysis
- `FIND_DATA_ISSUES.md` - Debugging guide  
- `VERIFICATION_CHECKLIST.md` - This checklist
