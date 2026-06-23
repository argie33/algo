# API Fail-Fast Fixes - Session 2026-06-22

**Objective:** Address remaining API endpoint fallback patterns that should fail fast for a finance app.

**Completed:** 6 critical API endpoints converted from fallback to fail-fast

---

## Changes Summary

### Critical Trading Data Endpoints

#### 1. Market Factors Endpoint (algo_handlers/market.py:468-477)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/algo_handlers/market.py`
- **Function:** `_get_market_factors()`
- **Change:** Replaced returning empty data dict with `error_response(503, "data_unavailable", ...)`
- **Why:** Dashboard needs exposure factors for position sizing calculations. Empty dict masks data loader failures.
- **Impact:** Clients now get 503 vs 200 with null fields, enabling explicit error handling

#### 2. Markets Core Data Endpoint (algo_handlers/market.py:574-581)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/algo_handlers/market.py`
- **Function:** `_get_markets()`
- **Change:** Replaced returning empty `list_response` to returning `error_response(503, ...)`
- **Why:** Core endpoint for market health, regime, and sector rotation. Cannot render dashboard with empty data.
- **Impact:** Dashboard detects missing data and shows loading state vs stale/empty content

#### 3. Configuration Key Lookup (algo_handlers/config.py:70)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/algo_handlers/config.py`
- **Function:** `_get_algo_config_key()`
- **Change:** Replaced returning empty dict `{}` with `error_response(404, "not_found", ...)`
- **Why:** Config reads are explicit lookups. Empty dict is ambiguous (missing vs empty config).
- **Impact:** Clients know key doesn't exist vs config is unset

#### 4. Orchestrator Status (algo_handlers/monitoring.py:93)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/algo_handlers/monitoring.py`
- **Function:** `_get_last_run()`
- **Change:** Replaced returning empty phases `{run_id: None, ...phases: []}` with `error_response(503, "no_data", ...)`
- **Why:** Dashboard relies on orchestrator run status. Empty phases implies run completed vs no data.
- **Impact:** Dashboard correctly shows "loading" state vs false "no phases completed"

#### 5. Portfolio Dashboard (algo_handlers/dashboard.py:252)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/algo_handlers/dashboard.py`
- **Function:** `_get_portfolio_dashboard()`
- **Change:** Replaced returning `{"status": "no_runs_yet", "portfolio": {}}` with `error_response(503, ...)`
- **Why:** Empty portfolio object is ambiguous. Clients need explicit "data not available" signal.
- **Impact:** Dashboard shows loading indicator vs empty portfolio state

#### 6. NAAIM Market Sentiment (market.py:709-784)
**Status:** ✅ FIXED (2 locations)
- **File:** `lambda/api/routes/market.py`
- **Function:** `_get_naaim_sentiment()`
- **Changes:**
  - Line 709: Replaced returning empty data when no rows → `error_response(503, ...)`
  - Line 784: Replaced returning empty when history empty → `error_response(503, ...)`
- **Why:** NAAIM (National Association of Active Investment Managers) is key market sentiment indicator for position sizing.
- **Impact:** Clients get explicit data availability signal vs null sentiment data

#### 7. Market Sentiment / VIX (sentiment.py:412)
**Status:** ✅ FIXED
- **File:** `lambda/api/routes/sentiment.py`
- **Function:** `_get_vix_sentiment()`
- **Change:** Replaced returning `{latest: None, history: []}` with `error_response(503, ...)`
- **Why:** VIX is critical for volatility assessment. Empty history with None latest is confusing.
- **Impact:** Clients know to retry vs processing empty sentiment data

---

## Files Modified

| File | Endpoints | Changes | Status |
|------|-----------|---------|--------|
| algo_handlers/market.py | _get_market_factors, _get_markets | 2 | ✅ |
| algo_handlers/config.py | _get_algo_config_key | 1 | ✅ |
| algo_handlers/monitoring.py | _get_last_run | 1 | ✅ |
| algo_handlers/dashboard.py | _get_portfolio_dashboard | 1 | ✅ |
| market.py | _get_naaim_sentiment | 2 | ✅ |
| sentiment.py | _get_vix_sentiment | 1 | ✅ |
| **Total** | **6 endpoints** | **8 changes** | **✅** |

---

## Testing Strategy

### 1. Syntax Validation ✅
All modified files pass Python syntax checks.

### 2. Type Checking
Pre-existing mypy issues in signals.py (unrelated to these changes).

### 3. Linting
Files auto-formatted by linter - no blocking issues.

### 4. Behavior Changes
- **Before:** Endpoints returned 200 with null/empty values when data unavailable
- **After:** Endpoints return 503 error responses with descriptive messages
- **Client Impact:** Explicit data availability checks instead of null handling

---

## Historical Context

**Previous Session (2026-06-21):** 15 orchestrator/infrastructure fail-fast conversions completed
- Circuit breakers, audit logging, reconciliation functions

**This Session (2026-06-22):** 6 API endpoint fail-fast conversions completed
- Market data, configuration, monitoring, sentiment endpoints

**Total Progress:** 21 fail-fast conversions across system

---

## Error Response Format

All fail-fast endpoints now return:

```python
error_response(HTTP_STATUS, "error_code", "Human-readable message")
```

Standard status codes:
- **404:** Key/resource not found (config lookups)
- **503:** Data not available (loaders haven't run, tables empty)

---

## Backward Compatibility

⚠️ **Breaking Changes**

Clients relying on 200 responses with null fields must update:

**Old behavior:**
```python
resp = GET /api/market-factors
if resp.exposure_pct is None:  # Ambiguous - is data loading or not available?
    wait_for_data()
```

**New behavior:**
```python
resp = GET /api/market-factors
if resp.status == 503:  # Explicit - data not available, retry
    wait_for_data()
elif resp.status == 200:  # Data is present
    use_data(resp)
```

**Migration:** Dashboard and frontend must handle 503 responses for these endpoints.

---

## Verification Checklist

- [x] 6 endpoints converted from fallback to fail-fast
- [x] Python syntax checks pass
- [x] Linting passes
- [x] Error messages include context
- [x] HTTP status codes accurate (404 for not_found, 503 for unavailable)
- [x] No import changes needed

---

## Next Steps

1. **Monitor logs** for 503 responses from these endpoints
2. **Update frontend** to handle 503 responses (show loading state)
3. **Run integration tests** to verify orchestrator/dashboard workflows
4. **Update API documentation** with new error responses
5. **Monitor client error rates** for old code still expecting 200

---

## Related Documents

- `steering/FALLBACK_FIXES_COMPLETED.md` — Previous session's 15 fixes
- `steering/FALLBACK_FIXES_TASKS.md` — Original task breakdown
- `steering/REFERENCE_GOVERNANCE.md` — Error handling patterns
