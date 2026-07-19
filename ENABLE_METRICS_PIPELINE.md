# How to Enable the Metrics Pipeline

**Status:** Metrics pipeline is configured but **not running** in production.
**Root Cause:** EventBridge Scheduler rule may be disabled or not deployed.
**Impact:** Metrics tables remain at 44.5% coverage (S&P 500 subset only). System halts on every orchestrator run because Phase 1 finds incomplete metrics.

## Quick Fix (if scheduler is just disabled)

```bash
# 1. Enable the EventBridge Scheduler rule
aws scheduler update-schedule \
  --name algo-computed-metrics-pipeline-prod \
  --state ENABLED

# 2. Verify it's enabled
aws scheduler get-schedule --name algo-computed-metrics-pipeline-prod

# 3. Check next execution time (should be today at 7:00 PM ET)
aws scheduler get-schedule --name algo-computed-metrics-pipeline-prod \
  --query 'NextExecution' --output text
```

## Full Fix (if terraform needs to be deployed)

```bash
# 1. Check that terraform has the scheduler configuration
cd terraform
grep -r "computed_metrics_pipeline_trigger" modules/pipeline/

# 2. Verify the rule definition (should be at 7:00 PM ET daily)
# Expected: resource "aws_scheduler_schedule" "computed_metrics_pipeline_trigger" {
#             schedule_expression = "cron(0 19 * * ? *)" (19:00 = 7 PM ET)

# 3. Re-deploy the scheduler rule
terraform apply -target module.pipeline.aws_scheduler_schedule.computed_metrics_pipeline_trigger

# 4. Verify it's deployed
aws scheduler list-schedules \
  --query "Schedules[?Name=='algo-computed-metrics-pipeline-*']" \
  --output table
```

## Manual Trigger (test without waiting for 7 PM)

```bash
# Trigger metrics pipeline immediately
python3 scripts/trigger_metrics_pipeline.py --environment production --watch

# This will:
# 1. Start the Step Functions execution
# 2. Monitor progress every 10 seconds
# 3. Report success/failure
# 4. Expected runtime: 2-3 hours (includes financial statements + all metrics)
```

## Verify It's Working

After enabling (or after next 7 PM ET):

```bash
# Check Step Functions execution history
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:123456789012:stateMachine:algo-computed-metrics-pipeline-prod \
  --max-results 10 \
  --output table

# Check CloudWatch logs
aws logs tail /aws/states/algo-computed-metrics-pipeline-prod --follow

# Check if data updated in database
psql -c "SELECT table_name, COUNT(*) as rows FROM (
  SELECT 'value_metrics' as table_name, COUNT(*) FROM value_metrics
  UNION ALL
  SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
  UNION ALL
  SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
  UNION ALL
  SELECT 'positioning_metrics', COUNT(*) FROM positioning_metrics
  UNION ALL
  SELECT 'stock_scores', COUNT(*) FROM stock_scores
) t GROUP BY table_name;"
```

## Pipeline Stages (what runs in order)

The computed_metrics_pipeline Step Functions state machine runs:

1. **CheckTradingDay** - Skip on weekends/holidays
2. **StockSymbols** - Load market constituents (5 min)
3. **FinancialStatements** - SEC Edgar annual/quarterly data (20-30 min)
4. **SecValuations** - Compute PE/PB/PS/PEG from SEC (10 min)
5. **Yfinance Snapshot** - Analyst sentiment + earnings (optional, 5 min)
6. **SecCompanyInfo** - Company metadata from SEC (5 min)
7. **Institutional Holdings** - SEC 13F ownership (10 min)
8. **Insider Holdings** - SEC Form 4/5 (10 min)
9. **ValueQualityGrowthMetrics** - Consolidated metrics loader (20 min)
10. **PositioningMetrics** - Ownership aggregation (10 min)
11. **StabilityMetrics** - Volatility/beta calculations (10 min)
12. **StockScores** - Composite scoring (5 min)
13. **BuySellDaily** - Signal generation (5 min)
14. **Orchestrator** - Run 9 trading phases

**Total time:** ~2-3 hours (depends on SEC API response times)

## If Pipeline Keeps Failing

Check Step Functions execution logs:

```bash
# Get detailed execution history
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:us-east-1:account:execution:algo-computed-metrics-pipeline-prod:execution-name

# Common failure points:
# 1. Financial statements loader timeout (SEC API slow)
#    → Increase timeout in terraform/modules/pipeline/main.tf
# 2. ECS task capacity exhausted
#    → Check ECS cluster CPU/memory available
# 3. RDS connection pool exhausted
#    → Use RDS Proxy (configured in terraform/modules/database/main.tf)
# 4. DynamoDB locks stuck
#    → Check data_loader_status table for RUNNING loaders
```

## Session 258 Context

**Fixed:** Phase 1 critical retry list now includes metric loaders (prevents silent stale data)
**Verified:** All metric loaders work when triggered locally (code is bulletproof)
**Issue:** EventBridge Scheduler not running them in production

**Current Coverage:**
- price_daily: 100% ✅
- sec_valuations: 85% ✅
- value_metrics: 44.5% ❌ (needs 80%+)
- quality_metrics: 44.5% ❌
- growth_metrics: 44.5% ❌
- positioning_metrics: 44.5% ❌
- stability_metrics: ~44% ❌
- stock_scores: 41.7% ❌

**Success Criteria:**
- [ ] EventBridge Scheduler enabled and running
- [ ] Pipeline executes daily at 7:00 PM ET
- [ ] All metrics reach 80%+ coverage
- [ ] Phase 1 passes without halting on incomplete metrics

## Troubleshooting Checklist

- [ ] Verify terraform was deployed recently: `aws lambda list-functions --query "Functions[?Name=='*loader*'].LastModified" | head -5`
- [ ] Check EventBridge Scheduler state: `aws scheduler get-schedule --name algo-computed-metrics-pipeline-prod --query State`
- [ ] Verify Step Functions state machine exists: `aws stepfunctions list-state-machines`
- [ ] Check IAM permissions: `aws iam get-role-policy --role-name algo-sfn-eod-pipeline-prod --policy-name algo-sfn-eod-pipeline-policy`
- [ ] Monitor RDS connections: `SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;`
- [ ] Check DynamoDB locks: `SELECT COUNT(*) FROM loader_execution_locks WHERE status='RUNNING' AND updated_at < NOW() - INTERVAL '1 hour';`
