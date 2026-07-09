# Algo Trading System - Quick Start Guide

This guide walks through setting up and running the algo trading system for live paper mode trading via Alpaca.

## Prerequisites

### Environment Variables (REQUIRED)
Set these BEFORE running anything:

```bash
# Database
export DB_HOST=<your-rds-host>
export DB_PORT=5432
export DB_NAME=algo
export DB_USER=<db-username>
export DB_PASSWORD=<db-password>

# AWS
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=<your-account-id>

# Alpaca (Paper Trading)
export APCA_API_KEY_ID=<your-paper-trading-key>
export APCA_API_SECRET_KEY=<your-paper-trading-secret>

# Execution
export EXECUTION_MODE=paper
export ORCHESTRATOR_DRY_RUN=false
```

### Database Setup
1. Create PostgreSQL database: `CREATE DATABASE algo;`
2. Run migrations: `python3 -m alembic upgrade head`
3. Verify tables exist: `python3 scripts/validate_orchestrator_readiness.py`

### AWS Setup
1. Create RDS database (PostgreSQL 14+)
2. Ensure Lambda has execution role with:
   - RDS access (security group rules)
   - Secrets Manager access (for Alpaca credentials)
   - DynamoDB access (for halt flags)
   - CloudWatch Logs access

## Running Loaders

Loaders must run BEFORE orchestrator to populate data:

```bash
# Quick validation
python3 scripts/validate_orchestrator_readiness.py

# Run critical loaders (one of each):
python3 loaders/load_prices.py --symbols SPY,QQQ
python3 loaders/load_stock_scores.py
python3 loaders/load_market_exposure_daily.py

# Verify data loaded
python3 -c "
from utils.db import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute('SELECT COUNT(*) FROM price_daily')
    print(f'Prices loaded: {cur.fetchone()[0]}')
    cur.execute('SELECT COUNT(*) FROM stock_scores')
    print(f'Scores loaded: {cur.fetchone()[0]}')
"
```

## Running Orchestrator

### Option 1: Local Execution (Testing)
```bash
# Dry run (no trading):
python3 -c "
from algo.orchestration import Orchestrator
from algo.infrastructure import get_config

config = get_config()
orch = Orchestrator(config=config, dry_run=True)
orch.execute()
"

# Live paper trading:
python3 -c "
from algo.orchestration import Orchestrator
from algo.infrastructure import get_config

config = get_config()
orch = Orchestrator(config=config, dry_run=False)
orch.execute()
"
```

### Option 2: AWS Lambda (Production)
```bash
# Trigger manually
aws lambda invoke \
  --function-name algo-orchestrator-dev \
  --payload '{"source":"manual-test","run_identifier":"morning","execution_mode":"paper"}' \
  /tmp/response.json

# Check CloudWatch logs
aws logs tail /aws/lambda/algo-orchestrator-dev --follow
```

### Option 3: EventBridge Scheduler (Automated)
Configured to run at:
- 9:30 AM ET (market open)
- 1:00 PM ET (mid-day)
- 5:30 PM ET (after close)

Check status:
```bash
aws scheduler list-schedules --group-name algo-orchestrator-dev
```

## Dashboard

### Access Dashboard
```bash
# Start frontend dev server
cd webapp
npm install
npm run dev

# Open http://localhost:5173
# Login with your credentials
```

### Verify Data Display
1. Navigate to Portfolio Dashboard
2. Check all panels load without errors:
   - Portfolio Value (position data)
   - KPIs (performance metrics)
   - Risk allocation
   - Sector concentration
   - R-Multiple ladder
   - Circuit breakers

If data is missing, check:
1. Loaders completed successfully
2. Orchestrator ran and populated tables
3. Dashboard API endpoints responding: `curl http://localhost:3001/api/algo/positions`

## Troubleshooting

### "All critical loaders are stale/missing"
**Problem**: Orchestrator won't run without fresh loader data

**Solutions**:
1. Run loaders manually: `python3 loaders/load_prices.py`
2. Check loader logs: `tail -f logs/loaders.log`
3. Verify EventBridge scheduler is firing loader pipelines
4. Check ECS cluster has capacity for loader tasks

### "Config validation failed"
**Problem**: Missing or invalid environment variables

**Solution**: Run validation script
```bash
python3 scripts/validate_orchestrator_readiness.py
```

### "Database connection failed"
**Problem**: Cannot connect to PostgreSQL

**Solutions**:
1. Verify RDS is running: `aws rds describe-db-instances`
2. Check security group allows port 5432
3. Verify credentials: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

### "Alpaca authentication failed"
**Problem**: Invalid API keys

**Solutions**:
1. Generate paper trading keys at https://app.alpaca.markets/
2. Store in AWS Secrets Manager: `algo/alpaca`
3. Verify environment variables set correctly

### Dashboard shows stale/cached data
**Problem**: Data is older than 30 minutes

**Solutions**:
1. Verify orchestrator ran recently: Check `algo_orchestrator_runs` table
2. Force refresh loaders: `python3 loaders/load_prices.py --backfill-days 1`
3. Refresh materialized view: `REFRESH MATERIALIZED VIEW algo_positions_with_risk`

## Architecture Overview

```
Loaders (runs 2-4x daily)
  ↓ (populate tables)
  ↓
Orchestrator (9 phases)
  ├─ Phase 1: Data freshness check
  ├─ Phase 2: Circuit breakers
  ├─ Phase 3: Position monitoring
  ├─ Phase 4: Reconciliation
  ├─ Phase 5: Exposure policy
  ├─ Phase 6: Exit execution
  ├─ Phase 7: Signal generation
  ├─ Phase 8: Entry execution
  └─ Phase 9: Final reconciliation
     ↓
Database (positions, trades, metrics)
     ↓
Dashboard (displays data via API)
     ↓
Frontend (React UI)
```

## Next Steps

1. **Local Testing**: Run orchestrator locally with dry_run=true
2. **Dashboard Verification**: Confirm all panels display data correctly
3. **Paper Trading Trial**: Run with dry_run=false for 1-2 trading days
4. **Monitor**: Watch CloudWatch logs and dashboard metrics
5. **Deploy to Production**: Update IaC and deploy via GitHub Actions

## Support

For issues:
1. Check logs: `tail -f logs/orchestrator.log`
2. Run validation: `python3 scripts/validate_orchestrator_readiness.py`
3. Review steering docs: `steering/OPERATIONS.md`
4. Check GitHub Actions: `.github/workflows/deploy-*.yml`

---

**Status**: System ready for paper trading. All components operational.
Follow the steps above to start executing trades.
