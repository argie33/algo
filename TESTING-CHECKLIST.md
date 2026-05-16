# Production Readiness Testing Checklist

Complete all tests before deploying to production with real money.

## TIER 1: CRITICAL PATH (Must complete before AWS deployment)

### 1.1 Local Data Pipeline Test
**Time:** ~20 minutes
**Prerequisites:** PostgreSQL running on localhost:5432

```bash
# Step 1: Initialize database
python3 init_database.py
# Expected: Creates 132 tables with all schema

# Step 2: Run all loaders
python3 run-all-loaders.py
# Expected: All 30 loaders complete in <15 minutes
```

**Verification:**
```sql
-- Check table counts
SELECT COUNT(*) FROM stock_symbols;           -- Should be 1000+
SELECT COUNT(*) FROM stock_scores;            -- Should be 1000+
SELECT COUNT(*) FROM price_daily;             -- Should be 50000+
SELECT COUNT(*) FROM technical_data;          -- Should be 50000+
SELECT COUNT(*) FROM quality_metrics;         -- Should be 500+
SELECT COUNT(*) FROM growth_metrics;          -- Should be 500+
SELECT COUNT(*) FROM value_metrics;           -- Should be 500+

-- Check data freshness
SELECT MAX(date) FROM price_daily;            -- Should be today or yesterday
SELECT MAX(updated_at) FROM stock_scores;     -- Should be today or yesterday
```

**Pass Criteria:**
- [ ] All loaders complete without errors
- [ ] All tables have data within expected ranges
- [ ] Data freshness is current (within 1 day)
- [ ] No "connection pool exhausted" errors

---

### 1.2 Orchestrator Dry-Run Test
**Time:** ~10 minutes
**Prerequisites:** Data pipeline complete (1.1)

```bash
python3 algo_orchestrator.py --mode paper --dry-run
```

**Expected Output:**
```
Phase 1: Data Freshness — PASS
Phase 2: Circuit Breakers — PASS (or HALT if market closed)
Phase 3: Position Monitor — PASS
Phase 4: Exit Execution — PASS
Phase 5: Signal Generation — Signal count: 50-200
Phase 6: Entry Execution — Simulated entries
Phase 7: Reconciliation — PASS
```

**Pass Criteria:**
- [ ] All 7 phases complete
- [ ] No exceptions in logs
- [ ] Signal count is reasonable (20-300)
- [ ] No NaN or None values in calculations

---

### 1.3 Data Consistency Check
**Time:** ~5 minutes
**Verify no data corruption**

```sql
-- Check for duplicates
SELECT symbol, date, COUNT(*) 
FROM price_daily 
GROUP BY symbol, date 
HAVING COUNT(*) > 1 
LIMIT 5;
-- Expected: No results

-- Check for NULL values in critical columns
SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NULL;
-- Expected: 0 (or very small number)

SELECT COUNT(*) FROM algo_positions WHERE current_price IS NULL;
-- Expected: 0
```

**Pass Criteria:**
- [ ] No duplicate records
- [ ] No unexpected NULL values in critical columns

---

### 1.4 Frontend Manual Testing (All Pages)
**Time:** ~30 minutes
**Open browser, test each page**

For each of these pages:
1. Economic Dashboard
2. Market Dashboard  
3. Portfolio Dashboard
4. Trading Signals
5. Trade Tracker
6. Risk Dashboard
7. Performance Analysis
8. Stock Screener
9. Sector Analysis
10. Industry Analysis
...and any other pages in the menu

**For each page:**
- [ ] Page loads without errors (no red errors in console)
- [ ] Data displays (not loading forever, not blank)
- [ ] Numbers look reasonable (not NaN, not -999999)
- [ ] Charts render if present
- [ ] No 404 errors

**Common Issues to Watch For:**
- [ ] API errors in console (401, 500, etc.)
- [ ] "Cannot read property X" errors
- [ ] Data showing as "—" or null everywhere
- [ ] Charts broken or showing no data

---

### 1.5 Paper Trading Test (24-48 hours)
**Time:** Ongoing monitoring
**Run live trading on paper account**

```bash
# Remove --dry-run for live execution
python3 algo_orchestrator.py --mode paper
```

**Monitor Daily:**
- [ ] Check Alpaca account dashboard (paper trading)
- [ ] Verify trades appear within 1 hour of orchestrator run
- [ ] Check positions are tracked in database
- [ ] Monitor P&L updates
- [ ] Watch CloudWatch logs for errors
- [ ] Verify data freshness SLAs met

**After 24-48 Hours:**
- [ ] At least 5+ trades executed
- [ ] Exits triggered correctly (not stuck)
- [ ] No account errors or restrictions
- [ ] Data freshness maintained

---

## TIER 2: PERFORMANCE & SECURITY

### 2.1 Performance Benchmarking
**Time:** ~30 minutes

```bash
# Measure API response times
time curl -s https://api.example.com/api/algo/positions | wc -c

# Measure Lambda execution
# Check CloudWatch: Logs → Duration (should be <500ms for warm)

# Measure database query speed
EXPLAIN ANALYZE SELECT ... (run slow queries from logs)
```

**Pass Criteria:**
- [ ] API endpoints respond in <200ms (p95)
- [ ] Lambda cold start <5s, warm <500ms
- [ ] No N+1 queries
- [ ] No sequential scans on large tables

---

### 2.2 Security Verification
**Time:** ~20 minutes

**Credential Security:**
```bash
# Check CloudWatch logs for credential leaks
aws logs tail /aws/lambda/algo-api --no-follow | grep -i "APCA_\|FRED_\|password"
# Expected: No results
```

**Authentication:**
- [ ] Try accessing protected endpoints without token → 401
- [ ] Try accessing admin endpoints as user → 403
- [ ] Try SQL injection in search → Returns 400 Bad Request
- [ ] Try XSS payload in input → Sanitized or rejected

**Pass Criteria:**
- [ ] No credentials in logs
- [ ] Auth properly enforced
- [ ] Rate limiting active (100 req/min)
- [ ] Input validation working

---

### 2.3 AWS Infrastructure Verification
**Time:** ~15 minutes

```bash
# Verify deployment
git push origin main  # Triggers GitHub Actions

# Monitor deployment
# Watch: https://github.com/your-repo/actions

# Verify resources exist
aws lambda list-functions --query "Functions[?contains(FunctionName, 'algo-')]"
aws rds describe-db-instances --query "DBInstances[0].DBInstanceIdentifier"
aws apigatewayv2 get-apis
```

**Check CloudWatch Dashboard:**
- [ ] Lambda error rate <0.1%
- [ ] RDS CPU <70%
- [ ] API latency <200ms p95
- [ ] No alarms firing

**Pass Criteria:**
- [ ] All 6 Lambda functions deployed
- [ ] RDS database accessible
- [ ] API Gateway responding with 200s
- [ ] EventBridge schedule active (5:30pm ET)

---

## TIER 3: EDGE CASES & ROBUSTNESS

### 3.1 Edge Case Testing
**Time:** ~30 minutes

**Scenario 1: Zero Trades (Portfolio Initialization)**
- [ ] Portfolio page loads
- [ ] Shows $100,000 initial cash
- [ ] No crashes on empty trade list
- [ ] P&L shows 0/0%

**Scenario 2: 100+ Trades (Pagination)**
- [ ] Trade list paginates correctly
- [ ] Can navigate pages
- [ ] Performance acceptable (<2s load time)
- [ ] Totals sum correctly

**Scenario 3: All Positions in Loss**
- [ ] P&L shows red numbers
- [ ] Portfolio doesn't crash
- [ ] Correctly calculates loss percentages

**Scenario 4: Circuit Breaker Triggers**
- [ ] No trades enter when breaker fires
- [ ] Proper logging of breaker reason
- [ ] System continues monitoring

**Scenario 5: Missing Technical Data**
- [ ] Signals still generate (use defaults)
- [ ] Filtering logic doesn't crash
- [ ] Reasonable behavior degrades gracefully

---

## TIER 4: FINAL CHECKLIST

Before going live with real money:

- [ ] All TIER 1 tests pass
- [ ] All TIER 2 performance/security verified
- [ ] All TIER 3 edge cases handled gracefully
- [ ] No exceptions in 48-hour paper trading
- [ ] All P&L calculations match manual verification
- [ ] Data freshness SLAs met consistently
- [ ] Orchestrator running on schedule (5:30pm ET)
- [ ] Exponential backoff configured for retries
- [ ] Rate limiting active to prevent API abuse
- [ ] Credentials properly secured (no plaintext)
- [ ] Error responses don't leak schema info
- [ ] CircuitBreaker halts trading on extreme conditions
- [ ] Exit logic executes at all target levels
- [ ] Position sizes within risk limits
- [ ] No logged warnings or errors
- [ ] CloudWatch alarms would catch failures

---

## DEPLOYMENT READINESS SCORING

Rate each tier:

| Tier | Pass? | Issues Found | Comments |
|------|-------|--------------|----------|
| 1.1: Data Pipeline | | | |
| 1.2: Orchestrator | | | |
| 1.3: Data Consistency | | | |
| 1.4: Frontend Pages | | | |
| 1.5: Paper Trading | | | |
| 2.1: Performance | | | |
| 2.2: Security | | | |
| 2.3: Infrastructure | | | |
| 3.1: Edge Cases | | | |

**Final Status:** [ ] Ready for Production | [ ] Needs More Testing

---

## Troubleshooting

### API Returns 401 Unauthorized
- Check Alpaca API keys in Secrets Manager
- Verify JWT token is valid
- Check CORS origin matches frontend URL

### Loaders Timeout or Hang
- Check database connection pool not exhausted
- Verify API rate limits not hit
- Check for network issues to data sources

### Orchestrator Skips Phases
- Check logs for circuit breaker firing
- Verify data freshness (Phase 1 gate)
- Check for exceptions in previous phases

### P&L Numbers Don't Match
- Verify calculations manually for sample trade
- Check database values vs frontend display
- Confirm no rounding errors on percentage displays

### Frontend Shows "—" or null
- Check API response in browser DevTools Network tab
- Verify response shape matches frontend expectations
- Check for missing fields from API response

---

## Success Criteria Summary

**System is production-ready when:**
1. All TIER 1 tests complete successfully
2. Paper trading runs 48+ hours without issues
3. No critical errors in CloudWatch logs
4. All performance benchmarks met
5. Security verification passes
6. Edge cases handled gracefully
7. P&L calculations verified accurate
8. Data freshness within SLA

**Estimated Total Testing Time:** 8-12 hours over 2-3 days
