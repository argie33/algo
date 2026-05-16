# Data Freshness Monitoring

## Daily Health Check (Solo Operation)

### Morning Before Market Open (9:30 AM ET)
```sql
-- What's stale?
SELECT symbol, MAX(date) as last_date, CURRENT_DATE - MAX(date) as days_old
FROM price_daily
GROUP BY symbol
HAVING MAX(date) < CURRENT_DATE - INTERVAL '1 day'
LIMIT 20;

-- How many rows loaded yesterday?
SELECT 
    (SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE - INTERVAL '1 day') as prices,
    (SELECT COUNT(*) FROM technical_data_daily WHERE date = CURRENT_DATE - INTERVAL '1 day') as technical,
    (SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE - INTERVAL '1 day') as buy_sell;

-- Any loaders fail?
SELECT loader_name, status, error_message 
FROM loader_sla_tracker 
WHERE date = CURRENT_DATE - INTERVAL '1 day' AND status != 'success';
```

### Market Close (4:30 PM ET)
```sql
-- Did we trade today?
SELECT COUNT(*) as positions, COUNT(DISTINCT symbol) as symbols
FROM algo_positions 
WHERE updated_at >= CURRENT_DATE;

-- Any risk alerts?
SELECT symbol, var_95, concentration_pct, beta 
FROM algo_risk_daily 
WHERE date = CURRENT_DATE 
AND (var_95 > 2.0 OR concentration_pct > 30 OR beta > 2.0);
```

## If Something's Broken

1. **Loader failed:** Check CloudWatch Logs → filter by loader name → look for exception stack trace
2. **Data is stale (>1h old):** 
   - Restart orchestrator: `python3 algo_orchestrator.py --mode paper --dry-run`
   - If still stale: Check if external APIs (FRED, Alpaca) are rate limiting
3. **Database query slow:** Run `ANALYZE;` then retry

## CloudWatch Dashboard

Monitor these in real-time:
- **LoaderSuccessRate** (target: 99%+)
- **DataFreshness_price** (target: <1 hour)
- **DataFreshness_technical** (target: <12 hours)
- **OrchestratorDuration** (target: <5 min)
- **APIErrorRate** (target: <0.1%)
- **DataQualityIssues** (target: 0)

If any red → check logs → restart orchestrator → escalate if persists 30+ min.

## Weekly Trend (Every Friday)

```sql
-- Last 7 days: which loaders are flaky?
SELECT 
    DATE(created_at) as date,
    loader_name,
    ROUND(100.0 * SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_pct
FROM loader_sla_tracker
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at), loader_name
ORDER BY success_pct ASC
LIMIT 20;

-- Slowest queries
SELECT query, ROUND(AVG(execution_ms), 0) as avg_ms, MAX(execution_ms) as max_ms, COUNT(*) as runs
FROM query_performance_log
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY query
HAVING AVG(execution_ms) > 500
ORDER BY avg_ms DESC;
```

## SLA Targets

| Metric | Target | Alarm Level |
|--------|--------|-------------|
| Price freshness | <1 hour | >60 min |
| Technical freshness | <12 hours | >12 hours |
| Loader success | 99%+ | <98% |
| Orchestrator runtime | <5 min | >6 min |
| API errors | <0.1% | >0.2% |
| Data quality | 0 issues | Any issue |

If alarm triggered: check logs → verify database is responding → restart orchestrator → if still broken after 30 min, investigate root cause in git log.
