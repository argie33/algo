# Phase 5: Frontend Visual Testing Plan

**Objective:** Verify that all frontend pages display real data correctly and match API responses.

**Setup:**
```bash
# Terminal 1: Start dev server
cd webapp/frontend
npm start

# Terminal 2: Monitor API responses
python3 -c "from lambda.api.lambda_function import handler; import json; print(json.dumps(handler({...}), indent=2))"
```

---

## ✅ CORE PAGES (High Priority)

### 1. Dashboard
- **URL:** `/`
- **Expected Data:** Market exposure percentage, market stage, uptrend/downtrend indicator
- **API Call:** `/api/algo/markets`
- **Test:**
  - [ ] Market exposure % displays (should be 0-100%)
  - [ ] Market stage shows Stage 1/2/3/4
  - [ ] Today's date matches server date
  - [ ] No error messages visible
  - [ ] Performance metrics (if available) render correctly

### 2. Stock Scores
- **URL:** `/scores`
- **Expected Data:** 9,989 stock scores with real values
- **API Call:** `/api/scores/stockscores`
- **Test:**
  - [ ] Table loads with real symbols (AAPL, MSFT, etc.)
  - [ ] Composite scores between 0-100
  - [ ] Component scores (momentum, value, growth, stability) visible
  - [ ] Pagination works (10+ pages expected)
  - [ ] Sorting by score works
  - [ ] Filtering by symbol works
  - [ ] Each symbol shows real score (not placeholder)

### 3. Signals (Buy/Sell)
- **URL:** `/signals`
- **Expected Data:** 12,996 buy/sell signals
- **API Call:** `/api/signals`
- **Test:**
  - [ ] Signal list loads with real data
  - [ ] Buy signals highlighted differently from sell signals
  - [ ] Date filter works (last 5 days, week, month)
  - [ ] Symbol search works
  - [ ] Signal count matches database (~12,996)
  - [ ] Recent signals show current/recent dates
  - [ ] Price, volume data displays

### 4. Portfolio
- **URL:** `/portfolio`
- **Expected Data:** Current positions, P&L, performance
- **API Calls:** `/api/portfolio`, `/api/portfolio/holdings`, `/api/portfolio/performance`
- **Test:**
  - [ ] Holdings table shows all open positions
  - [ ] Entry price, current price, gain/loss displays
  - [ ] P&L % shown with color coding (green/red)
  - [ ] Total portfolio value displays
  - [ ] Position count matches database
  - [ ] Cash balance shows
  - [ ] Performance metrics (if available)

### 5. Sectors
- **URL:** `/sectors`
- **Expected Data:** 11 sectors with ranking history
- **API Call:** `/api/sectors`
- **Test:**
  - [ ] All 11 sectors load (Technology, Healthcare, Financials, etc.)
  - [ ] Each sector shows: symbols, average price, momentum
  - [ ] Ranking history (1w, 4w, 12w ago) displays
  - [ ] Performance metrics (1d, 5d, 20d) visible
  - [ ] PE analysis (trailing, forward) shows
  - [ ] Sector rotation indicator works

### 6. Industries
- **URL:** `/industries`
- **Expected Data:** 100+ industries with rankings
- **API Call:** `/api/industries`
- **Test:**
  - [ ] Industries load (100+ should be present)
  - [ ] Each industry shows member symbols
  - [ ] Average price calculates
  - [ ] Ranking history shows
  - [ ] Performance metrics visible
  - [ ] Sorting by rank works
  - [ ] Search/filter by industry name works

### 7. Economic Dashboard
- **URL:** `/economic`
- **Expected Data:** 100,151 economic data rows (41 series)
- **API Call:** `/api/economic/leading-indicators`
- **Test:**
  - [ ] Economic indicators chart renders
  - [ ] Multiple time series visible (e.g., unemployment, inflation, GDP)
  - [ ] Dates are reasonable (recent data)
  - [ ] Data points show actual values (not placeholders)
  - [ ] Trend visualization works
  - [ ] Legend shows indicator names

### 8. Market Exposure
- **URL:** `/market-exposure` (or Dashboard widget)
- **Expected Data:** Daily exposure tracking
- **API Call:** `/api/algo/markets`
- **Test:**
  - [ ] Exposure % shows (0-100)
  - [ ] Daily history visible
  - [ ] Regime indicator shows (uptrend, consolidation, downtrend)
  - [ ] Distribution days count (if available)
  - [ ] Factors breakdown shows

---

## 📊 SECONDARY PAGES (Medium Priority)

### 9. Technical Analysis
- **URL:** `/technical` (if exists)
- **Expected Data:** RSI, ADX, ATR, moving averages
- **Test:**
  - [ ] Technical indicators chart renders
  - [ ] RSI (0-100) displays correctly
  - [ ] ADX shows trend strength
  - [ ] Moving averages (SMA50, SMA200) visible
  - [ ] Multiple timeframes available
  - [ ] Recent data current

### 10. Swing Trader Scores
- **URL:** `/swing-scores` (if exists)
- **Expected Data:** Swing trading quality scores
- **API Call:** `/api/algo/swing-scores`
- **Test:**
  - [ ] Score ranges display (A, B, C, D, F)
  - [ ] Symbol list shows high-quality swings
  - [ ] Components breakdown visible
  - [ ] Date filter works

### 11. Trade History
- **URL:** `/trades` (if exists)
- **Expected Data:** Past trades with entry/exit, P&L
- **API Call:** `/api/trades`
- **Test:**
  - [ ] All trades display
  - [ ] Entry date, entry price, exit price show
  - [ ] P&L calculation correct
  - [ ] Trade duration visible
  - [ ] Win/loss count visible

### 12. Backtest Results
- **URL:** `/research` or `/backtests`
- **Expected Data:** Historical backtest runs
- **API Call:** `/api/research/backtests`
- **Test:**
  - [ ] Backtest list loads (if any exist)
  - [ ] Parameters show (date range, symbols)
  - [ ] Results summary visible (win rate, Sharpe, max DD)
  - [ ] Empty state message if no backtests

---

## ⚠️ OPTIONAL PAGES (Nice to Have)

### 13. Earnings Calendar
- **URL:** `/earnings-calendar`
- **Expected Data:** Upcoming earnings dates
- **Status:** May be empty (no earnings loader implemented)
- **Test:**
  - [ ] Page loads without error
  - [ ] Shows message if no data available

### 14. Market Sentiment
- **URL:** `/sentiment` (if exists)
- **Expected Data:** Fear & Greed index, AAII sentiment
- **Status:** May be partially empty
- **Test:**
  - [ ] Page loads
  - [ ] Sentiment indicator displays
  - [ ] Historical chart visible
  - [ ] Empty state if no data

### 15. Risk Dashboard
- **URL:** `/risk` (if exists)
- **Expected Data:** Portfolio risk metrics, drawdown, concentration
- **Test:**
  - [ ] Max drawdown displays
  - [ ] VaR/CVaR shown
  - [ ] Concentration chart visible
  - [ ] Daily loss limit shown

---

## 🔍 DATA QUALITY CHECKS (For All Pages)

### For Each Page, Verify:

1. **No Console Errors**
   - [ ] Open browser DevTools (F12)
   - [ ] Check Console tab - no red errors
   - [ ] Check Network tab - all API calls return 200 OK

2. **Data Completeness**
   - [ ] No "null" or "undefined" text visible
   - [ ] No [object Object] errors
   - [ ] Dates in ISO format or readable format
   - [ ] Numbers have reasonable precision

3. **Performance**
   - [ ] Page loads within 2 seconds
   - [ ] Tables with 100+ rows paginate
   - [ ] Search/filter responds immediately (<500ms)
   - [ ] Charts render without lag

4. **Responsive Design**
   - [ ] Page works on 1920x1080 desktop
   - [ ] Table columns visible without horizontal scroll
   - [ ] Charts don't overflow container
   - [ ] All buttons clickable

5. **API Response Validation**
   - [ ] Response contains expected fields
   - [ ] Row counts match database expectations
   - [ ] Data types correct (numbers, strings, dates)
   - [ ] No hardcoded test data

---

## 📋 TESTING PROTOCOL

### Step 1: Setup (5 minutes)
```bash
# Terminal 1: Start frontend
cd webapp/frontend
npm start
# Wait for "webpack compiled"

# Terminal 2: Monitor API calls
# Open browser DevTools → Network tab
```

### Step 2: Test Each Page (30-45 minutes)
- Navigate to URL
- Verify data loads
- Check console for errors
- Verify calculations/data make sense
- Take screenshot if issue found

### Step 3: Document Issues
- Screenshot of issue
- URL/page name
- Expected vs actual data
- Severity (blocker, major, minor)

### Step 4: Report
- List of pages tested
- Any data mismatches found
- Any missing endpoints
- Any calculation errors

---

## 🎯 SUCCESS CRITERIA

**Phase 5 PASS if:**
- [ ] All 8 core pages display real data correctly
- [ ] No console errors on any page
- [ ] API responses match database expectations
- [ ] All calculations appear correct
- [ ] No "null"/"undefined" visible
- [ ] Pages load within 2 seconds

**Phase 5 FAIL if:**
- [ ] Any core page shows placeholder data
- [ ] API endpoint returns empty/error
- [ ] Data calculation mismatch detected
- [ ] Console has red errors
- [ ] Database count != API count

---

## 📝 NOTES

- **Earnings Calendar:** Expected to be empty (no earnings loader implemented)
- **Backtests:** May be empty if no backtests have been run
- **Sentiment:** May be partial (depends on FRED API configuration)
- **Quality Metrics:** May have low coverage (only 4 rows in database)

Date: 2026-05-16
System: Stock Analytics Platform
Version: Production-Ready Verification Phase
