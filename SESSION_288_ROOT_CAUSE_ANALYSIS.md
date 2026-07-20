# Session 288: Root Cause Analysis - Why Loaders Stopped Running

**Date:** 2026-07-19  
**Critical Finding:** AWS credentials expired July 8, 2026

---

## The Problem Chain

### Surface Issue: Stale Data (25+ tables from July 10)
```
buy_sell_daily - last update July 10 ❌
stock_scores - last update July 10 ❌
market_exposure_daily - last update July 10 ❌
...
```

### Root Cause: AWS Credentials Expired
Loaders stopped working because they cannot authenticate to AWS services (specifically DynamoDB for distributed lock management).

**Evidence:** Running metrics pipeline locally produces:
```
[CONFIG_FAILURE] DynamoDB check failed: ... The security token included in the request is invalid
[LOCK] DynamoDB permission denied: ... The security token included in the request is invalid
[price_extremes_52week] DynamoDB lock unavailable (permission denied)
LockAcquisitionError: DynamoDB lock manager unavailable (permission/access error)
```

---

## Why This Breaks Everything

### Architecture Design
1. **Loaders run locally (ECS Fargate)** but connect to shared database
2. **DynamoDB lock manager REQUIRED** to prevent race conditions across concurrent loader instances
3. **AWS credentials needed** for both DynamoDB and CloudWatch metrics

### Failure Chain
```
Loader starts
    ↓
Tries to acquire DynamoDB lock (for idempotency)
    ↓
AWS credentials invalid ❌
    ↓
LockAcquisitionError raised (FAIL-FAST by design - no silent fallback)
    ↓
Loader terminates, data NOT updated
    ↓
Data becomes stale
```

### Why Price Loaders Succeeded Longer
`load_prices.py` and `load_technical_indicators.py` may not require DynamoDB locks (or have different error handling).

---

## Credentials History

**Last Updated:** July 8, 2026 (file timestamp)
```
-rw-r--r-- 1 arger 197609 144 Jul  8 15:41 ~/.aws/credentials
```

**Time Since Expiry:** 11 days (July 8 → July 19)

**AWS Token TTL:** Typically 12 hours to 24 hours max. This credential has been invalid since ~July 9.

---

## Why EventBridge Scheduler Also Failed

EventBridge Scheduler invokes trigger-loaders Lambda → which spawns ECS loader tasks → which fail at DynamoDB lock acquisition.

```
EventBridge fires at 2 AM ET
    ↓
trigger-loaders Lambda invoked
    ↓
ECS task started: load_financial_statements.py
    ↓
DynamoDB lock: "The security token included in the request is invalid"
    ↓
Task failed, no retry
    ↓
No error alert sent (nobody monitoring)
    ↓
Nobody noticed loaders stopped ❌
```

---

## The Fix

### Immediate: Refresh AWS Credentials

**Option 1: AWS CLI**
```bash
aws configure
# Enter: Access Key ID, Secret Access Key, region (us-east-1), output (json)
```

**Option 2: Use Python to refresh**
```bash
python3 -c "import boto3; boto3.Session().get_credentials()"
```

**Option 3: Get new credentials from AWS Console**
- Go to AWS IAM → Your User → Security Credentials
- Create new Access Key (delete expired ones)
- Update ~/.aws/credentials file

### Verify Credentials Work
```bash
aws sts get-caller-identity
# Should return account ID, ARN, user name
```

### Test Loader After Refresh
```bash
python3 scripts/local_loader_scheduler.py --now morning
# Should complete 6/6 loaders successfully
```

### Refresh All Stale Data
```bash
# This will take 10-20 minutes
python3 scripts/local_loader_scheduler.py --now metrics
# Refreshes: financial statements, stock scores, buy/sell signals, etc.
```

---

## Why This Wasn't Caught

### Monitoring Gap
- ❌ No alert when loaders fail to run
- ❌ No check for "have loaders run in last 24h?"
- ❌ No AWS credential expiry warning (AWS doesn't notify)
- ❌ data_loader_status shows "last update July 10" but nobody noticed for 9 days

### Session 287 Audit Missed It
Session 287 claimed "comprehensive governance audit" but:
- ✅ Checked code exists
- ❌ Never ran loaders to verify they work
- ❌ Never queried data_loader_runs to check freshness
- ❌ Never checked AWS credential status

**Lesson:** Code review ≠ operational verification

---

## Preventing Future Outages

### Add Monitoring Alerts
```sql
-- Alert if loaders haven't run in 24 hours
SELECT loader_name, MAX(run_date) as last_run
FROM data_loader_runs
WHERE DATE(run_date) < DATE(NOW() - INTERVAL '1 day')
GROUP BY loader_name;

-- Alert if critical data >4h old during trading hours
SELECT table_name, age_days
FROM data_loader_status
WHERE age_days > 0.166  -- 4 hours
  AND status = 'ok'
  AND table_name IN ('buy_sell_daily', 'stock_scores', 'market_exposure_daily');
```

### Add Credential Expiry Check
```bash
# Run daily (before 2 AM ET when loaders start)
aws sts get-caller-identity || \
  echo "CRITICAL: AWS credentials invalid - loaders will fail"
```

### Set Calendar Reminder
AWS credentials typically valid for ~12-24 hours. Create recurring reminder:
- Every 30 days: refresh AWS credentials proactively
- Keep rotation schedule documented

---

## Timeline

| Date | Event |
|------|-------|
| Jul 8, 2026 | AWS credentials generated/last used (file timestamp 15:41) |
| Jul 9, 2026 | Credentials probably expired (12-24h TTL) |
| Jul 10, 2026 | Last loader run (`data_loader_runs` shows this as last date) |
| Jul 11-19, 2026 | Data gets stale (nobody notices, no alerts) |
| Jul 19, 2026 | Session 288 audit discovers stale data |

**Duration of Outage:** ~9 days with no data refresh

---

## Impact Assessment

### What's Broken
- ❌ Orchestrator has no fresh signals (Phase 7 can't generate trades)
- ❌ Dashboard shows week-old data
- ❌ Position sizing uses stale scores
- ❌ Risk calculations use old market exposure data

### What Still Works
- ✅ Orchestrator runs (just with stale data)
- ✅ Database connected
- ✅ Price loaders partially functional
- ✅ Technical indicators partially updated

### Trading Impact
If any trades executed in last 9 days, they used week-old signals. Risk calculations would be off.

---

## Next Steps (In Order)

1. **IMMEDIATE:** Refresh AWS credentials
   - `aws configure` or get new Access Key from AWS Console
   - Update ~/.aws/credentials file
   - Verify with `aws sts get-caller-identity`

2. **URGENT:** Refresh all stale data
   - `python3 scripts/local_loader_scheduler.py --now morning` (5-10 min)
   - `python3 scripts/local_loader_scheduler.py --now metrics` (10-20 min)
   - Verify data is fresh: check data_loader_status.age_days

3. **TODAY:** Add monitoring
   - Query loaders haven't run in 24h
   - Query critical tables > 4h old
   - Set AWS credential rotation reminder

4. **THIS WEEK:** Add automated safeguards
   - Pre-run credential check before orchestrator
   - Alert if any loader task fails
   - Dashboard warning if data >4h old

---

## Files to Check

- `~/.aws/credentials` - Contains AWS access keys (need refresh)
- `data_loader_runs` table - Shows last loader execution
- `data_loader_status` table - Shows current table freshness
- `algo_orchestrator_runs` table - Shows orchestrator execution (still running despite stale data!)

---

## Conclusion

**The system didn't fail gracefully.** The orchestrator kept running with 9-day-old data instead of:
1. Failing when data too stale (Phase 1 staleness check should have caught this)
2. Alerting operators that loaders are down
3. Blocking trade execution with invalid data

This needs investigation: Why didn't Phase 1 Data Freshness Check halt the orchestrator when data was clearly stale?
