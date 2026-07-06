# AWS Database Fix — Step-by-Step Instructions

**Status:** BLOCKING — AWS RDS schema broken, prevents all queries  
**Severity:** CRITICAL — Dashboard, API, and orchestrator non-functional  
**Date:** 2026-07-06  

---

## What's Broken

Your AWS database has **schema mismatches** that prevent the system from working:

1. **Code expects `algo_positions.is_open` column**
   - AWS RDS doesn't have this column
   - All queries referencing it fail with: `UndefinedColumn: column "is_open" does not exist`

2. **Critical table missing: `algo_signals`**
   - Needed for dashboard signals panel
   - Orchestrator can't log signals

3. **Many migrations not applied to AWS**
   - Columns missing on metric tables
   - Schema is incomplete vs. the main `lambda/db-init/schema.sql`

---

## The Fix (3 Simple Steps)

### Step 1: Connect to AWS CloudShell

Go to AWS Console → CloudShell (or use `aws cloudshell start` via CLI)

### Step 2: Run the Fix Script

```bash
cd algo && python3 scripts/aws_complete_database_fix.py
```

**What this does:**
- Connects to AWS RDS via Secrets Manager (no credentials needed)
- Adds missing `is_open` column to `algo_positions`
- Creates missing `algo_signals` table
- Applies all pending migrations (20+ column additions)
- Verifies everything worked

**Expected output:**
```
================================================================================
AWS RDS COMPLETE DATABASE FIX
================================================================================

1. Getting RDS credentials from AWS Secrets Manager...
   Host: algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com

2. Connecting to AWS RDS database...
   Connected to: stocks

3. Applying migrations...
   OK      algo_positions.is_open column
   OK      algo_signals table
   [... more migrations ...]
   
========================================================================
COMPLETE: 24 migrations applied, 3 skipped, 0 failed
========================================================================

[SUCCESS] Database fix complete!

Next steps:
  1. Kill orchestrator if running: pkill -9 python
  2. Restart dashboard: python -m dashboard -w
  3. Orchestrator will resume on next scheduled run (2:15 AM or 4:05 PM ET)
  4. Monitor AWS CloudWatch logs for loader jobs
```

### Step 3: Restart the System

**Still in CloudShell:**

```bash
# Kill any running processes
pkill -9 python

# Restart dashboard
python -m dashboard -w
```

**Wait for confirmation:**
- Dashboard should start and connect to local API
- Orchestrator will resume on its schedule:
  - **2:15 AM ET** — Morning pipeline (prices, technical data)
  - **4:05 PM ET** — End-of-day pipeline (market exposure, scores)

---

## Verify It Worked

**In CloudShell, run one of these:**

```bash
# Check algo_signals table exists
python3 -c "from utils.db import DatabaseContext; c = DatabaseContext('read'); cur = c.cursor; cur.execute('SELECT COUNT(*) FROM algo_signals'); print(f'algo_signals table: OK')"

# Check is_open column exists
python3 -c "from utils.db import DatabaseContext; c = DatabaseContext('read'); cur = c.cursor; cur.execute('SELECT COUNT(*) FROM algo_positions WHERE is_open = TRUE'); print(f'Open positions: OK')"

# Check latest price data
python3 -c "from utils.db import DatabaseContext; c = DatabaseContext('read'); cur = c.cursor; cur.execute('SELECT MAX(date) FROM price_daily'); print(f'Price data current as of: {cur.fetchone()[0]}')"
```

All should succeed without errors.

---

## What if it Fails?

If the script shows `FAILED: X migrations applied, Y skipped, Z failed` with Z > 0:

1. **Check CloudShell has AWS credentials:**
   ```bash
   aws sts get-caller-identity
   ```
   Should show your AWS account ID.

2. **Check RDS is accessible:**
   ```bash
   python3 -c "import psycopg2; print('psycopg2 ready')"
   ```

3. **Check Secrets Manager has the credentials:**
   ```bash
   aws secretsmanager get-secret-value --secret-id algo-db-credentials-dev --region us-east-1 | head -20
   ```

4. If still failing, contact AWS support or check CloudShell logs.

---

## Why This Happened

1. **Local dev uses:** `lambda/db-init/schema.sql` (full schema)
2. **AWS has been:** Manually migrated with partial scripts
3. **Result:** Schema drift — code expects columns that AWS doesn't have

Now fixed with a comprehensive migration that applies all pending changes in one go.

---

## Timeline to Full System Recovery

| Time | Event |
|------|-------|
| **Now** | Run fix script (5 min) + restart dashboard |
| **2:15 AM ET** | Morning orchestrator run starts (loaders run) |
| **4:05 PM ET** | End-of-day orchestrator run starts (stock scores updated) |
| **Next day** | System fully operational with fresh market data |

---

## Files Changed

- `scripts/aws_complete_database_fix.py` — NEW: Comprehensive fix script
- `SYSTEM_FIX_STRATEGY.md` — Documentation of issues and solution
- Commit: 28cf703e2

---

## Questions?

- If queries still fail after running the script, check that Z=0 (no failed migrations)
- If CloudShell can't connect to RDS, verify VPC access (RDS is in private VPC)
- If you need to roll back: `git revert 28cf703e2` then restore database from backup

---

**Run the fix now:**
```bash
cd algo && python3 scripts/aws_complete_database_fix.py
```

Then restart the system and the orchestrator will resume on its normal schedule.
