# CRITICAL FIX EXECUTION PLAN

**Status**: 🔴 BLOCKING — No data shows because AWS RDS schema doesn't match code expectations

## ROOT CAUSE
AWS RDS was initialized with partial schema. Many critical tables and columns are missing:
- ❌ `algo_signals` table (signals panel can't display)
- ❌ Metric table `data_unavailable` columns (quality, growth, value, positioning, stability)
- ❌ Market health columns (put_call_ratio columns missing)
- ⚠️ `algo_positions.is_open` computed column (code expects it for position queries)

## SOLUTION - 2 STEPS

### STEP 1: Apply Database Migrations (USER ACTION - 2 minutes)

**Location**: AWS CloudShell (or EC2 with VPC access to RDS)

```bash
# Clone repo or ensure you're in the algo project root
cd ~/algo

# Run the comprehensive database fix
python3 scripts/aws_complete_database_fix.py
```

**What it does**:
1. ✅ Creates missing tables: `algo_signals`, `orchestrator_execution_log` (correct schema)
2. ✅ Fixes market_sentiment table structure
3. ✅ Adds missing columns: data_unavailable, reason columns on all metric tables
4. ✅ Adds put_call_ratio columns to market_health_daily
5. ✅ Adds is_open computed column to algo_positions
6. ✅ Creates indexes for performance

**Expected output**:
```
4. Verifying schema...
   OK      algo_signals
   OK      market_sentiment
   OK      orchestrator_execution_log
   OK      stock_scores
COMPLETE: X migrations applied, Y skipped, Z failed
```

### STEP 2: Restart Services (USER ACTION - 1 minute)

```bash
# Kill running processes
pkill -9 python

# Restart dashboard
python -m dashboard -w
```

Orchestrator will resume on next scheduled run (9:30 AM, 1:00 PM, 3:00 PM, or 4:05 PM ET).

---

## VERIFICATION CHECKLIST

After applying fixes, verify:

```bash
# Check algo_signals table exists and has data
python3 -c "
from utils.db import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute('SELECT COUNT(*) FROM algo_signals')
    print(f'algo_signals: {cur.fetchone()[0]} records')
"

# Check dashboard loads without errors
python -m dashboard -w &
# Open dashboard in browser and verify:
# ✓ Market panel shows VIX, SPY price
# ✓ Signals panel shows signal data
# ✓ Scores panel shows growth_score column
# ✓ Positions panel shows open positions
```

---

## CODE STATUS - ALL IMPLEMENTED ✅

The following are already in code and will work once schema is fixed:

- ✅ Growth scores: Calculated in `load_growth_metrics.py`, included in API response
- ✅ Growth score weighting: 35% combined, 25% momentum, 20% quality, 15% value, 5% positioning
- ✅ Put/call ratio: Fetched in `load_market_health_daily.py`, used in risk calculations
- ✅ Positions status: Using `status` column correctly (not `is_open`)
- ✅ Data loaders: All explicit `data_unavailable` flags (no fallbacks/mocks)
- ✅ GitHub Actions: Workflows ready to deploy Lambda + apply migrations

---

## IF GITHUB ACTIONS DEPLOYMENT PREFERRED

Instead of manual CloudShell, can trigger via GitHub Actions:

```bash
# Run deployment workflow
gh workflow run apply-aws-migrations.yml --ref main
```

This will:
1. Check out code
2. Run migration script in AWS Lambda execution environment
3. Verify schema automatically
4. Post results

---

## AFTER FIX - EXPECTED DATA FLOW

1. **Orchestrator runs** (scheduled 9:30 AM, 1:00 PM, 3:00 PM, 4:05 PM ET weekdays)
2. **Phase 1**: Data freshness check → all loaders can now write to tables
3. **Phases 2-9**: Execute normally with complete schema
4. **Dashboard**: Shows real data from all panels
   - Market: VIX, SPY, yield curve, market regime
   - Signals: Generated signals with entry stages
   - Scores: Growth scores, composite scores
   - Positions: Open positions with ATR stops, P&L
   - Exposure: Current portfolio exposure by sector

---

## GITHUB ACTIONS STATUS

The following workflows are ready and will auto-run:

1. **deploy-api-lambda.yml** — Deploys API code changes
2. **deploy-orchestrator-lambda.yml** — Deploys orchestrator code changes  
3. **apply-aws-migrations.yml** — Applies database migrations
4. **orchestrator-scheduler.yml** — Triggers on-schedule (9:30 AM, 1:00 PM, 3:00 PM, 4:05 PM ET)

---

## TROUBLESHOOTING

**"connection refused" or "connection timeout":**
- Ensure CloudShell has access to RDS security group
- Check AWS credentials are loaded: `aws sts get-caller-identity`

**"Column does not exist" errors during fix:**
- Migrations are idempotent (safe to re-run)
- Script will skip already-applied migrations
- Check script output for specific failures

**Dashboard still blank after fix:**
- Wait for orchestrator to run (check next scheduled time)
- Or trigger manually: `python -m lambda.algo_orchestrator.lambda_function`

---

## MONITORING AFTER FIX

Check CloudWatch logs:
```bash
# Orchestrator execution logs
aws logs tail /aws/lambda/algo-orchestrator-dev --follow

# Loader execution logs
aws logs tail /ecs/algo-data-loaders --follow

# API Lambda logs
aws logs tail /aws/lambda/algo-api-dev --follow
```

Dashboard should update within 5 minutes of orchestrator completion.
