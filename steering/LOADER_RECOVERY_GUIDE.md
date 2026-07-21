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
# Refresh prices + technical data (actual data-refresh loaders)
python scripts/local_loader_scheduler.py --now morning

# Refresh quality/growth/value/scores/signals (EOD loaders)
python scripts/local_loader_scheduler.py --now metrics
```

**IMPORTANT (found + fixed 2026-07-20):** `scripts/run_local_orchestrator.py` does NOT
fetch fresh price/technical/fundamental data - it's the *trading* orchestrator (Phases
1-9: signal generation, risk gates, reconciliation) and only reads whatever is already
in the DB. Running it against stale data will not move `price_daily`/`technical_data_daily`
off their stale date - confirmed live (ran it, watched the max date stay unchanged).
`scripts/local_loader_scheduler.py` is the actual loader entry point (wraps
`loaders/load_prices.py`, `load_technical_indicators.py`, etc. - see
`steering/DATA_LOADERS.md`). This same confusion had been baked into the Windows Task
Scheduler config (`scripts/setup_windows_schedule.ps1` called the orchestrator, not the
loader scheduler) - both are now fixed. Run `run_local_orchestrator.py --morning`
afterward if you also want to exercise the trading/signal logic against the now-fresh
data.

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
| `Connection refused (RDS)` | Lambda not in VPC or SG misconfigured | Run: `python3 scripts/fix-lambda-vpc-config.py` |
| `Step Functions: NO_STATE_MACHINE` | EventBridge not triggering | Verify EventBridge rule exists and is ENABLED |

### Fix Low Coverage (if < 70%)

**Correction (2026-07-20):** the SQL below previously filtered on a `loader_name` column
and a `batch_size_override` key - `algo_config` is a flat key-value table (`key`, `value`,
`value_type`) with no per-loader scoping column, and `batch_size_override` isn't a real
config key (confirmed via `information_schema.columns` / a live `algo_config` query).
`loader_timeout_seconds` is real and global (applies to all loaders, not just one); use
`--parallelism` (see Fix #2 table above) to reduce per-loader load instead of a batch-size
config key that doesn't exist.

```sql
-- Increase the global loader timeout (applies to all loaders, not per-loader)
UPDATE algo_config
SET value = '900'  -- 15 minutes (was 7200s / 2h)
WHERE key = 'loader_timeout_seconds';
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
-- NOTE: the real table is loader_execution_history (loader_execution_status does not
-- exist - confirmed 2026-07-20, this doc previously referenced a nonexistent table).
SELECT 
  loader_name,
  status,
  execution_start,
  EXTRACT(EPOCH FROM (NOW() - execution_start)) / 60 as running_mins
FROM loader_execution_history
WHERE status = 'RUNNING' AND execution_start < NOW() - INTERVAL '30 minutes'
ORDER BY execution_start;

-- Force reset (careful - only if truly stuck)
UPDATE loader_execution_history
SET status = 'FAILED', error_message = 'Force reset - stuck >30min'
WHERE loader_name = 'quality_metrics' AND status = 'RUNNING';
```

Also check `loader_execution_locks` (advisory locks, separate from the history log above) -
a lock surviving past its `expires_at` with no corresponding running process is the other
common "stuck loader" symptom:

```sql
SELECT loader_name, locked_by, locked_at, expires_at
FROM loader_execution_locks
WHERE expires_at < NOW();
```

### Restart From Scratch

```bash
# Simplest full reload: re-run the actual loaders (watermark-based, so this is an
# incremental catch-up, not a hard reset - see steering/DATA_LOADERS.md #4).
python scripts/local_loader_scheduler.py --now morning
```

**Known gap (found 2026-07-20):** `loaders/load_prices.py`'s internal `run()` method
accepts a `backfill_days` parameter that forces re-fetching N days back regardless of the
per-symbol watermark, but nothing external wires it up - no CLI flag, no env var, and
`run_local_orchestrator.py` has no `--backfill-days` option (confirmed via its argparse
definitions). There's also no `algo-backfill-pipeline` state machine in Terraform. If you
need a true backfill (not just watermark catch-up), it currently requires calling
`PriceLoader.run(symbols, backfill_days=N)` directly from a Python shell, or deleting the
affected `loader_watermarks` rows so the next incremental run re-fetches from scratch.

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

**Correction (2026-07-20):** `scripts/data_patrol.py` does not exist - the real module is
`algo/algo_data_patrol.py`. The "every 5 min ECS service" claim below could not be
confirmed live: `/ecs/algo-data-patrol` only appears as a CloudWatch log-group retention
entry in `terraform/modules/lifecycle/main.tf`, plus a reference in
`terraform/errored.tfstate` (an errored/abandoned state file) - no evidence of an actual
running `algo-data-patrol` ECS service was found. The `algo_data_patrol` / `data_patrol_log`
DB tables are both empty locally, consistent with this never having run rather than having
run cleanly with nothing to report. Treat this section as aspirational until verified
against the real AWS account.

```bash
# Verify it's running (if it exists)
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
# Local (quickest) - `--run-all` on run_local_orchestrator.py runs the trading
# orchestrator's morning+afternoon+evening PHASES, it does not fetch data (same
# distinction as Fix #1 above). Use the loader scheduler to actually force loaders:
python scripts/local_loader_scheduler.py --now morning
python scripts/local_loader_scheduler.py --now metrics

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
