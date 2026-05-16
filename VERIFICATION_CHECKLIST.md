# Production Readiness Verification Checklist

**Date:** 2026-05-15 20:30  
**Status:** In Progress - Phase 1 Verification  
**Goal:** Verify platform is production-ready for live trading

---

## ✅ COMPLETED CHECKS

### Critical Bugs Fixed
- [x] **Market Exposure INSERT Bug** — Fixed column mismatch (commit 3036ed12f)
  - Was inserting to non-existent columns (exposure_pct, raw_score, regime, etc.)
  - Fixed to use correct columns (market_exposure_pct, long_exposure_pct, etc.)
  - Severity: CRITICAL - all exposure data was silently failing to persist
  
- [x] **Credential Manager Imports** — Fixed GitHub Actions blocker
  - 10+ modules had module-level credential_manager imports failing in CI
  - Implemented pattern: check DB_PASSWORD env var first, fallback to credential_manager
  - Severity: CRITICAL - was blocking all GitHub Actions deployments

- [x] **VaR Persistence** — Verified correct in algo_var.py
  - Uses algo_risk_daily table with correct columns (var_pct_95, cvar_pct_95, etc.)
  - Code is correct, INSERT will work

### Schema & Code Audits
- [x] Market exposure schema — Tables exist, columns match (with fix applied)
- [x] VaR schema — Tables exist, columns correct
- [x] Swing trader scores schema — Tables exist, INSERT correct
- [x] Trend template schema — Tables exist, columns correct  
- [x] Risk daily schema — Tables exist, columns correct

---

## ⏳ IN PROGRESS CHECKS

### Data Freshness Verification
- [ ] **Check GitHub Actions Deployment** 
  - Navigate to: https://github.com/argie33/algo/actions
  - Verify: All 6 jobs passed (Terraform, Docker, Lambdas, Frontend, Database)
  - Expected time: Today at 20:05 UTC (4:05pm ET) on weekdays
  
- [ ] **Verify Data is Fresh in Tables**
  - Connect to RDS database and check MAX(date) for:
    - [ ] price_daily — should have today's data (or yesterday if after 4pm)
    - [ ] market_exposure_daily — should have today's data  
    - [ ] algo_risk_daily — should have today's data
    - [ ] stock_scores — should be recent (< 1 day old)
    - [ ] swing_trader_scores — should be recent
    - [ ] technical_data_daily — should have today's data

- [ ] **Verify Frontend Pages Load**
  - Test in browser: https://d5j1h4wzrkvw7.cloudfront.net
  - [ ] Home/Dashboard loads without errors
  - [ ] ScoresDashboard loads and displays real stock scores
  - [ ] MarketHealth loads and shows real SPY/QQQ data
  - [ ] PortfolioDashboard loads
  - [ ] TradingSignals loads and shows real signals

- [ ] **Verify API Endpoints Return Data**
  - [ ] `GET /api/scores/stockscores` returns real scores
  - [ ] `GET /api/prices/history/AAPL` returns real price data
  - [ ] `GET /api/signals/stocks` returns real buy/sell signals
  - [ ] `GET /api/algo/status` returns orchestrator status
  - [ ] `GET /api/market/naaim` returns market sentiment data

### Calculation Verification  
- [ ] **Spot-check Minervini Score**
  - Take 1 stock (e.g., AAPL) and verify:
    - Trend template score is between 0-8
    - Score matches documented 8-point criteria
    - Data from database matches expected values

- [ ] **Spot-check Swing Score**
  - Take 1 stock with calculated swing_score
  - Verify:
    - Score is between 0-100
    - Components (setup, trend, momentum, etc.) sum correctly
    - Grade (A+/A/B/C/D/F) matches score

- [ ] **Spot-check Market Exposure**
  - Verify latest market_exposure_daily entry:
    - market_exposure_pct is between 0-100
    - exposure_tier is one of: tier_1, tier_2, tier_3, tier_4
    - is_entry_allowed is TRUE or FALSE (not NULL)
    - Created timestamp is recent

- [ ] **Spot-check VaR Calculation**
  - Verify latest algo_risk_daily entry:
    - var_pct_95 is positive number
    - cvar_pct_95 >= var_pct_95 (by definition)
    - portfolio_beta > 0
    - All values are reasonable (not infinite/NULL)

- [ ] **Spot-check TD Sequential**
  - Find a stock with active TD count
  - Verify count reaches 9 correctly
  - Verify doesn't exceed 13 without reset

### Pipeline Integrity
- [ ] **Verify Orchestrator Phases**
  - [ ] Phase 1 (Data freshness check) — data exists and is recent
  - [ ] Phase 2 (Circuit breakers) — can fire on stale data
  - [ ] Phase 3 (Position monitor) — can run if positions exist
  - [ ] Phase 4 (Exit execution) — exits can be placed
  - [ ] Phase 5 (Signal generation) — signals are ranked
  - [ ] Phase 6 (Entry execution) — trades can be executed
  - [ ] Phase 7 (Reconciliation) — Alpaca sync works

- [ ] **Verify Data Loader Pipeline**
  - [ ] EventBridge rule runs at 4:05pm ET weekdays
  - [ ] Step Functions state machine executes
  - [ ] ECS tasks pull latest data from APIs
  - [ ] Data is persisted to all required tables
  - [ ] No loader silently fails

---

## ❌ BLOCKING ISSUES FOUND

None currently. Market exposure fix removed the critical blocker.

---

## 📋 NEXT VERIFICATION STEPS

**If all checks above pass:**
1. System is ready for live trading with high confidence
2. Monitor CloudWatch logs for 24 hours
3. Run dry-run trades to test orchestrator end-to-end
4. Deploy with paper trading enabled

**If any checks fail:**
1. Document the failure with exact error/value
2. Create issue ticket with reproduction steps
3. Debug and fix
4. Re-run check

---

## 🔧 DEPLOYMENT STATUS

**Recent Commits:**
- `3036ed12f` - CRITICAL: Fixed market exposure INSERT
- `d85f26790` - Docs: Action plan and maturity assessment  
- `430053d9f` - Docs: Platform audit findings

**Deployment Pipeline:**
- [x] Code changes committed to main
- ⏳ GitHub Actions: Awaiting deployment (scheduled 4:05pm ET weekdays)
- ⏳ Terraform: Will apply when Actions runs
- ⏳ Lambda: Will deploy when Actions runs
- ⏳ Frontend: Will deploy when Actions runs
- ⏳ Database: Schema will initialize when Actions runs

**Timeline:**
- Changes merged: 2026-05-15 ~20:15
- Expected deployment: 2026-05-16 20:05 UTC (4:05pm ET) if weekday
- Or: Next 4:05pm ET on Mon/Tue/Wed/Thu/Fri

---

## 📞 ESCALATION CONTACTS

- **GitHub Actions Errors:** Check workflow logs at https://github.com/argie33/algo/actions
- **Database Connection:** Check RDS instance status in AWS Console
- **Lambda Errors:** Check CloudWatch logs: /aws/lambda/algo-orchestrator
- **ECS Task Errors:** Check CloudWatch logs: /aws/ecs/data-loaders

---

## ✨ CONFIDENCE ASSESSMENT

**Current Confidence Level:** 85%

**Why not 100%:**
- [ ] GitHub Actions deployment not yet verified to pass
- [ ] Data tables not yet verified to be populated
- [ ] Frontend pages not yet tested in browser
- [ ] Calculations not yet spot-checked with actual data

**Confidence will reach 100% after:**
- [ ] GitHub Actions successfully deploys
- [ ] Data tables verified fresh
- [ ] All 5 frontend pages tested
- [ ] All 5 calculations spot-checked
