# Database Error Logging Guide

## Overview

Database errors now capture full operational context automatically. When a database operation fails, the system logs:
- The SQL query that failed (sanitized for safety)
- Query parameters/arguments
- Operational context (stock ID, trade ID, position ID, etc.)
- Retry attempt number and maximum attempts
- Full exception traceback for debugging

This enables fast root-cause analysis (RCA) when phases fail without needing to enable verbose query logging across the entire database.

## Automatic Error Logging

### DatabaseContext (Automatic)

All database operations using `DatabaseContext` automatically capture errors:

```python
from utils.db import DatabaseContext

# Errors from this context are automatically logged with full details
with DatabaseContext("write") as cur:
    cur.execute("SELECT * FROM algo_trades WHERE trade_id = %s", (trade_id,))
    result = cur.fetchone()
```

The error log output looks like:

```json
{
  "operation": "db_operation",
  "query": "SELECT * FROM algo_trades WHERE trade_id = %s",
  "params": "[123]",
  "error_type": "OperationalError",
  "error_message": "connection lost",
  "context": {
    "symbol": "AAPL"
  }
}
```

## Structured Retry Logging

### OptimisticLockRetry with Context

When using retry logic, pass operational context to get comprehensive logging:

```python
from utils.db import OptimisticLockRetry

def update_position():
    with DatabaseContext("write") as cur:
        cur.execute("SELECT quantity FROM algo_positions WHERE position_id = %s", (pos_id,))
        current_qty = cur.fetchone()[0]
        
        cur.execute(
            "UPDATE algo_positions SET quantity = %s WHERE position_id = %s AND quantity = %s",
            (new_qty, pos_id, current_qty)
        )
        return cur.rowcount > 0

# Pass context to get full details in logs
success = OptimisticLockRetry.retry_on_race_condition(
    update_position,
    operation_name="update_position_quantity",
    query="UPDATE algo_positions SET quantity = %s WHERE position_id = %s AND quantity = %s",
    params=(new_qty, pos_id, current_qty),
    context={
        "position_id": pos_id,
        "stock_id": symbol,
        "new_quantity": new_qty,
    },
    max_attempts=3,
    base_delay_ms=100,
)
```

On retry, the log output shows:

```json
{
  "operation": "update_position_quantity",
  "attempt": 1,
  "max_attempts": 3,
  "error_type": "OperationalError",
  "delay_seconds": 0.1,
  "query": "UPDATE algo_positions SET quantity = %s ...",
  "params": "[10, 123, 5]",
  "context": {
    "position_id": 123,
    "stock_id": "AAPL",
    "new_quantity": 10
  }
}
```

## Manual Structured Logging

### StructuredDBLogger API

For operations that are not wrapped by `DatabaseContext`, use the logger directly:

```python
from utils.db import StructuredDBLogger

try:
    result = some_db_operation()
except Exception as e:
    StructuredDBLogger.log_db_error(
        operation_name="fetch_signals",
        query="SELECT * FROM algo_signals WHERE date > %s",
        params=(cutoff_date,),
        error=e,
        context={
            "stock_id": "AAPL",
            "loader_name": "load_technical_data_daily",
        },
    )
    raise
```

### Retry with Manual Logging

```python
success = OptimisticLockRetry.retry_on_exception(
    lambda: expensive_db_query(),
    operation_name="fetch_portfolio_value",
    query="SELECT SUM(position_value) FROM algo_positions",
    context={"user_id": user_id},
    max_attempts=3,
)
```

## Context Extraction

The system automatically extracts common identifiers from query parameters:
- `stock_id`, `symbol`, `ticker`
- `trade_id`, `position_id`, `order_id`
- `user_id`, `loader_name`, `correlation_id`

If these parameters are in your query args, they're automatically included in logs:

```python
# Automatically extracts "symbol" from params
cur.execute("SELECT * FROM prices WHERE symbol = %s", ("AAPL",))
# Log includes: "context": {"symbol": "AAPL"}
```

To override or add context, pass it explicitly to retry functions.

## Log Output Locations

Structured database errors are logged to:
1. **Application logs** (standard logger): Full human-readable format with traceback
2. **Structured JSON** (application logs): Machine-parsable format for aggregation
3. **Database audit log** (algo_audit_log table): All errors with context and timestamp

### Grep for Database Errors

Find all database errors with context:

```bash
# Find structured database errors (JSON format)
grep '\[DB_ERROR\]' orchestrator.log

# Find retry attempts
grep '\[DB_RETRY\]' orchestrator.log

# Find connection acquisition failures
grep '\[DB_CONTEXT_ERROR\]' orchestrator.log
```

### Example: RCA Workflow

When a phase fails with "Database error":

1. Check orchestrator logs for `[DB_ERROR]` or `[DB_RETRY]` entries
2. Look for the operation name and query that failed
3. Extract context (stock_id, trade_id, etc.) from the error
4. Reproduce using that exact combination

Example log extraction:

```
[DB_ERROR] {"operation": "update_position_123", "query": "UPDATE ...", 
  "error_type": "OperationalError", "context": {"stock_id": "TSLA", "position_id": 123}}

→ Now you can reproduce:
  SELECT * FROM algo_positions WHERE position_id = 123
  SELECT * FROM algo_trades WHERE symbol = 'TSLA'
```

## Best Practices

### 1. Always Pass Context to Retry Functions

```python
# Good: Retry functions get context
success = OptimisticLockRetry.retry_on_race_condition(
    operation,
    operation_name="update_trade",
    context={"trade_id": trade_id, "symbol": symbol},
)

# Bad: No context, harder to troubleshoot
success = OptimisticLockRetry.retry_on_race_condition(operation)
```

### 2. Use Meaningful Operation Names

```python
# Good: Specific operation name
operation_name="exit_position_AAPL_2024_06_20"

# Bad: Generic operation name
operation_name="update"
```

### 3. Include Identifiers in Context

```python
context = {
    "stock_id": symbol,
    "trade_id": trade_id,
    "position_id": position_id,
    "user_id": user_id,
    "phase": "phase4_exit_execution",
}
```

### 4. Log Query Patterns (Not Values)

Queries are sanitized to avoid logging sensitive data. Don't include actual prices/passwords in logs:

```python
# Good: Query shows structure, params are separate
query = "UPDATE algo_positions SET quantity = %s WHERE position_id = %s"
params = (new_qty, pos_id)

# Bad: Embedding values (also gets masked anyway)
query = f"UPDATE ... WHERE position_id = {pos_id}"
```

## Troubleshooting

### Issue: "Database error" with no details

**Problem**: DatabaseContext failed before executing a query.

**Solution**: Check for `[DB_CONTEXT_ERROR]` in logs. These are connection acquisition failures and show why the connection pool is exhausted (timeout, too many open connections, etc.).

```bash
grep '\[DB_CONTEXT_ERROR\]' orchestrator.log
```

### Issue: Query executes but timeout is wrong

**Problem**: Retry is stuck on a long-running query.

**Solution**: Check the retry logs for delay_seconds. If delays are small (100ms, 200ms, etc.), the query is retrying quickly. If the error is consistent, increase max_attempts or adjust base_delay_ms.

### Issue: Context extraction missed my identifier

**Problem**: Custom field like "campaign_id" isn't in automatic context.

**Solution**: Pass context explicitly:

```python
context = {
    "symbol": symbol,
    "campaign_id": campaign_id,  # Custom field
    "loader_name": "load_campaign_signals",
}
OptimisticLockRetry.retry_on_race_condition(
    operation,
    context=context,
)
```

## Security Notes

- Query text is sanitized (comments removed, whitespace compressed)
- Parameter values are shown but truncated (first 50 chars)
- Passwords, API keys: never in query text (should be in bind parameters)
- Long bulk operations: first N parameters shown, rest counted as "+N more"

To exclude a parameter from logs, don't pass it to the database function (use application logic instead).
