# Standardized Exception Handling for Loaders

## Overview

All loaders must use consistent exception handling to distinguish between:

1. **Transient errors** (retryable) - Timeouts, connection issues, rate limiting
2. **Permanent data issues** (non-retryable) - API schema changes, invalid data
3. **Unexpected errors** - All other exceptions, which should fail-fast

This document establishes the required patterns across the loader ecosystem.

---

## Exception Categories & Handling

### Transient Errors (Retryable)

These errors are temporary and should trigger retries via orchestrator retry logic.

| Error Type | Classification | Handler | Reason Code | Dashboard Severity |
|-----------|-----------------|---------|-------------|-------------------|
| `TimeoutError`, `socket.timeout` | Transient | `handle_timeout_error()` | `timeout_retryable` | Warning (retry soon) |
| `ConnectionError`, network issues | Transient | `handle_connection_error()` | `connection_error` | Warning (retry soon) |
| HTTP 429, 503 | Transient | `handle_rate_limit_error()` | `rate_limit_or_service_unavailable` | Warning (retry soon) |
| No data found | Transient | `handle_no_data_found()` | `no_data_found` | Info (expected) |

**Return behavior:** Return `data_unavailable` marker with reason code. Caller (orchestrator) will retry later.

**Log level:** WARNING (operator should be aware but not alarmed)

### Permanent Data Issues (Non-Retryable)

These errors indicate the data is genuinely unavailable or invalid. Retry won't help.

| Error Type | Classification | Handler | Reason Code | Dashboard Severity |
|-----------|-----------------|---------|-------------|-------------------|
| `KeyError` (missing fields) | Permanent | `handle_schema_mismatch()` | `api_schema_mismatch` | Alert (investigate) |
| `ValueError`, type errors | Permanent | `handle_invalid_data()` | `data_invalid` | Alert (investigate) |
| 404, resource not found | Permanent | `handle_resource_not_found()` | `{resource}_not_found` | Alert (investigate) |

**Return behavior:** Return `data_unavailable` marker with reason code. Don't retry.

**Log level:** ERROR (operator must investigate)

### Unexpected Errors (Fail-Fast)

Unknown exceptions indicate a bug or edge case not anticipated. These must fail-fast to surface the issue.

| Error Type | Behavior |
|-----------|----------|
| All other exceptions | Logged at CRITICAL level with full traceback, then re-raised |

**Fail-fast principle:** If we don't understand the error, stop processing and surface it. Don't silently degrade or ignore.

---

## Migration Path: Before → After

### Old Pattern (Problematic)

```python
# ❌ WRONG: Silent swallowing masks all errors
try:
    data = fetch_critical_data(symbol)
except Exception as e:
    logger.debug(f"Could not fetch: {e}")  # Invisible in production
    return None  # Caller can't tell if error is transient or permanent
```

Problems:
- Debug-level logging: Production errors invisible
- `None` return: Caller doesn't know what went wrong
- Silent fallback chains: System degrades invisibly
- No distinction: Timeout looks same as schema mismatch

### New Pattern (Correct)

```python
# ✅ CORRECT: Classified exception handling
try:
    data = fetch_critical_data(symbol)
except TimeoutError as e:
    marker = handle_exception(symbol, e, "fetching company data")
    return [marker]  # Marker says "try again later"
except KeyError as e:
    marker = handle_exception(symbol, e, "SEC API structure changed")
    return [marker]  # Marker says "needs investigation"
except Exception as e:
    # Unexpected error: fail-fast
    logger.critical(f"Unexpected {type(e).__name__}: {e}", exc_info=True)
    raise  # Surface the issue immediately
```

Benefits:
- Transient errors logged at WARNING: operator is aware
- Permanent errors logged at ERROR: requires investigation
- Unexpected errors logged at CRITICAL with traceback: clear signal
- `data_unavailable` markers: caller knows what happened
- Orchestrator can retry appropriately

---

## Usage: Import & Apply

### 1. Import the handlers

```python
from utils.loaders.exception_handler import (
    handle_exception,
    handle_timeout_error,
    handle_connection_error,
    handle_schema_mismatch,
    handle_invalid_data,
    handle_no_data_found,
    handle_resource_not_found,
)
```

### 2. Catch specific exceptions in order of specificity

```python
try:
    data = sec_client.get_submissions(cik)
except TimeoutError as e:
    # Transient: API slow, will retry
    return [handle_exception(symbol, e, "fetching SEC submissions")]
except KeyError as e:
    # Permanent: API schema changed
    return [handle_exception(symbol, e, "SEC API missing fields")]
except ValueError as e:
    # Permanent: Data validation failed
    marker = handle_invalid_data(symbol, e, "parsing SEC response")
    return [marker]
except Exception as e:
    # Unexpected: Fail-fast
    logger.critical(f"Unexpected error: {type(e).__name__}: {e}", exc_info=True)
    raise
```

### 3. Use `handle_exception()` for automatic routing

If you want automatic classification, use `handle_exception()` which routes based on exception type:

```python
try:
    data = fetch_data(symbol)
except (TimeoutError, ConnectionError, KeyError, ValueError) as e:
    # Any of these will be classified and routed appropriately
    return [handle_exception(symbol, e, "fetching data")]
except Exception as e:
    # Unexpected: fail-fast
    logger.critical(f"Unexpected {type(e).__name__}: {e}", exc_info=True)
    raise
```

### 4. Handle specific known scenarios with direct handlers

For scenarios that don't fit standard exception types, use direct handlers:

```python
if not data:
    marker = handle_no_data_found(symbol, "no recent filings found")
    return [marker]

if symbol_not_in_sec_database:
    marker = handle_resource_not_found(symbol, "CIK", "ticker not in SEC EDGAR")
    return [marker]
```

---

## Marker Format & Structure

All exception handlers return data_unavailable markers in standardized format:

```python
{
    "symbol": "AAPL",
    "data_unavailable": True,
    "reason": "timeout_retryable",  # or other reason code
    "reason_type": "temporary",     # "temporary" or "loader_failed"
}
```

### Reason Codes

**Transient (temporary):**
- `timeout_retryable` - API timed out
- `connection_error` - Network connection failed
- `rate_limit_or_service_unavailable` - API rate limited or 503
- `no_data_found` - No data for this symbol/period

**Permanent (loader_failed):**
- `api_schema_mismatch` - API structure changed
- `data_invalid` - Data validation failed
- `{resource}_not_found` - Resource (CIK, submissions, etc) not found

### Dashboard Interpretation

The dashboard filters on `reason_type`:
- `temporary` = warning-level, try again later (doesn't cause alerts)
- `loader_failed` = error-level, needs investigation (causes alerts)

---

## Common Patterns

### Pattern 1: SEC EDGAR API Fetch

```python
try:
    cik = self.sec_client.symbol_to_cik(symbol)
except ValueError:
    # CIK lookup failed: permanent (symbol not in SEC database)
    return [handle_resource_not_found(symbol, "CIK", "ticker not in SEC EDGAR")]

try:
    submissions = self.sec_client.get_submissions(cik)
except TimeoutError as e:
    # Timeout: transient (retry will work)
    return [handle_exception(symbol, e, "fetching SEC submissions")]
except KeyError as e:
    # API schema changed: permanent (needs code fix)
    return [handle_schema_mismatch(symbol, e, "SEC API missing 'filings' key")]

if not submissions:
    # Empty result: permanent for this fetch
    return [handle_no_data_found(symbol, "SEC submissions empty")]
```

### Pattern 2: Data Type Conversion

```python
try:
    shares = float(shares_string)
    if shares <= 0:
        return [handle_invalid_data(
            symbol, 
            ValueError(f"shares_outstanding must be > 0, got {shares}"),
            "validating share count"
        )]
except ValueError as e:
    # Cannot convert to float: permanent
    return [handle_invalid_data(symbol, e, "converting share count")]
```

### Pattern 3: Database Query

```python
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT ... FROM financial_statements WHERE symbol = %s", (symbol,))
        row = cur.fetchone()
        if not row:
            return [handle_no_data_found(symbol, "no financial statements")]
        # Process row...
except TimeoutError as e:
    return [handle_exception(symbol, e, "querying database")]
except Exception as e:
    logger.critical(f"Unexpected DB error: {type(e).__name__}: {e}", exc_info=True)
    raise
```

---

## Logging Best Practices

### Log Levels

| Exception Type | Level | Example |
|---|---|---|
| Transient error | WARNING | `logger.warning(f"[{symbol}] Transient timeout: {error}")` |
| Permanent error | ERROR | `logger.error(f"[{symbol}] API schema changed: {error}")` |
| Unexpected error | CRITICAL | `logger.critical(f"[{symbol}] Unexpected {type(e).__name__}: {e}", exc_info=True)` |

### Log Format

Always include:
1. Symbol (ticker) in brackets: `[AAPL]`
2. Error type name: `TimeoutError`, `KeyError`, etc
3. Error message (truncated if long)
4. Context: "fetching company facts", "validating share count"

```python
logger.warning(f"[{symbol}] Transient timeout fetching company facts: {e}")
logger.error(f"[{symbol}] API schema mismatch: {e}")
logger.critical(f"[{symbol}] Unexpected {type(e).__name__}: {e}", exc_info=True)
```

---

## Testing Exception Handlers

### Unit Test Example

```python
def test_handle_timeout_error():
    """Timeout should return transient marker."""
    error = TimeoutError("API slow")
    result = handle_timeout_error("AAPL", error, "fetching data")
    
    assert result["symbol"] == "AAPL"
    assert result["data_unavailable"] is True
    assert result["reason"] == "timeout_retryable"
    assert result["reason_type"] == "temporary"

def test_handle_schema_mismatch():
    """Schema mismatch should return permanent marker."""
    error = KeyError("expected_field")
    result = handle_schema_mismatch("MSFT", error, "SEC API structure changed")
    
    assert result["symbol"] == "MSFT"
    assert result["data_unavailable"] is True
    assert result["reason"] == "api_schema_mismatch"
    assert result["reason_type"] == "loader_failed"

def test_unexpected_error_raises():
    """Unexpected errors should be re-raised."""
    error = RuntimeError("something weird")
    
    with pytest.raises(RuntimeError, match="something weird"):
        handle_exception("GOOGL", error, "")
```

---

## Orchestrator Integration

The orchestrator respects `data_unavailable` markers:

1. **Transient markers** (`reason_type="temporary"`):
   - Phase doesn't fail
   - Orchestrator can retry later (if retrying is implemented)
   - Dashboard doesn't alert

2. **Permanent markers** (`reason_type="loader_failed"`):
   - Phase doesn't fail (loader handled it gracefully)
   - Orchestrator doesn't retry (won't help)
   - Dashboard may alert if too many failures in phase

3. **Unexpected exceptions** (re-raised):
   - Phase halts with error
   - Orchestrator reports failure
   - Dashboard alerts operator

---

## Migration Checklist

For each loader, verify:

- [ ] All known transient errors caught and handled
- [ ] All known permanent errors caught and handled
- [ ] Unexpected errors fail-fast (propagate/re-raise)
- [ ] No silent exception swallowing (no broad `except Exception: pass`)
- [ ] Log levels correct (WARNING for transient, ERROR for permanent, CRITICAL for unexpected)
- [ ] Markers use correct reason codes
- [ ] No cascading `.get()` chains that mask missing fields
- [ ] Type safety passes (`mypy --strict`)
- [ ] Linting passes (`ruff check`)

---

## Files Implementing Standard

Currently standardized:
- `loaders/load_company_info_sec.py` ✅
- `loaders/load_earnings_calendar_sec.py` ✅
- `loaders/load_sec_valuations.py` ✅

Framework:
- `utils/loaders/exception_handler.py` - Central exception handlers
- `utils/loaders/unavailable_markers.py` - Marker factory functions
- `utils/loaders/transient_errors.py` - Transient error exception types
- `tests/unit/loaders/test_exception_handler.py` - Comprehensive tests

---

## FAQ

**Q: Should I use `handle_exception()` or specific handlers?**

A: Prefer specific handlers for clarity. Use `handle_exception()` only for catch-all clauses that handle multiple error types. Specific handlers make code intent clearer.

**Q: What if I don't know whether an error is transient or permanent?**

A: Use the `classify_exception()` function to auto-detect, or mark it as `loader_failed` (permanent). It's better to be conservative (don't retry permanent errors) than aggressive (retry permanent errors).

**Q: Can I catch all exceptions with one handler?**

A: Only in the innermost try/except. Always have a specific catch for TimeoutError, KeyError, ValueError at minimum. The outer catch-all should fail-fast.

**Q: What if the API response is empty but that's expected?**

A: Use `handle_no_data_found()` to mark it temporary. This signals to the orchestrator that retry might find data later (e.g., new filings filed today).

**Q: Should I log before calling the handler?**

A: No. The handler logs at appropriate level. Just catch, call handler, and return marker.

---

## References

- `utils/loaders/exception_handler.py` - Implementation
- `tests/unit/loaders/test_exception_handler.py` - Test suite (20 tests)
- Session 243 - Implementation & standardization across loaders
