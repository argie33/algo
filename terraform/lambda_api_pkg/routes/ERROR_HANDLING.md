# Error Handling Standardization

## Principle

All API responses must have a consistent structure that allows the dashboard to reliably detect and report errors.

## Standard Format

### Success Responses
```json
{
  "statusCode": 200,
  "data": {/* response payload */}
}
```

### Error Responses
All errors MUST include the `_error` field with a user-facing message:
```json
{
  "statusCode": 4xx or 5xx,
  "errorType": "error_category",
  "message": "User-facing error description",
  "_error": "User-facing error description"
}
```

## Key Rules

1. **Every error response must have `_error` field** — dashboard checks for this field to detect errors
2. **Database errors are NOT exposed** — clients see generic messages; full errors logged server-side
3. **`_error` field is user-facing** — should explain what happened, not implementation details
4. **Consistent across all layers** — fetchers, routes, and middleware all follow the same pattern

## Enforcing the Standard

### At the Route Level
Use the `error_response()` helper from `routes.utils`:
```python
return error_response(400, 'bad_request', 'Invalid parameter')
```

This automatically sets `_error` = message.

### At the Decorator Level
Use `db_route_handler()` decorator:
```python
@db_route_handler('operation_name', default_error_response={'items': []})
def _get_data(cur):
    # Automatic error handling with _error field
    ...
```

### At the Fetcher Level
Return dict with `_error` key on error:
```python
def fetch_data(self):
    try:
        # fetch logic
        return {'items': data, '_source': 'database'}
    except Exception as e:
        return {'_error': str(e), 'items': []}
```

## Dashboard Error Detection

The dashboard's `api_call()` function in `api_data_layer.py`:
1. Checks for `_error` key in response
2. Logs the error message
3. Returns a consistent error object

All consumers check for `_error` before using data:
```python
resp = api_call('/api/algo/positions')
if "_error" in resp:
    logger.error(f"Failed: {resp['_error']}")
    return []  # return safe default
```

## Common Patterns

### Database Errors
- **Schema issue** (UndefinedTable, UndefinedColumn): statusCode 503, message "Database schema unavailable"
- **Connection error** (OperationalError): statusCode 503, message "Database unavailable"
- **Query timeout** (QueryCanceled): statusCode 504, message "Query timeout"
- **Other DB error**: statusCode 500, message "Database query failed"

### Validation Errors
- statusCode 400, errorType 'bad_request', message describing what's invalid

### Authorization Errors
- statusCode 403, errorType 'forbidden', message "Admin access required"

### Not Found
- statusCode 404, errorType 'not_found', message "Resource not found"

## Testing Error Handling

1. **API returns error**: Response must have `_error` field
2. **Dashboard consumes error**: Check that `_error` is detected and handled
3. **Fallback is safe**: Verify defaults are used when error occurs

## Migration from Inconsistent Patterns

Existing code patterns:
- ✅ Dict with `_error` key (already correct)
- ❌ Tuple (data, error_string) — convert to dict with `_error`
- ❌ Returns empty list on error — should return dict with `_error`
- ❌ Logs error but returns OK status — must return error statusCode

See `algo_metrics_fetcher.py` for migration example: fetch_open_positions and fetch_recent_trades changed from tuple to dict format.
