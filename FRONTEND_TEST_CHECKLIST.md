# Frontend Browser Testing Checklist

**Phase 2, Issue 5.2: Verify all 22 frontend pages work correctly**

## How to Test
1. Start dev server: `npm run dev` (from `webapp/frontend` directory)
2. Open http://localhost:5173 in browser
3. Navigate to each page and verify:
   - Page loads without errors
   - Data displays (not empty/broken)
   - No 404 errors
   - Charts/tables render properly
   - No console errors (F12 → Console tab)

## Pages to Test (22 Total)

### Authentication
- [ ] **LoginPage.jsx** — Login form loads, no errors

### Main Dashboards
- [ ] **AlgoTradingDashboard.jsx** — Shows portfolio, trades, performance metrics
- [ ] **PortfolioDashboard.jsx** — Portfolio overview, positions, allocations
- [ ] **MetricsDashboard.jsx** — Key metrics and performance indicators
- [ ] **PerformanceMetrics.jsx** — Detailed performance analytics
- [ ] **TradeTracker.jsx** — Trade history and P&L tracking

### Analysis Pages
- [ ] **SectorAnalysis.jsx** — Sector breakdown, rotation, strength
- [ ] **Sentiment.jsx** — Market sentiment indicators, VIX, fear/greed
- [ ] **EconomicDashboard.jsx** — Economic data, yields, inflation
- [ ] **MarketsHealth.jsx** — Market breadth, health indicators
- [ ] **TradingSignals.jsx** — Active trading signals (RSI, MACD, etc)

### Stock/Security Screens
- [ ] **SwingCandidates.jsx** — Swing trading candidates
- [ ] **DeepValueStocks.jsx** — Value stock candidates
- [ ] **StockDetail.jsx** — Individual stock details
- [ ] **ScoresDashboard.jsx** — Swing trader scores by stock

### Backtesting & Analysis
- [ ] **BacktestResults.jsx** — Historical backtest results
- [ ] **PreTradeSimulator.jsx** — Simulate trade scenarios

### System & Admin
- [ ] **ServiceHealth.jsx** — API health, database status
- [ ] **NotificationCenter.jsx** — System notifications, alerts
- [ ] **AuditViewer.jsx** — Audit log viewer
- [ ] **Settings.jsx** — User settings and preferences

### Error Handling
- [ ] **NotFound.jsx** — 404 page (navigate to non-existent route)

---

## Expected Results

| Category | Pass Criteria |
|----------|---------------|
| **Load** | Page appears within 2 seconds, no 503/500 errors |
| **Data** | Relevant data displays (not empty/null) |
| **UI** | Charts/tables render, no layout breaks |
| **Errors** | No 404 errors, no console red errors |
| **Navigation** | Links to other pages work |

---

## Known Issues to Watch For

⚠️ **Pages Previously Broken (now should be fixed):**
- **Sentiment.jsx** — Was showing no data, should now display fear/greed index + VIX
- **TradingSignals.jsx** — Was showing empty signals, should now display active RSI/MACD signals
- **SectorAnalysis.jsx** — Was showing no sector data, should now show rotation + strength

✅ **Should be working:**
- All 22 pages have database backing
- All API endpoints functional
- No hardcoded mock data (uses real database)

---

## Test Reporting

### Passing Test Example
```
✅ AlgoTradingDashboard.jsx
   - Page loads in 1.5s
   - Portfolio: Shows 5 positions
   - Trades: Shows last 10 trades
   - Chart: 6-month equity curve renders
   - Console: No errors
```

### Failing Test Example
```
❌ Sentiment.jsx
   - Page loads but shows: "Error loading data"
   - Console error: "Cannot read property 'fear_greed_index' of undefined"
   - Action: Check API /api/algo/data-status endpoint
```

---

## When Done

Document results in this format:
- Total pages tested: ___/22
- Pass: ___ ❌ Fail: ___
- Critical failures (blocking): ___
- Minor issues: ___

Push results to STATUS.md when complete.
