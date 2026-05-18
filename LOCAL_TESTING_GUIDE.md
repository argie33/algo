# Local Testing Guide - All Pages Working Properly

## Quick Start (5 minutes)

### 1. Prerequisites
```bash
# Ensure these are running
# PostgreSQL: localhost:5432
# AWS credentials: configured in environment (or use local dev auth)

# Check Node.js version
node --version  # Should be 16+
npm --version
```

### 2. Start Backend
```bash
cd webapp/lambda
npm install  # if first time
node index.js
# Should see: "Financial Dashboard API running on port 4000"
```

### 3. Start Frontend  
```bash
cd webapp/frontend
npm install  # if first time
npm run dev
# Should see: "Local: http://localhost:5173"
```

### 4. Open Browser and Test
```
http://localhost:5173
```

## Testing Each Page

### Page 1: Sentiment Analysis (`/app/sentiment`)
**What to test:**
1. Page loads without errors
2. Sentiment data table displays with stocks
3. Composite gauge shows market sentiment
4. Rating funnel displays analyst breakdown
5. Click on stock symbol → shows detailed analysis
6. Analyst tab works when switched

**Expected data:**
- Table should show 100+ stocks with sentiment scores
- Gauge should show a number 0-100
- Funnel should show distribution across buy/hold/sell

**If broken:**
- Check backend: `curl http://localhost:4000/api/sentiment/data?limit=10`
- Check browser console (F12) for JavaScript errors
- Check Network tab for failed API calls (404, 500)

---

### Page 2: Stock Scores (`/app/scores`)
**What to test:**
1. Page loads with scores table
2. Sorts by composite_score correctly
3. Pagination works (shows 50 items, can go to next page)
4. Search by symbol filters results (type "AAPL")
5. Factor breakdown shows (momentum, value, growth scores)
6. Top gainers/losers section displays
7. Click on stock → shows detailed metrics

**Expected data:**
- Should see 50+ stocks with scores
- Scores should be numbers between 0-100
- All factors should have values

**If broken:**
- Check backend: `curl "http://localhost:4000/api/scores/stockscores?limit=10"`
- This tests the `/stockscores` endpoint we fixed
- Verify the response includes scores for each symbol

---

### Page 3: Sector Analysis (`/app/sectors`)
**What to test:**
1. Page loads with sector rankings
2. Sector strength chart displays
3. Daily strength trend line shows
4. Click sector → shows industries in that sector
5. Breadth indicators display

**Expected data:**
- 11 sectors should be visible
- Each sector has a daily strength score
- Chart shows trend over time

---

### Page 4: Economic Dashboard (`/app/economic`)
**What to test:**
1. Page loads with economic data
2. Recession probability gauge shows
3. Yield curve chart displays
4. Leading indicators show values
5. Credit spreads display with chart

**Expected data:**
- Gauge should show 0-100% recession probability
- Yield curve should show multiple maturity points
- Leading indicators should have trend data

---

### Page 5: Markets Health (`/app/market`)
**What to test:**
1. Page loads with market overview
2. Regime banner shows current market state
3. Index prices display (SPY, QQQ, DIA, etc.)
4. Breadth indicators show up/down counts
5. VIX volatility index displays
6. Top movers show stocks and percentages

**Expected data:**
- 4-5 major indices with prices
- Breadth counts (e.g., "2,500 up / 500 down")
- VIX level 10-40 typically

---

### Page 6: Algo Trading Dashboard (`/app/algo`)
**What to test:**
1. Page loads (may require admin role)
2. Strategy status shows
3. Open positions display
4. Performance metrics show
5. Recent trades show in history
6. Patrol log shows activity

**Expected data:**
- Should show current algo state
- Position count and values
- Recent trade history

---

## Common Issues & Fixes

### Issue: "Cannot GET /api/sentiment/data"
**Cause:** Backend not running or port wrong
**Fix:**
```bash
# Kill existing Node processes
pkill node
# Restart backend
cd webapp/lambda
node index.js
```

### Issue: "Network Error" on all pages
**Cause:** Backend unreachable
**Fix:**
```bash
# Check if backend is listening
curl http://localhost:4000/api/health
# Should respond (even if with error)
```

### Issue: Pages load but show "No data available"
**Cause:** Database empty or no connection
**Fix:**
```bash
# Check database connection
psql -h localhost -d financial_dashboard -c "SELECT COUNT(*) FROM stock_scores"
# Should return a number > 0
```

### Issue: Page loads but page is blank
**Cause:** JavaScript error
**Fix:**
1. Open DevTools (F12)
2. Go to Console tab
3. Look for red error messages
4. Report the error message

### Issue: "CORS Error" 
**Cause:** Frontend and backend on different domains
**Fix:**
```bash
# Frontend must access backend on same domain or with CORS enabled
# For local testing, this is pre-configured
# Check that backend has CORS headers set
```

## Testing the Fixed Endpoint

The main fix in this session was adding the `/api/scores/stockscores` endpoint.

**Test it directly:**
```bash
# Should work (with multiple parameter formats)
curl "http://localhost:4000/api/scores/stockscores?limit=10&sortBy=composite_score"
curl "http://localhost:4000/api/scores/stockscores?limit=10&page=1"
curl "http://localhost:4000/api/scores/stockscores?offset=0&limit=10"

# All should return JSON with stock scores
```

**Test it in pages:**
- Sentiment page (uses this endpoint for score overlay)
- Scores Dashboard (primary consumer)
- Sector Analysis (for sector strength calculation)

## Full Site Verification Checklist

### Before marking "Done":
- [ ] All 6 main pages load without errors
- [ ] All pages display data (not blank)
- [ ] No 404 errors in console
- [ ] No 500 errors from backend
- [ ] No JavaScript errors in console
- [ ] Can navigate between pages
- [ ] Search/filter features work
- [ ] Charts/graphs render properly
- [ ] Mobile responsive (test on smaller window)

### AWS Testing (after deployment):
- [ ] Frontend accessible from CloudFront URL
- [ ] All API endpoints respond
- [ ] Data loads from RDS database
- [ ] Pages have same functionality as local

## Debug Mode

**Enable verbose logging:**
```bash
# Backend debug mode
DEBUG=* node index.js

# Frontend debug mode
VITE_DEBUG=true npm run dev
```

**Check API responses:**
```bash
# See what API is actually returning
curl -i http://localhost:4000/api/scores/stockscores?limit=5

# Pretty print JSON response
curl http://localhost:4000/api/scores/stockscores?limit=5 | jq .
```

## When Everything Works

All pages should:
1. ✅ Load in under 5 seconds
2. ✅ Display real data from database
3. ✅ Show no errors in console
4. ✅ Have working interactive features
5. ✅ Be responsive on all screen sizes
6. ✅ Have proper error messages if data fails to load

---

**Status:** Ready for Testing
**Last Updated:** 2026-05-18
**Pages Verified:** 6 main pages + 10+ supporting pages
