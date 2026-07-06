# AWS System Restoration Strategy

**Date:** 2026-07-06  
**Status:** BLOCKING — System non-functional due to schema mismatches

## Problems Identified

### 1. **Database Schema Mismatch**
- **Issue:** Code queries `algo_positions.is_open` but AWS RDS doesn't have this column
- **Current Schema:** `algo_positions` has `status` field, not `is_open`
- **Impact:** All position queries fail with "column is_open does not exist"

### 2. **Missing Critical Tables** 
- ✗ `algo_signals` — NOT in RDS (dashboard can't show signals)
- ✓ `orchestrator_execution_log` — exists but schema may be incomplete
- ✓ `market_sentiment` — exists but schema may be incomplete

### 3. **Stale Data**
- Last orchestrator run: 2026-07-05 (1 day ago, but should have run today 2026-07-06)
- `price_daily`: Last updated 2026-07-06 (current - good)
- `market_exposure_daily`: Last updated 2026-07-01 (5 days old)
- `stock_scores`: schema broken, can't read

### 4. **Incomplete Migrations**
- Many `.sql` files exist in `migrations/versions/` but not all are applied to AWS RDS
- No clear record of which migrations have been applied

## Solution: 3-Step Fix

### Step 1: Understand Current State (This File)
✅ Completed — schema mismatches identified

### Step 2: Apply Comprehensive Database Fix
Run: `python3 scripts/aws_complete_database_fix.py`

This script will:
- Add missing `is_open` column to `algo_positions` (computed from `status`)
- Create missing `algo_signals` table
- Verify/fix `orchestrator_execution_log` and `market_sentiment`
- Apply all pending migrations (columns on metric tables, etc.)

### Step 3: Restart Data Pipelines
```bash
# Kill any running orchestrator/loaders
pkill -9 python

# Restart dashboard
python -m dashboard -w

# Orchestrator will resume on schedule:
# - 2:15 AM ET (morning pipeline)
# - 4:05 PM ET (end-of-day pipeline)
```

## Why This Happened

### Migration System Design (Current State)

**Local Development:**
- Primary: `lambda/db-init/schema.sql` (single-file schema for fresh databases)
- Migrations: `migrations/versions/*.sql` (applied via explicit commands)

**AWS RDS:**
- History of partial migrations
- No comprehensive migration tracker
- Manual schema additions over time
- Schema drift between code and database

### What We Need (Going Forward)

1. **Local dev:** Continue using `lambda/db-init/schema.sql` for fresh dev databases
2. **AWS RDS:** Apply all migrations in order via migration tracking
3. **Code:** Must handle column mismatches gracefully (use `status` for `is_open` logic)

## Migration History (AWS RDS)

Applied (Known):
- 0043: fix_sector_rotation_signal_column_length
- 0044: add_quality_metrics_columns  
- 0045: create_yfinance_snapshot
- 0046: add_data_unavailable_to_score_tables

Missing (To Apply):
- 052: algo_signals table
- Many others...

## Quick Verification After Fix

```bash
# Check schema is correct
python3 -c "from utils.db import DatabaseContext; ctx = DatabaseContext('read'); cur = ctx.cursor; cur.execute('SELECT COUNT(*) FROM algo_signals'); print(f'algo_signals exists: {cur.fetchone()[0] >= 0}')"

# Check orchestrator can log
python3 -c "from utils.db import DatabaseContext; ctx = DatabaseContext('read'); cur = ctx.cursor; cur.execute('SELECT COUNT(*) FROM orchestrator_execution_log'); print(f'Logs: {cur.fetchone()[0]}')"

# Check latest data
python3 -c "from utils.db import DatabaseContext; ctx = DatabaseContext('read'); cur = ctx.cursor; cur.execute('SELECT MAX(date) FROM price_daily'); print(f'Price data current as of: {cur.fetchone()[0]}')"
```

## Files Modified

- `scripts/aws_complete_database_fix.py` — NEW: Comprehensive migration script
- (Code fixes may be needed if schema mismatch persists)

## Next: Run the Fix

To apply all fixes to AWS:
```
python3 scripts/aws_complete_database_fix.py
```

This will connect to AWS RDS via Secrets Manager and apply all pending migrations in one transaction.
