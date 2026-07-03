# API Hardening Guide - Phase 3 Production Hardening

## Overview

Phase 3 extends fail-fast patterns to API routes and Dashboard consumers. This document explains:
1. **What changed**: New fail-fast validation in API responses
2. **Why**: Prevent silent failures and partial data returns
3. **How to migrate**: Update your API consumers
4. **Error handling**: Proper error codes and HTTP status codes

## New Error Response Format

Starting with Phase 3, API responses include explicit error markers for missing critical data:

### Error Response (when critical data unavailable)

```json
{
  "_error": "string describing the error",
  "error_code": "missing_data | validation_error | upstream_error",
  "timestamp": "2026-07-03T16:00:00Z"
}
```

### Success Response (unchanged)

```json
{
  "data": { ... },
  "status": "ok"
}
```

## HTTP Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | Data available and valid | Use data |
| 409 | Critical data missing or malformed | Retry after data loads |
| 503 | Upstream service unavailable | Retry with exponential backoff |
| 500 | Internal server error | Check logs, contact support |

## Migration Guide

### Before (Phase 2)
```javascript
// Old: Assume data is always present
const data = await fetch('/api/positions').then(r => r.json());
const positions = data.positions;  // Could be undefined silently
```

### After (Phase 3)
```javascript
// New: Check for error markers
const response = await fetch('/api/positions').then(r => r.json());

if (response._error) {
  // Handle error appropriately
  if (response.status === 409) {
    // Retryable: Critical data not yet available
    setTimeout(() => retryFetch(), 5000);
  } else if (response.status === 503) {
    // Service unavailable: Retry with backoff
    exponentialBackoff();
  } else {
    // Other error: Log and alert user
    showError(response._error);
  }
  return;
}

// Data is guaranteed valid
const positions = response.positions;
```

## Dashboard Integration

The Dashboard now handles API errors gracefully:

### Error Detection

```javascript
import { check_data_error } from '../utils/api_hardening';

// Check if API response has error marker
const errorMsg = check_data_error(apiResponse, 'positions');
if (errorMsg) {
  // Handle error: log, retry, or show user message
  console.error('Position data unavailable:', errorMsg);
  return showEmptyPanel('Positions loading...');
}

// Data is valid - use it
renderPositions(apiResponse);
```

### Graceful Degradation

```javascript
// When critical data unavailable, show placeholder
function renderDashboard(data) {
  if (data._error) {
    return {
      positions: { 
        status: 'loading',
        message: 'Position data loading, please wait...'
      },
      risk: {
        status: 'loading',
        message: 'Risk metrics calculating...'
      }
    };
  }
  
  return renderFullDashboard(data);
}
```

## API Route Implementation

### Pattern 1: Validate Critical Data (MUST be present)

```python
from utils.api_hardening import ensure_critical_data

def _get_positions(cur):
    """Get open positions (fails fast if price data unavailable)."""
    
    # Fetch position data
    positions_data = fetch_positions(cur)
    
    # CRITICAL: Price data is required for position calculations
    try:
        prices = ensure_critical_data(positions_data, 'prices')
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"[HARDENING] Positions: {error_msg}")
        return error_response(409, 'missing_prices', error_msg)
    
    # Price data is guaranteed valid - safe to use
    return {
        'positions': calculate_positions(prices),
        'status': 'ok'
    }
```

### Pattern 2: Validate Optional Data (MAY be missing)

```python
from utils.api_hardening import check_data_error, get_safe_value

def _get_market_data(cur):
    """Get market data (breadth is optional)."""
    
    # Fetch breadth data (optional enrichment)
    breadth_data = fetch_market_breadth(cur)
    
    # OPTIONAL: Breadth data may be unavailable
    breadth_error = check_data_error(breadth_data, 'breadth')
    breadth = None
    if not breadth_error:
        # Data is available - use it
        breadth = get_safe_value(breadth_data, 'nh_count')
    else:
        # Data unavailable - log and continue without it
        logger.warning(f"Breadth data unavailable: {breadth_error}")
    
    return {
        'vix': fetch_vix(cur),
        'breadth': breadth,  # May be None
        'status': 'ok'
    }
```

### Pattern 3: Multiple Critical Fields

```python
from utils.api_hardening import validate_required_fields

def _get_portfolio(cur):
    """Get portfolio metrics (all fields critical)."""
    
    portfolio = fetch_portfolio(cur)
    
    # Validate all critical fields present
    validation = validate_required_fields(
        portfolio,
        required_fields=['total_value', 'cash', 'exposure_pct'],
        context='portfolio'
    )
    
    if not validation['valid']:
        return error_response(409, validation['error_code'], validation['error_message'])
    
    # All fields validated - safe to use
    return {
        'portfolio': portfolio,
        'status': 'ok'
    }
```

## Common Patterns

### Check for Error Before Using Data
```python
if response.get('_error'):
    # Don't use this data
    return error_response(response.get('http_status', 500), 
                         response.get('error_code'), 
                         response.get('_error'))
```

### Check for data_unavailable Marker
```python
if response.get('data_unavailable'):
    reason = response.get('reason', 'Unknown')
    logger.warning(f"Data unavailable: {reason}")
    return error_response(409, 'data_unavailable', reason)
```

### Safe Field Access
```python
from utils.api_hardening import get_safe_value

# Returns field value if present, or None/default if missing
price = get_safe_value(data, 'price', default=0)

# If data_unavailable marker present, returns None
volatility = get_safe_value(volatility_data, 'volatility')
```

## Testing Error Paths

### Test 1: Verify error marker detected
```python
def test_api_detects_missing_data():
    """Verify API returns error when critical data missing."""
    response = fetch_api('/api/positions')
    assert response.status_code in [409, 503]  # Retryable errors
    assert '_error' in response.json()
```

### Test 2: Verify graceful degradation
```python
def test_dashboard_handles_missing_data():
    """Verify Dashboard shows placeholder when data unavailable."""
    data = {'_error': 'Positions loading...'}
    panel = render_positions_panel(data)
    assert 'loading' in panel.lower()
```

## Rollback Plan

If errors occur during Phase 3:

1. **Revert** the new API routes to Phase 2 versions
2. **Monitor** error logs for patterns
3. **Fix** the underlying data loader issue
4. **Re-test** with Phase 3 hardening enabled

The hardening is **additive** - it doesn't break existing functionality, it just makes errors more explicit.

## Support

For questions about Phase 3 hardening:
1. Check this guide first
2. Search codebase for example implementations
3. Review test files for usage patterns
4. Contact the data engineering team

---

**Phase 3 Status**: ✅ Hardening utilities deployed  
**Next Step**: Update API routes to use hardening utilities  
**Target**: All critical API endpoints hardened by 2026-07-10
