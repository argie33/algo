# Work Plan: Platform Completion & Production Readiness

**Last Updated:** 2026-05-15  
**Scope:** Fix identified issues, complete data pipeline, ensure calculations correct, make system production-ready

---

## PHASE 1: IMMEDIATE FIXES (Done ✅)

**Time Estimate:** 5 minutes

- [x] Fix key_metrics API query bug (WHERE km.ticker)
- [x] Fix credential_manager duplicate call in algo_market_exposure.py

**Status:** COMPLETE

---

## PHASE 2: VERIFY DATA POPULATION (Investigation)

**Time Estimate:** 1-2 hours

Choose **A**, **B**, or **C** based on how deep we go:

### A. Light Verification (30 min) - Just check what's missing
Run quick queries to verify these tables have data:
- [ ] economic_calendar - Should have upcoming economic events
- [ ] key_metrics - **Confirmed EMPTY** - No loader found
- [ ] annual_income_statement, quarterly_income_statement
- [ ] annual_balance_sheet, quarterly_balance_sheet  
- [ ] annual_cash_flow, quarterly_cash_flow
- [ ] analyst_upgrade_downgrade
- [ ] analyst_sentiment_analysis
- [ ] value_metrics, quality_metrics, growth_metrics

**Output:** List of "missing" vs "populated" tables

### B. Full Data Audit (1.5 hours) - Check data quality
Same as A, plus:
- [ ] Run sample queries from each page
- [ ] Check for NULL-heavy columns
- [ ] Verify date ranges are recent (not stale)
- [ ] Check row counts make sense
- [ ] Verify calculations are correct (PE ratio = market_cap / net_income)

**Output:** Detailed data quality report with row counts, date ranges, null %

### C. With Loader Fixes (2+ hours) - Fix any broken loaders
Same as B, plus:
- [ ] Fix any broken loader code
- [ ] Add missing loaders (e.g., key_metrics)
- [ ] Manually populate stale data if needed

**Output:** All tables populated, all loaders working

---

## PHASE 3: FIX API RESPONSE FORMATS (Design & Implementation)

**Time Estimate:** 2-3 hours

**Problem:** Different endpoints return different shapes. Frontend has to handle multiple formats.

**Current Status:**
- Economic endpoints return flat arrays (not hierarchical)
- EconomicDashboard frontend expects: `{indicators: [...], yieldData: {...}}`
- Likely mismatch causing display issues

**Tasks:**
- [ ] Check what EconomicDashboard receives vs expects
- [ ] Fix `/api/economic/leading-indicators` response format
- [ ] Fix `/api/economic/yield-curve-full` response format
- [ ] Test EconomicDashboard page loads and displays correctly

**Output:** EconomicDashboard working with correct data

---

## PHASE 4: VERIFY ALL FRONTEND PAGES (Testing & Fixes)

**Time Estimate:** 2-4 hours

### Pages to Test (in order):
1. **AlgoTradingDashboard** - Main page, should work if algo data exists
2. **ScoresDashboard** - Stock scores, should work
3. **MarketsHealth** - Market health data, should work
4. **EconomicDashboard** - After phase 3 fix
5. **StockDetail** - **HIGH RISK** - needs key_metrics + financial statements
6. **DeepValueStocks** - **HIGH RISK** - needs value_metrics, quality_metrics, growth_metrics
7. **SectorAnalysis** - Risk assessment
8. **Sentiment** - Check if analyst/social data loads
9. **CommoditiesAnalysis** - Check if commodity tables populated
10. **BacktestResults** - Check if results data exists
11. **TradingSignals** - Check signal data
12. **PortfolioDashboard** - Check positions data

**For each page:**
- [ ] Load page, check for console errors
- [ ] Verify data displays (not spinner loops)
- [ ] Check calculations look correct
- [ ] Spot-check a few numbers

**Output:** List of pages with issues + fixes needed

---

## PHASE 5: VERIFY ALGO CALCULATIONS (Code Review & Testing)

**Time Estimate:** 2-4 hours

### Calculations to verify:
1. **Market Exposure** (algo_market_exposure.py)
   - [ ] 11-factor composite calculation
   - [ ] Weights sum to 100
   - [ ] Hard vetoes work correctly
   - [ ] Results in 0-100 range
   - [ ] Test: Run for 3 dates, verify numbers are reasonable

2. **Stock Scores** (algo_signals.py, algo_scoring.py)
   - [ ] Composite score calculation
   - [ ] Value score calculation
   - [ ] Factor weights correct
   - [ ] Test: Pick 5 stocks, manually verify score math

3. **VaR Calculation** (algo_portfolio_risk.py or similar)
   - [ ] Formula correct
   - [ ] Input data valid
   - [ ] Output in expected range

4. **Position Sizing** (algo_position_sizer.py)
   - [ ] Account balance calculation
   - [ ] Risk per trade calculation
   - [ ] Position size calculation

**Output:** Verified calculations, list of any formula issues

---

## PHASE 6: PERFORMANCE & SECURITY REVIEW (Optional)

**Time Estimate:** 2-3 hours

### Security Review:
- [ ] Check for SQL injection vulnerabilities (parameterized queries)
- [ ] Check for XSS vulnerabilities in frontend
- [ ] Verify Cognito disabled correctly (API is public)
- [ ] Check for credential leaks in logs
- [ ] Verify password in .env files not committed

### Performance Review:
- [ ] Database query times acceptable (<500ms)
- [ ] API response times (<1s for most endpoints)
- [ ] Frontend page loads reasonable (<3s)
- [ ] Lambda cold start impact acceptable
- [ ] No N+1 queries

**Output:** Security & performance checklist

---

## PHASE 7: DOCUMENTATION & DEPLOYMENT

**Time Estimate:** 1-2 hours

- [ ] Update STATUS.md with all findings
- [ ] Document any known limitations
- [ ] Verify GitHub Actions CI passing
- [ ] Test end-to-end deployment
- [ ] Update DEPLOYMENT_GUIDE.md if needed

---

## DECISION POINTS

**Question 1: How deep should we go?**
- Option A: Quick verification (Phase 2-A) - 30 min
- Option B: Full audit (Phase 2-B) - 1.5 hours
- Option C: Audit + fixes (Phase 2-C) - 2+ hours

**Question 2: Which frontend pages are critical?**
- Just ensure main pages work (Dashboard, Scores, Markets)
- Or test all 11 pages thoroughly

**Question 3: Should we fix missing data loaders?**
- No - disable features if data missing
- Yes - add loaders as needed

**Question 4: Timeline - how much time to invest?**
- Quick pass: 2-3 hours (phases 1-2-A)
- Thorough: 6-8 hours (phases 1-5)
- Complete: 10-12 hours (all phases)

---

## SUCCESS CRITERIA

Platform is "production-ready" when:

- [x] CI passing (GitHub Actions)
- [ ] All 11+ frontend pages load without errors
- [ ] Data displays correctly on each page (not NULLs or old dates)
- [ ] Key calculations verified correct
- [ ] No obvious bugs found
- [ ] System handles edge cases gracefully (invalid symbols, no data, etc.)
- [ ] Performance acceptable (<1s API, <3s page load)
- [ ] Security review passed

---

## CURRENT BLOCKER STATUS

**Unblocked:** All code fixes ready to deploy
**Blocked:** Need to know:
1. Which verification level (A/B/C)?
2. Which frontend pages are critical?
3. How much time to spend?
