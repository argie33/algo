# Root Cause Analysis - Session 109: Loader Brittleness

## CRITICAL FINDINGS

### Issue #1: Loader Lock Expiry Too Long (24+ Hours)
**Severity**: CRITICAL
**Impact**: Single crashed loader blocks ALL subsequent runs for 24 hours
**Current Behavior**:
- Loader timeout configured for 1440 minutes (24h)
- Lock expiry = timeout + 300s ≈ 24 hours
- Previous crashed loader's atexit handler didn't fire (crash before atexit registration)
- Lock remains held until 24-hour expiry
- Every subsequent loader run immediately fails with "Another instance already running"

**Root Cause**: Lock expiry tied to loader timeout, which for prices is 24h due to yfinance rate limiting

**Fix Required**:
- Separate lock expiry from loader execution timeout
- Use shorter default (30min-2h) for lock expiry
- Or: Implement lock heartbeat - crashed process stops updating, lock auto-released

---

### Issue #2: Loader Progress Monitor Kills at 0% After 300s (5min)
**Severity**: HIGH
**Status**: Unfixed in previous sessions
**Current Behavior**:
- local_loader_scheduler monitors progress every 30s
- Kills loader if stuck at 0% for >300s (5 minutes)
- stability_metrics killed after 300s with no progress
- price_daily killed after 300s with no progress

**Why Loaders Stuck at 0%**:
- Loader starts but can't acquire lock (locked by previous crashed instance)
- Exits immediately with "Another instance already running"
- Progress never updated → looks like 0% stall
- 5-minute threshold kills it, marks FAILED
- But atexit handler registered before lock check → lock never releases from previous run

**Root Cause**: Lock acquired AFTER progress monitoring starts but BEFORE atexit registered

**Fix Required**:
- Acquire lock FIRST, before progress monitoring setup
- Register atexit handler IMMEDIATELY after lock acquired
- Don't kill loaders based on 0% if they failed to start (check error_message vs stall)

---

### Issue #3: LOCAL_MODE Parallelism Override (Non-Critical But Wrong)
**Severity**: MEDIUM
**Status**: Fixed in config.py but misleading

**Problem**: In LOCAL_MODE, code bumps max parallelism to 8, but:
- Memory explicitly says yfinance blocks at parallelism >= 2
- local_loader_scheduler correctly sets LOADER_PARALLELISM=1
- But if env var not set, config.py would use constraint max (which is bumped to 8)

**Current Status**: Working correctly because LOADER_PARALLELISM=1 is set by local_loader_scheduler before subprocess

**Fix Recommended**: Remove the "bump to 8" logic in config.py; respect per-loader constraints as-is

---

## RECOMMENDED FIXES (Priority Order)

### Priority 1: Separate Lock Expiry from Loader Timeout
**File**: loaders/load_prices.py (and other loaders with lock code)

Current (line 3497):
```python
_lock_expiry_sec = max(execution_timeout_sec + 300, 600)
```

Fix:
```python
# Lock expiry should be SHORT to recover from crashes
# Separate from loader execution timeout (which may be 24h for yfinance rate limiting)
_lock_expiry_sec = max(300, 600)  # 5-10min lock expiry, not 24h
```

### Priority 2: Acquire Lock BEFORE Starting Progress Monitoring
**File**: loaders/load_prices.py (lines 3480-3575)

Move lock acquisition to BEFORE atexit registration is even a possibility.
Currently lock is acquired at line 3515, but atexit registered at line 3552.

If crash happens between those lines, lock is held but atexit never registered.

### Priority 3: Fix Progress Monitor False Positives
**File**: scripts/local_loader_scheduler.py (lines 39-105)

The _monitor_loader_progress() function checks if stalled at 0%, but this is a false positive if:
- Loader failed to acquire lock (returns immediately with error)
- Loader crashed before first progress update

Add logic to check error_message before killing:
```python
if completion_pct == 0 and stalled:
    # Check if loader actually TRIED to run or just failed to start
    # If error_message indicates "lock held" or other startup failure,
    # DON'T kill - let Phase 1 failsafe handle it
```

### Priority 4: Remove Parallelism Bump in LOCAL_MODE
**File**: utils/loaders/config.py (line 343)

Remove or comment out:
```python
if os.getenv("LOCAL_MODE") in ("true", "1"):
    max_parallelism = max(max_parallelism, 8)  # <-- REMOVE THIS
```

This is misleading and contradicts memory about yfinance rate limiting.

---

## TESTING PLAN

1. Delete all stale loader_execution_locks
2. Run `python loaders/load_prices.py` directly - should work
3. Interrupt it mid-run (Ctrl+C) - verify atexit releases lock
4. Run again immediately - should acquire fresh lock
5. Run local_loader_scheduler --now morning - should complete without lock conflicts

---

## SUMMARY

Monday brittleness root cause: Crashed loader from Friday holds 24-hour lock, blocking all Monday runs. Every Monday morning, first loader attempt fails "Another instance already running", cascading to stale data.

Fix: Separate lock expiry (5-10min) from execution timeout (24h). Ensures crashed loaders don't block future runs.
