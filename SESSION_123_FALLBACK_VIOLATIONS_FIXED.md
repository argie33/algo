# Session 123: Critical Fallback Violations Eliminated

## Summary
Eliminated 6 **CRITICAL** fallback violations across Lambda API routes where financial data was silently falling back to default values instead of failing fast. These violations created "sometimes works, sometimes doesn't" behavior that undermines finance app reliability.

## Violations Fixed

### 1. **dashboard.py:358** - Position Sort Fallback
**Violation:** `items.sort(key=lambda x: float(x.get("position_value", 0)), reverse=True)`
- **Issue:** Uses 0 as fallback for critical financial field position_value
- **Risk:** Sorts positions incorrectly if position_value is missing (displays wrong first to last)
- **Fix:** Explicit validation loop that raises if position_value missing/None

### 2. **dashboard.py:534-536** - Position Count/Value Fallbacks (3 violations)
**Violations:**
```python
pos_count = pos_result.get("pos_count") if pos_result else 0
pos_value = float(pos_result.get("total_positions_value", 0)) if pos_result else 0.0
closed_value = float(pos_result.get("closed_value", 0)) if pos_result else 0.0
```
- **Issue:** Uses 0 as fallback for position counts and values when query fails
- **Risk:** Dashboard silently shows $0 portfolio when it should show error
- **Fix:** 
  - Fail-fast if query returns no result (raises RuntimeError)
  - Explicit None checks for each field
  - Raises ValueError with field name if field is NULL or invalid type

### 3. **dashboard.py:553** - Portfolio Value Falsy Check
**Violation:** `if first_snapshot and first_snapshot.get("total_portfolio_value"):`
- **Issue:** Falsy check on numeric field (0.0 is legitimate, triggers fallback)
- **Risk:** Portfolio snapshots with $0 value skip entire initialization
- **Fix:** Changed to explicit `is not None` check

### 4. **dashboard.py:559** - Silent Exception Fallback
**Violation:** 
```python
except (ValueError, TypeError):
    pass  # Fall back to default if conversion fails
```
- **Issue:** Silent exception with no logging - hides data corruption
- **Risk:** Initial portfolio value silently defaults to $100,000 when real value is unparseable
- **Fix:** Explicit error message stating why snapshot value is invalid + raises exception

### 5. **monitoring.py:258** - Patrol Log Count Fallback
**Violation:** `total = row.get("total", 0)`
- **Issue:** Uses 0 as fallback for COUNT(*) result (should always return a row)
- **Risk:** Hides database corruption where COUNT(*) fails
- **Fix:**
  - Raises if COUNT(*) returns no row (should never happen)
  - Raises if "total" field is NULL
  - Validates type is int

### 6. **metrics.py:598** - Database NOW() Fallback Chain
**Violation:** `now_db = now_row.get("now") or next(iter(now_row.values()))`
- **Issue:** Falls back to arbitrary "first value" if NOW() is NULL
- **Risk:** Calculates data freshness with wrong timestamp
- **Fix:** Explicit None check, raises if NOW() returns NULL

### 7. **metrics.py:607** - Snapshot Timestamp Fallback
**Violation:** `last_write_at = data.get("updated_at") or data.get("created_at")`
- **Issue:** Falls back to created_at if updated_at missing (data integrity issue)
- **Risk:** Age calculation uses wrong timestamp when data column is missing
- **Fix:** Explicit None check on updated_at only, raises if missing

## Pattern Changes

### Before (Silent Fallback Pattern)
```python
value = result.get("field", 0)  # Hides missing data
or
value = result.get("field") or fallback  # Silent fallback chain
or
except Exception:
    pass  # Continue silently
```

### After (Fail-Fast Pattern)
```python
value_raw = result.get("field")
if value_raw is None:
    raise ValueError(f"[CONTEXT] field is NULL - required for calculation")
try:
    value = float(value_raw)
except (ValueError, TypeError) as e:
    raise ValueError(f"[CONTEXT] field invalid type ({value_raw}): {e}") from e
```

## Files Modified
- `lambda/api/routes/algo_handlers/dashboard.py` (4 violations)
- `lambda/api/routes/algo_handlers/monitoring.py` (1 violation)
- `lambda/api/routes/algo_handlers/metrics.py` (2 violations)

## Testing Required
- Portfolio calculation (empty positions table scenario)
- Portfolio calculation (stale snapshots scenario)
- Position display with missing price data
- Patrol log with empty data_patrol_log table
- Portfolio age calculation edge cases

## Why This Matters for Finance App
1. **No Silent Failures:** Every calculation path must either succeed with valid data or fail with clear error
2. **Consistent Behavior:** Same code path produces same result every time (not "sometimes works")
3. **Data Integrity:** Missing/invalid financial data is never hidden behind defaults
4. **Debugging:** Clear error messages identify exactly what data is missing/invalid (faster diagnosis)
5. **Audit Trail:** All failures are logged explicitly (not silent passes)

## Remaining Verified Patterns
- `market.py:329` - `summary.get("ok", 0)` - **OK:** Documented fallback for health check counts
- Config `.get()` with defaults - **OK:** Configuration defaults are appropriate
- `.get()` without defaults followed by explicit None check - **OK:** Correct pattern
