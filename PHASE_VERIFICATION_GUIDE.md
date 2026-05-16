# Production Readiness Phase Verification Guide

**Status:** Use this guide once API endpoints start returning 200 (not 401)

---

## Phase 1: Deployment Verification ✓ (MOSTLY DONE)

**Checklist:**
- [x] GitHub Actions CI passing
- [x] API health endpoint responds (200 OK)
- [ ] API data endpoints respond (200, not 401) — AWAITING INFRASTRUCTURE REDEPLOY
- [ ] Database schema initialized

**When API returns 200 on data endpoints:**
```bash
# Verify a few endpoints work
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=5
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status
```

**Success criteria:** All return HTTP 200 with JSON data

---

## Phase 2: Data Pipeline Validation (30 minutes)

**Test data freshness:**
```bash
# Connect to RDS PostgreSQL (via AWS Console or SSH tunnel if needed)
# Then run these checks:

# Price data
SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;
# Expected: 500+ rows

# Trading signals  
SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;
# Expected: 100+ rows

# Technical indicators
SELECT COUNT(*) FROM technical_data_daily WHERE date = CURRENT_DATE;
# Expected: 500+ rows

# Stock scores
SELECT COUNT(*) FROM stock_scores WHERE updated_at::date = CURRENT_DATE;
# Expected: 500+ rows

# Market exposure
SELECT COUNT(*) FROM market_exposure_daily WHERE date >= CURRENT_DATE - INTERVAL '7 days';
# Expected: 5+ rows (weekdays)

# Risk metrics
SELECT COUNT(*) FROM algo_risk_daily WHERE report_date >= CURRENT_DATE - INTERVAL '7 days';
# Expected: 5+ rows
```

**If any table is empty:**
- Check ECS loader logs: `aws logs tail /aws/ecs/data-loaders --since 6h`
- Look for errors in loader execution
- If recent, wait 24h for next scheduled run
- If stale, may need to manually trigger loaders

---

## Phase 3: API Endpoint Coverage (20 minutes)

**Test critical endpoints:**
```bash
API="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Algo trading
curl "$API/api/algo/status" | jq .
curl "$API/api/algo/positions" | jq .
curl "$API/api/algo/trades" | jq .

# Market data
curl "$API/api/stocks?limit=10" | jq .
curl "$API/api/sectors" | jq .
curl "$API/api/market/breadth" | jq .

# Signals
curl "$API/api/signals/stocks" | jq .
curl "$API/api/signals/etfs" | jq .

# Economic data
curl "$API/api/economic/leading-indicators" | jq .
curl "$API/api/economic/yield-curve-full" | jq .

# Risk & portfolio
curl "$API/api/portfolio/summary" | jq .
curl "$API/api/scores/correlation" | jq .
```

**Success criteria:**
- All return HTTP 200
- All have non-empty data (not `{"data": []}`)
- Data matches what frontend expects

---

## Phase 4: Calculation Verification (20 minutes)

**Spot-check 3 critical calculations:**

### Market Exposure
```sql
SELECT 
    date,
    market_exposure_pct,
    long_exposure_pct,
    short_exposure_pct
FROM market_exposure_daily 
ORDER BY date DESC LIMIT 1;
```

**Verify:**
- long_exposure_pct + short_exposure_pct ≈ 100
- market_exposure_pct = long_exposure_pct - short_exposure_pct
- Value between -100 and +100

### VaR (Value at Risk)
```sql
SELECT 
    report_date,
    var_pct_95,
    cvar_pct_95,
    portfolio_beta
FROM algo_risk_daily 
ORDER BY report_date DESC LIMIT 1;
```

**Verify:**
- 0 ≤ var_pct_95 ≤ 50
- cvar_pct_95 ≥ var_pct_95 (CVaR always ≥ VaR)
- 0.5 ≤ portfolio_beta ≤ 2.0 (typical equity range)

### Stock Scores
```sql
SELECT 
    symbol,
    composite_score,
    quality_score,
    growth_score,
    value_score
FROM stock_scores 
ORDER BY composite_score DESC 
LIMIT 10;
```

**Verify:**
- All scores between 0-100
- Top scorers are quality/growth stocks (AAPL, MSFT, etc. likely at top)
- Composite ≈ average of component scores

---

## Phase 5: Risk Management Audit (15 minutes)

**Check circuit breakers:**
```sql
SELECT 
    action_type,
    action_date,
    details->>'halt_reason' as halt_reason,
    status
FROM algo_audit_log
WHERE action_type = 'CIRCUIT_BREAKER'
ORDER BY action_date DESC
LIMIT 10;
```

**Verify:**
- Recent entries show when/why system halted (if at all)
- Drawdown limits are in code

**Check position limits in code:**
```bash
grep -n "MAX_POSITIONS\|max_position_size\|sector_exposure" algo_orchestrator.py
```

**Verify:**
- MAX_POSITIONS: ≤ 10
- max_position_size: ≤ 10% of portfolio  
- sector_exposure: ≤ 30%

---

## Phase 6: Security & Error Handling (10 minutes)

**Check error messages don't leak info:**
```bash
# In AWS CloudWatch Logs
aws logs tail /aws/lambda/algo-api-lambda --since 24h | grep -i "error\|exception"
```

**Verify:**
- Errors are generic ("database connection error" not credentials/paths)
- No SQL, filenames, or config details in error messages

**Verify parameterized queries:**
```bash
grep "cur.execute" lambda/api/lambda_function.py | head -5
```

**Verify:**
- All use `%s` placeholders with tuple arguments
- None use f-strings or string formatting

---

## Phase 7: End-to-End Orchestrator Testing (30 minutes)

**Check recent orchestrator runs:**
```sql
SELECT 
    action_type,
    action_date,
    details->>'status' as step_status,
    details->>'message' as message
FROM algo_audit_log
WHERE action_type IN ('PHASE_1', 'PHASE_2', 'PHASE_3', 'PHASE_4', 'PHASE_5', 'PHASE_6', 'PHASE_7')
ORDER BY action_date DESC
LIMIT 14;  -- Last 2 complete cycles
```

**Verify each phase:**
- Phase 1 (Data Freshness): ✓ Passed
- Phase 2 (Circuit Breakers): ✓ No errant halts
- Phase 3 (Position Monitor): ✓ All positions healthy
- Phase 4 (Exit Execution): ✓ Exits executed if needed
- Phase 5 (Signal Generation): ✓ Candidates evaluated
- Phase 6 (Entry Execution): ✓ New trades if conditions met
- Phase 7 (Reconciliation): ✓ P&L calculated

**Check recent positions:**
```sql
SELECT symbol, quantity, entry_price, current_price, status 
FROM algo_positions 
WHERE status IN ('open', 'OPEN')
ORDER BY position_id DESC
LIMIT 10;
```

**Verify:**
- All have realistic prices
- Position counts match expectations
- No stuck/stale positions

---

## Phase 8: Final Sign-Off Checklist (15 minutes)

**Complete verification:**

- [ ] CI/CD pipeline passing consistently (GitHub Actions)
- [ ] All 8+ critical tables have fresh data (≤24h)
- [ ] All 12+ API endpoints returning real data (HTTP 200)
- [ ] Market exposure calculations verified correct
- [ ] VaR calculations verified correct  
- [ ] Stock scores calculations verified correct
- [ ] Circuit breakers tested and working
- [ ] Risk limits properly configured
- [ ] Error handling graceful (no leaked info)
- [ ] All queries use parameterized statements (no SQL injection)
- [ ] API response time acceptable (<1s for most queries)
- [ ] 7-phase orchestrator executes daily
- [ ] Positions being tracked correctly
- [ ] Trades being logged with proper reasoning
- [ ] P&L calculations accurate
- [ ] Dashboard displays real data
- [ ] No silent data failures (all INSERTs working)

**GO/NO-GO DECISION:**
- **READY:** If 15/17 items checked (88%+ success)
- **CAUTION:** If 12-14 items checked (70-82% success) — monitor closely
- **NOT READY:** If <12 items checked (<70% success) — fix remaining issues first

---

## Timeline & Effort

| Phase | Time | Blocker? |
|-------|------|----------|
| 1. Deploy & Verify | 5 min | YES (infrastructure deploy) |
| 2. Data Pipeline | 30 min | YES (depends on Phase 1) |
| 3. API Endpoints | 20 min | NO (can run parallel with 2) |
| 4. Calculations | 20 min | NO (can run parallel with 2) |
| 5. Risk Audit | 15 min | NO (can run parallel with 2) |
| 6. Security | 10 min | NO (can run parallel with 2) |
| 7. E2E Testing | 30 min | YES (depends on Phase 2) |
| 8. Sign-Off | 15 min | YES (depends on Phase 7) |

**Total Critical Path:** ~75 minutes (infrastructure deploy + phases 1,2,7,8)

---

## Debugging Help

**If any verification fails:**

1. **Check logs:**
   ```bash
   # API Lambda logs
   aws logs tail /aws/lambda/algo-api-lambda --since 6h
   
   # Data loader logs
   aws logs tail /aws/ecs/data-loaders --since 6h
   
   # Orchestrator logs
   aws logs tail /aws/ecs/algo-orchestrator --since 6h
   ```

2. **Common issues:**
   - 401 errors: Check if Cognito is still required (should be false)
   - Empty tables: Check if loaders are running on schedule
   - Calculation errors: Check SQL queries match schema
   - Performance issues: Look for missing indexes

3. **Recovery:**
   - If data is stale: Manually trigger loaders (check ECS task definitions)
   - If calculation is wrong: Fix code, commit, push (auto-redeploys)
   - If API returns error: Check CloudWatch, fix code, redeploy

---

Generated: 2026-05-16
Next Review: After infrastructure redeploy completes (when 401 errors disappear)
