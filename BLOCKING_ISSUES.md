# Blocking Issues Found - May 27, 2026

## Summary
The trading system is 95% operational but blocked by signal generation not running for May 26 (latest trading day).

## Issue 1: CRITICAL - No Fresh Signals Since May 22

**Problem:** API returns signals from May 22, but we're on May 27 (and May 26 was a trading day).

**Root Cause:** EOD Pipeline (Step Functions) that generates signals either failed or didn't run on May 26 at 5:00 PM ET.

**Impact:** 
- Orchestrator can run but has no new signals to trade on
- System effectively halted since May 22 signals

**Investigation:**
- ✓ Orchestrator Lambda deployed and configured 
- ✓ EventBridge Scheduler rules enabled and configured
- ✓ Step Functions state machine deployed
- ✓ EOD pipeline schedule: `cron(0 21 ? * MON-FRI *)` = 5:00 PM ET (ENABLED)
- ✓ Morning pipeline schedule: `cron(30 9 ? * MON-FRI *)` = 5:30 AM ET (ENABLED)
- ✗ No fresh signals generated on May 26

**Evidence:**
- `curl http://localhost:3001/api/signals?symbol=SPY` returns signals dated May 22
- Price data loaded up to May 26 (verified fresh via price loader)
- Phase 1 & 2 orchestrator checks pass locally

**Next Steps to Fix:**
1. Check Step Functions execution history for May 26 EOD pipeline run (requires AWS access)
2. If pipeline ran but failed, check CloudWatch logs for error
3. If pipeline didn't run, verify EventBridge rule was triggered
4. Once identified, fix the root cause and re-run pipeline

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

## To Unblock Trading

1. **Priority 1 - Fix Signal Generation:**
   - Access AWS CloudWatch to check Step Functions execution history
   - Find May 26 20:00-21:30 UTC (5:00-4:30 PM ET) EOD pipeline execution
   - Identify failure reason
   - Fix and re-run pipeline or manually trigger signal generation

2. **Priority 2 - Verify Orchestrator Execution:**
   - After signals are fresh, verify orchestrator runs at next scheduled time
   - Check Phase 5 (signal generation) outputs trading signals

3. **Priority 3 - Monitor Going Forward:**
   - Watch for Step Functions failures in CloudWatch Alarms
   - Verify signal generation pipeline runs daily at 5 PM ET

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
