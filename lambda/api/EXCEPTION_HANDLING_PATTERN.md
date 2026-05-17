# Lambda API Exception Handling Pattern

## Overview
This document describes the standardized exception handling pattern for the Lambda API handler (`lambda_function.py`). This pattern replaces bare `except Exception` blocks with specific database exception handling that provides:
- Detailed error logging with operation context
- Appropriate HTTP status codes (503 for unavailable data, 500 for real errors)
- Clear error messages for clients
- Better debugging capabilities

## Pattern

Every database query method should have this exception handling structure:

```python
try:
    # Database query here
    self.cur.execute(query, params)
    results = self.cur.fetchall()
    return json_response(200, {'items': [dict(r) for r in results]})

except psycopg2.errors.UndefinedTable as e:
    logger.error(f'Required table not found: {e}', extra={'operation': 'fetch_data', 'table': 'table_name'})
    return error_response(503, 'service_unavailable', 'Data pipeline loading')

except psycopg2.errors.UndefinedColumn as e:
    logger.error(f'Column not found: {e}', extra={'operation': 'fetch_data', 'table': 'table_name'})
    return error_response(503, 'service_unavailable', 'Data schema mismatch')

except psycopg2.OperationalError as e:
    logger.error(f'Database connection error: {e}', extra={'operation': 'fetch_data'})
    return error_response(503, 'service_unavailable', 'Database unavailable')

except psycopg2.DatabaseError as e:
    logger.error(f'Database error: {e}', extra={'operation': 'fetch_data', 'error_type': type(e).__name__})
    return error_response(500, 'internal_error', 'Database query failed')

except Exception as e:
    logger.error(f'Unexpected error: {e}', extra={'operation': 'fetch_data', 'error_type': type(e).__name__})
    return error_response(500, 'internal_error', 'Failed to fetch data')
```

## Key Elements

### 1. Exception Order
Exceptions must be caught in this specific order:
1. `psycopg2.errors.UndefinedTable` - Schema isn't ready yet
2. `psycopg2.errors.UndefinedColumn` - Schema mismatch
3. `psycopg2.OperationalError` - Connection issues
4. `psycopg2.DatabaseError` - Other DB errors
5. Generic `Exception` - Fallback for unexpected errors

**Why**: Specific exceptions are subclasses of more general ones. Catching the most specific first prevents shadowing.

### 2. Logging
Each handler includes:
- Clear message describing what happened
- `extra` dict with context (operation name, relevant parameters)
- `error_type` for debugging (type(e).__name__)

Examples:
```python
logger.error('Required table not found', extra={'operation': 'fetch positions', 'table': 'algo_positions'})
logger.error(f'Column not found: {e}', extra={'operation': 'fetch signals', 'symbol': symbol})
logger.error(f'Unexpected error: {e}', extra={'operation': 'fetch data', 'error_type': type(e).__name__})
```

### 3. HTTP Status Codes & Messages

| Exception | HTTP Status | Error Code | Client Message |
|-----------|------------|-----------|-----------------|
| UndefinedTable | 503 | service_unavailable | "Data pipeline loading" |
| UndefinedColumn | 503 | service_unavailable | "Data schema mismatch" |
| OperationalError | 503 | service_unavailable | "Database unavailable" |
| DatabaseError | 500 | internal_error | "Database query failed" |
| Generic Exception | 500 | internal_error | Method-specific (keep original message) |

## Status Codes
- **503 Service Unavailable**: Used for transient issues (table not ready, schema mismatch, connection failed)
  - Client should retry after delay
  - Doesn't indicate a bug in the code
- **500 Internal Server Error**: Used for actual database errors or unexpected exceptions
  - Indicates a problem that should be investigated
  - Implies the issue isn't transient

## Example Methods Already Updated

The following methods have been updated with this pattern:
1. `_get_algo_status()` - Fetches latest algo run status
2. `_get_algo_trades()` - Fetches trade history
3. `_get_algo_positions()` - Fetches open positions
4. `_get_algo_performance()` - Calculates performance metrics
5. `_get_circuit_breakers()` - Fetches circuit breaker status
6. `_get_equity_curve()` - Fetches equity curve history
7. `_get_data_status()` - Fetches data freshness
8. `_get_notifications()` - Fetches notifications
9. `_get_signals_stocks()` - Fetches stock signals
10. `_get_signals_etf()` - Fetches ETF signals
11. `_get_price_history()` - Fetches price data

## Remaining Methods (61)

All other methods that interact with the database follow the same pattern. Search for `except Exception as e:` in lambda_function.py to find candidates for update:

```bash
grep -n "except Exception as e:" lambda/api/lambda_function.py
```

## Implementation Checklist

When updating a new method:
- [ ] Identify the main database query
- [ ] Note the primary tables being accessed
- [ ] Replace `except Exception as e:` block with full 5-handler pattern
- [ ] Update error message to be method-specific
- [ ] Add operation name to logger.error() calls
- [ ] Add relevant context (symbol, table name, etc.) to extra dict
- [ ] Test that syntax is correct: `python3 -m py_compile lambda_function.py`
- [ ] Verify method still returns proper error responses

## Testing

After updating exception handlers, verify:
1. **Syntax**: `python3 -m py_compile lambda/api/lambda_function.py`
2. **Logic**: Review the exception order is correct
3. **Error Messages**: Ensure client messages are clear and specific
4. **Logging**: Verify operation context is included in logs

## Benefits

This standardized pattern provides:
- **Observability**: Detailed logs with context for debugging
- **Resilience**: Proper distinction between transient (503) and persistent (500) errors
- **Maintainability**: Consistent pattern across all database methods
- **Safety**: Prevents silent failures and makes error causes visible
