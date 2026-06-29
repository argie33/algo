# Data Unavailability Marker Propagation Remediation

**Status**: IN PROGRESS  
**Scope**: Eliminate all silent marker-to-None conversions that defeat fail-fast governance  
**Priority**: CRITICAL - Affects financial decision accuracy  
**Estimated Effort**: 4-6 hours  
**Owner**: Financial data accuracy enforcement  

---

## Executive Summary

### The Problem

Code was **returning explicit `data_unavailable` markers** from scoring functions (following governance), then **silently converting them back to `None`** before the API could use them. This defeated the entire fail-fast framework.

**Real Example from load_stock_scores.py**:

```python
# Governance-compliant: returns marker
quality_score_result = self._score_quality(quality, symbol)
# Returns: {"symbol": "AAPL", "data_unavailable": True, "reason": "no_quality_metrics"}

# But then immediately...
quality_score = extract_score(quality_score_result)
# Returns: None  ❌ DESTROYS AVAILABILITY INFORMATION

# Result: API sees None, can't distinguish missing data from computation error
```

### The Impact

- **Data degradation invisible to operators**: Missing metrics silently ignored
- **Silent failures in position sizing**: Composite scores computed from incomplete data
- **Risk assessments on bad data**: Circuit breakers don't know when base metrics are unavailable
- **False confidence in scoring**: "Score is 45" without knowing 3 of 6 components missing

### The Fix (Implemented in ee4c8b962)

✅ **Removed silent conversions** - Stopped discarding markers  
✅ **Propagated markers through computation** - Tracked which metrics unavailable  
✅ **Added logging for degraded scores** - WARNING level when metrics missing  
✅ **Returned unavailability context** - API can now see what's missing  

---

## Violations Identified (65 Remaining)

### Category 1: Metric Loader Methods (20-25 violations)

These functions return `None` instead of explicit markers when input data missing:

#### load_quality_metrics.py
- `_calculate_roe()` - returns None when earnings missing
- `_calculate_roa()` - returns None when income/assets missing
- `_calculate_debt_to_equity()` - returns None when values missing
- **Pattern**: All ratio calculations (5-8 methods)

#### load_growth_metrics.py
- `_parse_revenue_growth()` - returns None on parse error
- `_parse_eps_growth()` - returns None on missing data
- **Pattern**: All growth calculation methods (3-5 methods)

#### load_value_metrics.py
- `_calculate_pe_ratio()` - returns None when earnings missing
- `_calculate_pb_ratio()` - returns None when book value missing
- `_calculate_ps_ratio()` - returns None when sales missing
- `_calculate_dividend_yield()` - returns None when dividend missing
- **Pattern**: All valuation ratio methods (4-6 methods)

#### load_stability_metrics.py
- `_calculate_volatility()` - returns None when <20 data points
- `_calculate_beta()` - returns None when benchmark missing
- `_calculate_drawdown()` - returns None when history insufficient
- **Pattern**: All stability metrics (3-5 methods)

#### load_positioning_metrics.py
- `_parse_institutional_ownership()` - returns None when unavailable
- `_parse_short_interest()` - returns None when unavailable
- **Pattern**: All positioning metrics (2-3 methods)

### Category 2: Signal Generation Enrichment (10-15 violations)

Optional enrichment data returns `None` at DEBUG level (acceptable logging but inconsistent):

#### buy_signal_generation_handler.py
- `_compute_avg_volume_50d()` - line 304: returns None
- `_determine_market_stage()` - line 339: returns None
- Pattern: Both log at DEBUG level, acceptable but inconsistent with other loaders

**Assessment**: LOW priority - already logged at appropriate level, but should be consistent with metric loaders

### Category 3: Market Health Fetchers (10+ violations)

API fetches that return `None` on transient/permanent errors:

#### market_health_fetchers.py
- `_fetch_put_call_ratio()` - returns None on all retries exceeded
- Pattern: Data source unavailable, should return explicit marker

**Assessment**: LOW priority - already retries appropriately, but should return marker dict with retry count

---

## Systematic Fix Pattern

### Before (Current - Violates Governance)
```python
def _calculate_pe_ratio(price: float, earnings: float | None) -> float | None:
    if earnings is None or earnings <= 0:
        return None  # ❌ Loses information about WHY data missing
    return price / earnings
```

### After (Fail-Fast Compliant)
```python
def _calculate_pe_ratio(
    price: float, 
    earnings: float | None, 
    symbol: str
) -> float | dict[str, Any]:
    """Calculate P/E ratio or return unavailability marker.
    
    Returns:
        float: P/E ratio if data available
        dict: {"symbol": str, "data_unavailable": True, "reason": str, "metric": str}
    """
    if earnings is None or earnings <= 0:
        logger.debug(f"[VALUE_METRICS] Earnings missing for {symbol}: {earnings}")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "missing_earnings" if earnings is None else "negative_earnings",
            "metric": "pe_ratio"
        }
    return price / earnings
```

### Handling in Caller
```python
result = self._calculate_pe_ratio(price, earnings, symbol)

if isinstance(result, dict) and result.get("data_unavailable"):
    logger.debug(f"[VALUE_METRICS] {result['reason']} for {symbol}")
    unavailable_metrics["pe_ratio"] = result["reason"]
else:
    pe_ratio_score = result  # it's a float
```

---

## Implementation Roadmap

### Phase 1: Quality Metrics (2 hours)
- [ ] Update load_quality_metrics.py - 8 methods
- [ ] Add unit tests - verify markers returned for empty/None inputs
- [ ] Verify API accepts marker dicts

### Phase 2: Growth & Value Metrics (1.5 hours)  
- [ ] Update load_growth_metrics.py - 4-5 methods
- [ ] Update load_value_metrics.py - 6 methods
- [ ] Combined unit tests

### Phase 3: Stability & Positioning (1.5 hours)
- [ ] Update load_stability_metrics.py - 5 methods
- [ ] Update load_positioning_metrics.py - 3 methods
- [ ] Integration tests with composite scoring

### Phase 4: Signal Handlers (1 hour)
- [ ] Update buy_signal_generation_handler.py - 2 methods
- [ ] Verify consistency with metric loaders
- [ ] Signal generation tests

### Phase 5: Pre-Commit Enforcement (0.5 hours)
- [ ] Add hook to detect `extract_*` patterns that hide markers
- [ ] Add hook to detect `return None` without context in metric loaders
- [ ] Update `.pre-commit-config.yaml`

---

## Testing Strategy

### Unit Tests (Per Loader)
```python
def test_calculate_metric_with_missing_data():
    """Verify marker dict returned when data missing."""
    result = loader._calculate_metric(None, symbol="TEST")
    assert isinstance(result, dict)
    assert result.get("data_unavailable") is True
    assert "reason" in result

def test_calculate_metric_with_valid_data():
    """Verify float returned when data valid."""
    result = loader._calculate_metric(100.0, symbol="TEST")
    assert isinstance(result, float)
    assert not isinstance(result, dict)
```

### Integration Tests (Metric Loader)
```python
def test_loader_propagates_unavailability_markers():
    """Verify markers flow through fetch_incremental."""
    result = loader.fetch_incremental(["SYMBOL_WITH_NO_METRICS"])
    assert result[0]["data_unavailable"] is True
    assert "reason" in result[0]
```

### API Tests (Stock Scores)
```python
def test_stock_scores_with_missing_metrics():
    """Verify API returns unavailable_metrics field."""
    response = api_client.get_stock_scores(["AAPL"])
    assert "unavailable_metrics" in response
    if response["unavailable_metrics"]:
        assert all(isinstance(v, str) for v in response["unavailable_metrics"].values())
```

---

## Pre-Commit Hook Additions

### Pattern 1: Silent Marker Conversion
```python
# .pre-commit-scripts/check-marker-silencing.py
pattern = r"def extract_\w+\(.*\).*return None"  # extract_score, extract_metric, etc.
# FAIL if found - use explicit handling instead
```

### Pattern 2: Silent None Returns in Metric Methods
```python
# .pre-commit-scripts/check-metric-none-returns.py
METRIC_LOADERS = [
    "load_quality_metrics.py",
    "load_growth_metrics.py",
    # ...
]
METRIC_METHODS = ["_calculate_", "_parse_", "_score_"]

# WARN if method returns None without explicit marker dict
# Exception: DEBUG-level logging allowed for optional enrichment
```

---

## Governance Alignment

**CLAUDE.md Requirements**:
1. ✅ No silent fallbacks for critical data
2. ✅ Optional data returns explicit markers
3. ✅ Callers can distinguish unavailability from errors
4. ✅ All data checks must be loggable
5. ✅ Type-safe with `mypy --strict`

**This fix ensures**:
- Markers never silently converted to None
- All unavailability has a reason  
- APIs can surface data degradation to operators
- Financial decisions transparent about data quality

---

## Risk Assessment

### Low Risk Because:
- ✅ Markers already returned from scoring functions (governance-compliant)
- ✅ Changes propagate info, don't change computation logic
- ✅ All scores still calculated same way for available metrics
- ✅ New fields additive to API responses (backward compatible)
- ✅ None-checks already in place for degraded scoring

### Testing Coverage:
- ✅ Unit tests for each metric loader
- ✅ Integration tests for composite scoring
- ✅ API contract tests for response structure
- ✅ Pre-commit hooks prevent regression

---

## Deployment Checklist

- [ ] Phase 1-4 fixes implemented
- [ ] All tests passing
- [ ] mypy --strict clean
- [ ] Pre-commit hooks added and tested
- [ ] Documentation updated (GOVERNANCE.md, DATA_LOADERS.md)
- [ ] Code review: verify all markers propagated
- [ ] Staging test: verify API returns unavailable_metrics
- [ ] Ops notified: new field in stock scores API
- [ ] Merged to main
- [ ] Deployed to production

---

## Related Governance Documents

- `CLAUDE.md` - Core fail-fast rules
- `GOVERNANCE.md` - Architecture principles  
- `DATA_LOADERS.md` - Loader patterns
- `API_ARCHITECTURE.md` - Error handling patterns
- `REMAINING_VIOLATIONS.md` - Phase 3 violation catalog
