# Error Handling Standards

## Overview

This document defines how different types of errors should be handled across the algo system.
The goal: distinguish between expected failures, transient failures, and true bugs.

## Exception Categories & Handling

### 1. Database Errors (psycopg2 exceptions)

**When to catch:**
- Query execution errors
- Connection pool exhausted
- Transaction conflicts

**How to handle:**
```python
import psycopg2

try:
    cur.execute("SELECT ...")
except psycopg2.DatabaseError as e:
    # Unexpected DB error - log ERROR, alert if critical
    logger.error(f"Database error: {e}")
except psycopg2.IntegrityError as e:
    # Constraint violation - log WARNING
    logger.warning(f"Integrity constraint: {e}")
except psycopg2.OperationalError as e:
    # Connection/availability error - transient, retry
    logger.warning(f"Database unavailable: {e}")
    # Retry with backoff
```

**Rule:** Never use bare `except Exception:` for DB operations.

### 2. Data Validation Errors

**When to catch:**
- Missing required columns in query result
- Type conversion failures
- Empty/null unexpected values

**How to handle:**
```python
try:
    value = float(row[0])
except (ValueError, TypeError, IndexError) as e:
    logger.debug(f"Data validation: column empty or wrong type: {e}")
    value = 0  # Safe default
except Exception as e:
    # Unexpected - this shouldn't happen
    logger.error(f"Unexpected validation error: {e}")
```

**Rule:** Catch specific type errors, not broad `Exception`.

### 3. API/External Service Errors

**When to catch:**
- HTTP timeouts
- Rate limiting
- Invalid API responses

**How to handle:**
```python
import requests

try:
    response = requests.get(url, timeout=5)
    response.raise_for_status()
except requests.Timeout:
    logger.warning(f"API timeout after 5s")
    # Retry with backoff
except requests.HTTPError as e:
    if e.response.status_code == 429:
        logger.warning("Rate limited, backing off")
    else:
        logger.error(f"API returned {e.response.status_code}")
except requests.RequestException as e:
    logger.error(f"API error: {e}")
```

**Rule:** Retry transient errors (timeout, 429), fail fast on permanent errors (400, 401).

### 4. Logic/Configuration Errors

**When to catch:**
- Missing config keys (expected to have defaults)
- Invalid parameter values
- Business logic invariants violated

**How to handle:**
```python
try:
    threshold = float(self.config.get('threshold', 20.0))  # Has default
    if threshold < 0 or threshold > 100:
        raise ValueError(f"Invalid threshold: {threshold}")
except ValueError as e:
    logger.error(f"Config error: {e}")
    # Use safe default or halt
    return False
```

**Rule:** Validate all external inputs (config, API responses).

### 5. Resource/File Errors

**When to catch:**
- File not found
- Directory permission denied
- File lock

**How to handle:**
```python
from pathlib import Path

try:
    data = Path("file.json").read_text()
except FileNotFoundError:
    logger.warning(f"File not found, using defaults")
    data = "{}"
except PermissionError:
    logger.error(f"No permission to read file")
    return False
except Exception as e:
    logger.error(f"Unexpected file error: {e}")
    return False
```

**Rule:** Catch specific IO exceptions.

---

## Logging Levels

| Level | When to use | Example |
|-------|-----------|---------|
| DEBUG | Expected errors that don't impact function | "Intraday check failed: no data yet" |
| INFO | Normal operations that user might care about | "Position halted due to stop loss" |
| WARNING | Unexpected but recoverable errors | "Database connection timeout, retrying" |
| ERROR | Significant failures that impact functionality | "Could not fetch current prices - signals halted" |
| CRITICAL | System-wide failures that halt all trading | "Database offline - orchestrator halted" |

---

## Patterns to Replace

### ❌ BAD: Overly Broad

```python
try:
    result = expensive_operation()
except Exception as e:
    logger.warning(f"Operation failed: {e}")
    return None
```

**Problems:**
- Catches KeyboardInterrupt, SystemExit, etc.
- Hides programming bugs (NameError, AttributeError)
- Doesn't distinguish between failure types

### ✅ GOOD: Specific & Deliberate

```python
try:
    result = expensive_operation()
except (ValueError, TypeError) as e:
    logger.debug(f"Invalid input: {e}")
    return None
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise  # Let caller decide what to do
except Exception as e:
    logger.error(f"Unexpected error (possible bug): {e}")
    raise
```

---

## Circuit Breaker Error Handling

For checks that fail-open (return False when error occurs):

```python
def _check_something(self) -> bool:
    try:
        # Check logic
        return check_result
    except psycopg2.OperationalError as e:
        # DB connection error - transient
        logger.warning(f"Check skipped due to DB error: {e}")
        return True  # Don't halt on transient errors
    except (ValueError, TypeError, IndexError) as e:
        # Data validation error
        logger.debug(f"Check data error: {e}")
        return True  # Don't halt on invalid data
    except Exception as e:
        # Unexpected error - could be a bug
        logger.error(f"Check failed unexpectedly: {e}")
        return False  # Conservative: halt until fixed
```

---

## Audit Logging

For all database modifications (INSERT, UPDATE, DELETE):

```python
try:
    cur.execute(f"UPDATE {table} SET ... WHERE {condition}")
    self.conn.commit()
    logger.info(f"Updated {table}: {condition}")
except psycopg2.IntegrityError as e:
    self.conn.rollback()
    logger.error(f"Cannot update {table}: {e}")
except psycopg2.OperationalError as e:
    self.conn.rollback()
    logger.warning(f"Database unavailable: {e}")
except Exception as e:
    self.conn.rollback()
    logger.error(f"Unexpected update error: {e}")
```

**Rule:** Always rollback on error and log the outcome.

---

## Checklist

When writing error handling:

- [ ] Use specific exception types (not bare `Exception`)
- [ ] Log at appropriate level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [ ] Consider whether error is expected or indicates a bug
- [ ] For DB operations, always rollback on error
- [ ] For transient errors (timeout, 429), retry with backoff
- [ ] For bugs (NameError, AttributeError), let exception propagate
- [ ] Document which exceptions each function might raise
- [ ] Test error paths in unit tests

---

## Current Audit Status

**Files to Review:**
- algo_circuit_breaker.py: 5 broad handlers (mostly OK - non-critical checks)
- algo_swing_score.py: 8 broad handlers (mixed - some should fail fast)
- algo_orchestrator.py: 6 broad handlers (mostly OK - Phase checks)
- algo_trade_executor.py: 12 broad handlers (PRIORITY - critical paths)
- algo_exit_engine.py: 3 broad handlers (PRIORITY - exit logic)

**Next Actions:**
1. Focus on trade_executor and exit_engine (critical paths)
2. Ensure all DB errors are psycopg2 specific
3. Add retry logic for transient failures
4. Create error handling tests
