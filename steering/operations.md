# Operational Runbook & Monitoring Guide

**Last Updated:** 2026-06-14  
**Owner:** Platform Operations  
**Purpose:** Complete guide to monitoring system health and responding to alerts

---

## Quick Start: System Health Status

Everything you need to know in one place:

```bash
# Check system health instantly
curl https://api.example.com/api/health

# Output shows:
# - Database connectivity + latency
# - Last successful loader run
# - Data freshness (all <24h old?)
# - Any stale or failed loaders
# - Overall status: healthy/degraded/unhealthy
```

**HTTP Codes:**
- `200 healthy` → All systems working, data fresh
- `200 degraded` → Some loaders failing or data slightly stale, but system running
- `503 unhealthy` → Critical component down or data very stale (>24h)

---

## Monitoring Architecture

### Layer 1: Real-Time Alerts (SNS Email)

**What triggers alerts:**
- API Lambda errors (5+ in 5 min)
- Algo Lambda errors (any error)
- API Gateway 5xx errors (5+ in 5 min)
- RDS CPU >80%, memory <256MB, connections >80
- Any critical loader failure
- Data staleness >24h

**What you get:** Email to `alert_email_to` (configured in Terraform)

**Response SLA:** 15 minutes (during business hours)

---

### Layer 2: Hourly Health Check (Lambda)

**Lambda Function:** `algo-health-monitor` (runs every 6 hours)

**Checks:**
1. All critical loaders ran in last 26 hours
2. All critical data tables have fresh data (<24h old)
3. Database is responsive
4. No cascading failures

**Output:**
- CloudWatch metric `Algo/HealthMonitor/LoaderHealth` (0=healthy, 1=degraded, 2=unhealthy)
- CloudWatch metric `Algo/HealthMonitor/DataFreshness` (0=healthy, 1=degraded, 2=unhealthy)
- SNS alert if status changes to degraded/unhealthy

**View results:** CloudWatch → Log Groups → `/aws/lambda/algo-health-monitor`

---

### Layer 3: On-Demand Health Check (API)

**Endpoint:** `GET /api/health` (public, no auth required)

**What it shows:**
```json
{
  "status": "healthy",
  "timestamp": "2026-06-14T12:00:00Z",
  "checks": {
    "database": {"status": "ok", "latency_ms": 45},
    "loaders": {
      "status": "ok",
      "last_run": "2026-06-14T04:05:00Z",
      "recent_failures": 0,
      "stale_loaders": []
    },
    "critical_data": {
      "status": "ok",
      "stale_tables": []
    }
  },
  "alerts": []
}
```

**Use when:** You want to verify system is healthy before running trades

---

### Layer 4: Frontend Error Tracking (CloudWatch Logs)

**Log Group:** `/aws/frontend/algo-trading-dashboard`

**What gets logged:**
- React component errors (rendering, lifecycle)
- API call failures (with response status, endpoint, message)
- Network errors
- Uncaught promise rejections
- Browser console errors

**Log Stream Format:** `{environment}/{userId}/{sessionId}`

**Search for errors:**
```
# Find all errors from production
[level = ERROR] AND [environment = production]

# Find all API 500 errors
[statusCode = 500] OR [statusCode = 503]

# Find errors for specific user
[userId = "user@example.com"]
```

**Respond to:** Check browser console first, then CloudWatch logs to understand context

---

## Daily Operations Checklist

### Start of Day (Before Market Open)

1. **Check health status**
   ```bash
   curl https://api.example.com/api/health
   ```
   Should show `"status": "healthy"`

2. **Check overnight loaders ran**
   - price_daily (runs at 4 AM ET)
   - sector_ranking (runs at 4 AM ET)
   Should be in `last_load_time` from API

3. **Check for overnight errors**
   - CloudWatch Logs: `/aws/frontend/algo-trading-dashboard`
   - CloudWatch Logs: `/aws/lambda/algo-api-dev`
   - Look for errors after market close yesterday through now

4. **Verify recent trades**
   - Check `/api/algo/trades` to see if yesterday's trades executed
   - If no trades, check `/api/algo/preview` to verify signals ran

---

### During Market Hours

1. **Every 2 hours:** Quick health check
   ```bash
   curl https://api.example.com/api/health | jq .status
   ```

2. **If any error notifications arrive:**
   - Read email alert first (it tells you what to look for)
   - Check relevant CloudWatch logs (endpoint in email)
   - Check API health status
   - Contact support if unclear

3. **If dashboard is slow:**
   - Check RDS CPU (CloudWatch → Metrics → AWS/RDS)
   - Check API Lambda duration (CloudWatch → Metrics → AWS/Lambda)
   - If API >10s, restart the Lambda (redeploy or manual restart)

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
1. **Do NOT manually cancel** - may cause issues with reconciliation
2. Check CloudWatch logs: `/aws/lambda/algo-algo-dev`
3. Find error message and root cause
4. Contact support with error details

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
- `analyst_ratings` → LOW (just affects filtering)

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
