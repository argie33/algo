# AWS Loader Fix & Data Population Strategy

**Goal:** Fix all issues with AWS loaders and load complete data so we can run algo with Friday data

**Target Date:** Friday May 15, 2026 (latest market data available)

---

## Issues to Fix

1. **No data loaded yet in AWS RDS** - Loaders scheduled but haven't executed (weekend/testing)
2. **Need all tiers of data** - Symbols, prices, signals, metrics for complete algo run
3. **Need Friday closing data** - Latest data point to test orchestrator
4. **Need verification** - CloudWatch logs showing successful execution

---

## Solution Strategy

### Phase 1: Verify Infrastructure (No AWS credentials required - just checks)
- [ ] Verify ECS cluster exists and is healthy
- [ ] Verify RDS database is accessible
- [ ] Verify API Gateway is responding
- [ ] Verify CloudWatch log groups are created
- [ ] Verify Docker image is in ECR

### Phase 2: Load Complete Data (Sequential tiers)
- [ ] **Tier 0:** Load stock symbols (loadstocksymbols.py)
- [ ] **Tier 1:** Load daily prices for stocks & ETFs (latest data)
- [ ] **Tier 1b:** Generate weekly/monthly price aggregates
- [ ] **Tier 1c:** Calculate technical indicators
- [ ] **Tier 2:** Load reference data (financials, market data)
- [ ] **Tier 2c:** Calculate TTM aggregates
- [ ] **Tier 2b:** Calculate computed metrics  
- [ ] **Tier 2d:** Generate stock scores
- [ ] **Tier 3:** Generate buy/sell signals
- [ ] **Tier 3b:** Generate signal aggregates
- [ ] **Tier 4:** Calculate algo metrics

### Phase 3: Verify Data Loaded
- [ ] Check RDS: `SELECT COUNT(*) FROM stock_symbols`
- [ ] Check RDS: `SELECT COUNT(*) FROM price_daily WHERE date = '2026-05-15'`
- [ ] Check RDS: `SELECT COUNT(*) FROM buy_sell_signal_daily WHERE date = '2026-05-15'`
- [ ] View CloudWatch logs for each loader - should show success

### Phase 4: Test Orchestrator with Friday Data
- [ ] Run orchestrator with run_date=2026-05-15
- [ ] Verify it reads Friday's data
- [ ] Check if any buy signals would trigger
- [ ] Record results in algo_audit_log
- [ ] Check CloudWatch logs for execution success

---

## Implementation

### Local Testing (before AWS)
```bash
# 1. Ensure database has data
python3 run-all-loaders.py

# 2. Run orchestrator with Friday data
python3 algo/algo_orchestrator.py --mode paper --run-date 2026-05-15
```

### AWS Execution
```bash
# With AWS credentials configured:
# 1. Verify AWS setup
bash test-aws-loaders.sh

# 2. Trigger tier 0 (symbols)
./trigger-loader-ecs.sh stock_symbols

# 3. Trigger tier 1 (prices)
./trigger-loader-ecs.sh stock_prices_daily
./trigger-loader-ecs.sh etf_prices_daily

# 4. Monitor CloudWatch logs
aws logs tail /ecs/algo-stock-prices-daily-loader --follow
```

---

## Success Criteria

✅ **All Tiers Complete** - All 10 tiers have executed without errors  
✅ **Data Populated** - RDS has data for May 15, 2026  
✅ **CloudWatch Logs** - Show "success" messages for each loader  
✅ **Orchestrator Runs** - Completes 7 phases with Friday data  
✅ **Audit Log** - Shows execution in algo_audit_log table  

---

## Key Files Involved

- `run-all-loaders.py` - Orchestrates all loaders locally
- `loaders/` - Individual loader scripts (40 loaders)
- `algo/algo_orchestrator.py` - Trading algorithm execution
- `terraform/modules/loaders/` - ECS task definitions & EventBridge rules
- `.github/workflows/deploy-all-infrastructure.yml` - AWS deployment

---

## Next Steps

1. Run local loaders to populate database
2. Verify orchestrator works with Friday data locally
3. Push to main to deploy Docker image update
4. Trigger loaders in AWS with CloudWatch monitoring
5. Run final verification and document results
