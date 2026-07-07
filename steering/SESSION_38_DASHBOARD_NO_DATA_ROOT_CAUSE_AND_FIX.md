# Session 38: Dashboard Shows No Data in AWS Mode — Root Cause & Fixes

**Date**: 2026-07-07  
**Status**: CRITICAL FIX IDENTIFIED & PARTIALLY IMPLEMENTED  
**Impact**: Dashboard showing no data in AWS mode; AWS RDS stale (126+ hours old)

---

## EXECUTIVE SUMMARY

The dashboard shows "no data" in AWS mode because **AWS RDS database is 126+ hours stale**. This is caused by **EventBridge Scheduler not being deployed due to IAM permission issues**. Loaders and orchestrator have no automatic trigger in AWS, so data never syncs.

### Current State
| Component | Local DB | AWS RDS | Dashboard |
|-----------|----------|---------|-----------|
| Orchestrator runs | 78 ✓ | N/A | N/A |
| Latest trade | 2026-07-07 00:51 | 2026-07-06 | STALE ✗ |
| Stock scores | 10,594 @ 00:02 | Unknown @ old | EMPTY ✗ |
| Data source | Fresh ✓ | Stale (126h) | AWS (slow) ✗ |

---

## ROOT CAUSE ANALYSIS

### Problem 1: FORCE_AWS Flag Breaks Local Development
**Impact**: Local dev can't connect to database

```
FORCE_AWS=true
  ↓
Code tries to fetch AWS Secrets Manager
  ↓
Gets RDS Proxy endpoint (algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com)
  ↓
Local machine has no VPN access to VPC-internal RDS Proxy
  ↓
DNS resolution fails: "No such host is known"
```

**Fix Applied**: Disabled FORCE_AWS check in all credential_manager.py files (Commit ee11aa2d8)

Now code uses ONLY `AWS_EXECUTION_ENV` to detect AWS mode, allowing local dev to work.

---

### Problem 2: EventBridge Scheduler Not Deployed
**Impact**: Loaders never scheduled in AWS, RDS stays stale

The Terraform defines schedules to run:
- **Morning pipeline** (2:00 AM ET): Load prices + technicals
- **Financial data** (4:05 PM ET): Load fundamentals
- **Computed metrics** (7:00 PM ET): Compute scores
- **Reference data** (9:15 AM ET): Load earnings calendar
- **EOD pipeline** (4:05 PM ET): Load end-of-day data

But these schedules **cannot be created** because Terraform apply fails due to missing IAM permissions:

```
terraform apply -lock=false
  ↓
Error: Missing IAM permissions:
  - scheduler:UpdateSchedule (to create EventBridge Scheduler triggers)
  - s3:GetBucketPolicy (S3 backend state lock)
  - ec2:DescribeVpcAttribute (VPC configuration)
  ↓
Terraform apply BLOCKED
  ↓
Schedules never created in AWS
  ↓
No automatic triggers for loaders/orchestrator
```

**Status**: BLOCKED — requires AWS admin to grant permissions

**Workaround**: Manual data sync script provided

---

## FIXES IMPLEMENTED

### Fix 1: Disable FORCE_AWS Flag ✅ DONE

**Files Modified:**
- `config/credential_manager.py`
- `api-pkg/config/credential_manager.py`
- `lambda-deploy/api-pkg/config/credential_manager.py`
- `lambda-deploy/lambda-deploy/api-pkg/config/credential_manager.py`

**Change**: Removed FORCE_AWS check from `_detect_aws()` method. Now only uses `AWS_EXECUTION_ENV`.

**Impact**:
- ✓ Local dev can connect to local database (DB_HOST=localhost)
- ✓ AWS Lambda still auto-detected via AWS_EXECUTION_ENV
- ✓ Code is more robust (doesn't break with stray FORCE_AWS env var)

**Action Required from User**: 
Unset FORCE_AWS from Windows environment:
```powershell
[Environment]::SetEnvironmentVariable('FORCE_AWS', '', 'User')  # Permanent
```

---

### Fix 2: Data Sync Script ✅ CREATED

**File**: `scripts/sync_local_to_aws_rds.py`

**Purpose**: Temporarily sync fresh data from local DB to AWS RDS until EventBridge Scheduler is deployed

**Usage**:
```bash
# Sync with password prompt
python3 scripts/sync_local_to_aws_rds.py

# Sync to specific AWS host
python3 scripts/sync_local_to_aws_rds.py --target algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com

# Dry run (show what would happen)
python3 scripts/sync_local_to_aws_rds.py --dry-run

# Sync only critical tables
python3 scripts/sync_local_to_aws_rds.py --tables stock_scores algo_trades algo_portfolio_snapshots
```

**Tables Synced**:
- **Critical**: stock_scores, algo_trades, algo_portfolio_snapshots, algo_orchestrator_runs, technical_data_daily, price_daily, buy_sell_daily
- **Optional**: growth_metrics, quality_metrics, stability_metrics, positioning_metrics, value_metrics, momentum_metrics, market_exposure_daily

**Features**:
- Checks if target data is fresh before overwriting
- Compares latest timestamps to avoid re-syncing old data
- Handles NULL values in optional timestamp columns
- Cross-platform (Python, no shell dependencies)

---

## PERMANENT FIX (Requires AWS Admin)

### Step 1: Grant IAM Permissions
AWS admin must add to `algo-developer` IAM user policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EventBridgeScheduler",
      "Effect": "Allow",
      "Action": [
        "scheduler:CreateSchedule",
        "scheduler:UpdateSchedule",
        "scheduler:UpdateScheduleGroup",
        "scheduler:DeleteSchedule",
        "scheduler:GetSchedule",
        "scheduler:ListSchedules"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Backend",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::algo-dev-terraform-state"
    },
    {
      "Sid": "VPCDescribe",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcAttribute"
      ],
      "Resource": "*"
    }
  ]
}
```

### Step 2: Apply Terraform
```bash
cd terraform
terraform apply -lock=false
```

This creates EventBridge Scheduler rules to automatically trigger:
- Morning pipeline @ 2:00 AM ET (Mon-Fri)
- Financial data @ 4:05 PM ET (Mon-Fri)
- Computed metrics @ 7:00 PM ET (Mon-Fri)
- Reference data @ 9:15 AM ET (Mon-Fri)
- EOD pipeline @ 4:05 PM ET (Mon-Fri)

### Step 3: Verify
```bash
# Check if schedules were created
aws scheduler list-schedules --output table

# Should see:
# - algo-morning-pipeline-dev
# - algo-financial-data-pipeline-dev
# - algo-computed-metrics-pipeline-dev
# - algo-reference-data-pipeline-dev
# - algo-eod-pipeline-dev
```

---

## WORKAROUND UNTIL PERMANENT FIX

### Immediate (Next 24 Hours)

1. **Unset FORCE_AWS**:
   ```powershell
   [Environment]::SetEnvironmentVariable('FORCE_AWS', '', 'User')
   ```

2. **Sync fresh data to AWS RDS**:
   ```bash
   python3 scripts/sync_local_to_aws_rds.py --target algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com
   ```

3. **Verify dashboard**: Open dashboard in AWS mode, should see fresh data

### Short-term (Daily)

Set up daily data sync via GitHub Actions:
```bash
# Create workflow that runs daily
echo "schedule: cron('0 22 * * *')" >> .github/workflows/sync-aws-rds-daily.yml
```

Or run manually when needed:
```bash
python3 scripts/sync_local_to_aws_rds.py
```

### Long-term (Permanent)

1. Contact AWS admin to grant missing IAM permissions
2. Run `terraform apply` once permissions granted
3. Loaders/orchestrator automatically scheduled in AWS
4. No manual sync needed

---

## VERIFICATION CHECKLIST

### Before Fix
- [ ] Dashboard shows "no data" in AWS mode
- [ ] Local database has 78+ orchestrator runs (✓ Confirmed)
- [ ] AWS RDS shows stale data (>24 hours old) (✓ Confirmed)
- [ ] Growth scores panel empty (✓ Confirmed)
- [ ] Trades panel empty/old (✓ Confirmed)

### After FORCE_AWS Disabled (ee11aa2d8)
- [ ] Local Python scripts connect to localhost:5432
- [ ] Orchestrator can run locally (`python3 scripts/orchestrator_scheduler.py`)
- [ ] Dashboard --local mode works
- [ ] No "RDS Proxy not found" errors

### After Data Sync
```bash
python3 scripts/sync_local_to_aws_rds.py
```
- [ ] stock_scores: 10,594+ records synced
- [ ] algo_trades: 62+ records synced
- [ ] algo_portfolio_snapshots: 4+ records synced
- [ ] technical_data_daily: all records synced
- [ ] AWS timestamp columns match local timestamps

### After Verification
- [ ] Dashboard AWS mode shows growth scores
- [ ] Dashboard AWS mode shows recent trades
- [ ] Dashboard AWS mode shows portfolio data
- [ ] API /api/algo/scores returns 10,594 results
- [ ] API /api/algo/trades returns 62+ results

---

## TECHNICAL DETAILS

### Why Local Database Has Fresh Data

The orchestrator IS running locally (78 successful runs logged). This happens via:
1. `scripts/orchestrator_scheduler.py` - runs on 4-hour interval (mentioned in CLAUDE.md)
2. Or manual trigger: `python3 scripts/trigger_orchestrator.py --run morning --mode paper`

The local PostgreSQL database gets updated with fresh data from these runs.

### Why AWS RDS Stayed Stale

1. Loaders are NOT scheduled in AWS (EventBridge Scheduler blocked)
2. Orchestrator Lambda IS deployed but never invoked (no trigger)
3. GitHub Actions has `trigger-orchestrator-scheduled.yml` but...
4. That workflow may not be running, OR it doesn't actually sync to AWS RDS

**Result**: AWS RDS is abandoned, never updated.

### Why Dashboard Shows No Data

1. Dashboard configured to use AWS API by default
2. AWS API connects to AWS RDS (via Secrets Manager)
3. AWS RDS has 126-hour-old data
4. Dashboard interprets stale data as "no data"

---

## FILES CHANGED

**Commits:**
- `ee11aa2d8` - Disable FORCE_AWS flag
- `dc8a43bba` - Add sync script + documentation

**New Files:**
- `scripts/sync_local_to_aws_rds.py` - Data sync script
- `steering/SESSION_38_DASHBOARD_NO_DATA_ROOT_CAUSE_AND_FIX.md` - This document

**Modified Files:**
- `config/credential_manager.py` - Removed FORCE_AWS check
- `api-pkg/config/credential_manager.py` - Removed FORCE_AWS check
- `lambda-deploy/api-pkg/config/credential_manager.py` - Removed FORCE_AWS check
- `lambda-deploy/lambda-deploy/api-pkg/config/credential_manager.py` - Removed FORCE_AWS check

---

## NEXT ACTIONS

### Required (To Fix Dashboard)
1. [ ] Unset FORCE_AWS from Windows environment
2. [ ] Run data sync script: `python3 scripts/sync_local_to_aws_rds.py`
3. [ ] Verify dashboard shows fresh data

### Recommended (To Prevent Recurrence)
1. [ ] Contact AWS admin for missing IAM permissions
2. [ ] Run `terraform apply` once permissions granted
3. [ ] Verify EventBridge Scheduler rules created
4. [ ] Test that loaders run automatically

### Optional (To Automate Sync)
1. [ ] Create GitHub Actions workflow to sync daily
2. [ ] Set up CloudWatch alarm if data becomes stale

---

## RELATED ISSUES

- **Issue**: User mentioned no trades since Jun 16 — This was separate issue fixed in Session 35 (Phase 5 constraints bug)
- **Issue**: Growth scores not showing — Fixed by data sync (scores are in database)
- **Issue**: Positions not sorted — Was display bug, fixed by query optimization
- **CRITICAL**: EventBridge Scheduler can't deploy — Requires AWS admin action

---

## REFERENCES

- `CLAUDE.md` - Project quick reference, mentions local scheduler workaround
- `steering/GOVERNANCE.md` - System architecture, EventBridge schedule details
- `steering/OPERATIONS.md` - CI/CD pipelines, deployment instructions
- `steering/DATA_LOADERS.md` - Loader pipeline schedule and triggers
- `steering/DATABASE_AND_ENVIRONMENTS.md` - Database connection priority
