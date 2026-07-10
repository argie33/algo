# Complete Database Migration Fix - Action Plan

## Current Status

### ✅ Infrastructure Fix: COMPLETE
- **Commit:** `933c1fd07` - VPC configuration fallbacks and validation
- **Result:** Lambda successfully creates with VPC access and connects to RDS
- **Evidence:** "Connected to stocks at algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com:5432"

### ❌ Database Lock: BLOCKING
- **Issue:** Migration 083 cannot acquire lock on positions_view
- **Error:** "canceling statement due to lock timeout"
- **Cause:** Another connection holding a lock, likely the orchestrator or long-running query

### 🎯 Final Goal
Make the GitHub Actions job complete with **exit code 0** (success)

---

## Root Cause of Lock

The migration is timing out waiting for an exclusive lock on the positions_view table. This happens when:

1. **Orchestrator is running** - Queries for trading analysis hold reads on positions_view
2. **Long-running dashboard query** - Dashboard calculates metrics holding table locks
3. **Concurrent migration attempt** - Another migration process holds the schema lock
4. **Stale connection** - An earlier deployment left a connection hanging

---

## Solutions (in order of preference)

### Option 1: Stop Orchestrator and Clear Locks (RECOMMENDED)
```bash
# 1. Stop the orchestrator to release any locks it holds
pkill -9 python

# 2. Clear long-running queries from database (run from Linux/Mac with psycopg2)
python3 scripts/resolve_migration_locks.py

# 3. Re-run workflow
gh workflow run deploy-all-infrastructure.yml \
  --repo argie33/algo \
  --ref main \
  --field skip_terraform=true

# 4. Monitor migrations job
gh run watch <run-id> --repo argie33/algo
```

### Option 2: RDS Restart (Nuclear, but guaranteed)
```bash
# Restart the database (this will disconnect all connections)
aws rds reboot-db-instance \
  --db-instance-identifier algo-db \
  --region us-east-1

# Wait 2-3 minutes for RDS to restart, then re-run workflow
gh workflow run deploy-all-infrastructure.yml \
  --repo argie33/algo \
  --ref main \
  --field skip_terraform=true
```

### Option 3: Manual Lock Termination (if you have database access)
```sql
-- Find blocking locks
SELECT blocked_locks.pid, blocking_locks.pid, blocking_activity.query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON ...
WHERE NOT blocked_locks.granted;

-- Terminate the blocking PID
SELECT pg_terminate_backend(12345);  -- Replace 12345 with actual PID
```

---

## Why This Fix Works

### VPC Configuration Problem (SOLVED)
```
Before: terraform output fails → VPC config empty → Lambda created without VPC access
After:  terraform output fails → AWS CLI fallback → Lambda created with VPC access
```

### Lock Problem (DIFFERENT ISSUE)
```
Before: N/A (Lambda couldn't connect to database at all)
After:  Lambda connects successfully, but migration times out on database lock
        This requires database administration to resolve
```

---

## Success Criteria

The GitHub Actions job will report **exit code 0** when:

1. ✅ Database locks are cleared
2. ✅ Migration 083 acquires exclusive lock on positions_view
3. ✅ All 37 pending migrations apply successfully
4. ✅ Lambda returns statusCode: 200

Current run: https://github.com/argie33/algo/actions/runs/28871357995

---

## Proof the Infrastructure Fix Works

From workflow run 28871357995, Lambda successfully:
1. Connected to RDS instance
2. Accessed schema_version table
3. Found all pending migrations
4. Started applying migrations
5. Failed on data-level issue (lock timeout), not infrastructure

This proves the VPC configuration fix resolved the original problem.

---

## Files Changed for Infrastructure Fix

- `.github/workflows/deploy-all-infrastructure.yml`
  - Added AWS CLI fallbacks for VPC discovery
  - Added validation to fail fast on incomplete VPC config
  - Added terraform state diagnostics

- `scripts/resolve_migration_locks.py`
  - Helper script to terminate long-running database queries

- `lambda/kill-locks/lambda_function.py`
  - Lambda function to clear locks (alternative approach)

---

## Next Actions

1. Choose solution from "Solutions" section above
2. Execute the chosen solution
3. Monitor the workflow run
4. Verify the job completes with exit code 0

**Recommendation:** Use Option 1 (Stop orchestrator + resolve_migration_locks.py) as it's
non-destructive and addresses the root cause.

If you're on Windows and can't run the Python script directly, use Option 2 (RDS reboot)
as it's guaranteed to clear all locks but requires 2-3 minutes downtime.
