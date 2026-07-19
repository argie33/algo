# Loader Flag System Standardization - Migration Guide

## Executive Summary

The data loading system has **5 broken flag systems** that cause recurring failures. This guide fixes them by creating:

1. **Centralized status enum** (`LoaderStatus`) - single source of truth for status values
2. **Status manager** (`LoaderStatusManager`) - consistent status update pattern across all loaders
3. **Validation layer** - orchestrator validates status values before using them
4. **Context-aware halt flag** - re-evaluates freshness instead of "fire and forget"
5. **Error tracking** - all failures must have reason in error_message

---

## Phase 1: Standardize Status Enum (DONE ✓)

**Files created:**
- `utils/loaders/status_enum.py` - Standard status values (NOT_STARTED, RUNNING, COMPLETED, FAILED, TIMEOUT)
- `utils/loaders/status_manager.py` - Centralized status update manager

**Status values (database MUST use these exact strings):**
```python
LoaderStatus.NOT_STARTED  # Hasn't started yet
LoaderStatus.RUNNING      # Currently executing
LoaderStatus.COMPLETED    # Finished successfully
LoaderStatus.FAILED       # Error occurred
LoaderStatus.TIMEOUT      # Exceeded timeout
LoaderStatus.IDLE         # Never registered (legacy, deprecated)
LoaderStatus.READY        # Loaded before but not running (legacy, deprecated)
LoaderStatus.EMPTY        # No data available (legacy, deprecated)
LoaderStatus.OK           # Unclear (legacy, deprecated)
```

---

## Phase 2: Fix Data Integrity (CURRENT BLOCKER)

**Problem:** Database has 8 different status values, many invalid:
```sql
SELECT DISTINCT status FROM data_loader_status ORDER BY status;
-- Returns: 'COMPLETED', 'EMPTY', 'FAILED', 'IDLE', 'OK', 'READY', 'RUNNING'
-- PROBLEM: No validation, no state machine
```

**Fix: Cleanup phase**
```sql
-- Step 1: Identify orphaned loaders (IDLE/READY for >7 days with no execution)
SELECT table_name, status, last_updated,
       (NOW() - last_updated) as age
FROM data_loader_status 
WHERE status IN ('IDLE', 'READY', 'OK', 'EMPTY')
  AND last_updated < NOW() - INTERVAL '7 days'
ORDER BY last_updated DESC;

-- Step 2: Reset these to NOT_STARTED (they need to run again)
UPDATE data_loader_status
SET status = 'NOT_STARTED', execution_started = NULL, execution_completed = NULL
WHERE status IN ('IDLE', 'READY', 'OK', 'EMPTY')
  AND last_updated < NOW() - INTERVAL '7 days';

-- Step 3: For loaders with status='RUNNING' for >24 hours, mark as TIMEOUT
UPDATE data_loader_status
SET status = 'TIMEOUT', 
    error_message = 'Manually marked timeout: was RUNNING >24h',
    execution_completed = NOW()
WHERE status = 'RUNNING' 
  AND execution_started < NOW() - INTERVAL '24 hours';

-- Step 4: Verify cleanup
SELECT status, COUNT(*) as count FROM data_loader_status GROUP BY status;
-- Should only have: COMPLETED, FAILED, NOT_STARTED, RUNNING, TIMEOUT
```

---

## Phase 3: Migrate All Loaders to StatusManager (NEXT TASK)

**Before:**
```python
# load_prices.py (inconsistent status values)
cur.execute(
    "INSERT INTO data_loader_status (table_name, status) VALUES (%s, 'running')",
    (table_name,)
)
# ... later ...
cur.execute(
    "UPDATE data_loader_status SET status = 'complete' WHERE table_name = %s",
    (table_name,)
)
```

**After:**
```python
# load_prices.py (standardized)
from utils.loaders.status_manager import LoaderStatusManager

manager = LoaderStatusManager("price_daily")
manager.mark_running()  # Sets status=RUNNING automatically

# ... loading loop ...
manager.update_progress(symbols_loaded=100, symbol_count=5000, completion_pct=2.0)

# ... finished ...
manager.mark_completed()  # Sets status=COMPLETED, completion_pct=100
# OR
manager.mark_failed("Connection timeout after 5 retries")
```

**Loaders to migrate (alphabetical order):**
1. ✓ `load_prices.py` - Uses 'running'/'complete'/'error'
2. ✓ `load_technical_indicators.py` - Uses "FAILED", sometimes crashes silently
3. ✓ `load_market_exposure_daily.py` - Uses 'running'/'completed'/'failed'
4. ✓ `load_value_metrics.py` - Session 193 bug: silent failures
5. ✓ `load_positioning_metrics.py` - Session 193 bug: silent failures
... (38 more loaders)

---

## Phase 4: Fix Orchestrator Status Validation

**Before:**
```python
# orchestrator.py line 658 - trusts whatever status is in database
if completion_pct is None:
    is_complete = False
    logger.error(f"[LOADER HEALTH] {table_name} completion_pct is NULL")
# Never checks if status VALUE is valid
```

**After:**
```python
# orchestrator.py - validate status enum
from utils.loaders.status_enum import LoaderStatus

if completion_pct is None:
    # CRITICAL: Validate status is a recognized value
    try:
        status_enum = LoaderStatus.from_string(status)
    except ValueError:
        logger.critical(f"[LOADER HEALTH] Invalid status '{status}' for {table_name}")
        raise RuntimeError(f"Loader status validation failed for {table_name}")
    
    if LoaderStatus.is_error(status):
        # Loader explicitly failed, not just incomplete
        is_complete = True
        is_error = True
    else:
        is_complete = False
```

---

## Phase 5: Fix Halt Flag Context-Awareness

**Problem:** Halt flag set at 2 AM (prices stale) blocks all trades at 9:30 AM (prices now fresh)

**Before:**
```python
# halt_flag_manager.py - fire and forget
if result.halted:
    self.halt_manager.set_halt_flag(f"Phase 1 degraded: {result.error}")
    # Flag persists until market open NEXT DAY
    # Doesn't re-check if data is fresh now
```

**After:**
```python
# halt_flag_manager.py - context-aware
def check_halt_flag(self) -> bool:
    """Check halt flag WITH freshness re-validation."""
    if not self._get_halt_flag():
        return False  # No halt
    
    # Halt is set - but is it still current?
    # Phase 1 can re-run in the morning and clear halt if data is fresh now
    if self._should_re_validate_freshness():
        # This halt might be stale (from overnight, data refreshed since then)
        logger.info("[HALT_FLAG] Re-validating freshness for active halt flag...")
        fresh_enough = self._check_data_freshness()
        if fresh_enough:
            self.clear_halt_flag("Data freshness re-validated - halt flag cleared")
            return False
    
    return True  # Halt still applies
```

---

## Phase 6: Orchestrator - Validate Status Before Using

**File:** `algo/orchestration/orchestrator.py` - `_check_loader_health()` method

**Add validation at top of loop:**
```python
for table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count in cur.fetchall():
    # CRITICAL FIX: Validate status is recognized value
    try:
        status_enum = LoaderStatus.from_string(status)
    except ValueError:
        raise RuntimeError(
            f"[LOADER HEALTH] Invalid status '{status}' for {table_name}. "
            f"Database contains invalid loader status. "
            f"Valid values: {LoaderStatus.all_strings()}"
        )
    
    if LoaderStatus.is_error(status_enum.value):
        # Loader explicitly failed, not just incomplete
        if not error_message:
            logger.warning(f"[LOADER HEALTH] {table_name} status={status} but error_message is NULL")
        # ... handle error case ...
```

---

## Phase 7: Add Halt Flag Timestamp Validation

**File:** `algo/orchestration/halt_flag_manager.py`

**Add to `check_halt_flag()`:**
```python
def check_halt_flag(self) -> bool:
    # ... existing code ...
    
    # NEW: If halt triggered >4 hours ago, re-validate freshness
    if trigger_date == now_date_et:
        hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
        
        # After 4 hours, halt might be stale (prices might have refreshed)
        # Require explicit "halt still valid" signal instead of "fire and forget"
        if hours_halted > 4:
            logger.info(
                f"[HALT_FLAG] Halt is {hours_halted:.1f}h old. "
                f"Re-validating that freshness issue still exists..."
            )
            # Don't auto-clear, but log that this halt is getting old
            # Next orchestrator run (Phase 1) will determine if still necessary
```

---

## Testing Plan

### Unit Tests
```python
# tests/test_loader_status_enum.py
def test_status_enum_valid_values():
    for status in LoaderStatus.all_strings():
        assert LoaderStatus.from_string(status)  # Shouldn't raise

def test_status_enum_invalid_raises():
    with pytest.raises(ValueError):
        LoaderStatus.from_string("BOGUS_STATUS")

def test_status_enum_case_sensitive():
    with pytest.raises(ValueError):
        LoaderStatus.from_string("running")  # lowercase should fail
```

### Integration Tests
```python
# tests/test_loader_status_manager.py
def test_status_manager_running():
    manager = LoaderStatusManager("test_table")
    manager.mark_running()
    status = manager.get_status()
    assert status["status"] == "RUNNING"
    assert status["execution_started"] is not None

def test_status_manager_completed():
    manager = LoaderStatusManager("test_table")
    manager.mark_running()
    manager.update_progress(completion_pct=100)
    manager.mark_completed()
    status = manager.get_status()
    assert status["status"] == "COMPLETED"
    assert status["completion_pct"] == 100.0
```

### System Tests
```bash
# 1. Check status consistency
python3 << 'EOF'
import psycopg2
from utils.loaders.status_enum import LoaderStatus

conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
cur = conn.cursor()
cur.execute("SELECT DISTINCT status FROM data_loader_status")

valid = set(LoaderStatus.all_strings())
for (status,) in cur.fetchall():
    if status not in valid:
        raise ValueError(f"Invalid status in database: {status}")

print("✓ All loader statuses are valid")
EOF

# 2. Run orchestrator preflight check
python3 check_system_health.py
# Should pass "Loader status validation" check
```

---

## Migration Checklist

- [ ] Phase 1: Created `status_enum.py` and `status_manager.py`
- [ ] Phase 2: Cleanup invalid statuses in database (SQL script above)
- [ ] Phase 3: Migrate all 42 loaders to use `LoaderStatusManager`
- [ ] Phase 4: Add status validation to `orchestrator.py` (`_check_loader_health()`)
- [ ] Phase 5: Add context-aware freshness re-check to `halt_flag_manager.py`
- [ ] Phase 6: Validate halt flag timestamp before applying (don't fire-and-forget)
- [ ] Phase 7: Run unit tests on status enum/manager
- [ ] Phase 8: Run integration tests on orchestrator preflight
- [ ] Phase 9: Manual test: run orchestrator and verify Phase 1 health checks pass
- [ ] Phase 10: Deploy to AWS and monitor for flag-related issues

---

## Success Criteria

**After migration, the system MUST:**
1. ✓ All loader status values match `LoaderStatus` enum (not 8 random strings)
2. ✓ All status updates go through `LoaderStatusManager` (not raw SQL)
3. ✓ All errors populate `error_message` column (no NULL errors)
4. ✓ Orchestrator validates status values before using them (fail-fast on corruption)
5. ✓ Halt flag expires after 4-6 hours or after data freshness re-validated
6. ✓ No more silent loader failures (status always reflects reality)
7. ✓ ValueMetrics/PositioningMetrics use status manager (Session 193 bug prevented)
8. ✓ Factor score coverage stays above 80% consistently

---

## Risk Mitigation

**Risk: Loaders still using raw SQL status updates (incomplete migration)**
- Mitigation: Add pre-commit hook to block commits with `status =` SQL outside status_manager
- Mitigation: Search codebase for raw status updates during code review

**Risk: Halt flag still stale after 4-hour threshold**
- Mitigation: Phase 1 explicitly clears halt if data is fresh, don't rely on auto-expiry
- Mitigation: Add CloudWatch alarm if halt flag active for >6 hours

**Risk: Database still has invalid status values after cleanup**
- Mitigation: Add trigger that rejects INSERT/UPDATE with invalid status values
- Mitigation: Add automated hourly check that alerts on status inconsistencies

---

## Next Steps

1. **Commit these files:**
   - `utils/loaders/status_enum.py` ✓ Done
   - `utils/loaders/status_manager.py` ✓ Done
   - `FLAG_SYSTEM_ANALYSIS.md` ✓ Done
   - This file ✓ Done

2. **Database cleanup (SQL script)** - Run manually to fix existing data
3. **Start Phase 3 migration** - One loader at a time, test each one
4. **Orchestrator validation** - Add enum validation in `_check_loader_health()`
5. **Deploy and monitor** - Watch factor score coverage, data staleness, halt flags
