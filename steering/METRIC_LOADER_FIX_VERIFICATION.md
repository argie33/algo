# Metric Loader Parallelism Fix - Verification Guide

**Commit**: `8cf84ff90` — "fix: increase min parallelism for metric loaders to 2-4"
**Date**: 2026-06-30 22:30
**Status**: DEPLOYED

## What Was Fixed

The Computed Metrics Pipeline (7:00 PM ET) was failing to complete because metric loaders with parallelism=2 were taking 40+ minutes to fetch 5000+ symbols via yfinance. The stock_scores loader requires 70-85% coverage from upstream metrics before it can run. Incomplete metrics = null scores for OPI and others.

**Solution**: Increased min parallelism for slow loaders from 1-2 → 2-4

### Changes Applied

| Loader | Old Min | New Min | New Max | Old Expected Time | New Expected Time |
|--------|---------|---------|---------|---|---|
| positioning_metrics | 2 | 3 | 4 | 20-41 min | 13-28 min |
| value_metrics | 2 | 3 | 4 | 20-41 min | 13-28 min |
| growth_metrics | 1 | 2 | 3 | 30-60 min | 15-30 min |
| quality_metrics | 1 | 2 | 3 | 30-60 min | 15-30 min |
| stability_metrics | 1 | 2 | 3 | 20-40 min | 10-20 min |

**File Modified**: `utils/loaders/config.py`

## Verification Steps

### 1. Confirm Configuration Deployed

```bash
grep -A 2 "positioning_metrics" utils/loaders/config.py
# Should show: (3, 4) with comment "Increased from 2 to 3"

grep -A 2 "value_metrics" utils/loaders/config.py  
# Should show: (3, 4)
```

✓ **Expected Result**: Config shows min parallelism = 3 for positioning/value metrics

---

### 2. Monitor Metric Table Coverage (Real-Time)

Run this while pipelines are executing:

```bash
python3 scripts/monitor_pipeline_progress.py
```

This will show:
- Current loader status and progress %
- Metric table coverage (should be increasing)
- Whether stock_scores prerequisites are met

**Run every 30-60 seconds** to watch progress:

```bash
while true; do python3 scripts/monitor_pipeline_progress.py; sleep 30; done
```

✓ **Expected Progress**:
- T+0: positioning_metrics starts (parallelism=3-4)
- T+15 min: positioning_metrics complete (100%)
- T+20 min: value_metrics complete (100%)
- T+25 min: growth/quality metrics start
- T+40 min: all metrics > 70% coverage
- T+45 min: stock_scores starts
- T+50 min: stock_scores complete

---

### 3. Check OPI and Sample Stocks

After pipelines complete, verify factor scores populated:

```bash
python3 scripts/check_opi_scores.py
```

**Expected Output** for OPI:

```
Symbol     Composite    Momentum    Quality    Growth    Value    Positioning Stability  RS%   Status    Updated
OPI          75.5        68.3        72.1      71.2      84.5      65.2        70.1   0.0   OK        2026-06-30 19:45:32
AAPL         82.3        85.2        88.0      80.3      79.5      75.8        82.0   5.2   OK        2026-06-30 19:44:15
```

✗ **BAD** (what we're fixing):
```
Symbol     Composite    Momentum    Quality    Growth    Value    Positioning Stability  RS%   Status    Updated
OPI          --           100.0       --         --       100.0    --           --     0.0   NULL      2026-06-30
```

✓ **GOOD** (expected after fix):
- All factor scores populated (no `--`)
- Composite score ≥ 50
- Each factor has numeric value

---

### 4. Verify No Large Data Gaps

```bash
python3 scripts/verify_metric_loaders.py
```

**Expected Output**:
```
METRIC LOADER VERIFICATION
================================================
positioning_metrics
  ✓ OK
    Coverage: 98.5% (4925/5000 available)
    Updated today: 4925 rows
    Latest update: 2026-06-30 19:18:23

value_metrics
  ✓ OK
    Coverage: 99.2% (4960/5000 available)
    ...

quality_metrics
  ✓ OK
    Coverage: 87.3% (4365/5000 available)  ← OK if SEC data sparse
    ...

SUMMARY
✓ Tables with sufficient data: 5/5

✓ All metric loaders appear to be running successfully!
  OPI and other stocks should have proper factor scores.
```

✗ **Problem Indicators**:
- Coverage < 70% for positioning, value, or stability metrics
- Any table showing "✗ INCOMPLETE"
- "✗ ERROR" for any metric table

---

## If Verification Shows Issues

### Problem: Still have coverage < 70%

**Cause**: Pipelines still running or RDS saturation reducing parallelism

**Check**:
1. Time elapsed: Has it been < 50 min since 7:00 PM pipeline start?
2. RDS saturation: Check CloudWatch metric `DatabaseConnections` — is it > 85?

**Fix**:
1. Wait another 10-15 min for loaders to complete
2. If still < 70%, check CloudWatch logs for loader errors
3. If RDS > 85, next step is to reduce concurrent loaders or increase RDS Proxy capacity

### Problem: Quality/Growth metrics show 0% coverage

**Cause**: Financial Data Pipeline (4:05 PM) hasn't completed

**Check**:
```bash
# Check financial tables
sqlite3 << EOF
SELECT COUNT(*) as annual_income FROM annual_income_statement;
SELECT COUNT(*) as quarterly_income FROM quarterly_income_statement;
EOF
```

**Fix**:
- Financial pipeline should complete by 5:45 PM
- Computed Metrics Pipeline waits until 7:00 PM for financial data
- If financial tables empty, check financial_data_pipeline logs

### Problem: Parallelism still reduced to 1-2 despite config change

**Cause**: Adaptive parallelism reduction due to RDS saturation

**Check**:
```bash
# Grep logs for parallelism adjustments
grep "RDS Proxy saturation" /var/log/loaders/*.log
```

**Fix**:
1. Short-term: Wait for earlier loaders to finish (reduces RDS load)
2. Long-term: Increase RDS Proxy pool size from 100 → 150+ connections

---

## Success Criteria

✓ **All of these must be true**:

1. ✓ `positioning_metrics` shows min parallelism 3 in config.py
2. ✓ `value_metrics` shows min parallelism 3 in config.py  
3. ✓ All metric tables > 70% coverage (except quality/growth if SEC data sparse)
4. ✓ OPI stock_scores shows numeric values for all factors (no `--`)
5. ✓ No "✗ INCOMPLETE" in verify_metric_loaders.py output
6. ✓ Pipeline completes before 8:00 PM (< 1 hour from 7:00 PM start)

---

## Rollback (if needed)

If the fix causes other issues (e.g., RDS exhaustion):

```bash
# Revert to previous parallelism (min=2, max=3 for positioning/value)
git revert 8cf84ff90

# Re-deploy new config
python3 loaders/reload_config.py  # If this script exists
# OR restart loaders with: LOADER_PARALLELISM=2 
```

---

## Long-Term Solutions

If this fix isn't sufficient, next steps are:

1. **Incremental Loading**: Only load symbols that changed (saves time)
2. **Caching**: Pre-cache metrics from prior day, update asynchronously
3. **Separate Pipelines**: Run Financial + Computed Metrics on different ECS tasks
4. **RDS Proxy Scaling**: Increase pool size from 100 → 150+ connections
5. **Async Scoring**: Allow stock_scores to start with partial metrics, update as they arrive

---

## Monitoring Dashboard

For continuous monitoring, use:

```bash
# Watch progress every 30 seconds
watch -n 30 'python3 scripts/monitor_pipeline_progress.py'

# Or in a loop with timestamps
while true; do
  echo "$(date +'%H:%M:%S')"
  python3 scripts/monitor_pipeline_progress.py
  sleep 30
done
```

---

## Questions?

- **Logs**: Check CloudWatch Logs for metric loaders:
  - `/aws/ecs/positioned_metrics`
  - `/aws/ecs/value_metrics`
  - `/aws/ecs/growth_metrics`
  - `/aws/ecs/quality_metrics`

- **Status**: Check Step Functions execution:
  - algo-computed-metrics-pipeline-{environment}
  - Check execution history for errors

- **Database**: Query metric tables directly:
  ```sql
  SELECT COUNT(*) FROM positioning_metrics WHERE data_unavailable = false;
  SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL;
  ```
