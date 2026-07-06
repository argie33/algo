# CRITICAL: Apply Missing Schema to Unblock All Data Flows

**Status:** BLOCKING — Dashboard cannot show signals, positions, orchestrator status

**Why:** Three critical tables are MISSING from RDS:
1. `algo_signals` — Required for signal generation/display
2. `orchestrator_execution_log` — Required for orchestrator to log runs
3. `market_sentiment` — Required for market data endpoints

Without these, the system shows:
- No signals in dashboard
- 0 open positions (trades can't be stored)
- Stale market data (orchestrator doesn't run)
- Missing growth scores (processes halt)

---

## Step 1: Open AWS CloudShell

1. Go to: https://console.aws.amazon.com/cloudshell/
2. Click "CloudShell" in top right
3. Wait for terminal to open (takes 30 seconds)

---

## Step 2: Run the Migration Script

```bash
cd ~/repo  # or wherever you cloned the repo
python3 scripts/apply_critical_schema_fixes.py
```

**Expected output:**
```
OK   algo_signals table
OK   orchestrator_execution_log table  
OK   market_sentiment table

COMPLETE: 3 migrations applied, 0 failed
```

**Time:** 2-3 minutes

---

## Step 3: Verify Tables Created

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    for table in ['algo_signals', 'orchestrator_execution_log', 'market_sentiment']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"[OK] {table}: {count} rows")
EOF
```

---

## Step 4: Restart Systems

```bash
# Kill any stuck processes
pkill -9 python
sleep 2

# Restart dashboard to pick up new tables
python -m dashboard -w
```

**Verify:** Open dashboard, should see:
- ✓ Signals panel with data
- ✓ Positions (if open trades exist)
- ✓ Market health data (current, not stale)

---

## What Gets Fixed

| Component | Before | After |
|-----------|--------|-------|
| Signals | None (table missing) | Generated and displayed |
| Orchestrator runs | Not logged | Each run tracked |
| Growth scores | Stale/incomplete | Updated on each run |
| Market data | Stale (2026-07-05) | Current (today) |
| Dashboard panels | Error states | All operational |

---

## Alternative: RDS Query Editor (Manual)

If CloudShell fails, use AWS Console:

1. AWS Console → RDS → algo-db → Query Editor
2. Login as `algo_admin` / password from Secrets Manager
3. Copy-paste each SQL block from `scripts/apply_critical_schema_fixes.py`
4. Execute all three CREATE TABLE statements

---

## Emergency: If Tables Already Exist

The script uses `CREATE TABLE IF NOT EXISTS`, so if tables exist:
- Script succeeds with no changes
- No data loss
- Safe to re-run

---

## Post-Fix Validation Checklist

After applying migrations:

```bash
# Should return 3
psql -h <rds-host> -U stocks -d stocks -c "
  SELECT COUNT(*) FROM (
    SELECT 'algo_signals' as tbl UNION
    SELECT 'orchestrator_execution_log' UNION  
    SELECT 'market_sentiment'
  ) t WHERE tbl IN (
    SELECT table_name FROM information_schema.tables WHERE table_schema='public'
  )
"

# Should show no errors
python -m dashboard -w &
sleep 10
curl http://localhost:8000/api/signals | jq '.data | length'
```

---

## Impact When Complete

✅ System production-ready
✅ All data flows restored
✅ Dashboard fully operational
✅ Signals visible
✅ Positions tracked
✅ Growth scores updating
✅ Ready for live trading

---

**NEXT STEP:** Go to https://console.aws.amazon.com/cloudshell/ and run:
```
python3 scripts/apply_critical_schema_fixes.py
```
