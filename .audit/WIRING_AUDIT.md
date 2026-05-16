# COMPREHENSIVE SYSTEM WIRING AUDIT

**Date:** 2026-05-16  
**Database Status:** 17/118 tables populated, 101 tables empty

## CRITICAL FINDINGS

### Tier 1: BLOCKING ALGO EXECUTION (Must Fix First)

#### Issue 1: Orchestrator Trade Tracking Disabled
**Tables:** algo_trades, algo_positions, algo_portfolio_snapshots, algo_audit_log (ALL EMPTY)

**Endpoints that fail:**
- `/api/algo/trades` → returns 0 rows (table empty)
- `/api/algo/positions` → returns 0 rows (table empty)
- `/api/algo/performance` → returns 0 rows (table empty)
- `/api/algo/equity-curve` → returns 0 rows (table empty)

**Frontend pages affected:**
- AlgoTradingDashboard (positions widget shows nothing)
- TradeTracker (entire page empty)
- PerformanceMetrics (no equity curve, no audit log)

**Root Cause:** Orchestrator code is not wired to write trades/positions. Need to check:
- algo_orchestrator.py TradeExecutor.execute_trade() — does it INSERT to algo_trades?
- PositionMonitor.track() — does it INSERT to algo_positions?

**Fix Required:** Wire orchestrator to populate these 4 tables.

---

#### Issue 2: Economic Data Missing (Blocks Circuit Breaker)
**Table:** economic_data (EMPTY)

**Endpoints affected:**
- `/api/economic/*` endpoints
- `/api/algo/circuit-breakers` (checks economic_data for yield curve)

**Frontend pages affected:**
- EconomicDashboard (entirely empty)
- AlgoTradingDashboard circuit-breaker widget (empty)

**Root Cause:** loadecondata.py requires FRED_API_KEY env var. If not set, loader doesn't run.

**Fix Required:** Add FRED_API_KEY to .env.local or implement fallback for circuit breaker.

---

### Tier 2: BLOCKING TRADING SIGNALS (Critical)

#### Issue 3: Technical Analysis Missing
**Table:** technical_data_daily (EMPTY — blocks 9 endpoints)

**Endpoints affected:**
- `/api/signals/stocks` (JOINs to technical_data_daily, returns NULL values)
- TradingSignals page relies on RSI, MACD, ATR from this table
- StockDetail page shows no technical indicators

**Frontend pages affected:**
- TradingSignals (shows signals but no technical context)
- StockDetail (no technical indicators tab)
- TechnicalAnalysis (entirely empty)
- SignalIntelligence (missing indicators)

**Root Cause:** loadtechnicalsdaily.py computes technical indicators in SQL. Need to verify:
- Does it handle all symbols?
- Does it run after price_daily loads?

**Fix Required:** Verify technical loader runs successfully and populates table.

---

#### Issue 4: Swing Trader Scores Missing
**Table:** swing_trader_scores (EMPTY — used by 5+ endpoints)

**Endpoints affected:**
- `/api/algo/swing-scores` → returns 0 rows
- `/api/algo/rejection-funnel` (LEFT JOIN to swing_trader_scores returns NULL)
- `/api/signals/stocks` (LEFT JOIN returns NULL)

**Frontend pages affected:**
- AlgoTradingDashboard swing-scores widget (empty)
- SwingCandidates (no scores, can't filter)
- SignalIntelligence (no swing context)

**Root Cause:** No loader populates this table. Needs investigation.

**Fix Required:** Check if loader exists or needs to be created.

---

### Tier 3: BLOCKING STOCK ANALYSIS (High Priority)

#### Issue 5: Company Profile Incomplete
**Table:** company_profile (38 rows — but should have 38 symbols with full data)

**Endpoints affected:**
- `/api/stocks/filters` (needs sector, industry for filtering)
- `/api/sectors` (needs company_profile for sector breakdown)
- `/api/industries` (needs company_profile for industry breakdown)

**Frontend pages affected:**
- StockDetail (shows partial company info)
- PortfolioDashboard (can't group by sector)
- SectorAnalysis (can't show stocks by sector)
- IndustryAnalysis (can't show stocks by industry)

**Status:** Table has 38 rows but may be incomplete. Check what data is missing.

**Fix Required:** Verify company_profile has all required columns populated (sector, industry, market_cap, PE, etc.).

---

#### Issue 6: Quarterly Financial Data Missing
**Tables:** quarterly_income_statement (0), quarterly_balance_sheet (0), quarterly_cash_flow (0)

**Endpoints affected:**
- `/api/financials/quarterly` → returns empty
- Financial pages show only annual data, not quarterly

**Frontend pages affected:**
- FinancialData (quarterly tab empty)
- FinancialMetrics (quarterly analysis missing)
- StockDetail (quarterly financials missing)

**Root Cause:** These loaders may exist but don't populate. Annual data loads (591 rows in annual_income_statement).

**Fix Required:** Verify quarterly loaders exist and run correctly.

---

#### Issue 7: Earnings Data Missing
**Tables:** earnings_history (0), earnings_estimates (0), earnings_estimate_revisions (0)

**Endpoints affected:**
- `/api/earnings/*` → returns 0 rows
- EarningsCalendar endpoint not implemented

**Frontend pages affected:**
- StockDetail earnings tab (empty)
- EarningsCalendar page (entirely empty)

**Root Cause:** loadearningshistory.py, loadearningsestimates.py may not run or fail silently.

**Fix Required:** Debug earnings loaders.

---

#### Issue 8: Metrics Tables Missing
**Tables:** 
- quality_metrics (0 rows)
- growth_metrics (0 rows)
- value_metrics (0 rows)
- momentum_metrics (0 rows)
- stability_metrics (0 rows)
- technical_data_daily/weekly/monthly (all 0)

**Endpoints affected:**
- `/api/stocks/filters` (uses all metrics for scoring)
- Advanced filter logic in AdvancedFilters.score_trade() returns 0 for all scores

**Frontend pages affected:**
- SwingCandidates (filters show 0 scores)
- DeepValueStocks (value filter returns no data)
- MetricsDashboard (all empty)
- All filter-based pages

**Root Cause:** No loaders populate these tables. May need to be created.

**Fix Required:** Identify which loaders should populate these and create if missing.

---

### Tier 4: BLOCKING SECTOR/MARKET ANALYSIS

#### Issue 9: Sector Performance Missing
**Tables:** sector_performance (0), sector_ranking (0), sector_rotation_signal (0)

**Endpoints affected:**
- `/api/sectors` → returns 0 rows
- `/api/algo/sector-rotation` → returns 0 rows

**Frontend pages affected:**
- SectorAnalysis (entirely empty)
- PortfolioDashboard sector breakdown (empty)

**Root Cause:** loadsectors.py may not populate correctly.

**Fix Required:** Debug sector loader.

---

#### Issue 10: Industry Performance Missing
**Tables:** industry_performance (0), industry_ranking (0)

**Endpoints affected:**
- `/api/industries` → returns 0 rows

**Frontend pages affected:**
- IndustryAnalysis (entirely empty)
- PortfolioDashboard industry breakdown (empty)

**Root Cause:** No loader populates industry tables.

**Fix Required:** Create industry loader or debug existing one.

---

## WORKING ENDPOINTS (No Issues)

✅ `/api/health` — OK  
✅ `/api/prices/history/{symbol}` — OK (queries price_daily: 47,391 rows)  
✅ `/api/signals/stocks` — PARTIAL (queries buy_sell_daily: 12,996 rows, but JOINs to empty technical_data_daily)  
✅ `/api/signals/etf` — PARTIAL (queries buy_sell_daily_etf: 72 rows)  
✅ `/api/financials/annual` — OK (queries annual_income_statement: 591 rows)  
✅ `/api/stocks` → list all stocks — OK (queries stock_symbols: 38 rows)  
✅ `/api/stocks/{symbol}` → detail — PARTIAL (basic data OK, missing technical/metrics)  

---

## SUMMARY TABLE

| Component | Status | Priority | Impact |
|-----------|--------|----------|--------|
| Algo trade tracking | BROKEN | P0 | Orchestrator can't record trades |
| Economic data | EMPTY | P0 | Circuit breaker doesn't work |
| Technical indicators | EMPTY | P1 | All signal analysis incomplete |
| Swing scores | EMPTY | P1 | Signal quality scoring broken |
| Company profile | PARTIAL | P1 | Sector/industry filtering broken |
| Quarterly financials | EMPTY | P2 | Financial analysis missing |
| Earnings data | EMPTY | P2 | Earnings calendar broken |
| Metrics tables | EMPTY | P2 | Advanced filtering broken |
| Sector data | EMPTY | P2 | Sector analysis broken |
| Industry data | EMPTY | P2 | Industry analysis broken |

---

## ACTION PLAN

### PHASE 1: Unblock Algo (30 mins)
1. Check algo_orchestrator.py for TradeExecutor.execute_trade() — does it INSERT to algo_trades?
2. Check PositionMonitor for position tracking logic
3. Wire trade/position recording if missing

### PHASE 2: Unblock Signals (1 hour)
1. Verify loadtechnicalsdaily.py runs and populates technical_data_daily
2. Create or debug swing_trader_scores loader
3. Test signals endpoints return complete data

### PHASE 3: Unblock Stock Analysis (1.5 hours)
1. Verify company_profile has all required fields
2. Debug quarterly financial loaders
3. Debug earnings loaders
4. Create missing metrics loaders if needed

### PHASE 4: Unblock Market Analysis (1 hour)
1. Debug sector and industry loaders
2. Verify endpoint queries

---

## NEXT STEP

Start with **PHASE 1: Check algo_orchestrator.py** to see if trade/position recording is wired.

