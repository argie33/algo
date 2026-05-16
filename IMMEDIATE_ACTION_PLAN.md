# Immediate Action Plan: Platform Production Readiness

**Updated:** 2026-05-15  
**Goal:** Verify platform is production-ready for live trading  
**Timeline:** 3-4 days of focused work

---

## PHASE 1: VERIFICATION (TODAY - 4 hours)

### 1.1 Verify Recent Critical Fixes Deployed (30 min)

**Fixes to verify:**
- ✓ Market exposure INSERT using correct columns (commit a9017bd2b)
- ✓ VaR INSERT using correct columns (commit a9017bd2b)
- ✓ Credential handling in GitHub Actions (5 commits)
- ✓ Cognito disabled (commit b0fc4905c)

**How to verify:**
```bash
# Check GitHub Actions deployment completed
# https://github.com/argie33/algo/actions

# Expected: All jobs passed (green checkmarks)
# - Terraform Apply ✅
# - Build Docker Image ✅
# - Deploy Algo Lambda ✅
# - Deploy API Lambda ✅
# - Deploy Frontend ✅
# - Initialize Database ✅
```

**Action:** If deployment failed, debug and fix before proceeding.

---

### 1.2 Verify All 22 Frontend Pages Have Real Data (1 hour)

**Pages to check:**
1. AlgoTradingDashboard — `/api/algo/*` endpoints
2. BacktestResults — `/api/research/*` endpoints
3. CommoditiesAnalysis — `/api/commodities/*` endpoints
4. DeepValueStocks — `/api/stocks` + `/api/scores/*` endpoints
5. EconomicDashboard — `/api/economic/*` + `/api/market/naaim` endpoints
6. MarketsHealth — `/api/market/*` endpoints
7. MetricsDashboard — `/api/algo/*` + performance endpoints
8. PortfolioDashboard — `/api/algo/positions`, `/api/algo/trades` endpoints
9. ScoresDashboard — `/api/scores/stockscores` endpoints
10. SectorAnalysis — `/api/sectors/*` endpoints
11. Sentiment — `/api/sentiment/*` endpoints
12. SignalIntelligence — `/api/signals/*` endpoints
13. StockDetail — `/api/stocks/{symbol}`, `/api/prices/*` endpoints
14. SwingCandidates — `/api/algo/swing-scores` endpoints
15. TradingSignals — `/api/signals/*` endpoints
... (7 more pages)

**Verification method:**
```bash
# For each page:
# 1. Open in browser: https://d5j1h4wzrkvw7.cloudfront.net
# 2. Check browser console (F12) for errors
# 3. Verify data loads (not hardcoded/mock)
# 4. Check API network tab for real data

# Example: ScoresDashboard should call:
# /api/scores/stockscores?limit=5000
# Response should have real stock scores from DB, not mock values
```

**Checklist:**
- [ ] All pages load without 404 errors
- [ ] No hardcoded or mock data visible
- [ ] All API calls return real data from database
- [ ] Performance acceptable (< 2s load time)

---

### 1.3 Spot-Check 5 Key Calculations (1 hour)

**Calculations to verify:**

1. **Minervini 8-Point Trend Template**
   - Check: algo_signals.py → _compute_minervini_score()
   - Verify: Score is 0-8, reflects actual price action
   - Test stock: AAPL (known good example)

2. **Swing Trader Score**
   - Check: algo_swing_score.py → SwingTraderScore.compute()
   - Verify: Uses correct weighted components (25/20/20/12/10/8/5)
   - Verify: Hard-fail gates are enforced
   - Test with database sample

3. **Market Exposure 11-Factor**
   - Check: algo_market_exposure.py → MarketExposure.compute()
   - Verify: Correctly sums to 100 points
   - Verify: Correctly persists to market_exposure_daily (FIXED in a9017bd2b)
   - Query database: SELECT * FROM market_exposure_daily WHERE date = TODAY ORDER BY created_at DESC LIMIT 1

4. **Value at Risk (VaR) Calculation**
   - Check: algo_var.py → compute()
   - Verify: Correctly calculates 95% VaR
   - Verify: Correctly persists to algo_var (FIXED in a9017bd2b)
   - Query database: SELECT * FROM algo_var WHERE date = TODAY ORDER BY created_at DESC LIMIT 1

5. **TD Sequential 9-Count**
   - Check: algo_signals.py → _td_sequential_9count()
   - Verify: Count reaches 9 on actual setup
   - Test with known example (chart pattern)

**Action:** Run spot checks, document any errors

---

### 1.4 Verify Data Loader Freshness (30 min)

**Key question:** Are loaders actually running and are we getting fresh data?

```bash
# Check which loaders are scheduled to run
grep -r "EventBridge\|cron\|schedule" terraform/modules/pipeline/

# Check data freshness in key tables
psql -h <RDS-ENDPOINT> -U stocks -d stocks -c "
  SELECT 
    'price_daily' AS table_name,
    MAX(date) AS latest_date,
    COUNT(*) AS row_count
  FROM price_daily
  UNION ALL
  SELECT 'technical_data_daily', MAX(date), COUNT(*)
  FROM technical_data_daily
  UNION ALL
  SELECT 'market_exposure_daily', MAX(date), COUNT(*)
  FROM market_exposure_daily
  UNION ALL
  SELECT 'algo_var', MAX(date), COUNT(*)
  FROM algo_var;"

# Expected: All MAX(date) should be TODAY or YESTERDAY
```

**Checklist:**
- [ ] price_daily has today's data (or yesterday if after hours)
- [ ] market_exposure_daily has today's data
- [ ] algo_var has today's data
- [ ] No gaps > 2 days in any critical table

---

## PHASE 2: BUG FIXES (TOMORROW - 4 hours)

### Issues Found in Phase 1

**If any checks fail above:**

1. **Broken API endpoint?**
   - [ ] Check lambda/api/lambda_function.py
   - [ ] Verify endpoint handler exists
   - [ ] Check database query for errors
   - [ ] Test endpoint manually with curl
   - [ ] Fix and commit

2. **Data not persisting?**
   - [ ] Check INSERT statements in calculation modules
   - [ ] Verify column names match schema
   - [ ] Check for silent failures (duplicate key errors, etc.)
   - [ ] Fix and commit

3. **Stale data in tables?**
   - [ ] Check which loaders are failing
   - [ ] Check EventBridge logs in CloudWatch
   - [ ] Check Lambda function logs for errors
   - [ ] Fix loader and redeploy

4. **Calculation error?**
   - [ ] Review formula against documented standard
   - [ ] Check inputs are correct
   - [ ] Check for NULL handling
   - [ ] Add unit tests if missing
   - [ ] Fix and commit

---

## PHASE 3: IMPROVEMENTS (THIS WEEK - 8 hours)

### High-Impact Improvements (Do in order)

#### 3.1 Add Performance Metrics (2 hours)
**Impact:** Critical for monitoring algo performance

**What to add:**
- Sharpe ratio calculation
- Sortino ratio calculation  
- Maximum drawdown tracking
- Win/loss ratio
- Profit factor

**Where:** 
- Backend: algo_performance.py (add calculation functions)
- Database: performance_metrics table (if not exists)
- API: /api/algo/performance endpoint (add new fields)
- Frontend: PerformanceMetrics.jsx (add charts)

**Priority:** HIGH

#### 3.2 Verify Data Loader Coverage (1.5 hours)
**Impact:** Prevents "missing stock" surprises

**Check:**
- How many stocks get loaded each day?
- Which stocks are missing?
- Are all S&P 500 stocks covered?
- Are all ETFs covered?

**Action:** Document findings, fix gaps

**Priority:** MEDIUM

#### 3.3 Fix Any Silent Failures (2 hours)
**Impact:** Ensures all decisions based on complete data

**Check for:**
- NULL values in critical columns
- Mismatched data types
- Missing or stale data
- Schema version mismatches

**Action:** Fix any issues found

**Priority:** HIGH

#### 3.4 Optimize Slow Queries (2.5 hours)
**Impact:** Faster dashboard loads, better UX

**Process:**
- Identify slow queries (> 500ms)
- Add missing indexes
- Optimize WHERE clauses
- Consider caching strategy

**Priority:** MEDIUM

---

## SUCCESS CRITERIA

Phase 1 Complete When:
- [ ] GitHub Actions deployment verified successful
- [ ] All 22 pages load with real data (no hardcoded/mock)
- [ ] 5 key calculations verified correct
- [ ] Data loader freshness confirmed
- [ ] No critical errors found

Phase 2 Complete When:
- [ ] All issues from Phase 1 are fixed
- [ ] All tests passing
- [ ] All commits pushed to main
- [ ] GitHub Actions deployment completed

Phase 3 Complete When:
- [ ] Performance metrics added
- [ ] Data loader coverage verified
- [ ] No silent failures remaining
- [ ] Slow queries optimized
- [ ] System ready for live trading

---

## RISK MITIGATION

**If major issues found:**
1. **Data integrity broken:** Restore from last known good backup, replay loaders
2. **Calculation error:** Implement unit tests, verify against external source
3. **Missing data:** Implement data freshness checks before trade execution
4. **Performance issue:** Implement query timeouts, add caching, reduce data volume

---

## DOCUMENTATION

As work is completed:
1. Update STATUS.md with findings
2. Document any fixes in commit messages
3. Update CLAUDE.md if patterns emerge
4. Save learnings to memory/ directory

---

## TIMELINE

| Phase | Duration | Start | End | Status |
|-------|----------|-------|-----|--------|
| Phase 1 (Verification) | 4 hours | TODAY | TODAY | 🔄 IN PROGRESS |
| Phase 2 (Bug Fixes) | 4 hours | TOMORROW | TOMORROW | ⏳ PENDING |
| Phase 3 (Improvements) | 8 hours | THIS WEEK | THIS WEEK | ⏳ PENDING |

**Total:** 16 hours focused work over 3-4 days

---

## RESOURCES

- **Live system:** https://d5j1h4wzrkvw7.cloudfront.net
- **API:** https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com
- **Database:** algo-db (RDS endpoint in AWS Console)
- **Logs:** CloudWatch → /aws/lambda/algo-orchestrator, /aws/ecs/data-loaders
- **GitHub:** https://github.com/argie33/algo/actions
- **Code:** C:\Users\arger\code\algo
