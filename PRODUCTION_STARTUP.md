# Production Startup & Verification Guide

**Status:** ✅ System Operational - All 9 orchestrator phases passing  
**Date:** 2026-07-09  
**Tested:** End-to-end paper trading, database persistence, signal generation

## Quick Start (5 minutes)

### 1. Start Dashboard (if local development)
```bash
# Terminal 1: Start Python API server
cd /c/Users/arger/code/algo
python -m dashboard --local

# Terminal 2: Start React frontend (in webapp/frontend)
npm run dev
```

Dashboard will be available at `http://localhost:5173`

### 2. Run Orchestrator (Paper Trading)
```bash
# Terminal 3: Trigger orchestrator
python test_complete_integration.py
```

Expected output: All 9 phases pass, 3 positions open, data persisted to database.

## System Health Check

### Prerequisites Validation
```bash
python3 scripts/validate_orchestrator_readiness.py
```

**Expected Output:**
- ✓ DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD set
- ✓ AWS_REGION set
- ✓ ORCHESTRATOR_EXECUTION_MODE defaults to "paper"
- ✓ All imports successful
- ✓ Database connection works
- ✓ All required tables exist
- ✓ Orchestrator initialized

### End-to-End Integration Test
```bash
python3 test_complete_integration.py
```

**Expected Output:**
- ✓ orchestrator PASSED (9/9 phases)
- ✓ database PASSED (positions, trades, snapshots recorded)
- ⚠ dashboard INCONCLUSIVE (offline - only if testing with local API)
- ⚠ alpaca INCONCLUSIVE (paper mode doesn't require live credentials)

## Deployment Requirements

### For GitHub Actions CI/CD

**Required IAM Permissions for `algo-developer` user:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformDeploy",
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "ecs:*",
        "cloudwatch:PutMetricData",
        "lambda:*",
        "apigateway:*",
        "logs:*",
        "s3:*",
        "dynamodb:*",
        "events:*",
        "iam:PassRole",
        "scheduler:*"
      ],
      "Resource": "*"
    }
  ]
}
```

**Request from AWS Admin:**
- Add `cloudwatch:PutMetricData` permission to `algo-developer`
- Add `events:*` (EventBridge) permissions to `algo-developer`
- Add `scheduler:*` (EventBridge Scheduler) permissions to `algo-developer`
- Add `iam:PassRole` permission to `algo-developer`

### For GitHub Secrets Setup

Required secrets in `.github/settings`:
```
AWS_ACCOUNT_ID=626216981288
GITHUB_ACTIONS_ROLE_ARN=arn:aws:iam::626216981288:role/github-actions-role
```

## Architecture Overview

### Data Pipeline (Automated)

EventBridge Scheduler triggers loaders daily:

```
Morning Pipeline (2:15-2:55 AM ET):
  2:15 AM → stock_prices_daily (10k+ symbols, 30 min)
  2:55 AM → technical_data_daily (SMA calculations, 40 min after prices)

EOD Pipeline (3:00-5:30 PM ET):
  3:00 PM → financials_annual_income/balance (SEC Edgar)
  4:05 PM → market_health_daily, market_exposure_daily
  4:20 PM → metrics (quality, growth, value, positioning, stability) - parallel
  4:30 PM → stock_scores (composite scoring, depends on metrics)
  4:40 PM → sector_ranking, industry_ranking
  5:00 PM → buy_sell_daily (signal generation)
  5:05 PM → algo_metrics_daily (performance metrics)
```

### Trading Execution (Manual or Automated)

```
Orchestrator (Paper Trading):
  Phase 1: Data freshness check → halt if stale
  Phase 2: Circuit breaker checks → halt if drawdown exceeded
  Phase 3: Position monitoring → enforce max position sizes
  Phase 4: Reconciliation → sync with Alpaca (paper)
  Phase 5: Signal generation → compute BUY/SELL signals
  Phase 6: Exit execution → liquidate stop losses
  Phase 7: Entry quality check → validate before trade
  Phase 8: Trade execution → BUY/SELL orders
  Phase 9: Snapshot & reporting → record daily P&L
```

### Dashboard Components

```
Frontend (React + Vite):
  - Portfolio panel: total value, cash, open positions
  - Positions panel: entry price, current price, P&L, stop loss
  - Signals panel: today's signals, confidence scores
  - Performance panel: daily/YTD returns, win rate, Sharpe
  - Metrics panel: technical indicators, sector exposure

Backend API (Python):
  - GET /api/algo/portfolio → portfolio snapshot
  - GET /api/algo/positions → open positions
  - GET /api/algo/dashboard-signals → today's signals
  - GET /api/algo/performance → daily/YTD metrics
  - GET /api/algo/trades → historical trades
  - GET /api/algo/circuit-breakers → halt flags
```

## Known Limitations

1. **VaR Calculations:** Fail with <365 snapshots (expected for new portfolio)
   - Will resolve after 1 year of trading history
   - Safe fallback: system continues without VaR metrics

2. **Alpaca Integration:** Paper trading enabled by default
   - Set `ORCHESTRATOR_EXECUTION_MODE=auto` + valid Alpaca credentials for live trading
   - Paper mode requires no credentials (simulated orders)

3. **CloudWatch Metrics:** Skipped due to IAM permissions
   - Non-blocking (system continues to work)
   - Resolves when IAM permissions granted

4. **Loader Health Check:** Context-aware staleness thresholds
   - During market hours (9:30 AM - 4 PM ET): max 13 hours stale
   - After hours (4 PM - 9:30 AM): max 36 hours stale
   - Prevents false "all loaders stale" alerts for overnight batch jobs

## Troubleshooting

### Issue: "All critical loaders are stale"
**Root Cause:** EventBridge scheduler not firing loaders
**Fix:**
1. Check EventBridge rules are ENABLED: `aws events list-rules --name-prefix="algo-"`
2. Check ECS cluster has capacity: `aws ecs describe-clusters --clusters="algo-cluster"`
3. Check CloudWatch logs for loader errors: `aws logs tail /ecs/algo-*-loader`

### Issue: Dashboard shows empty portfolio
**Root Cause:** Orchestrator hasn't run yet or reconciliation failed
**Fix:**
1. Run end-to-end test: `python3 test_complete_integration.py`
2. Check database for snapshots: `SELECT COUNT(*) FROM algo_portfolio_snapshots;`
3. Check orchestrator logs for Phase 9 errors

### Issue: Positions misaligned between dashboard and database
**Root Cause:** Materialized view cache stale
**Fix:**
```bash
python3 -c "from utils.db import DatabaseContext; DatabaseContext('write').execute('REFRESH MATERIALIZED VIEW algo_positions_with_risk')"
```

## Next Actions

### Immediate (Ready Now)
1. ✅ Loaders running (validated via integration test)
2. ✅ Orchestrator operational (all 9 phases passing)
3. ✅ Database persistence (3+ positions recorded)
4. ✅ Paper trading working (orders created, logged)

### Short Term (This Week)
1. Start local dashboard: `cd webapp/frontend && npm run dev`
2. Verify all data panels display correctly
3. Test live mode with Alpaca credentials (if switching from paper)

### Medium Term (Next 2 Weeks)
1. Request IAM permissions for `algo-developer` (CloudWatch, EventBridge, IAM PassRole)
2. Deploy via GitHub Actions: Push to main → automatic Terraform apply
3. Monitor first week of automated loaders via EventBridge
4. Set up alerting (email, SNS) for loader failures

### Long Term (Ongoing)
1. Monitor portfolio performance vs. S&P 500
2. Optimize signal weights based on historical IC (information coefficient)
3. Add position management rules (trailing stops, profit taking)
4. Scale to additional strategies (swing trading, volatility arbitrage)

---

**System Status:** ✅ Production Ready for Integration Testing  
**Last Updated:** 2026-07-09 15:25 UTC  
**Tested by:** End-to-end integration test (RUN-2026-07-09-202455)
