# Remaining Governance Violations (Phase 3)

**Status**: 65 VIOLATIONS REMAINING  
**Estimated Effort**: ~16 hours for systematic implementation  
**Priority**: High (Phase 3 of structured fix list)

## Overview

After completing Phases 1-2 (87 violations fixed), 65 violations remain across Phase 3. All remaining violations have exact locations, current patterns, recommended fixes, and test requirements documented below for systematic parallel implementation.

---

## Phase 3: High-Priority Marker Returns (65 Violations)

### 1. load_stock_scores.py (20+ violations)

**Remaining Violations**:
- Line 563: `_score_quality()` - `if not metrics: return None`
- Line 615: `_score_growth()` - `if not metrics: return None`
- Line 623: `_score_single_growth()` - `if val is None: return None`
- Line 668: `_score_value()` - `if not metrics: return None`
- Line 720: `_score_positioning()` - `if not metrics: return None`
- Line 766: `_score_stability()` - `if not metrics: return None`
- Line 825: `_score_momentum()` - `if not metrics: return None`
- Lines 376, 406, 436, 463, 491, 556: All `_get_*()` methods returning None

**Current Pattern**:
```python
def _score_quality(self, metrics: dict[str, Any] | None) -> float | None:
    if not metrics:
        return None
```

**Required Fix**:
```python
def _score_quality(self, metrics: dict[str, Any] | None) -> float | dict | None:
    if not metrics:
        logger.debug("[STOCK_SCORES] Quality metrics unavailable")
        return {
            "symbol": self.symbol,
            "data_unavailable": True,
            "reason": "no_quality_metrics",
            "score_type": "quality"
        }
```

**Test Requirements**:
- [ ] `_score_quality(None)` returns dict with `data_unavailable=True`
- [ ] All `_score_*()` functions return markers for empty/None inputs
- [ ] `fetch_incremental()` properly handles marker returns
- [ ] API returns markers to dashboard without errors

---

### 2. load_earnings_history.py (15+ violations)

**Remaining Violations**:
- `_convert_to_float()` returns None for missing/invalid earnings data
- `_parse_eps()` returns None on parse errors
- `_parse_revenue()` returns None on missing data

**Current Pattern**:
```python
def _convert_to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
```

**Required Fix**:
```python
def _convert_to_float(value, symbol: str, field: str):
    if value is None or value == "":
        logger.debug(f"[EARNINGS] {field} missing for {symbol}")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": f"missing_{field}"
        }
    try:
        return float(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"[EARNINGS] Parse error {field} for {symbol}: {value}")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": f"parse_error_{field}",
            "error": str(e)
        }
```

**Test Requirements**:
- [ ] Missing data returns marker dict
- [ ] Parse errors return marker with error context
- [ ] Callers distinguish missing data from computation failures
- [ ] Dashboard handles partial earnings with markers

---

### 3. load_stability_metrics.py (15+ violations)

**Remaining Violations**:
- `_calculate_volatility()` returns None for <20 prices
- `_calculate_beta()` returns None with missing benchmark data
- `_calculate_drawdown()` returns None with insufficient history

**Current Pattern**:
```python
def _calculate_volatility(prices: list[float]) -> float | None:
    if len(prices) < 20:
        return None
```

**Required Fix**:
```python
def _calculate_volatility(prices: list[float], symbol: str) -> float | dict | None:
    if len(prices) < 20:
        logger.debug(f"[STABILITY] Insufficient history for {symbol}: {len(prices)} < 20")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "insufficient_price_history",
            "data_points": len(prices),
            "required": 20
        }
```

**Test Requirements**:
- [ ] Volatility with <20 prices returns marker
- [ ] Markers include data sufficiency context
- [ ] Downstream callers handle partial metrics
- [ ] Risk calculations gracefully degrade

---

### 4. load_value_metrics.py (15+ violations)

**Remaining Violations**:
- `_calculate_pe_ratio()` returns None when earnings missing
- `_calculate_pb_ratio()` returns None when book value missing
- `_calculate_ps_ratio()` returns None when sales missing
- `_calculate_dividend_yield()` returns None when dividend missing

**Current Pattern**:
```python
def _calculate_pe_ratio(price: float, earnings: float | None) -> float | None:
    if earnings is None or earnings <= 0:
        return None
    return price / earnings
```

**Required Fix**:
```python
def _calculate_pe_ratio(price: float, earnings: float | None, symbol: str) -> float | dict | None:
    if earnings is None or earnings <= 0:
        logger.debug(f"[VALUE] Earnings missing for {symbol}: {earnings}")
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "missing_earnings",
            "metric": "pe_ratio"
        }
    return price / earnings
```

**Test Requirements**:
- [ ] Each metric returns distinct marker for missing data
- [ ] Markers include metric-specific reason
- [ ] Callers can identify which financial metrics are unavailable
- [ ] Scoring gracefully handles partial value data

---

## Implementation Strategy

### Systematic Approach:
1. **Update return type annotations** for all `_score_*()` and `_get_*()` functions
2. **Replace None returns** with explicit marker dicts (use consistent structure)
3. **Add logging** (DEBUG level) when markers are returned
4. **Update callers** to check `data_unavailable` flag instead of truthiness
5. **Test each loader** with missing/invalid input data

### Parallel Implementation:
- Each file can be fixed independently
- Test requirements can be implemented in parallel
- All fixes follow the same marker structure pattern

### Success Criteria:
- ✅ All functions return explicit markers instead of None
- ✅ Logging added at marker return points
- ✅ Test coverage for marker scenarios
- ✅ No silent None returns remain
- ✅ mypy --strict passes on all files

---

## Governance Rules Applied

**Per CLAUDE.md**:
- Optional enrichment data must return explicit `data_unavailable` markers
- Never return None without context (always fail explicitly)
- Callers must distinguish "data unavailable" from "computation error"
- All data checks must be loggable

---

## Related Documentation

- `GOVERNANCE.md` - Core governance rules
- `FAIL_FAST_AUDIT_GOVERNANCE.md` - Fail-fast patterns
- `DATA_LOADERS.md` - Loader patterns and validation
