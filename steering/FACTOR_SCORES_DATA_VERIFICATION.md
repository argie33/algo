# Factor Scores Data Verification Checklist

**Date**: 2026-07-01  
**Status**: Infrastructure Operational, Pipeline Executing Successfully  
**Goal**: Verify data is flowing into factor_scores after infrastructure fixes

---

## Executive Summary

After fixing the ECS infrastructure (VPC endpoints, ECR image pulls) and deploying loader parallelism increases (positioning/value/growth/quality metrics at min parallelism 2-4), the EOD and Computed Metrics pipelines should now be loading factor scores properly.

**Expected State After Successful Pipeline Run:**
- All metric tables (positioning, value, stability, quality, growth) populated at ≥70% coverage
- stock_scores table updated with numeric factor scores (no NULL/missing values)
- OPI and other test stocks showing scores for Quality, Growth, Value, Positioning, Stability

---

## Pre-Verification Checklist

Before running verification, confirm:

- [ ] EOD Pipeline has executed (check Step Functions: `algo-eod-pipeline-dev`)
- [ ] Computed Metrics Pipeline has executed (check Step Functions: `algo-computed-metrics-pipeline-dev`)
- [ ] At least 2 hours have passed since pipeline start (accounts for data load time)
- [ ] RDS instance is AVAILABLE (CloudWatch: `algo-db-prod`, state = AVAILABLE)

---

## Verification Steps

### 1. Check Upstream Metric Table Coverage

**Purpose**: Verify that positioning, value, quality, growth, stability metric loaders have populated data

**Run**:
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
    Latest update: 2026-07-01 16:32:15

value_metrics
  ✓ OK
    Coverage: 99.2% (4960/5000 available)
    ...

quality_metrics
  ✓ OK
    Coverage: 87.3% (4365/5000 available)  ← OK even if lower (SEC data sparse)
    ...

growth_metrics
  ✓ OK
    Coverage: 83.5% (4175/5000 available)
    ...

stability_metrics
  ✓ OK
    Coverage: 95.0% (4750/5000 available)
    ...

SUMMARY
✓ Tables with sufficient data: 5/5
✓ All metric loaders appear to be running successfully!
  OPI and other stocks should have proper factor scores.
```

**Status Check**:
- [ ] positioning_metrics coverage ≥ 70%?
- [ ] value_metrics coverage ≥ 70%?
- [ ] stability_metrics coverage ≥ 70%?
- [ ] quality_metrics coverage ≥ 50% (or marked as optional)?
- [ ] growth_metrics coverage ≥ 50% (or marked as optional)?

**If any metric shows < thresholds:**
  - Check time: Is it still within pipeline window (< 1 hour from start)?
  - Check CloudWatch: Are loaders still running?
  - Check logs: Any timeout or failure messages?

---

### 2. Check Factor Scores for Sample Stocks

**Purpose**: Verify that stock_scores table has been populated with actual numeric factor scores

**Run**:
```bash
python3 scripts/check_opi_scores.py
```

**Expected Output**:
```
====================================================================================================
STOCK FACTOR SCORES
====================================================================================================
Symbol     Composite    Momentum    Quality    Growth    Value    Positioning Stability  RS%    Status        Updated
----------------------------------------------------------------------------------------------------
OPI          75.5         68.3       72.1      71.2      84.5      65.2       70.1    0.0    OK            2026-07-01 17:15:32
AAPL         82.3         85.2       88.0      80.3      79.5      75.8       82.0    5.2    OK            2026-07-01 17:14:45
MSFT         79.8         88.1       85.5      82.1      76.3       72.5       80.1    8.5    OK            2026-07-01 17:13:22
TSLA         68.5         72.3       55.0      65.2      62.1       68.9       71.0    2.3    OK            2026-07-01 17:12:15
```

**Status Check**:
- [ ] OPI has numeric Composite score (not NULL or "--")?
- [ ] OPI has numeric Quality score?
- [ ] OPI has numeric Growth score?
- [ ] OPI has numeric Value score?
- [ ] OPI has numeric Positioning score?
- [ ] OPI has numeric Stability score?
- [ ] All scores are between 0-100?
- [ ] Updated timestamp is recent (today's date)?

**If scores still show NULL or "--":**
  - This means stock_scores loader hasn't run yet or pre-flight validation failed
  - Check for these specific issues:

#### Issue: stock_scores Pre-Flight Validation Failed

Check CloudWatch logs for `algo-stock-scores-loader`:
```
[STOCK_SCORES] Pre-flight validation failed: positioning_metrics only 45.2% coverage
```

**Cause**: Upstream metric loader didn't complete in time

**Fix Options**:
1. Wait longer for metrics to complete (check metric loader status)
2. Check if positioning_metrics/value_metrics are running at reduced parallelism due to RDS saturation
3. Monitor RDS connections in CloudWatch (should be < 85 connections if healthy)
4. If persistent, check for loader timeouts in individual metric CloudWatch logs

#### Issue: stock_scores Completed But Scores Are NULL

Check this SQL query to understand why:
```sql
SELECT symbol, 
       composite_score, 
       unavailable_metrics,
       updated_at
FROM stock_scores 
WHERE symbol = 'OPI'
ORDER BY updated_at DESC
LIMIT 1;
```

**Expected**: composite_score should be numeric, unavailable_metrics should list which factors had no data

**If NULL**: Stock scores loader ran but couldn't compute valid score

---

### 3. Detailed Metric Coverage Analysis

**Purpose**: Drill down into why specific metrics might be missing

**Run**:
```bash
python3 << 'EOF'
import psycopg2
from utils.db import DatabaseContext

symbol = 'OPI'

with DatabaseContext("read") as cur:
    # Check positioning_metrics for OPI
    cur.execute("""
    SELECT data_unavailable, insider_ownership, institutional_ownership, short_interest
    FROM positioning_metrics 
    WHERE symbol = %s 
    ORDER BY updated_at DESC LIMIT 1
    """, (symbol,))
    row = cur.fetchone()
    if row:
        data_unavailable, insider, inst, short = row
        print(f"{symbol} positioning_metrics:")
        print(f"  data_unavailable: {data_unavailable}")
        print(f"  insider_ownership: {insider}")
        print(f"  institutional_ownership: {inst}")
        print(f"  short_interest: {short}")
    else:
        print(f"NO positioning_metrics for {symbol}")
    
    # Check quality_metrics
    cur.execute("""
    SELECT data_unavailable, roe, debt_to_equity, current_ratio
    FROM quality_metrics 
    WHERE symbol = %s 
    ORDER BY updated_at DESC LIMIT 1
    """, (symbol,))
    row = cur.fetchone()
    if row:
        data_unavailable, roe, debt, current = row
        print(f"\n{symbol} quality_metrics:")
        print(f"  data_unavailable: {data_unavailable}")
        print(f"  roe: {roe}")
        print(f"  debt_to_equity: {debt}")
        print(f"  current_ratio: {current}")
    else:
        print(f"\nNO quality_metrics for {symbol}")
EOF
```

**Expected Output**:
- positioning_metrics: data_unavailable=False, with actual insider/institutional/short_interest values
- quality_metrics: data_unavailable=False OR True (True is OK for REITs with SEC gaps)

---

## What If Verification Fails?

### Symptom: Factor Scores Still Show "--"

**1. Check if loaders are still running:**
```bash
aws logs tail /aws/lambda/algo-positioning-metrics-loader --follow
# Watch for any timeout or error messages
```

**2. Check RDS saturation:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=algo-db-prod \
  --start-time 2026-07-01T15:00:00Z \
  --end-time 2026-07-01T17:00:00Z \
  --period 60 \
  --statistics Average
```
- If avg > 85 connections: RDS is saturated, parallelism being reduced
- Fix: Wait for earlier loaders to complete or increase RDS Proxy capacity

**3. Check for incomplete metrics blocking stock_scores:**
```bash
python3 << 'EOF'
from utils.db import DatabaseContext

with DatabaseContext("read") as cur:
    for table in ['positioning_metrics', 'value_metrics', 'stability_metrics']:
        cur.execute(f"""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE data_unavailable = false) as available,
            COUNT(*) FILTER (WHERE data_unavailable = true) as unavailable
        FROM {table}
        """)
        total, avail, unavail = cur.fetchone()
        coverage = avail / total if total > 0 else 0
        print(f"{table}: {coverage:.1%} coverage ({avail}/{total})")
EOF
```

**Expected**:
- positioning_metrics: ≥70% available
- value_metrics: ≥70% available  
- stability_metrics: ≥70% available

**If < thresholds:**
- Orchestrator pre-flight validation will fail
- stock_scores won't compute
- Loaders likely timing out or incomplete

**Fix**:
1. Check Step Functions logs: Why did metric loaders not complete?
2. Check if RDS is the bottleneck (DatabaseConnections metric)
3. Check if loaders hit yfinance rate limits (look for 429 errors in logs)
4. If rate limited, may need to reduce parallelism temporarily to let system recover

---

## Success Criteria (All Must Pass)

- [ ] All metric tables (positioning, value, stability, quality, growth) populated
- [ ] positioning_metrics and value_metrics coverage ≥ 70%
- [ ] OPI composite_score is numeric (not NULL)
- [ ] OPI has ≥4 non-NULL factor scores
- [ ] OPI updated_at is recent (today's date)
- [ ] No errors in verify_metric_loaders.py output
- [ ] CloudWatch logs show no timeout errors for metric loaders

---

## Key Data Points to Track

**For Ongoing Monitoring:**

After initial verification passes, track these metrics:

```sql
-- Daily metric table completeness
SELECT 'positioning_metrics' as table_name,
       COUNT(*) as total_rows,
       COUNT(*) FILTER (WHERE data_unavailable = false) as available_rows,
       ROUND(100.0 * COUNT(*) FILTER (WHERE data_unavailable = false) / COUNT(*), 1) as coverage_pct,
       MAX(updated_at) as latest_update
FROM positioning_metrics;

-- factor_scores population
SELECT COUNT(*) as total_stocks,
       COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as with_scores,
       ROUND(100.0 * COUNT(*) FILTER (WHERE composite_score IS NOT NULL) / COUNT(*), 1) as score_pct,
       MAX(updated_at) as latest_update
FROM stock_scores;

-- Sample quality scores
SELECT symbol, composite_score, 
       momentum_score, quality_score, growth_score, value_score, positioning_score, stability_score
FROM stock_scores
WHERE symbol IN ('OPI', 'AAPL', 'MSFT', 'TSLA')
ORDER BY updated_at DESC;
```

---

## Infrastructure Changes Deployed (2026-06-30 to 2026-07-01)

1. **VPC Endpoints Enabled** — Allows ECS tasks to pull images from ECR
2. **ECS Task Parallelism** — Metric loaders run at min parallelism 2-4 (was 1-2)
3. **Orchestrator Timeout** — Increased from 15 to 25 minutes
4. **Granular Timestamps** — stock_scores uses datetime.now(timezone.utc) for intraday updates
5. **Dependency-Aware Recomputation** — Orchestrator automatically retriggers stock_scores when upstream metrics newer

These changes should allow:
- Metric loaders to complete in 13-30 minutes (vs. 40-83 minutes previously)
- stock_scores to recompute multiple times per day
- Factor scores to reflect latest market data

---

## Next Steps

1. Run verification steps 1-3 above
2. If all pass: Infrastructure is working, data flowing as expected
3. If any fail: Check troubleshooting section and CloudWatch logs
4. Document any issues in `/steering/TROUBLESHOOTING.md` for ops team

**Goal Achievement**: Once all verification criteria pass, the infrastructure is confirmed operational and ready for production use.
