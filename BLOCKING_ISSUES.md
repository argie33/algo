# Blocking Issues Found - May 27, 2026

## Summary
The trading system is operational but has incomplete signal coverage. May 26 signals exist but are only 33% coverage (913/2734 symbols).

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
