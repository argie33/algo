# Issue 5.2: Frontend Browser Testing Checklist

**Status:** Ready for Manual Testing  
**Required:** Start dev server, open in browser, test each page

## Quick Start

```bash
# Terminal 1: Start dev server
cd webapp/frontend
npm run dev

# Terminal 2: Open browser
# Navigate to: http://localhost:5173 (or port shown in terminal)
```

---

## Core Pages (Must Test - Data Flows)

### 1. Dashboard (Home)
- [ ] Page loads without errors
- [ ] Market health card displays current data
- [ ] S&P 500 chart shows price movement
- [ ] Top movers table (gainers/losers) populated with real data
- [ ] Click "View All" navigates to Stocks page
- **Expected:** Shows current market status, red/green indicators match direction

### 2. Stocks (Screener)
- [ ] Page loads without 404 errors
- [ ] Stock table displays full list of symbols with data
- [ ] Search box filters symbols correctly
- [ ] Sort by columns (price, change%, volume) works
- [ ] Click stock symbol → Stock Detail page opens
- [ ] Pagination works if > 100 symbols
- **Expected:** Shows ~10,000 stock symbols from database

### 3. Stock Detail (e.g., AAPL)
- [ ] Page loads with correct symbol in URL
- [ ] Basic info card: Price, Change%, Volume
- [ ] Price chart displays historical daily prices
- [ ] Buy/Sell signals section shows latest signals
- [ ] No crashes when clicking different stocks
- **Expected:** Shows stock data joined with price_daily table

### 4. Sectors
- [ ] Page loads without errors
- [ ] Sector performance table displays all sectors
- [ ] Column sort works (Name, Change%, 1Y Return)
- [ ] Click sector → Sector Detail page opens
- [ ] Heatmap or chart shows sector rotation data
- **Expected:** 11-15 sectors with performance metrics

### 5. Market Health
- [ ] Page loads without errors
- [ ] Market status indicators visible (Bullish/Bearish/Neutral)
- [ ] VIX display shows current value + historical chart
- [ ] NYSE/NASDAQ breadth data displayed (Advance/Decline ratio)
- [ ] Economic calendar shows latest data
- **Expected:** Real-time market health metrics

### 6. Signals (Trading Signals)
- [ ] Page loads without errors
- [ ] Signal table shows buy/sell signals for stocks/ETFs
- [ ] Filter by signal type (Buy/Sell/Neutral) works
- [ ] Sort by date, confidence, symbol works
- [ ] Timestamp shows recent signals (today/yesterday)
- **Expected:** 300+ daily buy/sell signals

### 7. Portfolio
- [ ] Page loads without errors
- [ ] Portfolio summary card: Total Value, Gain/Loss, Return %
- [ ] Open positions table shows current holdings
- [ ] Click position → Position Detail page opens
- [ ] Closed trades history displays past trades
- **Expected:** Real-time position data from algo_positions table

### 8. Performance (Algo Performance)
- [ ] Page loads without errors
- [ ] Summary metrics display: Win Rate, Profit Factor, Sharpe
- [ ] Equity curve chart shows cumulative P&L over time
- [ ] Monthly returns calendar/table visible
- [ ] Trade list shows recent closed trades
- **Expected:** Real trading performance metrics

---

## Sentiment & Technical Pages (Data Quality Check)

### 9. Fear & Greed Index
- [ ] Page loads without errors
- [ ] Current F&G score displays (0-100 scale)
- [ ] Historical chart shows recent trend
- [ ] Labels ("Extreme Fear" to "Extreme Greed") correct for score
- **Expected:** 250 data points from CNN Fear & Greed API

### 10. Sentiment Analysis
- [ ] Page loads without errors
- [ ] Sentiment chart displays stock sentiment scores
- [ ] Analyst ratings (Buy/Hold/Sell) show distribution
- [ ] Sentiment correlation with price movement visible
- **Expected:** Analyst sentiment data joined with price data

### 11. Economic Calendar
- [ ] Page loads without errors
- [ ] Calendar shows major economic releases
- [ ] Date filter works (select date range)
- [ ] Actual vs Forecast vs Previous values displayed
- **Expected:** Fed rates, employment, CPI, GDP releases

### 12. Market Trends
- [ ] Page loads without errors
- [ ] Sector trends sparklines display (7-day change)
- [ ] Industry heatmap shows relative strength
- [ ] Top movers within sector displayed
- **Expected:** Real-time sector rotation data

---

## Navigation & UI (Page Structure Check)

### 13. Navigation Menu
- [ ] All menu items present and clickable
- [ ] Active page highlighted
- [ ] Logo click returns to Dashboard
- [ ] Menu responsive on mobile (hamburger menu)

### 14. Layout
- [ ] Header consistent across all pages
- [ ] Sidebar/navigation visible and functional
- [ ] Footer displays copyright, links
- [ ] Page doesn't have layout shifts or broken styling

### 15. Responsive Design
- [ ] Desktop (1920px) → content displays properly
- [ ] Tablet (768px) → layout adapts
- [ ] Mobile (375px) → hamburger menu works
- [ ] Tables scroll horizontally on small screens

---

## Error Handling & Edge Cases

### 16. Error States
- [ ] 404 page displays for invalid route
- [ ] Loading spinner shows while fetching data
- [ ] Error message displays if API fails
- [ ] No "undefined" or "[object Object]" text visible

### 17. Empty States
- [ ] If no data: "No data available" message shows
- [ ] Search with no results shows "No results found"
- [ ] Graceful handling of null/missing values

### 18. Performance
- [ ] Dashboard loads in < 3 seconds
- [ ] Stock list loads in < 5 seconds
- [ ] Charts render smoothly without lag
- [ ] Clicking between pages is responsive (< 1 second)

---

## Known Fixed Pages (Re-verify)

### 19. Sentiment Page (Previously Broken)
- [ ] Loads without 500 error
- [ ] Analyst sentiment table displays data
- [ ] No "Cannot read property" errors in console
- **Expected:** analyst_sentiment_analysis table now exists

### 20. Signals Page (Previously Broken)
- [ ] Loads without 500 error
- [ ] Buy/Sell signal table populated
- [ ] Sparklines display signal history
- **Expected:** buy_sell_daily table joins correctly

### 21. Fear & Greed Page
- [ ] Loads without 500 error
- [ ] F&G index displays (1-100 scale)
- [ ] Chart shows historical trend
- **Expected:** fear_greed_index table populated by loader

---

## Test Execution Guide

### Quick Test (15 min)
1. Load Dashboard → Verify market data displays
2. Load Stocks → Verify table has data
3. Load Signals → Verify signals display
4. Load Portfolio → Verify positions display
5. Load Performance → Verify metrics display

**Pass Criteria:** All 5 pages load without errors, data displays

### Full Test (45 min)
1. Visit all 21 pages listed above
2. For each page: Check console for JavaScript errors (F12)
3. Click around, change filters, click links
4. Verify data freshness (timestamps make sense)
5. Check network tab for failed requests (404, 500)

**Pass Criteria:** All pages load, no errors, data realistic

### Regression Test (30 min)
1. Test previously broken pages (19-21)
2. Test navigation between all pages
3. Test search/filter functionality
4. Verify responsive design on mobile

---

## Debugging Tips

If a page fails:

1. **Check Console (F12 → Console)**
   - Look for JavaScript errors (red text)
   - Common: "Cannot read property X of undefined"
   - Note error message + URL

2. **Check Network Tab (F12 → Network)**
   - Click the page, then look at Network tab
   - Look for red requests (404, 500)
   - Click request → Response tab → see actual error

3. **Check if API is Running**
   - Open browser console: `fetch('/api/health').then(r => r.json()).then(console.log)`
   - Should return `{status: "healthy"}`

4. **Check Local Environment**
   - Is `npm run dev` still running?
   - Did you run `python3 run-all-loaders.py`?
   - Is PostgreSQL running on localhost:5432?

---

## Sign-Off

When all pages pass:

```
✅ Frontend testing complete
- All 21 pages load without errors
- Data displays correctly
- No JavaScript console errors
- Navigation works end-to-end
```

Date: ______  
Tester: ____________________  
Issues Found: ________________________

**READY FOR PRODUCTION DEPLOYMENT**
