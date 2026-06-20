# Fix Dashboard Data Issues - Strategic Guide

## Goal
Use the dashboard as a **diagnostic tool** to find and fix real data issues. Show only real data, never placeholder/fallback values.

## Strategy: Three Layers of Validation

### Layer 1: API Boundary (api_data_layer.py)
- All API responses validated before returning to fetchers
- Implements retry logic with exponential backoff (capped at 30s)
- Circuit breaker pattern prevents hammering downed APIs
- Caches responses for fallback during outages
- Returns `{"_error": "message"}` only on failure, never placeholder data

### Layer 2: Endpoint Validators (response_validators.py)
- 15+ validators for critical endpoints (portfolio, performance, markets, etc.)
- Validates critical fields exist and can be converted to correct type
- On failure: returns `{"_error": "message"}` immediately
- Prevents silently accepting invalid data

### Layer 3: Fetchers (fetchers.py)
- Check `_is_api_error(data)` → return error dict immediately
- Validate critical fields before returning success
- On stale data: return `{"_error": "...", "_data_stale": True}`
- On missing required fields: return `{"_error": "..."}`
- **Key rule:** Return ONLY `{"_error": "..."}` on failure, NO fallback structures with None values

## How to Identify Issues

### Run Diagnostic to Find Problems

```bash
python -m tools.dashboard.diagnose_dashboard
```

Output shows:
- **✓ Success** - Data loading correctly
- **⚠ Stale** - Loader hasn't run recently (data is old but usable)
- **✗ Errors** - API call failed or validation failed
- **⚡ Missing fields** - Data returned but some fields unexpectedly None

### Run Dashboard to See Issues Visually

```bash
python -m tools.dashboard.dashboard -w 30
```

The error panel at the top shows:
- Red [✗] for hard errors (critical data unavailable)
- Yellow [⚠] for stale data (old but present)
- Press [d] to expand and see all failed endpoints

## How to Fix Issues

### Type 1: API/Network Errors (✗)

**Problem:** API endpoint not responding

**Fix:**
1. Check API is running: `curl https://api-url/api/health`
2. Check logs: AWS CloudWatch → Lambda logs
3. Check RDS: Ensure security groups allow VPC access
4. If auth failed: Regenerate Cognito tokens

### Type 2: Stale Data (⚠)

**Problem:** Scheduled loaders haven't run recently

**Fix:**
```bash
# Option 1: Trigger via GitHub Actions
gh workflow run manual-invoke-loaders.yml \
  -f loaders="portfolio,performance"

# Option 2: Run locally
python -m loaders.load_portfolio_snapshot
python -m loaders.load_performance_metrics
```

### Type 3: Missing Fields (⚡)

**Problem:** API returned but some fields are None

**Fix:**
1. Check if field is optional (look in `response_validators.py`)
2. If required: Check database directly
   ```sql
   SELECT * FROM portfolio ORDER BY last_updated DESC LIMIT 1;
   ```
3. Check loader logs for errors
4. If loader failed: Re-run it with verbose logging

## Fetcher Refactoring Checklist

When adding a new endpoint or fixing a broken one, follow this pattern:

```python
def fetch_something(c):
    """Fetch data from API."""
    try:
        data = api_call("/api/endpoint")
        
        # 1. Check for API-level error
        if _is_api_error(data):
            return data  # Already has {"_error": "..."}
        
        # 2. Validate required fields exist
        if "critical_field" not in data:
            error_msg = "Missing critical_field"
            logger.error(error_msg)
            record_data_quality_issue("endpoint", "critical_field", "missing")
            return {"_error": error_msg}
        
        # 3. Validate data freshness if time-sensitive
        is_fresh, freshness_error = _check_data_freshness(
            data.get("timestamp"), max_age_seconds=3600, source_name="SomethingData"
        )
        if not is_fresh:
            logger.warning(freshness_error)
            record_data_quality_issue("endpoint", "timestamp", "data_stale", freshness_error)
            return {"_error": freshness_error, "_data_stale": True}
        
        # 4. Convert fields with strict validation (no silent None fallbacks)
        try:
            value = safe_float_strict(data["some_field"], "endpoint.some_field")
        except StrictValidationError as e:
            error_msg = f"Conversion failed: {e}"
            logger.error(error_msg)
            record_data_quality_issue("endpoint", "some_field", "conversion_failed", str(e))
            return {"_error": error_msg}
        
        # 5. Return only real data (use .get() for truly optional fields)
        return {
            "required_field": value,
            "optional_field": data.get("optional"),  # get() ok here - legitimately optional
        }
    
    except Exception as e:
        error_msg = _format_fetcher_error("something", e)
        logger.error(error_msg)
        return {"_error": error_msg}
```

**Key points:**
- ✅ Use `.get()` for truly optional fields
- ❌ Don't use `.get()` for critical fields
- ✅ Validate types strictly (safe_float_strict, not safe_float)
- ❌ Don't return `{"field": None}` - that's a placeholder
- ✅ Log every error with `record_data_quality_issue()`
- ✅ Return ONLY `{"_error": "..."}` on failure

## Panel Error Handling Checklist

When writing/fixing a panel:

```python
def panel_something(data):
    """Render something panel."""
    
    # 1. Check for error FIRST
    err_panel = _error_panel("data", data, "TITLE", border="color")
    if err_panel:
        return err_panel
    
    # 2. At this point, data is guaranteed valid (no error, no stale flag)
    # Safe to access critical fields directly
    value = data["critical_field"]
    
    # 3. Optional fields can use .get() since they're genuinely optional
    optional = data.get("optional_field", default_value)
    
    # 4. Build panel with real data (never fallback to dashes/zeros)
    return Panel(...)
```

**Key points:**
- ✅ Call `_error_panel()` first
- ✅ Only render if no error
- ✅ Access critical fields directly (no `.get()` with defaults)
- ❌ Never show placeholder values (dashes, zeros, "unknown")
- ✅ Use `.get()` only for genuinely optional fields

## Verification After Fixes

### 1. Run Diagnostic
```bash
python -m tools.dashboard.diagnose_dashboard
# Check: All critical fetchers show "✓ Success"
# Check: No "✗ ERRORS" section
# Check: No "⚠ STALE" section (or acceptable age)
```

### 2. Run Dashboard
```bash
python -m tools.dashboard.dashboard
# Check: No error panel at top
# Check: All data visible (real values, not placeholders)
# Check: Portfolio/performance/positions all show
```

### 3. Test Suite
```bash
pytest tests/test-dashboard-aws.py -v
# All tests pass
# No warnings about missing fields
```

## Critical Fields by Endpoint

These fields cause silent failures if missing. Always validate them:

| Endpoint | Critical Fields | Why Critical |
|----------|-----------------|--------------|
| `/api/algo/portfolio` | `total_portfolio_value`, `total_cash`, `position_count` | Portfolio display, position count, cash management |
| `/api/algo/performance` | `total_trades`, `winning_trades`, `losing_trades` | Win rate calculation, metrics |
| `/api/algo/markets` | `spy_close`, `vix_level`, `regime` | Position sizing, risk management |
| `/api/algo/config` | `enable_algo`, `execution_mode`, `max_positions` | Safety gates, execution rules |
| `/api/algo/last-run` | `phases`, `success`, `halted`, `run_at` | Algo health, phase status |

## Freshness Thresholds

Data older than these ages should be marked stale:

| Data Type | Max Age | Reason |
|-----------|---------|--------|
| Portfolio | 5 days | Algo only runs trading days; long weekend = 4 calendar days |
| Performance | 1 hour | PnL changes frequently during trading |
| Market data | 24 hours | Daily data ok, but overnight updates important |
| Health/Status | 1 hour | Operational data needs freshness |
| Config | N/A (rarely changes) | Only when explicitly updated |

## References

- **CLAUDE.md** → Dashboard API Validation Strategy (architecture decision)
- **tools/dashboard/fetchers.py** → Fetcher implementations (examples)
- **tools/dashboard/response_validators.py** → Validation rules
- **tools/dashboard/error_boundary.py** → Error detection utilities
- **tools/dashboard/panels/_helpers.py** → `_error_panel()` helper
- **steering/dashboard-diagnostics.md** → Troubleshooting guide
