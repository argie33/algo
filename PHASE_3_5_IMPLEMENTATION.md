# Phase 3.5: API Endpoint Hardening Implementation

## Status: IN PROGRESS ⏳

This document tracks the implementation of fail-fast validation across API routes and Dashboard consumers.

## Current State Assessment

### ✅ Already Using data_unavailable
- `fetchers_portfolio.py`: Returns data_unavailable for missing performance data
- `fetchers_signals.py`: Returns data_unavailable for missing signal data
- `dashboard/error_boundary.py`: Handles error markers gracefully
- `dashboard/panels/`: All panels use safe_get_list() which returns marker dicts

### ✅ Already Checking Freshness
- `lambda/api/routes/algo_handlers/external.py`: Validates economic_calendar freshness
- API routes using `check_data_freshness()` before data access

### ❌ Need Hardening
The following fetchers need explicit data_unavailable marker validation:

1. **fetchers_market.py** (fetch_risk_metrics)
   - Currently: Returns risk data directly
   - Needed: Validate critical fields (VaR, CVaR, Beta)
   - Status: ⏳ Implementation pending

2. **fetchers_market.py** (fetch_breadth)
   - Currently: Returns breadth data directly
   - Needed: Optional data validation pattern
   - Status: ⏳ Implementation pending

3. **fetchers_market.py** (fetch_macro_data)
   - Currently: Returns macro data directly
   - Needed: Optional data validation for economic data
   - Status: ⏳ Implementation pending

4. **fetchers_market.py** (fetch_sentiment)
   - Currently: Returns sentiment directly
   - Needed: Validate sentiment availability
   - Status: ⏳ Implementation pending

5. **fetchers_sector.py** (all fetchers)
   - Currently: Returns sector data directly
   - Needed: Validate sector data freshness
   - Status: ⏳ Implementation pending

## Implementation Pattern (Example: fetch_risk_metrics)

### Before (Current)
```python
def fetch_risk_metrics(c: None) -> dict[str, Any]:
    """Fetch risk metrics from API."""
    data = api_call(get_endpoint_path("risk_metrics"))
    return {
        "var": safe_float(data.get("var_95")),
        "cvar": safe_float(data.get("cvar_95")),
        "beta": safe_float(data.get("beta")),
    }
```

### After (Phase 3.5)
```python
from utils.api_hardening import ensure_critical_data, validate_dashboard_data

def fetch_risk_metrics(c: None) -> dict[str, Any]:
    """Fetch risk metrics from API (fail-fast on missing critical fields)."""
    data = api_call(get_endpoint_path("risk_metrics"))
    
    # Validate critical fields required for risk assessment
    is_valid, error_msg = validate_dashboard_data(
        data,
        required_fields=["var_95", "cvar_95", "beta"],
        endpoint="risk_metrics"
    )
    
    if not is_valid:
        logger.error(f"[HARDENING] Risk metrics unavailable: {error_msg}")
        return {
            "_error": error_msg,
            "data_unavailable": True,
            "reason": "risk_metrics_incomplete"
        }
    
    return {
        "var": safe_float(data.get("var_95")),
        "cvar": safe_float(data.get("cvar_95")),
        "beta": safe_float(data.get("beta")),
        "status": "ok"
    }
```

## Implementation Checklist

### Phase 3.5a: Market Data Hardening
- [ ] Update `fetch_risk_metrics` - Validate critical risk fields
- [ ] Update `fetch_breadth` - Optional breadth validation
- [ ] Update `fetch_macro_data` - Optional macro validation
- [ ] Update `fetch_sentiment` - Validate sentiment availability
- [ ] Add error detection to `fetch_vix` if needed

### Phase 3.5b: Sector Data Hardening
- [ ] Update `fetch_sector_ranking` - Validate sector data
- [ ] Update `fetch_industry_ranking` - Validate industry data
- [ ] Update `fetch_rotation_signals` - Validate rotation signals

### Phase 3.5c: API Route Hardening
- [ ] Add validation middleware to `lambda_function.py`
- [ ] Update risk_dashboard routes with error checking
- [ ] Update market routes with error checking
- [ ] Update sentiment routes with error checking

### Phase 3.5d: Dashboard Consumer Updates
- [ ] Update panel headers to show error states
- [ ] Add error messages to risk displays
- [ ] Update error boundary to categorize new error types
- [ ] Test dashboard graceful degradation on errors

## Testing Strategy

### Unit Tests (Per Fetcher)
```python
def test_fetch_risk_metrics_missing_critical_field():
    """Should return error when critical field missing."""
    with patch('dashboard.fetchers_market.api_call') as mock_call:
        mock_call.return_value = {"var_95": 2.5}  # Missing cvar_95, beta
        result = fetch_risk_metrics(None)
        assert result.get("_error") is not None
        assert result.get("data_unavailable") is True
```

### Integration Tests
```python
def test_dashboard_shows_error_on_missing_risk_data():
    """Dashboard should show error placeholder on risk data failure."""
    # Mock fetcher to return error
    # Render dashboard
    # Assert error message visible
    pass
```

## Success Criteria

✅ Phase 3.5 is complete when:
- All critical fetchers validate required fields
- All fetchers return proper error responses (not silent None)
- All dashboard panels handle error responses gracefully
- All tests pass (1,023+ tests)
- No data_unavailable errors are silent

## Time Estimate

- Phase 3.5a (Market data): 1-2 hours
- Phase 3.5b (Sector data): 30 minutes
- Phase 3.5c (API routes): 30 minutes
- Phase 3.5d (Dashboard): 1 hour
- Testing & validation: 30 minutes
- **Total: 3-4 hours**

## Deployment

Phase 3.5 deploys alongside Phase 4 monitoring setup:
- Week 2: Implement all hardening
- Week 3: Full integration testing
- Week 4: Deploy with Phase 4 monitoring

---

Status: **Foundation ready for implementation**  
Next: Update fetchers_market.py with validation pattern
