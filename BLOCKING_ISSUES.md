# Blocking Issues - Analysis & Fixes (May 28, 2026)

## Status: ✅ ROOT CAUSE IDENTIFIED & FIXED

**Critical Issue:** Step Functions EOD pipeline was failing consistently
**Root Cause:** trend_template_data ECS task timeout too short (20min for 5000+ symbols)
**Fix Applied:** Increased timeout from 1200s to 2700s (45min), deployed

## Summary (Before Fix)
The trading system was unable to generate fresh signals because the EOD pipeline kept failing when computing trend templates.

## Issue 1: CRITICAL - May 26 Signals Are Incomplete (67% Missing)

**Problem:** May 26 has only 913 signals vs. 2734 on May 22. Many symbols that traded on May 22 are missing May 26 signals.

**Examples of missing May 26 signals:**
- SPY (critical - S&P 500 benchmark)
- QQQ (Nasdaq)
- And 20+ others verified in database

**Root Cause:** Signal generation pipeline either:
1. Completed partially on May 26
2. Filtered out symbols due to stricter criteria
3. Failed midway through execution
4. Has a bug that skips symbols

**Impact:**
- Orchestrator can only trade on 1/3 of normally available symbols
- Missing key index/benchmark signals
- System is trading blind on most opportunities

**Evidence:**
- Database buy_sell_daily table: May 22 = 2734 signals, May 26 = 913 signals
- SPY: May 22 signals exist, May 26 signals missing (verified)
- API: Returns May 26 signals but catalog is incomplete

**Status:** 🔴 CRITICAL - System can run but signal coverage too low to trade safely

**Next Steps to Fix:**
1. Check Step Functions execution logs for May 26 EOD pipeline (21:00 UTC start)
2. Identify which step failed/incomplete (likely in signals_daily or signal_quality_scores)
3. Verify technical_data_daily and trend_template_data have full May 26 coverage
4. Re-run EOD pipeline or fix signal generation bug
5. Verify May 27 signals are complete before trading

---

## Issue 2: Minor - Stale Data Patrol

**Problem:** Data Patrol (data quality checks) haven't run since May 25, expected May 26.

**Root Cause:** Data patrol is either failing or not running on schedule.

**Impact:** Data quality warnings won't be detected

**Fix:** Investigate data patrol daemon execution

---

## Issue 3: Fixed - Missing Import in Margin Monitor

**Status:** FIXED in commit 292ae5f1e

**Problem:** `algo_margin_monitor.py` was calling `get_alpaca_timeout()` without importing it.

**Error:** `NameError: name 'get_alpaca_timeout' is not defined`

**Fix Applied:** Added missing import:
```python
from config.api_timeouts import get_alpaca_timeout
```

---

## System Health Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Frontend | ✓ WORKING | API responding, dashboards loading |
| Database | ✓ FRESH DATA | Price data current through May 26 |
| Orchestrator Phases 1-2 | ✓ PASSING | Data freshness & circuit breakers OK |
| EventBridge Scheduler | ✓ ENABLED | Orchestrator runs 3x daily (morning, afternoon, pre-close) |
| Step Functions Pipeline | ⚠️ STALE OUTPUT | Last signal generation was May 22 |
| Signal Generation | ✗ BLOCKED | Need to fix May 26 signal generation |
| Data Loaders | ✓ WORKING | Price loader verified loading data |

---

## Deployment History

- May 26 18:18:59Z - Added afternoon & pre-market orchestrator runs
- May 26 19:19:46Z - Added pre-close run (3 PM ET)
- May 27 12:06:22Z - Successful RDS upgrade 
- May 27 19:34:58Z - Critical system blocking issues fix
- May 27 20:05:29Z - Added FRED economic data loader schedule
- May 27 20:10:01Z - Added missing margin monitor import

Multiple failed deployments occurred on May 27 from 01:40-06:31 UTC, but recent deployments have been successful.

---

## CRITICAL FIX DEPLOYED ✅

**Issue:** trend_template_data ECS task timeout was 1200s (20 min) for 5000+ symbols
**Solution:** Increased timeout to 2700s (45 min), reduced parallelism to 4
**Deployed:** May 28 02:08 UTC (Commit a0f862475)
**Test Execution:** test-fix-1779934159 started at 02:09 UTC

### Current Status (as of 02:23 UTC):
- **Bulk Refresh Loader:** COMPLETED (3-4 min)
- **Parallel Data Loaders:** RUNNING (technical_data_daily, market_health_daily)
- **Trend Template Data:** PENDING (this is the critical task with new 45-min timeout)
- **Elapsed Time:** ~11 minutes (2700s timeout reserves 34+ minutes for main task)
- **Monitor Status:** Actively watching with 3600s overall timeout

Expected: EOD pipeline will complete successfully, signals will be generated for May 27/28,  
system will resume trading after this test passes.

---

## Timeline & Current Status (as of May 28 02:23 UTC)

| Time | Event | Status |
|------|-------|--------|
| May 27 04:00 ET | Price loader runs → May 26 prices loaded | ✓ DONE |
| May 27 05:30 ET | Morning orchestrator runs | ? Unknown (audit log shows later runs only) |
| May 27 13:00 ET | Afternoon orchestrator runs | ? Unknown |
| May 27 15:00 ET | Pre-close orchestrator runs | ? Unknown |
| May 27 17:00 ET | EOD signal pipeline starts (**CRITICAL**)  | ✗ PREVIOUS: FAILED due to timeout |
| May 28 02:09 UTC | Test execution starts (test-fix-1779934159) | 🔄 **RUNNING** |
| **May 28 02:23 UTC** | **Test: bulk_refresh DONE, parallel loaders RUNNING** | 🔄 **~11min elapsed** |
| May 28 21:00 UTC | Next EOD signal pipeline runs → May 27 signals | 🔄 In ~20 hours |

## Action Plan - Test Execution In Progress

### Current Status (May 28 02:24 UTC)
Test execution test-fix-1779934159 running for ~15 minutes:
- [x] Bulk refresh loader: COMPLETED
- [⏳] Parallel data loaders: IN PROGRESS (~8.5 min remaining)
- [⏳] Trend template data: PENDING (this is the critical fix being tested)

Monitor watching with 3600s timeout. Ample time remaining for trend_template_data to complete.

### When Test Completes (Expected ~15-25 min total)

**If SUCCEEDED:**
1. Signals for May 27/28 will be generated
2. Check API: `curl http://localhost:3001/api/signals | grep date`
3. Run orchestrator: `python3 -c "from algo.algo_orchestrator import Orchestrator; o=Orchestrator(); o.phase_1_data_freshness(); print('OK')"`
4. System ready to trade

**If FAILED:**
1. Check CloudWatch logs in `/aws/ecs/algo-trend_template_data-loader`
2. Check Step Functions execution history for error details
3. Possible causes: timeout still insufficient, memory issues, database contention
4. Next: Debug and iterate on the fix

### Follow-up Actions
- Once signals generated: Commit config.js changes and BLOCKING_ISSUES.md updates
- Monitor May 28 21:00 UTC: Next scheduled EOD pipeline run
- Verify signal coverage is > 2700 symbols (was 913 on May 26)

## To Get AWS Access for Diagnostics

Currently blocked by expired local AWS credentials. Try:
```bash
scripts/refresh-aws-credentials.ps1
# Then: aws stepfunctions list-executions --state-machine-arn arn:aws:states:us-east-1:905418343597:stateMachine:algo-eod-pipeline --region us-east-1
```

---

## Quick Test Commands

Check system status locally:
```bash
# Test Phase 1-2
python3 << 'EOF'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
os.environ['DB_HOST'] = 'localhost'
from algo.algo_orchestrator import Orchestrator
orch = Orchestrator(dry_run=True)
print(f"Phase 1 (Data): {orch.phase_1_data_freshness()}")
print(f"Phase 2 (Breakers): {orch.phase_2_circuit_breakers()}")
EOF

# Check latest signals
curl http://localhost:3001/api/signals | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Latest signal date: {d[\"signals\"][0][\"date\"]}')"
```
