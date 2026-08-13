# LOADING BRITTLENESS ROOT CAUSE AUDIT — SESSION 103

## Executive Summary
Every Monday (and throughout the week), the loading system fails with cascading brittleness. Today's investigation identified **5 interdependent root causes** that create a perfect storm of failures. Sessions 92-102 fixed individual symptoms but missed the systematic architectural issues.

---

## FINDINGS: THE BRITTLENESS CASCADE

### Issue #1: Subprocess Hangs at 0% Completion (NO RECOVERY)
**Status**: CRITICAL - **Prevents ALL pipelines from progressing**

Local observed evidence (2026-08-13 11:59:03):
```
price_daily          | RUNNING | 0.0% | started 11:59:03 | NO ERROR MESSAGE | NO PROCESS
etf_price_*.         | RUNNING | 0.0% | started 11:59:03 | NO ERROR MESSAGE | NO PROCESS
company_info_sec     | RUNNING | 0.0% | started 11:27:14 | NO ERROR MESSAGE | NO PROCESS
```

**Root Cause**:
- Subprocess hangs silently before writing first completion_pct update
- No error message → no visibility into what failed
- 0% completion persists indefinitely—Phase 1 failsafe can't detect "incomplete" (only < configured threshold)
- Downstream loaders (buy_sell depends on prices) block forever
- No timeout kicks in because subprocess may be hung (not CPU-bound, not running over time limit)

**Why Sessions 92-102 missed it**:
- Memory documents "timeout fixes" but subprocess stuck at 0% isn't a timeout—it's a hang
- Phase 1 failsafe monitors completion_pct >= threshold OR status == COMPLETED (line 1353-1367)
- 0% completion doesn't trigger either condition
- Silent hang = never detected, never retried, never failed over

**Why local dev is vulnerable**:
- yfinance rate limiting causes wait/backoff (not active CPU), so subprocess appears "running"
- Database locks on multi-symbol concurrent loads cause subprocess to wait indefinitely (lock contention)
- No per-phase watchdog to detect "stalled progress" (0% for >N minutes)

---

### Issue #2: Database Row Lock Cascade (Connection Pool Poisoning)
**Status**: CRITICAL - **Locks entire system after first loader failure**

Local observed evidence:
```
ERROR: INSERT into data_loader_status times out
CONTEXT: while inserting index tuple in relation "data_loader_status"
ERROR: SELECT with FOR UPDATE times out
CONTEXT: while locking tuple in relation "data_loader_status"
```

**Root Cause**:
- hung subprocess leaves transaction open with row lock
- LoaderStatusManager.mark_running() calls occur inside transaction
- If subprocess never returns, transaction never commits/rolls back
- Subsequent LoaderStatusManager calls wait for lock indefinitely
- After ~30 seconds, psycopg2 statement timeout fires
- Poisoned connection returned to pool
- Next operation on that connection fails

This is exactly the Session 95 "connection pool transaction abort cascade" issue, but the fix wasn't sufficient. The real issue is that hung subprocesses leave transactions hanging.

---

### Issue #3: Stale Lock Files Block Loaders
**Status**: MEDIUM - **Multiplies hangs and reduces parallelism**

Local observed evidence:
```
/tmp/algo-locks/company_info_sec.lock (stale, from 06:27, not cleaned)
```

**Root Cause**:
- Loaders acquire file lock before starting (lock_file.py pattern)
- Hung subprocess doesn't delete lock on exit
- Next loader invocation waits for lock indefinitely (blocks until timeout)
- local_loader_scheduler mentions this but doesn't auto-clean

**Why dangerous**:
- Multiplies hang duration (lock wait timeout + actual load timeout + retry overhead)
- Transforms one hung process into a 2-3 hour pipeline failure

---

### Issue #4: invoke_loader_retry() Has 900s Timeout But Prices Need 1440m
**Status**: HIGH - **Makes retries impossible for long loaders**

Code (algo/orchestrator/phase1_failsafe_retry.py line 1247-1252):
```python
result = subprocess.run(
    [sys.executable, "scripts/run_loader.py", loader_name, "--force-refresh"],
    capture_output=True,
    text=True,
    timeout=900,  # 15 minute timeout
)
```

Timeout configuration (loaders/loader_timeout_config.py):
```python
"prices": 1440 * 60,  # 1440 min (24h) - accommodate yfinance rate limiting slowdown
```

**The Problem**:
- Local scheduler uses correct 1440m timeout (line 482: `scheduler_timeout = int(timeout * 1.1)`)
- But Phase 1 failsafe retry hardcodes 900s (15 min) regardless of configured loader timeout
- If prices fail during normal morning pipeline run, Phase 1 failsafe can NEVER retry it
  (subprocess times out after 15 min, long before prices' 24h budget runs out)
- Retry becomes impossible → stale data Monday

---

### Issue #5: 0% Completion Not Detected as "Stalled" By Failsafe
**Status**: HIGH - **Prevents detection of hung loaders**

Code (phase1_failsafe_retry.py, line 1353-1367):
```python
elif completion_pct >= min_completion_pct:
    logger.info(f"[PHASE 1 FAILSAFE] Loader recovered: {loader_name} {completion_pct:.1f}%")
    return True, completion_pct, "success"
elif status == "COMPLETED":
    logger.critical(f"[PHASE 1 FAILSAFE] Loader completed but dangerously incomplete: {loader_name} {completion_pct:.1f}%")
    return False, completion_pct, "failed"
```

**The Problem**:
- Monitors for: "completion >= threshold" OR "status == COMPLETED"
- Neither is true for hung subprocess (status=RUNNING, completion=0%)
- Monitor loop just sleeps 10 seconds and checks again
- After timeout_seconds elapsed, returns (False, None, "timeout")
- But original subprocess is STILL RUNNING in background, now unreachable

**Why it matters**:
- Hung subprocess never transitions out of RUNNING
- Status update for "still_failing" applies mark_failed() logic (line 380-381 in check_and_retry_incomplete_loaders)
- But mark_failed() calls go to LoaderStatusManager, which hangs on row lock
- Retry loop stalls waiting to record retry failure

---

## MONDAY CASCADE SEQUENCE

This is why Monday always fails:

1. **Friday afternoon**: Prices loader (or company_info) starts, hits yfinance rate limit + database lock contention
2. **Friday 17:00**: Subprocess hangs at 0% completion, never updates status
3. **Friday 18:00**: Morning orchestrator (or manual backfill) tries to retry—Phase 1 failsafe subprocess times out after 15 min (prices needs 24h)
4. **Friday 18:30**: Try to mark retry as failed—database lock on company_info_sec row blocks mark_failed()
5. **Friday 19:00**: Connection pool poisoned, all subsequent DB ops hang
6. **Saturday 00:00**: Still RUNNING at 0%, lock file still exists, reap_stale_running_loaders() hasn't run yet (only runs on pipeline invoke)
7. **Monday 09:30**: Morning pipeline starts, tries to load prices again, acquires same stale lock file (never cleaned), hangs again
8. **Monday 11:00**: Phase 1 detects stale data from Friday, tries failsafe retry—same 900s timeout insufficient, subprocess times out
9. **Monday 12:00**: Everything halted, manual backfill required

---

## SESSIONS 92-102 ANALYSIS: What They Fixed vs. What They Missed

### What Sessions 92-102 Got Right:
1. ✅ Timeout configuration increases (prices 900m→1440m)
2. ✅ Circuit breaker 1.5x buffer for >90% completion
3. ✅ Failsafe retry 85% conservative threshold
4. ✅ Pre-marking tables RUNNING before subprocess (prevents NOT_STARTED stuck state)
5. ✅ Central loader timeout config (fail-fast on unregistered)

### What They Missed:
1. ❌ **Subprocess hang at 0%** (no progress monitoring)
2. ❌ **Stale lock file cleanup** (recommends manual `rm` but doesn't auto-cleanup)
3. ❌ **invoke_loader_retry() 900s hardcoded timeout** (way too short for real loaders)
4. ❌ **Connection pool transaction rollback** (still not auto-rollback on hung subprocess)
5. ❌ **Stalled progress detection** (can't distinguish "hung at 0%" from "just started")

---

## IMPACT ASSESSMENT

**Why this matters for production**:
- Local dev shows the exact same cascade that happens in production
- AWS ECS task timeouts + CloudWatch monitoring are manual, not automatic recovery
- No auto-cleanup of stale state between runs
- Manual operator backfill is the only "recovery" → operator burden, delayed trading

**Scope**:
- Affects every loader execution locally
- Cascades to downstream loaders (buy_sell depends on prices)
- Blocks entire orchestrator runs (Phase 1 freshness check halts when prices stale)

---

## RECOMMENDED FIXES (Session 103)

Priority order:

### P0: Auto-Cleanup Stale Locks Before Each Pipeline Run
- Before invoking any loaders, check `/tmp/algo-locks/` for files older than 30 min
- Delete them with warning
- Prevents multiplied hang duration

### P0: Detect Stalled Progress in Local Subprocess
- Pre-subprocess: record timestamp when subprocess starts
- During failsafe retry monitoring: if 0% completion for >5 minutes, mark FAILED immediately
- Don't wait for full timeout_seconds if progress is stalled

### P1: Fix invoke_loader_retry() Timeout for LOCAL_MODE
- Use configured loader timeout, not hardcoded 900s
- For prices: use 1440m (same as local_loader_scheduler)
- Allows actual retry instead of premature timeout

### P1: Connection Pool Rollback on Hung Subprocess
- Detect if subprocess exited abnormally (returncode != 0 or hung)
- Force rollback on any pooled connection from that subprocess
- Prevent poison connection from affecting subsequent operations

### P2: Improve Subprocess Error Visibility
- Run subprocess with stderr capture (local_loader_scheduler does this, good!)
- But Phase 1 failsafe should also capture stderr, not just return/timeout
- Update data_loader_status.error_message with last 50 lines of stderr

---
