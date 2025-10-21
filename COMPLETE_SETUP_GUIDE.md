# Complete Market Indicators Setup & Testing Guide

## Phase 1: Database Setup & Data Loading

### Step 1A: Reset Database to Loader Schema
This creates the correct table structure that the loaders expect:

```bash
cd /home/stocks/algo/webapp/lambda

# Run the reset script to create proper schema
psql -U postgres -d stocks -f scripts/reset-database-to-loaders.sql 2>&1
```

**Expected Output**: Tables created successfully
- company_profile
- price_daily
- etf_price_daily
- market_data
- key_metrics
- last_updated
- naaim
- aaii_sentiment

### Step 1B: Load Data (Takes 5-10 minutes)
```bash
cd /home/stocks/algo

# 1. Load stock price data (required for all indicators)
python3 loadpricedaily.py

# 2. Load company info and market data for stocks
python3 loadinfo.py

# 3. Load professional sentiment (NAAIM)
python3 loadnaaim.py

# 4. Load retail sentiment (AAII)
python3 loadaaiidata.py

# 5. (Optional) Load Fear & Greed Index
python3 loadfeargreed.py

# 6. (Optional) Load buy/sell signals
python3 loadbuyselldaily.py
```

### Step 1C: Verify Data Loaded

```bash
# Check treasury yields (^TNX = 10Y, ^IRX = 3M)
psql -U postgres -d stocks -c \
  "SELECT symbol, close, date FROM price_daily \
   WHERE symbol IN ('^TNX', '^IRX') \
   ORDER BY date DESC LIMIT 2;"

# Expected: 2 rows with ^TNX and ^IRX prices

# Check market breadth data
psql -U postgres -d stocks -c \
  "SELECT COUNT(DISTINCT symbol), COUNT(*) FROM price_daily \
   WHERE date >= CURRENT_DATE - INTERVAL '5 days';"

# Expected: 3000+ rows spanning multiple stocks

# Check professional sentiment
psql -U postgres -d stocks -c \
  "SELECT date, naaim_number_mean, bullish FROM naaim \
   ORDER BY date DESC LIMIT 2;"

# Expected: Recent data with bullish percentage

# Check retail sentiment
psql -U postgres -d stocks -c \
  "SELECT date, bullish, neutral, bearish FROM aaii_sentiment \
   ORDER BY date DESC LIMIT 2;"

# Expected: Recent data with sentiment percentages
```

---

## Phase 2: Backend Setup & Testing

### Step 2A: Fix Backend Routes

The backend uses correct table names but we need to ensure queries are right.

**Current status**:
- ✅ Yield Curve queries use `price_daily` table with `close` column
- ✅ Breadth queries use `price_daily` with `open`/`close`
- ✅ Sentiment queries use `naaim` and `aaii_sentiment` tables

**File**: `/home/stocks/algo/webapp/lambda/routes/market.js` (already updated)

### Step 2B: Test Individual Endpoints

Start backend server:
```bash
cd /home/stocks/algo/webapp/lambda
npm start  # or: node app.js or: serverless offline
```

In another terminal, test each endpoint:

```bash
# Test 1: Yield Curve (from /api/market/overview response)
curl -s http://localhost:3001/api/market/overview | \
  jq '.data.yield_curve'

# Expected output:
# {
#   "tnx_10y": 4.35,
#   "irx_2y": 5.42,
#   "spread_10y_2y": -1.07,
#   "is_inverted": true,
#   "date": "2024-10-21"
# }

# Test 2: Market Breadth
curl -s http://localhost:3001/api/market/breadth

# Expected output:
# {
#   "success": true,
#   "data": {
#     "total_stocks": 3248,
#     "advancing": 1856,
#     "declining": 1234,
#     "advance_decline_ratio": "1.51"
#   }
# }

# Test 3: Sentiment Divergence
curl -s http://localhost:3001/api/market/sentiment-divergence

# Expected output:
# {
#   "success": true,
#   "data": {
#     "professional_bullish": 68.5,
#     "retail_bullish": 45.2,
#     "divergence": -23.3,
#     "signal": "Professionals Overly Bullish"
#   }
# }
```

### Step 2C: Run Backend Tests

```bash
cd /home/stocks/algo/webapp/lambda

# Run market route tests
npm test -- tests/unit/routes/market.test.js

# Run all tests
npm test

# Expected: All tests pass
```

---

## Phase 3: Frontend Setup & Testing

### Step 3A: Update Frontend Components

Verify components exist:
```bash
ls -la /home/stocks/algo/webapp/frontend/src/components/ | grep -i "yield\|mcclellan\|sentiment"
```

Expected files:
- ✅ `YieldCurveCard.jsx`
- ✅ `McClellanOscillatorChart.jsx`
- ✅ `SentimentDivergenceChart.jsx`

### Step 3B: Build Frontend

```bash
cd /home/stocks/algo/webapp/frontend

# Install dependencies (if needed)
npm install

# Build for production
npm run build

# Expected: No errors, dist folder created
```

### Step 3C: Verify Frontend Imports

Check that MarketOverview.jsx has imports:
```bash
grep -n "YieldCurveCard\|McClellanOscillator\|SentimentDivergence" \
  /home/stocks/algo/webapp/frontend/src/pages/MarketOverview.jsx
```

Expected: 3 import statements found

### Step 3D: Test Frontend Locally

```bash
cd /home/stocks/algo/webapp/frontend

# Start dev server
npm run dev

# Open http://localhost:5173
# Navigate to Market Overview page
# Verify you see:
# 1. Yield Curve card (top left)
# 2. McClellan Oscillator chart (top right)
# 3. Sentiment Divergence chart (full width below)
```

---

## Phase 4: End-to-End Testing

### Step 4A: Verify Data Flow

```bash
# 1. Check database has all required data
psql -U postgres -d stocks -c "
  SELECT
    (SELECT COUNT(DISTINCT symbol) FROM price_daily) as price_records,
    (SELECT COUNT(*) FROM naaim) as naaim_records,
    (SELECT COUNT(*) FROM aaii_sentiment) as aaii_records,
    (SELECT MAX(date) FROM price_daily) as latest_price_date;
"

# 2. Check backend can access data
curl -s http://localhost:3001/api/market/overview | jq '.data | keys'

# 3. Verify frontend calls APIs
# Open browser Dev Tools (F12)
# Go to Network tab
# Navigate to Market Overview
# Look for API calls to:
# - /api/market/overview
# - /api/market/mcclellan-oscillator
# - /api/market/sentiment-divergence
```

### Step 4B: Smoke Test All Components

```bash
# Start everything
cd /home/stocks/algo/webapp/lambda && npm start &
cd /home/stocks/algo/webapp/frontend && npm run dev &

# Open browser at http://localhost:5173/market-overview

# Verify:
# [ ] Page loads without errors
# [ ] 3 new indicator components display
# [ ] Real data shows (not "N/A" or defaults)
# [ ] Data updates every 60 seconds
# [ ] No console errors

# Trigger manual refresh:
# [ ] Open DevTools Console
# [ ] Clear any errors
# [ ] F5 to refresh page
# [ ] Verify data reloads
```

---

## Phase 5: Test Suite Execution

### Step 5A: Run All Tests

```bash
cd /home/stocks/algo/webapp/lambda

# Run all tests
npm test 2>&1 | tee test-results.log

# Check results
grep -E "PASS|FAIL|Tests:" test-results.log
```

### Step 5B: Create Test Report

```bash
# Generate test coverage
npm test -- --coverage > coverage-report.txt

# View report
cat coverage-report.txt | grep -E "File|Statements|Branches|Functions|Lines"
```

### Step 5C: Update Market Route Tests

If tests are failing, add these test cases to `market.test.js`:

```javascript
describe("Market Indicators", () => {
  test("GET /market/yield-curve returns spread data", async () => {
    query.mockResolvedValue({
      rows: [{
        tnx_10y: 4.35,
        irx_2y: 5.42,
        date: new Date().toISOString().split('T')[0],
        spread: -1.07,
        is_inverted: true
      }]
    });

    const response = await request(app).get("/market/yield-curve");
    expect(response.status).toBe(200);
    expect(response.body.data).toHaveProperty('spread_10y_2y');
  });

  test("GET /market/breadth-indices returns advance/decline counts", async () => {
    query.mockResolvedValue({
      rows: [{
        total_stocks: 3248,
        advancing: 1856,
        declining: 1234,
        advance_decline_ratio: 1.51
      }]
    });

    const response = await request(app).get("/market/breadth-indices");
    expect(response.status).toBe(200);
    expect(response.body.data).toHaveProperty('advancing');
  });

  test("GET /market/sentiment-divergence returns sentiment data", async () => {
    query.mockResolvedValue({
      rows: [{
        date: new Date().toISOString().split('T')[0],
        professional_bullish: 68.5,
        retail_bullish: 45.2,
        divergence: -23.3
      }]
    });

    const response = await request(app).get("/market/sentiment-divergence");
    expect(response.status).toBe(200);
    expect(response.body.data).toHaveProperty('divergence');
  });
});
```

---

## Phase 6: Verification Checklist

### Database ✅
- [ ] price_daily has 1000+ records for treasury symbols (^TNX, ^IRX)
- [ ] price_daily has 90+ days of data for multiple stocks
- [ ] naaim table has recent data (within 7 days)
- [ ] aaii_sentiment table has recent data (within 7 days)

### Backend ✅
- [ ] `/api/market/overview` returns with `yield_curve` object
- [ ] `/api/market/breadth-indices` returns advance/decline counts
- [ ] `/api/market/sentiment-divergence` returns professional vs retail sentiment
- [ ] All endpoints return 200 with valid data
- [ ] Error handling works for missing data

### Frontend ✅
- [ ] YieldCurveCard displays spread and inversion status
- [ ] McClellanOscillatorChart displays breadth momentum
- [ ] SentimentDivergenceChart displays professional vs retail
- [ ] Components auto-update every 60 seconds
- [ ] No console errors or warnings
- [ ] Components handle missing data gracefully

### Tests ✅
- [ ] All market route tests pass
- [ ] No test failures or skipped tests
- [ ] Test coverage > 80%
- [ ] New indicator tests included

---

## Troubleshooting

### Issue: "No data available" from endpoints

**Solution**: Check if data loaders ran successfully
```bash
# Check last run times
psql -U postgres -d stocks -c \
  "SELECT script_name, last_run FROM last_updated \
   ORDER BY last_run DESC LIMIT 10;"

# If empty/old, re-run loaders:
cd /home/stocks/algo
python3 loadpricedaily.py
python3 loadnaaim.py
python3 loadaaiidata.py
```

### Issue: Treasury symbols (^TNX, ^IRX) not found

**Solution**: These symbols need to be in price_daily table
```bash
# Check if symbols exist
psql -U postgres -d stocks -c \
  "SELECT DISTINCT symbol FROM price_daily WHERE symbol LIKE '^%' LIMIT 10;"

# If missing, check if loadpricedaily.py includes them
grep -i "TNX\|IRX" /home/stocks/algo/loadpricedaily.py
```

### Issue: Frontend components not rendering

**Solution**: Check imports and check browser console
```bash
# Verify imports exist
grep "import.*YieldCurve" /home/stocks/algo/webapp/frontend/src/pages/MarketOverview.jsx

# Check for API errors in console
# Open DevTools → Console → Look for error messages
# Check Network tab for failed API calls
```

### Issue: Tests failing

**Solution**: Ensure database mocks are set up
```bash
# Run single test file with logging
npm test -- tests/unit/routes/market.test.js --verbose

# Check mock implementation
grep -A 5 "jest.mock" /home/stocks/algo/webapp/lambda/tests/unit/routes/market.test.js
```

---

## Success Criteria

Everything is working when:

✅ **Database**:
- `SELECT * FROM price_daily WHERE symbol IN ('^TNX','^IRX')` returns data
- `SELECT * FROM naaim ORDER BY date DESC LIMIT 1` returns recent data
- `SELECT * FROM aaii_sentiment ORDER BY date DESC LIMIT 1` returns recent data

✅ **Backend**:
- All 3 endpoints return status 200 with real data
- No "N/A" or placeholder values

✅ **Frontend**:
- Market Overview page shows all 3 new indicator components
- Components display real data (not loading states)
- Browser console has no errors

✅ **Tests**:
- npm test passes with 0 failures
- Coverage report shows >80% coverage for market routes

---

## Quick Command Reference

```bash
# Database verification
psql -U postgres -d stocks -c "SELECT COUNT(*) FROM price_daily"
psql -U postgres -d stocks -c "SELECT MAX(date) FROM naaim"

# Run loaders
cd /home/stocks/algo && python3 loadpricedaily.py && python3 loadnaaim.py && python3 loadaaiidata.py

# Backend tests
cd /home/stocks/algo/webapp/lambda && npm test

# Frontend build
cd /home/stocks/algo/webapp/frontend && npm run build

# Test endpoints
curl http://localhost:3001/api/market/overview | jq '.data.yield_curve'

# View logs
tail -f /home/stocks/algo/webapp/lambda/logs/*.log
```

