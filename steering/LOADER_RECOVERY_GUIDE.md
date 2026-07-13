# Loader Recovery Guide

**Quick Fix:** Data is stale when prices are > 30 minutes old during trading hours.

---

## Quick Diagnosis

```bash
# Check data staleness
python scripts/monitor_data_staleness.py

# Look for 💀 (DEAD) status on: price_daily, technical_data_daily, algo_signals
```

---

## Why Loaders Are Stale

**Root Cause:** EventBridge Scheduler only runs MON-FRI.

| Schedule | Time ET | Days | Status |
|----------|---------|------|--------|
| Morning | 2:00 AM | MON-FRI | ENABLED |
| EOD | 4:05 PM | MON-FRI | ENABLED |

**Today is Sunday → Loaders won't run until Monday 2 AM.**

---

## Fix #1: Manual Refresh (Quick - 2 min)

### Option A: Local Dev (Recommended)

```bash
# Refresh prices + technical data (morning pipeline)
python scripts/run_local_orchestrator.py --morning

# Expected output:
# ✅ Phase 1: Symbols... OK (0.1s)
# ✅ Phase 2: Prices... OK (5.2s)
# ✅ Phase 3: Technical... OK (3.1s)
# ...
# ✅ Phase 9: Signals... OK (1.2s)
# Total: 12.6s, 10 signals generated
```

### Option B: AWS Lambda (Production)

```bash
# Check scheduler status
aws scheduler list-schedules \
  --query 'Schedules[?contains(Name, `pipeline`)]' \
  --region us-east-1

# Expected: state=ENABLED for both morning-pipeline and eod-pipeline

# Manually trigger morning pipeline
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:algo-morning-pipeline" \
  --name "manual-refresh-$(date +%s)" \
  --region us-east-1

# Monitor execution
aws stepfunctions describe-execution \
  --execution-arn "arn:aws:states:us-east-1:ACCOUNT_ID:execution:algo-morning-pipeline:manual-refresh-xyz" \
  --region us-east-1 --query 'status'
# Expected: RUNNING → SUCCEEDED (5-10 min)
```

---

## Fix #2: If Loaders Keep Failing

### Check Logs

```bash
# Check Step Functions execution logs
aws stepfunctions describe-execution \
  --execution-arn "arn:..." \
  --region us-east-1

# Check ECS task logs for specific phases
aws logs get-log-events \
  --log-group-name /ecs/algo-cluster \
  --log-stream-name algo-morning-pipeline/price-loader/xxxx \
  --region us-east-1 \
  --limit 50
```

### Common Failures

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `price_loader: timeout (300s)` | yfinance rate-limited | Reduce batch_size in algo_config (default 1000 → 500) |
| `quality_metrics: 70% coverage` | SEC filings unavailable | Expected for ~13% of stocks (micro-caps) - acceptable |
| `Connection refused (RDS)` | Lambda not in VPC or SG misconfigured | Run: `bash scripts/fix-lambda-vpc.sh` |
| `Step Functions: NO_STATE_MACHINE` | EventBridge not triggering | Verify EventBridge rule exists and is ENABLED |

### Fix Low Coverage (if < 70%)

```sql
-- Increase timeout for metric loaders
UPDATE algo_config
SET value = '900'  -- 15 minutes
WHERE key = 'loader_timeout_seconds' AND loader_name = 'quality_metrics';

-- Reduce batch size to avoid rate limits
UPDATE algo_config
SET value = '50'  -- was 100
WHERE key = 'batch_size_override' AND loader_name = 'quality_metrics';
```

---

## Fix #3: If EventBridge Never Triggers

### Enable Schedules (if disabled)

```bash
# List all schedules
aws scheduler list-schedules --region us-east-1

# If morning-pipeline state=DISABLED:
aws scheduler update-schedule \
  --name algo-morning-pipeline \
  --state ENABLED \
  --region us-east-1

# Verify
aws scheduler get-schedule \
  --name algo-morning-pipeline \
  --region us-east-1 --query 'State'
# Expected: ENABLED
```

### Verify IAM Permissions

EventBridge Scheduler needs:
- `stepfunctions:StartExecution` on the state machine
- `iam:PassRole` on the scheduler role

```bash
# Check the scheduler role policy
aws iam get-role-policy \
  --role-name algo-eventbridge-scheduler-role \
  --policy-name algo-stepfunctions-invoke
```

---

## Fix #4: If Data Stays Stale (Deep Dive)

### Check Data Loader Status Table

```sql
-- See what's actually running/failed
SELECT 
  table_name,
  last_updated,
  completion_pct,
  reason
FROM data_loader_status
ORDER BY last_updated DESC
LIMIT 15;

-- Expected: all tables have completion_pct = 100
-- If not, see reason field for error details
```

### Check for Stuck Loaders

```sql
-- Some loaders may be stuck in RUNNING state
SELECT 
  loader_name,
  status,
  started_at,
  EXTRACT(EPOCH FROM (NOW() - started_at)) / 60 as running_mins
FROM loader_execution_status
WHERE status = 'RUNNING' AND started_at < NOW() - INTERVAL '30 minutes'
ORDER BY started_at;

-- Force reset (careful - only if truly stuck)
UPDATE loader_execution_status
SET status = 'FAILED', reason = 'Force reset - stuck >30min'
WHERE loader_name = 'quality_metrics' AND status = 'RUNNING';
```

### Restart From Scratch

```bash
# This forces a full reload from source APIs (slow, expensive)
# Use only if data is corrupted

# Backfill last 5 days of prices
python scripts/run_local_orchestrator.py --backfill-days 5

# Or manually via AWS:
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:xxx:stateMachine:algo-backfill-pipeline" \
  --input '{"backfill_days": 5}' \
  --region us-east-1
```

---

## Monitoring Setup (Prevent Future Issues)

### 1. CloudWatch Alarm for Stale Data

```bash
# Monitor price_daily table age
aws cloudwatch put-metric-alarm \
  --alarm-name "algo-stale-prices" \
  --alarm-description "Alert if prices are >60min old during trading hours" \
  --metric-name "DataStaleness" \
  --namespace "Algo/Data" \
  --statistic Average \
  --period 300 \
  --threshold 60 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "arn:aws:sns:us-east-1:xxx:ops-alerts" \
  --region us-east-1
```

### 2. Data Patrol Task (Every 5 min)

The system runs `scripts/data_patrol.py` every 5 minutes to check freshness.

```bash
# Verify it's running
aws ecs list-tasks \
  --cluster algo-cluster \
  --service-name algo-data-patrol \
  --region us-east-1

# View logs
aws logs tail /ecs/algo-cluster --filter-pattern "data-patrol" --follow
```

### 3. Dashboard Staleness Indicator

Dashboard shows data freshness on the main panel:
- 🟢 **GREEN**: All loaders fresh
- 🟡 **YELLOW**: 1+ loaders stale (>threshold but <2× threshold)
- 🔴 **RED**: 1+ loaders critical (>2× threshold)

---

## Prevention Checklist

- [ ] EventBridge Scheduler ENABLED (`aws scheduler list-schedules`)
- [ ] State machine roles have `stepfunctions:StartExecution` permission
- [ ] RDS connection pool has capacity (check `pg_stat_activity` if failures occur)
- [ ] Alpaca API not rate-limited (yfinance may be the bottleneck, not Alpaca)
- [ ] CloudWatch alarms configured for critical data stales
- [ ] Data Patrol task running every 5 minutes
- [ ] Operator aware of MON-FRI schedule (weekends/holidays have no auto-run)

---

## Emergency: Force All Loaders NOW

```bash
# Local (quickest)
python scripts/run_local_orchestrator.py --run-all  # morning + afternoon + evening

# AWS (full pipeline)
for pipeline in morning eod; do
  aws stepfunctions start-execution \
    --state-machine-arn "arn:aws:states:us-east-1:xxx:stateMachine:algo-${pipeline}-pipeline" \
    --name "emergency-refresh-$(date +%s)" \
    --region us-east-1
done

# Monitor
watch -n 10 'python scripts/monitor_data_staleness.py'
```

---

## Questions?

See:
- `steering/DATA_LOADERS.md` — Loader architecture & timeouts
- `steering/OPERATIONS.md` — EventBridge & Lambda config
- `steering/COMMON_OPERATIONS.md` — Dashboard troubleshooting
- CloudWatch Logs: `/ecs/algo-cluster` (ECS tasks), `/aws/lambda/algo-*` (Lambda funcs)
