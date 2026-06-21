# API Response Validation Strategy

Single source of truth for API validation across the platform. All responses pass through one of two canonical validators based on the direction and layer.

## Two-Tier Validation Architecture

**Layer 1: Outbound Response Validation** (Lambda API Routes)
- **Location:** `lambda/api/routes/utils.py`
- **Canonical Validator:** `ResponseValidator.validate_endpoint_response()` from `shared_contracts/response_validator.py`
- **Purpose:** Validate Lambda API responses conform to published contract BEFORE returning to client
- **Trigger:** ALL responses from `lambda/api/routes/*.py` must validate against contract schema
- **Failure Mode:** Log warning (validation is optional, does not fail request — for gradual migration)

**Layer 2: Inbound Response Validation** (Dashboard Data Layer)
- **Location:** `tools/dashboard/api_data_layer.py`
- **Canonical Validator:** 15+ specialized validators in `tools/dashboard/response_validators.py`
- **Purpose:** Validate inbound API responses at dashboard boundary (fail-fast, prevent data corruption)
- **Trigger:** Called by `api_data_layer.py:api_call()` on all inbound responses
- **Failure Mode:** Return `{"_error": "message"}` on validation failure (fail-fast)

**DO NOT CONFLATE:** These validators serve different purposes. Using one in the other's context defeats both.

---

## Schema Registry: dashboard_api_contract.py

Central source of truth for all API endpoint definitions. Contains:

```python
DASHBOARD_ENDPOINTS = {
    "run": {
        "path": "/api/algo/last-run",
        "method": "GET",
        "response_schema": ResponseSchema(
            required_fields=["run_id", "completed_at", "started_at", "success"],
            optional_fields=["halted", "errored", "summary", ...],
            field_types={"run_id": (str, int), "success": bool, ...}
        ),
        "strict_fields": ["run_id", "success"],  # Must never be None
        "critical": True,  # Dashboard won't render without this
    },
    ...
}
```

**When Adding New Endpoints:**
1. Define in `DASHBOARD_ENDPOINTS` with full schema
2. Update `ResponseSchema` with required/optional fields and types
3. Register `strict_fields` (fields that must never be None)
4. Update Lambda route to return this schema exactly
5. Dashboard automatically uses this definition — no manual synchronization needed

---

## Lambda API Routes: Outbound Response Validation

**Current State:** 37 Lambda route files using `json_response()`/`error_response()`. Only 4 files actively validate responses using `ResponseValidator`.

**Requirements for All Lambda Routes:**
1. Validate response against contract BEFORE returning
2. Catch validation failures and log (not fail request)
3. Return response with correct HTTP status code
4. Include `_error` field in ALL error responses for consistency

**Implementation Pattern:**

```python
from shared_contracts.response_validator import ResponseValidator

def handle_get_portfolio(cur):
    # ... fetch data from database ...
    
    response_data = {
        "total_portfolio_value": 100000.50,
        "total_cash": 25000.00,
        "open_positions": 3
    }
    
    # Validate response matches contract (logs warning if invalid)
    is_valid, error_msg = ResponseValidator.validate_endpoint_response(
        "port",  # Endpoint name from DASHBOARD_ENDPOINTS
        response_data
    )
    if not is_valid:
        logger.warning(f"Response validation failed: {error_msg}")
    
    # Return response (validation failure does not fail request)
    return json_response(200, response_data)
```

**Migration Timeline:**
- Phase 1 (now): Add validation calls to 10+ high-traffic routes
- Phase 2 (2 weeks): Add to remaining 25+ routes
- Phase 3 (4 weeks): Flip validation from warning to error (fail-closed)

---

## Dashboard Data Layer: Inbound Response Validation

**Current State:** Fully implemented. All responses validated at `api_data_layer.py:api_call()` using specialized validators.

**Key Pattern:** Fail-fast, no silent defaults.

```python
# In api_data_layer.py
response = requests.get(url, timeout=5)
data = response.json()

# Validate response
try:
    validated_data = validate_portfolio_response(data)
    return validated_data
except ResponseValidationError as e:
    logger.error(f"Portfolio validation failed: {e}")
    return {"_error": str(e)}  # Fail-fast, no fallback fields
```

---

## Old Pattern: `.get(None)` Anti-Pattern

**DO NOT USE** this pattern — it masks validation failures:

```python
# ❌ WRONG: Silent defaults hide missing data
position_value = data.get("position_value")  # Returns None if missing
if position_value is None:
    position_value = 0  # Silent fallback, error never surfaces
```

**USE INSTEAD:**

```python
# ✅ CORRECT: Validate at boundary, fail-fast
if "_error" in data:
    return error_summary_panel(data["_error"])

# Access directly (validation guaranteed field exists)
position_value = data["position_value"]

# For truly optional fields:
yield_curve = data.get("yield_curve", None)  # OK: documented as optional
```

---

## Error Response Format

**All error responses must include `_error` field:**

```python
# Success response
{
    "statusCode": 200,
    "data": {
        "total_portfolio_value": 100000.50,
        "total_cash": 25000.00,
        "open_positions": 3
    }
}

# Error response (validation failure, database error, etc)
{
    "statusCode": 503,
    "errorType": "ServiceUnavailable",
    "message": "Portfolio endpoint returned invalid response",
    "_error": "Portfolio endpoint returned invalid response"  # REQUIRED
}
```

The `_error` field enables consistent error detection across dashboard.

---

## Critical Fields That Must Never Be None

These fields are marked `strict_fields` in contracts. If missing/None, validation fails:

| Endpoint | Critical Fields |
|----------|-----------------|
| `run` | `run_id`, `success` |
| `mkt` | `spy_close`, `vix_level` |
| `port` | `total_portfolio_value`, `total_cash`, `open_positions` |
| `perf` | `n`, `w`, `l`, `streak` |
| `pos` | `symbol`, `quantity`, `avg_entry_price`, `current_price` |
| `trade` | `symbol`, `entry_price`, `exit_price`, `pnl`, `pnl_pct` |
| `sig` | `symbol`, `signal_type`, `strength` |

If ANY strict field is None, validation returns error. No fallback defaults.

---

## Centralized Validator Registry

Future enhancement: Create `ValidatorRegistry` in `shared_contracts/` to auto-generate validators from contract definitions, eliminating manual validator maintenance.

**Current Workaround:** Dashboard validators in `response_validators.py` are hand-written specializations for fail-fast semantics. Lambda validators in `response_validator.py` are generic schema-based.

**Path Forward:**
1. Keep both validators separate (different purposes)
2. Use shared `DASHBOARD_ENDPOINTS` as SSoT
3. Auto-generate Lambda validators from schema (Phase 4)

---

## Implementation Checklist

- [ ] Fix recursive `safe_float()` call in `lambda/api/routes/utils.py` (DONE)
- [ ] Add `ResponseValidator` import to 10 high-traffic Lambda routes
- [ ] Add validation calls to 10 high-traffic Lambda routes (logging mode)
- [ ] Add `_error` field to all error_response() calls
- [ ] Document which endpoints use which validator
- [ ] Review 50 files with `.get(None)` patterns and convert to fail-fast
- [ ] Create test coverage for validation failures
- [ ] Update API documentation with validation requirements
- [ ] Schedule migration to strict validation mode (Phase 3)

---

## References

- `shared_contracts/dashboard_api_contract.py` — Endpoint definitions & schemas
- `shared_contracts/response_validator.py` — Lambda outbound validator (generic)
- `tools/dashboard/response_validators.py` — Dashboard inbound validators (specialized)
- `lambda/api/routes/utils.py` — Lambda utilities & error response helpers
- `CLAUDE.md` → "Response Validator Architecture" section
