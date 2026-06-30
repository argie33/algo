# Performance Analytics R-Metrics - AWS Testing Guide

## Summary of Changes

This fix implements three missing performance analytics metrics:
- **avg_win_r**: Average R-multiple on winning trades
- **avg_loss_r**: Average R-multiple on losing trades
- **expectancy**: Expectancy = (Win Rate × Avg Win R) - (Loss Rate × Avg Loss R)

### Files Modified

1. **loaders/compute_performance_metrics.py** - Metrics now inserted into `algo_performance_daily` table
2. **scripts/apply_rds_migrations.py** - Added migration entries for the three new columns
3. **lambda/db-init/schema.sql** - Added columns to table definition for fresh database initialization
4. **tests/unit/test_r_metrics_computation.py** - Unit tests verifying expectancy formula

## Pre-Deployment Checklist

Before the ECS task runs, ensure:

### Database Schema
The three columns must exist in `algo_performance_metrics`:
- `avg_win_r NUMERIC(8, 4)`
- `avg_loss_r NUMERIC(8, 4)`
- `expectancy NUMERIC(8, 4)`

**How to apply:**
```bash
# Option 1: Run migrations script from within VPC
# (Lambda, EC2, ECS task, or via SSM port-forward)
cd /path/to/algo
python scripts/apply_rds_migrations.py

# Option 2: Manual SQL (from psql/DBeaver in VPC)
ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_win_r NUMERIC(8, 4);
ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_loss_r NUMERIC(8, 4);
ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS expectancy NUMERIC(8, 4);
```

## Running the Performance Metrics Loader

### Option 1: Wait for Scheduled Task
The performance metrics loader is scheduled to run nightly at ~4:45 PM ET as part of Phase 7 of the orchestration pipeline.

### Option 2: Manually Trigger ECS Task

```bash
# From AWS CLI (requires ECS permissions)
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition compute_performance_metrics:LATEST \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=DISABLED}" \
  --region us-east-1
```

Replace:
- `subnet-xxxxx`: Private subnet from VPC
- `sg-xxxxx`: ECS task security group
- Get these values from: `terraform output` or AWS console

## Verification Steps

### 1. Check Task Execution

```bash
# Monitor task status
aws ecs list-tasks --cluster algo-cluster --region us-east-1
aws ecs describe-tasks --cluster algo-cluster --tasks <TASK_ARN> --region us-east-1
```

### 2. Check CloudWatch Logs

The performance metrics loader logs to: `/ecs/algo-compute_performance_metrics-loader`

**Look for:**
- Task startup message
- "Performance metrics computed for <DATE>: N trades, M wins, L losses"
- R-metrics log: "R-metrics computed: avg_win_r=X.XXXX, avg_loss_r=X.XXXX, expectancy=X.XXXX"
- Success message: "Performance metrics loader completed successfully"

**Example successful log output:**
```
INFO - R-metrics computed: avg_win_r=2.1234, avg_loss_r=1.5678, expectancy=0.4567, win_rate=60% (6/10)
INFO - Performance metrics computed for 2026-06-30: 10 trades, 6 wins, 4 losses, sharpe=1.2345, max_dd=-15.67%
INFO - Performance metrics loader completed successfully
```

### 3. Verify Database Content

```sql
-- Query the performance metrics table to verify data was stored
SELECT 
    metric_date,
    total_trades,
    winning_trades,
    losing_trades,
    avg_win_r,
    avg_loss_r,
    expectancy,
    sharpe_ratio
FROM algo_performance_metrics
WHERE metric_date >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY metric_date DESC
LIMIT 5;
```

**Expected output:** 3 new columns with non-NULL values (not 0.0 unless there's no trade data)

### 4. Verify Daily Performance Table

```sql
-- Check that metrics also appear in the API consumption table
SELECT 
    report_date,
    total_trades,
    avg_w_r,
    avg_l_r,
    expectancy
FROM algo_performance_daily
WHERE report_date >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY report_date DESC
LIMIT 5;
```

## Expected Values

For a well-functioning trading system:

- **avg_win_r**: Typically 1.5 to 3.0+ (winning trades average 1.5 to 3 times the risk)
- **avg_loss_r**: Typically 0.8 to 1.2 (losing trades average 0.8 to 1.2 times the risk)
- **expectancy**: Should be positive (> 0) for profitable systems
  - Example: (0.6 × 2.5) - (0.4 × 1.0) = 1.5 - 0.4 = **1.1 R per trade**

## Troubleshooting

### Task Fails with Database Error
- Check: RDS is running and accessible from ECS task VPC
- Check: Columns exist (run migration first)
- Check: Database credentials in Secrets Manager are current

### Task Succeeds but Metrics are All Zero
- This is expected if: No trades exist in the database for the day
- Check: Trade data is being populated by earlier loaders (Phase 1-6)
- Check: Trades have required fields: `entry_price`, `entry_quantity`, `exit_date` or current price

### Task Succeeds but Metrics Are NULL
- Check: `_compute_r_metrics()` returned 0.0 for all metrics (indicates no R-multiple data)
- This means: `stop_loss_price` is missing or exit prices are not calculated
- Fix: Ensure trade data includes stop-loss and current pricing

## Code References

- **Metric Computation**: `loaders/compute_performance_metrics.py:_compute_r_metrics()` (line 334)
- **Database Insert**: `loaders/compute_performance_metrics.py:_insert_performance_metrics()` (line 436)
- **Daily Insert**: `loaders/compute_performance_metrics.py:_insert_performance_daily()` (line 503)
- **Unit Tests**: `tests/unit/test_r_metrics_computation.py`

## Next Steps

1. ✅ Code committed and pushed to main
2. ⏳ Apply database migrations (if not automatic)
3. ⏳ Run ECS task or wait for scheduled execution
4. ⏳ Verify logs show success
5. ⏳ Query database to confirm metrics are present
6. ✅ Mark goal as complete
