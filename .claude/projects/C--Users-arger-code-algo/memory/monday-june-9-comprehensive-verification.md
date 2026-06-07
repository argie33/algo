---
name: monday-june-9-comprehensive-verification
description: Complete end-to-end AWS verification plan for Issues #2, #4, #13 on Monday June 9
metadata:
  type: project
---

# Monday June 9, 2026 — Comprehensive AWS Verification Plan

**Goal:** Verify 3 critical issues are working in production via CloudWatch logs and AWS Console.

**Status:** All code deployed (commits 5a161a89c, 4b930facd, 3e5f887aa). Ready for Monday execution.

---

## Issue #13: Health Endpoint Signal Freshness ✅ ALREADY LIVE

**Status:** Verified LIVE Saturday June 7, 01:02 UTC

**Verification:** Can test anytime (endpoint always available)

```bash
# Command to test
curl -s "https://d2u93283nn45h2.cloudfront.net/api/health" | jq '.data | {freshness, degraded_mode_active, rds_connection_pool}'

# Expected response (Saturday):
# - statusCode: 200
# - signal_age_hours: ~160+ (weekend, no loaders)
# - degraded_mode_active: true (expected on weekend)
# - rds_connection_pool.status: HEALTHY
```

**Commit:** 3e5f887aa (CORS fix) + earlier freshness implementation

---

## Issue #2: Loader Completion Detection & Symbol Coverage ✅ DEPLOYED

**Scheduled:** Monday June 9, 2:00 AM ET (06:00 UTC) — 2:45-3:45 AM ET (06:45-07:45 UTC)

**What it does:**
- Detects hung/crashed loaders via `execution_started` vs `execution_completed` timestamps
- Validates symbol coverage >= 90% per loader
- Halts Phase 1 if any loader missing execution_completed or coverage < 90%

**How to verify:**

### Step 1: Check CloudWatch Logs (Monday 06:45 UTC / 2:45 AM ET)

**Log Group:** `/aws/ecs/algo-loaders`

**Search Pattern 1 - Loader Completion:**
```
fields @timestamp, loader_name, execution_completed, completion_pct, symbols_loaded, symbol_count
| filter ispresent(execution_completed)
| stats count() as loaders_completed
```

**Expected Output:**
- 5 loaders completed (stock_prices_daily, technical_data_daily, buy_sell_daily, signal_quality_scores, swing_trader_scores)
- completion_pct near 100%
- symbol_count matches symbols_loaded

**Search Pattern 2 - Symbol Coverage Validation:**
```
fields @timestamp, loader_name, symbols_loaded, symbol_count
| filter ispresent(symbol_count)
| stats count(symbol_count) as validation_checks by loader_name
| filter validation_checks > 0
```

**Expected Output:**
- All core loaders show symbol counts
- No HALT messages for coverage <90%

**Search Pattern 3 - Failure Detection:**
```
"execution_completed" and ("null" or "missing")
```

**Expected:** No matches (no hung loaders)

### Step 2: Check RDS Database (Monday 07:00 UTC / 3:00 AM ET)

**Connect to RDS:**
```bash
# Use AWS Secrets Manager credentials or local dev profile
psql -h [RDS_HOST] -U [DB_USER] -d algo_db
```

**Query 1 - Loader Execution Tracking:**
```sql
SELECT 
  loader_name,
  execution_started,
  execution_completed,
  symbols_loaded,
  symbol_count,
  EXTRACT(EPOCH FROM (execution_completed - execution_started))/60 as duration_minutes
FROM data_loader_status
WHERE execution_started > NOW() - INTERVAL '1 hour'
ORDER BY loader_name;
```

**Expected Output:**
```
loader_name           | execution_started     | execution_completed   | symbols_loaded | symbol_count | duration_minutes
stock_prices_daily    | 2026-06-09 06:02:15 | 2026-06-09 06:17:30 | 5000          | 5000         | 15.25
technical_data_daily  | 2026-06-09 06:18:00 | 2026-06-09 07:48:45 | 4950          | 5000         | 90.75
buy_sell_daily        | 2026-06-09 07:50:00 | 2026-06-09 08:20:30 | 5000          | 5000         | 30.50
signal_quality_scores | 2026-06-09 08:22:00 | 2026-06-09 08:52:15 | 5000          | 5000         | 30.25
swing_trader_scores   | 2026-06-09 08:54:00 | 2026-06-09 09:24:45 | 5000          | 5000         | 30.75
```

**Success Criteria:**
- ✅ All 5 loaders have BOTH execution_started AND execution_completed (no nulls)
- ✅ execution_completed > execution_started (timestamps are valid)
- ✅ Total duration < 450 minutes (should be ~230 min)
- ✅ symbols_loaded >= symbol_count * 0.90 (≥90% coverage)

### Step 3: Check Phase 1 Validation Logs (Monday 07:30 UTC / 3:30 AM ET)

**Log Group:** `/aws/lambda/algo-algo-dev`

**Search Pattern:**
```
"Phase 1" AND ("symbol_coverage" OR "execution_completed")
| filter ispresent(@message)
```

**Expected:**
- Logs showing symbol coverage checks passing (no HALT)
- Logs showing execution_completed validation (recent timestamps)

---

## Issue #4: Morning Prep Timing (2:00 AM ET Start) ✅ DEPLOYED

**Scheduled:** Monday June 9, 2:00 AM ET (06:00 UTC)

**What it does:**
- Starts morning prep pipeline at 2:00 AM ET
- Provides 450-minute safety buffer until 9:30 AM orchestrator
- Ensures all loaders complete before day-session trades

**How to verify:**

### Step 1: Verify EventBridge Rule in AWS Console (Can do anytime)

**AWS Console Path:** EventBridge → Scheduler → Schedules

**Look for:**
- Schedule name: `algo-morning-prep-pipeline-dev` (or similar)
- Schedule expression: `cron(0 2 ? * MON-FRI *)`
- Timezone: `America/New_York`
- Next run (Monday): 2026-06-09 06:00:00 UTC (2:00 AM ET)
- Status: ENABLED

### Step 2: Check Step Functions Execution (Monday 06:05 UTC / 2:05 AM ET)

**AWS Console Path:** Step Functions → Executions → morning-prep-pipeline-dev

**Look for:**
- Execution started at: 06:00-06:02 UTC (2:00-2:02 AM ET)
- Status: RUNNING (or SUCCEEDED if checking after completion)

**Expected Timeline:**
- 06:00 UTC: Execution started
- 06:02-06:17 UTC: stock_prices_daily (15 min)
- 06:18-07:48 UTC: technical_data_daily (90 min, parallel with market_health)
- 07:50-08:20 UTC: buy_sell_daily (30 min)
- 08:22-09:25 UTC: signal_quality_scores + swing_trader_scores (45 min parallel)
- 09:26-09:30 UTC: Completed, ready for 9:30 AM orchestrator
- Total: ~3h 30min (well within 7h 30min buffer)

### Step 3: Check CloudWatch Logs for Start Time (Monday 06:05 UTC)

**Log Group:** `/aws/states/algo-eod-pipeline-dev` or `/aws/states/morning-prep-pipeline-dev`

**Search Pattern:**
```
"Execution started" OR "morning_prep_pipeline"
| fields @timestamp, msg, executionArn
```

**Expected:**
- Timestamp: ~2026-06-09T06:00:00Z
- Clear indication morning prep started at intended time

---

## Success Checklist

### ✅ Issue #2 (Loader Completion)
- [ ] CloudWatch: 5 loaders with execution_completed timestamps
- [ ] CloudWatch: No HALT messages for symbol coverage
- [ ] RDS: All 5 loaders in data_loader_status with both timestamps
- [ ] RDS: symbols_loaded >= 90% for each loader
- [ ] Phase 1 logs: Show validation passing (no stale data halts)

### ✅ Issue #4 (Morning Prep Timing)  
- [ ] EventBridge: Schedule rule shows 2:00 AM ET (06:00 UTC)
- [ ] EventBridge: Rule is ENABLED and next run is Monday
- [ ] Step Functions: Execution started at 06:00-06:02 UTC
- [ ] Step Functions: Execution timeline completes by 09:30 UTC
- [ ] CloudWatch: Logs show start time at expected 06:00 UTC

### ✅ Issue #13 (Health Endpoint)
- [ ] Health endpoint returns HTTP 200
- [ ] Health endpoint includes signal_age_hours field
- [ ] Health endpoint includes CORS headers
- [ ] degraded_mode_active reflects actual system state

---

## Failure Scenarios & Debugging

### Scenario A: Loader Missing execution_completed

**Symptom:** CloudWatch shows execution_started but no execution_completed

**Root Cause:** Loader hung/crashed or task terminated before completion

**Debug Steps:**
1. Check CloudWatch logs for loader errors: `/aws/ecs/algo-loaders`
2. Check ECS task status: ECS → Clusters → Tasks → look for STOPPED tasks
3. Check RDS connection pool: Is it exhausted (high CPU)?
4. Check yfinance API status: Is rate limiting kicking in?

**Fix:**
- If rate limiting: Reduce batch size or increase timeout in algo_config
- If RDS: Check connection pool, increase RDS Proxy max_connections
- If hung task: Rerun manually with `aws ecs run-task...`

### Scenario B: symbol_coverage < 90%

**Symptom:** CloudWatch shows coverage < 90% for one loader

**Root Cause:** Partial API failure, batch timeout mid-load, or data fetch error

**Debug Steps:**
1. Check which loader failed: Filter CloudWatch by loader_name
2. Check batch processing logs: Look for "batch =[N]" with 429 errors
3. Check yfinance rate limiting: Is batch hitting 200/min limit?

**Fix:**
- If rate limiting: Early abort at batch 15 instead of waiting
- If timeout: Increase failsafe_grace_period in algo_config
- If data error: Check individual symbol in yfinance manually

### Scenario C: Morning Prep Didn't Start at 2:00 AM

**Symptom:** Step Functions execution started at wrong time

**Root Cause:** EventBridge rule misconfigured or timezone wrong

**Debug Steps:**
1. AWS Console: EventBridge → Scheduler → Check schedule_expression
2. AWS Console: Check schedule_expression_timezone (should be America/New_York)
3. AWS Console: Check rule is ENABLED

**Fix:**
- If wrong time: Update Terraform `schedule_expression` and `schedule_expression_timezone`
- If disabled: Enable rule in AWS Console
- Run: `terraform apply` after fixing main.tf

---

## AWS Credentials for Monday

**Before Monday morning 06:00 UTC, ensure credentials are fresh:**

```powershell
# In PowerShell
. scripts/refresh-aws-credentials.ps1
```

This updates `$PROFILE` with fresh AWS credentials from Secrets Manager.

---

## Timeline Summary

| Time (ET) | Time (UTC) | Event | Verification |
|-----------|-----------|-------|--------------|
| 2:00 AM | 06:00 | Morning prep starts | Step Functions execution |
| 2:15 AM | 06:15 | Loaders running | CloudWatch logs active |
| 3:30 AM | 07:30 | Loaders mostly done | Symbol coverage checks |
| 9:30 AM | 13:30 | Orchestrator Phase 1-5 | Health endpoint will update |

**Verification can happen between 3:00-3:45 AM ET (07:00-07:45 UTC)**

---

## Success = All Three Pass

If all three issues pass verification on Monday:
- ✅ System can detect hung loaders (Issue #2)
- ✅ System starts at right time with proper buffer (Issue #4)
- ✅ System reports freshness to API consumers (Issue #13)

This means core morning data pipeline is reliable and ready for production trading signals.

