# Deploy Critical Schema Fix via GitHub Actions

**Status:** Two commits ready to deploy
**Action Required:** Trigger GitHub Actions deployment
**Timeline:** 5-10 minutes total

---

## What Was Fixed

Added 2 critical missing tables to RDS schema:

1. **`algo_signals`** — Dashboard signals panel requires this
2. **`market_sentiment`** — Put/call ratio and market data endpoints require this

These tables were missing from RDS but referenced by code, causing:
- Dashboard signals panel to show no data
- Market endpoints to fail
- Put/call ratio unavailable
- Orchestrator unable to log execution

---

## How the Fix Works

1. **schema.sql updated** with `algo_signals` and `market_sentiment` table definitions
2. **db-init Lambda will rebuild** with new schema on next deployment
3. **RDS tables will be created** when db-init Lambda runs (idempotent, safe)
4. **All data flows restored** automatically

---

## Deploy via GitHub Actions

### Option 1: Automated (Recommended)
Push to GitHub and let CI/CD handle it:

```bash
git push origin main
```

Then go to GitHub Actions and wait for "Deploy All Infrastructure" to run:
1. Go to: https://github.com/argeropolos/algo/actions
2. Watch for "Deploy All Infrastructure" workflow
3. It will automatically trigger after CI passes
4. Watch progress in the Actions tab

### Option 2: Manual Trigger
If you want immediate deployment:

```bash
# Manual GitHub Actions trigger
gh workflow run deploy-all-infrastructure.yml -R argeropolos/algo \
  --ref main \
  -f skip_terraform=false \
  -f skip_image=false \
  -f skip_code=false
```

Or via GitHub Web UI:
1. Go to: https://github.com/argeropolos/algo/actions
2. Select "Deploy All Infrastructure" workflow
3. Click "Run workflow" button
4. Choose `main` branch
5. Leave options as default
6. Click "Run workflow"

---

## What the Workflow Does

When "Deploy All Infrastructure" runs:

```
1. Bootstrap Terraform Backend (S3 + DynamoDB)
   └─ Create/verify terraform state infrastructure

2. Terraform Apply
   └─ Apply any infrastructure changes

3. Build db-init Lambda
   └─ Packages schema.sql with new table definitions
   └─ Creates lambda_artifacts/db-init.zip with updated SQL

4. Invoke db-init Lambda
   └─ Connects to RDS
   └─ Executes schema.sql (now with algo_signals and market_sentiment)
   └─ Creates all tables (IF NOT EXISTS - safe to rerun)
   └─ Log: "Schema init done: X ok, Y skipped..."

5. Deploy Application Code
   └─ Deploy API Lambda
   └─ Deploy Orchestrator Lambda
   └─ Build and push ECS image
```

**Total time:** ~15 minutes

---

## Verify Deployment Success

After workflow completes, verify tables were created:

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    # Check all 3 critical tables exist
    for table in ['algo_signals', 'orchestrator_execution_log', 'market_sentiment']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"[OK] {table}: exists with {count} rows")
EOF
```

Expected output:
```
[OK] algo_signals: exists with 0 rows
[OK] orchestrator_execution_log: exists with 0 rows
[OK] market_sentiment: exists with 0 rows
```

---

## Verify Dashboard Works

After deployment:

```bash
# Kill any existing processes
pkill -9 python

# Restart dashboard
python -m dashboard -w

# In another terminal, test the API
curl http://localhost:8000/api/signals | jq '.data | length'
# Should return > 0 (or [] if no signals yet, but no error)
```

Dashboard should now show:
- ✅ Signals panel with data
- ✅ Market health data (current, not stale)
- ✅ Growth scores populating
- ✅ All panels operational

---

## Commits to Deploy

Two commits are ready:

### Commit 1: 506b0de06
**feat: Add critical schema migration fix script**
- Created `scripts/apply_critical_schema_fixes.py` (CloudShell backup)
- Created `steering/CRITICAL_SCHEMA_UNBLOCK.md` (manual instructions)

### Commit 2: 40fbda6
**fix: Add critical missing schema tables to unblock all data flows**
- Updated `lambda/db-init/schema.sql` with:
  - `algo_signals` table (signal storage)
  - `market_sentiment` table (put/call ratio, sentiment)
- Added proper indexes for performance

---

## If Something Goes Wrong

### Workflow Failed
1. Go to GitHub Actions → "Deploy All Infrastructure"
2. Click the failed run
3. Scroll to "Invoke db-init Lambda" step
4. Check logs for errors
5. Most common issue: Database connection timeout (non-fatal, will retry)

### Tables Still Missing
Run the CloudShell backup script (from commit 506b0de06):
```bash
# This is the manual CloudShell approach if automated deployment fails
python3 scripts/apply_critical_schema_fixes.py
```

### Dashboard Still Empty
1. Verify tables exist (check above)
2. Kill and restart dashboard: `pkill -9 python && python -m dashboard -w`
3. Check API responds: `curl http://localhost:8000/api/signals`

---

## Summary

✅ **Root cause identified:** 2 critical tables missing from RDS  
✅ **Fix implemented:** Tables added to schema.sql  
✅ **IaC ready:** GitHub Actions will deploy automatically  
✅ **Backup plan:** Manual CloudShell script available  
✅ **Timeline:** ~15 min automated, ~3 min manual  

**Next step:** Push to GitHub or trigger workflow manually
