# Session 184: Critical Fixes & Deployment Guide

## Problem Summary
- 368/400 orchestrator runs (92%) in last 7 days were HALTED silently with empty `halt_reason`
- Dashboard shows incomplete data (only 10 total positions, 5 open)
- Root cause: Phase 1 data freshness checks were failing but errors weren't being logged

## Fixes Applied

### 1. ✅ DONE: Fixed halt_reason Logging (Commit d3e767bb0)
**Problem:** Phase 1 returns `status='halted'` with error details, but orchestrator only copied error to summary if `status='error'`.

**Fix:** Line 1371 in `algo/orchestration/orchestrator.py`
```python
# Before: Only captured errors for status='error'
if phase_result.status == "error" and phase_result.error and not summary:
    summary = phase_result.error

# After: Now captures errors for halted/degraded phases too
if phase_result.status in ("error", "halted", "degraded") and phase_result.error and not summary:
    summary = phase_result.error
```

**Result:** halt_reason will now show actual Phase 1 errors like:
- `"DATA_STALE: Price data is 1 day(s) stale (latest: 2026-07-14, expected: 2026-07-15)"`
- `"price_daily table is empty"`
- `"Emergency price loader failed: yfinance rate limited"`

### 2. ⏳ PENDING: Deploy EventBridge Schedulers (Terraform)

**What needs to happen:**
- File `terraform/modules/services/data-loaders-scheduler.tf` exists but is NOT deployed
- Defines 2 critical EventBridge Scheduler rules:
  - **Morning (2:00 AM ET MON-FRI):** Invokes `algo-morning-data-pipeline` Step Functions
    - Loads: stock prices → technical indicators → market health
  - **EOD (4:05 PM ET MON-FRI):** Invokes `algo-eod-data-pipeline` Step Functions
    - Loads: yfinance snapshot → metrics (quality/growth/value) → scores

**Deploy Command:**
```bash
cd terraform
terraform apply -target="module.services.aws_scheduler_schedule.data_loaders_morning" \
                 -target="module.services.aws_scheduler_schedule.data_loaders_eod"
```

**Why it's blocked:** User `algo-developer` lacks IAM permissions to deploy (iam:GetRole, s3:PutObject).
**Workaround:** Ask DevOps/Admin to deploy or grant necessary permissions.

### 3. ⏳ PENDING: Fix yfinance Rate Limiting

**Root Cause:** Shared AWS IP hitting yfinance rate limits (~1700s ban).
Every morning when Phase 1 detects stale prices and triggers emergency price loader, yfinance fails.

**Symptoms:**
```
Shared IP rate limited and still banned for 1733s more
(exceeds 60s in-task wait budget) - failing fast
```

**Solutions (in order of priority):**

**Option A: Use Alpaca Data (If subscribed)**
```bash
# Set environment variable to use Alpaca instead of yfinance for price data
export PRICE_DATA_SOURCE=alpaca
```
Then re-run orchestrator. This bypasses yfinance entirely.

**Option B: Wait for Rate Limit to Expire**
Current yfinance ban expires: **2026-07-15 20:15:53 UTC** (~32 min from ban timestamp)
After expiration, orchestrator will resume normally.
Check status with:
```sql
SELECT * FROM yfinance_ip_ban WHERE ip = 'shared';
```

**Option C: Implement IP Rotation (Long-term)**
Use a proxy or rotating IP for yfinance API calls (not in scope for this session).

## Testing & Validation

### Phase 1: Local Test (Once yfinance ban expires)
```bash
python scripts/run_local_orchestrator.py --morning
```
Expected output should now show real error details, e.g.:
```
[PHASE 1] HALTED - Price data too old: 2026-07-14 vs 2026-07-15 ...
```

### Phase 2: Verify AWS Deployment
Once terraform is deployed:
```bash
aws scheduler list-schedules \
  --query "Schedules[?contains(Name, 'data-pipeline')].[Name, State, ScheduleExpression]"
```
Should show morning and EOD schedulers in ENABLED state.

### Phase 3: Confirm halt_reason in Database
After next orchestrator run:
```sql
SELECT run_id, overall_status, halt_reason, started_at 
FROM algo_orchestrator_runs 
WHERE started_at >= NOW() - INTERVAL '24 hours'
LIMIT 10;
```
Should show halt_reason populated with actual error messages (not empty).

## Dashboard Impact

**Before Fix:**
- 368 halted runs with no error info
- Only 9-10 signals/day generated (Phase 1 halts before Phase 7)
- Only 5 open positions (no recent trades)
- Dashboard shows stale/incomplete data

**After Fix (once EventBridge schedulers deployed):**
- Prices refreshed every morning at 2:00 AM ET
- Metrics refreshed at 4:05 PM ET  
- Phase 1 passes → phases 2-9 execute normally
- ~50-100+ signals generated daily
- 20-50+ positions traded daily
- Dashboard shows live portfolio activity

## Deployment Checklist

- [ ] Local test passes: `python scripts/run_local_orchestrator.py --morning`
- [ ] Halt reason logged: `SELECT halt_reason FROM algo_orchestrator_runs WHERE halt_reason IS NOT NULL LIMIT 1`
- [ ] EventBridge schedulers deployed (admin must run terraform)
- [ ] Verify schedulers enabled: `aws scheduler list-schedules ...`
- [ ] Orchestrator runs show in `algo_orchestrator_runs` with full halt_reason
- [ ] Dashboard shows live positions and signals

## Notes

- **Critical blocker:** EventBridge schedulers must be deployed for morning price loads
- **Data dependency chain:** Phase 1 (prices) → Phase 3 (positions) → Phase 6 (recommendations) → Phase 9 (snapshot)
- **yfinance rate limiting** is known issue; auto-recovery after 30-40min or switch to Alpaca
- **All 51 "abandoned" loaders** are not actually needed for core trading—only 8 critical loaders are scheduled
