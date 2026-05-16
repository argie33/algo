# Production Readiness Checklist

**Date:** 2026-05-15  
**Target:** Before 2026-06-01 launch  
**Owner:** DevOps + Platform Engineering  

---

## 🎯 EXECUTIVE CHECKLIST

Quick overview of critical items:

- [ ] **Data Pipeline** — All 6 critical loaders populating fresh data
- [ ] **API Endpoints** — All 12+ endpoints returning correct HTTP status
- [ ] **Orchestrator** — 7-phase execution completing without errors
- [ ] **Risk Controls** — Pre-trade validation blocking bad trades
- [ ] **Monitoring** — CloudWatch alarms triggering on failures
- [ ] **Database** — Performance indexes applied, queries < 100ms
- [ ] **Security** — npm audit clean, Dependabot critical issues patched
- [ ] **Infrastructure** — Lambda, ECS, RDS, EventBridge verified working

---

## 📋 DETAILED CHECKLIST

### Phase 1: Data Pipeline Validation

**Objective:** Ensure all loaders populate fresh data daily

```bash
cd /algo
python3 tests/integration/test_loader_validation.py
```

**Success Criteria:**
- [ ] price_daily has 500+ rows for today
- [ ] technical_data_daily populated with RSI, MACD, SMAs
- [ ] buy_sell_daily has signals for 80%+ of universe
- [ ] stock_scores updated within last 24 hours
- [ ] market_exposure_daily has regime and tier set
- [ ] algo_risk_daily has VaR and concentration metrics
- [ ] All data is < 1 hour old (price_daily), < 12 hours (technical)
- [ ] Loader SLA tracker shows 100% success rate

**If failures:**
- Run individual loaders in verbose mode: `python3 loadpricedaily.py --debug`
- Check `/cloudwatch` for loader error logs
- Verify API keys in credential_manager (FRED_API_KEY, Alpaca credentials)
- Check disk space on Lambda ECS task
- Inspect database error_log table for schema mismatches

### Phase 2: API Endpoint Validation

**Objective:** Verify all API handlers return correct HTTP status codes

```bash
# Run against staging API
curl -H "Authorization: Bearer $TOKEN" \
  https://api.algo.example.com/api/algo/exposure-policy
# Should return 200 + JSON, never 500 with empty data
```

**Critical Endpoints to Test:**
- [ ] `/api/health` → 200 OK
- [ ] `/api/algo/exposure-policy` → 200 + market regime
- [ ] `/api/algo/risk` → 200 + VaR/concentration
- [ ] `/api/algo/performance` → 200 + Sharpe/drawdown
- [ ] `/api/scores/stockscores` → 200 + scores array
- [ ] `/api/positions` → 200 + position list (if has positions)
- [ ] `/api/trades` → 200 + trade history
- [ ] `/api/backtest/results` → 200 + backtest data

**Test Script:**
```bash
# From /tests/integration/
python3 test_api_endpoints.py --env=staging --verbose
```

**If failures:**
- Check Lambda CloudWatch logs for exceptions
- Verify database connection string in Secrets Manager
- Ensure API Gateway routes match handler names
- Check request payload format (JSON, required fields)
- Verify authorization headers aren't blocking

### Phase 3: Orchestrator Execution

**Objective:** Run full 7-phase execution and verify all phases complete

```bash
# Paper trading mode (safe, no real orders)
python3 algo_orchestrator.py \
  --mode=paper \
  --date=2026-05-15 \
  --verbose
```

**Phase Completion Success Criteria:**
- [ ] Phase 1 (data load) completes in < 30s
- [ ] Phase 2 (market exposure) returns valid regime
- [ ] Phase 3a (signal generation) produces qualified trades
- [ ] Phase 3b (exposure policy) applies tier constraints
- [ ] Phase 4 (exit execution) finds and closes eligible positions
- [ ] Phase 5 (signal analysis) computes fresh signals
- [ ] Phase 6 (entry execution) respects max_positions and tier caps
- [ ] Phase 7 (reconciliation) completes without errors

**Phase Output:**
- [ ] All phases logged with timestamps in algo_audit_log
- [ ] No exceptions in CloudWatch (ERROR or CRITICAL level)
- [ ] Total execution time < 5 minutes
- [ ] Memory usage stable (< 2GB in Lambda)

**If failures:**
- Check specific phase error log: `SELECT * FROM algo_audit_log WHERE phase=X ORDER BY action_date DESC LIMIT 10`
- Verify data quality gate: `SELECT * FROM algo_audit_log WHERE action_type='halt'`
- Check for blocked positions: `SELECT * FROM algo_positions WHERE status='halted'`

### Phase 4: Risk Control Validation

**Objective:** Verify pre-trade gates block bad trades

**Circuit Breaker Tests:**
```bash
# Test each gate independently
python3 -c "from algo_circuit_breaker import CircuitBreaker; cb = CircuitBreaker(); cb.test_all_gates()"
```

**Should Block Entry If:**
- [ ] VIX > 40 and rising (volatility too high)
- [ ] Market in correction without follow-through day
- [ ] Credit spreads > 8.5% (systemic stress)
- [ ] Drawdown > max_drawdown_pct setting
- [ ] Concentration > 30% in top 5 holdings
- [ ] Portfolio margin < required reserve
- [ ] Data quality failures (missing prices, stale signals)

**Verify In Database:**
```sql
SELECT * FROM algo_positions 
WHERE halt_reason IS NOT NULL 
ORDER BY created_at DESC LIMIT 20;
```

**If gates too permissive:**
- Review circuit_breaker thresholds in config
- Check data quality issue root cause
- Verify halt_reason is being set on blocked positions

### Phase 5: CloudWatch Monitoring

**Objective:** Verify alarms are triggered on failures

**Check CloudWatch Dashboard:**
1. Go to CloudWatch console → Dashboards → StockAlgo
2. Verify metrics are updating (not stale):
   - [ ] LoaderSuccessRate (should be 100%)
   - [ ] DataFreshness (should be <1h for prices)
   - [ ] OrchestratorFailures (should be 0 for this run)
   - [ ] DataQualityIssues (should be 0)

**Verify Alarms:**
```bash
aws cloudwatch describe-alarms \
  --query 'MetricAlarms[*].[AlarmName,StateValue]' \
  --output table
```

Expected alarms:
- [ ] LoaderHealthCheck (should be OK)
- [ ] DataStaleness (should be OK if data fresh)
- [ ] APIErrorRate (should be OK)
- [ ] OrchestratorFailures (should be OK)

**If alarms missing or not triggering:**
- Run `python3 cloudwatch_monitoring.py` manually
- Check metrics are being emitted: `aws cloudwatch list-metrics --namespace StockAlgo`
- Verify SNS/email subscriptions are active

### Phase 6: Database Performance

**Objective:** Verify queries execute quickly with new indexes

**Run Performance Benchmark:**
```bash
# Check index usage
EXPLAIN ANALYZE SELECT * FROM price_daily WHERE symbol='AAPL' AND date='2026-05-15';
```

**Should see:**
- [ ] Index scan (not sequential scan)
- [ ] Execution time < 10ms
- [ ] Rows estimated matches actual

**Verify Indexes Exist:**
```sql
SELECT tablename, indexname FROM pg_indexes 
WHERE tablename IN (
  'price_daily', 'technical_data_daily', 'buy_sell_daily',
  'algo_positions', 'algo_trades', 'algo_risk_daily'
)
ORDER BY tablename;
```

**Count indexes:**
- [ ] price_daily has 2+ indexes
- [ ] algo_positions has 3+ indexes
- [ ] algo_trades has 2+ indexes

**If slow queries:**
- Run ANALYZE on tables: `ANALYZE price_daily; ANALYZE algo_positions;`
- Check stats: `SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables;`
- Consider adding more indexes if certain queries are slow

### Phase 7: Security Validation

**Objective:** Ensure no critical security issues

**npm Audit:**
```bash
cd webapp/frontend
npm audit --audit-level=critical
```

**Should return:**
- [ ] 0 critical vulnerabilities (fail if any found)
- [ ] Deploy only if "npm audit fix" succeeds

**Dependabot Alerts:**
1. Go to GitHub → Settings → Security → Dependabot
2. Filter to Critical severity
3. [ ] Should be 0 critical alerts
4. [ ] High severity: < 5 (acceptable for this sprint)

**If security issues found:**
- Merge Dependabot PRs for critical items first
- Test changes don't break auth/API
- Document any known issues in SECURITY.md

### Phase 8: Infrastructure Verification

**Objective:** Verify AWS services are running and accessible

**Lambda Function:**
```bash
aws lambda invoke --function-name StockAlgo-API \
  --payload '{"path":"/api/health"}' \
  response.json
cat response.json
# Should return 200 OK
```

**RDS Database:**
```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM price_daily;"
# Should return count > 0
```

**EventBridge Rule:**
```bash
aws events describe-rule --name StockAlgo-DailyRun
# Should show: "State": "ENABLED"
```

**ECS Task Definition:**
```bash
aws ecs describe-task-definition --task-definition StockAlgo-Loaders
# Should show ACTIVE task definition
```

**If infrastructure not working:**
- Check Terraform state: `terraform show | grep aws_`
- Verify credentials in AWS SSM Parameter Store
- Re-apply Terraform if needed: `terraform apply`

---

## 📊 METRICS TO MONITOR DAILY (First 2 Weeks)

Once deployed, track these metrics:

- **Loader Health:** 100% success rate for all critical loaders
- **Data Freshness:** price_daily updated within 1 hour of market close
- **API Latency:** All endpoints respond in < 500ms (p95)
- **Orchestrator Duration:** Full 7-phase execution < 5 minutes
- **Error Rate:** < 0.1% of requests return 5xx errors
- **Data Quality Issues:** < 1% of data with NULLs in critical fields
- **VaR Volatility:** Day-to-day changes < 0.5% (indicates data stability)

---

## 🚀 LAUNCH APPROVAL

**All checklist items must be ✅ BEFORE launch.**

**Sign-off Required From:**
- [ ] Platform Engineering (infrastructure verified)
- [ ] QA Lead (all tests passing, no blockers)
- [ ] Risk Management (gates tuned, circuit breakers validated)
- [ ] DevOps (monitoring, alarms, incident response ready)

**Post-Launch (First Week):**
- [ ] Daily monitoring of metrics above
- [ ] Paper trading only (no real money)
- [ ] Daily review of orchestrator logs
- [ ] On-call rotation established for alerts
- [ ] Incident response runbooks prepared

---

## 📞 ESCALATION CONTACTS

**If X fails, contact Y:**
- Data pipeline issue → Data Engineering lead
- API error → Backend Engineer
- Orchestrator logic issue → Algo Engineer
- Database performance → Database Admin
- Security issue → Security Team
- Infrastructure issue → DevOps Engineer

---

**Last Updated:** 2026-05-15  
**Next Review:** 2026-05-22 (after first week of staging tests)
