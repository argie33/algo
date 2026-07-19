# Factor Scores Coverage Analysis - Session 193

## Current Status

**Factor Score Coverage:**
- Quality Score: 81.3% (881 stocks missing) → requires `quality_metrics` input
- Growth Score: 85.5% (684 stocks missing) → requires `growth_metrics` input
- Value Score: 78.5% (1015 stocks missing) → requires `value_metrics` input
- Composite Score: 97.4% (complete)
- **Data Unavailable:** 123 stocks (2.6%) marked with reason "loader_failed" due to insufficient metric completeness

**Data Freshness:**
- quality_metrics: 50.6 hours stale (last updated 2026-07-15 00:00:00)
- growth_metrics: 43.5 hours stale (last updated 2026-07-15 07:09:02)
- value_metrics: 43.6 hours stale (last updated 2026-07-15 06:59:44)
- stability_metrics: 36.6 hours stale (last updated 2026-07-16 09:49:35)
- positioning_metrics: 43.6 hours stale (last updated 2026-07-15 07:09:02)

---

## Root Cause: Pipeline Task Failures

The **Computed Metrics Pipeline** (Step Function: `algo-computed-metrics-pipeline-dev`) runs on schedule **BUT is silently failing** on 2 loaders:

### Latest Pipeline Execution: 2026-07-16 18:00-20:19 UTC

| Phase | Loader | Status | Notes |
|-------|--------|--------|-------|
| 1 | YFinanceSnapshot | ✅ SUCCEEDED | (51 min) Fetched base data |
| 2 | FinancialDataLoaders | ✅ SUCCEEDED | (42 min) SEC financial statements |
| 3 | QualityMetrics | ✅ SUCCEEDED | (6 min) quality_metrics table updated |
| 4 | ValueMetrics | ❌ FAILED | (3 retry attempts, all failed) |
| 5 | PositioningMetrics | ❌ FAILED | (3 retry attempts, all failed) |
| 6 | StabilityMetrics | ✅ SUCCEEDED | (10 min) stability_metrics updated |
| 7 | StockScores | ✅ SUCCEEDED | (9 min) Calculated with incomplete input metrics |
| Pipeline | MetricsSuccess | ✅ COMPLETED | **But with missing output tables!** |

### Why Pipeline Marks as "Success" Despite Failures

The pipeline has error handling configured to **continue on loader failures** instead of halting:

```
ValueMetrics FAILED → LogValueMetricsFailure (log error) → Continue to PositioningMetrics
PositioningMetrics FAILED → LogPositioningMetricsFailure (log error) → Continue to StabilityMetrics
```

This means:
- ❌ value_metrics table never gets updated
- ❌ positioning_metrics table never gets updated
- ✅ Pipeline still marks as "SUCCEEDED"
- ✅ stock_scores calculated with incomplete input (falls back to stability + momentum)
- ✅ 123 stocks marked data_unavailable (insufficient completeness)

---

## Why ValueMetrics & PositioningMetrics Loaders Fail

Both loaders use the consolidated `load_yfinance_derived_metrics.py` loader, which:

1. Reads from `yfinance_snapshot` table (populated earlier by YFinanceSnapshot task)
2. Calculates derived metrics (PE, PB, PS, dividend yield, etc.)
3. Writes to 5 output tables: value_metrics, positioning_metrics, company_profile, earnings_calendar, analyst_sentiment_analysis

**Failure symptoms:**
- ECS task fails at startup (no CloudWatch logs created)
- Likely reasons: 
  1. **Memory/CPU limits too low** for yfinance data processing (~4700 stocks)
  2. **Timeout configuration** - task times out before completing
  3. **VPC/Network issue** - task can't connect to database from VPC
  4. **Missing dependencies** - yfinance rate limiting or API issues

**Task Configuration (from Terraform):**
```
value_metrics: { cpu = 512, memory = 1024, timeout = 1800 (30 min), parallelism = 1 }
```

The task processes 4711 stocks sequentially (parallelism=1) with 512 CPU + 1GB RAM for 30 min timeout.

---

## Impact on Factor Scores

With value_metrics missing:

```
Quality Score:    81.3% ✅ (quality_metrics available)
Growth Score:     85.5% ✅ (growth_metrics available)
Value Score:      78.5% ❌ (value_metrics MISSING)
Positioning:      81.3% ❌ (positioning_metrics MISSING)
Composite Score:  97.4% ✅ (falls back to stable + momentum)

123 stocks rejected with:
  "Completeness: 33.33% (2/6 metrics)"
  "Minimum 50% completeness (3/6 metrics) required"
  "Available metrics: quality=0%, growth=0%, value=0%, positioning=0%, stability=17%, momentum=17%"
```

These 123 stocks missing quality, growth, value, positioning inputs are marked `data_unavailable`.

---

## Solution

### Option 1: Fix ValueMetrics Task Configuration (Preferred)

Increase task resources in `terraform/modules/pipeline/main.tf`:

```hcl
"value_metrics" = { 
  cpu        = 1024,      # ← double from 512
  memory     = 2048,      # ← double from 1024
  timeout    = 3600,      # ← increase from 1800 (1h instead of 30m)
  parallelism = 2         # ← increase from 1 (allow concurrent processing)
}
```

**Why this fixes it:**
- 1GB RAM → 2GB RAM: Yfinance data processing needs more memory for 4711 stocks
- 512 CPU → 1024 CPU: Faster data processing reduces timeout risk
- 30 min → 60 min: More time for yfinance + database writes
- parallelism 1 → 2: Process 2 stocks concurrently (yfinance rate-limiting workaround)

**Deployment:**
```bash
cd terraform
terraform apply
# GitHub Actions will deploy the updated ECS task definition
# Next scheduled run (7 PM ET) will use new configuration
```

### Option 2: Manual Trigger (Temporary, for Testing)

```bash
python3 scripts/trigger_computed_metrics_pipeline.py
```

This triggers the Computed Metrics Pipeline immediately. After task config fix, run this to populate value_metrics.

### Option 3: Run Loaders Locally (For Debugging)

```bash
# Run the consolidated yfinance derived metrics loader
python3 scripts/run_loader.py metrics

# This writes to: value_metrics, positioning_metrics, company_profile, 
#                 earnings_calendar, analyst_sentiment_analysis
```

---

## Expected Outcome After Fix

Once ValueMetrics task completes successfully:

```
Quality Score:     81.3% (stable)
Growth Score:      85.5% (stable)
Value Score:       80.3% ↑ (improves from 78.5%)
Positioning Score: 81.3% ↑ (was 0%)
Composite Score:   97.4% (stable)

Stocks with data_unavailable: 0 (from 123)
  - All 4711 stocks now have >50% metric completeness
  - All factor scores valid and usable by trading signals
```

---

## Verification Steps

After applying the fix:

```bash
# 1. Check if metrics update next run
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
cur = conn.cursor()

cur.execute("""
  SELECT COUNT(*), MAX(updated_at) 
  FROM value_metrics 
  WHERE updated_at > NOW() - INTERVAL '1 hour'
""")
count, latest = cur.fetchone()
print(f"value_metrics: {count} rows, latest: {latest}")

# Repeat for positioning_metrics
cur.close()
conn.close()
EOF

# 2. Monitor next pipeline run
python3 scripts/trigger_computed_metrics_pipeline.py
# Wait ~2 hours for pipeline to complete
# Check: all loaders SUCCEEDED (no failures)

# 3. Verify factor score coverage
python3 check_system_health.py
# Should show stock_scores FRESH, not stale
```

---

## Session History

- **Session 192**: Fixed concurrency checks blocking orchestrator, Alpaca credentials mismatch
- **Session 193**: Diagnosed factor score coverage issue - ValueMetrics/PositioningMetrics loaders failing in pipeline

## Next Steps

1. Update `terraform/modules/pipeline/main.tf` with increased task resources
2. Run `terraform apply` to deploy new ECS task definition
3. Monitor next scheduled pipeline run (7 PM ET) or manually trigger with script
4. Verify value_metrics table is populated within 1 hour after fix
