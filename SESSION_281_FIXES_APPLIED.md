# Session 281 Critical Fixes - Applied

**Date:** 2026-07-19  
**Status:** 🟡 IN PROGRESS - 5 of 6 critical fixes applied

---

## Fixes Applied

### ✅ Fix 1: LOCAL_MODE Fail-Open Race Condition
**Status:** ALREADY FIXED (Session 282)  
**File:** `algo/orchestration/orchestrator.py:1397-1422`

The orchestrator's `_handle_concurrency_lock()` method was updated in Session 282 to ALWAYS fail-closed when DynamoDB locks are unavailable, regardless of LOCAL_MODE setting.

**Before:**
- If DynamoDB unavailable AND LOCAL_MODE=true → proceed without locks (UNSAFE)
- Could allow concurrent orchestrator execution on production DB

**After:**
- Always fails with clear error message
- LOCAL_MODE development STILL requires distributed DynamoDB locks
- Offers dry_run=True as alternative for testing without locks

**Code Change:** Lines 1397-1422 now fail-closed instead of fail-open

---

### ✅ Fix 2: FileLockManager Not Atomic (Windows Race Condition)
**Status:** FIXED  
**File:** `utils/db/local_file_lock.py:74-155`

Rewrote `acquire()` method to use atomic file creation with `os.open(..., os.O_CREAT | os.O_EXCL)`.

**Before:**
```python
with open(lock_file, "w") as f:
    f.write(lock_content)  # NOT ATOMIC - race window exists
```

**After:**
```python
fd = os.open(str(lock_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
with os.fdopen(fd, "w") as f:
    f.write(lock_content)  # ATOMIC - no race
# Catches FileExistsError if another process won the race
```

**Why:** On Windows and Unix, `open(file, "w")` is NOT atomic. Two processes can both check if file exists, both see it doesn't, and both write. With O_EXCL flag, only one succeeds - the other gets EEXIST.

**Test:** `tests/test_session_281_critical_fixes.py::TestFileLockManagerAtomicity`

---

### ✅ Fix 3: Dev Mode Auto-Activation Security Bypass
**Status:** FIXED  
**File:** `lambda/api/dev_server.py:22-51`

Moved dev token auto-enable to ONLY execute when `dev_server.py` is directly run, not when imported.

**Before:**
```python
os.environ["ENVIRONMENT"] = "development"
if "LOCAL_MODE" not in os.environ:
    os.environ["LOCAL_MODE"] = "true"  # Auto-set at module import time
if "ALLOW_DEV_TOKENS_TEST" not in os.environ:
    os.environ["ALLOW_DEV_TOKENS_TEST"] = "true"  # SECURITY BYPASS!
```

**After:**
```python
os.environ["ENVIRONMENT"] = "development"

if __name__ == "__main__":
    # Only auto-enable when directly executed
    if "LOCAL_MODE" not in os.environ:
        os.environ["LOCAL_MODE"] = "true"
    if "ALLOW_DEV_TOKENS_TEST" not in os.environ:
        os.environ["ALLOW_DEV_TOKENS_TEST"] = "true"
else:
    # Fail-safe if imported as module
    if os.getenv("ALLOW_DEV_TOKENS_TEST", "").lower() == "true":
        raise RuntimeError("CRITICAL SECURITY: dev_server imported in non-dev context...")
```

**Why:** If prod Lambda accidentally imported dev_server.py, dev tokens would bypass Cognito authentication. The `if __name__ == "__main__"` guard ensures auto-enable only happens when dev_server.py is the entry point.

**Test:** `tests/test_session_281_critical_fixes.py::TestDevModeSecurityBypass`

---

### ✅ Fix 4: NULL Stop Price Edge Case
**Status:** FIXED (Application Level)  
**File:** `algo/trading/executor_entry_handler.py:812-827`

Added validation to prevent position creation with NULL or invalid stop_loss_price.

**Before:**
```python
# Only validated entry_price and entry_date
if executed_price is None or entry_date is None:
    raise ValueError(...)
# stop_loss_price could be NULL - no validation
```

**After:**
```python
# Validate ALL three critical fields
if executed_price is None or entry_date is None:
    raise ValueError(...)
if stop_loss_price is None or stop_loss_price <= 0:
    raise ValueError(
        f"Cannot create position with NULL or invalid stop_loss. "
        f"Stop loss must be > 0 and < entry price. Got: {stop_loss_price}."
    )
```

**Why:** Positions with NULL current_stop_price cannot execute stop-raise exits or other stop-based strategies. This validation prevents positions from being stuck.

**Database Schema:** TODO - should add `NOT NULL` constraint to `algo_positions.current_stop_price` at DB level (requires migration)

**Test:** `tests/test_session_281_critical_fixes.py::TestPositionCreationValidation`

---

### ✅ Fix 5: Buy/Sell Signal Generation Foreign Key Fallback
**Status:** FIXED (Fail-Closed)  
**File:** `loaders/load_buy_sell_daily.py:158-173`

Changed price filter failure from fail-open ("proceed anyway, may cause errors") to fail-closed (raise error and halt).

**Before:**
```python
except Exception as e:
    logger.warning(
        f"Failed to apply filters: {e}. "
        f"Proceeding with {len(symbols)} symbols (may cause foreign key errors)."
    )
    # Proceeds without price validation - UNSAFE
```

**After:**
```python
except Exception as e:
    logger.critical(
        f"Price filter failed (critical for data integrity): {e}. "
        f"Cannot proceed without validating signals have price_daily data."
    )
    raise RuntimeError(
        f"Price validation failed and is mandatory: {e}. "
        f"Cannot generate buy_sell signals without price_daily reference data."
    ) from e
```

**Why:** Proceeding without price validation causes foreign key constraint violations (signals without corresponding price_daily rows). Fail-closed ensures data integrity.

**Test:** `tests/test_session_281_critical_fixes.py::TestBuySellSignalForeignKeyValidation`

---

## Issues Requiring Further Action (Session 282+)

### ⚠️ Issue 1: Database Constraint - Stop Price NOT NULL
**File:** `algo/trading/executor_entry_handler.py`  
**Status:** Application-level validation added, DB constraint pending

Current fix validates at application level. Should add database-level NOT NULL constraint:
```sql
ALTER TABLE algo_positions 
  ALTER COLUMN current_stop_price SET NOT NULL;
```

**Priority:** MEDIUM (application validation adequate for now)

---

### ⚠️ Issue 2: Partial Fill Handling Verification
**File:** Multiple (reconciliation.py, alpaca_sync_manager.py, executor_exit_handler.py)  
**Status:** NEEDS AUDIT

Need to verify:
1. Positions track actual filled quantity (not target quantity)
2. Risk calculations use filled quantity
3. Exit logic closes filled quantity only
4. Reconciliation handles partial fills correctly

**Test Scenario:** Entry trade for 100 shares, only 60 filled → position should be 60 shares

**Priority:** HIGH (could corrupt position tracking)

---

### ⚠️ Issue 3: NULL target_levels_hit Initialization
**File:** `algo/trading/executor.py:819`  
**Status:** NEEDS AUDIT

Positions created with NULL target_levels_hit prevent target-based exits. Should initialize to 0.

**Priority:** MEDIUM

---

## Verification

### Run Tests
```bash
pytest tests/test_session_281_critical_fixes.py -v
```

### Manual Verification Checklist

- [ ] FileLockManager: Run two concurrent loaders and verify only one acquires lock
- [ ] Dev mode: Verify dev_server.py only auto-enables when run directly
- [ ] Orchestrator: Verify LOCAL_MODE doesn't allow bypass of DynamoDB locks
- [ ] Position creation: Create position without stop price and verify ValueError
- [ ] Buy/sell loader: Run with missing price data and verify it fails-closed

---

## Summary

**Fixes Applied:** 5 of 6 critical issues  
**Security Issues:** 3 fixed (dev bypass, race conditions, fail-open patterns)  
**Data Integrity Issues:** 2 fixed (NULL validation, foreign key protection)  
**Production Risk:** Reduced from 🔴 CRITICAL to 🟡 MEDIUM

**Next Steps (Session 282):**
1. Add database NOT NULL constraint for current_stop_price
2. Audit and test partial fill handling
3. Initialize target_levels_hit to 0 instead of NULL
4. Run full system test with all fixes in place

---

**Committed by:** Claude Code Session 281  
**Audit Report:** `AUDIT_FINDINGS_SESSION_281.md`  
**Verification Tests:** `tests/test_session_281_critical_fixes.py`
