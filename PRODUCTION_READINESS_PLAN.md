# 🚀 Production Readiness Execution Plan
**Date:** 2026-05-15  
**Goal:** Transform platform from "almost working" to "production-ready and trustworthy"

---

## 📊 CURRENT STATE

| Component | Status | Confidence |
|-----------|--------|-----------|
| **Infrastructure** | ✓ Deployed (Terraform IaC) | 95% |
| **Critical Blocker** | ✓ FIXED (credential_manager) | 100% |
| **Data Pipeline** | ⚠ Uncertain (not all validated) | 60% |
| **API Endpoints** | ⚠ Untested in production | 50% |
| **Calculations** | ⚠ Some verified, some not | 65% |
| **Risk Management** | ⚠ VaR fixed, exposure pending | 70% |
| **Trading Execution** | ⚠ Code exists, not battle-tested | 40% |
| **Overall** | 🔧 UNDER MAINTENANCE | **62%** |

---

## 🎯 EXECUTION PHASES

### Phase 1: DEPLOY & VERIFY CI (2 hours)
**Status:** IN PROGRESS

**✓ COMPLETED:**
- Fixed credential_manager calls in 121 files
- Committed fix to git
- Pushed to GitHub

**NOW:**
1. Monitor GitHub Actions CI job
   - URL: https://github.com/argie33/algo/actions
   - Watch for: Terraform, Docker, Lambda, Frontend, Database jobs
   - Expected time: ~25-30 minutes
   - Success = all 6 jobs green

2. Once CI passes, verify AWS deployment
   ```bash
   # Test API is responding
   curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health
   
   # Expected: {"status": "healthy", "timestamp": "..."}
   ```

3. Verify database schema initialized
   ```bash
   psql -h <RDS-endpoint> -U stocks -d stocks -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';"
   # Expected: 50+ tables
   ```

**EXIT CRITERIA:** CI passes + API responds + Database has tables

---

### Phase 2: DATA PIPELINE VALIDATION (2 hours)

**Objective:** Verify all loaders are running and populating tables with fresh data

**Steps:**
1. Run validation suite:
   ```bash
   python3 comprehensive_validation_suite.py --check data
   ```

2. Check each critical table:
   ```bash
   # price_daily - should have today's data
   SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;
   # Expected: 100+ rows (each symbol)
   
   # buy_sell_daily - should have signals for today
   SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;
   # Expected: 100+ rows
   
   # technical_data_daily - should be fresh
   SELECT COUNT(*) FROM technical_data_daily WHERE date = CURRENT_DATE;
   # Expected: 100+ rows
   
   # economic_data - should have recent FRED series
   SELECT DISTINCT series_id FROM economic_data ORDER BY series_id;
   # Expected: BAMLH0A0HYM2, BAMLC0A0CM, T10Y2Y, FEDFUNDS, UNRATE, USREC, DCOILWTICO
   
   # stock_scores - composite scoring
   SELECT COUNT(*) FROM stock_scores;
   # Expected: 500+ rows (our universe)
   
   # market_exposure_daily - daily risk snapshots
   SELECT COUNT(*) FROM market_exposure_daily WHERE date >= CURRENT_DATE - INTERVAL '7 days';
   # Expected: 5+ rows (weekdays)
   
   # algo_risk_daily - VaR metrics
   SELECT COUNT(*) FROM algo_risk_daily WHERE report_date >= CURRENT_DATE - INTERVAL '7 days';
   # Expected: 5+ rows (weekdays)
   ```

3. If any table is empty or stale:
   - Check CloudWatch logs: `aws logs tail /aws/ecs/data-loaders --since 6h`
   - Identify which loader failed
   - Fix code, commit, push
   - Wait for re-deployment

**EXIT CRITERIA:** All critical tables have fresh data (≤24 hours old)

---

### Phase 3: API ENDPOINT COVERAGE (1.5 hours)

**Objective:** Verify all 24 pages have working API endpoints

**Steps:**
1. Test each major endpoint:
   ```bash
   # Health
   curl https://API/api/health
   
   # Algo trading
   curl https://API/api/algo/status
   curl https://API/api/algo/positions
   curl https://API/api/algo/trades
   
   # Market data
   curl "https://API/api/stocks?limit=10"
   curl "https://API/api/prices/history/AAPL?days=30"
   curl "https://API/api/sectors"
   curl "https://API/api/market/breadth"
   
   # Economic data
   curl "https://API/api/economic/leading-indicators"
   curl "https://API/api/economic/yield-curve-full"
   curl "https://API/api/economic/calendar"
   
   # Signals
   curl "https://API/api/signals/stocks?symbol=AAPL"
   curl "https://API/api/signals/etfs"
   
   # Sentiment
   curl "https://API/api/sentiment/analyst/insights/AAPL"
   
   # Portfolio
   curl "https://API/api/portfolio/summary"
   
   # Commodities
   curl "https://API/api/commodities"
   
   # Risk
   curl "https://API/api/scores/correlation"
   ```

2. For each endpoint:
   - ✓ Returns 200 status
   - ✓ Returns valid JSON
   - ✓ Data is non-empty (not {"data": []})
   - ✓ Data matches what frontend expects

3. If endpoint fails:
   - Check API Lambda logs: `aws logs tail /aws/lambda/algo-api-lambda --since 6h`
   - Identify missing table or query error
   - Fix code, deploy

**EXIT CRITERIA:** All 12+ critical endpoints return data

---

### Phase 4: CALCULATION VERIFICATION (1.5 hours)

**Objective:** Verify key calculations are correct

**Steps:**
1. Market Exposure calculation:
   ```bash
   SELECT 
       date,
       market_exposure_pct,
       long_exposure_pct,
       short_exposure_pct,
       long_exposure_pct - short_exposure_pct as calculated_net
   FROM market_exposure_daily
   ORDER BY date DESC
   LIMIT 7;
   ```
   - Verify: -100 ≤ market_exposure_pct ≤ +100
   - Verify: long + short = ~100 (fully invested)
   - Verify: net exposure matches algo strategy

2. VaR (Value at Risk) calculation:
   ```bash
   SELECT 
       report_date,
       var_pct_95,
       cvar_pct_95,
       stressed_var_pct,
       portfolio_beta
   FROM algo_risk_daily
   ORDER BY report_date DESC
   LIMIT 7;
   ```
   - Verify: 0 ≤ var_pct_95 ≤ 50
   - Verify: cvar_pct_95 ≥ var_pct_95 (CVaR always ≥ VaR)
   - Verify: portfolio_beta is reasonable (usually 0.8-1.5 for equity portfolio)

3. Stock Scores (composite):
   ```bash
   SELECT 
       symbol,
       composite_score,
       quality_score,
       growth_score,
       stability_score,
       value_score,
       momentum_score,
       positioning_score,
       (quality_score + growth_score + stability_score + value_score + momentum_score + positioning_score) / 6 as calculated_composite
   FROM stock_scores
   ORDER BY composite_score DESC
   LIMIT 10;
   ```
   - Verify: composite = average of 6 component scores
   - Verify: all scores between 0-100
   - Verify: top scorers are quality/growth stocks (not random)

4. Signal Quality Scoring:
   ```bash
   SELECT 
       symbol,
       date,
       trend_template_score,
       base_quality_score,
       volume_confirmation_score,
       composite_sqs,
       (trend_template_score + base_quality_score + volume_confirmation_score) / 3 as calculated_composite
   FROM signal_quality_scores
   WHERE date = CURRENT_DATE - INTERVAL '1 day'
   LIMIT 20;
   ```

**EXIT CRITERIA:** All calculations verified correct within expected ranges

---

### Phase 5: RISK MANAGEMENT AUDIT (1 hour)

**Objective:** Verify circuit breakers and risk controls are working

**Steps:**
1. Check circuit breaker logic:
   ```bash
   SELECT 
       action_type,
       action_date,
       details->>'halt_reason' as halt_reason,
       details->>'trigger_value' as trigger_value,
       status
   FROM algo_audit_log
   WHERE action_type = 'CIRCUIT_BREAKER'
   ORDER BY action_date DESC
   LIMIT 10;
   ```

2. Verify drawdown limits:
   - Max daily loss: should halt if > -2%
   - Max weekly loss: should halt if > -5%
   - Max monthly loss: should halt if > -10%
   - Max equity curve drawdown: should halt if > -15%

3. Check VIX-based halt:
   - Should halt if VIX > 50
   - Check recent VIX levels in economic_data table

4. Verify position limits:
   - Max positions: 10
   - Max position size: 10% of portfolio
   - Max sector exposure: 30%

**EXIT CRITERIA:** Circuit breakers verified, risk limits confirmed in code

---

### Phase 6: SECURITY & ERROR HANDLING (1 hour)

**Objective:** Verify error handling and security

**Steps:**
1. Check error messages don't leak info:
   ```bash
   # Look at recent errors
   aws logs tail /aws/lambda/algo-api-lambda --since 24h | grep -i "error\|exception"
   # Verify: Error messages are generic (not SQL, credentials, paths exposed)
   ```

2. Verify parameterized queries (not SQL injection):
   ```bash
   # Spot-check API handlers
   grep -n "cur.execute" lambda/api/lambda_function.py | head -5
   # Verify: All use %s placeholders with tuple args, not f-strings
   ```

3. Check authentication/authorization:
   - Cognito disabled? Yes (public API) ✓
   - API Gateway has auth? Check if needed

4. Verify timeout handling:
   ```bash
   # Check Lambda timeout settings
   aws lambda get-function-configuration --function-name algo-api-lambda | grep Timeout
   # Should be 25-30 seconds
   ```

**EXIT CRITERIA:** Error handling verified, security checks passed

---

### Phase 7: END-TO-END TRADING SIMULATION (2 hours)

**Objective:** Verify 7-phase orchestrator works end-to-end

**Steps:**
1. Check latest orchestrator run:
   ```bash
   SELECT 
       action_type,
       action_date,
       details->>'status' as step_status,
       details->>'message' as message
   FROM algo_audit_log
   WHERE action_type IN ('PHASE_1', 'PHASE_2', 'PHASE_3', 'PHASE_4', 'PHASE_5', 'PHASE_6', 'PHASE_7')
   ORDER BY action_date DESC
   LIMIT 14;  -- Last 2 complete cycles (7 phases × 2)
   ```

2. Verify each phase:
   - Phase 1 (Data Freshness): ✓ Passed
   - Phase 2 (Circuit Breakers): ✓ No halts (good market)
   - Phase 3 (Position Monitor): ✓ All positions healthy
   - Phase 4 (Exit Execution): ✓ Exits executed if needed
   - Phase 5 (Signal Generation): ✓ Candidates evaluated
   - Phase 6 (Entry Execution): ✓ New trades if conditions met
   - Phase 7 (Reconciliation): ✓ P&L calculated

3. Check positions:
   ```bash
   SELECT * FROM algo_positions WHERE status IN ('open', 'OPEN');
   # Should show: symbol, quantity, entry price, current price, P&L
   ```

4. Check recent trades:
   ```bash
   SELECT * FROM algo_trades ORDER BY trade_date DESC LIMIT 10;
   # Should show healthy win rate, proper risk management
   ```

**EXIT CRITERIA:** All 7 phases execute successfully, no errors in logs

---

### Phase 8: FINAL CHECKLIST & SIGN-OFF (1 hour)

**Objective:** Confirm system is production-ready

**Checklist:**

- [ ] CI/CD pipeline passing consistently
- [ ] All 8+ critical tables have fresh data
- [ ] All 12+ API endpoints returning real data
- [ ] Market exposure calculations verified correct
- [ ] VaR calculations verified correct
- [ ] Stock scores calculations verified correct
- [ ] Circuit breakers tested and working
- [ ] Risk limits properly configured
- [ ] Error handling graceful (no leaked info)
- [ ] All queries use parameterized statements (no SQL injection)
- [ ] Performance acceptable (<1s for most queries)
- [ ] 7-phase orchestrator executes daily
- [ ] Positions being tracked correctly
- [ ] Trades being logged with proper reasoning
- [ ] P&L calculations accurate
- [ ] Dashboard displays real data (not mock)
- [ ] No silent data failures (all INSERTs working)

**FINAL DECISION:**
- ✓ READY for production monitoring
- ✓ READY for paper trading
- ⚠ Recommended: Run 1-2 weeks paper trading before live
- ⚠ Recommended: Monitor daily until confident

---

## 📈 SUCCESS METRICS

**Minimum Viable (Go-live threshold):**
- ✓ 95%+ uptime of data pipeline
- ✓ 99%+ accuracy of calculations
- ✓ 0 silent data failures
- ✓ All circuit breakers functioning
- ✓ Full audit trail of all decisions

**Target (Production-grade):**
- ✓ 99.9%+ uptime
- ✓ 100% calculation accuracy
- ✓ <1s API response time (p99)
- ✓ <5ms calculation latency
- ✓ Real-time monitoring + alerts

---

## ⏰ TIMELINE

| Phase | Effort | Blocker? | Next Start |
|-------|--------|----------|-----------|
| 1. Deploy & CI | 2h | YES | Now |
| 2. Data Pipeline | 2h | YES | After Phase 1 |
| 3. API Endpoints | 1.5h | YES | After Phase 2 |
| 4. Calculations | 1.5h | NO | Parallel w/ Phase 3 |
| 5. Risk Audit | 1h | NO | Parallel w/ Phase 3 |
| 6. Security | 1h | NO | Parallel w/ Phase 4 |
| 7. E2E Testing | 2h | YES | After Phase 3 |
| 8. Sign-off | 1h | YES | After Phase 7 |

**TOTAL CRITICAL PATH:** ~8-10 hours  
**PARALLEL WORK:** ~3 hours  
**TOTAL CALENDAR TIME:** 6-8 hours if executed efficiently

---

## 🚨 ESCALATION PATHS

**If any blocker is hit:**

1. **Data loader failing**
   - Check CloudWatch: `aws logs tail /aws/ecs/data-loaders`
   - Identify which loader
   - Fix code → Commit → Push → Redeploy (auto via GitHub Actions)
   - Re-run validation

2. **API endpoint returning error**
   - Check API Lambda logs: `aws logs tail /aws/lambda/algo-api-lambda`
   - Identify SQL error or missing table
   - Fix code → Commit → Push → Redeploy
   - Re-test endpoint

3. **Calculation incorrect**
   - Check algorithm code (algo_market_exposure.py, algo_var.py, etc.)
   - Verify formula against spec
   - Add test case → Fix → Redeploy
   - Re-validate calculation

4. **Circuit breaker not halting**
   - Check algo_circuit_breaker.py logic
   - Verify breach logic is correct
   - Test with manual halt trigger
   - Fix → Redeploy

---

## 📝 DOCUMENTATION

Generated files:
- ✓ `AUDIT_REPORT_2026-05-15.md` - Detailed findings
- ✓ `comprehensive_validation_suite.py` - Automated tests
- ✓ `PRODUCTION_READINESS_PLAN.md` - This file
- ✓ `AWS_VERIFICATION_CHECKLIST.md` - Deployment verification

---

## 🎯 DECISION POINT

**Once all 8 phases complete:**

**Option A: LIVE TRADING**
- Precondition: All checks pass + 2 weeks paper trading success
- Risk: Real money at stake
- Upside: Full strategy execution

**Option B: EXTENDED PAPER TRADING**
- Precondition: All checks pass
- Duration: 2-4 weeks
- Benefit: Build confidence, catch edge cases
- Then: Transition to live

**Option C: CONTINUE DEVELOPMENT**
- If critical issues found in Phase 7-8
- Fix issues → Return to Phase 1
- Do NOT deploy to live until all phases pass

**RECOMMENDATION:** Option B (4 weeks paper trading, then live with 5% capital)

---

Generated: 2026-05-15  
Next Review: When all phases complete
Status: IN PROGRESS (Phase 1 - Awaiting CI)
