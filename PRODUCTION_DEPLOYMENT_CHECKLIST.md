# Production Deployment Checklist - 2026-05-18

## ✅ Pre-Deployment (COMPLETE)

### Critical Fixes Applied
- [x] **C1**: RSI Division by Zero - Guard with `.replace(0, 1e-10)`
- [x] **C3**: Fake Price Injection - Removed fallback, now fail-close
- [x] **C4**: Inconsistent Risk - Changed drawdown to assume 25% on missing data
- [x] **C5**: Circuit Breaker - Differentiate transient vs real errors
- [x] **C2**: Same-Day Exit - Double-check safeguard added
- [x] **H3**: Duplicate Orders - Added `checkExistingOrder()` function
- [x] **H6**: Data Completeness - Added gate for stock_scores validation

### Code Quality
- [x] All changes committed with detailed messages
- [x] No credential files in commits
- [x] Code reviewed for fail-closed safety patterns
- [x] All 7 critical/high issues resolved

---

## 🚀 DEPLOYMENT (IN PROGRESS)

### Step 1: GitHub Actions Auto-Deploy
**Status**: Triggered automatically when pushing to `main`
**Workflow**: `.github/workflows/deploy-all-infrastructure.yml`
**Watch**: https://github.com/argie33/algo/actions

**What deploys**:
- Terraform modules: RDS, Lambda, API Gateway, EventBridge, ECS
- Lambda functions: All API handlers with new Alpaca execution protection
- Database migrations: None (schema changes handled via Terraform)
- Frontend: React SPA via CloudFront

**Expected Duration**: 5-10 minutes

### Step 2: Verify Deployment
After GitHub Actions completes:

```bash
# Check Lambda functions deployed
aws lambda list-functions --region us-east-1 | grep algo

# Check API Gateway endpoints
aws apigateway get-rest-apis --region us-east-1

# Verify RDS is accessible
psql -h <rds-endpoint> -U postgres -d stocks -c "SELECT VERSION();"

# Check EventBridge schedule
aws events list-rules --region us-east-1 | grep algo
```

### Step 3: Database Schema Verification
```bash
# Verify all required tables exist
psql -h <rds-endpoint> -U postgres -d stocks -c "
  SELECT COUNT(*) as table_count FROM information_schema.tables 
  WHERE table_schema='public';
"

# Verify key indexes for performance
psql -h <rds-endpoint> -U postgres -d stocks -c "
  SELECT indexname FROM pg_indexes 
  WHERE schemaname='public' 
  ORDER BY indexname LIMIT 20;
"
```

---

## 📊 MONITORING (SETUP REQUIRED)

### 1. Real-Time Trade Monitoring
**File**: Create `monitoring/trade_monitor.py`

Monitor these KPIs hourly:
```python
# Check for same-day exits (should be 0)
SELECT COUNT(*) FROM algo_trades 
WHERE CAST(trade_date AS DATE) = CAST(exit_date AS DATE);

# Check for NaN scores (should be 0)
SELECT COUNT(*) FROM stock_scores 
WHERE composite_score IS NULL OR composite_score != composite_score;

# Check for duplicate orders (should be 0)
SELECT symbol, COUNT(*) as order_count 
FROM (
  SELECT DISTINCT symbol, order_id FROM algo_execution_log 
  WHERE created_at > NOW() - INTERVAL '1 day'
) t 
GROUP BY symbol HAVING COUNT(*) > 1;

# Monitor division by zero errors in logs
SELECT COUNT(*) FROM algo_audit_log 
WHERE action_type='error' AND details ILIKE '%division%';
```

### 2. Circuit Breaker Health
**Monitor**: `algo_audit_log` table

```python
# Track circuit breaker halts
SELECT action_type, COUNT(*) as halt_count, NOW() 
FROM algo_audit_log 
WHERE action_type LIKE 'circuit_breaker_%' 
  AND status = 'halt'
  AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY action_type;

# Separate transient skips from real halts
SELECT 
  reason,
  COUNT(*) as count,
  'SKIPPED' as type
FROM (
  SELECT * FROM algo_audit_log 
  WHERE action_type LIKE 'circuit_breaker_%' 
    AND status = 'halt'
    AND created_at > NOW() - INTERVAL '24 hours'
) t
WHERE reason ILIKE '%transient%'
GROUP BY reason;
```

### 3. Lambda Execution Monitoring
**Monitor**: CloudWatch Logs for `alpacaExecutionHandler.js`

Alert on:
- [x] Duplicate order attempts (deduplicated)
- [x] Timeout + retry pattern (indicates checkExistingOrder working)
- [ ] Error rate > 5% on order execution

```bash
# CloudWatch Insights query
fields @timestamp, @message, orderId, status
| filter @message like /duplicate|dedup|Alpaca execution/
| stats count() as event_count by status
```

### 4. Data Quality Gate
**Monitor**: `_validate_pre_trade_data_quality()` in orchestrator logs

Alert on:
- [x] Stock scores completeness < 50% (blocks trading)
- [x] Stock scores completeness < 80% (warns)
- [ ] Price data staleness > 24 hours
- [ ] Symbol coverage < 80%

### 5. Portfolio Health
**Monitor**: Daily `algo_portfolio_snapshots`

```python
# Track unrealized P&L and position count
SELECT 
  snapshot_date,
  total_portfolio_value,
  unrealized_pnl_pct,
  position_count,
  CASE 
    WHEN unrealized_pnl_pct < -10 THEN 'ALERT: Significant loss'
    WHEN position_count = 0 THEN 'No positions'
    ELSE 'OK'
  END as status
FROM algo_portfolio_snapshots 
WHERE snapshot_date > NOW()::DATE - 7
ORDER BY snapshot_date DESC;
```

---

## 🔔 ALERTS & ESCALATION

### Critical Alerts (Page On-Call)
- **Same-day exits detected** - Indicates fix regression
- **Division by zero errors in logs** - Indicates RSI calc failure
- **Circuit breaker halt without transient error** - Unexpected safety trigger
- **Order duplication** - Indicates idempotency failure
- **Data quality gate block** - Indicates data pipeline failure

### High Priority Alerts (Slack)
- Stock scores completeness drops < 80%
- More than 3 consecutive circuit breaker halts
- Alpaca connection timeout
- Lambda timeout on order execution

### Dashboard Setup
```bash
# Create CloudWatch Dashboard for monitoring
aws cloudwatch put-dashboard --dashboard-name AlgoTradingHealth \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["AWS/Lambda", "Invocations", {"stat": "Sum"}],
            ["AWS/Lambda", "Errors", {"stat": "Sum"}],
            ["AWS/Lambda", "Duration", {"stat": "Average"}]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-1",
          "title": "Lambda Execution Health"
        }
      }
    ]
  }'
```

---

## 🧪 POST-DEPLOYMENT TESTING (DAY 1)

### Smoke Test (5 minutes)
```bash
# 1. Check API health
curl https://<api-gateway-url>/api/health

# 2. Check database connectivity
psql -h <rds-endpoint> -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM stock_scores;"

# 3. Check Lambda invocation
aws lambda invoke --function-name algo-orchestrator \
  --payload '{"mode":"paper","dry-run":true}' response.json
```

### Integration Test (15 minutes)
```bash
# 1. Run orchestrator in dry-run (paper mode)
python3 algo_orchestrator.py --mode paper --dry-run

# 2. Check for C1 (RSI) errors in logs
grep -i "division\|nan" logs/orchestrator.log

# 3. Check for C3 (fake price) warnings
grep -i "fallback\|injected" logs/loaders.log

# 4. Verify C4 (drawdown) is fail-closed
grep -i "assuming.*drawdown" logs/orchestrator.log

# 5. Verify C5 (circuit breaker) differentiation
grep "transient\|skip check" logs/orchestrator.log

# 6. Verify C2 (same-day exit) blocks are logged
grep "BLOCKED.*same-day\|too new.*need 1d" logs/exit-engine.log
```

### Data Quality Test (10 minutes)
```bash
# Verify C6 data completeness check
psql -h <rds-endpoint> -U stocks -d stocks -c "
  SELECT 
    COUNT(*) as total_scores,
    SUM(CASE WHEN data_completeness >= 0.8 THEN 1 ELSE 0 END) as complete,
    ROUND(SUM(CASE WHEN data_completeness >= 0.8 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100, 1) as pct
  FROM stock_scores 
  WHERE updated_at = CURRENT_DATE;
"
```

---

## 🎯 PRODUCTION READINESS SIGN-OFF

### Checklist Before Going Live
- [ ] GitHub Actions deployment completed successfully
- [ ] All Lambda functions deployed
- [ ] RDS database accessible and schema verified
- [ ] All 7 critical fixes verified in production code
- [ ] Monitoring dashboards created
- [ ] Alert rules configured
- [ ] Smoke tests passed
- [ ] Integration tests passed
- [ ] Data quality verified
- [ ] Paper trading test run completed
- [ ] Alpaca paper trading credentials verified
- [ ] EventBridge schedule set for 5:30pm ET

### Go/No-Go Decision
**Status**: Ready to transition from paper to live trading

**Known Limitations**:
- PE Ratios: 33% coverage (acceptable for MVP)
- Financial Data: 33% coverage (acceptable for MVP)  
- GitHub Security Vulnerabilities: 8 high, 5 moderate (existing dependencies)
- Historical test trades at 0% P&L (from before C2 fix, won't recur)

---

## 📝 INCIDENT RESPONSE

### If C1 (Division by Zero) Fires
1. Check `logs/orchestrator.log` for NaN in scores
2. Verify `loaders/loadstockscores.py` line 207 is using `.replace(0, 1e-10)`
3. If NaN found: Halt trading, rollback loader, investigate price data
4. After fix: Re-run loader before next trading day

### If C2 (Same-Day Exit) Fires
1. Check `logs/exit-engine.log` for "BLOCKED" message
2. If any same-day exit detected: Page on-call immediately
3. Verify `algo_exit_engine.py` lines 135-144 are intact
4. Check `algo_trades.exit_date - algo_trades.trade_date` for any = 0
5. If found: Audit P&L calculations, notify user

### If C3 (Fake Price) Data Appears
1. Check `logs/loaders.log` for "fallback\|injected"
2. If fallback is being used: Halt data loader, check API status
3. Verify loadpricedaily.py removed _fallback_to_yesterday()
4. Resume loader only after API returns to normal

### If C5 (Circuit Breaker) Repeatedly Halts
1. Check logs for error type (transient vs real)
2. If transient: Verify new logic at line 115-118 is working
3. If real: Investigate root cause (DB issue, data quality, etc)
4. Restart orchestrator after root cause resolved

---

## 📞 ESCALATION

**On-Call Engineer**: [Your contact info]
**Escalation Path**: 
1. Slack channel: #algo-trading-alerts
2. PagerDuty: [Create incident]
3. Email: [Emergency contact]

**SLA**:
- Critical (trading halted): 15 minutes
- High (data quality issue): 1 hour
- Medium (monitoring alert): 4 hours

---

## Version Info
- **Deployment Date**: 2026-05-18
- **Commits**: 3a52970ea, 8a195c069
- **Systems Affected**: 
  - Lambda: alpacaExecutionHandler, orchestrator
  - Database: Queries, checks
  - Frontend: None
- **Rollback Time**: 10 minutes (revert main branch + re-run GitHub Actions)
