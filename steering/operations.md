# Operations & Monitoring Guide

## Health Status

**Quick check:** `curl https://api.example.com/api/health` → shows status (healthy/degraded/unhealthy), database latency, loader freshness.

**Alerts (SNS email):** API Lambda errors (5+ in 5 min), Algo Lambda errors (any), RDS CPU >80%/memory <256MB/connections >80, critical loader failure, data staleness >24h. Response SLA: 15 min.

**Health monitor Lambda:** Runs every 6h, checks loaders ran in 26h, data <24h old, database responsive. Metrics: `Algo/HealthMonitor/LoaderHealth`, `Algo/HealthMonitor/DataFreshness`.

**Frontend errors:** CloudWatch `/aws/frontend/algo-trading-dashboard` (format: {environment}/{userId}/{sessionId}). Search: `[level = ERROR] AND [environment = production]` or `[statusCode = 500] OR [statusCode = 503]`.

## Daily Operations

**Before market open:** (1) Check health (`curl https://api.example.com/api/health` → status=healthy), (2) Check overnight loaders (price_daily, sector_ranking @ 4 AM ET), (3) Check overnight errors (CloudWatch logs), (4) Verify yesterday's trades executed (`/api/algo/trades`).

**During market hours:** Every 2h quick health check. On errors: read alert email, check CloudWatch logs, check health status. If dashboard slow: check RDS CPU and API Lambda duration (CloudWatch metrics).

---

### End of Day (After Market Close)

1. **Verify EOD orchestrator ran**
   - Check API at 5:30 PM ET + 5 min
   - `/api/algo/last-run` should show recent execution
   - Check CloudWatch logs: `/aws/lambda/algo-algo-dev`

2. **Review daily P&L**
   - `/api/algo/performance` for day's returns
   - `/api/algo/trades` to confirm all trades executed

3. **Check EOD loaders**
   - Most loaders run at 4 AM ET (after hours)
   - They should show in data_loader_status table
   - AWS Console → RDS Query Editor: `SELECT * FROM data_loader_status ORDER BY last_execution_time DESC LIMIT 20;`

---

## Responding to Alerts

### Alert: "API Lambda Errors (5+ in 5 min)"

**What it means:** API endpoints are throwing errors

**Quick diagnosis:**
```bash
# Check health endpoint
curl https://api.example.com/api/health

# If shows database issue:
# → Database down or unresponsive

# If shows normal:
# → Check specific endpoint that's failing
curl https://api.example.com/api/algo/trades
```

**Common causes & fixes:**
1. **Database connection pool exhausted**
   - See RDS connections in CloudWatch (should be <80)
   - If >80: Too many concurrent requests, scale up RDS or reduce Lambda concurrency
   
2. **Query timeout** (504 Gateway Timeout)
   - Some query is taking >30s
   - Check CloudWatch Logs for slow query
   - May need database optimization or index

3. **Database down**
   - Check AWS Console → RDS → Instances
   - Verify it shows "Available" status
   - If restarting, will take 2-3 minutes

**Recovery steps:**
1. Check `/api/health` → see what's failing
2. Check CloudWatch logs for error details
3. If database issue: wait 5 minutes and re-test
4. If specific endpoint: redeploy Lambda
5. If still failing: restart RDS instance (brief downtime)

---

### Alert: "Algo Lambda Errors"

**What it means:** The orchestrator (trade execution) is failing

**Immediate action:** Check if trades are stuck

```bash
# Check last orchestrator run
curl https://api.example.com/api/algo/last-run

# If shows ERROR status:
# → Orchestrator failed, trades may not have executed

# Check if orders are pending
curl https://api.example.com/api/algo/trades \
  | jq '.items[] | select(.status=="pending")'
```

**If there are pending orders:**
1. Check age: Orders pending >2 hours are automatically cancelled by position monitor (fail-closed: stuck orders block exit logic)
2. For orders <2 hours old: Likely transient API issue, orchestrator will retry on next run
3. Check CloudWatch logs: `/aws/lambda/algo-algo-dev` for error pattern
4. If same orders keep failing: May need manual investigation of Alpaca order status

**Auto-cancel behavior (stale order detection):**
- **>1 hour pending:** Logged as alert, no action yet
- **>2 hours pending (120m default, configurable):** Automatically cancelled (in DB + on Alpaca if possible)
- **Halted symbols:** Exempted from auto-cancel (halts naturally keep orders pending)
- **Audit trail:** Every cancellation logged to `algo_audit_log` with action type `STALE_ORDER_AUTO_CANCELLED`

**Configuration:**
- `stale_order_alert_minutes` (default: 60) - threshold to log alert
- `stale_order_auto_cancel_minutes` (default: 120) - threshold to auto-cancel

**If no orders pending:**
1. Orchestrator will retry next scheduled run (1 PM, 3 PM, 5:30 PM ET)
2. Monitor `/api/algo/last-run` for next execution
3. Check logs for error pattern

---

### Alert: "Critical Loader Failed (price_daily, sector_ranking, etc.)"

**What it means:** Data pipeline broke, market data may be stale

**Immediate action:** Prevent stale data from being used

```bash
# Check data freshness
curl https://api.example.com/api/health | jq '.checks.critical_data'

# If shows stale tables:
# → Stop trading until data is fresh (if data is >24h old)
```

**For non-critical loaders (analyst ratings, insider trades):**
- Low impact, can wait until next scheduled run
- Monitor but no emergency action needed

**For critical loaders (price_daily, sector_ranking):**
- High impact on trade signals
- If data >24h old: **PAUSE TRADING** until fixed
- Check loader logs to find error
- May need to:
  - Verify data source is available (API down? Missing credentials?)
  - Re-run loader manually
  - Restart ECS task

**Restart failed loader:**
```bash
# In AWS Console → ECS → Task Definitions → [loader-name]
# Click "Run new task"
# Select cluster and launch
# Wait for task to complete
# Check CloudWatch logs
```

---

### Alert: "Data Stale (table >24h old)"

**What it means:** A data table hasn't been updated in >24 hours

**Impact by table:**
- `price_daily` → CRITICAL (stop trading)
- `sector_ranking` → CRITICAL (stop trading)
- `buy_sell_daily` → HIGH (signals may be wrong)
- `technical_data_daily` → MEDIUM (quality degradation)
- `analyst_ratings` → LOW (affects symbol filtering only)

**Response:**
1. **For CRITICAL tables:** Pause auto-trading immediately
2. Check which loader is responsible (from alert message)
3. Check loader's last execution: Did it fail? When did it last succeed?
4. If loader crashed: Restart it (see "Restart failed loader" above)
5. If data source is down: Wait and retry in 30 min
6. Resume trading when data is fresh

---

### Alert: "RDS CPU >80% / Connections >80"

**What it means:** Database is under heavy load

**Immediate action:**
```bash
# Check what's using connections
SELECT * FROM pg_stat_activity WHERE state != 'idle';

# Kill any stuck queries (if safe)
SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
WHERE state = 'idle for long time';
```

**If CPU consistently high:**
- Reduce Lambda concurrency (scale down auto-scaling)
- Add database indexes for slow queries
- Consider upgrading RDS instance size

**If connections consistently near max (80):**
- Reduce API Lambda concurrency
- Add connection pooling (check current pool size)
- Upgrade RDS connection limit

---

## Maintenance Tasks

### Weekly (Every Monday)

1. **Review error trends**
   - CloudWatch Insights: Look for repeating error patterns
   - Check if same errors appear multiple times
   - File tickets for recurring issues

2. **Database maintenance**
   - Check VACUUM/ANALYZE ran (should be automatic)
   - Verify no unused indexes consuming space
   - Check slow query log

3. **Verify backup integrity**
   - AWS Console → RDS → Automated backups
   - Verify daily backups exist for past 7 days
   - Test restore from backup (in dev environment)

---

### Monthly (First Monday)

1. **Capacity planning**
   - Review RDS CPU/memory trends
   - Check API Lambda duration trends
   - Plan upgrades if approaching limits

2. **Security audit**
   - Check AWS Secrets Manager - credentials still valid?
   - Review IAM permissions - any unnecessary access?
   - Check CloudWatch Logs retention - set to 90 days

3. **Data cleanup**
   - Archive old trades/positions (>1 year)
   - Vacuum database (VACUUM ANALYZE)
   - Remove old CloudWatch logs

---

### Quarterly (Every 3 Months)

1. **Full system test**
   - Test each API endpoint manually
   - Verify all loaders can run and complete
   - Verify trades execute end-to-end
   - Check alerts are actually being sent

2. **Disaster recovery drill**
   - Restore database from backup
   - Verify data integrity
   - Estimate RTO/RPO (recovery time/point objectives)

3. **Update operational runbook**
   - Document any new endpoints or changes
   - Update alert response procedures if things changed
   - Remove obsolete procedures

---

## Key Contacts & Escalation

**System Owner:** [Your email]  
**On-Call Rotation:** [Link to on-call schedule]  
**Alert Email:** [alert_email_to from Terraform]  
**Slack Channel:** #algo-operations

**Escalation Path:**
1. Check `/api/health` (might be self-healing)
2. Check CloudWatch logs (find root cause)
3. Try quick fix (restart, redeploy)
4. If still failing after 15 min: Page on-call
5. If trading is paused: Notify risk management

---

## Troubleshooting Decision Tree

```
System Alert Received
  ↓
Is /api/health showing healthy?
  ├─ YES → False alarm or transient, re-check in 5 min
  └─ NO → Continue
      ↓
  Which component is unhealthy?
  ├─ Database → Check RDS CloudWatch metrics
  │           → If down: Wait or restart
  │           → If slow: Check connections/CPU
  ├─ Loaders → Check which loader failed
  │           → Check loader's CloudWatch logs
  │           → Restart loader or check data source
  ├─ Data freshness → Which table? (check alert)
  │                  → When did it last update?
  │                  → Restart responsible loader
  └─ API errors → Check specific endpoint error logs
                 → Database issue? Connection pool?
                 → Redeploy Lambda or restart RDS
```

---

## CloudWatch Queries Reference

**Find all errors from last hour:**
```
fields @timestamp, @message, component, operation
| filter @message like /ERROR/
| stats count() by component
```

**Find slow API requests:**
```
fields @duration
| filter @duration > 5000
| stats avg(@duration), max(@duration) by @logStream
```

**Find database connection errors:**
```
fields @message
| filter @message like /connection/i
| stats count() by @message
```

**Find all failed loaders:**
```
fields loader_name, status, error_message
| filter status = "FAILED"
| stats count() by loader_name
```

---

## Key Metrics to Monitor

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| API latency (p95) | <500ms | 500-2000ms | >2000ms |
| RDS CPU | <30% | 30-80% | >80% |
| RDS connections | <40 | 40-80 | >80 |
| RDS free memory | >1GB | 256MB-1GB | <256MB |
| Loader success rate | 100% | 90-99% | <90% |
| Data freshness | <6h | 6-24h | >24h |
| Unhandled errors/hour | 0 | 1-5 | >5 |

---

## Links

- **AWS Console:** https://console.aws.amazon.com
- **CloudWatch Logs:** https://console.aws.amazon.com/logs
- **RDS Monitoring:** https://console.aws.amazon.com/rds → Monitoring
- **API Health:** https://api.example.com/api/health
- **API Health (detailed):** https://api.example.com/api/health/detailed (requires auth)
- **API Health (data):** https://api.example.com/api/health/pipeline (requires auth)
