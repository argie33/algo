# ECS Loader Completion Guide

## Current Status (May 22, 2026)
- **7 Critical Loaders Running**: Started ~16:10 UTC
- **Expected Completion**: ~180+ minutes for stock prices + signals + technicals
- **Workflow ID**: 26312128122
- **Monitor Task**: b9mlxasf2

## What's Running Now (7 Loaders)
1. `stock_prices_daily` - 6h timeout, needs 180+ min for 5000+ symbols
2. `stock_prices_weekly` - 6h timeout
3. `market_data_batch` - 8 consolidated tiny loaders
4. `technical_data_daily` - 6h timeout
5. `signals_daily` - writes to `buy_sell_daily` table
6. `algo_metrics_daily` - signal quality scores
7. `econ_data` - FRED economic indicators

## Next Steps After Completion

### Step 1: Verify Loader Completion (5 minutes)
```bash
# Check GitHub Actions workflow status
gh run view 26312128122 --json conclusion,status

# Once successful, run verification script
python3 scripts/verify_loader_completion.py
```

**Expected Output**:
- All 7 loaders exit code 0
- Tables populated: price_daily, technical_data_daily, buy_sell_daily, etc.
- At least 8M+ rows in price_daily
- At least 8M+ rows in technical_data_daily

### Step 2: Run Remaining Loaders (40 more)

After the 7 critical loaders complete, remaining loaders are:

#### High Priority (should run immediately after Step 1)
- ETF prices: `etf_prices_daily`, `etf_prices_weekly`, `etf_prices_monthly` (3 loaders)
- ETF signals: `signals_etf_daily`, `signals_etf_weekly`, `signals_etf_monthly` (3 loaders)
- Price variants: `stock_prices_monthly` (1 loader)
- Signal variants: `signals_weekly`, `signals_monthly` (2 loaders)

**How to Run**:
```bash
# Via manual workflow
gh workflow run manual-invoke-loaders.yml

# Or via ECS directly (see loaders-and-orchestrator.yml for command structure)
```

#### Medium Priority (weekly/monthly data)
- Financial statements (annual/quarterly): 6 loaders
- Key metrics: 1 loader
- TTM metrics: 2 loaders
- Earnings data: 4 loaders
- Analyst sentiment: 2 loaders
- Metrics (growth/quality/value): 3 loaders

#### Lower Priority (reference/sentiment data)
- Sectors/industry: 2 loaders
- Seasonality: 1 loader
- Market indices: 1 loader
- Investor sentiment (AAII, NAAIM): 2 loaders
- Fear & Greed: 1 loader
- Company profile: 1 loader
- Trend criteria: 1 loader
- Market health: 1 loader

#### Step Functions Managed (after loaders complete)
- `eod_bulk_refresh` - bulk price refresh
- `stock_scores` - compute-heavy scoring
- `swing_trader_scores` - swing score computation
- `trend_template_data` - trend template computation

### Step 3: Orchestrator & Trading Loop
```bash
# Check if orchestrator runs automatically after loaders
gh workflow view loaders-and-orchestrator.yml

# Monitor Phase 7 completion in orchestrator logs
aws logs filter-log-events --log-group-name "/aws/lambda/algo-algo-dev" \
  --query 'events[-10:].message' --output text | grep -E "Phase 7|completed"
```

## Command Reference

### Check Loader Status
```bash
# View latest workflow run
gh run list --workflow loaders-and-orchestrator.yml --limit 1

# Get detailed logs
gh run view <RUN_ID> --log | grep -E "Launching|completed|failed|exit code"

# Get specific loader logs
aws logs filter-log-events --log-group-name "/ecs/algo-<loader>-loader" --region us-east-1
```

### Manually Run Loaders
```bash
# Stock prices daily
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-stock_prices_daily-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0988e8d04bba87486],securityGroups=[sg-0ddae70a1a80b54bd],assignPublicIp=ENABLED}" \
  --region us-east-1

# Replace with other loader names as needed
```

### Check Database Load Progress
```bash
python3 scripts/verify_loader_completion.py  # Shows all tables + row counts
```

## Troubleshooting

### If Loaders Fail
1. Check CloudWatch logs: `/ecs/algo-<loader>-loader`
2. Look for common errors:
   - Database connection: Check RDS security group + credentials
   - API rate limiting: Check yfinance/Alpaca rate limits
   - Missing data: Check if upstream tables have data
   - Timeout: Check if loader needs more time (increase in terraform)

### If Orchestrator Fails
1. Check Lambda logs: `/aws/lambda/algo-algo-dev`
2. Common issues:
   - Missing technical_data_daily: signals depend on this
   - Price table gaps: Check if stock prices fully loaded
   - Database locks: Check for long-running transactions

### If Verification Shows Missing Tables
1. Confirm loader completed (exit code 0)
2. Check loader logs for INSERT errors
3. Verify database constraints/schema match expectations
4. Re-run failed loader

## Files Created for This Work
- `scripts/verify_loader_completion.py` - verification script
- `.claude/projects/*/memory/project_loader_completion_May22.md` - work tracking
- `LOADER_COMPLETION_GUIDE.md` - this file

## Success Criteria
- All 7 critical loaders: exit code 0
- Orchestrator Phase 7: "executed" message in logs
- Database tables: row counts match expected ranges
- Final state: Ready for trading algorithms to run
