# Error Handling Test Plan

## Overview
Verify that all data fetchers consistently return `_error` field in error responses, allowing the dashboard to reliably detect and report errors.

## Test Cases

### 1. API Endpoint Error Responses
All endpoints must return dict with `_error` field on error.

#### Test: Performance API Error
- **Endpoint:** `/api/algo/performance`
- **Setup:** Kill database connection or disable table
- **Expected:** `{"statusCode": 500+, "_error": "message", ...}`
- **Dashboard:** Should display "Performance data unavailable" instead of empty metrics

#### Test: Positions API Error
- **Endpoint:** `/api/algo/positions`
- **Setup:** Kill database connection
- **Expected:** `{"statusCode": 500+, "_error": "message", "data": {"items": []}}`
- **Dashboard:** Should display "Error: [message]" instead of "No open positions"

#### Test: Trades API Error
- **Endpoint:** `/api/algo/trades`
- **Setup:** Kill database connection
- **Expected:** `{"statusCode": 500+, "_error": "message", "data": {"items": []}}`
- **Dashboard:** Should return `{"_error": "...", "items": []}`

### 2. Dashboard Fetcher Error Detection
All fetch functions must detect `_error` in API response.

#### Test: fetch_perf() Error Handling
```python
# Mock API response with error
api_call_result = {"_error": "Database unavailable"}

# fetch_perf should return dict with _error key
result = fetch_perf(None)
assert result.get("_error") is not None
assert result.get("n") == 0  # Safe defaults
```

#### Test: fetch_positions() Error Handling
```python
# Mock API response with error
api_call_result = {"_error": "Connection failed"}

# fetch_positions should return dict with _error key
result = fetch_positions(None)
assert result.get("_error") is not None
assert result.get("items") == []  # Safe defaults
```

#### Test: fetch_recent_trades() Error Handling
```python
# Mock API response with error
api_call_result = {"_error": "Timeout"}

# fetch_recent_trades should return dict with _error key
result = fetch_recent_trades(None)
assert result.get("_error") is not None
assert result.get("items") == []  # Safe defaults
```

### 3. Dashboard Render Error Handling
Render functions must check for `_error` before accessing data.

#### Test: panel_positions() with Error
```python
# Mock error response
pos_data = {"_error": "Unable to fetch positions"}

# panel_positions should display error message
panel = panel_positions(pos_data)
assert "Error" in str(panel)  # Should show error, not crash
```

#### Test: panel_perf() with Error
```python
# Mock error response
perf_data = {"_error": "Performance data unavailable", "n": 0}

# Should display error safely
panel = panel_perf(perf_data)
assert "_error" in perf_data  # Error info preserved
```

#### Test: compute_sector_agg() with Error
```python
# Mock error response
pos_data = {"_error": "Could not fetch positions"}

# Should return safe defaults, not crash
sorted_secs, total, pv = compute_sector_agg(pos_data, {})
assert sorted_secs is None  # Safe return
assert total is None
assert pv == 0
```

### 4. Consistency Across Data Layer
All data sources must follow the same pattern.

#### Test: Unified Error Format
All fetchers must return one of:
1. Success: `{...data...}` (list for positions/trades, dict for other data)
2. Error: `{"_error": "message", ...}` with safe default fields

✅ No: `[]` (ambiguous - could mean no data or error)
✅ No: `{}` (ambiguous - could mean empty or error)
✅ No: Tuple `(data, error_string)` (inconsistent with API)

#### Test: Error Message Consistency
- API errors: Return `_error` with user-facing message
- Database errors: Log full error server-side, return generic message
- Network errors: Return timeout/unavailable message
- Validation errors: Return "Invalid [field]" message

### 5. Load All Parallel Fetcher Resilience
Dashboard's `load_all()` must handle individual fetcher failures.

#### Test: Single Fetcher Timeout
```python
# Simulate fetcher timeout
load_all() with one fetcher hanging

# Expected: Other fetchers complete, timeout fetcher marked as error
assert out["timing_out_fetcher"] == {"_error": "Timeout (exceeded XXXs)"}
```

#### Test: Fetcher Exception
```python
# Simulate fetcher exception
load_all() with one fetcher raising exception

# Expected: Exception caught, marked as error
assert out["failing_fetcher"] == {"_error": str(exception)}
```

## Verification Checklist

- [ ] All API endpoints return `_error` field on error (statusCode >= 400)
- [ ] All dashboard fetch functions check for `_error` in API response
- [ ] All render functions handle error responses safely (no crashes)
- [ ] Error messages are user-facing (no "table not found" etc.)
- [ ] Database errors logged server-side, generic message sent to client
- [ ] No fetcher returns empty list/dict that can't be distinguished from error
- [ ] All tuple returns migrated to dict format
- [ ] Dashboard parallel loader catches all exceptions and marks as errors

## Regression Tests

These should pass after changes:

1. Normal flow (no errors): Dashboard displays all data correctly
2. Single fetcher fails: Dashboard shows error for that section, others work
3. Multiple fetchers fail: Dashboard shows errors for multiple sections
4. Network intermittent: Retry logic in api_call handles it
5. All data unavailable: Dashboard shows all errors, still navigable

## Example Error Flow

```
User clicks "load dashboard"
  → load_all() runs 20+ fetchers in parallel
    → fetch_positions() calls api_call('/api/algo/positions')
      → HTTP 500, JSON response: {"statusCode": 500, "_error": "DB unavailable"}
      → api_call detects statusCode >= 400, returns {"_error": "DB unavailable"}
    → fetch_positions checks if data.get('_error'), returns {"_error": "...", "items": []}
    → load_all returns {"pos": {"_error": "...", "items": []}, ...}
    → render_dashboard gets this data
    → panel_positions checks if pos.get("_error"), displays error message
    → User sees: "[red]POSITIONS[/] Error: DB unavailable"
```

## Files to Test

- `lambda/api/routes/algo.py` - API handlers
- `lambda/api/routes/utils.py` - error_response() helper
- `lambda/api/api_data_layer.py` - Dashboard API client
- `tools/dashboard/dashboard.py` - Render and fetch functions
- `utils/algo_metrics_fetcher.py` - Unified metrics fetcher
