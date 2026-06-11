# Metrics Loaders — Full Implementation Guide

## Overview

This guide covers the complete implementation of hourly performance and risk metrics loaders. The solution reduces dashboard load time from 2-5 seconds to <100ms by pre-calculating expensive metrics and caching them in RDS tables.

**Timeline:** ~2 hours total (1h setup + 1h testing)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ EventBridge (Hourly 10 AM - 4 PM ET, EOD 5 PM)              │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Performance      │  │ Risk Metrics     │                │
│  │ Metrics Loader   │  │ Loader           │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
└───────────┼──────────────────────┼──────────────────────────┘
            │                      │
            ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│ RDS PostgreSQL (Algo Database)                              │
│                                                              │
│  algo_trades              ◄────────┐                        │
│  algo_portfolio_snapshots ◄────────┤                        │
│  price_daily              ◄────────┤                        │
│  economic_data            ◄────────┤                        │
│                                    │                        │
│  ┌──────────────────────────────────┘                      │
│  │                                                          │
│  ▼                                                          │
│  algo_performance_daily ──────┐                             │
│  algo_risk_daily ─────────────┤                             │
└──────────────────────────────┼─────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Dashboard           │
                    │  (fetch_perf_        │
                    │   analytics,         │
                    │   fetch_risk_        │
                    │   metrics)           │
                    │                      │
                    │  Load: <100ms        │
                    │  (table lookup only) │
                    └──────────────────────┘
```

---

## Step 1: Create RDS Tables (5 minutes)

### Option A: Run SQL Script (Recommended)

```bash
# From project root
psql -h $DB_HOST -U $DB_USER -d $DB_NAME < sql/001_create_metrics_tables.sql

# Verify tables created
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\d algo_performance_daily; \d algo_risk_daily;"
```

### Option B: Manual SQL (Alternative)

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

Then paste contents of `sql/001_create_metrics_tables.sql` and run.

### Expected Output

```
                        Table "public.algo_performance_daily"
     Column      │           Type           │ Collation │ Nullable │ Default
─────────────────┼──────────────────────────┼───────────┼──────────┼─────────
 report_date     │ date                     │           │ not null │
 rolling_sharpe_252d │ double precision     │           │          │
 rolling_sortino_252d │ double precision    │           │          │
 calmar_ratio    │ double precision         │           │          │
 ...
 updated_at      │ timestamp with time zone │           │ not null │ now()

Indexes:
    "algo_performance_daily_pkey" PRIMARY KEY, btree (report_date)
    "idx_perf_date_desc" btree (report_date DESC)
    "idx_perf_updated_at" btree (updated_at DESC)
```

---

## Step 2: Test Loaders Locally (10 minutes)

### Verify Imports

```bash
cd /path/to/algo
python3 -c "from loaders.load_algo_performance_daily import AlgoPerformanceDailyLoader; print('✓ Import OK')"
python3 -c "from loaders.load_algo_risk_daily import AlgoRiskDailyLoader; print('✓ Import OK')"
```

### Run Loaders Manually

**During market hours (10 AM - 4 PM ET):**

```bash
# Terminal 1: Performance metrics
python3 loaders/load_algo_performance_daily.py
# Expected: "SUCCESS: 1 performance metrics computed"

# Terminal 2: Risk metrics
python3 loaders/load_algo_risk_daily.py
# Expected: "SUCCESS: 1 risk metrics computed"
```

**Check tables populated:**

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << EOF
SELECT report_date, updated_at, 
       rolling_sharpe_252d, expectancy, max_drawdown_pct
FROM algo_performance_daily
WHERE report_date = CURRENT_DATE
ORDER BY report_date DESC LIMIT 1;

SELECT report_date, updated_at,
       var_pct_95, portfolio_beta, top_5_concentration
FROM algo_risk_daily
WHERE report_date = CURRENT_DATE
ORDER BY report_date DESC LIMIT 1;
EOF
```

**Expected Output:**

```
 report_date | updated_at          | rolling_sharpe_252d | expectancy | max_drawdown_pct
─────────────┼─────────────────────┼─────────────────────┼────────────┼──────────────────
 2026-06-10  | 2026-06-10 14:30:00 │               1.234 │       0.45 │             8.23
(1 row)
```

---

## Step 3: Schedule Loaders in EventBridge (30 minutes)

### Option A: AWS Console (Manual)

**1. Create Performance Metrics Rule**

1. Go to AWS EventBridge → Rules
2. Click "Create rule"
3. Name: `metrics-loaders-performance-hourly`
4. Pattern: Scheduled (cron)
5. Cron expression: `0 10-16 ? * MON-FRI *`  (10 AM - 4 PM ET)
6. Timezone: America/New_York
7. Click Next
8. Target: ECS task
   - Cluster: your ECS cluster
   - Task definition: metrics-loader (or create new)
   - Launch type: FARGATE
   - Subnets: your VPC subnets
   - Security groups: your security groups
   - Command: `python loaders/load_algo_performance_daily.py`
9. Click Next, Review, Create

**2. Create Risk Metrics Rule** (Same as above, but command = `python loaders/load_algo_risk_daily.py`)

**3. Create EOD Rules** (Optional, recommended)

Cron: `0 21 ? * MON-FRI *` (5 PM ET)
Targets: Same as above

### Option B: AWS CLI

```bash
# Substitute your values:
CLUSTER_ARN="arn:aws:ecs:us-east-1:123456789:cluster/your-cluster"
SUBNET="subnet-xxxxx"
SECGROUP="sg-xxxxx"
ROLE_ARN="arn:aws:iam::123456789:role/ecsTaskExecutionRole"

# Performance metrics hourly
aws events put-rule \
  --name metrics-loaders-performance-hourly \
  --schedule-expression "cron(0 10-16 ? * MON-FRI *)" \
  --state ENABLED \
  --region us-east-1

aws events put-targets \
  --rule metrics-loaders-performance-hourly \
  --targets \
    "Id"="1",\
    "Arn"="$CLUSTER_ARN",\
    "RoleArn"="$ROLE_ARN",\
    "EcsParameters"="{LaunchType=FARGATE,TaskDefinitionArn=arn:aws:ecs:us-east-1:123456789:task-definition/metrics-loader:1,NetworkConfiguration={awsvpcConfiguration={Subnets=[$SUBNET],SecurityGroups=[$SECGROUP]}}}" \
  --region us-east-1
```

### Verify EventBridge Rules Created

```bash
aws events list-rules \
  --name-prefix metrics-loaders \
  --region us-east-1
```

Expected: See both `metrics-loaders-performance-hourly` and `metrics-loaders-risk-hourly` in ENABLED state.

---

## Step 4: Test Dashboard Integration (15 minutes)

### During Market Hours (10 AM - 4 PM ET Mon-Fri)

**1. Load Dashboard**

```bash
curl -s http://localhost:3000/api/dashboard | jq '.perf_anl'
```

**Expected Response:**

```json
{
  "sharpe252": 1.234,
  "sortino": 0.956,
  "calmar": 2.456,
  "wr50": 52.5,
  "avg_w_r": 1.45,
  "avg_l_r": 0.95,
  "expectancy": 0.45,
  "maxdd": 8.23,
  "_source": "table"
}
```

**Check for `_source: "table"`** — confirms metrics are from cache, not calculated on-the-fly.

**2. Check Metrics Age**

```sql
SELECT 
  report_date,
  updated_at,
  EXTRACT(EPOCH FROM NOW() - updated_at) / 60 AS age_minutes,
  rolling_sharpe_252d,
  rolling_sortino_252d,
  calmar_ratio
FROM algo_performance_daily
WHERE report_date = CURRENT_DATE
ORDER BY report_date DESC LIMIT 1;
```

**Age should be <60 minutes** (freshly calculated by loader).

**3. Test Stale Data Handling**

```sql
-- Manually set metrics as stale (>2 hours old)
UPDATE algo_performance_daily 
SET updated_at = NOW() - INTERVAL '3 hours'
WHERE report_date = CURRENT_DATE;
```

```bash
# Reload dashboard
curl -s http://localhost:3000/api/dashboard | jq '.perf_anl'
```

**Expected:** `_unavailable: true` or empty dict (dashboard skips stale data)

Check logs: `grep "fetch_perf_analytics" logs/dashboard.log`
Expected: `"table data stale"` warning

---

## Step 5: Set Up Monitoring (10 minutes)

### CloudWatch Dashboards

Create a custom dashboard to monitor loader health:

```bash
aws cloudwatch put-dashboard \
  --dashboard-name MetricsLoaders \
  --dashboard-body file://config/cloudwatch-dashboard-metrics.json
```

### CloudWatch Alarms

Deploy alarms to alert on:
- Loader task failures
- Metrics table age >2 hours (during market hours)
- Dashboard metric cache misses

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name metrics-loader-failure \
  --alarm-description "Alert if metrics loaders fail" \
  --metric-name TasksFailed \
  --namespace ECS/ContainerInsights \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions arn:aws:sns:us-east-1:YOUR-ACCOUNT:ops-alerts
```

### Manual Health Check

```bash
# Run during market hours
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << EOF
-- Should show rows updated recently
SELECT report_date, updated_at, 
       EXTRACT(EPOCH FROM NOW() - updated_at) / 60 AS age_minutes
FROM algo_performance_daily
WHERE report_date = CURRENT_DATE;

SELECT report_date, updated_at,
       EXTRACT(EPOCH FROM NOW() - updated_at) / 60 AS age_minutes
FROM algo_risk_daily
WHERE report_date = CURRENT_DATE;
EOF
```

**If age_minutes > 120 during market hours:**
1. Check CloudWatch logs: `aws logs tail /ecs/metrics-loader --follow`
2. Check if EventBridge rule is enabled: `aws events describe-rule --name metrics-loaders-performance-hourly`
3. Manually trigger loader: `python loaders/load_algo_performance_daily.py`

---

## Troubleshooting

### Loaders Fail to Run

**Check EventBridge rule:**
```bash
aws events describe-rule --name metrics-loaders-performance-hourly
# Should show: State = ENABLED
```

**Check ECS task definition:**
```bash
aws ecs describe-task-definition --task-definition metrics-loader
# Verify: container command = ["python", "loaders/load_algo_performance_daily.py"]
```

**Check CloudWatch logs:**
```bash
aws logs tail /ecs/metrics-loader --follow
# Look for: ERROR in logs = task failed
```

**Manually trigger:**
```bash
python loaders/load_algo_performance_daily.py
# Should print: "SUCCESS: 1 performance metrics computed"
```

### Dashboard Shows "--" for Metrics

**Possible causes:**
1. Loaders haven't run yet (first run after deployment)
2. Table data is >2 hours old (loader failed/didn't run)
3. Dashboard freshness check is rejecting the data

**Diagnosis:**
```sql
-- Check if table has data
SELECT COUNT(*) FROM algo_performance_daily WHERE report_date = CURRENT_DATE;
-- Should be 1+

-- Check freshness
SELECT updated_at, 
       EXTRACT(EPOCH FROM NOW() - updated_at) / 60 AS age_minutes
FROM algo_performance_daily
WHERE report_date = CURRENT_DATE
ORDER BY updated_at DESC LIMIT 1;
-- age_minutes should be <120 (2 hours)
```

**If table is empty:**
1. Loaders haven't run yet → wait for top of hour (10 AM, 11 AM, etc)
2. Or manually trigger: `python loaders/load_algo_performance_daily.py`

**If age > 120:**
1. Loaders failed → check CloudWatch logs
2. Fix the issue, then manually trigger loaders

### Metrics Don't Match Historical Values

**Possible causes:**
1. Calculation logic differs between loader and dashboard
2. Source data changed (trades added/removed)
3. Rounding precision different

**Verification:**
```bash
# Compare calculations
python3 << EOF
from loaders.load_algo_performance_daily import AlgoPerformanceDailyLoader
loader = AlgoPerformanceDailyLoader()
# ... inspect calculation logic
EOF
```

Review git commit for calculation changes, compare with dashboard.py.

---

## Performance Tuning

### If Loaders Run Slow (>5 minutes)

1. **Add database indexes:**
```sql
CREATE INDEX idx_trades_status_date ON algo_trades(status, exit_date DESC);
CREATE INDEX idx_snapshots_date ON algo_portfolio_snapshots(snapshot_date DESC);
```

2. **Check query plans:**
```sql
EXPLAIN ANALYZE SELECT ... FROM algo_trades WHERE status = 'closed' ...
```

3. **Consider sampling:** Only use last 500 trades instead of all for Sharpe calculation.

### If Dashboard Still Slow

1. **Check other fetchers:** Dashboard may have bottleneck elsewhere
2. **Add Redis cache:** Cache table lookups for 5 minutes
3. **Use read replicas:** Route `fetch_perf_analytics` to RDS read replica

---

## Success Criteria

- [x] RDS tables created
- [x] Loaders run successfully locally
- [ ] EventBridge rules created and enabled
- [ ] Dashboard shows metrics (not "--") during market hours
- [ ] Metrics show `_source: "table"`
- [ ] No errors in CloudWatch logs for 24+ hours
- [ ] Alarms functional (test by manually setting stale time)
- [ ] Performance: Dashboard load <100ms (check browser DevTools)

---

## Files Created

- ✅ `loaders/load_algo_performance_daily.py` — Performance metrics calculation
- ✅ `loaders/load_algo_risk_daily.py` — Risk metrics calculation
- ✅ `tools/dashboard/dashboard.py` — Updated fetch functions
- ✅ `sql/001_create_metrics_tables.sql` — RDS schema
- ✅ `scripts/deploy-metrics-loaders.py` — Automated deployment helper
- ✅ `steering/performance-risk-metrics-loader.md` — Complete reference
- ✅ `IMPLEMENTATION_GUIDE.md` — This file

---

## Rollback

If something breaks:

```bash
# 1. Disable EventBridge rules
aws events disable-rule --name metrics-loaders-performance-hourly
aws events disable-rule --name metrics-loaders-risk-hourly

# 2. Dashboard reverts to showing "--" for metrics (safe fallback)

# 3. Investigate logs
aws logs tail /ecs/metrics-loader --follow

# 4. Fix issue, then re-enable
aws events enable-rule --name metrics-loaders-performance-hourly
aws events enable-rule --name metrics-loaders-risk-hourly
```

---

## Next: Optimization

After deployment is stable (24+ hours), consider:

1. **Reduce to 30-minute intervals** if hourly feels stale
2. **Add real-time trigger** on trade close for intraday metrics
3. **Extend to economic indicators** (yield curves, CPI using same pattern)
4. **Add multi-day cache** (keep metrics for last 7 days for trend analysis)
5. **Implement circuit breaker** metrics (pre-computed by loaders, not recalculated in dashboard)

See `DEPLOYMENT_CHECKLIST_METRICS.md` for next phase tasks.

---

**Status:** Ready for production deployment
