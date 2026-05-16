# Data Freshness & Quality Monitoring

**Date:** 2026-05-15  
**Environment:** Production  
**Monitoring Level:** CRITICAL PATH  

---

## Quick Health Check

```bash
# Run data freshness validation test
python3 tests/integration/test_loader_validation.py

# Check database schema
python3 tests/integration/test_schema_validation.py

# Expected: All checks PASS (green)
```

---

## 1. Daily Data Quality Checklist

### Morning (Before Market Open - 9:25 AM ET)

```sql
-- Check price data loaded
SELECT COUNT(*) as price_rows, MAX(date) as latest_date
FROM price_daily
WHERE date = CURRENT_DATE;
-- Expected: price_rows > 400, latest_date = today

-- Check technical indicators computed
SELECT COUNT(*) as tech_rows
FROM technical_data_daily
WHERE date = CURRENT_DATE
  AND sma_20 IS NOT NULL AND rsi IS NOT NULL;
-- Expected: tech_rows > 400

-- Check signals generated
SELECT COUNT(*) as signal_rows
FROM buy_sell_daily
WHERE date = CURRENT_DATE
  AND (buy_signal IS NOT NULL OR sell_signal IS NOT NULL);
-- Expected: signal_rows > 50

-- Check scores updated
SELECT COUNT(*) as score_rows
FROM stock_scores
WHERE DATE(updated_at) = CURRENT_DATE;
-- Expected: score_rows > 50
```

**If Any Fail:**
- Check CloudWatch logs for loader errors
- Verify database connectivity
- Run individual loaders in debug mode

### Market Close (3:30 PM ET - After Orchestrator)

```sql
-- Check market exposure computed
SELECT exposure_pct, regime, halt_reasons
FROM market_exposure_daily
WHERE date = CURRENT_DATE;
-- Expected: exposure_pct 0-100, regime in (confirmed_uptrend, uptrend_under_pressure, caution, correction)

-- Check risk metrics calculated
SELECT var_pct_95, portfolio_beta, top_5_concentration
FROM algo_risk_daily
WHERE report_date = CURRENT_DATE;
-- Expected: var_pct_95 0-10, portfolio_beta > 0, top_5_concentration 0-100

-- Check orchestrator completed
SELECT COUNT(*) as phase_count, MAX(action_date) as last_phase
FROM algo_audit_log
WHERE DATE(action_date) = CURRENT_DATE
  AND action_type IN ('success', 'halt');
-- Expected: phase_count >= 7, last_phase = today within last 5 minutes

-- Check data quality issues
SELECT COUNT(*) as quality_issues
FROM data_patrol_log
WHERE DATE(created_at) = CURRENT_DATE
  AND severity IN ('error', 'critical');
-- Expected: quality_issues = 0 (or minimal)
```

**If Any Fail:**
- Check phase execution logs
- Verify pre-trade data quality gate results
- Check CloudWatch metrics dashboard

---

## 2. Continuous Monitoring (CloudWatch Dashboard)

**Dashboard URL:** AWS CloudWatch → Dashboards → StockAlgo-Metrics

**Key Metrics to Monitor:**

| Metric | Threshold | Action |
|--------|-----------|--------|
| **LoaderSuccessRate** | Should be 100% | Alert if < 90% |
| **DataFreshness** | < 1h (price_daily) | Alert if > 2h |
| **DataFreshness** | < 12h (technical) | Alert if > 24h |
| **OrchestratorDuration** | < 5 minutes | Alert if > 10m |
| **OrchestratorFailures** | Should be 0 | Alert if > 0 |
| **APIErrorRate** | < 5% | Alert if > 10% |
| **DataQualityIssues** | Should be 0 | Alert if > 5 |

**Refresh Frequency:** Every 5 minutes during market hours

---

## 3. Hourly Verification (Automated)

**Scheduled Task:** Every hour via EventBridge

```python
# Equivalent SQL checks run automatically
def check_data_freshness():
    """Verify all data tables have recent updates."""
    checks = {
        'price_daily': {
            'expected_rows': 400,
            'max_age_hours': 1,
        },
        'technical_data_daily': {
            'expected_rows': 400,
            'max_age_hours': 12,
        },
        'buy_sell_daily': {
            'expected_rows': 50,
            'max_age_hours': 2,
        },
        'stock_scores': {
            'expected_rows': 50,
            'max_age_hours': 24,
        },
        'market_exposure_daily': {
            'expected_rows': 1,
            'max_age_hours': 8,  # Computed once/day after market close
        },
        'algo_risk_daily': {
            'expected_rows': 1,
            'max_age_hours': 8,
        },
    }
    
    for table, config in checks.items():
        row_count = query(f"SELECT COUNT(*) FROM {table} WHERE date = CURRENT_DATE")
        max_age = query(f"SELECT MAX(created_at) FROM {table}")
        
        if row_count < config['expected_rows']:
            alert(f"{table}: Only {row_count} rows, expected {config['expected_rows']}")
        
        if age_hours(max_age) > config['max_age_hours']:
            alert(f"{table}: Data is {age_hours} hours old")

    return all_checks_passed
```

**Alert Conditions:**
- Row count below threshold → WARNING
- Data age exceeds threshold → CRITICAL
- Any NULL in required columns → ERROR
- Missing table → CRITICAL

---

## 4. Daily Report Generation

**Time:** 4:00 PM ET (after orchestrator + risk calcs)

**Report Contents:**

```
═══════════════════════════════════════════════════════════════
                     DATA QUALITY REPORT
                    Date: 2026-05-15
═══════════════════════════════════════════════════════════════

LOADER STATUS:
  ✓ loadpricedaily       100%  (510 rows)
  ✓ loadstockscores      100%  (412 rows)
  ✓ loadtechnicalsdaily  100%  (510 rows)
  ✓ loadbuyselldaily     100%  ( 85 rows)
  ✓ loadecondata         100%  (  7 rows)

DATA FRESHNESS:
  ✓ price_daily          < 30 min (updated 3:52 PM)
  ✓ technical_data_daily < 2 hours (updated 3:45 PM)
  ✓ buy_sell_daily       < 1 hour (updated 3:55 PM)
  ✓ stock_scores         < 4 hours (updated 11:30 AM)

MARKET EXPOSURE:
  ✓ Regime: confirmed_uptrend
  ✓ Exposure: 85%
  ✓ Halt Reasons: None

RISK METRICS:
  ✓ VaR (95%): 1.42%
  ✓ Portfolio Beta: 1.23
  ✓ Top 5 Concentration: 18%

ORCHESTRATOR:
  ✓ Phase 1 (Data Load): 12s
  ✓ Phase 2 (Exposure): 8s
  ✓ Phase 3a (Signals): 45s
  ✓ Phase 3b (Policy): 2s
  ✓ Phase 4 (Exits): 3s
  ✓ Phase 5 (Analysis): 15s
  ✓ Phase 6 (Entries): 8s
  ✓ Phase 7 (Reconcile): 2s
  ━━━━━━━━━━━━━━━━━━━
  Total: 1m 35s

DATA QUALITY ISSUES: 0

═══════════════════════════════════════════════════════════════
```

**Distribution:** Email to team, Slack notification, uploaded to S3

---

## 5. Weekly Deep Dive Analysis

**Every Friday 4:00 PM ET**

```sql
-- 1. Loader Success Rate (weekly)
SELECT 
    loader_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes,
    ROUND(100.0 * SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
FROM loader_sla_tracker
WHERE start_time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY loader_name
ORDER BY success_rate DESC;

-- 2. Slowest Queries (find performance bottlenecks)
SELECT 
    query,
    count(*) as executions,
    ROUND(AVG(duration_ms), 0) as avg_duration_ms,
    MAX(duration_ms) as max_duration_ms
FROM query_execution_log
WHERE executed_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY query
ORDER BY avg_duration_ms DESC
LIMIT 10;

-- 3. Data Quality Trends
SELECT 
    DATE(created_at) as date,
    severity,
    COUNT(*) as issue_count
FROM data_patrol_log
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY date, severity
ORDER BY date DESC, severity;

-- 4. Market Regime Stability
SELECT 
    date,
    regime,
    exposure_pct,
    CASE 
        WHEN halt_reasons = '{}' THEN 'No halts'
        ELSE halt_reasons::TEXT
    END as halt_status
FROM market_exposure_daily
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY date DESC;
```

**Actions:**
- [ ] Review loader reliability (target: 99.5%)
- [ ] Identify slow queries for optimization
- [ ] Investigate quality issues (root cause analysis)
- [ ] Validate market regime consistency
- [ ] Check for data anomalies or gaps

---

## 6. Production Incident Response

**If Critical Alert Triggers:**

### Tier 1 (Data not loading - affects trading)
```
1. Check CloudWatch Logs for loader errors
2. Verify database connectivity
3. Check if external API is down (FRED, Yahoo Finance, etc.)
4. Run individual loader in debug mode
5. If >1 hour: escalate, consider trading halt
```

### Tier 2 (Stale data - affects decisions)
```
1. Check loader run history (is it running at all?)
2. Verify EventBridge rule is enabled
3. Check if loader process is stuck (timeout)
4. Restart the loader manually if needed
5. Monitor until fresh data arrives
```

### Tier 3 (Quality gates triggered - blocks entries)
```
1. Review pre-trade data quality gate details
2. Identify which validation failed (freshness? coverage? NULLs?)
3. Fix underlying data issue
4. Re-run orchestrator once fixed
```

---

## 7. Monthly Archive & Cleanup

**First Friday of each month:**

```sql
-- Archive old audit logs (keep 90 days)
INSERT INTO algo_audit_log_archive
SELECT * FROM algo_audit_log
WHERE action_date < CURRENT_DATE - INTERVAL '90 days';

DELETE FROM algo_audit_log
WHERE action_date < CURRENT_DATE - INTERVAL '90 days';

-- Archive old quality logs (keep 60 days)
INSERT INTO data_patrol_log_archive
SELECT * FROM data_patrol_log
WHERE created_at < CURRENT_DATE - INTERVAL '60 days';

DELETE FROM data_patrol_log
WHERE created_at < CURRENT_DATE - INTERVAL '60 days';

-- Analyze tables for query optimization
ANALYZE price_daily;
ANALYZE technical_data_daily;
ANALYZE buy_sell_daily;
ANALYZE algo_positions;
ANALYZE algo_trades;
```

---

## 8. Monitoring Dashboard Access

**CloudWatch Dashboard URL:**
```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=StockAlgo-Metrics
```

**Key Bookmarks:**
1. CloudWatch Dashboard (metrics overview)
2. CloudWatch Logs (error investigation)
3. RDS Performance Insights (database health)
4. Lambda Monitoring (function performance)
5. EventBridge Rules (job scheduling)

---

## 9. Escalation Contacts

**Data Quality Issues:**
- Primary: Data Engineering lead
- Secondary: Platform Engineering
- Escalation: CTO

**Performance Issues:**
- Primary: Database Admin
- Secondary: DevOps Engineer
- Escalation: Platform Engineering lead

**Production Incident:**
- Primary: On-call engineer (check oncall rotation)
- Secondary: Incident commander
- Escalation: Engineering manager

---

## 10. SLA Targets

| Service | Target | Threshold |
|---------|--------|-----------|
| **Data Freshness (price)** | < 1h | Alert > 2h |
| **Data Freshness (technical)** | < 12h | Alert > 24h |
| **Loader Success Rate** | 99.5% | Alert < 95% |
| **Orchestrator Duration** | < 5min | Alert > 10min |
| **API Availability** | 99.9% | Alert < 95% |
| **Data Quality Issues** | 0 | Alert > 0 |

---

**Last Updated:** 2026-05-15  
**Next Review:** 2026-05-22  
**Status:** COMPLETE
