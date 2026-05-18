# AWS Loader Fix Action Plan

**Goal**: Fix all AWS loader issues and load data for Friday testing (May 17, 2026 or latest Friday)

**Status**: Ready to execute - infrastructure is deployed, just need to trigger and monitor

---

## QUICK START (5 minutes)

### Step 1: Verify AWS credentials
```bash
aws sts get-caller-identity --region us-east-1
```
If this fails, configure AWS: `aws configure`

### Step 2: Run diagnostic
```bash
bash scripts/diagnose-aws-loaders.sh
```
This will check:
- ✓ AWS credentials
- ✓ RDS database status
- ✓ ECR Docker image
- ✓ ECS cluster
- ✓ EventBridge rules
- ✓ Secrets Manager
- ✓ CloudWatch log groups

### Step 3: Run infrastructure fixes
```bash
bash scripts/fix-aws-loaders.sh
```
This will:
- ✓ Enable any disabled EventBridge rules
- ✓ Create missing CloudWatch log groups
- ✓ Verify Docker image in ECR
- ✓ Verify Secrets Manager credentials
- ✓ Verify RDS database

---

## DETAILED EXECUTION PLAN

### Phase 1: Manual Loader Trigger (with monitoring)

Run loaders in dependency order and monitor CloudWatch logs:

```bash
bash scripts/trigger-all-loaders.sh
```

This script will:
1. **Tier 0** (3:30am ET): Load stock symbols (foundation for all other loaders)
   - Wait 5 minutes for completion
   - CloudWatch: `/ecs/algo-stock_symbols-loader`

2. **Tier 1** (4:00am ET): Load price data - 6 loaders in parallel
   - `stock_prices_daily` (daily OHLCV from Alpaca)
   - `stock_prices_weekly` (aggregated from daily)
   - `stock_prices_monthly` (aggregated from daily)
   - `etf_prices_daily` (ETF prices)
   - `etf_prices_weekly` (aggregated)
   - `etf_prices_monthly` (aggregated)
   - Wait 15 minutes for completion

3. **Tier 2** (Reference data - can run after Tier 1):
   - Company profiles (yfinance)
   - Analyst sentiment & ratings
   - Financial metrics (Finnhub)
   - Market indices
   - Economic data
   - Earnings data
   - Wait 30 minutes

4. **Tier 3** (Computed metrics - after Tier 2):
   - Growth metrics (revenue growth, EPS growth)
   - Quality metrics (ROE, margins, D/E ratio)
   - Value metrics (P/E, P/B, P/S ratios)
   - Wait 30 minutes

**Total Time**: ~90 minutes for all loaders

---

### Phase 2: Monitor Execution

While loaders are running, watch CloudWatch logs in real-time:

```bash
# Watch a specific loader
aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1

# Or watch all loader logs (requires filtering)
aws logs tail /ecs/algo- --follow --region us-east-1 --log-stream-name-prefix "ecs"
```

Look for:
- ✓ `[ENTRYPOINT] Starting loader: ...` - loader started
- ✓ `[ENTRYPOINT] Executing: python3 -u loaders/...` - loader is running
- ✓ `Loaded N symbols` / `Inserted M rows` - successful completion
- ✗ Error messages - failed loaders

---

### Phase 3: Verify Data Was Loaded

After all loaders complete, verify data in database:

```bash
# Check stock symbols count
aws lambda invoke --function-name algo-db-init \
  --region us-east-1 \
  --payload '{"action":"count_symbols"}' \
  /tmp/response.json && cat /tmp/response.json

# Or via API
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=1
```

Expected results:
- ✓ 5,000+ stock symbols
- ✓ 100,000+ daily price records
- ✓ Company profiles for 2,000+ symbols
- ✓ Latest prices dated May 17, 2026 (or today if today is Friday)

---

### Phase 4: Test Against Friday Data

Once data is loaded, test the orchestrator:

```bash
# Invoke the algo orchestrator to test with loaded data
aws ecs run-task \
  --cluster algo-dev \
  --task-definition algo-algo-orchestrator \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --region us-east-1

# Monitor orchestrator execution
aws logs tail /ecs/algo-algo-orchestrator --follow --region us-east-1
```

Check CloudWatch logs for:
- ✓ Phase 1: Symbol loading
- ✓ Phase 2-7: Trading logic execution
- ✓ Buy/sell signal generation
- ✓ Any trade execution log messages

---

## TROUBLESHOOTING

### If loader doesn't start
```bash
# Check ECS cluster has capacity
aws ecs describe-clusters --clusters algo-dev --region us-east-1

# Check if task definition exists
aws ecs list-task-definitions --family-prefix algo-stock_symbols-loader --region us-east-1

# Try to manually run a task
aws ecs run-task --cluster algo-dev \
  --task-definition algo-stock_symbols-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET],securityGroups=[SG],assignPublicIp=DISABLED}" \
  --region us-east-1
```

### If loader starts but fails
```bash
# Check CloudWatch logs for error messages
aws logs get-log-events \
  --log-group-name /ecs/algo-stock_symbols-loader \
  --log-stream-name $(aws logs describe-log-streams --log-group-name /ecs/algo-stock_symbols-loader --region us-east-1 --query 'logStreams[0].logStreamName' --output text) \
  --region us-east-1
```

### If database connection fails
```bash
# Check Secrets Manager has credentials
aws secretsmanager get-secret-value --secret-id algo-db-credentials-dev --region us-east-1

# Check RDS is accessible
aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1 --query 'DBInstances[0].DBInstanceStatus' --output text
# Should show: "available"
```

### If Docker image is wrong or missing
```bash
# Check ECR for latest image
aws ecr describe-images --repository-name algo-ecr-dev --region us-east-1

# If image is missing, push new one
git push origin main  # Triggers GitHub Actions deployment

# Monitor deployment
gh workflow view deploy-all-infrastructure.yml --repo argie33/algo
```

---

## COMPLETE LOADER LIST (40 loaders)

### Tier 0 (Foundations)
- stock_symbols

### Tier 1 (Prices)
- stock_prices_daily
- stock_prices_weekly
- stock_prices_monthly
- etf_prices_daily
- etf_prices_weekly
- etf_prices_monthly

### Tier 2 (Reference Data)
- company_profile
- analyst_sentiment
- analyst_upgrades_downgrades
- key_metrics
- earnings_history
- earnings_revisions
- earnings_surprise
- earnings_calendar
- seasonality
- market_indices
- econ_data
- aaiidata
- naaim_data
- feargreed
- sectors
- industry_ranking

### Tier 3 (Computed Metrics)
- growth_metrics
- quality_metrics
- value_metrics

### Tier 4 (Signals & Scoring) - Via Step Functions EOD Pipeline
- stock_scores
- signals_daily
- signals_weekly
- signals_monthly
- signals_etf_daily
- signals_etf_weekly
- signals_etf_monthly
- algo_metrics_daily
- eod_bulk_refresh

---

## EXPECTED TIMINGS

| Tier | Loaders | Time | Parallelism |
|------|---------|------|-------------|
| Tier 0 | 1 | 5 min | Sequential |
| Tier 1 | 6 | 15 min | 6 parallel |
| Tier 2 | 14 | 30 min | 4 parallel |
| Tier 3 | 3 | 30 min | Sequential |
| Step Functions EOD | 9 | 60 min | Mixed |
| **Total** | **33** | **~100 min** | **Optimized** |

---

## NEXT STEPS AFTER SUCCESS

1. ✓ Confirm all 40 loaders are working and data is fresh
2. ✓ Run orchestrator with loaded Friday data
3. ✓ Check CloudWatch logs for trading signals
4. ✓ Verify any buy/sell signals were generated
5. ✓ Document the current data state in STATUS.md
6. ✓ Commit all fixes to main branch

---

## REFERENCES

- **Terraform**: `terraform/modules/loaders/main.tf` - All 40 loader definitions
- **Entrypoint**: `entrypoint.sh` - How loaders are executed in ECS
- **Base Class**: `utils/optimal_loader.py` - Base loader implementation
- **Data Router**: `utils/data_source_router.py` - Multi-source data fetching
- **Database**: `utils/db_connection.py` - Connection pooling & retry logic

---

**Created**: 2026-05-18
**Status**: Ready to execute
**Estimated Completion**: ~2 hours
